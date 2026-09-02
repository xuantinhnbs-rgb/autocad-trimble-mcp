"""Client Python cho cau noi .NET toi Trimble Connect for Desktop.

Trimble Connect for Desktop khong co COM API; no expose mot Desktop .NET API
(Trimble.Connect.Desktop.API.dll, .NET Framework 4.8) qua kenh IPC noi bo.
Python 3.14 chua co pythonnet nen module nay dung mot cau noi nho viet bang C#:

    Python  --(JSON-lines qua stdin/stdout)-->  TrimbleBridge.exe  --> Trimble Connect

TrimbleBridge.exe duoc bien dich tu dong bang csc.exe cua .NET Framework
(co san trong moi ban Windows), khong can cai Visual Studio hay .NET SDK.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = ["TrimbleBridge", "TrimbleError", "get_bridge"]

PACKAGE_DIR = Path(__file__).resolve().parent
BRIDGE_DIR = PACKAGE_DIR / "bridge"
SOURCES = [BRIDGE_DIR / "TrimbleBridge.cs", BRIDGE_DIR / "Session.cs"]
EXE_PATH = BRIDGE_DIR / "TrimbleBridge.exe"

DEFAULT_INSTALL_DIRS = [
    Path(r"C:\Program Files\Trimble\Trimble Connect"),
    Path(r"C:\Program Files (x86)\Trimble\Trimble Connect"),
]

# Cac DLL bat buoc phai co trong thu muc cai dat de bien dich duoc.
REQUIRED_DLLS = [
    "Trimble.Connect.Desktop.API.dll",
    "Trimble.Connect.Desktop.API.Common.dll",
    "Trimble.Connect.Desktop.ExternalInterface.Services.dll",
]

CALL_TIMEOUT = 180.0  # giay; du rong cho cac truy van model lon


class TrimbleError(RuntimeError):
    """Loi tra ve tu Trimble Connect hoac tu chinh cau noi."""


# ---------------------------------------------------------------------------
# Dinh vi va bien dich
# ---------------------------------------------------------------------------

def find_install_dir() -> Path:
    """Tim thu muc cai Trimble Connect for Desktop."""
    env = os.environ.get("TRIMBLE_CONNECT_DIR")
    if env and (Path(env) / REQUIRED_DLLS[0]).exists():
        return Path(env)

    for candidate in DEFAULT_INSTALL_DIRS:
        if (candidate / REQUIRED_DLLS[0]).exists():
            return candidate

    raise TrimbleError(
        "Khong tim thay Trimble Connect for Desktop. Da tim trong: "
        + "; ".join(str(p) for p in DEFAULT_INSTALL_DIRS)
        + ". Neu cai o cho khac, dat bien moi truong TRIMBLE_CONNECT_DIR tro toi "
        "thu muc chua Trimble.Connect.Desktop.API.dll."
    )


def find_csc() -> Path:
    """Tim trinh bien dich C# cua .NET Framework (co san trong Windows)."""
    root = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET"
    candidates = [
        root / "Framework64" / "v4.0.30319" / "csc.exe",
        root / "Framework" / "v4.0.30319" / "csc.exe",
    ]
    for csc in candidates:
        if csc.exists():
            return csc
    raise TrimbleError(
        "Khong tim thay csc.exe cua .NET Framework 4.x. Can bat tinh nang "
        "'.NET Framework 4.8' trong Windows Features de bien dich cau noi."
    )


def _needs_build() -> bool:
    if not EXE_PATH.exists():
        return True
    exe_mtime = EXE_PATH.stat().st_mtime
    return any(src.stat().st_mtime > exe_mtime for src in SOURCES)


def build_bridge(install_dir: Optional[Path] = None, force: bool = False) -> Path:
    """Bien dich TrimbleBridge.exe neu chua co hoac ma nguon da doi."""
    install_dir = install_dir or find_install_dir()

    if not force and not _needs_build():
        return EXE_PATH

    missing = [d for d in REQUIRED_DLLS if not (install_dir / d).exists()]
    if missing:
        raise TrimbleError(
            f"Thieu DLL trong {install_dir}: {', '.join(missing)}. "
            "Ban Trimble Connect for Desktop nay co the khong kem Desktop API."
        )

    csc = find_csc()
    cmd = [
        str(csc),
        "/nologo",
        "/target:exe",
        "/platform:x64",
        "/optimize+",
        f"/out:{EXE_PATH}",
        "/reference:System.dll",
        "/reference:System.Core.dll",
        "/reference:System.Drawing.dll",
        "/reference:System.Web.Extensions.dll",
    ]
    cmd += [f"/reference:{install_dir / dll}" for dll in REQUIRED_DLLS]
    cmd += [str(src) for src in SOURCES]

    proc = subprocess.run(
        cmd,
        cwd=str(BRIDGE_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0 or not EXE_PATH.exists():
        raise TrimbleError(
            "Bien dich TrimbleBridge.exe that bai:\n"
            + (proc.stdout or "")
            + (proc.stderr or "")
        )

    _write_app_config(install_dir)
    return EXE_PATH


def _write_app_config(install_dir: Path) -> None:
    """Ke thua binding redirect cua TrimbleConnect.exe cho cau noi.

    Cac DLL cua Trimble tham chieu Newtonsoft.Json, JWT... theo phien ban cu;
    khong co redirect thi CLR se nem FileLoadException khi nap chung.
    """
    source = install_dir / "TrimbleConnect.exe.config"
    target = Path(str(EXE_PATH) + ".config")
    if not source.exists():
        return
    try:
        text = source.read_text(encoding="utf-8", errors="replace")
        start = text.find("<runtime>")
        end = text.find("</runtime>")
        runtime = text[start : end + len("</runtime>")] if start != -1 and end != -1 else ""
        target.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<configuration>\n"
            '  <startup><supportedRuntime version="v4.0" '
            'sku=".NETFramework,Version=v4.8" /></startup>\n'
            f"  {runtime}\n"
            "</configuration>\n",
            encoding="utf-8",
        )
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Cau noi
# ---------------------------------------------------------------------------

CREATE_NO_WINDOW = 0x08000000


class TrimbleBridge:
    """Giu mot TrimbleBridge.exe song lau dai va goi lenh vao do.

    Ket noi toi Trimble Connect phai duoc giu nguyen giua cac lenh, nen tien
    trinh nay ton tai suot vong doi cua MCP server.
    """

    def __init__(self, install_dir: Optional[Path] = None) -> None:
        self._install_dir = install_dir
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._replies: "queue.Queue[str]" = queue.Queue()
        self._reader: Optional[threading.Thread] = None
        self._next_id = 0
        self._log_path = Path(tempfile.gettempdir()) / "trimble_mcp_bridge.err.log"

    # -- vong doi tien trinh ------------------------------------------------

    def _start(self) -> None:
        install_dir = self._install_dir or find_install_dir()
        exe = build_bridge(install_dir)

        log = open(self._log_path, "w", encoding="utf-8")
        self._proc = subprocess.Popen(
            [str(exe), "--install-dir", str(install_dir)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log,
            cwd=str(BRIDGE_DIR),
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=CREATE_NO_WINDOW,
        )
        self._replies = queue.Queue()
        self._reader = threading.Thread(target=self._pump, args=(self._proc,), daemon=True)
        self._reader.start()

    def _pump(self, proc: subprocess.Popen) -> None:
        try:
            for line in proc.stdout:  # type: ignore[union-attr]
                line = line.strip()
                if line:
                    self._replies.put(line)
        except (OSError, ValueError):
            pass
        finally:
            self._replies.put("")  # danh dau tien trinh da chet

    def _alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def close(self) -> None:
        with self._lock:
            proc, self._proc = self._proc, None
            if proc is None:
                return
            try:
                if proc.stdin:
                    proc.stdin.close()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    # -- goi lenh -----------------------------------------------------------

    def call(self, cmd: str, _timeout: float = CALL_TIMEOUT, **args: Any) -> Any:
        """Chay mot lenh tren cau noi va tra ve phan `result`.

        Tham so cho phan hoi ten la `_timeout` de khong dam vao tham so
        `timeout` ma chinh Trimble API dung khi do tim instance.
        """
        payload = {k: v for k, v in args.items() if v is not None}

        with self._lock:
            if not self._alive():
                self._start()

            self._next_id += 1
            request = {"id": self._next_id, "cmd": cmd, "args": payload}

            assert self._proc is not None and self._proc.stdin is not None
            try:
                self._proc.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                self._proc.stdin.flush()
            except (OSError, ValueError) as exc:
                self._proc = None
                raise TrimbleError(f"Cau noi da dong khi gui lenh '{cmd}': {exc}") from exc

            line = self._await_reply(cmd, _timeout)

        response = json.loads(line)
        if not response.get("ok"):
            raise TrimbleError(response.get("error") or f"Lenh '{cmd}' that bai.")
        return response.get("result")

    def _await_reply(self, cmd: str, timeout: float) -> str:
        try:
            line = self._replies.get(timeout=timeout)
        except queue.Empty:
            raise TrimbleError(
                f"Trimble Connect khong phan hoi lenh '{cmd}' sau {timeout:.0f}s. "
                "Ung dung co the dang ban (dang nap model) hoac dang mo hop thoai cho thao tac."
            ) from None

        if line == "":
            detail = ""
            try:
                detail = self._log_path.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                pass
            self._proc = None
            raise TrimbleError(
                f"Cau noi toi Trimble Connect da thoat khi chay '{cmd}'."
                + (f" Chi tiet: {detail[:2000]}" if detail else "")
            )
        return line


# ---------------------------------------------------------------------------
# Instance dung chung
# ---------------------------------------------------------------------------

_bridge: Optional[TrimbleBridge] = None
_bridge_lock = threading.Lock()


def get_bridge() -> TrimbleBridge:
    global _bridge
    with _bridge_lock:
        if _bridge is None:
            _bridge = TrimbleBridge()
        return _bridge


def call(cmd: str, **args: Any) -> Any:
    """Loi tat cho get_bridge().call(...)."""
    return get_bridge().call(cmd, **args)


if __name__ == "__main__":
    # Kiem tra nhanh: python -m trimble_mcp.trimble_client [lenh] [json-args]
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    kwargs: Dict[str, Any] = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    try:
        print(json.dumps(call(command, **kwargs), indent=2, ensure_ascii=False))
    except TrimbleError as exc:
        print(f"LOI: {exc}", file=sys.stderr)
        raise SystemExit(1)
