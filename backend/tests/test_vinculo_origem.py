"""
O vínculo com o sistema de origem nunca é apagado por uma gravação comum.

A regra está em `app/shared/vinculo_origem.py`, com o relato do incidente que a
criou. Aqui ela é verificada em duas camadas:

1. A função, isolada — a ordem de precedência e os campos compostos.
2. Uma varredura sobre TODOS os services do projeto, que falha quando alguém
   escreve num campo de vínculo sem passar pela regra. É esta segunda que
   protege o domínio que ainda não existe: o defeito original apareceu em dez
   arquivos ao mesmo tempo, e nenhum teste por domínio teria pego todos.
"""

import ast
import pathlib

import pytest

from app.shared.vinculo_origem import (
    e_campo_de_vinculo,
    preservar_no_dicionario,
    resolver,
)

RAIZ_DOMINIOS = pathlib.Path(__file__).resolve().parents[1] / "app" / "domains"


class _Registro:
    """Um model qualquer, só com os atributos que interessam ao teste."""

    def __init__(self, **campos):
        self.__dict__.update(campos)


class TestResolver:
    def test_o_corpo_manda_quando_traz_valor(self):
        assert resolver("00999", "00168", "00111") == "00999"

    def test_cai_para_a_chave_da_busca(self):
        """O integrador não deveria precisar reenviar a própria chave que usou
        para identificar o registro."""
        assert resolver(None, "00168", "00111") == "00168"

    def test_cai_para_o_que_ja_estava_gravado(self):
        """O degrau que faltava, e que quebrou a produção: editar pela tela não
        manda o campo nem o query param."""
        assert resolver(None, None, "00168") == "00168"

    def test_sem_nada_continua_sem_nada(self):
        """Registro criado à mão não ganha vínculo do nada."""
        assert resolver(None, None, None) is None

    def test_string_vazia_conta_como_ausencia(self):
        """A integração manda "" quando o campo não se aplica. Gravar isso
        deixaria o registro com um vínculo que não casa com nada no ERP."""
        assert resolver("", None, "00168") == "00168"


class TestCamposCompostos:
    def test_reconhece_os_compostos(self):
        for nome in (
            "sistema_origem_id",
            "empresa_sistema_origem_id",
            "pedido_sistema_origem_id",
            "produto_sistema_origem_id",
        ):
            assert e_campo_de_vinculo(nome), nome

    def test_nao_confunde_com_outros_campos(self):
        for nome in ("sistema_origem", "origem_id", "nome", "sync_created_at"):
            assert not e_campo_de_vinculo(nome), nome

    def test_preserva_todos_os_vinculos_do_dicionario(self):
        registro = _Registro(
            sistema_origem_id="0186762",
            empresa_sistema_origem_id="01",
            produto_sistema_origem_id="12-2818",
            nome="antigo",
        )
        campos = {
            "sistema_origem_id": None,
            "empresa_sistema_origem_id": None,
            "produto_sistema_origem_id": None,
            "nome": "novo",
        }

        preservar_no_dicionario(campos, registro)

        assert campos["sistema_origem_id"] == "0186762"
        assert campos["empresa_sistema_origem_id"] == "01"
        assert campos["produto_sistema_origem_id"] == "12-2818"
        # Campo que não é vínculo continua sendo sobrescrito normalmente.
        assert campos["nome"] == "novo"

    def test_a_chave_da_busca_so_vale_para_o_campo_proprio(self):
        """`da_busca` é a identidade DESTE registro. Os compostos referenciam
        OUTRO registro, e o que localizou este não diz nada sobre eles."""
        registro = _Registro(sistema_origem_id=None, empresa_sistema_origem_id=None)
        campos = {"sistema_origem_id": None, "empresa_sistema_origem_id": None}

        preservar_no_dicionario(campos, registro, da_busca="0186762")

        assert campos["sistema_origem_id"] == "0186762"
        assert campos["empresa_sistema_origem_id"] is None


# ---------------------------------------------------------------------------
# A varredura: nenhum service escreve num campo de vínculo por fora da regra
# ---------------------------------------------------------------------------


def _funcoes_que_escrevem_vinculo(caminho: pathlib.Path):
    """As funções do arquivo que atribuem a um campo de vínculo.

    A verificação é por FUNÇÃO, e não por linha, porque a regra costuma ser
    aplicada algumas linhas acima da atribuição — `sistema_origem_id_final =
    resolver(...)` e depois `registro.sistema_origem_id = sistema_origem_id_final`.
    Olhar só a linha da atribuição acusaria código correto.

    Só atribuição a ATRIBUTO (`registro.campo = ...`), que é escrita no model.
    Passar o valor como argumento nomeado na construção de um schema de
    resposta é leitura, não escrita, e não entra. Construir o model com
    `Usuario(sistema_origem_id=...)` também não: é criação, e criação não tem
    valor anterior a preservar.
    """
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    for funcao in ast.walk(arvore):
        if not isinstance(funcao, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        campos = [
            alvo.attr
            for no in ast.walk(funcao)
            if isinstance(no, ast.Assign)
            for alvo in no.targets
            if isinstance(alvo, ast.Attribute) and e_campo_de_vinculo(alvo.attr)
        ]
        if campos:
            yield funcao, campos


def _aplica_a_regra(funcao) -> bool:
    return any(
        isinstance(no, ast.Name)
        and no.id in {"resolver_vinculo_origem", "resolver", "preservar_no_dicionario"}
        for no in ast.walk(funcao)
    )


@pytest.mark.parametrize(
    "arquivo",
    sorted(RAIZ_DOMINIOS.glob("*/*_service.py")),
    ids=lambda p: p.parent.name,
)
def test_nenhum_service_escreve_vinculo_por_fora_da_regra(arquivo):
    """Falha quando um service novo (ou uma linha nova num service antigo)
    atribui a um campo de vínculo sem passar por `vinculo_origem`.

    Se este teste falhar num código que você acabou de escrever: não é para
    contornar. Use `resolver` (campo a campo) ou `preservar_no_dicionario`
    (dicionário + setattr). Ver `app/shared/vinculo_origem.py`.
    """
    fora_da_regra = [
        (funcao.name, funcao.lineno, campos)
        for funcao, campos in _funcoes_que_escrevem_vinculo(arquivo)
        if not _aplica_a_regra(funcao)
    ]
    assert not fora_da_regra, (
        f"{arquivo.name} escreve em campo de vínculo sem usar "
        f"app/shared/vinculo_origem.py: {fora_da_regra}"
    )
