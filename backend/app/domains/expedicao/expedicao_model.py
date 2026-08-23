from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.conexao import Base
from app.shared.sync_mixin import IdMixin, SyncMixin

# Nenhum model de `pedidos` ou `usuarios` é importado aqui — as FKs abaixo
# apontam pra tabelas de outros domínios só pelo nome, e é o banco (FK real)
# quem recusa um id inexistente. Ver ARCHITECTURE.md → "Validação de id por
# foreign key". `pedido_itens` é documento (não cadastro), então nem
# `relationship()` é criado pra ele a partir daqui — quem precisa exibir
# dado do pedido consulta o domínio de pedidos separadamente.


class ExpedicaoPedidoStatus(Base, IdMixin, SyncMixin):
    """
    Em que ponto do galpão cada pedido está. Uma linha por pedido, atualizada
    conforme as etapas avançam.

    Existe em vez de gravar direto em `pedidos.status_id` porque aquele campo é
    da integração: um PUT do ERP no mesmo pedido sobrescreveria o andamento da
    expedição. Aqui o dono da escrita é só este domínio.

    `status_id` aponta para o mesmo catálogo `pedido_status` usado pelo pedido —
    o vocabulário de status é um só no sistema, não dois.
    """

    __tablename__ = "expedicao_pedido_status"

    # Único: é o status ATUAL, não histórico. Quem quiser reconstruir a linha do
    # tempo tem as datas de início e fim dos processos e dos itens.
    pedido_id: Mapped[str] = mapped_column(
        ForeignKey("pedidos.id"), nullable=False, unique=True, index=True
    )
    status_id: Mapped[str] = mapped_column(ForeignKey("pedido_status.id"), nullable=False, index=True)


class ExpedicaoAtribuicao(Base, IdMixin, SyncMixin):
    """
    Quem é o responsável por uma etapa de um pedido.

    É por etapa, não por pedido: o caso normal do galpão é uma pessoa separar e
    outra conferir o mesmo pedido, então `(pedido_id, tipo)` é que identifica a
    designação — não `pedido_id` sozinho.

    Esta tabela é o que decide o que cada um ENXERGA na listagem: operador sem
    a permissão `expedicao.atribuir` só vê pedido em que ele é o responsável de
    alguma etapa (ver `listar_pedidos` em expedicao_service.py). Por isso ela
    não é um enfeite de UI — é regra de acesso, e mora no backend.

    Desatribuir é `marcar_apagado`, nunca DELETE: quem atribuiu, para quem e
    quando é rastro de auditoria que o galpão vai querer no dia em que um
    pedido sair errado.
    """

    __tablename__ = "expedicao_atribuicoes"

    pedido_id: Mapped[str] = mapped_column(ForeignKey("pedidos.id"), nullable=False, index=True)
    # 'separacao' | 'conferencia' — mesmo par do TipoProcesso do contrato.
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    usuario_id: Mapped[str] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    # Quem distribuiu. Não é o mesmo que `usuario_id`, e é o que responde
    # "quem mandou fulano separar esse pedido?".
    atribuido_por_id: Mapped[str] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    data_atribuicao: Mapped[datetime] = mapped_column(DateTime(), nullable=False)

    # Sem UniqueConstraint em (pedido_id, tipo): o soft delete deixaria linhas
    # apagadas ocupando a chave, e o MySQL não tem índice único parcial. Quem
    # garante um responsável vivo por etapa é `atribuir` no service, que apaga
    # a atribuição anterior antes de gravar a nova.


class Separacao(Base, IdMixin, SyncMixin):
    __tablename__ = "expedicao_separacoes"

    pedido_id: Mapped[str] = mapped_column(ForeignKey("pedidos.id"), nullable=False, index=True)
    usuario_inicio_id: Mapped[str] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    usuario_fim_id: Mapped[str | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="em_andamento")
    data_inicio: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, default=None)
    # Quando a PRIMEIRA leitura foi registrada. Diferente de `data_inicio`, que
    # é quando o processo foi aberto: entre abrir a lista e bipar o primeiro
    # item pode passar muito tempo (o operador ainda vai até o endereço). O
    # tempo de trabalho de verdade se mede daqui, não da abertura.
    data_primeiro_bipe: Mapped[datetime | None] = mapped_column(
        DateTime(), nullable=True, default=None
    )
    data_fim: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, default=None)

    itens: Mapped[list["SeparacaoItem"]] = relationship(
        back_populates="separacao",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="SeparacaoItem.sync_created_at",
    )


class SeparacaoItem(Base, IdMixin, SyncMixin):
    """
    Não tem coluna de status: o estado do item é derivado das datas.
    `data_inicio` nula = pendente; início preenchido sem fim = em andamento;
    `data_fim` preenchida = finalizado. Uma coluna a menos, e zero chance de
    um campo `status` divergir das datas que medem o tempo gasto por item.
    """

    __tablename__ = "expedicao_separacao_itens"

    separacao_id: Mapped[str] = mapped_column(
        ForeignKey("expedicao_separacoes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pedido_item_id: Mapped[str] = mapped_column(ForeignKey("pedido_itens.id"), nullable=False, index=True)
    quantidade_separada: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data_inicio: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, default=None)
    data_fim: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, default=None)
    divergente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Gerente que liberou a finalização com quantidade abaixo da pedida.
    # NULL quando o item fechou completo (o caso normal). Sem essa coluna,
    # "quem autorizou a falta" não fica rastreável em lugar nenhum.
    usuario_autorizador_id: Mapped[str | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True, index=True
    )

    separacao: Mapped["Separacao"] = relationship(back_populates="itens")


class Conferencia(Base, IdMixin, SyncMixin):
    __tablename__ = "expedicao_conferencias"

    pedido_id: Mapped[str] = mapped_column(ForeignKey("pedidos.id"), nullable=False, index=True)
    usuario_inicio_id: Mapped[str] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    usuario_fim_id: Mapped[str | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="em_andamento")
    data_inicio: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, default=None)
    # Quando a PRIMEIRA leitura foi registrada. Diferente de `data_inicio`, que
    # é quando o processo foi aberto: entre abrir a lista e bipar o primeiro
    # item pode passar muito tempo (o operador ainda vai até o endereço). O
    # tempo de trabalho de verdade se mede daqui, não da abertura.
    data_primeiro_bipe: Mapped[datetime | None] = mapped_column(
        DateTime(), nullable=True, default=None
    )
    data_fim: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, default=None)

    itens: Mapped[list["ConferenciaItem"]] = relationship(
        back_populates="conferencia",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ConferenciaItem.sync_created_at",
    )


class ConferenciaItem(Base, IdMixin, SyncMixin):
    """Mesmo desenho de SeparacaoItem — estado derivado das datas."""

    __tablename__ = "expedicao_conferencia_itens"

    conferencia_id: Mapped[str] = mapped_column(
        ForeignKey("expedicao_conferencias.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pedido_item_id: Mapped[str] = mapped_column(ForeignKey("pedido_itens.id"), nullable=False, index=True)
    quantidade_conferida: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    divergente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    data_inicio: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, default=None)
    data_fim: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, default=None)
    # Mesmo papel de SeparacaoItem.usuario_autorizador_id — ver lá.
    usuario_autorizador_id: Mapped[str | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True, index=True
    )

    conferencia: Mapped["Conferencia"] = relationship(back_populates="itens")
