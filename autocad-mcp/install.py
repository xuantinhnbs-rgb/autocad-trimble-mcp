"""
Bộ cài đặt AutoCAD MCP Server
=============================
Chạy MỘT lệnh duy nhất trên máy mới:

    python install.py

Script sẽ tự làm hết: kiểm tra môi trường, cài thư viện, dò AutoCAD, rồi sinh file
cấu hình .mcp.json với đúng đường dẫn của máy đó.

Tùy chọn:
    python install.py --no-deps          bỏ qua bước cài thư viện
    python install.py --claude-desktop   ghi thêm cấu hình cho Claude Desktop
"""

import os
import sys
import json
import subprocess

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
# .mcp.json nằm ở gốc dự án (thư mục cha), không nằm cạnh install.py
PROJECT_ROOT = os.path.dirname(HERE)
SERVER = os.path.join(HERE, "server.py")
SERVER_NAME = "autocad-2022"

ok_count = 0
problems: list[str] = []


def step(title: str) -> None:
    print(f"\n{'=' * 66}\n{title}\n{'=' * 66}")


def good(msg: str) -> None:
    global ok_count
    ok_count += 1
    print(f"  [OK]   {msg}")


def warn(msg: str) -> None:
    print(f"  [!]    {msg}")


def fail(msg: str) -> None:
    problems.append(msg)
    print(f"  [LỖI]  {msg}")


def pick_python() -> str:
    """Chọn trình thông dịch để chạy server.

    Ưu tiên pythonw.exe: nó không bật cửa sổ console đen mỗi lần AI gọi tool.
    """
    exe = sys.executable
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return pythonw if os.path.exists(pythonw) else exe


def main() -> int:
    args = set(sys.argv[1:])
    print("╔" + "═" * 64 + "╗")
    print("║" + "  BỘ CÀI ĐẶT AUTOCAD MCP SERVER".ljust(64) + "║")
    print("╚" + "═" * 64 + "╝")

    # ---------------------------------------------------------------- 1
    step("1. KIỂM TRA MÔI TRƯỜNG")
    if not sys.platform.startswith("win"):
        fail(f"Chỉ chạy được trên Windows (đang là '{sys.platform}'). "
             "AutoCAD điều khiển qua COM, không có trên macOS/Linux.")
        return 1
    good(f"Windows - {sys.getwindowsversion().major}.{sys.getwindowsversion().minor}")

    if sys.version_info < (3, 10):
        fail(f"Cần Python 3.10 trở lên, đang dùng {sys.version.split()[0]}. "
             "Tải tại https://www.python.org/downloads/")
        return 1
    good(f"Python {sys.version.split()[0]} tại {sys.executable}")

    if not os.path.exists(SERVER):
        fail(f"Không thấy server.py cạnh install.py (tìm ở: {SERVER}). "
             "Hãy giải nén trọn gói rồi chạy lại.")
        return 1
    good(f"Thư mục cài đặt: {HERE}")

    # ---------------------------------------------------------------- 2
    step("2. CÀI THƯ VIỆN PHỤ THUỘC")
    req = os.path.join(HERE, "requirements.txt")
    if "--no-deps" in args:
        warn("Bỏ qua theo yêu cầu (--no-deps)")
    elif not os.path.exists(req):
        fail("Không thấy requirements.txt")
    else:
        print(f"  Đang chạy: pip install -r requirements.txt ...")
        proc = subprocess.run([sys.executable, "-m", "pip", "install", "-r", req],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
        if proc.returncode == 0:
            good("Đã cài xong thư viện")
        else:
            fail("pip cài thất bại:\n" + (proc.stderr or proc.stdout or "")[-800:])

    # ---------------------------------------------------------------- 3
    step("3. KIỂM TRA THƯ VIỆN NHẬP ĐƯỢC")
    for module, hint in (("win32com.client", "pip install pywin32"),
                         ("pythoncom", "pip install pywin32"),
                         ("mcp.server.mcpserver", "pip install --upgrade \"mcp>=2.1.0\"")):
        try:
            __import__(module)
            good(f"import {module}")
        except Exception as exc:
            fail(f"Không import được {module} ({exc}). Khắc phục: {hint}")

    # ---------------------------------------------------------------- 4
    step("4. DÒ AUTOCAD")
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        app = None
        for prog_id in ("AutoCAD.Application.24.1", "AutoCAD.Application.24",
                        "AutoCAD.Application"):
            try:
                app = win32com.client.GetActiveObject(prog_id)
                break
            except Exception:
                continue
        if app is None:
            warn("Chưa thấy AutoCAD nào đang chạy. Không sao - đây không phải lỗi cài đặt, "
                 "chỉ cần MỞ AutoCAD trước khi dùng.")
        else:
            good(f"Đã bắt được {app.Name} phiên bản {app.Version} "
                 f"({int(app.Documents.Count)} bản vẽ đang mở)")
    except Exception as exc:
        warn(f"Không kiểm tra được AutoCAD lúc này: {exc}")

    # ---------------------------------------------------------------- 5
    step("5. SINH FILE CẤU HÌNH MCP")
    entry = {
        "command": pick_python(),
        "args": [SERVER],
        "cwd": HERE,
        "env": {"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"},
    }

    target = os.path.join(PROJECT_ROOT, ".mcp.json")
    cfg = {}
    if os.path.exists(target):
        try:
            with open(target, encoding="utf-8") as fh:
                cfg = json.load(fh)
        except Exception:
            cfg = {}          # file hỏng thì ghi đè, không để chặn cài đặt
    cfg.setdefault("mcpServers", {})[SERVER_NAME] = entry
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)
    good(f"Đã ghi {target}")
    print(f"         command : {entry['command']}")
    print(f"         args    : {entry['args'][0]}")

    if "--claude-desktop" in args:
        appdata = os.getenv("APPDATA", "")
        if not appdata:
            warn("Không đọc được biến môi trường APPDATA, bỏ qua Claude Desktop")
        else:
            path = os.path.join(appdata, "Claude", "claude_desktop_config.json")
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                data = {}
                if os.path.exists(path):
                    try:
                        with open(path, encoding="utf-8") as fh:
                            data = json.load(fh)
                    except Exception:
                        data = {}
                data.setdefault("mcpServers", {})[SERVER_NAME] = entry
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=2, ensure_ascii=False)
                good(f"Đã ghi cấu hình Claude Desktop: {path}")
            except Exception as exc:
                warn(f"Không ghi được cấu hình Claude Desktop: {exc}")

    # ---------------------------------------------------------------- 6
    step("6. CHẠY THỬ SERVER")
    try:
        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, r'%s');"
             "import asyncio, server;"
             "print(len(asyncio.run(server.mcp.list_tools())))" % HERE],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120, cwd=HERE)
        count = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
        if proc.returncode == 0 and count.isdigit():
            good(f"Server nạp được {count} tool")
        else:
            fail("Server không khởi động được:\n"
                 + (proc.stderr or proc.stdout or "")[-800:])
    except Exception as exc:
        fail(f"Không chạy thử được server: {exc}")

    # ---------------------------------------------------------------- Kết
    step("KẾT QUẢ")
    if problems:
        print(f"  Có {len(problems)} vấn đề cần xử lý:")
        for p in problems:
            print(f"    - {p.splitlines()[0]}")
        return 1

    print(f"  Cài đặt thành công ({ok_count} mục đạt).\n")
    print("  CÁCH DÙNG:")
    print("    1. Mở AutoCAD và mở ít nhất một bản vẽ.")
    print(f"    2. Mở Claude Code tại thư mục: {PROJECT_ROOT}")
    print("       (hoặc khởi động lại Claude Desktop nếu dùng --claude-desktop)")
    print("    3. Bảo AI: \"kiểm tra kết nối AutoCAD\" để xác nhận.\n")
    print("  Muốn kiểm tra riêng phần COM:  python test_connection.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
