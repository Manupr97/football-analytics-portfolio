"""
matchcenter_scraper.py — Fetch del HTML del Match Centre de WhoScored.

Responsabilidad única: dado un match_id (o URL), devuelve el HTML
completo de la página para que payload_parser.py lo procese.

El HTML se guarda siempre en raw antes de parsear (re-parseable sin scrapear).

Uso:

    from ws_platform.scraping.matchcenter_scraper import MatchcenterScraper

    scraper = MatchcenterScraper(driver)
    html = scraper.fetch(match_id=1913956)
"""

from __future__ import annotations

import random
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import logging

from src.scraping.driver_factory import accept_cookies

log = logging.getLogger(__name__)

_BASE = "https://es.whoscored.com"
_MATCH_URL = _BASE + "/Matches/{match_id}/Live"

# Señales que confirman que el payload está cargado en la página
_PAYLOAD_XPATH = "//script[contains(., 'require.config.params[\"args\"]')]"
_HEADER_CSS = "#match-header"


class MatchcenterScraper:
    """
    Scraper del Match Centre de WhoScored.

    Args:
        driver: Driver de Selenium ya inicializado (se reutiliza entre partidos).
    """

    def __init__(self, driver) -> None:
        self.driver = driver

    def fetch(
        self,
        match_id: int,
        url: str | None = None,
        timeout: int = 25,
        retries: int = 3,
    ) -> str:
        """
        Navega a la página del partido y devuelve el HTML completo.

        Args:
            match_id: ID del partido en WhoScored.
            url:      URL completa. Si None, se construye desde match_id.
            timeout:  Segundos máximos de espera por elemento clave.
            retries:  Número máximo de reintentos con backoff exponencial.

        Returns:
            HTML completo de la página como string.

        Raises:
            RuntimeError: Si no se puede obtener el HTML tras todos los reintentos.
        """
        target_url = url or _MATCH_URL.format(match_id=match_id)
        last_exc: Exception | None = None

        for attempt in range(1, retries + 1):
            try:
                html = self._fetch_once(target_url, timeout=timeout)
                log.info(
                    "matchcenter_html_ok",
                    match_id=match_id,
                    attempt=attempt,
                    html_len=len(html),
                )
                return html

            except Exception as exc:
                last_exc = exc
                wait = 10 * (3 ** (attempt - 1))   # 10s, 30s, 90s
                log.warning(
                    "matchcenter_reintento",
                    match_id=match_id,
                    attempt=attempt,
                    retries=retries,
                    wait_s=wait,
                    error=str(exc),
                )
                if attempt < retries:
                    time.sleep(wait)

        raise RuntimeError(
            f"No se pudo obtener HTML de match_id={match_id} "
            f"tras {retries} intentos: {last_exc}"
        )

    def _fetch_once(self, url: str, timeout: int) -> str:
        """Un intento de navegación y extracción de HTML."""
        self.driver.get(url)
        accept_cookies(self.driver, timeout=8)

        wait = WebDriverWait(self.driver, timeout)

        # Esperar cabecera del partido
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, _HEADER_CSS)))

        # Esperar que el payload JavaScript esté embebido en la página
        wait.until(EC.presence_of_element_located((By.XPATH, _PAYLOAD_XPATH)))

        # Scroll para asegurar carga completa de scripts lazy
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.5)

        return self.driver.page_source