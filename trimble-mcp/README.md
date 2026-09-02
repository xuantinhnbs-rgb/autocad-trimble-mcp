# 🏗️ Trimble Connect Desktop MCP Server

MCP Server cho phép các mô hình AI (Claude Code, Claude Desktop, Cursor, Cline, v.v.) kết nối và điều khiển trực tiếp **Trimble Connect for Desktop** đang chạy trên máy Windows của bạn.

---

## ⚙️ Cách nó hoạt động

Trimble Connect for Desktop **không có COM API**. Thay vào đó nó mở một *Desktop .NET API* (`Trimble.Connect.Desktop.API.dll`, .NET Framework 4.8) qua kênh IPC nội bộ. `pythonnet` lại chưa hỗ trợ các bản Python mới, nên dự án này đi đường vòng bằng một cầu nối C# nhỏ:

```
Claude  ──MCP/stdio──►  trimble_server.py  ──JSON-lines──►  TrimbleBridge.exe  ──►  Trimble Connect
               (Python)                       (stdin/stdout)      (.NET 4.8)
```

`TrimbleBridge.exe` **được biên dịch tự động ở lần chạy đầu tiên** bằng `csc.exe` có sẵn trong mọi bản Windows (`C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe`) — **không cần cài Visual Studio hay .NET SDK**. Sửa file `.cs` rồi chạy lại là nó tự biên dịch lại.

Kết nối tới Trimble Connect được **giữ nguyên suốt vòng đời server**, nên trạng thái (dự án đang mở, model đã nạp) không bị mất giữa các lệnh.

---

## 📐 Hợp đồng trả về

**Mọi** tool đều trả về một object JSON có khóa `ok`:

```jsonc
{ "ok": true,  "models": [...], "count": 12 }                                   // thành công
{ "ok": false, "error": "Chua co du an nao dang mo trong Trimble Connect..." }  // thất bại
```

Không tool nào ném ngoại lệ ra ngoài, nên AI luôn nhận được thông điệp đọc được thay vì một vệt lỗi .NET thô.

Server tự xử lý các tình huống sau mà không cần khởi động lại:

| Tình huống | Cách xử lý |
|---|---|
| Chưa kết nối tới Trimble Connect | Tự dò instance và kết nối ở lệnh đầu tiên |
| Trimble Connect bị đóng | Bắt sự kiện `TrimbleConnectDesktopClosed`, tự kết nối lại ở lệnh sau |
| Người dùng đóng/mở dự án khác | Bắt sự kiện `ProjectClosed`, tự đọc lại dự án đang active |
| Cầu nối .NET chết bất thường | Khởi động lại tiến trình và kèm nội dung log vào thông điệp lỗi |
| Trimble Connect treo / đang bận | Trả lỗi có thời hạn (mặc định 180 s) thay vì treo theo |

---

## 🚀 Cài đặt

Yêu cầu:

* Windows + **Trimble Connect for Desktop** đã cài (kèm thư mục `C:\Program Files\Trimble\Trimble Connect`).
* Python 3.10 trở lên với gói `mcp` (đã kiểm chứng tới 3.14).
* .NET Framework 4.x (mặc định đã có trong Windows 10/11).

```bash
pip install -r requirements.txt
```

Đăng ký server — cách nhanh nhất là chạy `python install.py` **ở gốc dự án**, nó tự
dò đường dẫn của máy bạn và sinh ra `.mcp.json`.

Muốn tự viết tay thì thêm mục sau, nhớ sửa hai đường dẫn cho khớp máy:

```jsonc
{
  "mcpServers": {
    "trimble-connect": {
      "command": "C:/Python314/python.exe",
      "args": ["C:/duong/dan/du-an/trimble-mcp/trimble_server.py"],
      "cwd": "C:/duong/dan/du-an/trimble-mcp",
      "env": { "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8" }
    }
  }
}
```

> Dùng dấu `/` trong JSON để khỏi phải escape `\\`. Windows nhận bình thường.

Nếu cài Trimble Connect ở ổ khác, đặt biến môi trường `TRIMBLE_CONNECT_DIR` trỏ tới thư mục chứa `Trimble.Connect.Desktop.API.dll`.

### Tự kiểm tra

Chạy từ **trong thư mục `trimble-mcp/`**:

```bash
python -m trimble_mcp.selftest          # đi đúng đường Claude dùng: stdio JSON-RPC
python -m trimble_mcp.trimble_client status
python -m trimble_mcp.trimble_client find_objects '{"limit": 5}'
```

---

## 🧰 Danh sách tool (34)

### Kết nối & dự án

| Tool | Việc |
|---|---|
| `get_status` | Trạng thái kết nối + dự án đang mở. **Gọi đầu tiên.** |
| `list_connections` | Các instance Trimble Connect đang mở |
| `connect` | Kết nối / kết nối lại tới một instance |
| `start_desktop_app` | Khởi động một instance mới |
| `refresh` | Đọc lại dự án đang active sau khi đổi dự án |
| `get_project` | Tên, identifier, thư mục làm việc của dự án |

### Model

| Tool | Việc |
|---|---|
| `list_models` | Liệt kê model (`all` / `loaded` / `unloaded`) |
| `load_models`, `unload_models` | Nạp / gỡ model khỏi khung nhìn 3D |
| `get_model_placement` | Vị trí, cao độ, tỷ lệ, góc xoay |
| `set_model_placement` | Đặt vị trí / tỷ lệ / góc xoay (chỉ tham số được truyền mới đổi) |
| `reset_model_placement` | Trả về placement gốc |
| `get_model_content_path` | Đường dẫn file cục bộ của model |

### Đối tượng

| Tool | Việc |
|---|---|
| `find_objects` | Tìm theo `all` / `selected` / `type` / `visual_state` / `attribute` / `ids` |
| `get_selection` | Đối tượng người dùng đang chọn |
| `select_objects` | Chọn / bỏ chọn theo identifier |
| `set_visual_state`, `reset_visual_state` | `Visible` / `Hidden` / `Highlighted` / `Unhighlighted` |
| `isolate_objects` | Ẩn hết, chỉ hiện những đối tượng đã cho |
| `set_color`, `reset_color` | Tô màu (`#RRGGBB`, `255,0,0`, hoặc `red`) |
| `reset_all` | Hủy toàn bộ isolate + tô màu |
| `get_object_attributes` | Toàn bộ property set (IFC) của đối tượng |
| `get_attribute_names` | Tên các thuộc tính có trên tập đối tượng |
| `get_attribute` | Đọc một thuộc tính trên nhiều đối tượng |
| `get_related_objects` | Duyệt cây phân cấp (`Child` / `Parent`, `Immediate` / `All`) |

### View & camera

| Tool | Việc |
|---|---|
| `list_views`, `activate_view`, `create_view` | Quản lý view đã lưu |
| `get_camera`, `set_camera` | Đọc / đặt camera (vị trí, hướng, up, kiểu chiếu) |
| `zoom_to_objects` | Đưa camera về khung các đối tượng |

### Cài đặt

| Tool | Việc |
|---|---|
| `get_selection_mode`, `set_selection_mode` | `HighestLevelAssembliesAndSystems` \| `IndividualObjects` |

---

## 💡 Ví dụ hội thoại

> **"Trong dự án đang mở có những model nào?"**
> → `get_status` → `list_models`

> **"Tô đỏ toàn bộ tường trong model kiến trúc."**
> → `list_models` → `find_objects(by="type", type_name="IfcWall", model_id=...)` → `set_color(ids=[...], color="red")`

> **"Tôi đang chọn mấy cấu kiện này, cho tôi xem thuộc tính của chúng."**
> → `get_selection` → `get_object_attributes(ids=[...])`

> **"Chỉ hiện những gì tôi đang chọn thôi."**
> → `isolate_objects()` → sau đó `reset_all()` để trả lại

---

## 📁 Cấu trúc

```
trimble-mcp/
├── trimble_server.py               # điểm khởi chạy cho cấu hình MCP
├── requirements.txt                # chỉ cần mcp>=2.1.0
├── README.md                       # tài liệu này
└── trimble_mcp/
    ├── server.py                   # 34 tool MCP, hợp đồng {"ok": ...}
    ├── trimble_client.py           # tự biên dịch + quản lý tiến trình cầu nối
    ├── selftest.py                 # tự kiểm tra qua stdio JSON-RPC
    └── bridge/
        ├── TrimbleBridge.cs        # vòng lặp JSON-lines, nạp assembly, đọc tham số
        ├── Session.cs              # toàn bộ phần chạm vào Trimble Desktop API
        ├── TrimbleBridge.exe       # sinh tự động ở lần chạy đầu — xóa được
        └── TrimbleBridge.exe.config # sinh tự động (binding redirect của Trimble)
```

> Hai file `TrimbleBridge.exe*` **không có sẵn trong repo** — chúng được sinh ra ở lần
> chạy đầu tiên. Khi gửi thư mục này cho người khác, đừng kèm file `.exe`: Windows
> SmartScreen hay chặn file thực thi tải từ mạng về, cứ để máy đích tự biên dịch.

---

## 🔧 Gỡ rối

| Triệu chứng | Xử lý |
|---|---|
| `Khong tim thay instance nao cua Trimble Connect` | Mở Trimble Connect for Desktop. Nếu vẫn lỗi, kiểm tra Desktop API có bị tắt trong Settings không. |
| `Chua co du an nao dang mo` | Mở một project trong ứng dụng, rồi gọi `refresh`. |
| `Bien dich TrimbleBridge.exe that bai` | Bật ".NET Framework 4.8" trong Windows Features. |
| `Cau noi ... da thoat` | Xem log tại `%TEMP%\trimble_mcp_bridge.err.log`. |
| Server không phản hồi | Trimble Connect có thể đang mở hộp thoại chờ thao tác — xử lý xong hộp thoại đó. |
| `set_camera` không ăn | Đừng gọi ngay sau `zoom_to_objects`: hoạt ảnh zoom còn chạy sẽ ghi đè. |
| `set_camera` ra vị trí khác | Chuyển sang `Orthogonal` thì Trimble tự tính lại location — đúng thiết kế của ứng dụng. |
| `get_model_content_path` trả null | Model đồng bộ từ cloud không phơi đường dẫn cục bộ; dùng `get_object_attributes` để đọc dữ liệu. |
