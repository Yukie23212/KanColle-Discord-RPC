# Copyright (c) 2026 harunoyukie
# Licensed under CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/)

import queue
import threading
import sys

from .app import App, resource_path
from .constants import APP_TITLE
from .web_ui import start_web_server




def _colorref(hex_color):
    value = str(hex_color).lstrip("#")
    if len(value) != 6:
        raise ValueError("Expected RRGGBB color")
    r = int(value[0:2], 16)
    g = int(value[2:4], 16)
    b = int(value[4:6], 16)
    # Windows COLORREF stores RGB as 0x00BBGGRR.
    return (b << 16) | (g << 8) | r


def _set_native_titlebar_theme(window, light):
    """Set the Windows 11 DWM caption/text/border colors to match the web theme."""
    if sys.platform != "win32":
        return False
    native = getattr(window, "native", None)
    if native is None:
        return False
    try:
        import ctypes

        hwnd = native.Handle.ToInt32()
        dwmapi = ctypes.windll.dwmapi

        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        DWMWA_BORDER_COLOR = 34
        DWMWA_CAPTION_COLOR = 35
        DWMWA_TEXT_COLOR = 36

        caption = _colorref("#f4f7fb" if light else "#080b12")
        text = _colorref("#182233" if light else "#eaf0f8")
        border = _colorref("#d9e1ec" if light else "#263147")

        def set_attr(attribute, value, ctype):
            boxed = ctype(value)
            return dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(boxed), ctypes.sizeof(boxed)
            )

        set_attr(DWMWA_USE_IMMERSIVE_DARK_MODE, 0 if light else 1, ctypes.c_int)
        set_attr(DWMWA_CAPTION_COLOR, caption, ctypes.c_uint)
        set_attr(DWMWA_TEXT_COLOR, text, ctypes.c_uint)
        set_attr(DWMWA_BORDER_COLOR, border, ctypes.c_uint)
        return True
    except Exception:
        return False


def _start_backend(ready_queue):
    try:
        app = App()
        app.withdraw()
        ready_queue.put(("ok", app))
        app.mainloop()
    except BaseException as exc:
        try:
            ready_queue.put(("error", exc))
        except Exception:
            pass


def _request_backend_shutdown(app, timeout=5):
    done = threading.Event()
    box = {}
    app.web_command_queue.put((app._quit_app, done, box))
    if not done.wait(timeout):
        return False
    return "error" not in box


def run():
    try:
        import webview
    except ImportError as exc:
        raise SystemExit(
            "pywebview is required for the HTML desktop interface. "
            "Install it with: pip install pywebview"
        ) from exc

    ready_queue = queue.Queue(maxsize=1)
    backend_thread = threading.Thread(
        target=_start_backend,
        args=(ready_queue,),
        name="TkBackend",
        daemon=True,
    )
    backend_thread.start()

    try:
        kind, value = ready_queue.get(timeout=15)
    except queue.Empty as exc:
        raise SystemExit("The Python backend did not start within 15 seconds.") from exc

    if kind != "ok":
        raise SystemExit(f"Could not start the Python backend: {value}")

    app = value
    server = None
    close_requested = threading.Event()
    close_watcher = None

    try:
        # Keep the existing HTTP bridge for now. The browser is replaced by
        # pywebview, while the backend/API remains unchanged and easy to debug.
        server, url = start_web_server(app, open_browser=False)
        app.web_server = server
        app.web_server_url = url
        app.webview_close_event = close_requested

        window = webview.create_window(
            APP_TITLE,
            url,
            width=1200,
            height=800,
            min_size=(980, 620),
            resizable=True,
            text_select=True,
        )

        def set_titlebar_theme(light):
            native = getattr(window, "native", None)
            if native is None:
                return False

            def _apply():
                return _set_native_titlebar_theme(window, bool(light))

            try:
                if native.InvokeRequired:
                    from System import Func, Type  # type: ignore[reportMissingImports]
                    native.Invoke(Func[Type](_apply))
                else:
                    _apply()
                return True
            except Exception:
                return _set_native_titlebar_theme(window, bool(light))

        # The default web theme is dark; the browser-side theme code will
        # immediately synchronize a saved light preference when the page loads.
        set_titlebar_theme(False)

        from .web_ui import _bring_webview_to_front, _set_webview_theme
        _set_webview_theme.theme_callback = set_titlebar_theme

        def focus_webview_window():
            """Activate the native pywebview window from its GUI thread."""
            native = getattr(window, "native", None)
            if native is None:
                return False

            def _activate():
                was_topmost = bool(native.TopMost)
                try:
                    native.TopMost = True
                    native.Show()
                    native.BringToFront()
                    native.Activate()
                    native.Focus()

                    try:
                        import ctypes
                        ctypes.windll.user32.SetForegroundWindow(native.Handle.ToInt32())
                    except Exception:
                        pass
                finally:
                    if not was_topmost:
                        def _clear_topmost_on_gui():
                            try:
                                native.TopMost = False
                            except Exception:
                                pass

                        def _clear_topmost():
                            try:
                                if native.InvokeRequired:
                                    from System import Func, Type  # type: ignore[reportMissingImports]
                                    native.Invoke(Func[Type](_clear_topmost_on_gui))
                                else:
                                    _clear_topmost_on_gui()
                            except Exception:
                                pass

                        timer = threading.Timer(0.35, _clear_topmost)
                        timer.daemon = True
                        timer.start()

            if native.InvokeRequired:
                from System import Func, Type  # type: ignore[reportMissingImports]
                native.Invoke(Func[Type](_activate))
            else:
                _activate()
            return True

        _bring_webview_to_front.focus_callback = focus_webview_window

        def close_when_requested():
            close_requested.wait()
            try:
                window.destroy()
            except Exception:
                pass

        close_watcher = threading.Thread(
            target=close_when_requested,
            name="PyWebViewCloseWatcher",
            daemon=True,
        )
        close_watcher.start()

        debug = "--web-debug" in sys.argv
        webview.start(debug=debug)
    finally:
        close_requested.set()
        if server is not None:
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                pass

        if backend_thread.is_alive():
            _request_backend_shutdown(app)
            backend_thread.join(timeout=5)

    return 0
