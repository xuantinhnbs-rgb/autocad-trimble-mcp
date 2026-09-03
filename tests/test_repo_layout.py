"""
Kiểm tra bố cục repo và cấu hình mẫu.
=====================================
Những lỗi bắt ở đây là loại chỉ lộ ra lúc người khác clone về: file mẫu sai
JSON, `install.py` trỏ vào script không tồn tại, thiếu README hay
requirements ở một thư mục server, hay `.mcp.json` của máy bị commit lên.
Không cần Windows để chạy nhóm test này.
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SERVER_FOLDERS = ["autocad-mcp", "trimble-mcp"]


@pytest.fixture(scope="module")
def example_config():
    with open(ROOT / ".mcp.json.example", encoding="utf-8") as fh:
        return json.load(fh)


def test_file_mau_co_dung_hai_server(example_config):
    assert set(example_config["mcpServers"]) == {"autocad-2022", "trimble-connect"}


def test_moi_muc_trong_file_mau_du_khoa_can_thiet(example_config):
    for name, entry in example_config["mcpServers"].items():
        assert set(entry) >= {"command", "args", "cwd", "env"}, name
        assert entry["args"], name
        # stdio của MCP là văn bản UTF-8; thiếu hai biến này là gõ tiếng Việt ra rác.
        assert entry["env"].get("PYTHONIOENCODING") == "utf-8", name
        assert entry["env"].get("PYTHONUNBUFFERED") == "1", name


def test_install_py_tro_dung_vao_script_co_that():
    """`install.py` khai báo đường dẫn server bằng tay — kiểm tra nó chưa lệch."""
    import sys

    sys.path.insert(0, str(ROOT))
    import install

    for name, cfg in install.SERVERS.items():
        script = ROOT / cfg["folder"] / cfg["script"]
        assert script.is_file(), "%s -> thiếu %s" % (name, script)


def test_ten_server_trong_install_py_khop_voi_file_mau(example_config):
    import sys

    sys.path.insert(0, str(ROOT))
    import install

    assert set(install.SERVERS) == set(example_config["mcpServers"])


@pytest.mark.parametrize("folder", SERVER_FOLDERS)
def test_moi_thu_muc_server_tu_chua_du_tai_lieu_va_phu_thuoc(folder):
    """Mỗi thư mục server phải gửi đi độc lập được, nên cần đủ README + requirements."""
    assert (ROOT / folder / "README.md").is_file()
    assert (ROOT / folder / "requirements.txt").is_file()


def test_gitignore_chan_cau_hinh_rieng_cua_may():
    """`.mcp.json` chứa đường dẫn tuyệt đối, lỡ commit lên là hỏng máy người khác."""
    noi_dung = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for muc in [".mcp.json", "__pycache__/", "TrimbleBridge.exe"]:
        assert muc in noi_dung, muc


def test_khong_commit_cau_hinh_thuc_te_hay_cau_noi_da_bien_dich():
    for path in [".mcp.json", "trimble-mcp/trimble_mcp/bridge/TrimbleBridge.exe"]:
        import subprocess

        out = subprocess.run(
            ["git", "ls-files", "--error-unmatch", path],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert out.returncode != 0, "%s đang bị theo dõi bởi git" % path
