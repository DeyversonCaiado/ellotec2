from datetime import date, datetime, time

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, noload, undefer

from app.domains.empresas import empresa_publico
from app.domains.notas_fiscais.nota_fiscal_contrato import (
    ItemNotaFiscalEntradaSchema,
    NotaFiscalAtualizarSchema,
    NotaFiscalBaseSchema,
    NotaFiscalCriarSchema,
)
from app.domains.notas_fiscais.nota_fiscal_model import NotaFiscal, NotaFiscalItem
from app.shared.sync_helpers import incrementar_versao, marcar_apagado

# Fechada de propósito: `sort` vem da query string, e interpolar isso num
# ORDER BY seria injeção. Mesmo padrão de pedido_service.listar_paginado.
_COLUNAS_ORDENAVEIS = {
    "data_emissao": NotaFiscal.data_emissao,
    "numero": NotaFiscal.numero,
    "valor_total": NotaFiscal.valor_total,
    # Sem `sync_created_at`/`sync_updated_at` aqui: ordenar a lista por eles
    # seria usar auditoria da linha como regra de negócio, o que o
    # ARCHITECTURE.md proíbe. A ordem de uma lista de documentos fiscais é por
    # data de EMISSÃO — um reprocessamento da integração não pode reorganizar a
    # tela sem que nada tenha acontecido no negócio.
}


def listar_paginado(
    sessao_db: Session,
    page: int,
    per_page: int,
    sort: str,
    sort_type: str,
    q: str | None = None,
    tipo_operacao: str | None = None,
    empresa_id: str | None = None,
    modelo: str | None = None,
    status_nota: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> tuple[list[NotaFiscal], int]:
    """Uma página de notas. Todo filtro é resolvido AQUI, no banco, sobre a
    base inteira — nunca sobre a página já carregada: filtrar no front daria
    resultado diferente conforme a página aberta, o que é simplesmente errado.
    """
    coluna = _COLUNAS_ORDENAVEIS.get(sort)
    if coluna is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Campo de ordenação inválido. Use data_emissao, numero ou valor_total.",
        )

    ordenacao = coluna.desc() if sort_type.lower() == "desc" else coluna.asc()
    consulta_base = (
        sessao_db.query(NotaFiscal)
        .filter(NotaFiscal.sync_deleted_at.is_(None))
        # `NotaFiscal.itens` é lazy="selectin": sem o noload, uma página de 20
        # notas dispararia o SELECT de todos os itens de todas elas — centenas
        # de linhas que a listagem nem mostra (ela devolve NotaFiscalResumoSchema).
        .options(noload(NotaFiscal.itens))
    )

    if tipo_operacao:
        consulta_base = consulta_base.filter(NotaFiscal.tipo_operacao == tipo_operacao)
    if empresa_id:
        consulta_base = consulta_base.filter(NotaFiscal.empresa_id == empresa_id)
    if modelo:
        consulta_base = consulta_base.filter(NotaFiscal.modelo == modelo)
    if status_nota:
        consulta_base = consulta_base.filter(NotaFiscal.status == status_nota)

    # O período se refere sempre à data de EMISSÃO — a data de negócio do
    # documento —, nunca a sync_updated_at, que é campo de auditoria e muda
    # quando um reprocessamento toca a linha.
    if data_inicio:
        consulta_base = consulta_base.filter(
            NotaFiscal.data_emissao >= datetime.combine(data_inicio, time.min)
        )
    if data_fim:
        # `time.max` e não `<= data_fim`: data_emissao é DateTime, e comparar
        # com a data pura excluiria tudo que foi emitido depois da meia-noite
        # do último dia — ou seja, o dia inteiro.
        consulta_base = consulta_base.filter(
            NotaFiscal.data_emissao <= datetime.combine(data_fim, time.max)
        )

    q = (q or "").strip()
    if q:
        termo = f"%{q}%"
        consulta_base = consulta_base.filter(
            or_(
                NotaFiscal.numero.ilike(termo),
                NotaFiscal.chave_acesso.ilike(termo),
                NotaFiscal.emitente_razao_social.ilike(termo),
                NotaFiscal.emitente_cnpj_cpf.ilike(termo),
                NotaFiscal.destinatario_razao_social.ilike(termo),
                NotaFiscal.destinatario_cnpj_cpf.ilike(termo),
                NotaFiscal.sistema_origem_id.ilike(termo),
            )
        )

    total = consulta_base.count()
    itens = (
        # Desempate por id: sem ele, duas páginas podem repetir ou pular uma
        # linha quando várias têm o mesmo valor na coluna ordenada.
        consulta_base.order_by(ordenacao, NotaFiscal.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return itens, total


def obter_por_id(sessao_db: Session, nota_id: str) -> NotaFiscal:
    nota = (
        sessao_db.query(NotaFiscal)
        .filter(NotaFiscal.id == nota_id, NotaFiscal.sync_deleted_at.is_(None))
        .first()
    )
    if nota is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Nota fiscal não encontrada."
        )
    return nota


def obter_com_xml(sessao_db: Session, nota_id: str) -> NotaFiscal:
    """`xml_original` é `deferred` no model — não vem em nenhum SELECT normal.
    Esta é a única função que pede a coluna explicitamente."""
    nota = (
        sessao_db.query(NotaFiscal)
        .options(undefer(NotaFiscal.xml_original), noload(NotaFiscal.itens))
        .filter(NotaFiscal.id == nota_id, NotaFiscal.sync_deleted_at.is_(None))
        .first()
    )
    if nota is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Nota fiscal não encontrada."
        )
    return nota


def obter_por_chave_acesso(
    sessao_db: Session, chave_acesso: str, empresa_id: str | None = None
) -> NotaFiscal:
    """A chave é única na SEFAZ, mas nesta tabela a unicidade é por empresa
    (ver UniqueConstraint em nota_fiscal_model.py) — a mesma nota pode estar
    guardada por duas filiais. Sem a empresa, ambiguidade é erro explícito, e
    não escolha arbitrária: devolver a linha da filial errada em silêncio faria
    o UPDATE seguinte colidir com a linha certa, num 409 sem causa aparente.
    Mesmo raciocínio de `pedido_service.obter_por_sistema_origem_id`.
    """
    consulta = sessao_db.query(NotaFiscal).filter(
        NotaFiscal.chave_acesso == chave_acesso, NotaFiscal.sync_deleted_at.is_(None)
    )
    if empresa_id:
        consulta = consulta.filter(NotaFiscal.empresa_id == empresa_id)

    # limit(2) basta: só interessa saber se há mais de um.
    encontrados = consulta.limit(2).all()

    if not encontrados:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Nota fiscal não encontrada."
        )
    if len(encontrados) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A chave de acesso '{chave_acesso}' existe em mais de uma empresa. "
                "Informe empresaId ou empresaSistemaOrigemId para identificar a nota."
            ),
        )
    return encontrados[0]


def resolver_empresa(
    sessao_db: Session, empresa_id: str | None, empresa_sistema_origem_id: str | None
) -> str | None:
    """Traduz o par (id, sistema de origem) da empresa num id, ou None se
    nenhum dos dois veio. Usado pelas rotas de GET, que não têm corpo."""
    if empresa_sistema_origem_id:
        resolvido = empresa_publico.obter_id_por_sistema_origem_id(
            sessao_db, empresa_sistema_origem_id
        )
        if resolvido is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Empresa com sistemaOrigemId '{empresa_sistema_origem_id}' não encontrada.",
            )
        return resolvido
    return empresa_id


def _resolver_empresa_id(
    sessao_db: Session, dados: NotaFiscalCriarSchema | NotaFiscalAtualizarSchema
) -> str:
    if dados.empresa_sistema_origem_id:
        empresa_id = empresa_publico.obter_id_por_sistema_origem_id(
            sessao_db, dados.empresa_sistema_origem_id
        )
        if empresa_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Empresa não encontrada para o sistema de origem informado.",
            )
        return empresa_id

    return dados.empresa_id


def _validar_documento_disponivel(
    sessao_db: Session,
    dados: NotaFiscalCriarSchema | NotaFiscalAtualizarSchema,
    empresa_id: str,
    ignorar_id: str | None = None,
) -> None:
    """Antecipa as duas constraints de unicidade da tabela para devolver 409
    com mensagem legível, em vez do 422 genérico do handler de IntegrityError.

    Importar a mesma nota duas vezes é o erro mais comum de integração fiscal
    (o job roda de novo, o XML é reenviado), então vale a query a mais.
    """
    if dados.chave_acesso:
        consulta = sessao_db.query(NotaFiscal).filter(
            NotaFiscal.chave_acesso == dados.chave_acesso,
            NotaFiscal.empresa_id == empresa_id,
            NotaFiscal.sync_deleted_at.is_(None),
        )
        if ignorar_id:
            consulta = consulta.filter(NotaFiscal.id != ignorar_id)
        if consulta.first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe uma nota com essa chave de acesso para essa empresa.",
            )

    # A chave natural do documento — é ela que pega a duplicata quando não há
    # chave de acesso (NFS-e).
    consulta = sessao_db.query(NotaFiscal).filter(
        NotaFiscal.empresa_id == empresa_id,
        NotaFiscal.modelo == dados.modelo,
        NotaFiscal.serie == dados.serie,
        NotaFiscal.numero == dados.numero,
        NotaFiscal.emitente_cnpj_cpf == dados.emitente_cnpj_cpf,
        NotaFiscal.sync_deleted_at.is_(None),
    )
    if ignorar_id:
        consulta = consulta.filter(NotaFiscal.id != ignorar_id)
    if consulta.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Já existe uma nota com esse modelo, série, número e emitente "
                "para essa empresa."
            ),
        )


def _montar_itens(itens_entrada: list[ItemNotaFiscalEntradaSchema]) -> list[NotaFiscalItem]:
    """Grava cada item exatamente como veio no documento. O cadastro de
    produtos NÃO é consultado: código e descrição são snapshot do que estava
    impresso na nota, e `produto_id`, quando informado, é validado pela FK no
    INSERT — não por uma query redundante aqui (ver "Validação de id por
    foreign key" no ARCHITECTURE.md)."""
    return [
        NotaFiscalItem(
            numero_item=item.numero_item,
            produto_id=item.produto_id,
            produto_codigo=item.produto_codigo,
            produto_descricao=item.produto_descricao,
            codigo_barras=item.codigo_barras,
            ncm=item.ncm,
            cfop=item.cfop,
            unidade=item.unidade,
            quantidade=item.quantidade,
            preco_unitario=item.preco_unitario,
            valor_total_item=item.valor_total_item,
            valor_frete=item.valor_frete,
            valor_desconto=item.valor_desconto,
            cst_icms=item.cst_icms,
            aliquota_icms=item.aliquota_icms,
            valor_icms=item.valor_icms,
            valor_icms_st=item.valor_icms_st,
            cst_ipi=item.cst_ipi,
            aliquota_ipi=item.aliquota_ipi,
            valor_ipi=item.valor_ipi,
            lote=item.lote,
            validade=item.validade,
            informacoes_adicionais=item.informacoes_adicionais,
        )
        for item in itens_entrada
    ]


def _aplicar_campos(nota: NotaFiscal, dados: NotaFiscalBaseSchema, empresa_id: str) -> None:
    """Copia a capa do contrato para o model. Existe para que criar() e
    atualizar() não repitam 40 atribuições e divirjam com o tempo."""
    nota.empresa_id = empresa_id
    nota.pedido_id = dados.pedido_id
    nota.modelo = dados.modelo
    nota.tipo_operacao = dados.tipo_operacao
    nota.finalidade = dados.finalidade
    nota.chave_acesso = dados.chave_acesso
    nota.numero = dados.numero
    nota.serie = dados.serie
    nota.natureza_operacao = dados.natureza_operacao
    nota.data_emissao = dados.data_emissao
    nota.data_saida_entrada = dados.data_saida_entrada
    nota.status = dados.status
    nota.protocolo_autorizacao = dados.protocolo_autorizacao
    nota.data_autorizacao = dados.data_autorizacao

    nota.emitente_cnpj_cpf = dados.emitente_cnpj_cpf
    nota.emitente_razao_social = dados.emitente_razao_social
    nota.emitente_nome_fantasia = dados.emitente_nome_fantasia
    nota.emitente_inscricao_estadual = dados.emitente_inscricao_estadual
    nota.emitente_municipio = dados.emitente_municipio
    nota.emitente_uf = dados.emitente_uf

    nota.destinatario_cnpj_cpf = dados.destinatario_cnpj_cpf
    nota.destinatario_razao_social = dados.destinatario_razao_social
    nota.destinatario_inscricao_estadual = dados.destinatario_inscricao_estadual
    nota.destinatario_municipio = dados.destinatario_municipio
    nota.destinatario_uf = dados.destinatario_uf

    nota.valor_produtos = dados.valor_produtos
    nota.valor_frete = dados.valor_frete
    nota.valor_seguro = dados.valor_seguro
    nota.valor_desconto = dados.valor_desconto
    nota.valor_outras_despesas = dados.valor_outras_despesas
    nota.valor_icms = dados.valor_icms
    nota.valor_ipi = dados.valor_ipi
    nota.valor_total = dados.valor_total

    nota.transportadora_nome = dados.transportadora_nome
    nota.transportadora_cnpj_cpf = dados.transportadora_cnpj_cpf
    nota.modalidade_frete = dados.modalidade_frete
    nota.quantidade_volumes = dados.quantidade_volumes
    nota.peso_bruto = dados.peso_bruto
    nota.peso_liquido = dados.peso_liquido

    nota.sistema_origem_id = dados.sistema_origem_id
    nota.informacoes_complementares = dados.informacoes_complementares
    # O XML só é sobrescrito quando vier preenchido: uma correção de capa
    # enviada sem o XML não pode APAGAR o documento original, que é o que a
    # legislação obriga a guardar por 5 anos.
    if dados.xml_original:
        nota.xml_original = dados.xml_original


def criar(sessao_db: Session, dados: NotaFiscalCriarSchema) -> NotaFiscal:
    empresa_id = _resolver_empresa_id(sessao_db, dados)
    _validar_documento_disponivel(sessao_db, dados, empresa_id)

    # A capa e os itens vão num único commit: `NotaFiscal.itens` tem
    # cascade="all, delete-orphan", então o SQLAlchemy inclui os INSERTs dos
    # itens no mesmo flush. Se qualquer item violar uma FK, o commit inteiro
    # falha e NADA fica persistido — nem a capa, nem metade dos itens.
    nota = NotaFiscal()
    _aplicar_campos(nota, dados, empresa_id)
    nota.itens = _montar_itens(dados.itens)

    sessao_db.add(nota)
    sessao_db.commit()
    sessao_db.refresh(nota)
    return nota


def atualizar(
    sessao_db: Session,
    nota_id: str,
    dados: NotaFiscalAtualizarSchema,
    chave_acesso: str | None = None,
) -> NotaFiscal:
    # A empresa é resolvida ANTES de localizar a nota: é ela que desambigua a
    # chave de acesso, que sozinha pode apontar para a cópia de outra filial.
    empresa_id = _resolver_empresa_id(sessao_db, dados)

    nota = (
        obter_por_chave_acesso(sessao_db, chave_acesso, empresa_id)
        if chave_acesso
        else obter_por_id(sessao_db, nota_id)
    )

    _validar_documento_disponivel(sessao_db, dados, empresa_id, ignorar_id=nota.id)
    _aplicar_campos(nota, dados, empresa_id)
    incrementar_versao(nota)

    for item_antigo in list(nota.itens):
        sessao_db.delete(item_antigo)
    # O flush é obrigatório AQUI, e não é detalhe de performance: sem ele o
    # SQLAlchemy emite os INSERTs dos itens novos antes dos DELETEs dos
    # antigos, e a constraint `uq_nota_fiscal_itens_numero` recusa a
    # atualização inteira — reenviar a mesma nota corrigida falharia sempre,
    # porque o item 1 novo esbarra no item 1 velho que ainda não foi apagado.
    sessao_db.flush()
    nota.itens = _montar_itens(dados.itens)

    sessao_db.commit()
    sessao_db.refresh(nota)
    return nota


def apagar(sessao_db: Session, nota_id: str) -> None:
    nota = obter_por_id(sessao_db, nota_id)
    marcar_apagado(nota)
    sessao_db.commit()
