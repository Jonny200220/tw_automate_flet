# """Gestión de Playwright en un hilo dedicado con su propio event loop.

# Por qué un hilo aparte: en Windows, uvicorn con ``--reload`` (o varios workers)
# usa un ``SelectorEventLoop``, que NO soporta subprocesos. Playwright necesita
# lanzar el navegador como subproceso, así que fallaría con ``NotImplementedError``
# si corriera en el loop de uvicorn.

# Solución: Playwright vive en su propio hilo con un ``ProactorEventLoop``, y las
# corrutinas de scraping se envían a ese loop desde el loop de la app mediante
# ``run_coroutine_threadsafe`` + ``wrap_future`` (para poder ``await`` el resultado
# de forma natural). Un único navegador se comparte entre jobs; cada job usa su
# propio contexto aislado.
# """

# import asyncio
# import logging
# import sys
# import threading
# from collections.abc import Awaitable, Callable
# from concurrent.futures import Future as ConcurrentFuture
# from pathlib import Path
# from typing import TypeVar

# from playwright.async_api import Browser, Page, Playwright, async_playwright

# logger = logging.getLogger("towell.automation.browser")

# T = TypeVar("T")


# def _new_event_loop() -> asyncio.AbstractEventLoop:
#     """Crea un event loop que soporta subprocesos (Proactor en Windows)."""
#     if sys.platform == "win32":
#         return asyncio.ProactorEventLoop()
#     return asyncio.new_event_loop()


# class BrowserManager:
#     """Administra un navegador Chromium compartido en un hilo/loop propio."""

#     def __init__(
#         self,
#         headless: bool = True,
#         timeout_ms: int = 30_000,
#         slow_mo_ms: int = 0,
#     ) -> None:
#         self._headless = headless
#         self._timeout_ms = timeout_ms
#         self._slow_mo_ms = slow_mo_ms
#         self._loop: asyncio.AbstractEventLoop | None = None
#         self._thread: threading.Thread | None = None
#         self._playwright: Playwright | None = None
#         self._browser: Browser | None = None

#     async def start(self) -> None:
#         """Arranca el hilo de Playwright y lanza el navegador."""
#         ready: ConcurrentFuture[None] = ConcurrentFuture()
#         self._thread = threading.Thread(
#             target=self._thread_main,
#             args=(ready,),
#             name="playwright-loop",
#             daemon=True,
#         )
#         self._thread.start()
#         await asyncio.wrap_future(ready)  # espera a que el loop del hilo esté listo
#         await self._submit(self._launch())

#     def _thread_main(self, ready: ConcurrentFuture[None]) -> None:
#         loop = _new_event_loop()
#         self._loop = loop
#         asyncio.set_event_loop(loop)
#         loop.call_soon(ready.set_result, None)
#         try:
#             loop.run_forever()
#         finally:
#             loop.close()

#     async def _launch(self) -> None:
#         logger.info("Iniciando Playwright (headless=%s)", self._headless)
#         self._playwright = await async_playwright().start()
#         self._browser = await self._playwright.chromium.launch(
#             headless=self._headless,
#             slow_mo=self._slow_mo_ms,
#         )

#     async def _close(self) -> None:
#         if self._browser is not None:
#             await self._browser.close()
#             self._browser = None
#         if self._playwright is not None:
#             await self._playwright.stop()
#             self._playwright = None
#         logger.info("Playwright detenido")

#     async def stop(self) -> None:
#         """Cierra el navegador y detiene el hilo/loop de Playwright."""
#         if self._loop is None:
#             return
#         try:
#             await self._submit(self._close())
#         finally:
#             self._loop.call_soon_threadsafe(self._loop.stop)
#             if self._thread is not None:
#                 self._thread.join(timeout=10)
#             self._loop = None
#             self._thread = None

#     def _submit(self, coro: Awaitable[T]) -> asyncio.Future[T]:
#         """Programa una corrutina en el loop de Playwright y permite await
#         desde el loop llamante (el de la app)."""
#         if self._loop is None:
#             raise RuntimeError("BrowserManager no inicializado; llama a start() primero")
#         concurrent_future = asyncio.run_coroutine_threadsafe(coro, self._loop)  # type: ignore[arg-type]
#         return asyncio.wrap_future(concurrent_future)

#     async def run_scrape(
#         self,
#         runner: Callable[[Page, Path], Awaitable[T]],
#         download_dir: Path,
#     ) -> T:
#         """Abre un contexto aislado, cede una página al ``runner`` y limpia.

#         Todo el scraping ocurre dentro del loop de Playwright, por lo que la
#         página y sus llamadas ``await`` viven en el loop correcto.
#         """
#         return await self._submit(self._scrape(runner, download_dir))

#     async def _scrape(
#         self,
#         runner: Callable[[Page, Path], Awaitable[T]],
#         download_dir: Path,
#     ) -> T:
#         if self._browser is None:
#             raise RuntimeError("Navegador no inicializado")
#         context = await self._browser.new_context(
#             accept_downloads=True,
#             viewport={"width": 1920, "height": 1080},
#         )
#         context.set_default_timeout(self._timeout_ms)
#         page = await context.new_page()
#         try:
#             return await runner(page, download_dir)
#         except Exception:
#             # Deja evidencia visual del punto de fallo para depurar portales frágiles.
#             try:
#                 shot = download_dir / "error.png"
#                 await page.screenshot(path=str(shot), full_page=True)
#                 logger.error("Captura del error guardada en %s", shot)
#             except Exception:  # noqa: BLE001 - la captura es best-effort
#                 logger.debug("No se pudo guardar la captura de error")
#             raise
#         finally:
#             await context.close()
