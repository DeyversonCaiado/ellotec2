"""
Configuração do banco do sistema de origem (Oracle), lida do .env.

Por que não sai de `core/settings.py`, que é onde toda config do projeto mora:
`shared/*` não pode importar de `core/*` (ver ARCHITECTURE.md → "Regras de
import entre domínios"), e este pacote foi colocado em `shared/` de propósito.
Para a regra continuar valendo, o pacote lê o próprio recorte do .env — mesmo
arquivo, mesmas variáveis, só que sem criar a dependência de volta.

É a única exceção à frase "nenhum outro lugar do código lê variável de ambiente
direto" que existe no projeto, e ela existe por causa da posição do pacote. Se
um dia `sistema_origem` for movido para `core/`, esta classe deve ser apagada e
os campos passam para `core/settings.py`.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class OracleSettings(BaseSettings):
    # Prefixo ELLOTEC_ em todas: são as mesmas variáveis já usadas pelos outros
    # projetos que falam com este ERP, e repetir o nome de lá evita duas
    # convenções para a mesma credencial. Assim `oracle_user` lê
    # ELLOTEC_ORACLE_USER, e assim por diante.
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="ELLOTEC_"
    )

    oracle_user: str = ""
    oracle_password: str = ""
    # Ex: "servidor:1521/ORCL" — a mesma string que o cliente Oracle aceita.
    oracle_dsn: str = ""

    # Schema e função de contexto que o ERP exige logo após conectar. Sem eles a
    # sessão enxerga o schema errado e as tabelas "não existem".
    oracle_schema: str = "GESTCOM"
    oracle_funcao_contexto: str = "GESTCOM2009"

    # Diretório do Oracle Instant Client. OBRIGATÓRIO: o servidor do ERP é
    # antigo e o modo thin do `oracledb` recusa a conexão com
    # "DPY-3010: connections to this database server version are not supported
    # by python-oracledb in thin mode". Não existe fallback para thin — sem
    # client, não conecta.
    #
    # No Windows, escreva o caminho com barra normal (C:/oracle/...): barra
    # invertida em arquivo .env vira escape.
    oracle_client_dir: str = ""

    # Código do usuário gravado em `USUARIO_ALTERACAO` no ERP. É um código do
    # cadastro de lá, não o id do usuário daqui — por isso é configuração, e
    # não algo derivado do usuário logado.
    oracle_usuario_alteracao: str = "00200"

    @property
    def configurado(self) -> bool:
        # O client entra na conta: sem ele a conexão falha de qualquer jeito, e
        # é melhor dizer "não configurado" do que deixar o driver errar lá na
        # frente com uma mensagem que não aponta para o .env.
        return bool(
            self.oracle_user
            and self.oracle_password
            and self.oracle_dsn
            and self.oracle_client_dir
        )


@lru_cache
def obter_oracle_settings() -> OracleSettings:
    return OracleSettings()
