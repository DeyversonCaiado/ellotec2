"""
Entrada da sincronização com o sistema de origem (Oracle do ERP).

Roda em processo próprio, separado do `uvicorn` que serve a API — é um
integrador que fala com a própria API via HTTP, então precisa dela já no ar
em `http://localhost:8000`.

Rodar a partir de `C:\\projetos\\ellotec2\\backend`:

    python -m app.shared.sistema_origem.app
"""

import datetime
import os
import time
import traceback

from app.shared.sistema_origem.core.log import get_logger
from app.shared.sistema_origem.gestcom.sincronizacao import (
    funcionarios,
    clientes,
    marcas,
    produtos,
    pedidos,
    entregas,
)

logger = get_logger("sistema_origem")


def rotina_sistema_origem():
    """Sincroniza funcionários, clientes, marcas, produtos, pedidos e entregas
    com a API ELLOTEC, um depois do outro. Falha definitiva num registro derruba a
    aplicação inteira (ver sincronizar_* em `gestcom/sincronizacao/`) — dado de origem
    precisa ser corrigido antes de reiniciar.

    Entregas vem por último porque depende de funcionários (o vendedor da nota)
    e de empresas já cadastradas — as notas chegam pelo mesmo ciclo, e não
    adianta mandá-las antes de quem elas referenciam existir aqui."""
    try:
        while True:
            agora = datetime.datetime.now()

            # Só roda se estiver entre 07h00 e 18h00
            if 7 <= agora.hour < 18:
                funcionarios.sincronizar_funcionarios()
                clientes.sincronizar_clientes()
                marcas.sincronizar_marcas()
                produtos.sincronizar_produtos()
                pedidos.sincronizar_pedidos()
                entregas.sincronizar_entregas()
            else:
                # fora do horario permitido, nao faça nada
                pass

            # espera 10 segundos
            time.sleep(10)

    except Exception as e:
        print(traceback.format_exc())
        logger.error(f"Rotina de sincronização falhou, encerrando o processo: {e}")
        os._exit(1)


if __name__ == '__main__':
    rotina_sistema_origem()
