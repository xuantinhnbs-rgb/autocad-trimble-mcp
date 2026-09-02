# PP — MCP Server cho AutoCAD & Trimble Connect

Hai MCP server độc lập, cho phép AI (Claude Code, Claude Desktop, Cursor, Cline…)
điều khiển trực tiếp phần mềm đang chạy trên máy Windows này.

| Server | Điều khiển | Số tool | Tài liệu |
|---|---|---|---|
| `autocad-2022` | AutoCAD 2022 qua COM | 49 | [autocad-mcp/README.md](autocad-mcp/README.md) |
| `trimble-connect` | Trimble Connect for Desktop qua .NET API | 34 | [trimble-mcp/README.md](trimble-mcp/README.md) |

Cả hai đều dùng chung một hợp đồng trả về: **mọi tool đều trả JSON có khóa `ok`**
(`{"ok": true, ...}` hoặc `{"ok": false, "error": "..."}`), không tool nào ném ngoại lệ
ra ngoài — AI luôn nhận được thông điệp đọc được thay vì vệt lỗi thô.

---

## 📁 Cấu trúc dự án

```
PP/
├── .mcp.json           # cấu hình MCP cho Claude Code (đọc từ gốc dự án)
├── mcp_config.json     # bản sao dùng cho Claude Desktop / Cursor / Cline
│
├── autocad-mcp/        # ⬅ MỌI THỨ của MCP AutoCAD nằm trong đây
├── trimble-mcp/        # ⬅ MỌI THỨ của MCP Trimble nằm trong đây
│
├── ban-ve/             # PDF bản vẽ tham chiếu (không liên quan tới code)
└── _archive/           # code cũ & file rỗng, giữ lại phòng khi cần
```

Mỗi thư mục app là **một bộ hoàn chỉnh, tự đứng được**: có `README.md`,
`requirements.txt` và điểm khởi chạy riêng. Muốn chia sẻ một app cho người khác,
chỉ cần nén đúng thư mục đó gửi đi.

---

## 🚀 Bắt đầu

```powershell
# AutoCAD
cd autocad-mcp
pip install -r requirements.txt
python install.py            # tự kiểm tra môi trường + ghi .mcp.json ở gốc dự án

# Trimble Connect
cd ..\trimble-mcp
pip install -r requirements.txt
python -m trimble_mcp.selftest
```

Sau đó mở Claude Code **tại thư mục gốc `PP/`** — đây là nơi chứa `.mcp.json`.

---

## ⚠️ Lưu ý khi đổi máy

`.mcp.json` và `mcp_config.json` chứa **đường dẫn tuyệt đối**. Chép dự án sang máy
khác thì phải sửa lại `command` (đường dẫn `python.exe`) và `args`/`cwd` cho khớp.
Với AutoCAD, chạy `python autocad-mcp/install.py` sẽ tự sinh lại đúng đường dẫn.

Đường dẫn trong JSON dùng dấu `/` cho gọn — Windows nhận bình thường, khỏi phải
escape `\\`.

---

## 📦 Chia sẻ cho người khác

Mã nguồn **không hardcode đường dẫn máy bạn** — chỉ hai file cấu hình JSON ở gốc là
có. Khi gửi đi:

1. Nén thư mục app tương ứng (`autocad-mcp/` hoặc `trimble-mcp/`).
2. **Bỏ** `__pycache__/` và `trimble_mcp/bridge/TrimbleBridge.exe*` — file `.exe` tải
   từ mạng về hay bị SmartScreen chặn, cứ để máy đích tự biên dịch lại.
3. Người nhận đọc `README.md` trong thư mục đó và tự sửa 2 đường dẫn trong cấu hình MCP.
