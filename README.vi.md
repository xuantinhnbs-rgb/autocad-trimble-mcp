# autocad-trimble-mcp

*[English](README.md) · **Tiếng Việt***

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
autocad-trimble-mcp/
├── install.py          # dò đường dẫn của máy hiện tại rồi sinh .mcp.json
├── .mcp.json.example   # bản mẫu để xem cấu trúc cấu hình
│
├── autocad-mcp/        # ⬅ MỌI THỨ của MCP AutoCAD nằm trong đây
├── trimble-mcp/        # ⬅ MỌI THỨ của MCP Trimble nằm trong đây
│
└── .github/workflows/  # CI: nạp thử cả hai server trên Windows
```

`.mcp.json` **không nằm trong repo** vì nó chứa đường dẫn tuyệt đối riêng của
từng máy. Chạy `install.py` để sinh ra file này cho máy của bạn.

Mỗi thư mục app là **một bộ hoàn chỉnh, tự đứng được**: có `README.md`,
`requirements.txt` và điểm khởi chạy riêng. Muốn chia sẻ một app cho người khác,
chỉ cần nén đúng thư mục đó gửi đi.

---

## 🚀 Cài đặt

**Yêu cầu:** Windows, Python 3.10 trở lên, và phần mềm tương ứng đang cài trên máy
(AutoCAD 2022+ / Trimble Connect for Desktop).

```powershell
git clone https://github.com/xuantinhnbs-rgb/autocad-trimble-mcp.git
cd autocad-trimble-mcp

pip install -r autocad-mcp/requirements.txt     # nếu dùng AutoCAD
pip install -r trimble-mcp/requirements.txt     # nếu dùng Trimble Connect

python install.py
```

`install.py` tự dò `python.exe` và thư mục dự án **trên máy đang chạy**, nạp thử
từng server để chắc chắn đủ thư viện, rồi ghi `.mcp.json` với đường dẫn đúng.
Không phải sửa tay đường dẫn nào.

```powershell
python install.py --check            # chỉ kiểm tra, không ghi gì
python install.py --autocad          # chỉ cấu hình AutoCAD
python install.py --trimble          # chỉ cấu hình Trimble
python install.py --claude-desktop   # ghi thêm vào config của Claude Desktop
```

Xong thì mở Claude Code **tại thư mục gốc của dự án** (nơi chứa `.mcp.json`), gõ
`/mcp` để kiểm tra server đã kết nối chưa.

> Với Cursor / Cline / Claude Desktop: chép nội dung `.mcp.json` vừa sinh ra vào
> file cấu hình MCP của công cụ đó, hoặc dùng cờ `--claude-desktop` ở trên.

---

## 🔧 Cài thủ công

Nếu không muốn chạy `install.py`, chép [.mcp.json.example](.mcp.json.example) thành
`.mcp.json` rồi sửa `command`, `args`, `cwd` cho khớp máy bạn.

Dùng dấu `/` trong đường dẫn JSON để khỏi phải escape `\\` — Windows nhận bình thường.
Phải dùng `python.exe`, **không dùng `pythonw.exe`**: MCP giao tiếp qua stdio nên cần
stdout, mà `pythonw.exe` thì không có.

---

## ❓ Gặp lỗi?

| Triệu chứng | Xử lý |
|---|---|
| `/mcp` báo server không kết nối | Chạy `python install.py --check` xem thiếu gì |
| `ModuleNotFoundError: mcp` | `pip install -r <thư-mục-app>/requirements.txt` |
| Server chạy nhưng mọi tool báo lỗi | Phần mềm chưa mở, hoặc chưa mở file/dự án nào trong đó |
| Lỗi tiếng Việt khi chạy script tay | Đặt `PYTHONIOENCODING=utf-8` trước khi chạy |

Chi tiết theo từng app xem README riêng: [AutoCAD](autocad-mcp/README.md) ·
[Trimble Connect](trimble-mcp/README.md).

---

## 📄 Giấy phép

[MIT](LICENSE) — dùng thoải mái kể cả cho mục đích thương mại, chỉ cần giữ lại
dòng ghi công.
