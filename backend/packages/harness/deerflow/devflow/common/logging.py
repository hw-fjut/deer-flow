"""Logging configuration"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logger(name: str, log_dir: str | None = None) -> logging.Logger:
    """Setup logger
    
    Args:
        name: Logger name
        log_dir: Log file directory, None for console only
    
    Returns:
        Configured Logger instance
    """
    logger = logging.getLogger(f"devflow.{name}")
    
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        
        # Console output
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # File output
        if log_dir:
            log_path = Path(log_dir)
            log_path.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_path / f"{name}.log",
                maxBytes=10*1024*1024,
                backupCount=5,
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
    
    return logger
