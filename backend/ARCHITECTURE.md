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
│   └── pedidos/                       # CRUD de pedidos
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

- Nenhum service de domínio chama `sessao.delete(registro)` em model com
  `SyncMixin`. Sempre `marcar_apagado(registro)` de `shared/sync_helpers.py`.
- `sync_synced_at` é gerenciado por processo de sincronização futuro — nenhum
  service de domínio escreve nesse campo.
- PKs são UUID (não auto-increment) — sistema distribuído não pode usar
  auto-increment porque duas réplicas offline colidiriam IDs na sincronização.

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
| **Escrita** — gravar/alterar/apagar no outro domínio | Não. Nunca. |
| **Regra reimplementada** — recalcular por conta própria o que é regra do outro | Não. Nunca. |

Um domínio é **dono** dos seus dados e das suas regras. Os outros podem
*perguntar*, nunca *mexer*, e nunca *adivinhar*.

### O que PODE (com exemplos concretos)

| Caso | Exemplo em ERP | Como se faz |
|---|---|---|
| FK para uma tabela de cadastro | `clientes.cidade_id` → `cidades.id` | `cliente_model.py` importa **apenas o model** `Cidade` |
| Exibir dado vivo do cadastro referenciado | listagem de clientes mostrando o nome da cidade | `relationship()` no model, ou `cidade_publico.py` |
| Pedir um cálculo ao dono da regra | `pedidos` perguntando o preço atual a `produtos` | `produto_publico.obter_preco(sessao_db, produto_id)` |
| Validar que um id existe | criar pedido com `cliente_id` | **não importa nada** — a FK do banco recusa |

### O que NÃO PODE (com exemplos concretos)

| Caso | Exemplo em ERP | Por que é proibido |
|---|---|---|
| Query na tabela de outro domínio | `sessao_db.query(Cidade)` dentro de `cliente_service.py` | Se a tabela mudar, quebra em N domínios de uma vez. É a duplicação que a regra existe para impedir |
| Importar o `_service` de outro domínio | `from app.domains.produtos import produto_service` em `pedido_service.py` | Traz junto toda a regra de negócio do outro, sem contrato nenhum. A dependência vira invisível |
| Importar `_router` ou `_contrato` de outro domínio | `pedido_router.py` usando `ProdutoRespostaSchema` | Amarra o formato da sua API ao do outro: mudar a resposta de produtos quebraria pedidos |
| Escrever no estado de outro domínio | `pedido_service` baixando estoque em `produtos` e dando `commit()` | Quem é dono da transação? Se o pedido falhar depois, o estoque já baixou e não volta |
| Reimplementar a regra do outro | um relatório recalculando desconto com fórmula própria em vez de perguntar a `pedidos` | Passam a existir duas verdades. Elas divergem em silêncio, e ninguém percebe até o cliente reclamar |
| Importar dado que deveria estar congelado | guardar só `produto_id` e ler o preço atual para exibir um pedido antigo | O preço de hoje não é o preço praticado ontem. Ver "Antes de importar, pergunte se o dado devia ser congelado" |

### Como se faz: o arquivo de fronteira `<dominio>_publico.py`

Quando um domínio precisa de dado **vivo** de outro (não serve snapshot, não
serve só a FK), o canal é um arquivo de fronteira criado **na pasta do domínio
dono do dado**. Regras dele, todas obrigatórias:

1. Nome: `<dominio>_publico.py` (ex: `cidade_publico.py`), dentro de
   `domains/<dominio>/`.
2. Só **leitura**. Nenhuma função dele escreve, altera, apaga ou dá `commit()`.
3. Recebe `Session` e ids primitivos como parâmetro.
4. Devolve contrato próprio (`ContratoBase`) ou tipo primitivo —
   **nunca o model SQLAlchemy**.
5. Quem consome importa **apenas esse arquivo**, nunca outro arquivo do domínio.

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

> **Hoje nenhum `_publico.py` existe no projeto, porque nenhum domínio precisou.**
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

### E quando eu preciso mesmo *escrever* em outro domínio?

Isso não se resolve com import — nenhum tipo de import é a resposta certa aqui.
O caso clássico em ERP é "confirmar pedido → baixar estoque → gerar título
financeiro": três domínios, uma transação só.

A solução é uma **camada de orquestração** acima dos domínios (um service de
caso de uso que abre a transação, chama cada domínio e decide o `commit`/
`rollback`), ou eventos de domínio.

> **Hoje o projeto não tem essa camada, e isso está correto** — nenhum caso de
> uso precisou dela ainda. Quando o primeiro aparecer, crie a camada nesse
> momento; não a antecipe.

### O conceito, sem ambiguidade

Rode este roteiro na ordem. Pare no primeiro item que descrever o seu caso:

1. **Só preciso guardar a referência?** → FK. Importa no máximo o *model*.
2. **Preciso exibir um dado atual do outro domínio?** → `relationship()`
   (cadastro) ou `<dominio>_publico.py`.
3. **Preciso de um cálculo/regra do outro domínio?** → função de leitura no
   `<dominio>_publico.py` **dele**. Nunca recalcule por conta própria.
4. **Preciso gravar no outro domínio?** → **pare.** Isso não é import, é
   orquestração. Ver a seção acima.
5. **O dado precisa ficar congelado no tempo?** → snapshot na sua própria
   tabela. Não importe nada.

**Se nenhum dos cinco descreve o que você está fazendo, não invente um sexto
caminho: pare e pergunte.** Um import fora dessas cinco formas é sempre um bug
de arquitetura, mesmo que o código funcione e os testes passem.

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