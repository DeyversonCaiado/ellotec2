"""
Canal pelo qual outros domínios pedem uma operação NO ERP (hoje: `expedicao`).

Regras do arquivo de fronteira (ver backend/ARCHITECTURE.md → "Como se faz: o
arquivo de fronteira `<dominio>_publico.py`"): recebe tipos primitivos, devolve
contrato próprio ou primitivo, e quem consome importa **só este arquivo** —
nunca `sistema_origem_service` direto.

Uma diferença em relação às outras bordas de escrita do projeto, e ela é
importante: `enderecamento_publico.baixar_lote` não dá `commit()` porque
escreve na `Session` de quem chamou, e o dono da transação decide o desfecho.
Aqui não existe `Session` — a escrita é no Oracle do ERP, uma conexão de fora,
que **precisa** commitar sozinha. Ou seja, a regra "nenhuma função da borda dá
commit" continua valendo para o NOSSO banco, e é justamente por isso que quem
chama tem que commitar o MySQL só DEPOIS que esta função voltar sem erro: se a
ordem se inverter, o ERP fica fechado e o nosso banco achando que não fechou.
"""

from decimal import Decimal

from app.domains.sistema_origem import sistema_origem_service

# Reexportados para quem consome não precisar conhecer o service: são os
# valores que a tela usa para explicar a recusa ao operador.
STATUS_EXIGIDO = sistema_origem_service.STATUS_EXIGIDO
TAMANHO_ESPECIE = sistema_origem_service.TAMANHO_ESPECIE


def finalizar_pedido(
    *,
    empresa_sistema_origem_id: str,
    pedido_sistema_origem_id: str,
    usuario_sistema_origem_id: str,
    volume: Decimal,
    especie: str,
    peso_liquido: Decimal,
    peso_bruto: Decimal,
    usuario_login: str = "",
) -> None:
    """Fecha a conferência do pedido no ERP (status `FEC` + volumes e pesos).

    Levanta `HTTPException` quando a invariante do ERP não fecha — pedido
    inexistente (404), pedido que já saiu do `PED` (409), canal fora do ar
    (503). Volta `None` em caso de sucesso: o ERP não devolve nada que o
    chamador precise, e o que interessa a ele é só "deu ou não deu".

    **Não é idempotente**: a segunda chamada encontra o pedido já fora do
    `PED` e é recusada com 409. É essa recusa que faz o papel da trava.
    """
    sistema_origem_service.finalizar_pedido(
        empresa_sistema_origem_id=empresa_sistema_origem_id,
        pedido_sistema_origem_id=pedido_sistema_origem_id,
        usuario_sistema_origem_id=usuario_sistema_origem_id,
        volume=volume,
        especie=especie,
        peso_liquido=peso_liquido,
        peso_bruto=peso_bruto,
        usuario_login=usuario_login,
    )
