# 🚀 AutoCAD 2022 MCP Server (Model Context Protocol)

MCP Server cho phép các mô hình AI (Claude Code, Claude Desktop, Cursor, Cline, Antigravity, v.v.) kết nối và điều khiển trực tiếp phần mềm **AutoCAD** trên máy Windows của bạn. Được phát triển và kiểm thử trên **AutoCAD 2022** — xem mục [Tương thích phiên bản](#-tương-thích-phiên-bản) bên dưới nếu bạn dùng bản khác.

---

## 🧩 Tương thích phiên bản

[`autocad_client.py`](autocad_client.py) bám vào AutoCAD đang chạy qua ba ProgID COM, thử lần lượt:

1. `AutoCAD.Application.24.1`
2. `AutoCAD.Application.24`
3. `AutoCAD.Application`

Hai ProgID đầu ứng đúng với số phiên bản COM nội bộ của **AutoCAD 2022**. ProgID thứ ba
là ProgID **chung**, không gắn số phiên bản — Windows sẽ trỏ nó tới bất kỳ bản AutoCAD
nào đang đăng ký làm COM server mặc định trên máy đó.

Vì vậy:

- **AutoCAD 2022** → luôn kết nối được, đã kiểm thử kỹ.
- **Bản khác (2023 trở lên, bản Full — không phải LT vì LT không có COM API)** →
  nhiều khả năng vẫn kết nối được nhờ ProgID chung ở bước 3, do API ActiveX phần lớn
  tương thích ngược giữa các phiên bản. Tuy nhiên **chưa được kiểm chứng đầy đủ**: một
  vài tool có thể lệch tham số hoặc tên thuộc tính nếu Autodesk đổi API giữa các bản.

Nếu bạn dùng bản khác 2022 và gặp lỗi `DISP_E_UNKNOWNNAME` (AutoCAD không hỗ trợ
thuộc tính/phương thức này) ở một tool cụ thể, đó là dấu hiệu API đã lệch — hãy báo
lại qua issue kèm phiên bản AutoCAD của bạn.

---

## 📐 Hợp đồng trả về

**Mọi** tool đều trả về một object JSON có khóa `ok`:

```jsonc
{ "ok": true,  "handle": "2A7", "layer": "TRUC", ... }          // thành công
{ "ok": false, "error": "Bán kính phải lớn hơn 0, nhận được -5.0." }   // thất bại
```

Không tool nào ném ngoại lệ ra ngoài, nên AI luôn nhận được thông điệp đọc được thay vì một vệt lỗi COM thô. Thông điệp lỗi viết bằng tiếng Việt và nói rõ cách khắc phục.

Server tự phục hồi trong các tình huống sau mà không cần khởi động lại:

| Tình huống | Cách xử lý |
|---|---|
| AutoCAD đang bận (đang trong lệnh, đang regen) | Tự chờ và thử lại, kể cả với từng đối tượng trong vòng lặp |
| AutoCAD bị đóng rồi mở lại | Phát hiện con trỏ COM chết và tự kết nối lại |
| Người dùng chuyển sang bản vẽ khác | Tự bám theo bản vẽ hiện hành |
| MCP gọi tool từ nhiều luồng khác nhau | Dồn toàn bộ COM về một luồng chuyên trách |

---

## 📌 49 công cụ được hỗ trợ

### 1. Kết nối & tài liệu
| Tool | Công dụng |
|---|---|
| `check_autocad_connection` | Kiểm tra kết nối, phiên bản, có đang kẹt lệnh không |
| `get_active_document_info` | Thông tin bản vẽ hiện hành |
| `list_open_documents` | Danh sách mọi bản vẽ đang mở |
| `switch_document` | Chuyển bản vẽ hiện hành theo tên hoặc chỉ số |
| `create_new_document` | Tạo bản vẽ mới (tùy chọn từ `.dwt`) |
| `open_dwg_document` | Mở file `.dwg` / `.dxf` / `.dwt` |
| `save_document` | Lưu hoặc Save As |
| `close_document` | Đóng bản vẽ hiện hành |

### 2. Vẽ hình học
| Tool | Công dụng |
|---|---|
| `draw_line` | Đoạn thẳng |
| `draw_circle` | Hình tròn |
| `draw_arc` | Cung tròn (góc nhập bằng **độ**) |
| `draw_ellipse` | Elip |
| `draw_point` | Điểm |
| `draw_polyline_2d` | Đa tuyến 2D |
| `draw_polyline_3d` | Đa tuyến 3D |
| `draw_rectangle` | Hình chữ nhật khép kín |
| `draw_spline` | Đường cong trơn |
| `draw_hatch` | Tô mặt cắt vào biên khép kín có sẵn |
| `insert_block` | Chèn block trong bản vẽ hoặc từ file `.dwg` ngoài |

### 3. Chữ & kích thước
| Tool | Công dụng |
|---|---|
| `add_text_annotation` | Text đơn dòng |
| `add_mtext_annotation` | MText nhiều dòng |
| `add_aligned_dimension` | Kích thước gióng nghiêng |
| `add_dimension` | Mọi kiểu: aligned, linear, horizontal, vertical, angular, radial, diametric |
| `add_leader` | Đường dẫn ghi chú có mũi tên |

### 4. Hiệu chỉnh
| Tool | Công dụng |
|---|---|
| `modify_entities` | move, copy, rotate, scale, mirror, offset, array_rect, array_polar, explode |
| `set_entity_properties` | Đổi layer / màu / linetype / lineweight / nội dung chữ |
| `delete_entities` | Xóa theo handle, theo layer, theo loại, hoặc xóa sạch |

### 5. Truy vấn
| Tool | Công dụng |
|---|---|
| `get_drawing_summary` | Thống kê theo kiểu và theo layer |
| `list_entities` | Liệt kê chi tiết kèm handle và tọa độ |
| `get_entity_details` | Đọc một đối tượng theo handle, kèm hộp bao |
| `get_selected_entities` | Đọc những gì người dùng đang chọn trên màn hình |
| `get_drawing_extents` | Giới hạn bao ngoài bản vẽ |
| `find_or_replace_text` | Tìm / thay thế chuỗi hàng loạt |

### 6. Layer & bảng ký hiệu
| Tool | Công dụng |
|---|---|
| `list_drawing_layers` | Danh sách layer kèm trạng thái |
| `set_active_or_create_layer` | Tạo / sửa / kích hoạt layer |
| `delete_layer` | Xóa layer (có thể dời đối tượng sang layer khác trước) |
| `list_blocks` | Danh sách block đã định nghĩa |
| `list_styles` | Text style, dim style, linetype, layout |

### 7. Hệ thống & lệnh
| Tool | Công dụng |
|---|---|
| `zoom_view` | extents / all / window / center / previous |
| `regen_drawing` | Regen |
| `get_system_variable` | Đọc biến hệ thống |
| `set_system_variable` | Đặt biến hệ thống |
| `send_autocad_command` | Gửi lệnh vào dòng lệnh (không lấy được giá trị trả về) |
| `run_autolisp` | Chạy AutoLISP **và lấy về giá trị trả về** — lối thoát vạn năng |
| `purge_drawing` | Purge |
| `audit_drawing` | Audit và sửa lỗi cấu trúc |

### 8. Xuất file & vẽ hàng loạt
| Tool | Công dụng |
|---|---|
| `export_drawing_to_pdf` | Xuất PDF qua máy in ảo, có kiểm chứng file đã tạo |
| `export_drawing_to_dxf` | Xuất DXF (không đổi tên bản vẽ đang mở) |
| `batch_draw` | **Vẽ tới 5000 đối tượng trong một lần gọi** |

---

## ⚡ Hiệu năng

Mỗi đối tượng tốn vài lời gọi COM (~5 ms). Vì vậy:

- **Cần vẽ từ vài chục đối tượng trở lên → luôn dùng `batch_draw`.** Đo thực tế: 300 đối tượng trong ~4 giây.
- `list_entities` mặc định **dừng ngay khi đủ `limit`** (50 đối tượng trên bản vẽ 2000 đối tượng: 0,7 giây). Muốn biết tổng số khớp chính xác thì truyền `count_all=True` (chậm hơn nhiều).
- `get_drawing_summary` phải đọc từng đối tượng: bản vẽ 2000 đối tượng mất khoảng 10 giây. Tổng số đối tượng luôn chính xác, riêng phần phân loại bị cắt theo `max_scan` (mặc định 20000).

---

## 🛠️ Cài đặt & cấu hình

### 1. Thư viện phụ thuộc
```powershell
pip install -r requirements.txt
```

### 2. Kiểm tra kết nối
Mở AutoCAD (2022 hoặc bản mới hơn — xem [Tương thích phiên bản](#-tương-thích-phiên-bản)) với ít nhất một bản vẽ, sau đó:
```powershell
python test_connection.py
```

### 3. Cấu hình MCP

Cách nhanh nhất là chạy `python install.py` **ở gốc dự án** — nó tự dò đường dẫn
của máy bạn và sinh ra `.mcp.json`.

Muốn tự viết tay thì thêm mục sau vào cấu hình MCP của công cụ bạn dùng, nhớ sửa
hai đường dẫn cho khớp máy:

```json
{
  "mcpServers": {
    "autocad-2022": {
      "command": "C:/Python314/python.exe",
      "args": ["C:/duong/dan/du-an/autocad-mcp/server.py"],
      "cwd": "C:/duong/dan/du-an/autocad-mcp",
      "env": { "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8" }
    }
  }
}
```

> Dùng dấu `/` trong JSON để khỏi phải escape `\\`. Windows nhận bình thường.
> Chạy `python install.py` sẽ tự sinh mục này vào `.mcp.json` ở gốc dự án.

---

## 💡 Ví dụ câu lệnh cho AI

- *"Kiểm tra bản vẽ hiện tại có bao nhiêu layer và thống kê số đối tượng."*
- *"Vẽ hình chữ nhật 500x300 tại gốc (0,0) và ghi kích thước hai cạnh."*
- *"Tạo layer `COT_BE_TONG` màu đỏ rồi vẽ 96 cột bước 1425 dọc theo tuyến."*
- *"Tìm mọi chữ chứa `KM83+075` và đổi thành `KM83+075.63`."*
- *"Chép cụm tường chắn này thành mảng 10 hàng cách nhau 1425."*
- *"Xuất bản vẽ ra PDF tại Desktop."*

---

## 📂 Cấu trúc

```
autocad-mcp/
├── server.py                    # 49 tool MCP, mỗi tool bọc bởi safe() — không bao giờ ném lỗi ra ngoài
├── autocad_client.py            # toàn bộ giao tiếp COM, cơ chế thử lại và tự kết nối lại
├── app.py                       # giao diện điều khiển (tùy chọn, không bắt buộc để chạy MCP)
├── install.py                   # cài đặt tự động + sinh .mcp.json ở gốc dự án
├── test_connection.py           # kiểm tra nhanh có bám được vào AutoCAD không
├── draw_square.py               # ví dụ dùng AutoCADClient trực tiếp
├── send_to_active_acad.py       # gửi lệnh thẳng vào AutoCAD đang chạy
├── create_desktop_shortcut.py   # tạo lối tắt app.py ra Desktop
├── run_app.bat / run_app_hidden.vbs   # khởi chạy app.py (bản .vbs không nháy console)
├── requirements.txt
└── scripts/                     # file LISP/script AutoCAD rời, không được code nào import
    ├── draw_lines.lsp
    ├── draw_lines.scr
    └── draw_square.scr
```

Bốn file `server.py`, `autocad_client.py`, `app.py`, `test_connection.py` **phải nằm cùng một
thư mục** — chúng `import autocad_client` theo tên trần, tách ra là gãy.

Bản `autocad_mcp/` cũ (dùng `mcp.server.fastmcp`, đã bị bỏ ở `mcp` 2.x) không còn
được dùng và không có trong repo — nó chỉ nằm trong thư mục `_archive/` trên máy
tác giả, đã được `.gitignore` loại ra.

---

## 🧪 Phát triển

Lint, test và quy ước khi thêm tool: xem [CONTRIBUTING.md](../CONTRIBUTING.md) ở
gốc dự án. Thêm hoặc bỏ tool thì phải sửa cả bảng ở trên **và** `EXPECTED_COUNTS`
trong [tests/test_tool_contracts.py](../tests/test_tool_contracts.py) — không thì
test đỏ, đúng như thiết kế.
