---
name: angular-primeng-manutencao
description: >
  Orientações de processo e contenção para manutenção de páginas Angular 20 com
  PrimeNG 20, Tailwind CSS v4 e ícones Lucide. Use quando for alterar, corrigir
  ou estender componentes em um projeto existente.
---

# Manutenção de páginas Angular 20 + PrimeNG + Tailwind

Aborde cada tarefa como um desenvolvedor sênior chamado para fazer uma intervenção
cirúrgica em código de produção: o objetivo não é refatorar, não é modernizar,
não é demonstrar conhecimento de PrimeNG. O objetivo é resolver exatamente o que
foi pedido, sem deixar rastros desnecessários.

## Ancore-se no código existente antes de escrever qualquer coisa

Se a tarefa não especificar como algo deve ser implementado, **identifique como o
projeto já resolve o mesmo tipo de problema antes de propor qualquer solução**.
Localize no próprio projeto:

- Um componente que já usa o mesmo PrimeNG component que você vai usar.
- Um padrão de signal input (`input()`, `output()`) já em uso no mesmo domínio.
- A forma como o projeto importa e registra módulos PrimeNG nos `imports[]`.
- A convenção de `styleClass`, `pt` (pass-through) ou classes Tailwind que o
  projeto já adotou para aquele tipo de elemento.

Só depois de mapear essa referência local declare qual solução vai adotar —
e ela deve ser consistente com o que já existe. Inventar um padrão novo quando
um análogo local existe é a forma mais comum de um IA introduzir divergência
silenciosa em uma codebase.

## Princípios de intervenção

**Escopo carrega intenção.** Quando o pedido é "adicionar um campo de filtro",
a intenção é um campo — não um refactor do formulário inteiro, não uma extração
de serviço, não novos tipos TypeScript que ninguém pediu. O tamanho da mudança
deve ser proporcional ao tamanho do pedido.

**O componente PrimeNG certo já resolve o problema.** Antes de escrever lógica
custom de UI, verifique se o componente nativo já oferece a prop ou slot que
você precisaria implementar manualmente. Um `<p-select [filter]="true">` já tem
busca interna. Um `<p-table [loading]="true">` já tem overlay de carregamento.
Implementar à mão o que o componente já oferece é desperdício e cria inconsistência
visual com o resto da aplicação.

**Tailwind é layout e espaçamento. PrimeNG é comportamento e estado.** Não use
classes Tailwind para simular estados que o PrimeNG já expressa via `severity`,
`variant`, `outlined`, `text`, `size`. Não use props do PrimeNG para fazer o que
é trabalho do Tailwind — como definir gap entre elementos ou alinhar um flex container.
Quando os dois se misturam corretamente, o template fica legível. Quando um tenta
fazer o trabalho do outro, o template acumula ruído.

**Estrutura é informação.** Antes de adicionar um `<p-card>` ou um `<p-panel>`,
pergunte se o agrupamento visual comunica algo verdadeiro sobre a relação dos dados —
ou se é só decoração. Um container a mais é um nível extra de aninhamento, mais
seletores CSS para especificidade, mais superfície para conflito de estilos.

**Contenha o escopo de arquivos.** Cada tarefa deve tocar no máximo dois arquivos.
Se a solução exige mais que isso, é sinal de que o escopo foi mal compreendido ou
que existe uma abstração ausente que não foi pedida — nesse caso, resolva só o
que foi pedido e aponte o problema separadamente.

## Processo: mapear → planejar → criticar → implementar

Trabalhe em duas passagens. Na primeira, **não escreva código** — apenas:

1. Identifique o arquivo exato onde a mudança vai acontecer.
2. Localize o análogo local: qual componente do projeto já resolve algo parecido.
3. Descreva em uma frase o que vai ser adicionado/alterado e por quê é suficiente.
4. Liste quais imports PrimeNG serão necessários e confirme que ainda não existem
   no arquivo.

Na segunda passagem, revise esse plano antes de escrever qualquer linha:

- A mudança resolve exatamente o que foi pedido, nem mais nem menos?
- Você está adicionando algum import, tipo, serviço ou arquivo que não é
  estritamente necessário para essa tarefa? Se sim, remova.
- O padrão que você vai usar existe em outro lugar do projeto? Se não existe,
  você está introduzindo um padrão novo — o que exige justificativa explícita.
- A mudança vai criar conflito de CSS layer entre PrimeNG e Tailwind?
  (ver seção de especificidade abaixo)

Só depois de confirmar essas respostas escreva a implementação.

Faça o máximo dessa reflexão internamente. Apresente ao usuário apenas a
implementação final e, se houver decisão não óbvia, uma frase explicando o
que você optou por não fazer e por quê.

## Contenção e autocrítica

Código gerado por IA tende a acumular em três padrões ruins que você deve
ativamente evitar:

1. **Criar arquivo novo quando editar o existente resolve.** Um novo `*.service.ts`
   para lógica de duas linhas, um novo `*.pipe.ts` para uma transformação inline,
   um novo `*.interface.ts` para um tipo já inferível. Só crie arquivo novo quando
   o projeto já tem convenção estabelecida para aquele tipo de separação.

2. **Importar módulo inteiro quando o standalone basta.** Em Angular 20, cada
   componente PrimeNG pode ser importado individualmente. `import { TableModule }`
   quando só `p-table` é usado no template é importação desnecessária. Importe
   o mínimo que o template usa.

3. **Adicionar classes Tailwind sobre props PrimeNG que já resolvem.** Ver
   `class="text-red-500"` quando `severity="danger"` existe. Ver
   `class="w-full"` dentro de um `<p-fluid>` que já faz isso. Essas redundâncias
   não causam bug imediato mas acumulam como ruído.

Antes de entregar, aplique o teste do espelho: olhe para cada linha que você
adicionou e pergunte se ela está lá porque é necessária ou porque pareceu boa
ideia na hora. Remova o que não for necessário. A implementação certa normalmente
é menor do que a primeira que vem à mente.

## Referência de componentes PrimeNG

Se precisar de informações detalhadas sobre uso, props, slots ou eventos de
qualquer componente PrimeNG, consulte a documentação otimizada para LLMs em:
`https://primeng.dev/llms/llms.txt`

## Vocabulário de componentes — use o termo correto do PrimeNG 20

Muitos nomes mudaram entre versões. Usar o nome errado força o usuário a corrigir
depois. No PrimeNG 20, os nomes corretos são:

| Padrão UI               | Componente correto          | Módulo a importar              |
|-------------------------|-----------------------------|-------------------------------|
| Select / dropdown       | `<p-select>`                | `SelectModule`                |
| Calendário / datepicker | `<p-datepicker>`            | `DatePickerModule`            |
| Overlay lateral         | `<p-drawer>`                | `DrawerModule`                |
| Overlay flutuante       | `<p-popover>`               | `PopoverModule`               |
| Toggle on/off           | `<p-toggleswitch>`          | `ToggleSwitchModule`          |
| Multi-seleção           | `<p-multiselect>`           | `MultiSelectModule`           |
| Senha                   | `<p-inputpassword>`         | `InputPasswordModule`         |
| Tags livres             | `<p-inputtags>`             | `InputTagsModule`             |

Nunca use `DropdownModule`, `CalendarModule`, `SidebarModule` ou `OverlayPanelModule`
— são nomes de versões anteriores que ainda podem aparecer em treinamento de LLM
mas não existem mais no PrimeNG 20.

## Ícones Lucide — padrão do projeto

O projeto usa `@lucide/angular` (não `lucide-angular`, que está depreciado).
Ícones são usados via `<lucide-icon name="..." [size]="16" />` com o componente
`LucideIcon` importado no `imports[]` do componente standalone.

Ao adicionar um ícone em uma tela existente, verifique primeiro se o mesmo ícone
já é usado em outro componente do mesmo domínio — use o mesmo `name` para manter
consistência semântica. Não use ícone de ação diferente para a mesma operação em
telas diferentes (ex.: não use `"trash"` em uma tela e `"x"` em outra para a
mesma ação de remoção).

Ícones dentro de botões PrimeNG usam o slot `icon` via `ng-template`:

```html
<p-button severity="danger" [text]="true" (onClick)="remover(item)">
  <ng-template pTemplate="icon">
    <lucide-icon name="trash-2" [size]="14" />
  </ng-template>
</p-button>
```

Não misture PrimeIcons (`pi pi-trash`) com Lucide no mesmo projeto — escolha um
e mantenha.

## Especificidade CSS — quando Tailwind e PrimeNG conflitam

O projeto deve ter no `styles.scss`:

```scss
@import "tailwindcss";
@import "tailwindcss-primeui";
@layer tailwind, primeng;
```

Com essa configuração, utilities Tailwind sobrescrevem estilos de componente
PrimeNG automaticamente. Se você encontrar um comportamento visual inesperado
em uma tela, verifique primeiro se essa ordem de layers está correta antes de
adicionar `!important` ou `::ng-deep`.

Nunca adicione `::ng-deep` em código novo — use `[pt]` (pass-through) para
customizar elementos internos de componentes PrimeNG:

```html
<!-- Não faça -->
<p-table class="minha-tabela" /> <!-- + ::ng-deep .minha-tabela .p-datatable-thead -->

<!-- Faça -->
<p-table [pt]="{ header: { class: 'bg-surface-50 text-sm' } }" />
```

As classes semânticas do plugin `tailwindcss-primeui` como `bg-primary`,
`text-muted-color`, `bg-surface-100` e `border-surface` respeitam o tema ativo
e o dark mode automaticamente — prefira-as a cores hardcoded como `bg-indigo-500`.

## Signals e inputs — padrão Angular 20

Em componentes existentes, respeite o padrão já em uso. Se o componente usa
`@Input()`, não migre para `input()` sem pedido explícito. Se usa `input()`,
não reverta para `@Input()`.

Ao criar inputs em componentes novos exigidos pela tarefa, use o padrão Angular 20:

```typescript
// correto
label    = input<string>('');
disabled = input<boolean>(false);
onChange = output<string>();

// não faça em código novo
@Input() label: string = '';
@Output() onChange = new EventEmitter<string>();
```

Computed values derivados de signals usam `computed()`, não getters calculados
na renderização:

```typescript
// correto
labelFormatado = computed(() => this.label().toUpperCase());

// evite em código signal-based
get labelFormatado() { return this.label.toUpperCase(); } // só válido se label for @Input()
```

## Sobre texto em telas

Texto em interface é código — merece o mesmo cuidado. Labels, tooltips, mensagens
de erro e estados vazios devem ser escritos do ponto de vista do usuário, não da
implementação. "Nenhum registro encontrado" comunica estado. "Array vazio" não
comunica nada.

Mensagens de erro de validação devem dizer o que está errado e como corrigir,
não repetir o nome do campo: "Informe um CNPJ válido" em vez de "CNPJ inválido".
Ações em botões descrevem o que acontece ao clicar: "Salvar rascunho", não "OK".
O rótulo do botão que abre o processo e a mensagem de confirmação usam o mesmo
verbo.

Quando uma tela existente tem texto inconsistente com essas regras e a tarefa não
inclui revisão de copy, não altere o texto — aponte o problema separadamente se
for relevante.
