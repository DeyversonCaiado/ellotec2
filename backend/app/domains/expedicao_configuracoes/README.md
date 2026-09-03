# Configurações da expedição

Os parâmetros do processo de separação e conferência. Uma linha na tabela
`expedicao_configuracoes`, para o galpão inteiro, e uma tela que é um painel de
marcar/desmarcar — sem listagem, sem "novo", sem "apagar".

## Por que é um domínio, e não uma tela dentro de `expedicao`

Porque o dono é outro. Quem separa e confere executa a regra; quem liga e
desliga a regra responde pelo processo. Misturar os dois numa tela só significa
que o operador do coletor enxerga (e um dia clica) o botão que muda o
comportamento da fila inteira.

A separação aparece nas chaves de permissão: `expedicao_configuracoes.acessar` e
`expedicao_configuracoes.gravar.editar` são independentes de
`expedicao.separacao.executar` e `expedicao.conferencia.executar`.

## Os parâmetros

Os dois primeiros parâmetros desligam a trava de endereçamento de
`expedicao_service._bloqueio_do_item`. Antes de deixar um pedido entrar na
separação ou na conferência, a expedição compara, item por item, o que o pedido
pede com o que está endereçado no par (produto, lote) da linha. Duas coisas
reprovam, e **cada uma tem o seu parâmetro**.

Basta um item reprovado para barrar o **pedido inteiro**, com 409.

### `permite_conferir_com_divergencia`

**"Permite conferir pedido com divergência de estoque e lote"** — padrão
`False`.

Desliga a regra do **saldo endereçado**: a soma dos endereços em que aquele lote
está é menor que a quantidade vendida. É `>=`, não `==` — o endereço guarda o
estoque inteiro do lote, não uma reserva do pedido.

### `permite_conferir_fora_do_multiplo_de_venda`

**"Permite conferir pedido com endereço fora do múltiplo de venda"** — padrão
`False`.

Desliga a regra da **embalagem de venda**: o saldo de um endereço não fecha em
múltiplo da caixa em que o produto é vendido (7 unidades soltas num produto de
caixa de 12). Na bipagem cada leitura da caixa vale a caixa inteira, então o
operador nunca zera um endereço assim.

### Por que são dois parâmetros

Porque são problemas diferentes do galpão: falta de mercadoria endereçada versus
saldo quebrado numa prateleira. Um galpão pode conviver com um e não com o
outro, e um interruptor só obrigaria a desligar as duas checagens para resolver
metade do problema.

### Onde a configuração é aplicada

Em `_bloqueio_do_item`, antes de a frase de bloqueio existir — **não** em
`_bloqueio_do_pedido`, depois. Regra desligada é regra não calculada, não um
bloqueio calculado que alguém ignora adiante: no contrato com o front,
`bloqueio_enderecamento` preenchido significa "este pedido não pode ser
iniciado", e é assim que a listagem pinta a linha de vermelho e que o detalhe
esconde o botão. Preencher sem barrar quebraria essa leitura em todas as telas
de uma vez.

**Não confundir com `expedicao.enderecamento.liberar`.** Aquela permissão
destrava UM pedido, numa execução delegada, com o aval de quem responde pelo
galpão, e fica registrada naquele pedido. Estes parâmetros são decisão de
configuração: valem para a fila inteira até alguém desmarcar.

## Como ler o parâmetro de outro domínio

Por `expedicao_configuracao_publico.obter_parametros(sessao_db)`, que devolve
todos os parâmetros de uma vez — nunca importando o model ou o service (ver
`backend/ARCHITECTURE.md` → "Regras de import entre domínios"). São todos juntos
porque quem os consome precisa deles na mesma decisão, e uma função por
parâmetro daria N consultas para ler uma linha só.

A borda **não cria a linha**: ler parâmetro é leitura, e um `_publico.py` não dá
`commit()`. Banco sem a linha responde `PADRAO` — as duas travas ligadas. Quem
materializa a linha é `expedicao_configuracao_service.obter`, no GET do painel.

Numa listagem, leia uma vez para a página inteira: os parâmetros são do galpão,
não do pedido, e consultá-los por linha daria N consultas iguais. É o que
`expedicao_service.listar_pedidos` faz.

## Ao adicionar um parâmetro novo

1. Coluna no model, com o `default` que reproduz o comportamento de hoje —
   parâmetro novo nunca muda o que já estava valendo.
2. Campo nos dois schemas de `expedicao_configuracao_contrato.py`.
3. Migração Alembic com a coluna `NOT NULL` e o mesmo default.
4. Campo em `ParametrosExpedicao` e em `PADRAO`, no
   `expedicao_configuracao_publico.py`, se outro domínio for consumir.
5. No front: campo no model, controle no `FormGroup`, linha no painel — **com o
   "?" e o popover explicando com exemplo**. O efeito de um parâmetro destes
   aparece longe daqui, na mão do operador, dias depois; um rótulo de uma linha
   não dá conta.
6. Teste em `tests/test_expedicao_configuracoes.py` cobrindo o padrão de fábrica
   e o efeito na regra que ele governa.
