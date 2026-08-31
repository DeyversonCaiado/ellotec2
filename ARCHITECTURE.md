# ARCHITECTURE.md — ELLOTEC ERP

> Este documento é a referência principal para qualquer pessoa ou agente de IA
> que for manter, estender ou refatorar este projeto. Leia isso antes de tocar
> em qualquer código. As decisões aqui não são acidente — refletem uma
> filosofia deliberada de arquitetura.

> ⚠️ **AVISO PARA AGENTES DE IA — leia antes de qualquer tarefa**
>
> Este arquivo é um documento de **arquitetura e convenções**, não um espelho
> do código-fonte. Todos os blocos de código aqui são **fragmentos ilustrativos**
> que demonstram padrões — eles não representam o conteúdo completo de nenhum
> arquivo do projeto. Em particular:
>
> - Listas de domínios, chaves de permissão, rotas e imports mostradas nos
>   exemplos refletem o estado inicial do projeto. O projeto real pode ter mais
>   domínios, mais chaves e mais arquivos do que os listados aqui.
> - Nunca trate um exemplo deste documento como o conteúdo definitivo e
>   exaustivo do arquivo correspondente. Sempre leia o arquivo real no
>   repositório antes de editar.
> - Quando uma tarefa exigir adicionar algo novo (domínio, permissão, rota),
>   siga o **padrão descrito** — não se limite ao **conteúdo exemplificado**.

## Filosofia geral

> "Estratégico primeiro, flat, abstrai por dor."

1. **Comece monolítico, separe por contexto delimitado.** Não existe
   `services/`, `models/`, `components/` na raiz cortando o projeto inteiro
   por camada técnica. Existe `domains/usuarios/`, `domains/clientes/`,
   `domains/produtos/`, `domains/pedidos/` — cada um é uma pasta
   autocontida que junta tudo que aquele contexto de negócio precisa.

2. **Dentro de cada domínio, comece procedural.** Um domínio tem, no mínimo:
   - `*.model.ts` — tipos. Entrada/saída do domínio, sem cerimônia.
   - `*.service.ts` — lógica de acesso a dados (HTTP) **e** estado local
     (signal). Não separamos "repository" de "service" de "store" só porque
     em teoria poderiam crescer — isso é abstração por antecipação, e é
     proibida por princípio aqui.
   - `*-list/`, `*-form/` — páginas (componentes standalone), uma pasta por
     página. Cada página tem `.ts` (lógica + template via `templateUrl`) e
     `.html` (template).
   - `*.routes.ts` — rotas do domínio, com os guards de permissão já
     aplicados ali, não espalhados em outro lugar.

3. **Abstrai por dor, não por precaução.** Pergunta de bolso antes de criar
   uma interface/abstração nova: *"isso já trocou de implementação pelo
   menos uma vez nos últimos meses?"* Se não, não abstrai. Os serviços de domínio
   (ex: `UsuarioService`, `ClienteService`, `ProdutoService`, `PedidoService`
   — e todos os que forem adicionados) são classes concretas, não interfaces
   com DI de múltiplas implementações — porque hoje não existe a dor de trocar
   a implementação. Quando o backend chegar, a troca acontece **dentro** de
   cada `.service.ts` (veja seção "Como plugar o backend real"), sem
   precisar reescrever quem consome.

4. **Separa por responsabilidade, não por camada arquitetural.** Não tem
   `controllers/`, `services/`, `repositories/`, `dtos/` cortando o projeto.
   Separação é: "isso é regra de negócio" vs. "isso é I/O" vs. "isso é
   apresentação" — e essa separação acontece **dentro de cada arquivo**, não
   espalhando o mesmo domínio em 5 pastas diferentes.

## Estrutura de pastas

> A árvore abaixo reflete a estrutura **inicial** do projeto. Novos domínios
> serão adicionados em `domains/` conforme o sistema cresce — a ausência de
> um domínio aqui não significa que ele não existe no repositório.

```
src/app/
├── core/                          # infraestrutura transversal (não é "domínio de negócio")
│   ├── auth/
│   │   ├── auth.models.ts         # UsuarioLogado, LoginPayload, LoginResponse
│   │   ├── auth.service.ts        # login/logout, contrato HTTP + signal de sessão
│   │   ├── auth.guard.ts          # bloqueia rotas sem login
│   │   ├── auth.interceptor.ts    # injeta Bearer token + X-Device-Id em todo request, trata 401
│   │   ├── dispositivo.service.ts # gera/persiste o UUID do dispositivo em localStorage
│   │   └── login-page/            # tela de login
│   ├── permissions/
│   │   ├── permission.model.ts    # PermissaoKey (union type) — CONTRATO ÚNICO. Só tipos.
│   │   ├── permission.guard.ts    # bloqueia rota por PermissaoKey
│   │   └── permissao.directive.ts # *appPermissao="'dominio.acao'" — esconde elementos
│   ├── navegacao/
│   │   └── navegacao.model.ts     # ESTRUTURA_APP (fonte única) → MENU_PRINCIPAL + ARVORE_PERMISSOES
│   └── layout/
│       ├── shell.ts / shell.html  # sidebar + topbar + painel de equipe (o "app shell")
│       └── home-page/             # dashboard inicial
├── domains/                       # cada pasta = um contexto delimitado de negócio
│   ├── usuarios/                  # CRUD de usuários + matriz de permissões
│   ├── clientes/                  # CRUD de clientes (template_cliente)
│   ├── produtos/                  # CRUD de produtos (template_produto)
│   └── pedidos/                # CRUD de pedidos, busca cliente+produto
├── shared/ui/                     # componentes 100% genéricos, sem regra de negócio
│   ├── icon.component.ts          # ícones SVG por nome (ver seção PrimeIcons abaixo)
│   └── page-header.component.ts   # cabeçalho de página (breadcrumb + título + slot de ações)
├── environments/
│   ├── environment.ts             # mockAuth: false, apiUrl: http://localhost:8000 (backend ativo)
│   └── environment.prod.ts        # mockAuth: false, apiUrl: /api
├── app.routes.ts                  # composição de rotas: login (público) + shell (protegido)
└── app.config.ts                  # providers globais (router, http, locale, providePrimeNG)
```

### Por que `core/` existe e não é mais um domínio

`core/` não segue a regra "contexto delimitado de negócio" porque não é
negócio — é o que toda a aplicação precisa pra funcionar (sessão, permissão,
casca visual). Por isso `core/` tem regra de import própria, diferente da de
um domínio: ver "Regras de lint / import (a fazer cumprir)", que é a única
seção que define o que pode ser importado de onde.

## O contrato de permissões (ponto central do sistema)

Tudo de permissão gira em torno de **um único arquivo**:
`core/permissions/permission.model.ts`.

### Modelo: flat key set

Cada permissão do sistema é uma **string opaca e única** do tipo
`PermissaoKey`. Não existe mais o par `(DominioId, Acao)` com ações fixas
de CRUD — qualquer funcionalidade de negócio, seja ela CRUD ou não, vira
uma chave nomeada com o padrão `dominio.contexto.acao`.

> ⚠️ **O bloco abaixo é um fragmento ilustrativo**, não o conteúdo completo
> de `permission.model.ts`. Ele mostra a **estrutura e o padrão de nomenclatura**
> usando os domínios iniciais como exemplo. O arquivo real no repositório
> conterá todas as chaves de todos os domínios existentes no projeto —
> **sempre leia o arquivo antes de editar**, nunca substitua pelo conteúdo abaixo.

```typescript
// FRAGMENTO ILUSTRATIVO — não é o conteúdo completo do arquivo
// Arquivo real: core/permissions/permission.model.ts
// Padrão de nomenclatura: dominio.contexto.acao

export type PermissaoKey =
  // --- Usuários (exemplo de domínio simples) ---
  | 'usuarios.acessar'
  | 'usuarios.gravar.incluir'
  | 'usuarios.gravar.editar'
  | 'usuarios.apagar'
  // --- Pedidos (exemplo com ações não-CRUD) ---
  | 'pedidos.acessar'
  | 'pedidos.gravar.incluir'
  | 'pedidos.gravar.editar'
  | 'pedidos.apagar'
  | 'pedidos.condicao_pagamento.aplicar'
  | 'pedidos.desconto.liberar_manual'
  // ATENÇÃO: este union type está incompleto aqui propositalmente.
  // No arquivo real, todo domínio do projeto tem suas chaves declaradas.
  // Ao adicionar um domínio novo, adicione suas chaves no arquivo real,
  // não neste documento.
  ;

// O que o usuário carrega — simples e verificável em O(1)
// Serializado como array de strings no JSON (backend → front)
// e convertido para Set na hidratação da sessão em AuthService
export type PermissoesUsuario = Set<PermissaoKey>;

// Nó da árvore visual — usado APENAS pela tela de gestão de permissões
// Não é fonte da verdade: a fonte da verdade é PermissaoKey acima
export interface NoArvorePermissao {
  label: string;
  chave?: PermissaoKey;          // ausente em nós-pai (agrupadores)
  filhos?: NoArvorePermissao[];
}

// FRAGMENTO ILUSTRATIVO — a constante real contém todos os domínios do projeto
export const ARVORE_PERMISSOES: NoArvorePermissao[] = [
  {
    label: 'Usuários',   // exemplo de domínio simples (apenas CRUD)
    filhos: [
      { label: 'Acessar listagem', chave: 'usuarios.acessar' },
      { label: 'Incluir', chave: 'usuarios.gravar.incluir' },
      { label: 'Editar', chave: 'usuarios.gravar.editar' },
      { label: 'Apagar', chave: 'usuarios.apagar' },
    ],
  },
  {
    label: 'Pedidos', // exemplo de domínio com ações não-CRUD
    filhos: [
      { label: 'Acessar listagem', chave: 'pedidos.acessar' },
      {
        label: 'Gravação',
        filhos: [
          { label: 'Incluir', chave: 'pedidos.gravar.incluir' },
          { label: 'Editar', chave: 'pedidos.gravar.editar' },
        ],
      },
      { label: 'Apagar', chave: 'pedidos.apagar' },
      { label: 'Aplicar condição de pagamento', chave: 'pedidos.condicao_pagamento.aplicar' },
      { label: 'Liberar desconto manual', chave: 'pedidos.desconto.liberar_manual' },
    ],
  },
  // ... demais domínios estão no arquivo real
];
```

### Convenção de nomenclatura das chaves

```
dominio.contexto.acao
   │        │      └─ verbo ou substantivo da operação
   │        └─ agrupador funcional (opcional — omitir se desnecessário)
   └─ nome do domínio em snake_case
```

Exemplos corretos:
- `pedidos.acessar` — sem contexto intermediário quando a ação é direta
- `pedidos.gravar.incluir` — contexto `gravar` agrupa as variantes inclusão/edição
- `pedidos.condicao_pagamento.aplicar` — contexto descreve a funcionalidade de negócio

Nunca use `criar` / `editar` como chaves avulsas de nível 2 — use sempre o contexto
`gravar` com filhos `incluir` e `editar`. Isso é deliberado: botão "Gravar" no formulário
é o mesmo elemento para inclusão e edição; o componente decide qual chave checar com base
no estado (ver "Botão contextual" abaixo).

### Como checar no código

```typescript
// FRAGMENTO ILUSTRATIVO — padrão de implementação, não o arquivo completo

// Em AuthService.login() — hidrata a sessão convertendo o array do JSON em Set
this.sessao.set({
  ...payload,
  permissoes: new Set(payload.permissoes as PermissaoKey[]),
});

// Em AuthService (ou PermissionService) — verificação O(1)
temPermissao(chave: PermissaoKey): boolean {
  return this.sessao()?.permissoes.has(chave) ?? false;
}
```

### Botão contextual (inclusão vs. edição no mesmo formulário)

Quando um único botão "Gravar" cobre tanto inclusão quanto edição, o
componente resolve a chave correta — o guard e a diretiva não precisam
saber do contexto:

```typescript
// FRAGMENTO ILUSTRATIVO — aplique o mesmo padrão em qualquer domínio com formulário
// Exemplo usando pedidos; substitua pelo domínio real ao implementar

// qualquer-form.ts
protected get permissaoGravar(): PermissaoKey {
  return this.registroId()              // signal com o id do registro, null se novo
    ? 'dominio.gravar.editar'           // substitua 'dominio' pelo domínio real
    : 'dominio.gravar.incluir';
}
```

```html
<!-- qualquer-form.html — mesmo padrão para qualquer formulário de domínio -->
<p-button
  label="Gravar"
  *appPermissao="permissaoGravar"
  (onClick)="gravar()"
/>
```

### Três pontos de consumo (e só três)

`PermissaoKey` é consumida em **três lugares** — não existe uma quarta forma
de checar permissão espalhada em algum componente avulso:

1. **`permissionGuard(chave: PermissaoKey)`** nas rotas (`*.routes.ts`) —
   bloqueia o carregamento da página inteira se o usuário não tiver a chave.
   Chave de acesso à listagem é tipicamente `'dominio.acessar'`.
2. **`*appPermissao="'dominio.contexto.acao'"`** nos templates — esconde
   botões e seções específicas sem bloquear a rota.
3. **Árvore de checkboxes** renderizada a partir de `ARVORE_PERMISSOES`
   (`core/navegacao/navegacao.model.ts`) no formulário de usuário — onde um
   admin marca/desmarca chaves. A UI lê a árvore; o que é salvo no backend é
   só o `Set` de chaves marcadas.

Se surgir um quarto lugar checando permissão de forma diferente desses três,
é sinal de bug, não de feature nova.

### Adicionando uma nova permissão

1. Adicione a chave em `PermissaoKey` seguindo a convenção de nomenclatura.
2. Adicione a ação correspondente no módulo certo de `ESTRUTURA_APP`
   (`core/navegacao/navegacao.model.ts`) — a árvore de permissões e o menu
   lateral são DERIVADOS dali, então esse é o único lugar a editar.
3. Aplique `*appPermissao` ou `permissionGuard` nos pontos de consumo.
4. Adicione a chave no seed/migração do backend para que ela possa ser
   atribuída a usuários.

### A estrutura do app é uma fonte só: `ESTRUTURA_APP`

`core/navegacao/navegacao.model.ts` declara a hierarquia da aplicação em
quatro níveis, e dela saem por derivação o menu lateral e a árvore de
permissões — que antes eram duas listas paralelas editadas na mão e que
divergiam em silêncio:

```
seção ("Aplicações")        → só no menu, cabeçalho fixo, não colapsa
  grupo ("Cadastros")       → acordeão no menu, nó-pai na árvore
    módulo ("Produtos")     → item clicável no menu, nó na árvore
      ação ("Incluir")      → só na árvore, é a permissão em si
```

Regras que sustentam o arranjo:

- `MENU_PRINCIPAL` e `ARVORE_PERMISSOES` **nunca** são escritos à mão. São
  `.map()`/`.flatMap()` sobre `ESTRUTURA_APP`, no mesmo arquivo.
- A primeira ação de um módulo é, por convenção, a de acesso
  (`dominio.acessar`) — é ela que o menu usa para esconder o item de quem
  não tem permissão.
- Módulo sem ações (ex: Início) fica fora da árvore de permissões e aparece
  sempre no menu. Grupo sem título tem os módulos soltos sob o cabeçalho da
  seção, sem acordeão.
- `permission.model.ts` guarda **só tipos** (`PermissaoKey`,
  `PermissoesUsuario`, `NoArvorePermissao`) e não importa nada em runtime. A
  direção é sempre `navegacao → permissions`, nunca o contrário — é isso que
  impede ciclo de import.
- A seção **não** vira nível na árvore de permissões: quem agrupa permissão é
  o grupo. Renomear uma seção é mudança puramente visual.

Nunca crie uma chave no template sem antes declará-la em `PermissaoKey` —
o TypeScript vai reclamar, e isso é proposital.

## Integração com o backend (FUSE ERP API)

O backend real (`fuse-erp-api/`) já está integrado. O que foi feito:

1. `environment.ts` aponta para `http://localhost:8000` (porta do FastAPI) e
   `mockAuth: false` — o front faz chamadas HTTP reais em desenvolvimento.
2. Os services de domínio (`AuthService` e todos os services de `domains/`)
   ainda têm o branch `if (environment.mockAuth)`
   interno, que agora nunca executa em dev. Isso é intencional: se precisar voltar
   ao modo mock temporariamente (ex: backend offline), basta ligar `mockAuth: true`
   em `environment.ts` — nenhum outro arquivo muda.
3. O `authInterceptor` injeta **dois** headers em todo request:
   - `Authorization: Bearer <token>` — quando há sessão ativa.
   - `X-Device-Id: <uuid>` — **sempre**, inclusive no login. O backend bloqueia
     (400) qualquer login sem esse header.
4. O `DispositivoService` (`core/auth/dispositivo.service.ts`) é o responsável
   pelo `X-Device-Id`: gera um UUID via `crypto.randomUUID()` no primeiro
   carregamento, salva em `localStorage`, e reutiliza em toda sessão futura no
   mesmo navegador. Esse UUID não muda com atualização de browser ou troca de
   rede — é a âncora estável que o backend usa para vincular sessões a dispositivos.

### Contrato de serialização: camelCase em ambos os lados

O backend (FastAPI/Pydantic) serializa todas as respostas em **camelCase** via
`SchemaBase` com `alias_generator = to_camel` — portanto os campos chegam ao
front exatamente com os nomes que os modelos TypeScript definem:
`razaoSocial`, `nomeFantasia`, `criadoEm`, `precoUnitario`, `refreshToken`, etc.

O backend também aceita payloads em camelCase do front (via `populate_by_name = True`
no `SchemaBase`), então o front não precisa converter nada — manda o que já tem.

**Não crie models TypeScript com snake_case.** O contrato é camelCase de ponta
a ponta, e o único lugar que conhece snake_case é o código Python interno do backend.

### Os campos `sync*` nunca entram na regra de negócio

Toda tabela do backend tem cinco campos de sincronização, que chegam ao front
como `syncCreatedAt`, `syncUpdatedAt`, `syncDeletedAt`, `syncVersion` e
`syncSyncedAt`. Eles existem para auditoria e para o futuro processo de
replicação entre réplicas — e **é proibido usá-los como dado de negócio**.

Conta como uso proibido, em qualquer tela:

- ordenar eventos por `syncCreatedAt` (linha do tempo, histórico, ocorrências);
- exibir `syncCreatedAt`/`syncUpdatedAt` como se fosse um fato do negócio
  ("registrado em", "entregue em", "aprovado em");
- filtrar período por `syncUpdatedAt` — o período é sempre a data de negócio
  (data do pedido, data de emissão, data da interação);
- usá-los em qualquer cálculo (prazo, SLA, idade do documento).

O motivo é que esses campos descrevem **a linha**, não o **fato**. Um
reprocessamento da integração, uma correção de texto ou uma futura rotina de
replicação tocam a linha e mexem em `syncUpdatedAt` sem que nada tenha
acontecido no negócio. Quem ordenou a timeline por `syncCreatedAt` vê a ordem
mudar sozinha; quem filtrou por `syncUpdatedAt` vê o documento entrar e sair do
período.

**Quando o negócio precisa de um instante, o backend cria uma coluna própria** e
o front consome essa coluna. Foi assim que nasceu
`entrega_nota_interacoes.data_interacao` (`dataInteracao`), que substituiu o uso
de `syncCreatedAt` na linha do tempo da gestão de entregas.

O uso legítimo dos `sync*` é diagnóstico — "quando esta linha foi tocada pela
última vez pela integração" —, e nesse caso o rótulo na tela precisa deixar
claro que é sobre o registro, não sobre o fato.

## O vínculo com o sistema de origem (`sistemaOrigemId`) não é da tela

Todo campo terminado em **`sistemaOrigemId`** guarda a identidade do registro no
ERP: `sistemaOrigemId`, `empresaSistemaOrigemId`, `pedidoSistemaOrigemId`,
`produtoSistemaOrigemId`. Quem cria e mantém esse vínculo é a **integração**,
nunca um formulário.

**A regra, do lado do front, são duas frases:**

1. Formulário de domínio **não edita** campo de vínculo. Ele não aparece como
   input, e não vai no payload.
2. Se o formulário precisar **exibir** o vínculo (para conferência), ele é
   somente-leitura.

### Por que isso está escrito aqui, e não só no backend

Porque o dano nasceu aqui. A tela de usuários não envia `sistemaOrigemId` — o
que está certo. Mas o backend, ao receber um `PUT` sem o campo, gravava `null` em
cima do valor existente. O front cumpria a regra e o registro perdia o vínculo
mesmo assim.

O backend foi corrigido (ver `backend/ARCHITECTURE.md` → "O vínculo com o
sistema de origem nunca é apagado"), e a proteção agora está lá, que é o lugar
certo: a barreira real é do servidor. Esta seção existe para o outro lado da
mesma moeda — **não tente "consertar" isso pelo front** mandando o campo de
volta no payload.

O efeito daquele defeito foi caro e apareceu longe da causa: o funcionário
`00168` perdeu o vínculo numa edição de tela, e **dias depois** a integração de
pedidos parou por três dias, porque todo pedido daquele vendedor passou a ser
recusado com 404.

### O que NÃO fazer

```typescript
// ERRADO — reenviar o vínculo para "não deixar apagar"
gravar(): void {
  this.service.atualizar(this.id(), {
    ...this.form.value,
    sistemaOrigemId: this.usuario()?.sistemaOrigemId,  // não faça isso
  });
}
```

Isso parece defensivo e é o contrário: transforma um campo que a tela não
governa em algo que a tela passa a governar. Basta o formulário carregar um
registro desatualizado para ele gravar um vínculo velho por cima do novo. A
garantia é do backend, e ela já existe.

```html
<!-- ERRADO — o vínculo não é editável -->
<input type="text" formControlName="sistemaOrigemId" />
```

### O que fazer

Se o vínculo precisa aparecer, ele é informação, não campo:

```html
<!-- CERTO — exibe para conferência, sem editar -->
@if (usuario()?.sistemaOrigemId) {
  <p class="text-xs text-gray-500">
    Código no ERP: <span class="font-mono">{{ usuario()!.sistemaOrigemId }}</span>
  </p>
}
```

No `.model.ts`, o campo entra no tipo de **resposta** (a tela lê) e fica fora do
tipo de **payload** de gravação (a tela não escreve) — a menos que o consumidor
daquele service seja a própria integração.

### A exceção que existe hoje: `produto-form`

O formulário de produtos **tem** um input de `sistemaOrigemId`, e é a única tela
que edita um campo de vínculo. Isso é anterior a esta seção.

Ela não viola a regra principal — desde a correção do backend, campo vazio cai
no valor já gravado e **não apaga nada**. O que ela permite é *trocar* o vínculo
à mão, o que só faz sentido para ligar um produto cadastrado manualmente a um
código do ERP.

Se essa capacidade não for usada de verdade, o input deve virar exibição
somente-leitura, como no exemplo acima. Enquanto existir, é exceção conhecida e
única — não é precedente para telas novas.

### Onde isso importa hoje

Nas telas de cadastro dos domínios alimentados pela integração: clientes,
produtos, marcas, empresas, usuários e pedidos. Ao criar uma tela nova para um
domínio com campo de vínculo, siga o desenho desta seção.

## Regras de lint / import (a fazer cumprir)

> Esta seção é a **autoridade** sobre o que pode atravessar a fronteira de um
> domínio no front. Se algum outro trecho deste documento parecer dizer outra
> coisa, vale o que está escrito aqui. A regra equivalente do backend está em
> `backend/ARCHITECTURE.md` → "Regras de import entre domínios", e as duas
> seguem o mesmo critério.

### Direção dos imports (regras estruturais)

- **`domains/*` pode importar de `core/*` e `shared/*` livremente.**
- **`core/*` nunca importa de `domains/*`.**
- **`shared/*` nunca importa de `core/*` nem de `domains/*`** — tem que ser
  genérico o bastante pra não depender de nada específico da aplicação.
- **`domains/X` importa de `domains/Y` somente nas formas autorizadas abaixo.**

### O critério que decide tudo: o que está atravessando a fronteira

A pergunta certa não é *"esses dois domínios podem se conhecer?"*. É
**"o que está passando de um para o outro?"**:

| O que atravessa | Permitido? |
|---|---|
| **Leitura** — pedir um dado ao domínio dono dele | Sim |
| **Escrita** — criar/alterar/apagar registro de outro domínio | Não. Nunca. |
| **Regra reimplementada** — refazer por conta própria a regra ou a chamada HTTP do outro | Não. Nunca. |

Um domínio é **dono** dos seus dados e das suas regras. Os outros podem
*perguntar*, nunca *mexer*, e nunca *adivinhar*.

No front isso é mais simples que no backend: services Angular são singletons
(`providedIn: 'root'`), então **injetar o service do domínio dono é o canal
correto** — é exatamente para isso que existe a injeção de dependência do
Angular. Não existe aqui o equivalente do `<dominio>_publico.py` do backend.

> **A regra de escrita aqui é mais dura que a do backend, e isso é de propósito.**
> Lá, um domínio pode pedir a outro que altere o estado dele por uma função de
> borda sem `commit()` (ver "Escrita pela borda" no `backend/ARCHITECTURE.md`),
> porque tudo acontece numa transação só. Aqui não existe transação: cada
> chamada é um HTTP independente, que pode falhar sozinho e deixar metade feita.
> Escrita cruzada no front continua sendo **não. Nunca.** — se uma tela precisa
> gravar em dois domínios, quem coordena isso é **um endpoint do backend**, não
> dois `subscribe` em sequência.

### O que PODE (com exemplos concretos)

| Caso | Exemplo em ERP |
|---|---|
| Injetar o service de outro domínio para **ler** (`listar`, `buscar`, `obterPorId`) | `cliente-form` injeta `CidadeService` para o combobox de cidade |
| Ler cadastro para montar um documento | `pedido-form` injeta `ClienteService` e `ProdutoService` para pesquisar cliente e produto |
| Importar o `.model.ts` (interface) de outro domínio | `pedido.model.ts` referenciando o tipo `Cliente` — é tipo puro, não carrega comportamento |

### O que NÃO PODE (com exemplos concretos)

| Caso | Exemplo em ERP | Por que é proibido |
|---|---|---|
| Refazer a chamada HTTP do outro domínio | `cliente.service.ts` chamando `http.get('/cidades')` por conta própria | Duplica o endpoint. Se a rota ou o contrato mudar, quebra em todo lugar que copiou |
| Chamar método de **escrita** do service de outro domínio | `pedido-form` chamando `clienteService.criar(...)` | Escrita cruzada. Se precisa cadastrar cliente, navegue para a tela de clientes |
| Importar componente de página de outro domínio | usar `<app-cliente-list>` dentro de `domains/pedidos/` | Página é privada do domínio. Se for reaproveitável, o lugar dela é `shared/ui/` |
| Reimplementar regra de negócio do outro | tela de relatório recalculando o total do pedido com fórmula própria | Passam a existir duas verdades, que divergem em silêncio |

### O conceito, sem ambiguidade

Rode este roteiro na ordem. Pare no primeiro item que descrever o seu caso:

1. **Preciso exibir/pesquisar dado de outro domínio?** → injete o service dele
   e chame um método de **leitura**.
2. **Preciso só do tipo TypeScript?** → importe o `.model.ts` dele.
3. **Preciso criar/alterar/apagar registro de outro domínio?** → **pare.**
   Navegue para a tela daquele domínio; não chame a escrita de fora.
4. **Preciso de um componente visual que já existe em outro domínio?** →
   **pare.** Se é genérico, mova para `shared/ui/`; se não é, duplique o
   template no seu domínio.

**Se nenhum dos quatro descreve o que você está fazendo, não invente um quinto
caminho: pare e pergunte.** Um import fora dessas quatro formas é sempre um bug
de arquitetura, mesmo que o código funcione e a tela renderize.

Quando configurar lint de verdade, a ferramenta recomendada é
`eslint-plugin-boundaries` ou regras de path customizadas no ESLint flat
config, restringindo imports por padrão de path.

## Convenções de nomenclatura

- Tudo em **português** — variáveis, métodos, rotas, mensagens de erro,
  labels. Isso é proposital (reflete o domínio de negócio real do time) e
  deve ser mantido consistente; não misture inglês no meio.
- Arquivos: `kebab-case`. Classes: `PascalCase`. Métodos/variáveis:
  `camelCase` em português (`criarMapaPermissoesVazio`, `apagar`,
  `permissoesFiltradas`).
- Componentes de página ficam em pastas com o mesmo nome em kebab-case:
  `usuario-list/usuario-list.ts` exporta a classe `UsuarioList`.

## Stack técnica

- **Angular 20**, 100% standalone components (sem `NgModule`), `signals`
  para estado local e de sessão, `@if`/`@for`/`@switch` (control flow novo,
  não `*ngIf`/`*ngFor` salvo na diretiva estrutural customizada
  `*appPermissao`, que por natureza precisa ser uma diretiva estrutural).
- **Roteamento com lazy loading** (`loadComponent`/`loadChildren`) em todo
  domínio — cada domínio é seu próprio chunk JS, carregado só quando
  acessado.
- **Tailwind CSS** (versão compatível com Angular 20) para utilitários de
  layout e espaçamento. PrimeNG e Tailwind coexistem sem conflito: PrimeNG
  cuida dos componentes interativos com seu próprio design token, Tailwind
  cuida do layout da página e dos espaçamentos entre componentes. Não use
  classes Tailwind para sobrescrever internos de componentes PrimeNG — use o
  mecanismo de Pass Through (PT) ou variáveis CSS do tema para isso.
- **PrimeNG v20** como biblioteca de componentes UI. Detalhes de setup e uso
  estão na seção abaixo.
- **Reactive Forms** (`FormBuilder`, `ReactiveFormsModule`) em todos os
  formulários de domínio. Usamos `inject()` em vez de injeção via
  construtor sempre que o form é inicializado como *field initializer* logo
  abaixo dos `inject()` — isso evita o erro clássico do TypeScript
  "property used before its initialization" que ocorre se o form depender
  de uma propriedade injetada via parâmetro de construtor.

## PrimeNG v20 — setup e regras de uso

### Instalação e compatibilidade

```bash
npm install primeng @primeuix/themes
```

PrimeNG v20 requer **Angular 20** e é a versão mínima recomendada para esse
par. Não use versões anteriores do PrimeNG com Angular 20 — há breaking
changes nas APIs de Signal e standalone que tornam versões antigas
incompatíveis.

> **Licença:** PrimeNG v20 adota modelo dual Community/Commercial (PrimeUI).
> Projetos internos corporativos devem avaliar a necessidade de licença
> comercial em https://primeui.dev/pricing. Registre a chave em
> `app.config.ts` via `providePrimeNG({ license: '...' })` se aplicável.

### Configuração global (`app.config.ts`)

`providePrimeNG` é o único ponto de configuração global da biblioteca.
**Não existe mais script global carregado via `angular.json`** — diferente
do Preline (que exigia `scripts: ["node_modules/preline/dist/preline.js"]`
no `angular.json`), o PrimeNG é puro Angular e não depende de inicialização
imperativa fora do ciclo de vida do framework.

```typescript
// FRAGMENTO ILUSTRATIVO — estrutura esperada do app.config.ts
// O arquivo real pode conter providers adicionais não listados aqui.
// Ao adicionar um provider novo, inclua no arquivo real sem remover os existentes.

// app.config.ts
import { ApplicationConfig, LOCALE_ID } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { registerLocaleData } from '@angular/common';
import { providePrimeNG } from 'primeng/config';
import Aura from '@primeuix/themes/aura';
import { authInterceptor } from './core/auth/auth.interceptor';
import { routes } from './app.routes';
import localePt from '@angular/common/locales/pt';

registerLocaleData(localePt);

export const appConfig: ApplicationConfig = {
  providers: [
    provideRouter(routes),
    provideHttpClient(withInterceptors([authInterceptor])),
    { provide: LOCALE_ID, useValue: 'pt-BR' },
    providePrimeNG({
      theme: { preset: Aura },
      // ripple: true, // opcional — habilita efeito ripple globalmente
    }),
    // outros providers do projeto ficam aqui
  ],
};
```

**Temas disponíveis:** `Aura` (padrão recomendado), `Material`, `Lara`,
`Nora`. Todos importados de `@primeuix/themes/<nome>`. Escolha um tema e
mantenha consistente — não misture temas entre domínios.

### Importação de componentes nos standalone components

Cada componente PrimeNG é um standalone Angular module importado
individualmente. **Nunca importe um barrel `primeng/primeng` genérico** —
isso quebra tree-shaking e aumenta o bundle desnecessariamente.

```typescript
// FRAGMENTO ILUSTRATIVO — demonstra o padrão de importação individual.
// Importe apenas os módulos que o componente real usar; não copie esta lista
// como se fosse a lista canônica de imports de qualquer componente.

// exemplo: um componente de listagem qualquer
import { Component } from '@angular/core';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';

@Component({
  standalone: true,
  imports: [TableModule, ButtonModule, ToastModule], // somente o que este componente usa
  providers: [MessageService],
  templateUrl: './meu-componente.html',
})
export class MeuComponente { ... }
```

### Mapeamento Preline → PrimeNG (componentes mais usados)

| Funcionalidade         | Era (Preline)                    | É agora (PrimeNG v20)                     |
|------------------------|----------------------------------|-------------------------------------------|
| Dropdown/Select        | `data-hs-select`                 | `<p-select>` (`SelectModule`)             |
| Modal/Dialog           | `data-hs-overlay`                | `<p-dialog>` (`DialogModule`)             |
| Accordion              | `data-hs-accordion`              | `<p-accordion>` (`AccordionModule`)       |
| Tabs                   | `data-hs-tabs`                   | `<p-tabs>` (`TabsModule`)                 |
| Tooltip                | `data-hs-tooltip`                | `pTooltip` directive (`TooltipModule`)    |
| Multiselect            | implementação customizada        | `<p-select [multiple]="true">` ¹          |
| Datepicker             | `data-hs-datepicker`             | `<p-datepicker>` (`DatePickerModule`)     |
| Toast/Notificação      | não havia padrão único           | `<p-toast>` + `MessageService`            |
| Tabela com paginação   | tabela HTML manual               | `<p-table>` (`TableModule`)               |
| Confirmação de ação    | `window.confirm()` ou modal manual | `<p-confirmdialog>` + `ConfirmationService` |
| Sidebar/Drawer         | CSS manual                       | `<p-sidebar>` (`SidebarModule`) ²         |
| Breadcrumb             | HTML manual em `page-header`     | `<p-breadcrumb>` (`BreadcrumbModule`)     |
| Spinner de loading     | CSS manual                       | `<p-progressspinner>` (`ProgressSpinnerModule`) |

> ¹ `MultiSelect` como componente separado existe no v20 mas está **deprecated** —
> use `<p-select [multiple]="true">` para novas implementações.
>
> ² `Drawer` é o componente do v20 que substitui o `Sidebar` do Preline.
> Ideal para o menu lateral do shell quando em modo mobile/offcanvas.

### Serviços globais do PrimeNG que precisam de provider

Alguns componentes dependem de serviços que devem ser declarados no
`providers` do componente ou no provider raiz. Regra: declare no componente
que consome, não globalmente, exceto onde indicado.

| Serviço             | Onde declarar         | Usado por                          |
|---------------------|-----------------------|------------------------------------|
| `MessageService`    | componente que dispara toasts | `ToastModule`              |
| `ConfirmationService` | componente que confirma ações | `ConfirmDialogModule`    |
| `DialogService`     | componente que abre dialogs dinâmicos | `DynamicDialogModule` |

### PrimeIcons

PrimeNG v20 usa ícones SVG via `PrimeIcons` (pacote `primeicons`).
O `shared/ui/icon.component.ts` existente pode ser mantido para ícones
customizados do sistema, mas para ícones padrão dentro de componentes
PrimeNG (botões, inputs, menus), use a API nativa do componente:

```html
<!-- Botão com ícone PrimeNG -->
<p-button icon="pi pi-save" label="Salvar" />

<!-- Ícone avulso via classe CSS -->
<i class="pi pi-user"></i>
```

O CSS do PrimeIcons é carregado automaticamente pelo PrimeNG — não é
necessário nenhuma entrada em `angular.json`. Se precisar de ícones além do
catálogo PrimeIcons, use o `icon.component.ts` existente com SVGs inline.

> **Atenção:** o pacote `primeng/icons` (ícones como componentes Angular
> standalone) está **deprecated** e será removido numa versão futura. Não use
> `import { ... } from 'primeng/icons/...'` em código novo.

### Pass Through (PT) — como customizar internos sem quebrar o tema

Quando precisar ajustar o visual interno de um componente PrimeNG (ex:
adicionar uma classe Tailwind em um elemento interno), use a API de
**Pass Through**, não sobrescreva o CSS global:

```html
<p-table [pt]="{ header: { class: 'bg-gray-50' } }" ... />
```

Isso garante que a customização seja localizada e não afete outros usos do
mesmo componente na aplicação.

### O que NÃO fazer com PrimeNG

- **Não carregue nada do PrimeNG via `angular.json → scripts`** — diferente
  do Preline, o PrimeNG não tem script JS externo. Tudo é importado via
  módulos Angular.
- **Não chame `HSStaticMethods.autoInit()` ou equivalente** — isso era
  específico do Preline para inicializar componentes JS no DOM. O PrimeNG
  não precisa de inicialização imperativa.
- **Não misture componentes Preline com PrimeNG** — se encontrar remnantes
  de `data-hs-*` no HTML ou `hs-*` em classes, remova e substitua pelo
  equivalente PrimeNG da tabela de mapeamento acima.
- **Não use `MultiSelect` standalone em código novo** — está deprecated no
  v20. Use `<p-select [multiple]="true">`.

## Onde cada coisa fica (perguntas frequentes para o agente de IA)

- **"Preciso adicionar um campo novo no formulário de cliente."** → mexe só
  em `domains/clientes/cliente.model.ts` (tipo), `cliente-form/cliente-form.ts`
  (FormGroup) e `cliente-form/cliente-form.html` (input). Se o campo for novo
  no banco, atualizar o model Python e gerar migração no backend também.
- **"Preciso adicionar um domínio novo (ex: `fornecedores`)."** →
  1. Adiciona as chaves do novo domínio em `PermissaoKey` (`permission.model.ts`),
     seguindo a convenção `fornecedores.acessar`, `fornecedores.gravar.incluir`, etc.
  2. Adiciona o módulo `Fornecedores` (com rótulo, ícone, rota e as ações) no
     grupo certo de `ESTRUTURA_APP` (`core/navegacao/navegacao.model.ts`).
     Isso já resolve menu lateral E árvore de permissões de uma vez.
  3. Cria `domains/fornecedores/` seguindo exatamente a forma de
     `domains/clientes/` (copie a estrutura: `.model.ts`, `.service.ts`,
     `-list/`, `-form/`, `.routes.ts`).
  4. Registra a rota em `app.routes.ts` (`loadChildren`) com
     `canActivate: [permissionGuard('fornecedores.acessar')]`.
  5. Registra as novas chaves no seed/migração do backend — os dois lados
     precisam estar em sync.
- **"O usuário não devia ver o botão de apagar."** → confirma que o botão
  está dentro de `*appPermissao="'dominio.apagar'"` no template da página de
  listagem. A chave deve existir em `PermissaoKey` em `permission.model.ts`.
- **"Preciso bloquear uma rota inteira por permissão."** → no `*.routes.ts`
  do domínio, aplica `canActivate: [permissionGuard('dominio.acessar')]`.
  Use sempre a chave `.acessar` do domínio para guards de rota.
- **"Preciso adicionar uma permissão nova que não é CRUD (ex: liberar desconto)."** →
  1. Adiciona a chave em `PermissaoKey` (`'pedidos.desconto.liberar_manual'`).
  2. Adiciona a ação no módulo `Pedidos` dentro de `ESTRUTURA_APP`
     (`core/navegacao/navegacao.model.ts`).
  3. Aplica `*appPermissao` no botão/elemento do template.
  4. Registra a chave no seed/migração do backend.
  Nunca crie uma chave só no template sem declará-la no union type.
- **"Como funciona o mock de autenticação?"** → `AuthService.loginMock()`,
  ativado via `environment.mockAuth = true`. Hoje está `false` (backend real).
  Útil para desenvolver com o backend offline — só mudar o flag em
  `environment.ts`, nenhum outro arquivo muda.
- **"O interceptor HTTP precisa de alguma mudança?"** → Não para uso normal.
  O `authInterceptor` já injeta `X-Device-Id` e `Authorization: Bearer` em
  todo request automaticamente. Para adicionar outro header global, o lugar
  certo é `auth.interceptor.ts` — nunca adicionar headers diretamente em
  services de domínio.
- **"O que é o `DispositivoService` e posso ignorá-lo?"** → Não ignore. Ele
  gera o UUID estável do dispositivo (`X-Device-Id`) que o backend exige em
  todo request (400 no login sem ele, 401 nos demais). É infraestrutura pura
  — não tem lógica de negócio e não deve ser chamado por domínios, só pelo
  interceptor.
- **"Os nomes dos campos no JSON batem com os modelos TypeScript?"** → Sim.
  O backend serializa tudo em camelCase via `SchemaBase` — os campos chegam
  exatamente com os nomes que os `interface` TypeScript definem. Não crie
  modelos TypeScript com snake_case.
- **"Como adiciono um componente PrimeNG num standalone component?"** →
  Importe o módulo específico no array `imports` do decorator `@Component`.
  Veja a seção "Importação de componentes" acima. Nunca importe tudo de uma
  vez via barrel genérico.
- **"Qual tema PrimeNG estamos usando?"** → `Aura` (importado de
  `@primeuix/themes/aura`), configurado em `app.config.ts` via
  `providePrimeNG`. Para trocar de tema, mude só essa linha — nenhum outro
  arquivo precisa mudar.
- **"Ainda tem alguma coisa do `angular.json → scripts` do Preline?"** →
  Não deve ter. Se encontrar `"node_modules/preline/dist/preline.js"` ou
  qualquer entrada Preline lá, remova. PrimeNG não usa esse mecanismo.

## O que é decoração visual (não confundir com feature pendente)

A sidebar (`core/navegacao/navegacao.model.ts` → seção "Aplicações") pode ter
itens fictícios replicando o template visual de referência (Analytics,
Finanças, Crypto, Gerador de imagens IA, Academia, Calendário, Mensageiro,
E-commerce, Gerenciador de arquivos, Central de ajuda, Correio, Notas,
Scrumboard). **Esses itens não têm `rota` definida e não navegam para lugar
nenhum** — existem só para fidelidade visual com o design de referência.
Da mesma forma, o painel de "equipe" à direita no `shell.html`
(`equipeFicticia`) é só decoração visual, sem dado real por trás.

Não trate esses itens como bugs ("o link não funciona") nem como features
faltando — eles são propositalmente não-funcionais. Se algum desses vier a
virar feature real no futuro, vira um domínio novo seguindo o mesmo padrão
de `domains/`.