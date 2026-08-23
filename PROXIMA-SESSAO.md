# Prompt para a próxima sessão

Copie o bloco abaixo inteiro como primeira mensagem da nova sessão.

---

Leia `ARCHITECTURE.md` e `backend/ARCHITECTURE.md` antes de tocar em qualquer
código — eles são a autoridade sobre estrutura de pastas, regras de import
entre domínios, convenção camelCase e onde cada coisa mora. Depois leia
`backend/tests/test_expedicao_e2e.py`, que é o teste mais completo do projeto e
mostra o padrão de teste esperado (TestClient sobre SQLite em memória, com
`obter_usuario_atual` substituído por override).

## Contexto do que já está pronto no domínio de expedição

O fluxo de **atribuição de pedidos** está implementado e testado ponta a ponta:

- Tabela `expedicao_atribuicoes` — chave lógica `(pedido_id, tipo)`, porque uma
  pessoa separa e outra confere o mesmo pedido.
- Permissão `expedicao.atribuir` decide o que cada um enxerga: **quem não tem
  só vê pedidos atribuídos a ele, e vê lista vazia se nada foi atribuído.**
  Essa é uma decisão de negócio tomada e reafirmada — não proponha o modelo
  híbrido ("vê os atribuídos + os sem dono") nem fila puxada.
- O filtro de visibilidade é aplicado na **consulta paginada** do backend
  (`expedicao_service.listar_pedidos`), nunca na tela.
- `iniciar_processo` devolve 403 se a etapa está atribuída a outro operador.
- Conferência só pode ser atribuída depois de a separação ser finalizada.
- Remover responsável é `usuarioId: null` no mesmo endpoint — não é operação
  separada.
- Correção de código de barras na bipagem grava no Oracle do ERP e, só se
  confirmado lá, no espelho local (`app/shared/sistema_origem/`).

## O que eu preciso agora: um teste E2E de UI

Os testes atuais batem na API. Quero um **teste ponta a ponta pela interface**,
cobrindo o mesmo fluxo de atribuição que `test_e2e_atribuicao_da_distribuicao_ate_a_conferencia`
cobre no backend, mas pelo navegador.

Cenário a percorrer:

1. Logar como **coordenador** (usuário com `expedicao.atribuir`) e abrir
   `/expedicao`. A fila do período aparece.
2. Marcar dois ou três pedidos no checkbox da primeira coluna e clicar em
   **Atribuir separação**, escolhendo um operador. Confirmar que o nome do
   designado passa a aparecer na coluna Etapa.
3. Tentar **Atribuir conferência** num pedido cuja separação não foi feita e
   confirmar que a tela mostra a recusa (409) com a mensagem explicando que a
   separação precisa ser finalizada antes.
4. Logar como o **operador designado** e abrir `/expedicao`: só os pedidos
   atribuídos a ele aparecem.
5. Logar como um **operador sem nenhuma atribuição**: a lista abre vazia — isso
   é o comportamento correto, não um bug.
6. Voltar ao coordenador e remover a atribuição pelo `x` na linha; confirmar
   que o pedido some da lista do operador.

Verifique também o **filtro de status do ERP** (multiselect dentro do accordion
"Filtros avançados"): marcar um status recarrega do servidor, e a escolha
sobrevive a recarregar a página, porque é persistida em localStorage.

Use a ferramenta de navegador (`preview_start` / `read_page` / `computer`) — o
front sobe com `npm start` na porta 4200. **Eu preciso fazer o login, porque
você não digita senha.** Me avise quando a tela estiver aberta e eu logo.

## Coisas que você vai encontrar e NÃO deve tentar consertar de passagem

- `tests/test_usuario_service.py` (19 falhas), `tests/test_pedido_service.py`
  (10 erros) e `tests/test_pedido_sistema_origem.py` (10 falhas) estão
  quebrados de antes: os helpers de teste montam schemas sem campos que
  passaram a ser obrigatórios (ex: `cargo_id` em `UsuarioCriarSchema`). É
  trabalho à parte — me pergunte antes de mexer.
- O banco MySQL é o da empresa (`192.168.20.12/dashboard`), acessado por VPN.
  **Não rode `alembic upgrade` sem me perguntar.**
- O Oracle do ERP exige `oracledb` 3.4 em **modo thick** com o Instant Client em
  `C:/oracle/instantclient_19_28`. Não atualize o driver para 4.x.
