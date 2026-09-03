from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.auth.seguranca import verificar_senha
from app.domains.usuarios.usuario_model import Usuario, UsuarioPermissao


def obter_id_por_sistema_origem_id(sessao_db: Session, sistema_origem_id: str) -> str | None:
    """Só leitura — devolve o id primitivo, nunca o model. Canal usado por
    outros domínios (ex: pedidos) para resolver um usuário/vendedor pelo id
    do sistema de origem sem importar `usuario_service`."""
    usuario = (
        sessao_db.query(Usuario)
        .filter(Usuario.sistema_origem_id == sistema_origem_id, Usuario.sync_deleted_at.is_(None))
        .first()
    )
    return usuario.id if usuario else None


def obter_sistema_origem_id(sessao_db: Session, usuario_id: str) -> str | None:
    """O caminho inverso de `obter_id_por_sistema_origem_id`: o código do
    funcionário no ERP a partir do nosso id.

    É LEITURA do campo de vínculo, não escrita — a regra de nunca apagar
    `sistema_origem_id` (ver ARCHITECTURE.md) não se aplica aqui. Existe porque
    o ERP grava a conferência em nome de um código de funcionário DELE, e o
    usuário logado é o nosso.
    """
    usuario = (
        sessao_db.query(Usuario)
        .filter(Usuario.id == usuario_id, Usuario.sync_deleted_at.is_(None))
        .first()
    )
    return usuario.sistema_origem_id if usuario else None


def obter_login(sessao_db: Session, usuario_id: str) -> str | None:
    """O login do usuário — o que ele digita para entrar, não o nome de
    exibição. Existe para mensagem de erro poder dizer de qual CONTA está
    falando quando a pessoa tem mais de uma."""
    usuario = (
        sessao_db.query(Usuario)
        .filter(Usuario.id == usuario_id, Usuario.sync_deleted_at.is_(None))
        .first()
    )
    return usuario.usuario if usuario else None


def obter_nomes(sessao_db: Session, usuario_ids: list[str]) -> dict[str, str]:
    """usuario_id -> nome, numa consulta só. Para telas em lista, onde um
    `obter_nome` por linha viraria dezenas de idas ao banco por página."""
    if not usuario_ids:
        return {}
    linhas = (
        sessao_db.query(Usuario.id, Usuario.nome)
        .filter(Usuario.id.in_(set(usuario_ids)))
        .all()
    )
    return dict(linhas)


def obter_nome(sessao_db: Session, usuario_id: str) -> str | None:
    """Só leitura — o nome de exibição do usuário (ex: o vendedor impresso no
    cabeçalho da lista de separação)."""
    usuario = (
        sessao_db.query(Usuario)
        .filter(Usuario.id == usuario_id, Usuario.sync_deleted_at.is_(None))
        .first()
    )
    return usuario.nome if usuario else None


@dataclass(frozen=True)
class UsuarioResumo:
    """O mínimo para montar um seletor de pessoas em outra tela."""

    id: str
    nome: str


def listar_por_permissao(sessao_db: Session, chave: str) -> list[UsuarioResumo]:
    """Usuários ativos que têm a permissão `chave`, ordenados por nome.

    Existe para o seletor de responsável da expedição: só faz sentido atribuir
    uma separação a quem pode executá-la. Quem sabe ler `usuario_permissoes` é
    este domínio — a expedição pergunta em vez de consultar a tabela por conta
    própria (ver ARCHITECTURE.md → "Regras de import entre domínios").
    """
    usuarios = (
        sessao_db.query(Usuario)
        .join(UsuarioPermissao, UsuarioPermissao.usuario_id == Usuario.id)
        .filter(
            UsuarioPermissao.chave == chave,
            Usuario.ativo.is_(True),
            Usuario.sync_deleted_at.is_(None),
        )
        .order_by(Usuario.nome.asc())
        .all()
    )
    return [UsuarioResumo(id=usuario.id, nome=usuario.nome) for usuario in usuarios]


def validar_credencial_de_cargo(
    sessao_db: Session, login: str, senha: str, cargo_nome: str
) -> str | None:
    """
    Confere usuário + senha e exige que o cargo seja `cargo_nome`. Devolve o
    id do usuário quando tudo bate, senão None — nunca diz QUAL das condições
    falhou, pra não virar oráculo de "esse login existe?".

    Isso mora aqui, e não no domínio que chama, porque conferir credencial é
    regra de `usuarios` (é ele que conhece `senha_hash` e `cargo`). O
    consumidor — hoje a expedição, no override de gerente para resetar um
    processo ou finalizar item com falta — pergunta, não reimplementa.

    Não cria sessão nem emite token: é uma autorização pontual de uma ação,
    não um login. Quem está logado continua sendo quem estava.
    """
    usuario = (
        sessao_db.query(Usuario)
        .filter(Usuario.usuario == login, Usuario.sync_deleted_at.is_(None))
        .first()
    )
    if usuario is None or not usuario.ativo:
        return None
    if usuario.cargo.nome != cargo_nome:
        return None
    if not verificar_senha(senha, usuario.senha_hash):
        return None
    return usuario.id
