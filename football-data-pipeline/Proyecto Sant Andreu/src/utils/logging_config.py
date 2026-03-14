"""
logging_config.py
Configuración del sistema de logs para el pipeline
"""
import logging
import sys
from pathlib import Path
from datetime import datetime

def setup_logging(log_dir: Path = None, level: int = logging.INFO) -> logging.Logger:
    """
    Configura el sistema de logging con salida a archivo y consola.
    
    Args:
        log_dir: Directorio donde guardar los logs
        level: Nivel de logging (default: INFO)
    
    Returns:
        Logger configurado
    """
    # Crear logger principal
    logger = logging.getLogger("sant_andreu_pipeline")
    logger.setLevel(level)
    
    # Evitar duplicar handlers si ya existen
    if logger.handlers:
        return logger
    
    # Formato de los mensajes
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Handler para consola
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Handler para archivo (si se especifica directorio)
    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Nombre del archivo con fecha
        log_file = log_dir / f"pipeline_{datetime.now().strftime('%Y%m%d')}.log"
        
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        logger.info(f"Log file: {log_file}")
    
    return logger


def get_logger(name: str = None) -> logging.Logger:
    """
    Obtiene un logger hijo del logger principal.
    
    Args:
        name: Nombre del módulo (se añade como sufijo)
    
    Returns:
        Logger configurado
    """
    base_logger = logging.getLogger("sant_andreu_pipeline")
    
    if name:
        return base_logger.getChild(name)
    return base_logger


# Test
if __name__ == "__main__":
    from config import get_config
    cfg = get_config()
    
    logger = setup_logging(cfg.LOGS_DIR)
    logger.info("Sistema de logging inicializado correctamente")
    logger.debug("Este mensaje solo aparece en nivel DEBUG")
    logger.warning("Este es un mensaje de advertencia")
