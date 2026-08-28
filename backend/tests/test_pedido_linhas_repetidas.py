"""
Repetição de produto num pedido.

A identidade da linha é `(produto, lote)`. O endereço não entra: ele é onde a
mercadoria está guardada no nosso galpão, não o que o cliente comprou. Um lote
se espalha por vários endereços de verdade, mas isso é assunto da separação —
nos ERPs grandes a linha do pedido nem carrega endereço.

Uma regra anterior incluía o endereço na chave e deixava passar exatamente o
defeito que motivou esta: a consulta da integração cruzava a linha do pedido com
o estoque por endereço e devolvia uma linha por endereço, cada uma com a
quantidade INTEIRA. Um pedido de 14.000 un entrava com 42.000, e a validação
aprovava. Ver a migração c9e4a71f5b38.
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


def test_mesmo_produto_e_lote_repetido_e_recusado():
    """O produto cartesiano da integração, que é o que esta regra existe para
    barrar. Duas linhas de 40 un do mesmo produto e lote viravam 80 un num
    pedido de 40.

    Na origem do defeito as duas vinham com endereços diferentes — a consulta
    de lá cruzava a linha do pedido com o estoque por endereço. Hoje o endereço
    nem chega no contrato do pedido (ele é do domínio `enderecamento`), então as
    duas linhas chegam idênticas e a regra as recusa pelo par produto+lote."""
    with pytest.raises(ValidationError, match="mesmo produto e lote"):
        PedidoCriarSchema(**_pedido([_item(), _item()]))


def test_mesmo_produto_em_lotes_diferentes_e_aceito():
    """Lote é fabricação diferente — são duas coisas distintas para o cliente,
    e é a única forma legítima de o mesmo produto repetir no pedido."""
    pedido = PedidoCriarSchema(**_pedido([_item(), _item(lote="5L3600")]))
    assert len(pedido.itens) == 2


def test_linha_identica_e_recusada():
    with pytest.raises(ValidationError, match="mesmo produto e lote"):
        PedidoCriarSchema(**_pedido([_item(), _item()]))


def test_produtos_diferentes_continuam_aceitos():
    pedido = PedidoCriarSchema(**_pedido([_item(), _item(produtoSistemaOrigemId="0010101")]))
    assert len(pedido.itens) == 2


def test_itens_sem_lote_nao_escapam_da_regra():
    """No MySQL dois NULL não colidem num unique, então o banco deixaria passar.
    Aqui em Python None == None, e é o contrato que fecha esse buraco."""
    with pytest.raises(ValidationError, match="mesmo produto e lote"):
        PedidoCriarSchema(**_pedido([_item(lote=None), _item(lote=None)]))
