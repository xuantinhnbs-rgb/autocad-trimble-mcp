"""
Điểm khởi chạy Trimble Connect MCP Server.
==========================================
Dùng file này trong cấu hình MCP (Claude Desktop / Claude Code / VS Code):

    "command": "<đường dẫn python.exe>",
    "args": ["<thư mục dự án>/trimble-mcp/trimble_server.py"],
    "cwd": "<thư mục dự án>/trimble-mcp"

Lần chạy đầu tiên sẽ tự biên dịch cầu nối .NET (TrimbleBridge.exe) bằng csc.exe
có sẵn trong Windows — không cần cài Visual Studio hay .NET SDK.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from trimble_mcp.server import main  # noqa: E402

if __name__ == "__main__":
    main()
