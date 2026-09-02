"""
Cài đặt MCP server cho AutoCAD và Trimble Connect.
==================================================
Dò đường dẫn của chính máy đang chạy rồi sinh ra file `.mcp.json` ở gốc dự án,
nên chép dự án đi đâu, đổi tên thư mục hay dùng Python bản nào cũng chạy đúng.

    python install.py                  # cấu hình cả hai server
    python install.py --autocad        # chỉ AutoCAD
    python install.py --trimble        # chỉ Trimble Connect
    python install.py --claude-desktop # ghi thêm vào config của Claude Desktop
    python install.py --check          # chỉ kiểm tra, không ghi gì

Muốn kiểm tra sâu riêng phần AutoCAD (COM, bản vẽ đang mở) thì chạy
`python autocad-mcp/install.py`.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Mỗi server: thư mục con, file khởi chạy, và gói python bắt buộc
SERVERS = {
    "autocad-2022": {
        "folder": "autocad-mcp",
        "script": "server.py",
        "label": "AutoCAD 2022",
        "needs": ["mcp", "win32com"],
        "app": "AutoCAD 2022 trở lên",
    },
    "trimble-connect": {
        "folder": "trimble-mcp",
        "script": "trimble_server.py",
        "label": "Trimble Connect",
        "needs": ["mcp"],
        "app": "Trimble Connect for Desktop + .NET Framework 4.x",
    },
}

OK, WARN, BAD = "  [OK]  ", "  [!]   ", "  [X]  "


def say(mark, msg):
    print(mark + msg)


def step(title):
    print("\n" + "=" * 62 + "\n  " + title + "\n" + "=" * 62)


def python_exe():
    """Đường dẫn python.exe (không dùng pythonw.exe: MCP stdio cần stdout)."""
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        candidate = exe[: -len("pythonw.exe")] + "python.exe"
        if os.path.exists(candidate):
            return candidate
    return exe


def as_json_path(*parts):
    """Ghép đường dẫn và đổi sang dấu / — JSON khỏi phải escape dấu gạch ngược."""
    return os.path.join(*parts).replace("\\", "/")


def check_module(name):
    return (
        subprocess.run(
            [python_exe(), "-c", "import " + name],
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


def entry_for(cfg):
    """Sinh một mục mcpServers với đường dẫn tuyệt đối của máy này."""
    folder = os.path.join(HERE, cfg["folder"])
    return {
        "command": python_exe().replace("\\", "/"),
        "args": [as_json_path(folder, cfg["script"])],
        "cwd": folder.replace("\\", "/"),
        "env": {"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"},
    }


def load_test(name, cfg):
    """Nạp thử server và đếm số tool — bắt lỗi thiếu thư viện ngay lúc cài."""
    folder = os.path.join(HERE, cfg["folder"])
    module = os.path.splitext(cfg["script"])[0]
    code = (
        "import sys, asyncio; sys.path.insert(0, r'%s');"
        "import %s as m;"
        "srv = getattr(m, 'mcp', None) or __import__('%s').mcp;"
        "print(len(asyncio.run(srv.list_tools())))" % (folder, module, module)
    )
    if name == "trimble-connect":
        code = (
            "import sys, asyncio; sys.path.insert(0, r'%s');"
            "from trimble_mcp import server;"
            "print(len(asyncio.run(server.mcp.list_tools())))" % folder
        )
    try:
        proc = subprocess.run(
            [python_exe(), "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            cwd=folder,
        )
    except Exception as exc:
        return None, str(exc)
    out = (proc.stdout or "").strip().splitlines()
    count = out[-1] if out else ""
    if proc.returncode == 0 and count.isdigit():
        return int(count), None
    return None, (proc.stderr or proc.stdout or "")[-500:]


def merge_into(path, entries):
    """Ghi các mục vào file cấu hình, giữ nguyên những server khác đã có sẵn."""
    cfg = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                cfg = json.load(fh)
        except Exception:
            cfg = {}  # file hỏng thì ghi đè, không để chặn việc cài
    cfg.setdefault("mcpServers", {}).update(entries)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def main():
    args = sys.argv[1:]
    check_only = "--check" in args
    wanted = [n for n, c in SERVERS.items() if "--" + c["folder"].split("-")[0] in args]
    if not wanted:
        wanted = list(SERVERS)

    step("1. MOI TRUONG")
    say(OK, "Python  : %s" % sys.version.split()[0])
    say(OK, "Thuc thi: %s" % python_exe())
    say(OK, "Du an   : %s" % HERE)
    if os.name != "nt":
        say(BAD, "Ca hai server chi chay tren Windows.")
        return 1

    step("2. THU VIEN")
    missing = set()
    for name in wanted:
        for mod in SERVERS[name]["needs"]:
            if check_module(mod):
                say(OK, "%-10s co san" % mod)
            else:
                say(BAD, "%-10s CHUA CO" % mod)
                missing.add(SERVERS[name]["folder"])
    for folder in sorted(missing):
        say(WARN, "Chay: pip install -r %s/requirements.txt" % folder)
    if missing:
        return 1

    step("3. NAP THU SERVER")
    entries, failed = {}, []
    for name in wanted:
        cfg = SERVERS[name]
        script = os.path.join(HERE, cfg["folder"], cfg["script"])
        if not os.path.exists(script):
            say(BAD, "%-16s khong thay %s" % (name, script))
            failed.append(name)
            continue
        count, err = load_test(name, cfg)
        if count is None:
            say(BAD, "%-16s khong nap duoc:\n%s" % (name, err))
            failed.append(name)
        else:
            say(OK, "%-16s nap duoc %d tool" % (name, count))
            entries[name] = entry_for(cfg)

    if not entries:
        return 1

    if check_only:
        say(WARN, "Che do --check: khong ghi file cau hinh nao.")
        return 0 if not failed else 1

    step("4. GHI CAU HINH")
    target = merge_into(os.path.join(HERE, ".mcp.json"), entries)
    say(OK, "Da ghi %s" % target)
    for name, entry in entries.items():
        print("         %-16s -> %s" % (name, entry["args"][0]))

    if "--claude-desktop" in args:
        appdata = os.getenv("APPDATA", "")
        if appdata:
            path = os.path.join(appdata, "Claude", "claude_desktop_config.json")
            merge_into(path, entries)
            say(OK, "Da ghi %s" % path)
            say(WARN, "Khoi dong lai Claude Desktop de nap cau hinh moi.")
        else:
            say(WARN, "Khong doc duoc bien APPDATA, bo qua Claude Desktop.")

    step("XONG")
    for name in entries:
        say(OK, "%-16s can co: %s" % (name, SERVERS[name]["app"]))
    print("\n  Buoc tiep theo:")
    print("    1. Mo phan mem tuong ung (AutoCAD / Trimble Connect) va mo mot file.")
    print("    2. Mo Claude Code tai thu muc: %s" % HERE)
    print("    3. Go /mcp de kiem tra server da ket noi chua.\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
