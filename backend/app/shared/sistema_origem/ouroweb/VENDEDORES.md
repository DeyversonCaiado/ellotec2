# Onde ficam os vendedores no OuroWeb

Levantamento feito em 2026-09-01 direto no banco (só leitura). Serve para
quando formos integrar cotações e precisarmos saber *de quem* é cada cotação.

## Resumo para quem vai integrar

Duas coisas, e o resto do documento é o detalhe delas:

1. **O vendedor é `Tab_Funcionários`** — não existe tabela de vendedor; é o
   cadastro de pessoas, e vendedor é quem tem `IdFunção = 25`.
2. **O cliente se liga ao vendedor por `Tab_Cadastro.IdFuncionário`**, que
   aponta para `Tab_Funcionários.IdFuncionário`. É um vendedor por cliente,
   sem tabela de carteira no meio. Preenchido em 100% dos 29.024 cadastros,
   sem nenhum órfão — **mas 94% apontam para o mesmo código (4), que é o
   default de quem cadastra, e não uma carteira de verdade.** Ler a seção
   "Carteira de clientes" antes de usar.
3. **O produto é `Tab_Estoque`**, e a chave é `IdItem` — o código do produto
   no GESTCOM. O de-para com o portal fica em
   `Tab_Cce<Portal>ProdutoVinculado`, por hospital e com vários equivalentes
   por item.

**Sentido da integração:** quem alimenta o OuroWeb é o **GESTCOM**. A ponte
futura é GESTCOM → OuroWeb; o ellotec2 apenas lê deste banco e nunca escreve.

## A tabela é `Tab_Funcionários`

Não existe tabela de vendedor no OuroWeb. Existe um cadastro único de pessoas —
`Tab_Funcionários` — e "vendedor" é um funcionário com uma determinada função.

Atenção ao nome: **é acentuado e precisa de colchetes** no SQL
(`[Tab_Funcionários]`). Boa parte do schema do OuroWeb é assim, inclusive
colunas (`[IdFuncionário]`, `[IdFunção]`).

Colunas que interessam:

| Coluna | Tipo | O que é |
| --- | --- | --- |
| `IdFuncionário` | nvarchar | Código do vendedor. É por ele que as outras tabelas apontam. |
| `pk_int_Funcionario` | int | Chave interna. É o que a tabela de BI guarda. |
| `NOME` | nvarchar | Nome do vendedor. |
| `IdFunção` | int | 25 = Vendedor, 10 = Vendedor externo, 14 = Representante. |
| `Ativo` | bit | Se está ativo. |
| `IdFuncIntegracao` | varchar | **Código do funcionário no ERP.** É a ponte entre os dois sistemas. |

Descrição das funções fica em `[Tab_Funcionários_Funções]`.

### Armadilhas já verificadas

- **`Tab_Vendedor` não serve.** Existe, mas tem 1 linha só ("JANE GRECCO"), com
  cara de teste esquecido. Não é o cadastro.
- **As flags `bit_Vendedor` e `bit_Representante` não são confiáveis.** De 198
  funcionários, apenas 2 têm `bit_Vendedor = 1` e 6 têm `bit_Representante = 1`,
  enquanto ~180 têm `IdFunção = 25`. Quem manda é a função, não a flag.
- **`Ativo = 1` não quer dizer pessoa de verdade.** Há registros como
  `RPA`, `GESTBI`, `MANAGER`, `VAZIO`, `DESATIVADO`, `CLIENTE POTENCIAL`,
  `TESTE` e `CONTRATO AHPACEG` com `IdFunção = 25`. Se a integração for listar
  vendedores para escolha humana, isso vai aparecer na tela.
- **`IdFuncionário` não é único de fato.** Existem nomes repetidos com códigos
  diferentes (`KAMILA SOARES LEITE` em 97 e 104; `THIAGO RODRIGUES` em 48 e 49,
  este último com o mesmo `IdFuncIntegracao` do outro). Não dá para casar por
  nome, e mesmo `IdFuncIntegracao` tem duplicata.
- **`IdFuncIntegracao` pode ser nulo** (ex.: `REGIANE FERRREIRA`, `THIAGO
  RODRIGUES` 48). Ou seja: nem todo vendedor do OuroWeb tem par no ERP.
- **`NOME` vem sujo**: espaço sobrando no fim e, em alguns casos, `\n` no meio
  (`DINAMARA LOPES\n`, `POLLYANNA BÁRBARA HENRIQUE \n`). Se for exibir ou casar,
  limpe antes.

## Como chegar no vendedor de uma cotação

O vendedor **não está** nas tabelas do portal (`Tab_CceBionexoPedido*`,
`Tab_CceApoioPedido*`). Ele vem do **cadastro do hospital**: a cotação aponta
para um cadastro, e o cadastro tem o funcionário responsável.

Isto não é dedução — é o que a procedure `sp_mng_GerarDadosGestaoPortalBionexo`
faz (existe uma equivalente para cada portal: Apoio, Síntese, Huma, GTPlan).

```sql
SELECT cab.int_IdPdc            AS cotacao,
       cab.str_NomeHospital     AS hospital,
       f.[IdFuncionário]        AS codigo_vendedor,
       f.NOME                   AS vendedor,
       f.IdFuncIntegracao       AS codigo_vendedor_erp
FROM Tab_CceBionexoPedidoCabecalho cab WITH (NOLOCK)
JOIN Tab_Cadastro cad WITH (NOLOCK)
  ON cad.pk_int_Cadastro = cab.fk_int_Cadastro
LEFT JOIN [Tab_Funcionários] f WITH (NOLOCK)
  ON f.[IdFuncionário] = cad.[IdFuncionário]
```

Duas coisas que custaram tempo e vale registrar:

- É `Tab_Cadastro.IdFuncionário`, **não** `Tab_Cadastro.Vendedor`. A coluna
  `Vendedor` existe e parece a certa, mas está nula na maioria dos hospitais —
  o primeiro teste voltou vendedor nulo em 15 de 15 cotações por causa disso.
- O join tem que ser `LEFT`. Hospital recém-chegado pelo portal pode não ter
  funcionário atribuído, e um `INNER` sumiria com a cotação inteira em silêncio.

Conferido com cotações dos últimos 3 dias: PDC 664589916 (Hospital Unimed
Recife) → `WILLIAM JEOVA DA SILVA PERILLO`, código 4, ERP 2.

## Atalho: `Tab_BI_CCe_GestaoPortal`

O OuroWeb já mantém uma tabela de BI consolidando **todos os portais**, uma
linha por item de cotação, e ela já traz o vendedor pronto:

- `int_Representante` = `Tab_Funcionários.pk_int_Funcionario` (confirmado:
  WILLIAM → pk 14; JULIA PEREIRA PRAGER → pk 67)
- `str_Representante` = o nome
- `int_portal`: 1 = Bionexo, 2 = Apoio, 3 = Síntese, 4 = Huma, 5 = GTPlan
- `int_IdUsuario` / `str_NomeUsuario` são **outra coisa**: quem respondeu a
  cotação no sistema, não o vendedor da conta. Não confundir.

Se a integração for analítica (cotações por vendedor, por portal), ler daqui é
mais simples do que refazer o join para cada portal. A view `vw_lst_bi_Cotacoes`
é essa tabela já formatada, com `Portal` e `Regiao` calculados.

**Cuidado com o tamanho.** Um `GROUP BY int_Representante` sem filtro estourou
o timeout de 60 segundos da conexão. Sempre filtre por `dte_DataVencimento`.

Contrapartida: é uma tabela **derivada**, populada pelas procedures
`sp_mng_GerarDadosGestaoPortal*`. Não sabemos com que frequência elas rodam. Se
a integração precisar de dado ao vivo, use as tabelas do portal + o join acima;
o BI serve para histórico e análise.

## Nota sobre o sentido da integração

Este banco é **somente leitura** para nós (ver `conexao.py` e o
`ARCHITECTURE.md`). Nada aqui é escrito pelo ellotec2.

Vale notar que o vínculo com o ERP mora em `IdFuncIntegracao` — ou seja, quando
formos casar um vendedor do OuroWeb com um funcionário nosso, a chave natural é
essa, não o nome nem o `IdFuncionário`. E, como já registrado acima, ela pode
vir nula ou repetida: a integração precisa decidir o que fazer nesses dois casos
antes de existir, não depois.

---

# Carteira de clientes: como o cliente se liga ao vendedor

Levantamento de 2026-09-01, mesma sessão (só leitura).

## A ligação é uma coluna só: `Tab_Cadastro.IdFuncionário`

Não existe tabela de carteira. O vínculo mora no próprio cadastro do cliente,
e é **um vendedor por cliente**:

```sql
SELECT c.Codinome        AS codigo_cliente,
       c.NomeFantasia    AS cliente,
       c.CGC             AS cnpj,
       f.[IdFuncionário] AS codigo_vendedor,
       f.NOME            AS vendedor
FROM Tab_Cadastro c WITH (NOLOCK)
JOIN [Tab_Funcionários] f WITH (NOLOCK)
  ON f.[IdFuncionário] = c.[IdFuncionário]
WHERE c.ClienteFornecedor = '1'
```

A integridade é boa: 29.024 cadastros, **todos** com `IdFuncionário`
preenchido, e **zero** apontando para funcionário inexistente. Aqui o `JOIN`
pode ser `INNER` sem perder linha — ao contrário do join da cotação, que
precisa de `LEFT`.

### Candidatos descartados, todos vazios

Vale registrar para ninguém refazer a busca:

- `Tab_Cadastro.Vendedor` — 0 de 29.024 preenchidos. O nome engana.
- `Tab_Cadastro_Outros_Representantes` — 1 linha, inativa. Seria o caminho para
  carteira compartilhada por grupo de produto ou marca, mas não é usada.
- `Tab_Cadastro.int_IdUsuarioTMK` — 0 preenchidos.
- `Tab_FuncionarioGrupoProduto`, `Marcas_Representante`, `Usuarios_Marcas`,
  `MapaVendasExcecaoVendasUsuario` — 0 linhas cada.

Ou seja: **não há carteira por marca, por grupo de produto ou por região neste
banco.** É a coluna única, e nada mais.

## O problema que a integração vai encontrar

A carteira está concentrada num código só:

| Código | Vendedor | Cadastros | Só clientes (`cf='1'`) |
| --- | --- | --- | --- |
| 4 | WILLIAM JEOVA DA SILVA PERILO | 27.418 | 5.477 |
| 51 | CLIENTE POTENCIAL | 497 | 490 |
| 26 | PATRICIO DE OLIVEIRA SANTOS | 200 | 199 |
| 122 | ABEL JOSE ROCHA | 112 | 112 |
| 56 | JULIA PEREIRA PRAGER | 71 | 71 |

**94% dos cadastros apontam para o código 4.** Pelo padrão (e por 51 ser
literalmente "CLIENTE POTENCIAL"), isso é o *default de quem cadastrou*, não
uma carteira de verdade. Bate com o passo 1: as cotações do Bionexo caem
majoritariamente no mesmo código 4.

Consequência prática: **atribuir cotação a vendedor por esta coluna vai jogar a
maioria no William.** Antes de construir em cima disso, confirmar com o
comercial se o dono real da carteira está no ERP e o OuroWeb só recebe o
default. Se for esse o caso, a carteira tem que vir do ERP, e esta coluna serve
no máximo como fallback.

## Filtrar cliente de verdade

`ClienteFornecedor` (nvarchar) classifica o cadastro:

| Valor | Qtd | O que é |
| --- | --- | --- |
| `'2'` | 20.429 | fornecedor / outros — inclui borracharia, cartório, transportadora |
| `'1'` | 7.051 | cliente |
| `NULL` | 1.540 | sem classificação |
| `'3'` | 4 | resíduo |

Sem `WHERE ClienteFornecedor = '1'` a contagem de "clientes" fica quase 4x
maior e sem sentido.

`Status` **não serve** para separar ativo de inativo: 28.894 dos 29.024 estão em
`0`, 129 em `NULL` e 1 em `1`.

## Ponte com o ERP: só o CNPJ

Diferente do vendedor (que tem `IdFuncIntegracao`), o cliente **não tem código
do ERP** neste banco:

- `str_CodigoIntegracao` — 0 de 29.024 preenchidos.
- `bit_ClienteIntegracao` — 0 marcados.

O único identificador comum é o **CNPJ/CPF em `CGC`**, preenchido em 29.020 dos
29.024. `Codinome` é o código do cliente **dentro do OuroWeb** (29.024 valores
distintos, portanto único), e `pk_int_Cadastro` é a chave interna — nenhum dos
dois vale fora daqui.

Então, ao casar cliente do OuroWeb com cliente do ellotec2/ERP, a chave é o
CNPJ, com todo o cuidado que isso pede: normalizar (só dígitos) antes de
comparar, e decidir o que fazer quando o mesmo CNPJ aparecer mais de uma vez.

## `Mov_Estoque` está vazia

Vale saber: a tabela de movimento de estoque tem **0 linhas**. O OuroWeb guarda
cadastro e cotação de portal, não venda. Não dá para inferir a carteira "de
fato" (quem realmente fatura para quem) por aqui — esse dado está no ERP.

## Cuidado: os nomes na BI são um retrato congelado

Achado por acaso, mas importa. Em `Tab_Funcionários`, o funcionário 4 se chama
`WILLIAM JEOVA DA SILVA PERILO` (um L). Em `Tab_BI_CCe_GestaoPortal`, as
linhas recentes do mesmo `int_Representante = 14` trazem
`WILLIAM JEOVA DA SILVA PERILLO` (dois L).

A tabela de BI **copia o nome no momento em que a procedure roda** e não
atualiza depois. Portanto:

- Nunca case registros por `str_Representante`. Use `int_Representante`
  (= `pk_int_Funcionario`).
- Se for exibir o nome do vendedor, leia de `Tab_Funcionários`, não do BI —
  senão a tela mostra o nome antigo.

---

# Produtos: o nosso catálogo e o de-para do portal

Levantamento de 2026-09-01, mesma sessão (só leitura).

## A tabela é `Tab_Estoque`

22.983 produtos. Chave `pk_int_Estoque` (int). O item da cotação aponta direto
para ela:

```
Tab_CceBionexoPedidoItens.fk_int_Estoque  →  Tab_Estoque.pk_int_Estoque
```

(Confirmado na procedure `sp_mng_GerarDadosGestaoPortalBionexo`, que faz esse
mesmo join. Vale para os outros portais, trocando o prefixo `Bionexo`.)

Colunas que interessam:

| Coluna | O que é |
| --- | --- |
| `pk_int_Estoque` | chave interna; é para onde tudo aponta |
| `IdItem` | **código do produto no ERP — é a PK da tabela** |
| `Descrição` | descrição |
| `CódigoFábrica` | igual a `IdItem` em 22.982 dos 22.983; não é dado novo |
| `códigobarra` | EAN, preenchido em 19.412 |
| `ClassificaçãoFiscal` | NCM |
| `str_UnidadeVenda` | unidade (`CX`, `FR`, `PT`, `UN`…) |
| `IdMarca` | marca |
| `int_StatusCadastro` | 1 = ativo, 2 = morto (ver abaixo) |

## O código do produto é `IdItem`, e ele é o do ERP

`Tab_Estoque.IdItem` carrega o código do produto no GESTCOM. Quem alimenta
este banco é o **ERP**, não o ellotec2 — a integração futura é GESTCOM →
OuroWeb, e o ellotec2 só lê daqui.

Dá para conferir isso contra o ellotec2, que espelha o mesmo código do ERP em
`produtos.sistema_origem_id`. Medido no conjunto inteiro, não por amostra:

| | Qtd |
| --- | --- |
| `Tab_Estoque` (OuroWeb) | 22.983 |
| `produtos` com `sistema_origem_id` (ellotec2) | 23.007 |
| **presentes nos dois** | **22.980** |
| só no OuroWeb | 3 |
| só no ellotec2 | 27 |

Numa amostra de 200 códigos, a descrição bateu **200/200, idêntica**
(ex.: `0022970` = `BUSSULFANO 60MG/10ML` nos dois).

Ou seja: os dois sistemas coincidem porque ambos carregam o código do GESTCOM.
Isso confirma que `IdItem` é o código do ERP — e é bem melhor do que o caso do
cliente, que não tem código de integração nenhum e só pode ser casado por CNPJ.

## O de-para do produto equivalente

É uma tabela por portal:

| Tabela | Linhas |
| --- | --- |
| `Tab_CceBionexoProdutoVinculado` | 127.993 |
| `Tab_CceApoioProdutoVinculado` | 61.195 |
| `Tab_CceSinteseProdutoVinculado` | 15.923 |
| `Tab_CceHumaProdutoVinculado` | 0 |
| `Tab_CceGTplanProdutoVinculado` | 0 |

Estrutura (a do Bionexo; as outras são iguais trocando o prefixo):

```sql
SELECT v.str_CodigoProdutoBionexo AS codigo_no_portal,
       v.fk_int_IdCadastro        AS hospital,
       e.IdItem                   AS nosso_codigo,
       e.[Descrição]              AS nosso_produto
FROM Tab_CceBionexoProdutoVinculado v WITH (NOLOCK)
JOIN Tab_Estoque e WITH (NOLOCK)
  ON e.pk_int_Estoque = v.fk_int_IdProduto
```

Zero órfãos nas 127.993 linhas — `fk_int_IdProduto` sempre existe em
`Tab_Estoque`.

### Três características que mudam o desenho da integração

**1. O vínculo é por hospital, não global.** A chave é o par
(`str_CodigoProdutoBionexo`, `fk_int_IdCadastro`). 13.814 códigos aparecem em
mais de um cadastro. O mesmo código pode significar produtos diferentes em
hospitais diferentes — não dá para tratar como catálogo único do portal.

**2. Não é 1:1, é uma lista de candidatos.** 25.833 pares (código + hospital)
apontam para **mais de um** produto nosso. Exemplo real — código `94945`,
cadastro 25460, quatro equivalentes, todos ativos:

- `0019026` MASCARA DE PROTECAO PFF2 N95
- `0021393` SAFETY MASCARA PFF2 KN95
- `0019291` MASCARA DE PROTECAO PFF2 N95 CX/25
- `0022943` MASCARA PROTECAO BRANCA PFF2 N95 CX/20

Faz sentido para o negócio (são equivalentes de verdade), mas a integração
precisa **escolher** um, não apenas resolver o de-para. Quem escolhe, e com que
critério, é decisão de negócio — não existe coluna de preferência na tabela.

**3. A origem do vínculo está em `bit_ApiDepara`:** 9.486 vieram por API,
118.507 são manuais. `dte_DataHoraVinculo` só está preenchida em 812 linhas, e
`int_IdUsuario` quase sempre nulo — ou seja, **não há histórico de quem vinculou
o quê e quando** para a maioria.

## `int_StatusCadastro` separa produto vivo de morto

| Status | Qtd | Cadastro mais recente |
| --- | --- | --- |
| 1 | 5.281 | 2026-08-31 |
| 2 | 17.702 | 2024-02-29 |

O `2` é produto morto: não entra nada novo nele desde fevereiro de 2024.
Confirmado pelo uso real — nos itens de cotação Bionexo dos últimos 3 dias,
**1.770 apontam para produto de status 1 e apenas 2 para status 2**.

Não use `bit_ProdutoObsoleto` para isso: está `0` nos 22.983.

## O número que precisa estar claro desde o começo

Nos últimos 3 dias, de **222.447 itens** de cotação do Bionexo, **220.675
(99,2%) não têm `fk_int_Estoque` preenchido** — nenhum produto nosso vinculado.

Isso é normal e não é defeito: a cotação traz o catálogo inteiro do hospital, e
nós respondemos só a fatia que vendemos. Mas qualquer tela, contagem ou
relatório precisa nascer sabendo disso, senão vai parecer que a integração está
quebrada.

## Uma tabela que pode interessar depois

`Tab_EstoqueRespostaAutomaticaCce` (14.871 linhas) liga produto a empresa
(`fk_int_Estoque`, `fk_int_IdEmpresa`) e é o que governa a resposta automática
de cotação. Não foi explorada a fundo; fica o registro de que existe.

---

# Enviar produto do GESTCOM para o OuroWeb: o que mais precisa ir junto

Levantamento de 2026-09-01. **Ainda é estudo** — nada foi escrito no SQL Server.
A pergunta respondida aqui é: para inserir um produto em `Tab_Estoque`, que
outros cadastros precisam existir antes, e que linhas filhas precisam vir
depois.

## As dependências de `Tab_Estoque`

A tabela tem **14 chaves estrangeiras declaradas, todas habilitadas** — o banco
vai recusar o insert se o pai não existir. Mas só 5 são usadas de fato; as
outras estão nulas nos 22.983 produtos:

| Precisa? | Coluna | Tabela pai | Linhas hoje |
| --- | --- | --- | --- |
| sim | `Grupo` | `Tab_EstoqueGrupo` | 8 |
| sim | `Grupo` + `Referência` (composta) | `Tab_EstoqueReferência` | 133 |
| sim | `UnidadeCompra` | `Tab_EstoqueUnidade` | 185 |
| sim | `IdMarca` | `Tab_Estoque_Marcas` | 988 |
| sim | `ClassificaçãoFiscal` | `Tab_ClassificaçãoFiscal` | 665 |
| não | `Categoria` | `Tab_EstoqueCategoria` | nula em 100% |
| não | `Fornecedor` | `Tab_Cadastro` | nula em 100% |
| não | `IdGarantia` | `Tab_Garantia` | nula em 100% |
| não | `fk_int_apresentacao` | `Tab_Estoque_Apresentacao` | nula em 100% |
| não | `fk_int_ClassificacaoDesconto` | `Tab_Estoque_ClassificacaoDesconto` | nula em 100% |
| não | `fk_int_AmparoLegalPISCOFINS` | `AmparoLegalPISCOFINS` | nula em 100% |
| não | `fk_int_IdUnItemCompra` / `Venda` | `Tab_Estoque_Unidades_Itens` | 5.265 de 22.983 |

### Na prática, só a marca dá trabalho

Grupo, referência e NCM **não têm taxonomia real para replicar**. 22.982 dos
22.983 produtos usam a mesma combinação placeholder:

- `Grupo = '601'` (a descrição no `Tab_EstoqueGrupo` é literalmente `PADRAO`)
- `Referência = '001'`
- `ClassificaçãoFiscal = '001'`

Os três valores já existem nas tabelas pai. Ou seja: a integração fixa esses
valores e não precisa enviar nada.

O único cadastro que pode faltar é a **marca**. Produto com marca nova exige
inserir antes em `Tab_Estoque_Marcas`. E essa tabela já tem a ponte com o ERP
pronta: `IdMarca` é a chave interna, e `IdIntegracao` guarda o código da marca
no GESTCOM (preenchido em 919 das 988). Só `IdMarca` é obrigatório na tabela.

## Duas tabelas filhas que na prática são obrigatórias

Não são FK saindo de `Tab_Estoque`, mas **nenhum produto existe sem elas**:

**`Tab_EstoqueEmpresa`** — 68.943 linhas, que é exatamente 22.983 × 3, e **zero
produtos sem linha**. Uma por empresa. As três empresas são:

| IdEmpresa | Empresa |
| --- | --- |
| 1 | ELLO DISTRIBUIÇÃO LTDA - EPP |
| 3 | ELLO DISTRIBUIÇÃO LTDA - BSB |
| 4 | ELLO DISTRIBUICAO LTDA - SP |

(Note que não existe empresa 2.) É aqui que moram preço, custo e o `Ativo` por
empresa. Só `IdEmpresa` e `IdItem` são obrigatórios — todo o resto tem default,
inclusive as ~120 colunas de preço.

**`Tab_Estoque_Unidades_Itens`** — 28.857 linhas, também **zero produtos sem**.
Unidades e fatores de conversão. Tem `int_IdUnidadeBionexo`, que é o casamento
da unidade com o portal — provavelmente vai importar quando a integração for
responder cotação.

## Quatro armadilhas do insert

**1. A PK é `IdItem`, não `pk_int_Estoque`.** O `PK_Tab_Estoque` é sobre
`IdItem` (nvarchar), e `pk_int_Estoque` é **IDENTITY** — quem gera é o OuroWeb.
O GESTCOM manda `IdItem` e não pode mandar `pk_int_Estoque`. Isso não atrapalha
as filhas, porque todas se ligam por `IdItem`; só as tabelas do portal
(`fk_int_Estoque`) usam o inteiro, e essas são preenchidas pelo próprio OuroWeb.

**2. Os 108 NOT NULL não assustam.** São quase todos campos fiscais (`bit_*`,
`Perc*`, `Reducao*`), e **todos têm default**. A única coluna NOT NULL sem
default é `IdItem`. Um insert enxuto é viável.

**3. O trigger `CodigoBarra_InsertUpdate` é frágil.** Ele rejeita EAN duplicado
com `RAISERROR` + `Rollback Tran`. Dois problemas:

- Está escrito para uma linha só (`SELECT @CodigoBarra = Inserted.CódigoBarra
  FROM Inserted`). Num INSERT de várias linhas ele **checa apenas uma** — o
  resto passa sem validação.
- O `Rollback Tran` derruba a **transação inteira**, não só a linha ofensora.

Conclusão prática: inserir **linha a linha**, e tratar o erro de EAN duplicado
explicitamente.

**4. Cinco FKs estão `is_not_trusted`** (`Tab_Cadastro`, `Categoria`,
`Referência`, `Unidade`, `Garantia`): já existe dado violando alguma delas. Elas
continuam sendo validadas em insert novo — então não muda o que precisa ser
enviado —, mas **não sirva-se delas para concluir que os dados atuais estão
íntegros**.

## Ordem de envio

```
1. Tab_Estoque_Marcas          -- só se a marca ainda não existir
2. Tab_Estoque                 -- o produto; chave = IdItem
3. Tab_EstoqueEmpresa          -- uma linha por empresa (1, 3 e 4)
4. Tab_Estoque_Unidades_Itens  -- unidade e conversão
```

Grupo, referência, unidade e classificação fiscal **não precisam ser enviados**:
use os valores placeholder que já existem.

Ainda em aberto, para quando sair do levantamento: quem preenche preço e custo
em `Tab_EstoqueEmpresa` (o GESTCOM manda, ou o comercial mexe no OuroWeb?), e o
que decide o `int_StatusCadastro` (1 ou 2) de um produto novo.

---

# Tabela de preço: onde mora o preço que vai para o portal

Levantamento de 2026-09-01. Ainda é estudo — nada foi escrito no SQL Server.

## `Tab_ListaPreco` + `Tab_ListaPreco_Itens`

A tabela de preço existe e **é por estado e por empresa**, como se esperava.

`Tab_ListaPreco` (168 linhas):

| Coluna | O que é |
| --- | --- |
| `pk_int_ListaPreco` | chave |
| `str_Descricao` | nome, no padrão `Tabela_<UF>[_Auto]_<empresa>` |
| `fk_int_IdEmpresa` | empresa (1, 3 ou 4) |
| `str_UF` | UF da lista — **nula em todas as 168, ver abaixo** |
| `int_RespostaAutomatica` | 2 = resposta manual, 3 = resposta automática |
| `bit_Ativo` / `bit_Bloqueio` | situação |

As 168 saem de 3 empresas × 28 UFs × 2 tipos. As 28 "UFs" são os 26 estados,
o DF e `EX` (exterior). Exemplos da empresa 1: `Tabela_GO_1`
(`int_RespostaAutomatica = 2`) e `Tabela_GO_Auto_1` (`= 3`).

`Tab_ListaPreco_Itens` (803.700 linhas, ~4.790 por lista) é o preço em si:

| Coluna | O que é |
| --- | --- |
| `fk_int_ListaPreco` | a lista |
| `fk_int_Estoque` | o produto (→ `Tab_Estoque.pk_int_Estoque`) |
| `dbl_ValorPraticado` | preço de venda |
| `dbl_ValorCusto` | custo |

## Como o portal resolve o preço de um item

A procedure é **`usp_lst_CceListaPrecoValorVendaItem`** (há a irmã
`usp_lst_CceListaPrecoValorCustoItem` para o custo). Ela recebe empresa,
cadastro (hospital), `IdItem` e um flag de resposta automática, e devolve o
valor. A ordem:

1. Lê a config `bln_HabilitarListadePreco` da empresa em
   `tab_ConfigCampo` / `tab_ConfigCampoAtributo`. Se for 0, devolve 0 e acabou.
   **Hoje está `1` nas três empresas.**
2. Define o tipo de lista: `2` se resposta manual, `3` se automática.
3. **Tenta pela UF:** pega `Tab_Cadastro.Estado` do hospital e procura em
   `Tab_ListaPreco` a lista com `str_UF` igual, mesma empresa, `bit_Ativo = 1`
   e `int_RespostaAutomatica IN (1, <tipo>)`.
4. **Se não achou, cai na lista do cliente:** `Tab_ListaPreco_Cliente` +
   `Tab_ListaPreco_Cliente_Itens`, para aquele `fk_int_Cadastro`.

Note que o valor `1` em `int_RespostaAutomatica` significaria "serve para os
dois casos" — mas nenhuma lista usa `1` hoje (só 2 e 3, 84 de cada).

## O caminho por UF está morto hoje

A procedure compara `a.str_UF = @str_UF`, mas **`str_UF` é nula nas 168
listas**. A UF só existe dentro do texto de `str_Descricao` (`Tabela_GO_1`),
que a procedure não lê.

Consequência: o passo 3 nunca casa, e **todo preço do portal é resolvido pelo
passo 4**, a lista por cliente. É o que explica o tamanho das duas tabelas:

| Tabela | Linhas | Disco |
| --- | --- | --- |
| `Tab_ListaPreco_Itens` (por UF) | 803.700 | 102 MB |
| `Tab_ListaPreco_Cliente` | 180.871 | — |
| **`Tab_ListaPreco_Cliente_Itens`** (por cliente) | **822.364.788** | **66 GB** |

### De onde saem os 822 milhões de linhas

A conta fecha exatamente, e cada fator foi conferido:

```
 29.024 clientes
   ×  6 listas cada     (3 empresas × 2 tipos: manual e automática)
   =  180.871 vínculos cliente↔lista   (Tab_ListaPreco_Cliente)
   ×  ~4.548 produtos por vínculo
   =  822.364.788 linhas               (Tab_ListaPreco_Cliente_Itens)
```

Um cliente de Goiás está ligado a exatamente 6 listas — `Tabela_GO_1`, `GO_3`,
`GO_4`, `GO_Auto_1`, `GO_Auto_3`, `GO_Auto_4` — e, para cada uma, o catálogo
inteiro é gravado de novo com preço, só para ele. (21.571 clientes têm 6 listas;
7.237 têm 7; um punhado tem mais, provavelmente por atuarem em mais de um
estado.)

### Não é duplicação pura: existe exceção por cliente

Vale saber antes de propor qualquer simplificação. Medido no produto
`0020755` (APTAMIL SOJA 1 400G) na `Tabela_GO_1`, olhando todos os clientes:

| Preço | Clientes |
| --- | --- |
| R$ 3,1658 — igual ao da lista do estado | 5.301 |
| R$ 42,91 | 1 |

Ou seja: a tabela por cliente existe para permitir **preço negociado
individualmente**. É funcionalidade real.

O que é desproporcional é o custo: para guardar **uma** exceção, o sistema grava
**5.302** linhas. Ele materializa a lista inteira para todo mundo, em vez de
guardar apenas quem foge da regra do estado.

**Consequência para a integração:** a tabela por cliente não pode ser ignorada,
porque é onde vivem as exceções negociadas. Se um dia `str_UF` for preenchida, o
caminho por estado passa a atender o caso normal e o caminho por cliente vira o
que ele deveria ser — a exceção — mas continua sendo necessário consultar os
dois.

`Tab_ListaPreco_Cliente_Itens` tem as mesmas colunas da versão por UF
(`fk_int_ListaPreco_Cliente`, `fk_int_Estoque`, `dbl_ValorPraticado`,
`dbl_ValorCusto`).

Duas leituras possíveis — vale confirmar com quem cuida do OuroWeb qual é:
preencher `str_UF` foi esquecido, ou alguma rotina popula a lista-por-cliente
de propósito. O efeito prático é o mesmo: **hoje o preço não é resolvido por
estado**, apesar de as listas por estado existirem e estarem preenchidas.

Para quando formos decidir qual preço vai ao portal, isso é uma boa notícia:
**preencher `Tab_ListaPreco.str_UF` liga o caminho por estado**, que já está
implementado na procedure, e tira o preço da dependência da tabela de 66 GB.
Mas é mudança no sistema de outro fornecedor — não é decisão nossa sozinha.

## Cuidados ao consultar

- **`Tab_ListaPreco_Cliente_Itens` não pode ser varrida.** Um
  `SELECT COUNT(*)` nela estoura o timeout de 60s. Para contar linhas sem
  varrer, use `sys.partitions`:
  ```sql
  SELECT t.name, SUM(p.rows) FROM sys.tables t
  JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0,1)
  WHERE t.name = 'Tab_ListaPreco_Cliente_Itens' GROUP BY t.name
  ```
- `pk_int_ListaPreco_Cliente_Itens` é `int`, e 822 milhões já é **38% do teto
  de 2,1 bilhões**. Não é problema nosso, mas é bom saber que existe.
- `Tab_EstoqueP2UF` tem cara de ser preço por UF (`str_Estado`, `cur_Valor`),
  mas está **vazia**. Não é por ali.

## Onde ficam preço e custo fora da lista

Lembrando o que já está na seção de produto: `Tab_EstoqueEmpresa` tem ~120
colunas de preço e custo por empresa (`PreçoVendaA/B/C`, `CustoMédio`,
`PreçoFábrica`, os `cur_PrecoPmcCmed_*` da CMED etc.). É o cadastro base de
preço do produto; a lista de preço é a camada que o portal consulta.

## Do lado do GESTCOM, a tabela de preço também é por estado

Informação de Deyverson: **a nossa tabela de preço, no GESTCOM, é por estado.**

Isso resolve boa parte da dúvida de desenho:

- O mapeamento é direto — uma linha da tabela por estado do GESTCOM vira uma
  linha em `Tab_ListaPreco_Itens` da lista daquele estado, sem transformação.
- Não teríamos como alimentar `Tab_ListaPreco_Cliente_Itens` de qualquer forma:
  preço por cliente **não existe no GESTCOM**. Só existe por estado.
- Portanto o caminho por UF da procedure não é só o mais barato: é o único que
  o nosso dado permite alimentar.

Fica como pendência do lado do OuroWeb preencher `Tab_ListaPreco.str_UF`, sem o
que a procedure ignora as listas por estado (ver acima). As exceções negociadas
por cliente continuam vivendo na tabela por cliente, mantidas por lá — não é
dado que nós enviamos.
