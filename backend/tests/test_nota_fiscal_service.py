"""
Testes do domínio notas_fiscais (app/domains/notas_fiscais).

O foco não é CRUD — é o que quebra em silêncio num domínio fiscal:

- entrada e saída convivem na mesma tabela e são separadas por filtro;
- a precisão decimal do leiaute da NF-e sobrevive à ida e volta do banco;
- a mesma nota não entra duas vezes quando a integração reprocessa o XML;
- o XML original não é apagado por uma atualização que não o reenvia.

Os valores usados aqui são de uma NF-e real (modelo 55, 7 itens), incluindo o
`vUnCom` de 5 casas que motivou a coluna Numeric(21, 10).
"""

from datetime import datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.domains.empresas.empresa_model import Empresa
from app.domains.notas_fiscais import nota_fiscal_service
from app.domains.notas_fiscais.nota_fiscal_contrato import (
    NotaFiscalAtualizarSchema,
    NotaFiscalCriarSchema,
)

CHAVE = "35260461418042000131550040019871341248416070"


@pytest.fixture()
def empresa(sessao_db) -> Empresa:
    registro = Empresa(
        razao_social="ELLO DISTRIBUICAO LTDA",
        nome_fantasia="Ello",
        cnpj="14.115.388/0001-80",
    )
    sessao_db.add(registro)
    sessao_db.commit()
    return registro


def _dados_criar(empresa, **overrides) -> NotaFiscalCriarSchema:
    base = dict(
        empresa_id=empresa.id,
        modelo="55",
        tipo_operacao="entrada",
        chave_acesso=CHAVE,
        numero="1987134",
        serie="4",
        natureza_operacao="VENDAS",
        data_emissao=datetime(2026, 4, 29, 9, 24, 45),
        emitente_cnpj_cpf="61.418.042/0001-31",
        emitente_razao_social="CIRURGICA FERNANDES C.MAT.CIR.HO.SO.LTDA",
        emitente_uf="SP",
        destinatario_cnpj_cpf="14.115.388/0001-80",
        destinatario_razao_social="ELLO DISTRIBUICAO LTDA",
        destinatario_uf="GO",
        valor_produtos=Decimal("29452.08"),
        valor_total=Decimal("31741.83"),
        quantidade_volumes=43,
        peso_bruto=Decimal("460.500"),
        xml_original="<nfeProc>...</nfeProc>",
        itens=[
            dict(
                numero_item=1,
                produto_codigo="12-2818",
                produto_descricao="LANCETA DE SEGURANCA 28GX1.8MM CX100 WILTEX",
                codigo_barras="7899780173003",
                ncm="90183999",
                cfop="6102",
                unidade="CX",
                quantidade=Decimal("2000.00"),
                preco_unitario=Decimal("7.1292800000"),
                valor_total_item=Decimal("14258.56"),
                lote="2512366503",
            )
        ],
    )
    base.update(overrides)
    return NotaFiscalCriarSchema(**base)


def test_grava_preco_unitario_com_as_casas_do_leiaute(sessao_db, empresa):
    """`vUnCom` aceita 10 casas decimais. Se a coluna arredondar, o somatório
    dos itens deixa de bater com o total da nota — e o MySQL faz isso com um
    simples warning, sem falhar o INSERT."""
    nota = nota_fiscal_service.criar(sessao_db, _dados_criar(empresa))
    sessao_db.expire_all()

    item = nota_fiscal_service.obter_por_id(sessao_db, nota.id).itens[0]
    assert item.preco_unitario == Decimal("7.1292800000")
    assert item.quantidade == Decimal("2000.0000")


def test_entrada_e_saida_convivem_e_sao_separadas_por_filtro(sessao_db, empresa):
    """As duas moram na mesma tabela: o menu tem dois itens, o banco tem um."""
    nota_fiscal_service.criar(sessao_db, _dados_criar(empresa))
    nota_fiscal_service.criar(
        sessao_db,
        _dados_criar(
            empresa,
            tipo_operacao="saida",
            chave_acesso=None,
            numero="900",
            serie="1",
            emitente_cnpj_cpf="14.115.388/0001-80",
        ),
    )

    entradas, total_entradas = nota_fiscal_service.listar_paginado(
        sessao_db, 1, 20, "data_emissao", "desc", tipo_operacao="entrada"
    )
    _, total_saidas = nota_fiscal_service.listar_paginado(
        sessao_db, 1, 20, "data_emissao", "desc", tipo_operacao="saida"
    )
    _, total_geral = nota_fiscal_service.listar_paginado(
        sessao_db, 1, 20, "data_emissao", "desc"
    )

    assert (total_entradas, total_saidas, total_geral) == (1, 1, 2)
    assert entradas[0].chave_acesso == CHAVE


def test_recusa_a_mesma_nota_duas_vezes(sessao_db, empresa):
    """O erro mais comum de integração fiscal: o job roda de novo e reenvia o
    mesmo XML."""
    nota_fiscal_service.criar(sessao_db, _dados_criar(empresa))

    with pytest.raises(HTTPException) as erro:
        nota_fiscal_service.criar(sessao_db, _dados_criar(empresa))
    assert erro.value.status_code == 409


def test_recusa_duplicata_sem_chave_de_acesso(sessao_db, empresa):
    """NFS-e não tem chave de 44 dígitos — quem pega a duplicata aí é a chave
    natural do documento (empresa, modelo, série, número, emitente)."""
    dados = _dados_criar(empresa, modelo="NFSE", chave_acesso=None)
    nota_fiscal_service.criar(sessao_db, dados)

    with pytest.raises(HTTPException) as erro:
        nota_fiscal_service.criar(sessao_db, dados)
    assert erro.value.status_code == 409


def test_atualizar_sem_xml_nao_apaga_o_documento_original(sessao_db, empresa):
    """Guardar o XML é obrigação legal de 5 anos. Uma correção de capa enviada
    sem ele não pode zerar a coluna."""
    nota = nota_fiscal_service.criar(sessao_db, _dados_criar(empresa))

    dados = _dados_criar(empresa, natureza_operacao="COMPRA", xml_original=None)
    nota_fiscal_service.atualizar(
        sessao_db, nota.id, NotaFiscalAtualizarSchema(**dados.model_dump())
    )
    sessao_db.expire_all()

    atualizada = nota_fiscal_service.obter_com_xml(sessao_db, nota.id)
    assert atualizada.natureza_operacao == "COMPRA"
    assert atualizada.xml_original == "<nfeProc>...</nfeProc>"


def test_item_sem_produto_cadastrado_e_aceito(sessao_db, empresa):
    """Numa nota de entrada o produto é do fornecedor e pode não existir aqui.
    Recusar a nota por isso impediria de guardar um documento que a empresa é
    obrigada a guardar."""
    nota = nota_fiscal_service.criar(sessao_db, _dados_criar(empresa))
    assert nota.itens[0].produto_id is None


def test_nota_nasce_sem_pedido_e_recusa_pedido_inexistente(sessao_db, empresa):
    """`pedido_id` é opcional porque toda nota de entrada (e as de devolução e
    remessa) não tem pedido deste lado. Quando vier preenchido, quem recusa id
    inexistente é a FK do banco — o service não consulta o domínio pedidos."""
    nota = nota_fiscal_service.criar(sessao_db, _dados_criar(empresa))
    assert nota.pedido_id is None

    with pytest.raises(IntegrityError):
        nota_fiscal_service.criar(
            sessao_db,
            _dados_criar(empresa, chave_acesso=None, numero="999", pedido_id="nao-existe"),
        )


def test_periodo_filtra_pela_data_de_emissao(sessao_db, empresa):
    """O período da tela é sempre a data de negócio do documento, nunca os
    campos de auditoria (`sync_*`), que mudam a cada reprocessamento."""
    nota_fiscal_service.criar(sessao_db, _dados_criar(empresa))

    _, dentro = nota_fiscal_service.listar_paginado(
        sessao_db,
        1,
        20,
        "data_emissao",
        "desc",
        data_inicio=datetime(2026, 4, 29).date(),
        data_fim=datetime(2026, 4, 29).date(),
    )
    _, fora = nota_fiscal_service.listar_paginado(
        sessao_db,
        1,
        20,
        "data_emissao",
        "desc",
        data_inicio=datetime(2026, 5, 1).date(),
        data_fim=datetime(2026, 5, 31).date(),
    )

    # A nota foi emitida às 09:24 do dia 29 — um filtro de "29 até 29" que
    # comparasse com a data pura a excluiria, porque 09:24 > 00:00.
    assert (dentro, fora) == (1, 0)
