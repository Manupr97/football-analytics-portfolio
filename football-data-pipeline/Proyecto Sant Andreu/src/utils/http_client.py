"""
http_client.py
Cliente HTTP robusto con retries, backoff exponencial y manejo de errores
"""
import time
import random
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional
from pathlib import Path

from config import get_config
from utils.logging_config import get_logger

logger = get_logger("http_client")


class HttpClient:
    """Cliente HTTP con session persistente, retries y delays aleatorios"""
    
    def __init__(self, config=None):
        self.config = config or get_config()
        self.session = self._create_session()
        self._last_request_time = 0
    
    def _create_session(self) -> requests.Session:
        """Crea una session con retry strategy"""
        session = requests.Session()
        
        # Configurar retries
        retry_strategy = Retry(
            total=self.config.MAX_RETRIES,
            backoff_factor=self.config.RETRY_BACKOFF,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Headers por defecto
        session.headers.update(self.config.REQUEST_HEADERS)
        
        return session
    
    def _wait_between_requests(self):
        """Aplica delay aleatorio entre requests para no saturar el servidor"""
        elapsed = time.time() - self._last_request_time
        min_wait = self.config.MIN_DELAY
        
        if elapsed < min_wait:
            # Delay aleatorio entre MIN y MAX
            delay = random.uniform(self.config.MIN_DELAY, self.config.MAX_DELAY)
            time.sleep(delay)
    
    def get(self, url: str, **kwargs) -> Optional[requests.Response]:
        """
        Realiza GET request con manejo de errores.
        
        Args:
            url: URL a consultar
            **kwargs: Argumentos adicionales para requests.get
        
        Returns:
            Response object o None si falla
        """
        self._wait_between_requests()
        
        try:
            logger.debug(f"GET {url}")
            
            response = self.session.get(
                url,
                timeout=self.config.REQUEST_TIMEOUT,
                **kwargs
            )
            
            self._last_request_time = time.time()
            
            response.raise_for_status()
            return response
            
        except requests.exceptions.Timeout:
            logger.error(f"Timeout en request a {url}")
            return None
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error {e.response.status_code} en {url}")
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error en request a {url}: {e}")
            return None
    
    def get_html(self, url: str) -> Optional[str]:
        """
        Obtiene el HTML de una URL.
        
        Args:
            url: URL a consultar
        
        Returns:
            HTML como string o None si falla
        """
        response = self.get(url)
        if response:
            return response.text
        return None
    
    def download_and_save(self, url: str, save_path: Path) -> bool:
        """
        Descarga HTML y lo guarda en disco.
        
        Args:
            url: URL a descargar
            save_path: Ruta donde guardar el archivo
        
        Returns:
            True si se guardó correctamente, False si falló
        """
        html = self.get_html(url)
        
        if html:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_text(html, encoding="utf-8")
            logger.debug(f"Guardado: {save_path}")
            return True
        
        return False
    
    def close(self):
        """Cierra la session"""
        self.session.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Instancia global (singleton)
_client: Optional[HttpClient] = None


def get_http_client() -> HttpClient:
    """Retorna el cliente HTTP global"""
    global _client
    if _client is None:
        _client = HttpClient()
    return _client


# Test
if __name__ == "__main__":
    client = get_http_client()
    cfg = get_config()
    
    # Test con la URL de clasificación
    logger.info(f"Probando conexión a {cfg.COMPETITION_URL}")
    response = client.get(cfg.COMPETITION_URL)
    
    if response:
        logger.info(f"OK - Status: {response.status_code}, Tamaño: {len(response.text)} bytes")
    else:
        logger.error("Fallo en la conexión")
