"""
Repetição de produto num pedido.

A regra antiga olhava só o produto e recusava o caso normal do galpão: o mesmo
item, do mesmo lote, guardado em dois endereços. Cada linha diz onde buscar
qual quantidade — somar as duas apagaria justamente o que a separação usa.
"""

import pytest
from pydantic import ValidationError

from app.domains.pedidos.pedido_contrato import PedidoCriarSchema


def _item(**overrides) -> dict:
    base = {
        "produtoSistemaOrigemId": "0019159",
        "produtoCodigo": "0019159",
        "produtoDescricao": "CLOR.ONDANSETRONA 2MG/ML CX/50AMPX2ML",
        "quantidade": 40,
        "precoUnitario": 1.0,
        "enderecoProduto": "06-12-08-04-02",
        "lote": "78XA0563",
    }
    base.update(overrides)
    return base


def _pedido(itens: list[dict]) -> dict:
    return {
        "dataPedido": "2026-08-20",
        "clienteId": "cliente-1",
        "empresaSistemaOrigemId": "1",
        "statusSistemaOrigemId": "PED",
        "itens": itens,
    }


def test_mesmo_produto_e_lote_em_enderecos_diferentes_e_aceito():
    """O caso real que quebrou: 40 unidades num endereço e 40 em 'NÃO ENDEREÇADO'."""
    pedido = PedidoCriarSchema(
        **_pedido([_item(), _item(enderecoProduto="NAO ENDEREÇADO")])
    )
    assert len(pedido.itens) == 2


def test_mesmo_produto_em_lotes_diferentes_e_aceito():
    pedido = PedidoCriarSchema(**_pedido([_item(), _item(lote="5L3600")]))
    assert len(pedido.itens) == 2


def test_linha_identica_nos_tres_campos_e_recusada():
    # Sem nada que distinga as duas linhas, são duas linhas para a mesma coisa.
    with pytest.raises(ValidationError, match="mesmo produto, lote e endereço"):
        PedidoCriarSchema(**_pedido([_item(), _item()]))


def test_produtos_diferentes_continuam_aceitos():
    pedido = PedidoCriarSchema(**_pedido([_item(), _item(produtoSistemaOrigemId="0010101")]))
    assert len(pedido.itens) == 2
