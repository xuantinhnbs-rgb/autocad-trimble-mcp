"""Tự kiểm tra Trimble Connect MCP server qua đúng đường Claude dùng (stdio JSON-RPC).

Chạy:  python -m trimble_mcp.selftest
Không sửa gì trong mô hình: chỉ gọi các tool chỉ-đọc, trừ khi thêm cờ --write.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "trimble_server.py"


class Client:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, str(LAUNCHER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(ROOT),
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._id = 0

    def send(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        while True:
            line = self.proc.stdout.readline()
            if not line:
                err = self.proc.stderr.read()
                raise RuntimeError(f"Server đã thoát. stderr:\n{err}")
            data = json.loads(line)
            if data.get("id") == self._id:
                if "error" in data:
                    raise RuntimeError(data["error"])
                return data.get("result")

    def notify(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def tool(self, name: str, **args: Any) -> Any:
        result = self.send("tools/call", {"name": name, "arguments": args})
        for block in result.get("content", []):
            if block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except json.JSONDecodeError:
                    return block["text"]
        return result

    def close(self) -> None:
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


def show(label: str, payload: Any, width: int = 700) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if len(text) > width:
        text = text[:width] + f"\n  ... (cắt bớt, tổng {len(text)} ký tự)"
    print(f"\n### {label}\n{text}")


def main() -> int:
    # Console Windows mặc định là cp1252, không in được tiếng Việt có dấu.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    client = Client()
    try:
        init = client.send(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "selftest", "version": "1.0"},
            },
        )
        client.notify("notifications/initialized")
        print("Server:", init["serverInfo"])

        tools = client.send("tools/list")["tools"]
        print(f"Số tool: {len(tools)}")

        status = client.tool("get_status")
        show("get_status", status)
        if not status.get("ok"):
            print("\nKhông kết nối được — dừng.")
            return 1
        if not status.get("project"):
            print("\nChưa mở project nào trong Trimble Connect for Desktop.")
            print("Hãy mở một project rồi chạy lại để kiểm tra phần model/đối tượng.")
            return 2

        show("get_project", client.tool("get_project"))

        models = client.tool("list_models")
        show("list_models", models)

        show("list_views", client.tool("list_views"))
        show("get_camera", client.tool("get_camera"))
        show("get_selection_mode", client.tool("get_selection_mode"))
        show("get_selection", client.tool("get_selection", limit=5))

        found = client.tool("find_objects", limit=5, with_type_name=True, with_type_summary=True)
        show("find_objects", found)

        objects = found.get("objects") or []
        if objects:
            ids = [o["identifier"] for o in objects[:2]]
            show("get_attribute_names", client.tool("get_attribute_names", ids=ids))
            show("get_object_attributes", client.tool("get_object_attributes", ids=ids, limit=1))
            show("get_related_objects",
                 client.tool("get_related_objects", ids=ids[:1], relation="Parent"))
        else:
            print("\nDự án chưa nạp model nào nên không có đối tượng để kiểm tra.")

        print("\nOK — máy chủ trả lời đầy đủ.")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
