"""
fixtures_scraper.py — Scraping de fixtures finalizados desde WhoScored.

Navega a la página de fixtures de una competición y extrae la lista de
partidos finalizados (con marcador) mes a mes.

Uso:

    from ws_platform.scraping.fixtures_scraper import FixturesScraper

    scraper = FixturesScraper(driver)
    df = scraper.fetch_finished(
        fixtures_url="https://es.whoscored.com/regions/.../fixtures/...",
        months=["oct 2025", "nov 2025"],
    )
"""

from __future__ import annotations

import re
import time
from datetime import date

import pandas as pd
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import logging

from src.scraping.driver_factory import accept_cookies, robust_click

log = logging.getLogger(__name__)

_BASE = "https://es.whoscored.com"

# Abreviaturas de mes en español → número
_MONTH_MAP = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4,
    "may": 5, "jun": 6, "jul": 7, "ago": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dic": 12,
}

# El datepicker de WhoScored usa "sept" en lugar de "sep"
_DATEPICKER_LABEL = {"sep": "sept"}


class FixturesScraper:
    """
    Scraper de fixtures de WhoScored.

    Args:
        driver: Driver de Selenium ya inicializado.
    """

    def __init__(self, driver) -> None:
        self.driver = driver

    def fetch_finished(
        self,
        fixtures_url: str,
        months: list[str],
        timeout: int = 25,
    ) -> pd.DataFrame:
        """
        Extrae todos los partidos finalizados de los meses indicados.

        Args:
            fixtures_url: URL de la página de fixtures de la competición.
            months:       Lista de meses en formato "mmm YYYY" (ej: ["oct 2025", "nov 2025"]).
            timeout:      Segundos de espera por elementos clave.

        Returns:
            DataFrame con columnas: match_id, home_name, away_name,
            score_home, score_away, match_date, match_centre_url.
        """
        self.driver.get(fixtures_url)
        wait = WebDriverWait(self.driver, timeout)

        wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, 'div[class*="Accordion-module_accordion"]')
        ))
        accept_cookies(self.driver, timeout=8)

        all_records: list[dict] = []

        for month_label in months:
            try:
                records = self._scrape_month(month_label, timeout=timeout)
                all_records.extend(records)
                log.info(
                    "fixtures_mes_scrapeado",
                    month=month_label,
                    n_partidos=len(records),
                )
            except Exception as exc:
                log.error(
                    "fixtures_mes_error",
                    month=month_label,
                    error=str(exc),
                )

        if not all_records:
            return pd.DataFrame()

        df = (
            pd.DataFrame(all_records)
            .drop_duplicates(subset=["match_id"])
            .reset_index(drop=True)
        )

        log.info(
            "fixtures_scraping_completado",
            url=fixtures_url,
            total_partidos=len(df),
        )
        return df

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------

    def _scrape_month(self, month_label: str, timeout: int) -> list[dict]:
        """Navega al mes indicado y extrae los partidos finalizados."""
        wait = WebDriverWait(self.driver, timeout)

        # Esperar a que la página esté estable antes de abrir el calendario
        # (importante: tras el mes anterior el DOM puede estar recargando)
        wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, 'div[class^="Accordion-module_accordion"]')
        ))
        # Asegurar que el toggle del datepicker es interactuable
        wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, '[class*="DatePicker-module_datePicker"] button, '
                               '[class*="toggleCalendar"], [class*="datePicker"] button')
        ))

        self._open_calendar(timeout)
        self._select_month(month_label)

        # Esperar a que el datepicker se cierre (el clic en el mes lo cierra)
        try:
            wait.until(EC.invisibility_of_element_located((By.ID, "datePicker")))
        except TimeoutException:
            pass

        # Esperar a que los accordeones del nuevo mes carguen
        wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, 'div[class*="Accordion-module_accordion"]')
        ))
        # Pausa para que el DOM se estabilice completamente antes del siguiente mes
        time.sleep(1.5)

        self._open_all_accordions()
        return self._extract_finished_matches()

    def _open_calendar(self, timeout: int) -> None:
        """
        Abre el datepicker haciendo clic en el botón que muestra el mes activo.

        El toggle real en WhoScored es el botón que muestra el mes/año actual
        (ej: "feb 2026 ▲"). No hay un #toggleCalendar — el propio label es el toggle.
        """
        wait = WebDriverWait(self.driver, timeout)

        # Si el datepicker ya está abierto, no hacer nada
        try:
            dp = self.driver.find_element(By.ID, "datePicker")
            if dp.is_displayed():
                return
        except Exception:
            pass

        # El toggle es el botón con el label del mes activo.
        # Selectores en orden de prioridad según el DOM observado:
        toggle_selectors = [
            # Botón dentro del contenedor del datepicker (clase moderna)
            '[class*="DatePicker-module_datePicker"] button',
            # Botón dentro de cualquier div que contenga "datePicker" en la clase
            '[class*="datePicker"] > button',
            '[class*="datePicker"] button',
            # Fallbacks históricos
            '#toggleCalendar',
            '.toggleDatePicker',
        ]

        toggle = None
        for sel in toggle_selectors:
            try:
                toggle = self.driver.find_element(By.CSS_SELECTOR, sel)
                if toggle.is_displayed():
                    break
                toggle = None
            except Exception:
                continue

        if toggle is None:
            raise RuntimeError("No se encontró el botón toggle del datepicker.")

        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", toggle)
        self.driver.execute_script("arguments[0].click();", toggle)

        wait.until(EC.visibility_of_element_located((By.ID, "datePicker")))

    def _select_month(self, month_label: str) -> None:
        """
        Hace clic en el mes dentro del datepicker.

        El datepicker abre siempre en el año actual. Si el mes objetivo
        pertenece a un año distinto hay que navegar primero al año correcto
        antes de seleccionar el mes.
        """
        parts = month_label.split()
        canon = parts[0].lower()
        target_year = int(parts[1]) if len(parts) > 1 else None
        dp_label = _DATEPICKER_LABEL.get(canon, canon[:4])

        # --- Paso 1: navegar al año correcto si es necesario ---
        if target_year is not None:
            self._ensure_year(target_year)

        # --- Paso 2: seleccionar el mes ---
        xpaths = [
            f"//*[@id='datePicker']//tbody[contains(@class,'monthsTbody')]"
            f"//td[normalize-space(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'))='{dp_label}']",
            # fallback 3 letras
            f"//*[@id='datePicker']//tbody[contains(@class,'monthsTbody')]"
            f"//td[normalize-space(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'))='{canon[:3]}']",
        ]

        month_td = None
        for xp in xpaths:
            try:
                month_td = self.driver.find_element(By.XPATH, xp)
                break
            except NoSuchElementException:
                continue

        if not month_td:
            raise RuntimeError(f"No se encontró el mes '{month_label}' en el datepicker.")

        self.driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", month_td
        )
        self.driver.execute_script("arguments[0].click();", month_td)
        time.sleep(0.6)

    def _ensure_year(self, target_year: int) -> None:
        """
        Si el datepicker no está mostrando target_year, abre el selector de
        año y hace clic en el año correcto.

        Estructura del DOM observada:
          - Botón activo: div.yearMonthSelector > button  (contiene el año actual)
          - Tabla de años: tbody.yearsTbody > tr > td     (lista de años seleccionables)
        """
        # Leer el año actualmente mostrado
        try:
            year_btn = self.driver.find_element(
                By.CSS_SELECTOR,
                "#datePicker [class*='yearMonthSelector'] button"
            )
            current_year_text = year_btn.text.strip()
            current_year = int(re.search(r"\d{4}", current_year_text).group())
        except Exception:
            # Si no podemos leer el año, intentamos de todas formas
            current_year = None

        if current_year == target_year:
            return  # Ya estamos en el año correcto

        log.debug(
            "datepicker_cambio_año",
            current_year=current_year,
            target_year=target_year,
        )

        # Abrir el selector de año haciendo clic en el botón del año
        try:
            year_btn = self.driver.find_element(
                By.CSS_SELECTOR,
                "#datePicker [class*='yearMonthSelector'] button"
            )
            self.driver.execute_script("arguments[0].click();", year_btn)
            time.sleep(0.4)
        except Exception as exc:
            raise RuntimeError(f"No se pudo abrir el selector de año: {exc}")

        # Buscar y hacer clic en la celda del año objetivo
        year_xpath = (
            f"//*[@id='datePicker']//tbody[contains(@class,'yearsTbody')]"
            f"//td[normalize-space(.)='{target_year}']"
        )
        try:
            year_td = self.driver.find_element(By.XPATH, year_xpath)
            self.driver.execute_script("arguments[0].click();", year_td)
            time.sleep(0.4)
        except NoSuchElementException:
            raise RuntimeError(
                f"Año {target_year} no encontrado en el datepicker. "
                f"Años disponibles: "
                + str([td.text.strip() for td in self.driver.find_elements(
                    By.XPATH,
                    "//*[@id='datePicker']//tbody[contains(@class,'yearsTbody')]//td"
                )])
            )

    def _open_all_accordions(self) -> None:
        """
        Abre los acordeones de días que estén cerrados.

        WhoScored abre todos los accordeones por defecto al cambiar de mes,
        así que normalmente no hay nada que hacer. Solo se abre manualmente
        los que aparezcan cerrados (caso excepcional).
        """
        for acc in self.driver.find_elements(
            By.CSS_SELECTOR, 'div[class*="Accordion-module_accordion"]'
        ):
            try:
                opened = acc.find_elements(
                    By.CSS_SELECTOR, 'div[class*="childrenOpened"]'
                )
                if not opened:
                    hdr = acc.find_element(
                        By.CSS_SELECTOR, 'div[class*="Accordion-module_header"]'
                    )
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", hdr
                    )
                    hdr.click()
                    time.sleep(0.15)
            except Exception:
                continue

    def _extract_finished_matches(self) -> list[dict]:
        """
        Extrae los partidos finalizados de la vista actual.
        Un partido está finalizado si tiene marcador (dos números enteros).

        Usa class*= en todos los selectores porque las clases de WhoScored
        llevan hashes de build (ej: Match-module_row__zwBOn).
        """
        records = []

        for acc in self.driver.find_elements(
            By.CSS_SELECTOR, 'div[class*="Accordion-module_accordion"]'
        ):
            match_date = self._parse_day_date(acc)

            # Contenedor de filas: childrenOpened indica que está expandido
            try:
                rows_container = acc.find_element(
                    By.CSS_SELECTOR, 'div[class*="childrenOpened"]'
                )
            except Exception:
                continue

            # Las filas son div[class*="Match-module_row"] directamente
            for row in rows_container.find_elements(
                By.CSS_SELECTOR, 'div[class*="Match-module_row"]'
            ):
                record = self._extract_row(row, match_date)
                if record:
                    records.append(record)

        return records

    def _parse_day_date(self, accordion) -> str | None:
        """
        Extrae la fecha del acordeón de día.

        Formato real de WhoScored: 'viernes, ago 15 2025' (MES DÍA AÑO).
        También acepta el formato antiguo 'Dom 5 oct 2025' (DÍA MES AÑO)
        como fallback por compatibilidad.
        """
        try:
            label = accordion.find_element(
                By.CSS_SELECTOR, 'div[class*="Accordion-module_header"] span'
            ).text.strip()

            # Formato actual: "viernes, ago 15 2025" → MES DÍA AÑO
            m = re.search(r"([a-záéíóú]+)\s+(\d{1,2})\s+(\d{4})", label, re.IGNORECASE)
            if m:
                month = _MONTH_MAP.get(m.group(1).lower()[:4])
                day   = int(m.group(2))
                year  = int(m.group(3))
                if month:
                    return date(year, month, day).isoformat()

            # Fallback: "Dom 5 oct 2025" → DÍA MES AÑO
            m = re.search(r"(\d{1,2})\s+([a-záéíóú]+)\s+(\d{4})", label, re.IGNORECASE)
            if m:
                day   = int(m.group(1))
                month = _MONTH_MAP.get(m.group(2).lower()[:4])
                year  = int(m.group(3))
                if month:
                    return date(year, month, day).isoformat()
        except Exception:
            pass
        return None

    def _extract_row(self, row, match_date: str | None) -> dict | None:
        """
        Extrae datos de una fila de partido.
        Devuelve None si no está finalizado (sin marcador).
        """
        # URL y match_id
        href = None
        try:
            a = row.find_element(
                By.CSS_SELECTOR, 'a[id^="scoresBtn-"], a[href^="/matches/"]'
            )
            href = a.get_attribute("href") or a.get_attribute("data-href")
            if href and href.startswith("/"):
                href = _BASE + href
        except Exception:
            return None

        match_id = None
        if href:
            m = re.search(r"/matches/(\d+)/", href, re.IGNORECASE)
            if m:
                match_id = int(m.group(1))
        if not match_id:
            return None

        # Marcador — si no hay dos números, el partido no está finalizado
        score_home, score_away = self._parse_score(row)
        if score_home is None or score_away is None:
            return None

        # Equipos — class*= por hashes de build
        home_name, away_name = None, None
        try:
            teams = row.find_elements(
                By.CSS_SELECTOR, 'div[class*="Match-module_teamName"] a'
            )
            if len(teams) >= 2:
                home_name = teams[0].text.strip()
                away_name = teams[1].text.strip()
        except Exception:
            pass

        return {
            "match_id":         match_id,
            "home_name":        home_name,
            "away_name":        away_name,
            "score_home":       score_home,
            "score_away":       score_away,
            "match_date":       match_date,
            "match_centre_url": f"{_BASE}/Matches/{match_id}/Live",
        }

    def _parse_score(self, row) -> tuple[int | None, int | None]:
        """
        Extrae el marcador de una fila. Devuelve (None, None) si el partido
        no está finalizado (guiones, hora futura, etc.).

        En WhoScored el marcador está en:
          <a class="Match-module_score__XXX"><span>1</span><span>3</span></a>
        Los <span> hijos NO tienen clase propia — hay que llegar por el <a> padre.

        IMPORTANTE: no usar regex sobre row.text como fallback porque el texto
        puede contener la hora del partido (ej: "21:00") que se interpreta
        erróneamente como marcador.
        """
        try:
            # Selector principal: spans hijos del <a class*="Match-module_score">
            score_a = row.find_elements(
                By.CSS_SELECTOR, 'a[class*="Match-module_score"]'
            )
            if score_a:
                spans = score_a[0].find_elements(By.TAG_NAME, "span")
                numbers = [int(s.text.strip()) for s in spans if s.text.strip().isdigit()]
                if len(numbers) >= 2:
                    return numbers[0], numbers[1]
                # El <a> existe pero sus spans no son números → partido no finalizado
                return None, None

            # Fallback: spans con clase "score"/"Score"
            score_els = row.find_elements(
                By.CSS_SELECTOR, 'span[class*="score"], span[class*="Score"]'
            )
            numbers = [int(el.text.strip()) for el in score_els if el.text.strip().isdigit()]
            if len(numbers) >= 2:
                return numbers[0], numbers[1]
        except Exception:
            pass
        return None, None
