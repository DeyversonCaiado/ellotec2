"""
`sistema_origem_id` sozinho NÃO identifica um pedido.

A unicidade na tabela é do par `(sistema_origem_id, empresa_id)`: cada
empresa/filial integra com o próprio ERP, e o mesmo número existe nas duas.

O bug real que estes testes travam: a busca por `sistema_origem_id` fazia
`.first()` e podia devolver o pedido da OUTRA empresa. A atualização seguinte
colidia com o registro correto e devolvia 409 — um erro cuja causa não tinha
relação aparente com o que a integração havia pedido.

A regra vale só para a busca por `sistema_origem_id`. Quem chama pelo `id` da
URL continua igual: aquele é UUID, já identifica sozinho.
"""

from datetime import date

import pytest
from fastapi import HTTPException

from app.domains.cidades.cidade_model import Cidade
from app.domains.clientes.cliente_model import Cliente
from app.domains.empresas.empresa_model import Empresa
from app.domains.pedidos import pedido_service
from app.domains.pedidos.pedido_model import Pedido, PedidoStatus

SISTEMA_ORIGEM = "0186263"


@pytest.fixture()
def duas_empresas(sessao_db):
    """O mesmo número de pedido em duas filiais — o cenário real."""
    cidade = Cidade(codigo_municipio=5208707, nome="Goiânia", uf="GO")
    sessao_db.add(cidade)
    sessao_db.commit()

    cliente = Cliente(
        razao_social="Distribuidora Saúde Total Ltda",
        nome_fantasia="Saúde Total",
        cpf_cnpj="12.345.678/0001-90",
        cidade_id=cidade.id,
    )
    matriz = Empresa(
        razao_social="Ellotec Matriz",
        nome_fantasia="Matriz",
        cnpj="00.000.000/0001-00",
        sistema_origem_id="1",
    )
    filial = Empresa(
        razao_social="Ellotec Filial",
        nome_fantasia="Filial",
        cnpj="00.000.000/0002-00",
        sistema_origem_id="2",
    )
    status = PedidoStatus(chave="PED")
    sessao_db.add_all([cliente, matriz, filial, status])
    sessao_db.commit()

    for indice, empresa in enumerate((matriz, filial)):
        sessao_db.add(
            Pedido(
                numero=f"PED-0000{indice}",
                data_pedido=date(2026, 8, 20),
                cliente_id=cliente.id,
                cliente_nome_fantasia="Saúde Total",
                cliente_cnpj="12.345.678/0001-90",
                empresa_id=empresa.id,
                status_id=status.id,
                sistema_origem_id=SISTEMA_ORIGEM,
                observacoes="",
            )
        )
    sessao_db.commit()
    return matriz, filial


class TestBuscaPorSistemaOrigem:
    def test_sem_empresa_a_busca_ambigua_e_recusada(self, sessao_db, duas_empresas):
        # Antes devolvia `.first()` — um dos dois, escolhido pela ordem do
        # banco. Errar em silêncio é pior que recusar.
        with pytest.raises(HTTPException) as excecao:
            pedido_service.obter_por_sistema_origem_id(sessao_db, SISTEMA_ORIGEM)

        assert excecao.value.status_code == 409
        assert "mais de uma empresa" in excecao.value.detail

    def test_com_empresa_encontra_o_pedido_certo(self, sessao_db, duas_empresas):
        matriz, filial = duas_empresas

        da_matriz = pedido_service.obter_por_sistema_origem_id(sessao_db, SISTEMA_ORIGEM, matriz.id)
        da_filial = pedido_service.obter_por_sistema_origem_id(sessao_db, SISTEMA_ORIGEM, filial.id)

        assert da_matriz.empresa_id == matriz.id
        assert da_filial.empresa_id == filial.id
        assert da_matriz.id != da_filial.id

    def test_busca_pelo_id_nao_e_afetada(self, sessao_db, duas_empresas):
        """O id da URL é UUID: identifica sozinho, sem empresa nenhuma."""
        matriz, _filial = duas_empresas
        alvo = pedido_service.obter_por_sistema_origem_id(sessao_db, SISTEMA_ORIGEM, matriz.id)

        assert pedido_service.obter_por_id(sessao_db, alvo.id).id == alvo.id

    def test_sem_ambiguidade_a_empresa_continua_opcional(self, sessao_db, duas_empresas):
        matriz, _filial = duas_empresas
        # Número que só existe numa empresa: a integração pode continuar
        # chamando sem informar empresa, como sempre fez.
        pedido = pedido_service.obter_por_sistema_origem_id(sessao_db, SISTEMA_ORIGEM, matriz.id)
        pedido.sistema_origem_id = "SO-UNICO"
        sessao_db.commit()

        assert pedido_service.obter_por_sistema_origem_id(sessao_db, "SO-UNICO").id == pedido.id

    def test_empresa_inexistente_no_sistema_de_origem_gera_404(self, sessao_db, duas_empresas):
        with pytest.raises(HTTPException) as excecao:
            pedido_service.resolver_empresa(sessao_db, None, "nao-existe")

        assert excecao.value.status_code == 404
