from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth.seguranca import gerar_hash_senha
from app.domains.usuarios.usuario_model import Usuario, UsuarioPermissao
from app.domains.usuarios.usuario_contrato import UsuarioAtualizarSchema, UsuarioCriarSchema
from app.shared.sync_helpers import incrementar_versao, marcar_apagado
from app.shared.vinculo_origem import resolver as resolver_vinculo_origem


def listar(sessao_db: Session) -> list[Usuario]:
    return (
        sessao_db.query(Usuario)
        .filter(Usuario.sync_deleted_at.is_(None))
        .order_by(Usuario.nome)
        .all()
    )


def listar_resumo(sessao_db: Session) -> list[Usuario]:
    """Só usuários ativos — usado pelo canal leve (UsuarioResumoSchema) que
    outros domínios consomem sem precisar de usuarios.acessar."""
    return (
        sessao_db.query(Usuario)
        .filter(Usuario.sync_deleted_at.is_(None), Usuario.ativo.is_(True))
        .order_by(Usuario.nome)
        .all()
    )


def listar_paginado(
    sessao_db: Session,
    page: int,
    per_page: int,
    sort: str,
    sort_type: str,
    busca: str | None = None,
) -> tuple[list[Usuario], int]:
    colunas_permitidas = {
        "sync_created_at": Usuario.sync_created_at,
        "sync_updated_at": Usuario.sync_updated_at,
        "nome": Usuario.nome,
        "email": Usuario.email,
        "usuario": Usuario.usuario,
    }

    coluna = colunas_permitidas.get(sort)
    if coluna is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Campo de ordenação inválido. Use sync_created_at, sync_updated_at, nome, email ou usuario.",
        )

    ordenacao = coluna.desc() if sort_type.lower() == "desc" else coluna.asc()
    consulta_base = sessao_db.query(Usuario).filter(Usuario.sync_deleted_at.is_(None))

    busca = (busca or "").strip()
    if busca:
        termo = f"%{busca}%"
        consulta_base = consulta_base.filter(
            (Usuario.nome.ilike(termo)) | (Usuario.email.ilike(termo)) | (Usuario.usuario.ilike(termo))
        )

    total = consulta_base.count()
    itens = (
        consulta_base.order_by(ordenacao, Usuario.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return itens, total


def obter_por_id(sessao_db: Session, usuario_id: str) -> Usuario:
    usuario = (
        sessao_db.query(Usuario)
        .filter(Usuario.id == usuario_id, Usuario.sync_deleted_at.is_(None))
        .first()
    )
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    return usuario


def _validar_email_disponivel(sessao_db: Session, email: str, ignorar_id: str | None = None) -> None:
    consulta = sessao_db.query(Usuario).filter(Usuario.email == email, Usuario.sync_deleted_at.is_(None))
    if ignorar_id:
        consulta = consulta.filter(Usuario.id != ignorar_id)
    if consulta.first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Já existe um usuário com esse e-mail.")


def _validar_usuario_disponivel(sessao_db: Session, usuario: str, ignorar_id: str | None = None) -> None:
    consulta = sessao_db.query(Usuario).filter(Usuario.usuario == usuario, Usuario.sync_deleted_at.is_(None))
    if ignorar_id:
        consulta = consulta.filter(Usuario.id != ignorar_id)
    if consulta.first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Já existe um usuário com esse nome de usuário.")


def _validar_sistema_origem_disponivel(
    sessao_db: Session, sistema_origem_id: str | None, ignorar_id: str | None = None
) -> None:
    if not sistema_origem_id:
        return

    consulta = (
        sessao_db.query(Usuario)
        .filter(Usuario.sistema_origem_id == sistema_origem_id, Usuario.sync_deleted_at.is_(None))
    )
    if ignorar_id:
        consulta = consulta.filter(Usuario.id != ignorar_id)
    if consulta.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Já existe um usuário com esse sistema de origem."
        )


def obter_por_sistema_origem_id(sessao_db: Session, sistema_origem_id: str) -> Usuario:
    usuario = (
        sessao_db.query(Usuario)
        .filter(Usuario.sistema_origem_id == sistema_origem_id, Usuario.sync_deleted_at.is_(None))
        .first()
    )
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    return usuario


def _sincronizar_permissoes(sessao_db: Session, usuario: Usuario, chaves: list[str]) -> None:
    """Substitui as linhas de UsuarioPermissao do usuário pelo conjunto de
    chaves enviado: apaga as que saíram, adiciona as que entraram. O volume
    é sempre pequeno (dezenas de chaves no máximo), então recalcular o
    conjunto inteiro é mais simples e robusto que um diff incremental."""
    chaves_novas = set(chaves)
    existentes = {p.chave: p for p in usuario.permissoes}

    for chave, registro in list(existentes.items()):
        if chave not in chaves_novas:
            usuario.permissoes.remove(registro)
            sessao_db.delete(registro)

    for chave in chaves_novas - existentes.keys():
        registro = UsuarioPermissao(usuario_id=usuario.id, chave=chave)
        sessao_db.add(registro)
        usuario.permissoes.append(registro)


def criar(sessao_db: Session, dados: UsuarioCriarSchema) -> Usuario:
    _validar_email_disponivel(sessao_db, dados.email)
    _validar_usuario_disponivel(sessao_db, dados.usuario)
    _validar_sistema_origem_disponivel(sessao_db, dados.sistema_origem_id)

    usuario = Usuario(
        usuario=dados.usuario,
        sistema_origem_id=dados.sistema_origem_id,
        nome=dados.nome,
        email=dados.email,
        senha_hash=gerar_hash_senha(dados.senha),
        cargo_id=dados.cargo_id,
        ativo=dados.ativo,
    )
    sessao_db.add(usuario)
    sessao_db.flush()

    _sincronizar_permissoes(sessao_db, usuario, dados.permissoes)

    sessao_db.commit()
    sessao_db.refresh(usuario)
    return usuario


def atualizar(
    sessao_db: Session,
    usuario_id: str,
    dados: UsuarioAtualizarSchema,
    sistema_origem_id: str | None = None,
) -> Usuario:
    usuario = (
        obter_por_sistema_origem_id(sessao_db, sistema_origem_id)
        if sistema_origem_id
        else obter_por_id(sessao_db, usuario_id)
    )

    # NUNCA apaga o vínculo com o ERP. A ordem é: o que o corpo mandou, senão o
    # que localizou o registro, senão O QUE JÁ ESTAVA GRAVADO.
    #
    # Esse último degrau é o que faltava, e ele quebrou a produção: editar o
    # registro pela TELA manda um corpo sem `sistemaOrigemId` e sem o query
    # param, então o campo era zerado em silêncio. O funcionário 00168 perdeu o
    # vínculo desse jeito, e a integração de pedidos parou por três dias em
    # loop de restart — todo pedido dele passou a responder 404 "Vendedor não
    # encontrado para o sistema de origem informado".
    #
    # Só a integração cria esse vínculo; ninguém o remove por um formulário que
    # nem exibe o campo. Para desvincular de verdade, é um caminho explícito.
    sistema_origem_id_final = resolver_vinculo_origem(
        dados.sistema_origem_id, sistema_origem_id, usuario.sistema_origem_id
    )

    _validar_email_disponivel(sessao_db, dados.email, ignorar_id=usuario.id)
    _validar_usuario_disponivel(sessao_db, dados.usuario, ignorar_id=usuario.id)
    _validar_sistema_origem_disponivel(sessao_db, sistema_origem_id_final, ignorar_id=usuario.id)

    usuario.usuario = dados.usuario
    usuario.sistema_origem_id = sistema_origem_id_final
    usuario.nome = dados.nome
    usuario.email = dados.email
    usuario.cargo_id = dados.cargo_id
    usuario.ativo = dados.ativo
    if dados.senha:
        usuario.senha_hash = gerar_hash_senha(dados.senha)
    incrementar_versao(usuario)

    _sincronizar_permissoes(sessao_db, usuario, dados.permissoes)

    sessao_db.commit()
    sessao_db.refresh(usuario)
    return usuario


def apagar(sessao_db: Session, usuario_id: str, usuario_solicitante_id: str) -> None:
    if usuario_id == usuario_solicitante_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Você não pode apagar seu próprio usuário.")

    usuario = obter_por_id(sessao_db, usuario_id)
    marcar_apagado(usuario)
    sessao_db.commit()
