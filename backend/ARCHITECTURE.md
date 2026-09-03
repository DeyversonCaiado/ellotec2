# ARCHITECTURE.md — ELLOTEC ERP API

> Referência principal para qualquer pessoa ou agente de IA que for manter,
> estender ou refatorar este backend. Leia antes de tocar em código. Segue a
> mesma filosofia do `ARCHITECTURE.md` do front (`ELLOTEC-erp/ARCHITECTURE.md`)
> — vale a pena ler os dois juntos, já que os contratos de domínio e
> permissão precisam continuar idênticos nos dois lados.

## Filosofia geral

Mesma de sempre: **estratégico primeiro, flat, abstrai por dor.**

1. **Pasta por domínio**, não por camada técnica. `app/domains/usuarios/`
   junta tudo que o domínio usuário precisa: model, contrato, service, router.
   Não existe `app/models/`, `app/routers/`, `app/schemas/` na raiz cortando
   o projeto inteiro por tipo de arquivo.
2. **Dentro de cada domínio, 4 arquivos com responsabilidade clara**:
   - `*_model.py` — tabela SQLAlchemy. Só estrutura e relações, zero regra
     de negócio.
   - `*_contrato.py` — contratos Pydantic de entrada/saída. Zero SQL, zero HTTP.
   - `*_service.py` — regra de negócio e queries. Não conhece HTTP.
   - `*_router.py` — camada HTTP: rota, status code, dependency de permissão.
     Chama o service, não reimplementa regra de negócio.

   `*_contrato.py` tem esse nome (e não `*_schema.py`) porque é literalmente
   o contrato da API: o que entra, o que sai, e o que é recusado na entrada.
3. **Abstrai por dor.** Não tem repository pattern, não tem `IUsuarioRepo`
   + implementação trocável — porque hoje não existe a dor de trocar ORM/banco.
4. **Contratos fortes entre domínios.** `PERMISSOES_VALIDAS`
   (`core/permissions/permission_model.py`) é o contrato único de permissão,
   nunca reimplementado com strings soltas em algum service avulso.

## Estrutura de pastas

```
app/
├── core/                              # infraestrutura transversal
│   ├── settings.py                    # toda config vem daqui (lida de .env)
│   ├── database/
│   │   ├── conexao.py                 # engine, SessionLocal, Base, dependency obter_sessao
│   │   └── todos_os_models.py         # importa todos os models para registrar no metadata
│   ├── auth/
│   │   ├── auth_contrato.py           # LoginPayload, LoginResponse, etc.
│   │   ├── auth_service.py            # orquestra login: senha + dispositivo + sessão + JWT
│   │   ├── auth_router.py             # /auth/login, /auth/refresh, /auth/logout, /auth/me
│   │   ├── seguranca.py               # hash de senha, geração/validação de JWT, hash de refresh token
│   │   ├── dispositivo_model.py       # tabela `dispositivos`
│   │   ├── dispositivo_service.py     # identifica/registra/valida dispositivo (fingerprint)
│   │   ├── fingerprint.py             # cálculo do hash de fingerprint server-side
│   │   ├── sessao_model.py            # tabela `sessoes` (refresh tokens)
│   │   ├── sessao_service.py          # cria/revoga sessão
│   │   └── dependencies.py            # obter_usuario_atual, exigir_permissao — usados em TODO endpoint
│   └── permissions/
│       ├── permission_model.py        # PERMISSOES_VALIDAS (chave flat) — mesmo contrato do front
│       └── permission_contrato.py     # validar_chaves_permissao — usado nos schemas que carregam `permissoes: list[str]`
├── domains/                           # 4 arquivos por domínio — ver "Regras de import entre domínios"
│   ├── usuarios/                      # CRUD de usuários + matriz de permissões
│   ├── clientes/                      # CRUD de clientes
│   ├── produtos/                      # CRUD de produtos
│   ├── pedidos/                       # CRUD de pedidos
│   ├── estoque/                       # saldo por produto e por lote
│   └── enderecamento/                 # endereços do galpão e o lote em cada um
│   └── sistema_origem/                # o que o ELLOTEC manda o ERP fazer (sem tabela nossa)
├── shared/
│   ├── sync_mixin.py                  # SyncMixin (5 campos sync_*) + IdMixin (UUID)
│   ├── sync_helpers.py                # marcar_apagado(), incrementar_versao()
│   ├── contrato_base.py               # ContratoBase — base de todos os contratos Pydantic (camelCase)
│   └── router_base.py                 # RouterBase — APIRouter com response_model_by_alias=True
└── main.py                            # registra routers, CORS, metadados do FastAPI/OpenAPI
alembic/                               # migrações de schema (geradas com --autogenerate)
scripts/seed.py                        # popula banco com admin + dados de exemplo
```

## Segurança: o que o backend garante e por quê

### Toda permissão é checada no backend, sempre

O front tem guards de rota e diretivas de UI que escondem botões sem
permissão — mas isso é só UX. A barreira real é o backend. Todo endpoint de
domínio usa `exigir_permissao("dominio.contexto.acao")` (`core/auth/dependencies.py`),
que em sequência:

1. Valida o JWT (assinatura + expiração).
2. Confirma que o usuário existe, está ativo, não foi soft-deletado.
3. Confirma que o `device_id` do header `X-Device-Id` bate com o
   `dispositivo_id` gravado no JWT.
4. Busca a permissão do usuário pro domínio e verifica a ação específica.

Qualquer falha → 401 ou 403 antes de qualquer service de domínio ser chamado.

### Autenticação: JWT curto + sessão revogável

- **Access token (JWT)**: 30 min, nunca persistido, só verificado por assinatura.
  Carrega `sub` (usuario_id) e `dispositivo_id`.
- **Refresh token**: opaco (não JWT), 30 dias, persistido como **hash SHA-256**
  em `sessoes`. Permite revogar acesso remotamente sem esperar o access token
  expirar. Se o banco vazar, ninguém ganha sessões válidas — pelo mesmo motivo
  que nunca se guarda senha em texto puro.

### Identificação de dispositivo (duas camadas)

**Por que não só fingerprint?** Fingerprint de navegador muda com frequência
natural (atualização de browser, troca de rede, modo anônimo) e geraria logout
indevido constantemente.

A solução usa duas camadas complementares:

1. **`device_id` (âncora principal)**: UUID gerado uma única vez pelo cliente,
   salvo em localStorage, enviado em todo request no header `X-Device-Id`. Não
   muda com atualização de navegador nem troca de rede — é a parte "imutável"
   pedida. O JWT carrega o `dispositivo_id` correspondente, e todo request
   autenticado confirma que o header `X-Device-Id` bate com o registro do banco
   — proteção contra uso de token roubado em outro dispositivo.

2. **`fingerprint_hash` (plausibilidade)**: hash SHA-256 de User-Agent +
   Accept-Language + 3 primeiros octetos do IP. Calculado a cada login e
   comparado com o salvo. Diferença não derruba a sessão — só incrementa
   `contador_anomalias`. Acima do limite configurado, marca o dispositivo como
   não confiável e bloqueia requests futuros daquele device_id.

## O contrato de permissões (mesmo modelo do front)

Tudo de permissão gira em torno de `core/permissions/permission_model.py`.
Não existe mais o par `(DominioId, Acao)` com ações fixas de CRUD — qualquer
funcionalidade de negócio, seja ela CRUD ou não, vira uma chave nomeada no
padrão `dominio.contexto.acao`, exatamente como documentado no
`ARCHITECTURE.md` do front (`PermissaoKey`).

```python
# FRAGMENTO ILUSTRATIVO — não é o conteúdo completo do arquivo
# Arquivo real: core/permissions/permission_model.py

PERMISSOES_VALIDAS: list[str] = [
    "usuarios.acessar",
    "usuarios.gravar.incluir",
    "usuarios.gravar.editar",
    "usuarios.apagar",
    "pedidos.acessar",
    "pedidos.gravar.incluir",
    "pedidos.gravar.editar",
    "pedidos.apagar",
    "pedidos.condicao_pagamento.aplicar",
    # ... demais domínios estão no arquivo real
]
```

### Armazenamento: uma linha por chave marcada

A tabela `usuario_permissoes` (`domains/usuarios/usuario_model.py`) tem uma
linha por `(usuario_id, chave)` marcada — não mais uma linha por domínio com
4 colunas booleanas. `UsuarioPermissao.chave` é uma string livre do catálogo
`PERMISSOES_VALIDAS`, validada nos schemas de entrada
(`validar_chaves_permissao` em `permission_contrato.py`) antes de chegar no
banco. Dar ou tirar uma permissão de um usuário é inserir ou apagar uma
linha; `usuario_service._sincronizar_permissoes` recebe o conjunto de chaves
desejado e recalcula o diff (insere o que faltar, apaga o que sobrar) a cada
`criar`/`atualizar`.

### Serialização: array de strings de ponta a ponta

`UsuarioRespostaSchema.permissoes`, `UsuarioLogadoSchema.permissoes`,
`UsuarioCriarSchema.permissoes` e `UsuarioAtualizarSchema.permissoes` são
todos `list[str]` — o mesmo formato que o front espera para hidratar
`Set<PermissaoKey>` em `AuthService.login()`. Não serializar como objeto por
domínio nunca mais; é sempre lista plana de chaves marcadas.

### Como checar no código

```python
# FRAGMENTO ILUSTRATIVO — padrão de implementação, não o arquivo completo

# core/auth/dependencies.py
def exigir_permissao(chave: str):
    def verificar(ctx: ContextoRequisicao = Depends(obter_usuario_atual)) -> ContextoRequisicao:
        tem_permissao = any(p.chave == chave for p in ctx.usuario.permissoes)
        if not tem_permissao:
            raise HTTPException(status_code=403, detail=f"Permissão negada: requer '{chave}'.")
        return ctx
    return verificar

# Uso num router de domínio
@router.get("", dependencies=[Depends(exigir_permissao("produtos.acessar"))])
def listar(...): ...
```

### Adicionando uma nova permissão

1. Adicione a chave em `PERMISSOES_VALIDAS` (`permission_model.py`), seguindo
   a convenção `dominio.contexto.acao`.
2. Adicione a mesma chave em `PermissaoKey`/`ARVORE_PERMISSOES` no front
   (`core/permissions/permission.model.ts`) — os dois lados precisam ficar
   em sync manualmente, não existe geração automática entre eles.
3. Aplique `exigir_permissao("chave")` no(s) endpoint(s) que a usam.
4. Se for uma permissão administrável por usuário comum (não só técnica),
   garanta que ela apareça na árvore de permissões do form de usuário no front.
5. Gere uma migração Alembic apenas se a mudança afetar estrutura de tabela —
   adicionar uma chave nova ao catálogo não exige migração, já que
   `usuario_permissoes.chave` é uma coluna de texto livre.

## Campos de sincronização (SyncMixin)

Todas as tabelas de negócio têm 5 campos obrigatórios:

| Campo | Propósito |
|---|---|
| `sync_created_at` | quando o registro nasceu (imutável após insert) |
| `sync_updated_at` | quando mudou pela última vez (auto via `onupdate`) |
| `sync_deleted_at` | soft delete — NULL = vivo. Nunca DELETE físico em negócio |
| `sync_version` | contador otimista, incrementado em toda escrita |
| `sync_synced_at` | quando foi confirmado replicado a outro nó (NULL = pendente) |

**Regras inegociáveis:**

- **Nenhum campo `sync_*` participa de regra de negócio.** Ver a seção logo
  abaixo — esta é a regra mais fácil de violar sem perceber.
- Nenhum service de domínio chama `sessao.delete(registro)` em model com
  `SyncMixin`. Sempre `marcar_apagado(registro)` de `shared/sync_helpers.py`.
- `sync_synced_at` é gerenciado por processo de sincronização futuro — nenhum
  service de domínio escreve nesse campo.
- PKs são UUID (não auto-increment) — sistema distribuído não pode usar
  auto-increment porque duas réplicas offline colidiriam IDs na sincronização.

### Os campos `sync_*` nunca entram na regra de negócio

Eles descrevem **a linha**, não o **fato** que a linha representa. É proibido
usá-los como dado de negócio, em qualquer domínio:

| Uso | Permitido? |
|---|---|
| Ordenar eventos (linha do tempo, histórico, ocorrências) por `sync_created_at` | **Não** |
| Devolver `sync_created_at`/`sync_updated_at` como um fato ("registrado em", "entregue em") | **Não** |
| Filtrar período por `sync_updated_at` | **Não** — o período é sempre a data de negócio |
| Calcular prazo, SLA ou idade do documento a partir deles | **Não** |
| Decidir qual registro é "o mais recente" numa regra | **Não** |
| Diagnosticar quando a linha foi tocada pela integração | Sim — é para isso que existem |
| Alimentar o futuro worker de replicação (`sync_synced_at`) | Sim |

**O motivo é concreto, não estético.** Um reprocessamento da integração, uma
correção de texto ou a futura rotina de replicação tocam a linha e mexem em
`sync_updated_at` sem que nada tenha acontecido no negócio. Quem ordenou por
`sync_created_at` vê a ordem mudar sozinha; quem filtrou por `sync_updated_at`
vê o documento entrar e sair do período; quem calculou prazo a partir deles
passa a medir o tempo desde o último reprocessamento.

Há ainda um motivo técnico que pega mesmo quem "só queria ordenar":
`sync_created_at` é `DATETIME` sem precisão fracionária, ou seja, resolução de
**segundo**. Dois registros criados no mesmo segundo empatam, e o desempate cai
no `id` — que é UUID, aleatório e não cronológico. O "mais recente" vira
sorteio. Foi exatamente isso que aconteceu na linha do tempo da gestão de
entregas antes da correção.

**Quando o negócio precisa de um instante, crie uma coluna própria** e
preencha-a explicitamente no service:

```python
# FRAGMENTO ILUSTRATIVO — app/domains/entregas/entrega_model.py

class EntregaNotaInteracao(Base, IdMixin, SyncMixin):
    # O instante do EVENTO — é dele que a timeline ordena e é ele que a tela
    # exibe. Nasce igual à data de inclusão, mas é campo de negócio: se um dia
    # a interação puder ser lançada com data retroativa, é aqui que a data vai.
    data_interacao: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    # A ordem dentro da nota, imune a empate de segundo no relógio.
    sequencia: Mapped[int] = mapped_column(Integer, nullable=False)
```

O mesmo raciocínio vale para soft delete: `sync_deleted_at` diz que a linha foi
removida, e não *por que* nem *quando o negócio cancelou algo* — se essa
informação importa, ela tem coluna própria.

## O vínculo com o sistema de origem nunca é apagado

Todo campo cujo nome termina em **`sistema_origem_id`** guarda a identidade do
registro no ERP: `sistema_origem_id`, `empresa_sistema_origem_id`,
`pedido_sistema_origem_id`, `produto_sistema_origem_id`. Eles existem em
praticamente todo domínio que a integração alimenta — clientes, produtos,
marcas, empresas, usuários, pedidos, estoque, endereçamento, entregas e notas
fiscais.

**A regra é uma frase:** uma gravação que não traz o campo **não o apaga**.

A ordem de precedência, sempre a mesma, é:

1. o valor que o **corpo** da requisição trouxe;
2. senão, o valor pelo qual o registro foi **localizado** (o query param que a
   integração usa em `PUT /recurso/{id}?sistema_origem_id=...`);
3. senão, **o que já estava gravado**.

Apagar o vínculo é operação explícita, e hoje não existe endpoint para ela. Se
um dia existir, será um caminho próprio, com nome próprio — nunca o efeito
colateral de um formulário que sequer exibe o campo.

### O incidente que criou a regra

Faltava o degrau 3, e a falta era invisível: a tela de usuários não exibe nem
envia `sistemaOrigemId`, e edita **pelo id**, sem o query param. Os dois
primeiros degraus davam `None`, e o campo era zerado em silêncio — sem erro, sem
log, com `sync_version` incrementando normalmente.

O funcionário `00168` perdeu o vínculo assim. A consequência apareceu **dias
depois e em outro domínio**: todo pedido daquele vendedor passou a responder
`404 Vendedor não encontrado para o sistema de origem informado`, o sincronizador
levantou `RuntimeError`, o processo morreu, o systemd reiniciou, e o ciclo se
repetiu a cada 30 segundos. A integração de pedidos ficou **três dias parada**,
com 173 pedidos represados, enquanto o `systemctl status` mostrava
`active (running)`.

Guarde a forma do defeito, que é o que se repete: **a escrita errada é barata e
silenciosa; a conta chega longe dali.**

### Como se faz

A regra mora em **`app/shared/vinculo_origem.py`**, num lugar só. Não escreva a
cadeia de `or` à mão — a versão manual já foi escrita errado em dez arquivos ao
mesmo tempo.

**Campo a campo**, quando o service atribui direto:

```python
# FRAGMENTO ILUSTRATIVO
from app.shared.vinculo_origem import resolver as resolver_vinculo_origem

nota.sistema_origem_id = resolver_vinculo_origem(
    dados.sistema_origem_id, ja_gravado=nota.sistema_origem_id
)
```

**Dicionário**, quando o service faz `model_dump()` + laço de `setattr` — cuida
de todos os campos de vínculo de uma vez, inclusive os compostos:

```python
# FRAGMENTO ILUSTRATIVO
from app.shared.vinculo_origem import preservar_no_dicionario

campos = dados.model_dump()
preservar_no_dicionario(campos, cliente, da_busca=sistema_origem_id)

for campo, valor in campos.items():
    setattr(cliente, campo, valor)
```

`da_busca` só se aplica ao campo `sistema_origem_id`, que é a identidade
**deste** registro. Os compostos referenciam **outro** registro, e a chave que
localizou este não diz nada sobre eles.

### O que NÃO precisa da regra

**Criação.** Não há valor anterior a preservar, então
`Usuario(sistema_origem_id=dados.sistema_origem_id)` está correto como está.

**Leitura.** Passar o valor como argumento nomeado ao montar um schema de
resposta (`UsuarioRespostaSchema(sistema_origem_id=usuario.sistema_origem_id)`)
é leitura, não escrita.

### Como isso é cobrado

`tests/test_vinculo_origem.py` faz uma **varredura em todos os services** com
`ast`: para cada função que atribui a um campo de vínculo, exige que a função
use `vinculo_origem`. Um domínio novo que escreva por fora quebra o teste com o
nome do arquivo e da função.

Isso é deliberado: o defeito original apareceu em dez arquivos ao mesmo tempo, e
nenhum teste por domínio teria pego todos. Se o teste falhar no seu código, não
é para contorná-lo — é para usar a regra.

## Regras de import entre domínios

> Esta seção é a **autoridade** sobre o que pode atravessar a fronteira de um
> domínio. Se algum outro trecho deste documento parecer dizer outra coisa,
> vale o que está escrito aqui.

### Direção dos imports (regras estruturais)

- `domains/*` pode importar de `core/*` e `shared/*` livremente.
- `core/*` pode importar de `shared/*` (é por isso que `SyncMixin` mora em
  `shared/sync_mixin.py` e não em `core/database/`: os models de `core/auth`
  e os de `domains/*` precisam dele, e assim `shared/` não precisa importar
  nada de volta).
- `core/*` nunca importa de `domains/*` — **com uma exceção declarada:
  `core/auth`, que importa os models de `domains/usuarios`. Ver "A exceção
  de `core/auth` ↔ `domains/usuarios`" abaixo.**
- `shared/*` nunca importa de `core/*` nem de `domains/*`.
- `domains/X` importa de `domains/Y` **somente** nas formas autorizadas
  abaixo — nunca de outra forma.

### O critério que decide tudo: o que está atravessando a fronteira

A pergunta certa não é *"esses dois domínios podem se conhecer?"*. É
**"o que está passando de um para o outro?"**:

| O que atravessa | Permitido? |
|---|---|
| **Leitura** — perguntar um dado ou um cálculo | Sim, por um canal declarado |
| **Escrita** — pedir ao dono que altere o estado dele | Sim, pelo mesmo canal, e **sem `commit()`** |
| **Escrita direta** — dar `sessao_db.add`/`delete`/`commit` na tabela do outro | Não. Nunca. |
| **Regra reimplementada** — recalcular por conta própria o que é regra do outro | Não. Nunca. |

Um domínio é **dono** dos seus dados e das suas regras. Os outros podem
*perguntar* e *pedir*, nunca *mexer por conta própria*, e nunca *adivinhar*.

A diferença entre as duas linhas de escrita é quem executa a mudança. `pedir`
é chamar uma função que o dono escreveu, que valida as regras dele e falha se
elas não fecharem. `mexer` é o chamador manipular a tabela alheia direto — aí
a regra do dono deixa de existir, porque ninguém a executou.

### O que PODE (com exemplos concretos)

| Caso | Exemplo em ERP | Como se faz |
|---|---|---|
| FK para uma tabela de cadastro | `clientes.cidade_id` → `cidades.id` | `cliente_model.py` importa **apenas o model** `Cidade` |
| Exibir dado vivo do cadastro referenciado | listagem de clientes mostrando o nome da cidade | `relationship()` no model, ou `cidade_publico.py` |
| Pedir um cálculo ao dono da regra | `pedidos` perguntando o preço atual a `produtos` | `produto_publico.obter_preco(sessao_db, produto_id)` |
| **Pedir ao dono que altere o estado dele** | a expedição baixando o saldo do endereço ao finalizar a separação | `enderecamento_publico.baixar_lote(sessao_db, lote_id, qtd)` — **sem `commit()`** |
| Validar que um id existe | criar pedido com `cliente_id` | **não importa nada** — a FK do banco recusa |

### O que NÃO PODE (com exemplos concretos)

| Caso | Exemplo em ERP | Por que é proibido |
|---|---|---|
| Query na tabela de outro domínio | `sessao_db.query(Cidade)` dentro de `cliente_service.py` | Se a tabela mudar, quebra em N domínios de uma vez. É a duplicação que a regra existe para impedir |
| Importar o `_service` de outro domínio | `from app.domains.produtos import produto_service` em `pedido_service.py` | Traz junto toda a regra de negócio do outro, sem contrato nenhum. A dependência vira invisível |
| Importar `_router` ou `_contrato` de outro domínio | `pedido_router.py` usando `ProdutoRespostaSchema` | Amarra o formato da sua API ao do outro: mudar a resposta de produtos quebraria pedidos |
| Escrever **direto** na tabela de outro domínio | `pedido_service` fazendo `sessao_db.query(Estoque).update(...)` | A regra do dono não roda. Ele valida saldo, mínimo, bloqueio — nada disso acontece quando outro mexe na tabela por fora |
| Dar `commit()` dentro da função de borda do outro | `enderecamento_publico.baixar_lote` commitando por conta própria | Quem é dono da transação? Se a finalização falhar depois, a baixa já foi e não volta. Ver a regra 2 da borda, abaixo |
| Reimplementar a regra do outro | um relatório recalculando desconto com fórmula própria em vez de perguntar a `pedidos` | Passam a existir duas verdades. Elas divergem em silêncio, e ninguém percebe até o cliente reclamar |
| Importar dado que deveria estar congelado | guardar só `produto_id` e ler o preço atual para exibir um pedido antigo | O preço de hoje não é o preço praticado ontem. Ver "Antes de importar, pergunte se o dado devia ser congelado" |

### Como se faz: o arquivo de fronteira `<dominio>_publico.py`

Quando um domínio precisa de dado **vivo** de outro (não serve snapshot, não
serve só a FK), ou precisa que o outro **altere o estado dele**, o canal é um
arquivo de fronteira criado **na pasta do domínio dono do dado**. Regras dele,
todas obrigatórias:

1. Nome: `<dominio>_publico.py` (ex: `cidade_publico.py`), dentro de
   `domains/<dominio>/`.
2. **Nenhuma função dele dá `commit()` ou `rollback()`** — nem as de leitura,
   nem as de escrita. A função de escrita altera objetos na `Session` que
   recebeu e devolve; quem abriu a transação decide o desfecho. **Esta é a
   regra que sustenta todas as outras** — ver "Escrita pela borda" abaixo.
3. Recebe `Session` e ids primitivos como parâmetro.
4. Devolve contrato próprio (`ContratoBase`) ou tipo primitivo —
   **nunca o model SQLAlchemy**.
5. Quem consome importa **apenas esse arquivo**, nunca outro arquivo do domínio.
6. Função de escrita **valida as invariantes do dono** e levanta exceção quando
   elas não fecham. Saldo insuficiente é erro de quem guarda o saldo, não de
   quem pediu a baixa.

```python
# FRAGMENTO ILUSTRATIVO — padrão do arquivo de fronteira
# Arquivo: app/domains/cidades/cidade_publico.py

from sqlalchemy.orm import Session
from app.shared.contrato_base import ContratoBase


class CidadeResumo(ContratoBase):
    """Contrato próprio da fronteira — não é o model, não é o schema do router."""
    id: str
    nome: str
    uf: str


def obter_resumo(sessao_db: Session, cidade_id: str) -> CidadeResumo | None:
    ...
```

Assim a dependência fica em **um arquivo só, visível e contável por grep** —
que é exatamente o objetivo da regra.

> **Existem hoje:** `cidade_publico`, `cliente_publico`, `empresa_publico`,
> `marca_publico`, `pedido_publico`, `produto_publico`, `usuario_publico`,
> `estoque_publico` e `enderecamento_publico` — todos nasceram de uma
> necessidade concreta, e só `enderecamento_publico` tem função de escrita.
> Não crie um "para o caso de precisar" (ver princípio nº 3: abstrai por dor).

### Importar *model* é diferente de importar *service*

Um `model` é estrutura de tabela — não carrega regra de negócio. Por isso
`cliente_model.py` pode importar o model `Cidade` para declarar a FK e o
`relationship()`, e isso **não** viola a regra.

Duas condições, ambas obrigatórias:

- O model importado é de um **cadastro** (tabela de referência), não de um
  documento com regra de negócio própria.
- O model importado **nunca importa de volta**. Essa é a linha que evita ciclo
  de import — a mesma razão explicada em "A exceção de `core/auth` ↔
  `domains/usuarios`".

Importar `_service`, `_router` ou `_contrato` de outro domínio continua
proibido em qualquer situação.

### Antes de importar, pergunte se o dado devia ser congelado

Esta é a pergunta mais importante em ERP, e a que mais gera bug quando é
esquecida:

> **"Se esse dado mudar daqui a dois anos, o registro de hoje deve mudar junto?"**

- **Não deve mudar** → é um **fato histórico**. Grave como snapshot na sua
  própria tabela. Não importe nada.
  Exemplos: preço praticado no pedido, nome e CNPJ do cliente na nota emitida,
  endereço no momento do envio.
- **Deve mudar** → é um **dado vivo**. Use FK e leia o valor atual.
  Exemplo: a cidade no cadastro do cliente — se o cadastro for corrigido,
  você quer ver o valor corrigido.

Snapshot e FK não são regras gerais do projeto: **a escolha é feita tabela a
tabela, por quem modela**, no momento de criar a tabela. O que este documento
define é só o critério de decisão acima — a decisão em si é de negócio e
pertence ao model daquele domínio, não a este arquivo.

### Escrita pela borda: quando um domínio precisa alterar o estado de outro

O caso clássico em ERP é "confirmar pedido → baixar estoque → gerar título
financeiro": vários domínios, **uma transação só**. No projeto ele apareceu de
verdade quando a expedição passou a baixar o saldo do endereço ao finalizar a
separação.

**A solução é uma função de escrita no `<dominio>_publico.py` do dono**, e não
uma camada nova. Quem baixa saldo de endereço é o `enderecamento`; a expedição
só *pede*:

```python
# FRAGMENTO ILUSTRATIVO — app/domains/enderecamento/enderecamento_publico.py

def baixar_lote(sessao_db: Session, estoque_lotes_id: str, quantidade: Decimal) -> list[BaixaAplicada]:
    """Baixa `quantidade` do lote, distribuindo entre os endereços em que ele
    está. NÃO dá commit: quem abriu a transação decide o desfecho."""
```

```python
# FRAGMENTO ILUSTRATIVO — quem consome (app/domains/expedicao/expedicao_service.py)

enderecamento_publico.baixar_lote(sessao_db, lote_id, quantidade)   # só marca na Session
processo.data_fim = agora                                            # o estado do próprio domínio
sessao_db.commit()                                                   # UM commit, no dono da transação
```

**Por que isto é seguro, sendo que a versão anterior deste documento proibia.**
A proibição antiga era justificada assim: *"Quem é dono da transação? Se o
pedido falhar depois, o estoque já baixou e não volta"*. Repare que o problema
descrito nunca foi a escrita — foi o **`commit()`**. Com a regra 2 da borda
("nenhuma função dá commit"), o problema simplesmente não existe: a baixa e a
finalização estão na mesma transação, e o `rollback` desfaz as duas juntas.

**O que a borda de escrita garante, e a escrita direta não:**

- A regra do dono roda. `baixar_lote` recusa saldo insuficiente porque saldo é
  invariante do `enderecamento`. Um `UPDATE` disparado de fora não recusaria
  nada.
- A dependência continua contável por grep, num arquivo só.
- O dono pode mudar como guarda o saldo (uma tabela, duas, um agregado) sem que
  ninguém mais precise saber.

**Regras da função de escrita**, além das da borda:

1. Nome de **verbo de negócio**, não de CRUD: `baixar_lote`, `reservar`,
   `estornar` — nunca `atualizar_quantidade` ou `set_saldo`. O nome tem que
   dizer o que aconteceu no negócio, senão a borda vira um ORM disfarçado.
2. Nunca `commit()`, nunca `rollback()`, nunca `flush()` que o chamador não
   espere.
3. Levanta exceção quando a invariante do dono não fecha.
4. É idempotente ou explicitamente não é — e a docstring diz qual dos dois.

> **Quando ainda vale criar uma camada de orquestração:** quando o caso de uso
> não pertence a nenhum domínio, e sim ao meio deles (ex: um "faturar pedido"
> que coordena pedidos + estoque + financeiro + fiscal em regras próprias). Aí o
> caso de uso tem regra própria e precisa de casa. Enquanto o que existe for "um
> domínio pede uma coisa ao outro", a borda resolve — e é ela que o projeto usa
> hoje (ver princípio nº 3: abstrai por dor).

### O conceito, sem ambiguidade

Rode este roteiro na ordem. Pare no primeiro item que descrever o seu caso:

1. **Só preciso guardar a referência?** → FK. Importa no máximo o *model*.
2. **Preciso exibir um dado atual do outro domínio?** → `relationship()`
   (cadastro) ou `<dominio>_publico.py`.
3. **Preciso de um cálculo/regra do outro domínio?** → função de leitura no
   `<dominio>_publico.py` **dele**. Nunca recalcule por conta própria.
4. **Preciso alterar o estado do outro domínio?** → função de **escrita** no
   `<dominio>_publico.py` **dele**, com nome de verbo de negócio e **sem
   `commit()`**. Ver "Escrita pela borda" acima. O que continua proibido é
   `add`/`update`/`delete`/`commit` na tabela dele a partir do seu service.
5. **O dado precisa ficar congelado no tempo?** → snapshot na sua própria
   tabela. Não importe nada.

**Se nenhum dos cinco descreve o que você está fazendo, não invente um sexto
caminho: pare e pergunte.** Um import fora dessas cinco formas é sempre um bug
de arquitetura, mesmo que o código funcione e os testes passem.

## Onde mora o endereço da mercadoria (e por que não no pedido)

Esta seção existe porque o caso já deu bug uma vez e o padrão vale para
qualquer campo parecido.

`pedido_itens` **não tem** coluna de endereço. O que o cliente comprou é
`(produto, lote, quantidade)`; **onde a mercadoria está guardada é assunto do
nosso galpão**, e mora em dois domínios próprios:

| Domínio | Tabelas | Responsabilidade |
|---|---|---|
| `estoque` | `estoque`, `estoque_lotes` | Quanto tem do produto na empresa, e o mesmo saldo aberto por lote (com fabricação e vencimento) |
| `enderecamento` | `estoque_enderecos`, `estoque_endereco_lote` | Os lugares do galpão, e em quais deles cada lote está |

A relação lote ↔ endereço é **muitos-para-muitos de verdade**: o mesmo lote se
espalha por vários endereços, e o mesmo endereço guarda lotes de produtos
diferentes. Era por espremer isso numa coluna `endereco_produto` na linha do
pedido que a consulta da integração devolvia **uma linha de pedido por
endereço, cada uma com a quantidade INTEIRA** — um pedido de 14.000 un entrava
com 42.000 (ver as migrações `c9e4a71f5b38` e `d2b7f4e9a610`).

**Como a expedição chega no endereço**, sem consultar tabela alheia:

```
item do pedido (produto_id, lote)
  → estoque_publico.obter_ids_de_lotes(...)        # id em estoque_lotes
  → enderecamento_publico.obter_descricoes_por_lote(...)   # list[str]
```

Duas fronteiras de leitura, duas consultas para o pedido inteiro, e o contrato
da expedição devolve `enderecos: list[str]` — nunca um campo único. Lista vazia
significa "lote ainda não endereçado", que é operação normal e não erro: a
separação segue e o operador procura, como já fazia.

**A regra geral por trás disso:** antes de pôr um campo numa tabela, pergunte
de quem é o fato. Se o dado descreve o **nosso** processo (onde está, quem
separou, quando conferiu) e não o **documento** (o que foi comprado, por quanto,
para quem), ele não pertence ao documento — mesmo que seja conveniente tê-lo
ali. E se a cardinalidade real for "vários", uma coluna de texto nunca é a
resposta; a resposta é uma tabela.

## Validação de id por foreign key

Quando um registro guarda o id de outro domínio, **nenhum service consulta o
outro domínio só para ver se o id existe**. Quem recusa id inexistente é a
própria foreign key:

```
POST /<recurso>  {"algumId": "nao-existe", ...}
  → o INSERT viola a FK
  → SQLAlchemy levanta IntegrityError
  → o handler em main.py devolve 422
```

Isso vale para qualquer domínio, e tem duas consequências práticas:

- O handler de `IntegrityError` em `main.py` **é parte do desenho**, não um
  detalhe. Sem ele o erro vira 500.
- Os testes ligam `PRAGMA foreign_keys=ON` no SQLite (`tests/conftest.py`).
  O SQLite ignora FK por padrão — sem o pragma, um teste de "id inexistente"
  passaria sem exercitar nada.

## A exceção de `core/auth` ↔ `domains/usuarios`

> **Escopo:** esta seção trata **apenas** de `core/` importar de `domains/` —
> é a exceção declarada na primeira lista de "Regras de import entre domínios".
> Ela **não** afrouxa nada entre um domínio e outro: para `domains/X` →
> `domains/Y`, vale só aquela seção.

`core/auth/dependencies.py`, `auth_service.py` e `auth_router.py` importam
`Usuario` e `UsuarioPermissao` de `domains/usuarios/usuario_model.py`.
Isso é intencional, e vale entender o porquê antes de "consertar".

**A razão:** `usuarios` não é um domínio de negócio como `clientes`,
`produtos` e `pedidos`. É a **face administrativa do contexto de
identidade** — a mesma coisa que `core/auth`, separada em outra pasta só
porque tem tela de CRUD. Não existe login sem consultar a tabela de
usuários, e não existe `exigir_permissao` sem ler `usuario.permissoes`.

A dependência é de mão dupla, e isso confirma o diagnóstico: `usuario_router`
importa `exigir_permissao` de `core/auth`, e `usuario_service` importa
`gerar_hash_senha`. `usuarios` é o único domínio que fala a língua de auth —
porque é auth. Nenhum dos outros três toca em hash de senha ou em
`PERMISSOES_VALIDAS`.

**A regra que vale, então, não é "core nunca importa domains" — é esta:**

- `core/auth` pode importar **os models** de `domains/usuarios`
  (`Usuario`, `UsuarioPermissao`) e nada mais de `domains/*`.
- `core/auth` **nunca** importa `_service`, `_router` ou `_publico` de
  domínio nenhum.
- `usuario_model.py` **nunca** importa de `core/auth`.

Essa última linha é a que sustenta tudo: hoje `usuario_model.py` só importa
`Base` e os mixins, então a cadeia de imports termina ali e o Python resolve
sem ciclo. No dia em que alguém puser
`from app.core.auth.seguranca import gerar_hash_senha` dentro do model (para
criar um `usuario.definir_senha()`, por exemplo), o ciclo fecha e a
aplicação para de subir com `ImportError` — num ponto do código sem relação
aparente com a mudança. Se precisar de hash, ele fica no service.

**Por que não separar de vez:** dá pra modelar `Credencial` em auth e
`Usuario` cadastral em domains, com tradução entre os dois. Seriam duas
tabelas, sincronização entre elas e uma camada de tradução para resolver um
problema que hoje não dói — e autenticação é subdomínio genérico, o último
lugar onde vale gastar modelagem. Ver princípio nº 3: abstrai por dor.

## Convenção de serialização: camelCase de ponta a ponta

Todo schema Pydantic herda de `ContratoBase` (`shared/contrato_base.py`), que
configura `alias_generator = to_camel`. Isso significa:

- **Internamente (Python)**: campos em snake_case, batendo com os atributos
  SQLAlchemy (`razao_social`, `criado_em`, `preco_unitario`).
- **No JSON de resposta**: camelCase automático (`razaoSocial`, `criadoEm`,
  `precoUnitario`), exatamente como os modelos TypeScript do front definem.
- **Nos payloads recebidos do front**: `populate_by_name = True` faz o Pydantic
  aceitar tanto snake_case quanto camelCase — o front manda camelCase e o
  backend entende.

**Regra prática**: ao criar um campo novo num schema, nomeie em snake_case
no Python. O camelCase no JSON é automático — não precisa declarar `alias`
manualmente em lugar nenhum.

Todo router herda de `RouterBase` (`shared/router_base.py`), que força
`response_model_by_alias=True` em toda rota — garante que as respostas
usem os aliases camelCase sem precisar declarar em cada endpoint.

**Nunca use `BaseModel` ou `APIRouter` diretamente** nos schemas e routers de
domínio. Sempre `ContratoBase` e `RouterBase`. O `main.py` pode usar `FastAPI`
diretamente (não é router de domínio).

## Domínio de consulta a banco externo

O domínio `cotacoes/` (menu **Inteligência de Mercado**) inaugurou um padrão
que foge do desenho normal, e a diferença é proposital: **ele não lê o nosso
MySQL**. Todos os dados vêm do **OuroWeb**, o SQL Server do Bionexo, que é a
base de outro sistema.

### O que muda em relação a um domínio comum

| Domínio comum | Domínio de consulta a banco externo |
|---|---|
| 4 arquivos (`_model`, `_contrato`, `_service`, `_router`) | **3 arquivos — não existe `_model.py`** |
| tem tabela e migração Alembic | nenhuma tabela nossa, nenhuma migração |
| service recebe `Session` do SQLAlchemy | service **não recebe sessão nenhuma** |
| router usa `Depends(obter_sessao)` | router **não usa** `obter_sessao` |
| chaves `acessar` + `gravar.*` + `apagar` | só **`acessar`** — não há o que gravar |
| pode expor `_publico.py` a outros domínios | **não expõe nada**: nenhum outro domínio o consome |

Não existe `cotacao_model.py` porque não há tabela nossa para mapear. Mapear o
schema de outro sistema criaria a ilusão de que podemos alterá-lo — a mesma
razão pela qual `sistema_origem/gestcom/` também não tem models.

### Somente leitura, e isso inclui objeto temporário

O acesso ao OuroWeb é **estritamente de leitura**. Não é só "não dar UPDATE":
não criamos índice, view, procedure, tabela de apoio nem tabela temporária
(`SELECT INTO #tmp`) no servidor deles. Quando uma consulta está lenta, a saída
é **reescrever o SQL**.

Isso está garantido no código: `shared/sistema_origem/ouroweb/conexao.py` expõe
apenas `buscar_um()` e `buscar_todos()`, não tem equivalente do `executar()` do
gestcom, e abre a conexão com `autocommit=False`. A ausência da função de
escrita é intencional e não deve ser "corrigida" por conveniência.

Note que os dois bancos de origem **não têm a mesma permissão**: no Oracle do
GESTCOM a escrita existe num caso específico (a correção de código de barras
grava em `fat_produtos`); no OuroWeb, nunca.

### Isolamento: não conversa com outros domínios

`cotacoes/` não importa nenhum outro domínio, e nenhum outro domínio o importa.
A única dependência é a de sempre, `core/auth/dependencies.exigir_permissao` —
sem ela qualquer pessoa logada acessaria a tela, e a checagem de permissão é a
barreira real do sistema (o guard do front é só UX).

Se um dia algum dado do Bionexo precisar cruzar com dado nosso, isso **não**
vira import entre domínios: a regra continua valendo, e a saída é o
`<dominio>_publico.py` como em qualquer outra fronteira.

### Paginação é obrigatória, e no banco

São cerca de **8 GB** nas tabelas do Bionexo: `Tab_CceBionexoPedidoItens`
sozinha tem mais de 35 milhões de linhas, e um período de 3 dias já devolve
mais de 200 mil itens. Duas travas existem por isso, e nenhuma é opcional:

1. **`OFFSET/FETCH NEXT` no SQL Server.** A página é recortada pelo banco.
   Trazer tudo e fatiar em Python estouraria a memória do worker no primeiro
   acesso.
2. **Período obrigatório, com janela máxima de 90 dias** (`JANELA_MAXIMA_DIAS`),
   e `perPage` com teto de 100 (`PER_PAGE_MAXIMO`). Sem período, a consulta
   varre a base inteira.

Como em qualquer listagem do projeto, **todo filtro é resolvido na consulta**,
nunca sobre a página já carregada.

### Duas otimizações que parecem estilo e são desempenho

O servidor do OuroWeb é **I/O-bound**: `PAGEIOLATCH_SH` (espera por leitura de
disco) é a maior espera acumulada dele. Tudo que faz o SQL Server materializar
dados a mais custa caro ali, e as duas decisões abaixo existem por causa disso.
Ambas foram medidas — se mexer nelas, **meça de novo**.

**1. A ordem do JOIN.** A primeira versão partia de `Tab_CceBionexoPedido` e
juntava cabeçalho, itens, cadastro e cidade de uma vez. Com `ORDER BY
dte_DataVencimento` + `OFFSET`, o plano escolhido passava de **10 minutos**,
enquanto o mesmo `COUNT(*)` respondia em 0,4s. A versão atual recorta primeiro
os cabeçalhos do período numa CTE (que usa o índice de `dte_DataVencimento`) e
só então junta os itens. Por isso `_condicoes()` separa os filtros em "de
cabeçalho" e "de item" — filtro de cabeçalho aplicado depois do join não reduz
nada.

**2. Paginação em duas etapas (deferred join).** Mesmo com a CTE, selecionar
todas as colunas e ordenar numa tacada levava **69 segundos** para devolver 50
linhas — de novo contra 0,3s do `COUNT(*)` sobre os mesmos joins, e de forma
consistente, não por oscilação de carga. O motivo é o que o `ORDER BY` precisa
carregar: para devolver 50 linhas ordenadas, o SQL Server materializa e ordena
as ~220 mil linhas do período **junto com as colunas de texto largo**
(`str_DescricaoProduto` tem 1500 caracteres), e isso vai para disco.

A solução é ordenar só as CHAVES e buscar o texto depois, para os 50 ids da
página (`_linhas_por_id`). Mesma consulta: **1,5 segundo**. A ordem devolvida
pelo `IN` não é garantida, então ela é reposta em Python a partir da etapa 1 —
pedir ao banco para ordenar de novo traria o custo de volta.

A **exportação não usa** esse truque, e não teria como: ela devolve todas as
linhas, então o texto largo precisa ser lido de qualquer forma. É por isso que
ela tem um timeout próprio de 600s (`timeout_exportacao_segundos`) enquanto a
tela usa 60s.

### Ordenação vem de lista fechada

`sort` chega pela URL e vira nome de coluna no SQL. Aceitar texto livre seria
injeção — por isso existe `ORDENACOES_VALIDAS` em `cotacao_contrato.py`, um
dicionário de chave da API para coluna. Qualquer valor fora dele responde 422.
Todo o resto entra por bind (`%(nome)s`).

### Banco fora do ar é 503, não 500

`OuroWebIndisponivel` é traduzido para `503 Service Unavailable` no router. Não
é defeito nosso: é o sistema de origem indisponível, e a tela precisa saber a
diferença para dizer o que aconteceu em vez de mostrar "erro interno".

## Domínio que ESCREVE no sistema de origem

O domínio `sistema_origem/` é o irmão de `cotacoes/` para o outro lado: também
não tem tabela nossa e também não usa a `Session` do SQLAlchemy, mas em vez de
LER um banco externo, ele **manda o ERP (GESTCOM, Oracle) fazer alguma coisa**.

> Não confundir com o pacote **`app/shared/sistema_origem/`**, que tem o mesmo
> nome e é outra coisa: lá mora a INFRAESTRUTURA (conexão, config, rotinas de
> sincronização); aqui mora a REGRA DE NEGÓCIO de "o que o ELLOTEC pode pedir ao
> ERP". O domínio usa a infraestrutura; a infraestrutura nunca importa o
> domínio.

### O nome é do assunto, não da função

Hoje existe uma operação só — finalizar o pedido depois da conferência. O
domínio não se chama `finalizacao_origem` de propósito: outras operações do ERP
virão para cá, e renomear um domínio depois custa rota, chave de permissão,
tela e migração. Nomear pelo assunto não é abstração antecipada (o código
continua tendo só o que é usado hoje) — é só não escolher um nome que já nasce
com data de validade.

### Arquivos

| Arquivo | Papel |
|---|---|
| `sistema_origem_service.py` | o SQL, as constantes do ERP e a regra. Não recebe `Session` |
| `sistema_origem_publico.py` | a borda: é por aqui que os outros domínios pedem |

Não existe `_model.py` (não há tabela nossa), não existe migração, e **não
existe `_router.py`**: nenhuma das operações é uma tela por si só. Quem expõe o
endpoint é o domínio que tem o caso de uso — hoje `expedicao`, que já é dono da
conferência, da permissão e da tela onde o operador está.

### A borda daqui commita, e isso não contradiz a regra

A regra do `<dominio>_publico.py` diz que **nenhuma função da borda dá
`commit()`**. Ela continua valendo, e vale sobre a **nossa `Session`**: quem
abriu a transação do MySQL é quem decide o desfecho dela.

Aqui não existe `Session`. A escrita é numa conexão Oracle própria, que precisa
commitar sozinha — não há como um `commit` do MySQL desfazer um `UPDATE` já
gravado em outro banco. Duas consequências práticas, e as duas são obrigatórias:

1. **O ERP commita primeiro; o nosso banco depois.** Se a ordem se inverter e o
   ERP recusar, fica gravado aqui que o pedido foi fechado lá — mentira que só
   aparece no faturamento.
2. **A falha do ERP tem que ficar registrada no nosso banco.** É o que responde,
   dias depois, "por que este pedido está conferido aqui e aberto lá?". Foi para
   isso que nasceram as quatro colunas de `expedicao_conferencias` —
   `finalizado_origem_em`, `motivo_falha_origem`,
   `tentativa_origem_usuario_id` e `tentativa_origem_em`. Todas de negócio,
   nunca campos `sync_*`.

   As duas de tentativa foram acrescentadas depois, e o motivo vale registrar:
   o motivo gravado conta o QUE aconteceu, mas não em nome de quem. A primeira
   recusa real em produção foi "o usuário não tem vínculo com o sistema de
   origem" — e a única pergunta que importava era *qual conta clicou*, porque
   contas administrativas nossas (`admin`) não têm código de funcionário no ERP
   e caem exatamente nessa recusa. Sem as colunas, a resposta dependia de
   alguém lembrar. Elas são sobrescritas a cada tentativa e **não** são limpas
   no sucesso: aí passam a responder "quem fechou o pedido, e quando".

### A pré-condição é lida do próprio ERP, com trava

Antes de qualquer escrita, o service lê o status atual do pedido no Oracle com
`SELECT ... FOR UPDATE` e exige que ele ainda esteja em `PED`. O `FOR UPDATE`
não é detalhe de estilo: sem ele, entre ler o status e gravar o `FEC` cabe o
faturamento do pedido pelo outro lado, e a nossa baixa passaria por cima dele
sem ninguém perceber.

Pela mesma razão a operação **não é idempotente e não deve ser**: a segunda
chamada encontra o pedido fora do `PED` e é recusada com 409. É essa recusa que
faz o papel da trava.

### Como os erros são traduzidos

| Situação | Resposta | Por quê |
|---|---|---|
| Pedido não existe no ERP | 404 | o vínculo aponta para um registro que não está lá |
| Pedido fora do `PED` | 409 | alguém mexeu no pedido do lado de lá; não é erro do operador |
| Empresa/pedido/usuário sem vínculo | 409 | sem o código do ERP não dá para identificar o registro — e chutar daria baixa no pedido errado |
| Oracle fora do ar, sem client, credencial errada | 503 | canal indisponível, não defeito nosso. A conferência feita no galpão continua valendo |
| Erro do driver no meio da transação (ORA-…) | 502 | o ERP recusou; nada foi commitado |

Nunca 500: das cinco linhas acima, nenhuma é "a aplicação quebrou", e chamar
todas de erro interno tiraria do operador a única informação que decide o que
ele faz em seguida — tentar de novo, ou chamar o faturamento.

### Os tipos e tamanhos vêm de `all_tab_columns`, nunca de estimativa

O Oracle não recusa estouro de coluna com uma mensagem útil — recusa com
`ORA-12899` já dentro da transação. Por isso os tamanhos são checados antes de
abrir a conexão, e as constantes ficam nomeadas no topo do service.

Mas o ponto mais importante é de onde eles saem. **Consulte
`all_tab_columns`** antes de assumir tipo ou tamanho de coluna do ERP:

```sql
select data_type, data_length from all_tab_columns
 where table_name = 'FAT_CAPAPEDIDO' and column_name = 'VOLUME_PEDIDO';
```

A especificação da tela do ERP que originou esta função anotava
`:vVOLUME(FLOAT)` e `:vMARCA_PEDIDO(VARCHAR[6])`, e as duas anotações
enganavam: `VOLUME_PEDIDO` é `VARCHAR2(10)` — **texto** — e `MARCA_PEDIDO` é
`VARCHAR2(20)`, não 6 (aquele 6 era o tamanho do literal `'OUTROS'`). Os
valores anotados descrevem o que a tela mandava, não a coluna.

O caso do volume não daria erro nenhum, e é o pior tipo de defeito por isso: um
bind numérico numa coluna de texto é convertido pelo Oracle usando o
`NLS_NUMERIC_CHARACTERS` da sessão, que em português usa vírgula. O pedido
ficaria com `4,0` gravado onde o ERP grava `4`. Os dois "parecem" quatro.
Por isso a string é montada em `_volume_para_o_erp`, no nosso lado.

Os limites conferidos hoje:

| coluna | tipo real | o que a constante do service diz |
|---|---|---|
| `FAT_POLICE.FUNCIONARIO` | `VARCHAR2(5)` | `TAMANHO_FUNCIONARIO = 5` |
| `FAT_CAPAPEDIDO.CONFERIDOR` | `VARCHAR2(20)` | recebe o mesmo código; vale o menor dos dois |
| `FAT_CAPAPEDIDO.ESPECIE_PEDIDO` | `VARCHAR2(10)` | `TAMANHO_ESPECIE = 10` |
| `FAT_CAPAPEDIDO.VOLUME_PEDIDO` | `VARCHAR2(10)` | `TAMANHO_VOLUME = 10` |
| `FAT_CAPAPEDIDO.PESO_LIQUIDO` / `PESO_BRUTO` | `NUMBER` | numéricos de verdade |
| `FAT_CAPAPEDIDO.MARCA_PEDIDO` | `VARCHAR2(20)` | `MARCA_PEDIDO = "DIVERSOS"` |

Quando o mesmo valor vai para duas colunas de tamanhos diferentes, **vale o
menor** — é o que o código faz com o código do funcionário.

### Como isso é testado sem tocar o ERP

O Oracle do GESTCOM é **base de produção**: um teste que conecte de verdade muda
o status de pedidos reais. `tests/test_sistema_origem_finalizar_pedido.py`
substitui `conectar` por uma conexão de mentira que só anota o que recebeu, e
afirma sobre o que foi anotado — quais comandos saíram, em que ordem, com que
parâmetros, e se houve `commit`. O teste do fluxo completo
(`TestFinalizarNoSistemaOrigem` em `test_expedicao_e2e.py`) troca a própria
borda por uma função de mentira e verifica o que fica gravado do nosso lado.

Nenhum teste automatizado deste projeto escreve no ERP, e nenhum deve passar a
escrever.

## Onde cada coisa fica (FAQ para agente de IA)

- **Adicionar campo em produto**: `produto_model.py` (coluna em snake_case) →
  `produto_contrato.py` (campo Pydantic em snake_case — camelCase no JSON é
  automático) → `alembic revision --autogenerate` → `alembic upgrade head`.
- **Adicionar domínio novo (ex: fornecedores)**:
  1. Adicione as chaves `fornecedores.acessar`, `fornecedores.gravar.incluir`,
     `fornecedores.gravar.editar`, `fornecedores.apagar` (e quaisquer chaves
     de negócio não-CRUD) em `PERMISSOES_VALIDAS` (`permission_model.py`).
  2. Adicione as mesmas chaves em `PermissaoKey`/`ARVORE_PERMISSOES` no front
     (`permission.model.ts`).
  3. Criar `domains/fornecedores/` com os 4 arquivos, seguindo `domains/clientes/`.
     Usar `ContratoBase` nos contratos e `RouterBase` no router.
  4. Importar o model em `core/database/todos_os_models.py`.
  5. Registrar o router em `app/main.py`.
  6. `alembic revision --autogenerate` + `alembic upgrade head` (só necessário
     se o domínio novo tiver tabela própria — a tabela `usuario_permissoes`
     não muda de estrutura ao adicionar chaves novas).
- **Exigir permissão num endpoint**: parâmetro
  `_ctx = Depends(exigir_permissao("dominio.contexto.acao"))` no endpoint do router.
- **Revogar sessão de usuário remotamente**: `sessao_service.revogar_todas_sessoes_do_usuario(db, usuario_id)`.
- **Soft delete**: sempre `marcar_apagado(registro)`, nunca `sessao.delete(registro)`.
- **Um domínio precisa de dado de outro**: ver "Regras de import entre
  domínios" → "O conceito, sem ambiguidade". Aquele roteiro de 5 passos decide
  o caso; não decida por conta própria nem por analogia com outro domínio.

## Pendências conhecidas para produção

- **`JWT_SEGREDO` é de desenvolvimento.** Trocar por valor aleatório forte antes
  de qualquer deploy (`openssl rand -hex 32`).
- **Processo de sincronização não existe ainda.** Os campos `sync_*` estão prontos;
  o worker que lê `sync_synced_at IS NULL` e propaga para outras réplicas é
  trabalho futuro.
- **Rate limiting ausente.** Adicionar throttle em `/auth/login` antes de produção.
- **CORS restrito a `localhost:4200`.** Ajustar `CORS_ORIGENS` no `.env` para o
  domínio real em produção.