# Bipagem: como um código lido vira um produto

Documento de **regra de negócio**, não de código. Descreve o que a expedição faz
com o que o leitor do coletor entrega, e — mais importante — **por que** cada
passo existe. Toda decisão aqui nasceu de um caso concreto do galpão.

A implementação mora em dois arquivos:

| Arquivo | Responsabilidade |
|---|---|
| `app/shared/gs1.py` | Decide **o que foi lido** e produz os códigos a procurar |
| `app/domains/produtos/produto_publico.py` → `obter_por_codigo_barras` | Decide **qual produto é**, procurando no cadastro |

A expedição (`expedicao_service.bipar`) não procura produto por conta própria:
ela pergunta ao domínio dono do cadastro e recebe o produto ou nada.

---

## Visão geral

```
leitura do coletor
        │
        ▼
┌─────────────────────────────────────────┐
│ ETAPA 1 — que tipo de leitura é essa?   │   shared/gs1.py
│ linear? QR Code GS1? Digital Link?      │
└─────────────────────────────────────────┘
        │  lista de códigos candidatos
        ▼
┌─────────────────────────────────────────┐
│ ETAPA 2 — busca exata, em 3 origens     │   produto_publico
│ nota → logística → DUN-14               │
└─────────────────────────────────────────┘
        │  não achou nada?
        ▼
┌─────────────────────────────────────────┐
│ ETAPA 3 — desempate pelo DV             │   produto_publico
│ ignora o último dígito, exige 1 só      │
└─────────────────────────────────────────┘
        │
        ▼
  produto  ou  422 "não cadastrado"
                     │
                     ▼
        ┌─────────────────────────────────────────┐
        │ Botão "Verificar ANVISA" (sob demanda)  │   produto_service
        │ confere o código na CMED e vincula      │   + shared/tabela_cmed
        └─────────────────────────────────────────┘
```

---

## Etapa 1 — Que tipo de leitura é essa?

O leitor entrega **uma string**, e ela pode ser duas coisas bem diferentes.

### Código de barras linear

EAN-13, DUN-14, código interno. O conteúdo **é** o código. Não há nada a
interpretar, e a string vai inteira para a etapa 2.

### QR Code / DataMatrix GS1

O conteúdo é uma sequência de *element strings*, cada uma identificada por um
**AI** (Application Identifier). O código do produto está no **AI `01`** — o
GTIN, sempre com **14 posições**. Junto vêm lote (`10`), validade (`17`), série
(`21`) e o que mais o fabricante imprimir.

Sem extrair o GTIN, a leitura inteira (com lote e validade grudados) seria
procurada no cadastro e não acharia nada.

São reconhecidas as três formas que aparecem na prática:

| Forma | Exemplo |
|---|---|
| Element strings separadas por FNC1 (`0x1D`) | `0107891234567895␝10LOTE123` |
| Element strings concatenadas, AI 01 na frente | `010789123456789517260101` |
| GS1 Digital Link | `https://id.gs1.org/01/07891234567895/10/LOTE` |

Alguns leitores prefixam um **identificador de simbologia** (`]d2`, `]Q3`, `]e0`…)
quando configurados para "transmitir símbolo". Ele não faz parte do conteúdo e é
descartado antes de qualquer coisa.

### A regra que separa os dois casos

Um DUN-14 que por acaso comece com `01` tem 14 dígitos. Um AI `01` seguido de
GTIN precisa de 16 caracteres. **É o comprimento que distingue**, e é por isso
que a forma concatenada exige mais de 16 caracteres para ser tratada como GS1.

Sobra um caso genuinamente ambíguo: exatamente `01` + 14 dígitos e nada mais.
Pode ser um QR que carrega só o GTIN, ou um código linear de 16 dígitos. Como
não dá para saber, **as duas leituras viram candidatos** — a crua na frente,
porque é o que o cadastro pode ter literalmente.

### Zeros à esquerda

O cadastro guarda EAN-13 com 13 dígitos. No QR Code, o mesmo produto aparece
como esse EAN-13 precedido de zero, porque o AI `01` sempre tem 14 posições.

**São o mesmo número.** Por isso todo GTIN extraído gera dois candidatos: a
forma de 14 e a forma sem os zeros à esquerda. Recusar a leitura por causa de um
zero seria o cadastro certo com a bipagem quebrada.

Isso vale **só para GTIN extraído de payload GS1**. Tirar zero de um código
linear qualquer inventaria um número que ninguém cadastrou.

---

## Etapa 2 — Busca exata, em três origens

O produto tem três lugares onde um código de barras pode estar, e eles são
procurados **nesta ordem**:

| # | Origem | Onde mora | O que é |
|---|---|---|---|
| 1 | **Código de barras da nota** | `produtos.codigo_barra_notas` | O que vem do ERP (`fat_produtos.CODIGO_BARRA`) e sai impresso na nota fiscal. É um só, porque no ERP é um só. |
| 2 | **Códigos de logística** | `produto_codigo_barras` (N linhas) | Os códigos impressos nas caixas que chegam ao galpão — fabricante, distribuidor, reembalagem. Nascem e vivem só neste banco. |
| 3 | **DUN-14** | `produtos.dun_14` | O GTIN-14 da embalagem de despacho, a caixa fechada. |

**A ordem é fixa de propósito.** Um mesmo número achado em duas origens tem que
resolver sempre para o mesmo produto, independente da hora do dia — ordem
variável faria a bipagem responder coisas diferentes para a mesma leitura.

Dentro de cada origem, os candidatos da etapa 1 também são testados em ordem: o
GTIN literal ganha da forma sem zeros à esquerda.

**Nenhuma das três colunas é única.** Cadastro duplicado vindo de integração
pode repetir o mesmo número, e uma constraint única faria a importação quebrar
por causa de uma linha. Havendo mais de um cadastro com o mesmo número, **o
primeiro ativo resolve**.

Produto inativo ou apagado (`sync_deleted_at`) nunca casa, em nenhuma origem.

---

## Etapa 3 — Desempate pelo dígito verificador

Só roda **depois de as três origens falharem na busca exata**. Enquanto existir
um cadastro que bate exatamente, é ele que vale.

### O problema que isso resolve

Acontece de a embalagem trazer o EAN com o **dígito verificador errado** —
falha de impressão do fabricante — enquanto a nota fiscal traz o dígito certo.

Caso real que motivou a regra, **SONDA FOLEY 2 VIAS LÁTEX Nº 18 30ML**:

```
Nota fiscal:  693687731305 6
Embalagem:    693687731305 3
              └──────────┘ └┘
               12 dígitos   dígito
               idênticos    verificador
```

Não houve troca de titularidade nem mudança de fabricante. O prefixo `693`
indica origem chinesa, e como o prefixo da empresa e a numeração do item são
rigorosamente os mesmos, é o **mesmo fabricante e o mesmo produto**. Numa troca
de titularidade a raiz do código muda por completo.

O que diverge é só o 13º dígito, que não é escolhido por ninguém: ele é
calculado por uma fórmula de checagem ponderada sobre os 12 anteriores. Para a
base `693687731305` o resultado obrigatório é **6**. O código terminado em **3**
é matematicamente inválido segundo as regras da GS1.

### Por que a nota está certa e a caixa errada

A **SEFAZ valida a fórmula do dígito verificador** no campo `cEAN` na emissão da
NF-e. Se o emissor tentasse emitir com o final `3`, o documento seria rejeitado
com erro de dígito verificador inválido. O faturamento não tem escolha: emite
com o dígito correto. A embalagem física, que ninguém valida, continua com a
impressão falha.

Resultado no galpão: o operador bipa a caixa e o sistema não acha o produto,
mesmo com o cadastro correto.

### Como funciona

1. Do código lido, **descarta-se o último dígito** — sobra a *base*.
2. Procura-se essa base contra a base de todos os códigos cadastrados, **nas
   três origens ao mesmo tempo**.
3. Se **exatamente um produto** responde, é ele.
4. Se **mais de um** produto responde, a bipagem **recusa**.

Aqui não há ordem de preferência entre as origens: o desempate só vale se a
resposta for única, e "única" é sobre o **produto**, não sobre onde o código
estava. O mesmo produto achado pela nota e pela logística continua sendo um só.

### Por que exigir resposta única

Ignorar o DV é abrir mão de um dígito de conferência. Dois produtos diferentes
podem compartilhar a mesma base, e nesse caso a leitura é genuinamente ambígua.

**Errar o produto na conferência é pior que pedir para o operador conferir o
cadastro.** Por isso, ao contrário da busca exata, não existe "escolhe o
primeiro" nesta etapa — ambíguo é recusado.

### As travas

| Trava | Por quê |
|---|---|
| Mínimo de **8 dígitos** | Abaixo disso, "ignorar o último" deixa de ser tolerância e vira curinga: com 4 dígitos a base casaria com meio cadastro. |
| Só código **numérico** | Código interno alfanumérico não tem dígito verificador para estar errado. |
| Bases de **mesmo comprimento** | Comparar base com base já garante isso: a base de um EAN-13 tem 12 dígitos, a de um DUN-14 tem 13. Um nunca casa com o outro por acidente. |
| Só produto **ativo** | Cadastro inativo não é opção de bipagem, então também não pode tornar a leitura ambígua — senão desativar um produto quebraria a bipagem de outro. |

---

## Depois de achar o produto

Encontrar o cadastro é só metade. `expedicao_service.bipar` ainda aplica:

1. **É o produto deste item?** Se não, `422 "Este código de barras é de outro
   produto."` O desempate da etapa 3 não afrouxa isso — ele ajuda a *encontrar*
   o cadastro, não a aceitar qualquer coisa.
2. **Quanto vale esta leitura?** O pedido é sempre em unidade, mas há produto
   que só se vende em caixa fechada. Cada bipe vale
   `quantidade_multipla_venda`, multiplicado pelo multiplicador digitado no
   coletor (que conta caixas).
3. **Cabe no que foi pedido?** Passar da quantidade do item é recusado, com a
   explicação do múltiplo quando ele for maior que 1.

Não achou o produto em nenhuma das três etapas:
`422 "Código de barras não cadastrado em nenhum produto."`

A tela de bipagem, nesse caso, oferece o botão **Verificar ANVISA** (abaixo) e,
se ele não resolver, orienta a cadastrar o código em **Produtos → código de
barras logística**. Corrigir cadastro digitando um código à mão a partir do
coletor não existe: o produto passou a ter vários códigos e o ERP tem um só,
então o que a correção deveria fazer lá é uma decisão em aberto.

---

## Verificar ANVISA — quando nada foi encontrado

Botão que aparece **só** na mensagem de código não cadastrado. Existe porque o
caso mais comum de "não achei" em medicamento não é cadastro faltando: é o
produto circular com mais de um EAN, e o cadastro daqui conhecer só um deles.

### De onde vem a informação

Da tabela **CMED** (`cotacao_tabela_cmed`), a lista oficial de medicamentos com
preço regulado. Ela vive neste banco mas é de outro sistema — não tem model, não
está no metadata do Alembic, e toda conversa com ela mora em
`app/shared/tabela_cmed.py`.

A CMED publica até **três EANs por apresentação** (`ean_1`, `ean_2`, `ean_3`),
justamente porque o mesmo medicamento circula com mais de um código: troca de
embalagem, apresentação hospitalar e de farmácia, reimpressão do fabricante.

### O que o botão faz

1. **O produto tem `registro_anvisa` no cadastro?** Sem ele não há o que
   consultar. Não é erro — a maior parte do catálogo é correlato, não
   medicamento registrado.
2. **Esse registro existe na CMED?** A comparação é **dígito a dígito**: o
   registro é escrito de várias formas (`1.7056.0066.003-7`, `1705600660037`) e
   a CMED guarda só os dígitos.
3. **O código lido está entre os EANs daquele registro?** Esta é a trava
   principal. Sem ela a função viraria "importe os códigos da CMED para este
   produto" — que é outra coisa, e que aceitaria vincular um produto ao registro
   errado sem ninguém perceber. **O que autoriza a escrita é a caixa na mão do
   operador concordar com a fonte oficial.**
4. **Algum desses EANs já é de outro produto?** Se sim, **nada é gravado** — nem
   os que não conflitam. A tela mostra qual código pertence a qual produto.

Passando os quatro, os EANs entram como **códigos de logística** do produto, e a
leitura recusada é registrada na hora — o operador não precisa bipar de novo.

Nada é gravado em `codigo_barra_notas` (espelho do ERP, quem escreve lá é a
integração) nem em `dun_14` (a CMED publica EAN de apresentação, não DUN de
caixa de despacho).

### Por que tudo ou nada no conflito

Vincular só os códigos livres deixaria o cadastro num estado que ninguém pediu e
que é pior de desfazer do que de refazer. Duas apresentações compartilhando EAN
é sinal de cadastro errado em algum dos dois lados, e isso é decisão de gente —
não de rotina automática rodando no meio de uma conferência.

### Onde isso mora, e por quê

| Camada | Arquivo |
|---|---|
| SQL da CMED | `app/shared/tabela_cmed.py` |
| Regra e escrita | `produto_service.vincular_codigos_da_anvisa` |
| Endpoint | `POST /produtos/{id}/codigos-barras/anvisa` |

**O endpoint é do domínio de produtos, não da expedição**, mesmo sendo acionado
pela tela do coletor: quem grava em `produto_codigo_barras` é o dono da tabela.
A expedição não escreve no cadastro (ver `ARCHITECTURE.md` → "Regras de import
entre domínios"); a tela de bipagem só dispara e mostra o resultado.

A permissão é **`produtos.codigo_barras.vincular_anvisa`**, chave própria e não
`produtos.gravar.editar`: quem usa isto é o operador do coletor, que não tem
(nem deve ter) acesso de edição ao cadastro. A escrita que a chave libera é
estreita — só códigos publicados pela CMED para o registro do próprio produto, e
só quando o código lido confere.

**Lacuna conhecida:** a operação não grava linha de histórico. `historico.
empresa_id` é NOT NULL com FK e este endpoint é do domínio de produtos, onde não
existe uma empresa natural — ao contrário da expedição, que sempre fala de um
pedido. O rastro hoje é a própria linha em `produto_codigo_barras`, que carrega
`sync_created_at`.

---

## Onde estão os testes

| Arquivo | O que cobre |
|---|---|
| `tests/test_gs1.py` | Etapa 1 isolada — linear vs. GS1, prefixo de simbologia, Digital Link, zeros à esquerda |
| `tests/test_expedicao_e2e.py` | Etapas 2 e 3 pela API: código de logística, QR Code, e a classe `TestDesempatePeloDigitoVerificador` com o caso da sonda e todas as travas |
| `tests/test_produto_anvisa.py` | Verificar ANVISA: match, conflito nas três origens, cada recusa, formatos de registro e a permissão |

## Ao mexer nesta regra

- **A ordem das três origens é decisão de negócio**, tomada e reafirmada. Não
  reordene sem pedir.
- **O desempate é sempre o último passo.** Promovê-lo faria uma leitura com DV
  errado ganhar de um cadastro que bate exato.
- **Nunca troque a recusa por ambiguidade por "escolhe o primeiro".** É a única
  coisa que impede a etapa 3 de virar uma fonte silenciosa de produto trocado.
- **Verificar ANVISA não pode virar "importar da CMED".** Se a conferência do
  código lido (passo 3) sair, a operação passa a vincular códigos a um produto
  sem nenhuma evidência física de que é o produto certo.
