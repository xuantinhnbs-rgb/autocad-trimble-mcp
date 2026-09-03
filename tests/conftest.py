"""
Tiện ích chung cho test.
========================
Nạp cả hai MCP server trong cùng một tiến trình pytest. Hai server đều có
module tên `server`, nên phải nạp bằng `importlib` với tên riêng, không dùng
`import server` trần.

Không test nào ở đây cần AutoCAD hay Trimble Connect đang chạy: cả hai client
đều kết nối lười (lazy), việc đăng ký tool không chạm vào ứng dụng nào.
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
AUTOCAD_DIR = ROOT / "autocad-mcp"
TRIMBLE_DIR = ROOT / "trimble-mcp"

# Marker dùng chung: nạp được server thì phải có Windows (COM / .NET Framework).
# Riêng test bố cục repo thì chạy được ở mọi hệ điều hành.
chi_tren_windows = pytest.mark.skipif(
    sys.platform != "win32", reason="Hai server chỉ chạy trên Windows"
)


def _load_file_as(module_name, path, extra_path):
    """Nạp một file .py thành module có tên chỉ định."""
    if module_name in sys.modules:
        return sys.modules[module_name]
    if str(extra_path) not in sys.path:
        sys.path.insert(0, str(extra_path))
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def autocad_server():
    """Module `autocad-mcp/server.py` đã nạp xong."""
    return _load_file_as("acad_mcp_server", AUTOCAD_DIR / "server.py", AUTOCAD_DIR)


@pytest.fixture(scope="session")
def trimble_server():
    """Module `trimble-mcp/trimble_mcp/server.py` đã nạp xong."""
    if str(TRIMBLE_DIR) not in sys.path:
        sys.path.insert(0, str(TRIMBLE_DIR))
    from trimble_mcp import server

    return server


def list_tools(server_module):
    """Danh sách tool của một server (list_tools là coroutine)."""
    return asyncio.run(server_module.mcp.list_tools())
