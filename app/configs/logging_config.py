import logging
from logging.handlers import QueueHandler, QueueListener
from queue import Queue
import os
import atexit

# Garante que o diretório de logs existe
os.makedirs("logs", exist_ok=True)

# Fila global para logs assíncronos
log_queue = Queue()
listener = None

def configurar_logger(nome_logger, arquivo_log=None, nivel=logging.DEBUG,
                      formato="%(asctime)s [%(levelname)s] %(name)s: %(message)s"):
    """
    Configura um logger com arquivo e fila assíncrona, incluindo suporte a logs resumidos de contexto.
    """
    global listener

    # Define arquivo de log
    if arquivo_log is None:
        modulo = nome_logger.split('.')[-1]
        arquivo_log = f"logs/{modulo}.log"
    
    logger = logging.getLogger(nome_logger)

    # Limpa handlers existentes
    if logger.hasHandlers():
        logger.handlers.clear()

    # Handler de arquivo
    file_handler = logging.FileHandler(arquivo_log)
    file_handler.setFormatter(logging.Formatter(formato))
    logger.addHandler(file_handler)

    # Handler de fila
    queue_handler = QueueHandler(log_queue)
    logger.addHandler(queue_handler)

    # Nível de log
    logger.setLevel(nivel)

    # Inicia listener se necessário
    if listener is None:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(formato))
        listener = QueueListener(log_queue, handler)
        listener.start()
        atexit.register(encerrar_listener)

    # Adiciona método utilitário ao logger para logs de contexto resumidos
    def log_contexto(contexto_nome, resumo="Contexto carregado e aplicado"):
        logger.debug(f"[CONTEXT] {contexto_nome}: {resumo}")

    logger.log_contexto = log_contexto
    return logger

def encerrar_listener():
    global listener
    if listener:
        listener.stop()
        listener = None
