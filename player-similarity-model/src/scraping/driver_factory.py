"""
driver_factory.py — Chrome driver unificado para todo el proyecto.

Intenta undetected-chromedriver primero (mejor bypass anti-bot).
Cae a Selenium estándar + webdriver-manager si falla.

Uso:

    from ws_platform.scraping.driver_factory import build_driver, quit_driver

    driver = build_driver(headless=True)
    try:
        driver.get(url)
        ...
    finally:
        quit_driver(driver)
"""

from __future__ import annotations

import threading
import time
from typing import Any

import logging

# undetected_chromedriver parchea un ejecutable en disco al crear el driver.
# Si dos threads intentan crearlo a la vez, uno falla con WinError 183.
# Este lock serializa la creación — solo un driver arranca a la vez.
_BUILD_LOCK = threading.Lock()

log = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def build_driver(headless: bool = True) -> Any:
    """
    Construye un Chrome driver con anti-detección.

    La creación está serializada con un Lock para evitar que múltiples threads
    intenten parchear el ejecutable de undetected_chromedriver simultáneamente
    (WinError 183 en Windows).

    Args:
        headless: Si True (default), corre sin ventana visible.

    Returns:
        Driver de Selenium/undetected-chromedriver listo para usar.
    """
    use_headless = headless

    with _BUILD_LOCK:
        driver = _try_undetected(use_headless)

    if driver is None:
        raise RuntimeError(
            "No se pudo crear el driver de Chrome con undetected_chromedriver. "
            "Verifica que Chrome esté instalado y actualizado."
        )

    return driver


def _chrome_args(headless: bool) -> list[str]:
    args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--window-size=1440,1000",
        "--lang=es-ES",
        f"--user-agent={_UA}",
        "--disable-blink-features=AutomationControlled",
    ]
    if headless:
        args.append("--headless=new")
    return args


def _try_undetected(headless: bool) -> Any | None:
    try:
        import undetected_chromedriver as uc

        opts = uc.ChromeOptions()
        for arg in _chrome_args(headless):
            opts.add_argument(arg)

        driver = uc.Chrome(options=opts)
        driver.set_page_load_timeout(45)
        driver.implicitly_wait(5)
        log.info("driver_creado", tipo="undetected_chromedriver", headless=headless)
        return driver
    except Exception as exc:
        log.warning("driver_uc_fallback", error=str(exc))
        return None


def _try_standard(headless: bool) -> Any:
    """Fallback a Selenium estándar (requiere webdriver-manager instalado)."""
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service

    try:
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
    except ImportError:
        # webdriver_manager no instalado — intentar con chromedriver en PATH
        service = Service()

    opts = webdriver.ChromeOptions()
    for arg in _chrome_args(headless):
        opts.add_argument(arg)
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(service=service, options=opts)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    driver.set_page_load_timeout(45)
    driver.implicitly_wait(5)
    log.info("driver_creado", tipo="selenium_standard", headless=headless)
    return driver


def quit_driver(driver: Any) -> None:
    """
    Cierra el driver de forma segura.

    Después de quit(), neutraliza __del__ para evitar el OSError/WinError 6
    que undetected_chromedriver lanza cuando el GC intenta cerrar un proceso
    de Chrome que ya fue terminado por nosotros.
    """
    try:
        driver.quit()
    except Exception:
        pass
    finally:
        # UC llama a self.quit() en __del__, lo que falla con WinError 6
        # porque el proceso ya está cerrado. Lo anulamos para silenciar el ruido.
        try:
            driver.__class__.__del__ = lambda self: None
        except Exception:
            pass


def robust_click(driver: Any, element: Any) -> bool:
    """
    Intenta hacer clic en un elemento con tres métodos de fallback.
    Devuelve True si tuvo éxito.
    """
    from selenium.webdriver.common.action_chains import ActionChains

    for method in (
        lambda: element.click(),
        lambda: ActionChains(driver).move_to_element(element).pause(0.1).click(element).perform(),
        lambda: driver.execute_script("arguments[0].click();", element),
    ):
        try:
            method()
            return True
        except Exception:
            continue
    return False


def accept_cookies(driver: Any, timeout: int = 8) -> bool:
    """
    Acepta el banner de cookies de Quantcast en WhoScored si aparece.
    Devuelve True si encontró y aceptó el banner.
    """
    from selenium.webdriver.common.by import By

    keywords = ["acepto", "aceptar", "accept", "agree", "consent"]

    try:
        # Intento 1: botones con texto reconocible
        for el in driver.find_elements(By.XPATH, "//button|//a"):
            text = (el.text or "").strip().lower()
            if text and any(k in text for k in keywords):
                if el.is_displayed() and robust_click(driver, el):
                    time.sleep(0.4)
                    return True

        # Intento 2: selectores CSS conocidos del banner Quantcast
        for css in [
            ".qc-cmp2-summary-buttons button",
            "#qc-cmp2-container .qc-cmp2-summary-buttons button",
            'button[aria-label*="Aceptar"]',
            'button[aria-label*="accept"]',
        ]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, css)
                if el.is_displayed() and robust_click(driver, el):
                    time.sleep(0.4)
                    return True
            except Exception:
                continue
    except Exception:
        pass

    return False