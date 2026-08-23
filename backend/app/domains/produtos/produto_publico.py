from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.produtos.produto_model import Produto, ProdutoCodigoBarras
from app.shared import gs1


@dataclass(frozen=True)
class ProdutoBipagem:
    """O que a expedição precisa saber de um produto a cada bipe: quem ele é e
    quantas unidades vale uma leitura."""

    id: str
    quantidade_multipla_venda: int


def obter_id_por_sistema_origem_id(sessao_db: Session, sistema_origem_id: str) -> str | None:
    """Só leitura — devolve o id primitivo, nunca o model. Canal usado por
    outros domínios (ex: pedidos) para resolver um produto pelo id do
    sistema de origem sem importar `produto_service`."""
    produto = (
        sessao_db.query(Produto)
        .filter(Produto.sistema_origem_id == sistema_origem_id, Produto.sync_deleted_at.is_(None))
        .first()
    )
    return produto.id if produto else None


@dataclass(frozen=True)
class ProdutoExpedicao:
    """O que as telas da expedição mostram do cadastro do produto — o que não é
    snapshot do pedido. Todos saem da mesma linha, então saem juntos: campos da
    mesma tabela não justificam uma consulta cada.

    Marca e os códigos de barras estão aqui porque o operador confere a caixa
    pelo que está impresso nela antes de bipar — e nenhum deles é congelado no
    pedido: vale o cadastro de hoje, que é o mesmo que a bipagem valida."""

    unidade: str
    quantidade_multipla_venda: int
    marca_nome: str
    codigo_barra_notas: str | None
    codigos_barras_logistica: tuple[str, ...] = ()
    dun_14: str | None = None


def obter_para_expedicao(sessao_db: Session, produto_ids: list[str]) -> dict[str, ProdutoExpedicao]:
    """produto_id -> dados de cadastro, numa consulta só. Ids sem cadastro vivo
    ficam de fora, e quem consome assume o padrão (unidade vazia, múltiplo 1).

    Consulta o model inteiro (e não colunas soltas) porque `Produto.marca` é
    `lazy="joined"` e `Produto.codigos_barras_logistica` é `lazy="selectin"`:
    marca e códigos vêm junto, sem uma consulta por item da tela."""
    if not produto_ids:
        return {}
    produtos = (
        sessao_db.query(Produto)
        .filter(Produto.id.in_(produto_ids), Produto.sync_deleted_at.is_(None))
        .all()
    )
    return {
        produto.id: ProdutoExpedicao(
            unidade=produto.unidade or "",
            quantidade_multipla_venda=produto.quantidade_multipla_venda or 1,
            marca_nome=produto.marca.nome if produto.marca else "",
            codigo_barra_notas=produto.codigo_barra_notas,
            codigos_barras_logistica=tuple(
                linha.codigo for linha in produto.codigos_barras_logistica
            ),
            dun_14=produto.dun_14,
        )
        for produto in produtos
    }


def obter_sistema_origem_id(sessao_db: Session, produto_id: str) -> str | None:
    """Código do produto no ERP (`codigo_pro` lá, `sistema_origem_id` aqui).

    Canal de leitura usado pela expedição quando precisa falar do produto com o
    sistema de origem. Devolve None quando o produto nasceu aqui e não tem
    correspondente lá."""
    produto = (
        sessao_db.query(Produto)
        .filter(Produto.id == produto_id, Produto.sync_deleted_at.is_(None))
        .first()
    )
    return produto.sistema_origem_id if produto else None


def _primeiro_ativo_por_coluna(sessao_db: Session, coluna, codigos: list[str]) -> Produto | None:
    """Primeiro produto ativo cuja coluna bate com qualquer um dos códigos.

    Os códigos vêm na ordem de preferência (ver `gs1.codigos_para_buscar`), e a
    ordem é preservada em Python: o `IN` do banco não tem ordem, então filtrar
    por todos de uma vez e escolher aqui é o que garante que o GTIN literal
    ganhe da forma sem zeros à esquerda."""
    produtos = (
        sessao_db.query(Produto)
        .filter(
            coluna.in_(codigos),
            Produto.ativo.is_(True),
            Produto.sync_deleted_at.is_(None),
        )
        .all()
    )
    if not produtos:
        return None
    por_codigo = {getattr(produto, coluna.key): produto for produto in reversed(produtos)}
    for codigo in codigos:
        if codigo in por_codigo:
            return por_codigo[codigo]
    return None


def _primeiro_ativo_por_codigo_logistica(
    sessao_db: Session, codigos: list[str]
) -> Produto | None:
    linhas = (
        sessao_db.query(ProdutoCodigoBarras)
        .join(Produto, Produto.id == ProdutoCodigoBarras.produto_id)
        .filter(
            ProdutoCodigoBarras.codigo.in_(codigos),
            ProdutoCodigoBarras.sync_deleted_at.is_(None),
            Produto.ativo.is_(True),
            Produto.sync_deleted_at.is_(None),
        )
        .all()
    )
    if not linhas:
        return None
    por_codigo = {linha.codigo: linha for linha in reversed(linhas)}
    for codigo in codigos:
        if codigo in por_codigo:
            return sessao_db.get(Produto, por_codigo[codigo].produto_id)
    return None


# Tamanho mínimo para tentar o desempate pelo dígito verificador. Abaixo disso
# "ignorar o último dígito" deixa de ser uma tolerância e vira um curinga: com 4
# dígitos, a base casaria com meio cadastro.
_MINIMO_PARA_IGNORAR_DV = 8


def _base_sem_dv(coluna):
    """A expressão SQL do código sem o último dígito.

    `substr(coluna, 1, length(coluna) - 1)` roda igual no MySQL e no SQLite dos
    testes. Comparar base com base já exige mesmo comprimento — um EAN-13 nunca
    vai casar com um DUN-14 por acidente."""
    return func.substr(coluna, 1, func.length(coluna) - 1)


def _bases_para_buscar(codigos: list[str]) -> list[str]:
    """As bases (código sem o DV) dos candidatos que são numéricos e longos o
    bastante para o desempate fazer sentido. Código interno alfanumérico fica de
    fora: ele não tem dígito verificador para estar errado."""
    bases = [
        codigo[:-1]
        for codigo in codigos
        if codigo.isdigit() and len(codigo) >= _MINIMO_PARA_IGNORAR_DV
    ]
    return list(dict.fromkeys(bases))


def _produtos_por_base(sessao_db: Session, bases: list[str]) -> list[Produto]:
    """Produtos ativos com algum código cuja base bate — nas TRÊS origens.

    Diferente da busca exata, aqui não há ordem de preferência entre as origens:
    o desempate só vale se a resposta for única, e "única" é sobre o produto, não
    sobre onde o código estava. O mesmo produto achado pela nota e pela logística
    continua sendo um só produto."""
    encontrados: dict[str, Produto] = {}

    for coluna in (Produto.codigo_barra_notas, Produto.dun_14):
        produtos = (
            sessao_db.query(Produto)
            .filter(
                coluna.isnot(None),
                _base_sem_dv(coluna).in_(bases),
                Produto.ativo.is_(True),
                Produto.sync_deleted_at.is_(None),
            )
            .all()
        )
        for produto in produtos:
            encontrados[produto.id] = produto

    linhas = (
        sessao_db.query(Produto)
        .join(ProdutoCodigoBarras, ProdutoCodigoBarras.produto_id == Produto.id)
        .filter(
            _base_sem_dv(ProdutoCodigoBarras.codigo).in_(bases),
            ProdutoCodigoBarras.sync_deleted_at.is_(None),
            Produto.ativo.is_(True),
            Produto.sync_deleted_at.is_(None),
        )
        .all()
    )
    for produto in linhas:
        encontrados[produto.id] = produto

    return list(encontrados.values())


def _por_base_ignorando_dv(sessao_db: Session, codigos: list[str]) -> Produto | None:
    """Último recurso da bipagem: casar ignorando o dígito verificador, e só se
    a resposta for uma só.

    **Por que isso existe.** Acontece de a embalagem trazer um EAN com o dígito
    verificador errado — falha de impressão do fabricante — enquanto a nota
    fiscal traz o dígito certo. A NF-e não tem escolha: a SEFAZ valida o DV do
    campo `cEAN` e rejeita o documento se ele não fechar, então o faturamento
    emite com o dígito correto. O caixote na mão do operador continua com o
    errado. Caso real no cadastro: SONDA FOLEY 2 VIAS LÁTEX Nº 18 30ML, nota
    6936877313056 e embalagem 6936877313053 — mesmos 12 primeiros dígitos, mesmo
    fabricante, mesmo produto, DV divergente.

    **Por que exigir resposta única.** Ignorar o DV é abrir mão de um dígito de
    conferência, e dois produtos diferentes podem compartilhar a mesma base. Se
    mais de um cadastro responde, a leitura é ambígua e a bipagem RECUSA — errar
    o produto na conferência é pior que pedir para o operador conferir o
    cadastro. Não existe "escolhe o primeiro" aqui, ao contrário da busca exata.
    """
    bases = _bases_para_buscar(codigos)
    if not bases:
        return None

    produtos = _produtos_por_base(sessao_db, bases)
    return produtos[0] if len(produtos) == 1 else None


def obter_por_codigo_barras(sessao_db: Session, leitura: str) -> ProdutoBipagem | None:
    """Canal usado pela expedição a cada bipagem no coletor: recebe o que o
    leitor mandou, devolve o produto (ou None se não houver cadastro).

    **Antes de procurar, decide o que foi lido.** Código de barras linear é o
    código em si; QR Code / DataMatrix GS1 é um pacote de campos, e o produto
    está no AI `01` — o GTIN de 14 posições, que precisa ser extraído antes de
    qualquer consulta. Quem faz essa leitura é `shared/gs1.py`; aqui só chega a
    lista de códigos a procurar.

    A ordem da busca é: **código de barras da nota → códigos de logística →
    DUN-14.** Ela reflete o que é mais provável estar na mão do operador, e é
    fixa de propósito: um mesmo número achado em dois lugares tem que resolver
    sempre para o mesmo produto, independente da hora do dia.

    Nenhum dos campos é único (ver produto_model.py): havendo mais de um
    cadastro com o mesmo número, o primeiro ativo resolve.

    **Só depois de as três falharem** entra o desempate pelo dígito verificador
    (`_por_base_ignorando_dv`), que casa ignorando o último dígito e exige
    resposta única. É deliberadamente o último passo: enquanto existir um
    cadastro que bate exatamente, é ele que vale.

    O passo a passo completo, com os porquês, está em
    `app/domains/expedicao/README.md`.
    """
    codigos = gs1.codigos_para_buscar(leitura)
    if not codigos:
        return None

    produto = _primeiro_ativo_por_coluna(sessao_db, Produto.codigo_barra_notas, codigos)
    if produto is None:
        produto = _primeiro_ativo_por_codigo_logistica(sessao_db, codigos)
    if produto is None:
        produto = _primeiro_ativo_por_coluna(sessao_db, Produto.dun_14, codigos)
    if produto is None:
        produto = _por_base_ignorando_dv(sessao_db, codigos)
    if produto is None:
        return None
    return ProdutoBipagem(
        id=produto.id, quantidade_multipla_venda=produto.quantidade_multipla_venda or 1
    )
