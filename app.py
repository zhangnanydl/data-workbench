from __future__ import annotations

import os
import multiprocessing
import sys
import traceback
import ctypes
from pathlib import Path

import webview
from Evtx.Evtx import Evtx as _BundledEvtx  # Ensure the optional parser is included in frozen builds.


_INSTANCE_MUTEX = None


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def main() -> None:
    backend_dir = resource_path("backend")
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    from dataworkbench.bridge import DesktopBridge

    index_path = resource_path("frontend/dist/client/index.html")
    if not index_path.exists():
        raise SystemExit("前端尚未构建，请先在 frontend 目录运行 npm run build。")

    portable_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    # pywebview dispatches exposed API calls away from its native message
    # loop. Keeping a spawned process pool alive beside WebView2 can make the
    # WinForms host stop pumping messages on some Windows builds, so desktop
    # execution stays in those API worker threads instead.
    bridge = DesktopBridge(project_root=Path(os.getenv("DATAWORKBENCH_HOME", portable_root)), use_worker=False)
    window = webview.create_window(
        "数据工坊",
        index_path.as_uri(),
        js_api=bridge,
        width=1440,
        height=960,
        min_size=(1100, 720),
        background_color="#f7f8fa",
    )
    bridge.attach_window(window)
    # The app owns a single native window. WebView2 can leave helper threads
    # alive after that window closes, so terminate only after the closed event.
    def on_closed() -> None:
        bridge.close()
        os._exit(0)

    window.events.closed += on_closed
    webview.start(debug=os.getenv("DATAWORKBENCH_DEBUG") == "1")


def install_crash_log() -> None:
    root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    log_path = root / "data-workbench-crash.log"

    def log_exception(exc_type, exc_value, exc_traceback) -> None:
        log_path.write_text("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)), encoding="utf-8")

    sys.excepthook = log_exception


def ensure_single_instance() -> bool:
    """Keep WebView2 profile access in one process and focus an existing window."""
    global _INSTANCE_MUTEX
    if os.name != "nt":
        return True
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    _INSTANCE_MUTEX = kernel32.CreateMutexW(None, False, "Local\\DataWorkbenchDesktopSingleInstance")
    if kernel32.GetLastError() != 183:
        return True
    user32 = ctypes.windll.user32
    handle = user32.FindWindowW(None, "数据工坊")
    if handle:
        user32.ShowWindowAsync(handle, 9)
        user32.SetForegroundWindow(handle)
    return False


if __name__ == "__main__":
    multiprocessing.freeze_support()
    install_crash_log()
    if ensure_single_instance():
        main()
