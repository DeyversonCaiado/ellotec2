from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from dataclasses import dataclass

from app.domains.marcas import marca_publico
from app.domains.produtos.produto_model import Produto, ProdutoCodigoBarras
from app.domains.produtos.produto_contrato import ProdutoAtualizarSchema, ProdutoCriarSchema
from app.shared import tabela_cmed
from app.shared.sync_helpers import incrementar_versao, marcar_apagado

# Campos do contrato que não são coluna de `produtos` — cada um tem tratamento
# próprio no criar/atualizar e por isso sai do `model_dump` que alimenta o model.
_CAMPOS_FORA_DA_TABELA = {"marca_sistema_origem_id", "codigos_barras_logistica"}


def listar_paginado(
    sessao_db: Session,
    page: int,
    per_page: int,
    sort: str,
    sort_type: str,
    q: str | None = None,
) -> tuple[list[Produto], int]:
    colunas_permitidas = {
        "sync_created_at": Produto.sync_created_at,
        "sync_updated_at": Produto.sync_updated_at,
        "codigo": Produto.codigo,
        "descricao": Produto.descricao,
    }

    coluna = colunas_permitidas.get(sort)
    if coluna is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Campo de ordenação inválido. Use sync_created_at, sync_updated_at, codigo ou descricao.",
        )

    ordenacao = coluna.desc() if sort_type.lower() == "desc" else coluna.asc()
    consulta_base = sessao_db.query(Produto).filter(Produto.sync_deleted_at.is_(None))

    q = (q or "").strip()
    if q:
        termo = f"%{q}%"
        consulta_base = consulta_base.filter(or_(Produto.descricao.ilike(termo), Produto.codigo.ilike(termo)))

    total = consulta_base.count()
    itens = (
        consulta_base.order_by(ordenacao, Produto.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return itens, total


def obter_por_id(sessao_db: Session, produto_id: str) -> Produto:
    produto = (
        sessao_db.query(Produto)
        .filter(Produto.id == produto_id, Produto.sync_deleted_at.is_(None))
        .first()
    )
    if produto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado.")
    return produto


def obter_por_sistema_origem_id(sessao_db: Session, sistema_origem_id: str) -> Produto:
    produto = (
        sessao_db.query(Produto)
        .filter(Produto.sistema_origem_id == sistema_origem_id, Produto.sync_deleted_at.is_(None))
        .first()
    )
    if produto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado.")
    return produto


def _validar_codigo_disponivel(sessao_db: Session, codigo: str, ignorar_id: str | None = None) -> None:
    consulta = sessao_db.query(Produto).filter(Produto.codigo == codigo, Produto.sync_deleted_at.is_(None))
    if ignorar_id:
        consulta = consulta.filter(Produto.id != ignorar_id)
    if consulta.first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Já existe um produto com esse código.")


def _validar_sistema_origem_disponivel(
    sessao_db: Session, sistema_origem_id: str | None, ignorar_id: str | None = None
) -> None:
    if not sistema_origem_id:
        return

    consulta = sessao_db.query(Produto).filter(
        Produto.sistema_origem_id == sistema_origem_id, Produto.sync_deleted_at.is_(None)
    )
    if ignorar_id:
        consulta = consulta.filter(Produto.id != ignorar_id)
    if consulta.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Já existe um produto com esse sistema de origem."
        )


def _resolver_marca_id(sessao_db: Session, dados: ProdutoCriarSchema | ProdutoAtualizarSchema) -> str:
    if dados.marca_sistema_origem_id:
        marca_id = marca_publico.obter_id_por_sistema_origem_id(sessao_db, dados.marca_sistema_origem_id)
        if marca_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Marca não encontrada para o sistema de origem informado.",
            )
        return marca_id

    return dados.marca_id


def _sincronizar_codigos_logistica(
    sessao_db: Session, produto_id: str, codigos: list[str]
) -> None:
    """Recalcula o diff entre o que está gravado e o conjunto que veio no
    contrato: insere o que falta, apaga (soft) o que sobra, não toca no que já
    está igual.

    Mesmo padrão de `usuario_service._sincronizar_permissoes`. Apagar e reinserir
    tudo seria mais curto, mas trocaria o id e a data de criação de códigos que
    não mudaram — e é por essa data que se descobre depois quando um código
    entrou no cadastro.
    """
    linhas = (
        sessao_db.query(ProdutoCodigoBarras)
        .filter(
            ProdutoCodigoBarras.produto_id == produto_id,
            ProdutoCodigoBarras.sync_deleted_at.is_(None),
        )
        .all()
    )
    desejados = set(codigos)
    atuais = {linha.codigo for linha in linhas}

    for linha in linhas:
        if linha.codigo not in desejados:
            marcar_apagado(linha)

    for codigo in codigos:
        if codigo not in atuais:
            sessao_db.add(ProdutoCodigoBarras(produto_id=produto_id, codigo=codigo))


def criar(sessao_db: Session, dados: ProdutoCriarSchema) -> Produto:
    _validar_codigo_disponivel(sessao_db, dados.codigo)
    _validar_sistema_origem_disponivel(sessao_db, dados.sistema_origem_id)

    campos = dados.model_dump(exclude=_CAMPOS_FORA_DA_TABELA)
    campos["marca_id"] = _resolver_marca_id(sessao_db, dados)

    produto = Produto(**campos)
    sessao_db.add(produto)
    sessao_db.flush()
    _sincronizar_codigos_logistica(sessao_db, produto.id, dados.codigos_barras_logistica)
    sessao_db.commit()
    sessao_db.refresh(produto)
    return produto


def atualizar(
    sessao_db: Session,
    produto_id: str,
    dados: ProdutoAtualizarSchema,
    sistema_origem_id: str | None = None,
) -> Produto:
    produto = (
        obter_por_sistema_origem_id(sessao_db, sistema_origem_id)
        if sistema_origem_id
        else obter_por_id(sessao_db, produto_id)
    )
    _validar_codigo_disponivel(sessao_db, dados.codigo, ignorar_id=produto.id)

    campos = dados.model_dump(exclude=_CAMPOS_FORA_DA_TABELA)
    campos["marca_id"] = _resolver_marca_id(sessao_db, dados)
    # Preserva o sistema_origem_id usado para localizar o registro quando o
    # corpo da requisição não o repetir — ver mesmo comentário em clientes.
    campos["sistema_origem_id"] = campos.get("sistema_origem_id") or sistema_origem_id
    _validar_sistema_origem_disponivel(sessao_db, campos["sistema_origem_id"], ignorar_id=produto.id)

    for campo, valor in campos.items():
        setattr(produto, campo, valor)
    incrementar_versao(produto)
    _sincronizar_codigos_logistica(sessao_db, produto.id, dados.codigos_barras_logistica)

    sessao_db.commit()
    sessao_db.refresh(produto)
    return produto


def apagar(sessao_db: Session, produto_id: str) -> None:
    produto = obter_por_id(sessao_db, produto_id)
    marcar_apagado(produto)
    # Os códigos de logística morrem junto: são linhas do produto, não cadastro
    # próprio. Deixá-los vivos faria a bipagem achar um produto apagado.
    _sincronizar_codigos_logistica(sessao_db, produto.id, [])
    sessao_db.commit()


# ---------------------------------------------------------------------------
# Vincular os códigos de barras que a CMED publica para o registro ANVISA
#
# O caso: o operador bipa a caixa, o código não está no cadastro, mas o produto
# é um medicamento registrado. A CMED publica até três EANs por apresentação, e
# um deles costuma ser exatamente o que está impresso na caixa. Em vez de mandar
# o operador cadastrar à mão (com a caixa na mão, no meio da contagem), o
# sistema consulta a fonte oficial e vincula.
#
# A operação é deliberadamente estreita — ver `vincular_codigos_da_anvisa`.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConflitoDeCodigo:
    """Um EAN da CMED que já pertence a OUTRO produto do cadastro."""

    codigo: str
    produto_id: str
    produto_codigo: str
    produto_descricao: str


@dataclass(frozen=True)
class ResultadoAnvisa:
    """O que aconteceu na verificação. `vinculados` só vem preenchido no
    sucesso; nos demais casos a lista é vazia e `motivo` diz por quê."""

    situacao: str  # vinculado | sem_registro | registro_nao_encontrado | codigo_nao_confere | conflito
    mensagem: str
    vinculados: tuple[str, ...] = ()
    conflitos: tuple[ConflitoDeCodigo, ...] = ()


def _conflitos_de(
    sessao_db: Session, produto_id: str, codigos: list[str]
) -> list[ConflitoDeCodigo]:
    """Códigos que já estão em OUTRO produto — em qualquer das três origens.

    Inclui produto inativo de propósito: inativo hoje pode ser reativado
    amanhã, e o conflito continuaria lá. A checagem é sobre o cadastro existir,
    não sobre ele estar em uso."""
    conflitos: dict[str, ConflitoDeCodigo] = {}

    def registrar(codigo: str, produto: Produto) -> None:
        if produto.id == produto_id or codigo in conflitos:
            return
        conflitos[codigo] = ConflitoDeCodigo(
            codigo=codigo,
            produto_id=produto.id,
            produto_codigo=produto.codigo,
            produto_descricao=produto.descricao,
        )

    for coluna in (Produto.codigo_barra_notas, Produto.dun_14):
        for produto in (
            sessao_db.query(Produto)
            .filter(coluna.in_(codigos), Produto.sync_deleted_at.is_(None))
            .all()
        ):
            registrar(getattr(produto, coluna.key), produto)

    for linha, produto in (
        sessao_db.query(ProdutoCodigoBarras, Produto)
        .join(Produto, Produto.id == ProdutoCodigoBarras.produto_id)
        .filter(
            ProdutoCodigoBarras.codigo.in_(codigos),
            ProdutoCodigoBarras.sync_deleted_at.is_(None),
            Produto.sync_deleted_at.is_(None),
        )
        .all()
    ):
        registrar(linha.codigo, produto)

    return list(conflitos.values())


def vincular_codigos_da_anvisa(
    sessao_db: Session, produto_id: str, leitura: str
) -> ResultadoAnvisa:
    """Confere o código bipado contra a CMED e, batendo, vincula os EANs de lá.

    A sequência, e por que cada passo existe:

    1. **O produto tem registro ANVISA?** Sem ele não há o que consultar. Não é
       erro: a maior parte do catálogo é correlato, não medicamento registrado.
    2. **O registro existe na CMED?** Registro digitado errado no cadastro, ou
       produto que saiu da lista, param aqui.
    3. **O código bipado está entre os EANs daquele registro?** Esta é a trava
       principal. Sem ela a função viraria "importe os códigos da CMED para este
       produto", que é outra coisa — e que aceitaria vincular um produto ao
       registro errado sem ninguém perceber. O que autoriza a escrita é a caixa
       na mão do operador concordar com a fonte oficial.
    4. **Algum desses códigos já é de outro produto?** Se sim, **nada é
       gravado** — nem os que não conflitam. Vincular metade deixaria o cadastro
       num estado que ninguém pediu e que é pior de desfazer do que de refazer.
       Duas apresentações compartilhando EAN é sinal de cadastro errado em algum
       dos dois, e isso é decisão de gente, não de rotina automática.

    Só depois disso os códigos entram como códigos de logística do produto.

    O que **não** é gravado: nada em `codigo_barra_notas` (é espelho do ERP,
    quem escreve lá é a integração) e nada em `dun_14` (a CMED publica EAN de
    apresentação, não DUN de caixa de despacho).
    """
    produto = obter_por_id(sessao_db, produto_id)

    registro = tabela_cmed.normalizar_registro(produto.registro_anvisa)
    if not registro:
        return ResultadoAnvisa(
            situacao="sem_registro",
            mensagem="Este produto não tem registro ANVISA no cadastro, então não há o que consultar na CMED.",
        )

    apresentacoes = tabela_cmed.buscar_por_registro(sessao_db, registro)
    if not apresentacoes:
        return ResultadoAnvisa(
            situacao="registro_nao_encontrado",
            mensagem=f"O registro {registro} não foi encontrado na tabela da CMED.",
        )

    lido = tabela_cmed.normalizar_registro(leitura)
    # `dict.fromkeys` em vez de set: preserva a ordem em que a CMED publica, que
    # é a ordem em que os códigos aparecem para o usuário depois.
    eans = list(dict.fromkeys(ean for linha in apresentacoes for ean in linha.eans))

    if lido not in eans:
        return ResultadoAnvisa(
            situacao="codigo_nao_confere",
            mensagem=(
                f"O código lido não está entre os da CMED para o registro {registro}. "
                f"Códigos publicados: {', '.join(eans)}."
            ),
        )

    conflitos = _conflitos_de(sessao_db, produto.id, eans)
    if conflitos:
        detalhe = "; ".join(
            f"{conflito.codigo} já é do produto {conflito.produto_codigo} — {conflito.produto_descricao}"
            for conflito in conflitos
        )
        return ResultadoAnvisa(
            situacao="conflito",
            mensagem=(
                "Nada foi alterado: um ou mais códigos da CMED já pertencem a outro "
                f"produto. {detalhe}."
            ),
            conflitos=tuple(conflitos),
        )

    ja_existentes = {
        linha.codigo
        for linha in sessao_db.query(ProdutoCodigoBarras)
        .filter(
            ProdutoCodigoBarras.produto_id == produto.id,
            ProdutoCodigoBarras.sync_deleted_at.is_(None),
        )
        .all()
    }
    novos = [ean for ean in eans if ean not in ja_existentes]
    for codigo in novos:
        sessao_db.add(ProdutoCodigoBarras(produto_id=produto.id, codigo=codigo))

    if novos:
        incrementar_versao(produto)

    # SEM linha de histórico, e isso é uma lacuna conhecida, não um esquecimento:
    # `historico.empresa_id` é NOT NULL com FK, e este endpoint é do domínio de
    # produtos — não existe uma empresa natural aqui, ao contrário da expedição,
    # que sempre fala de um pedido. Enquanto isso, o rastro é a própria linha em
    # `produto_codigo_barras`, que carrega `sync_created_at`.

    sessao_db.commit()
    return ResultadoAnvisa(
        situacao="vinculado",
        mensagem=(
            f"{len(novos)} código(s) da CMED vinculados ao produto."
            if novos
            else "Os códigos da CMED já estavam no cadastro deste produto."
        ),
        vinculados=tuple(novos),
    )
