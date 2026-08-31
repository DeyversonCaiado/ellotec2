"""
O vínculo com o sistema de origem nunca é apagado por uma gravação comum.

## A regra

Todo campo cujo nome termina em `sistema_origem_id` guarda a identidade do
registro no ERP: `sistema_origem_id`, `empresa_sistema_origem_id`,
`pedido_sistema_origem_id`, `produto_sistema_origem_id`. Uma gravação que não
traz esse campo **não o apaga** — ela mantém o que já estava gravado.

A ordem de precedência, sempre a mesma:

1. o valor que o CORPO da requisição trouxe;
2. senão, o valor pelo qual o registro foi LOCALIZADO (o query param que a
   integração usa em `PUT /recurso/{id}?sistema_origem_id=...`);
3. senão, **o que já estava gravado**.

Apagar o vínculo é uma operação explícita, e hoje não existe endpoint para ela.
Se um dia existir, será um caminho próprio, com nome próprio — nunca o efeito
colateral de um formulário que sequer exibe o campo.

## Por que esta regra existe (o incidente que a criou)

Faltava o degrau 3. A tela de usuários não exibe nem envia `sistemaOrigemId`, e
edita pelo id — sem o query param. Então os dois primeiros degraus davam `None`,
e o campo era zerado em silêncio: nenhum erro, nenhum log, `sync_version`
incrementando normalmente.

O funcionário `00168` (MARCOS RODRIGO FONSECA) perdeu o vínculo assim. A
consequência apareceu longe da causa, dias depois e em outro domínio: todo
pedido que apontava para aquele vendedor passou a responder
`404 Vendedor não encontrado para o sistema de origem informado`, o
sincronizador levantou `RuntimeError`, o processo morreu, o systemd reiniciou, e
o ciclo se repetiu a cada 30 segundos. O checkpoint da integração de pedidos
ficou **três dias parado**, com 173 pedidos represados — e o `systemctl status`
mostrando `active (running)` o tempo todo.

Cinco usuários estavam nesse estado quando o problema foi investigado. O mesmo
defeito existia, com o mesmo formato, em clientes, produtos, marcas, empresas,
pedidos, estoque, endereçamento, entregas e notas fiscais — ou seja, em todo
domínio que a integração alimenta.

## Como usar

Duas formas, conforme o service escreve:

- Campo a campo (`registro.sistema_origem_id = ...`): use `resolver`.
- Dicionário aplicado com `setattr` (o padrão `model_dump()` + laço): use
  `preservar_no_dicionario`, que cuida de todos os campos de vínculo de uma vez.

Ao criar um domínio novo com campo de vínculo, use um dos dois. Não escreva a
cadeia de `or` à mão: a regra existe num lugar só justamente porque a versão
manual já foi escrita errado em dez arquivos.
"""

# Sufixo que identifica um campo de vínculo. É sufixo, e não lista fechada, para
# que um campo novo (`transportadora_sistema_origem_id`, digamos) já nasça
# protegido sem ninguém precisar lembrar de registrá-lo aqui.
SUFIXO_VINCULO = "sistema_origem_id"


def e_campo_de_vinculo(nome: str) -> bool:
    return nome.endswith(SUFIXO_VINCULO)


def resolver(
    do_corpo: str | None,
    da_busca: str | None = None,
    ja_gravado: str | None = None,
) -> str | None:
    """O valor final do vínculo, na ordem corpo → busca → já gravado.

    `da_busca` é o `sistema_origem_id` que veio como query param e localizou o
    registro; passe `None` quando a operação não usa esse caminho.
    """
    return do_corpo or da_busca or ja_gravado


def preservar_no_dicionario(
    campos: dict, registro, da_busca: str | None = None
) -> dict:
    """Aplica a regra a TODO campo de vínculo de um `model_dump()`.

    Muda o dicionário no lugar e o devolve, para caber na linha que já existe
    antes do laço de `setattr`.

    O `da_busca` só vale para o campo `sistema_origem_id` — é a identidade
    daquele registro. Os compostos (`empresa_sistema_origem_id` e afins) são
    referência a OUTRO registro, e o que localizou este não diz nada sobre eles.
    """
    for nome, valor in list(campos.items()):
        if not e_campo_de_vinculo(nome):
            continue
        campos[nome] = resolver(
            do_corpo=valor,
            da_busca=da_busca if nome == SUFIXO_VINCULO else None,
            ja_gravado=getattr(registro, nome, None),
        )
    return campos
