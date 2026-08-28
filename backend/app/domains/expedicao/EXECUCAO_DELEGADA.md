# Execução delegada: o gerente executa a etapa no nome do operador

## O problema real

O galpão não tem coletor para todo mundo. O gerente designa alguém para separar
um pedido; essa pessoa trabalha com a lista impressa e avisa quando termina. O
gerente é quem registra no sistema que a separação começou e que ela acabou.

Antes disso existir, as duas saídas possíveis eram ambas falsas:

- o gerente abria a etapa com o próprio usuário → o sistema dizia que **ele**
  separou o pedido;
- ninguém registrava nada → o pedido ficava sem passagem pelo galpão, e o
  status nunca avançava.

Um relatório de produtividade construído sobre qualquer uma das duas mede a
pessoa errada.

## O desenho: ator e sujeito

É a mesma separação que qualquer sistema usa para "agir em nome de". A coluna
que já existia continua sendo o **sujeito**, e entra uma coluna nova para o
**ator**:

| Coluna | Quem é |
|---|---|
| `usuario_inicio_id` / `usuario_fim_id` | **de quem é o trabalho** — o operador atribuído |
| `usuario_gestor_inicio_id` / `usuario_gestor_fim_id` | **quem clicou**, quando não foi o operador |

`NULL` nas colunas de gestor significa que ator e sujeito são a mesma pessoa —
o caso normal, em que o operador abre e fecha a etapa sozinho.

A consequência prática de manter `usuario_inicio_id` apontando para o operador é
que **nada mais precisou mudar**: `_exigir_mesmo_usuario` continua valendo, e se
um coletor se liberar no meio do caminho o operador atribuído entra e biparia
normalmente a etapa que o gerente abriu para ele. O gerente, esse não bipa — ele
não é quem começou.

Não há coluna equivalente nos itens. A ação em lote é sempre um gerente só, no
mesmo instante; o par na capa já responde a pergunta, e coluna por item seria
abstração por antecipação.

## De quem é o trabalho: a atribuição, ou quem clicou

`_operador_da_etapa` responde isso em uma linha: **com** atribuição viva, o
trabalho é do responsável designado; **sem** atribuição, é de quem clicou.

O operador não vai no corpo da requisição em nenhum dos dois casos — ele sai da
atribuição ou da sessão, sempre no backend. Deixar a tela escolher o nome criaria
um segundo jeito de atribuir, paralelo à tabela que já é a fonte da verdade de
quem responde por cada etapa.

Quando ator e sujeito são a mesma pessoa, `_gestor_ou_nulo` deixa as colunas de
gestor em `NULL`. Isso é o que mantém a coluna significando exatamente o que ela
promete — "quem clicou, quando não foi o operador". Gravar o gerente ali quando
ele é o próprio operador diria que ele executou em nome de si mesmo, e o
relatório de produtividade contaria a mesma pessoa duas vezes.

### Isto já foi um 409, e por que deixou de ser

Até agosto de 2026 as duas ações recusavam com **409** quando não havia
atribuição, com a justificativa de que "sem ela o gerente estaria creditando a
etapa a ninguém". A justificativa não se sustentava: pedido sem responsável não é
de ninguém, é de quem resolveu pegá-lo. Na prática o gerente atribuía o pedido a
si mesmo só para liberar o botão — o que grava exatamente o mesmo resultado, com
um passo a mais e uma linha de atribuição que não significa nada.

`finalizar_delegado` continua conferindo, na hora de fechar, se o responsável
mudou depois da abertura: nesse caso quem o gerente está creditando não é mais
quem fez o trabalho, e a chamada é recusada — o caminho é resetar e refazer. Sem
atribuição nenhuma não há o que conferir, porque o processo já nasceu creditado a
quem o abriu.

## As duas ações são em lote, e o porquê

**Iniciar** abre a etapa com todos os itens já iniciados. A trava de "um item em
andamento por vez" existe para medir o tempo *por item* durante a bipagem; aqui
não há bipagem, então aplicá-la só obrigaria o gerente a dar um clique por linha
sem medir nada.

**Finalizar** fecha cada item pendente **com a quantidade pedida**, sem
divergência. Fechar com a quantidade gravada marcaria tudo como divergente
(ninguém bipou), e o relatório de falta passaria a apontar falta que não houve.
O gerente está confirmando que o operador fez o trabalho completo — é essa a
afirmação, e é ela que fica gravada.

Falta de verdade continua pelo caminho de sempre: item a item, com senha de
gerente em `finalizar_item`.

`data_primeiro_bipe` fica **NULL** nos dois casos. O "T. Separação" da listagem
some para esses pedidos, e isso é a informação correta — o tempo de trabalho
simplesmente não foi medido ali.

## Por que não pede senha de gerente

`resetar` e o fechamento com falta em `finalizar_item` pedem usuário e senha de
um gerente. Ali quem está na tela é o **operador**, e a credencial é a única
prova de que um gerente autorizou aquilo.

Aqui quem está logado **já é** o gerente, com `expedicao.delegar` checada no
endpoint. Pedir senha seria pedir que ele prove ser ele mesmo.

## A permissão

`expedicao.delegar` é separada de `expedicao.atribuir` de propósito: distribuir
trabalho e executar por outra pessoa são coisas diferentes, e o galpão pode
querer dar uma sem a outra.

Os endpoints não chamam `_exigir_execucao` — quem delega não executa a etapa,
despacha alguém que executa. Exigir dele `expedicao.separacao.executar`
obrigaria todo gerente a poder separar, o contrário do motivo de a delegação
existir.

## A exceção: liberar endereçamento inconsistente

Um pedido com endereçamento inconsistente (saldo endereçado menor que o pedido,
ou endereço que não fecha em múltiplo da embalagem de venda) não pode ser
separado nem conferido — nem pelo operador, nem pela execução delegada. A regra
está em `_bloqueio_do_item` e vale porque o problema é de cadastro do galpão, e
é mais barato corrigir antes do que remendar depois.

Só que às vezes a mercadoria está lá, o cadastro é que está errado, e o pedido
precisa faturar hoje. Para esse caso existe `expedicao.enderecamento.liberar`.

**O que a chave faz:** quem a tem atravessa o bloqueio pelos botões da execução
delegada — `iniciar-delegado` e `finalizar-delegado`. Nada mais.

**O que ela não faz:**

- Não libera o botão do rodapé, o do operador. Ele continua escondido, com a
  mesma frase de sempre ("Endereçamento inconsistente — o pedido não pode ser
  iniciado"). A exceção é de quem responde pelo galpão, não de quem separa.
- Não atravessa o status do ERP. Pedido fora de `PED` continua recusado com 409
  nos dois caminhos: status é do ERP, e não existe nada a fazer daqui sobre ele.
  É por isso que o detalhe do pedido devolve `statusPermiteIniciar` além de
  `podeIniciar` — com um booleano só, a tela não distinguiria as duas causas.

**Por que a chave também vale no fim, e não só no início.** Ao fechar a
separação, a expedição baixa o saldo do endereço por
`enderecamento_publico.baixar_lote`, que recusa saldo insuficiente. Liberar o
início sem liberar o fim deixaria o pedido preso em andamento — e não teria
destravado faturamento nenhum. Com a liberação, `baixar_lote` zera o que havia
no endereço e segue: a mercadoria de fato saiu da prateleira, e deixar o saldo
lá dentro criaria estoque fantasma, que é pior que a divergência que se aceitou.

**Rastro.** Não pede senha de gerente, pelo mesmo motivo do resto desta página:
quem está logado já é quem autoriza. Quem clicou fica em
`usuario_gestor_inicio_id` / `usuario_gestor_fim_id` quando não é o próprio
operador da etapa.

## Onde está

- Colunas: `Separacao` e `Conferencia` em `expedicao_model.py`
- Migração: `b7e3a9d51c04_expedicao_execucao_delegada.py`
- Regra: `iniciar_delegado` / `finalizar_delegado` em `expedicao_service.py`
- HTTP: `POST /expedicao/{tipo}/pedidos/{pedido_id}/iniciar-delegado` e
  `.../finalizar-delegado`
- Tela: os dois botões na caixa de cada etapa em `expedicao-pedido.html`
- Testes: `TestExecucaoDelegada` em `tests/test_expedicao_e2e.py`
- Liberação de endereçamento: `expedicao.enderecamento.liberar` em
  `permission_model.py`, `_pode_liberar_enderecamento` em `expedicao_router.py`,
  `permitir_saldo_insuficiente` em `enderecamento_publico.baixar_lote`
