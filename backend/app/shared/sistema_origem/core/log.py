"""
Logger dos scripts de sincronização com o sistema de origem.

Cada rotina de `gestcom/sincronizacao/` chama `get_logger(<nome>)` e grava em
`log/<nome>.log`, rotacionado diariamente. Independente do logging do FastAPI
(`app/main.py`) porque estes scripts rodam num processo próprio
(`python -m app.shared.sistema_origem.app`), não dentro do worker do uvicorn.
"""

import logging
from logging.handlers import TimedRotatingFileHandler
import os


class SafeTimedRotatingFileHandler(TimedRotatingFileHandler):
    """
    TimedRotatingFileHandler que não derruba a aplicação quando o arquivo
    de log está travado por outro processo (comum no Windows quando dois
    processos escrevem no mesmo arquivo). Se a rotação falhar, o handler
    apenas continua gravando no arquivo atual e tenta rotacionar novamente
    na próxima vez.
    """

    def doRollover(self):
        try:
            super().doRollover()
        except PermissionError:
            self.stream = self._open()


def get_logger(nome_logger="sistema_origem", pasta_logs="log", dias_reter=7):
    """
    Retorna um logger configurado para rotacionar os arquivos de log diariamente.
    """
    # Garante que a pasta de logs exista
    os.makedirs(pasta_logs, exist_ok=True)

    # Cria o logger
    logger = logging.getLogger(nome_logger)
    logger.setLevel(logging.INFO)

    # Evita duplicar handlers se já foi configurado antes
    if not logger.handlers:
        # Configura para criar um novo arquivo de log a cada dia
        handler = SafeTimedRotatingFileHandler(
            f"{pasta_logs}/{nome_logger}.log",
            when="midnight",  # troca à meia-noite
            interval=1,       # intervalo de 1 dia
            backupCount=dias_reter,  # mantém X dias de logs
            encoding="utf-8"
        )

        # Formato do log
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)

        # Adiciona o handler ao logger
        logger.addHandler(handler)

    return logger
