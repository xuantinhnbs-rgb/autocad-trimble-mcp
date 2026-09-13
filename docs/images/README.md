# Ảnh minh chứng — cách chúng được tạo ra

Mọi ảnh trong thư mục này đều chụp từ phần mềm thật đang chạy, ở trạng thái do
chính hai MCP server trong repo tạo ra. Không có ảnh nào là dựng lại, ghép hay
vẽ minh hoạ.

Hai script trong [`scripts/`](../../scripts/) làm việc này và có thể chạy lại:

| Script | Việc |
|---|---|
| [`capture-window.ps1`](../../scripts/capture-window.ps1) | Chụp một cửa sổ ứng dụng ra PNG, kể cả khung nhìn 3D tăng tốc phần cứng |
| [`redact-image.ps1`](../../scripts/redact-image.ps1) | Che vùng chữ nhận diện và cắt ảnh trước khi đưa lên repo công khai |

---

## `autocad-pier-elevation.png`

**Nội dung:** mặt đứng một trụ cầu — bệ móng, thân trụ, xà mũ, 5 gối cầu — kèm
5 layer, mặt cắt bê tông, 4 kích thước và 3 ghi chú dẫn. Toàn bộ do MCP vẽ vào
một bản vẽ trống mới; không mở file dự án nào.

Chuỗi tool đã dùng, theo đúng thứ tự:

```
create_new_document
set_active_or_create_layer   ×5   TRUC / KETCAU / BETONG / KICHTHUOC / GHICHU
set_system_variable          LTSCALE=60, DIMTXT=3.5, DIMASZ=3.5, DIMEXE=1.25,
                             DIMGAP=1, DIMDEC=0, DIMSCALE=80
batch_draw                   13 đối tượng trong MỘT lời gọi — 0,194 s
draw_hatch                   ×3   ANSI31 lên 3 biên khép kín
add_aligned_dimension        ×4   6000 / 9000 / 6000 / 1500 mm
add_leader                   ×3
zoom_view                    window
```

Bản vẽ dùng đơn vị milimet trong khi template mặc định là hệ inch, nên phải đặt
`DIMTXT`/`DIMASZ` trước khi tạo kích thước — để nguyên `0.18` của template thì
chữ số cao 0,18 mm trên hình dài 6000 mm, tức là mắt thường không thấy gì.

Chụp và che:

```powershell
.\scripts\capture-window.ps1 -ProcessName acad `
    -OutFile $env:TEMP\acad-shot.png -DelaySeconds 3

.\scripts\redact-image.ps1 -InFile $env:TEMP\acad-shot.png `
    -OutFile docs\images\autocad-pier-elevation.png `
    -Region '230,240,250,28,#313946,Ban-ve-du-an.dwg'
```

Vùng che là tab của bản vẽ thứ hai đang mở — một file dự án thật, không liên
quan đến bản demo.

---

## `trimble-ifc-colour-by-type.png`

**Nội dung:** một mô hình cầu cạn IFC, **7 824 đối tượng được tô màu theo IFC
type** trong một lượt:

| IFC type | Số đối tượng | Màu |
|---|---:|---|
| `IFCCOLUMN` (trụ, cọc) | 1 801 | `#E8833A` cam |
| `IFCBEAM` (dầm Super-T) | 3 857 | `#2E86C1` xanh dương |
| `IFCSLAB` (bản mặt cầu) | 1 896 | `#58D68D` xanh lá |
| `IFCPLATE` | 270 | `#F4D03F` vàng |

Phần còn màu gốc là các loại không nằm trong bảng trên (`IFCDISCRETEACCESSORY`,
`IFCREINFORCINGBAR`, `IFCVOIDINGFEATURE`).

Số đối tượng ở mức này thì **không nên** đẩy identifier qua tham số của tool.
Ảnh này được dựng bằng cách gọi thẳng các hàm trong `trimble_mcp.server` từ một
script Python — cùng mã nguồn, cùng cầu nối .NET, chỉ khác điểm gọi:

```python
import sys
sys.path.insert(0, "trimble-mcp")
from trimble_mcp import server as tc

MODEL = "<model identifier>"
for kieu, mau in [("IFCCOLUMN", "#E8833A"), ("IFCBEAM", "#2E86C1"),
                  ("IFCSLAB", "#58D68D"), ("IFCPLATE", "#F4D03F")]:
    ids = [o["identifier"] for o in
           tc.find_objects(by="type", type_name=kieu,
                           model_id=MODEL, limit=20000)["objects"]]
    for i in range(0, len(ids), 400):                 # chia lô 400
        tc.set_color(ids=ids[i:i + 400], color=mau, model_id=MODEL)
```

Khung nhìn đặt bằng `set_camera`, **không** dùng `activate_view`: một view đã lưu
mang theo cả trạng thái màu và hiển thị của lúc lưu, kích hoạt nó sẽ xoá sạch
màu vừa tô.

Chụp, che tên dự án và cắt bỏ dải view đã lưu (dải đó hiện mã hiệu tài liệu thật):

```powershell
.\scripts\capture-window.ps1 -ProcessName TrimbleConnect `
    -OutFile $env:TEMP\tc-shot.png -DelaySeconds 4

.\scripts\redact-image.ps1 -InFile $env:TEMP\tc-shot.png `
    -OutFile docs\images\trimble-ifc-colour-by-type.png `
    -Region '852,20,190,30,#FFFFFF,DU-AN-DEMO','1414,192,200,28,#FFFFFF,DU-AN-DEMO' `
    -Crop '0,0,1942,752'
```

---

## `install-check-and-tests.png`

**Nội dung:** ba lệnh mà CI chạy, trên một máy **không mở AutoCAD lẫn Trimble
Connect** — `install.py --check` nạp thử cả hai server và đếm được 49 + 34 tool,
`ruff` sạch, toàn bộ test hợp đồng xanh.

Đường dẫn trong ảnh là `X:\` vì repo được ánh xạ qua một ổ ảo trước khi chụp, để
ảnh không mang theo tên người dùng của máy:

```powershell
subst X: <thư mục repo>
# chạy 3 lệnh trong X:\ rồi chụp
subst X: /d
```

Lưu ý khi chạy lại: `pyproject.toml` đã có `addopts = "-q --strict-markers"`, nên
gõ thêm `pytest -q` thành `-qq` và pytest sẽ nuốt luôn dòng tổng kết
`N passed`. Cứ chạy `pytest` trần.

**Con số test trong ảnh là ảnh chụp tại một thời điểm.** Tài liệu cố tình không
nhắc lại con số đó ở bất kỳ đâu khác: grep và test giữ đồng bộ được mọi bản sao
của một dữ kiện, trừ bản nằm trong pixel. Thêm test thì ảnh này lỗi thời — chụp
lại nếu muốn, nhưng không có câu văn nào mâu thuẫn với nó cả.

---

## Quy tắc khi thêm ảnh mới

1. **Chụp từ ứng dụng thật**, ở trạng thái do MCP server tạo ra.
2. **Ghi lại chuỗi lệnh** đã dùng, vào chính file này, đủ để người khác dựng lại.
3. **Rà thông tin nhận diện trước khi commit** — tên người dùng trong đường dẫn,
   tên dự án của khách hàng, mã hiệu tài liệu, tài khoản đăng nhập, số bản quyền.
   Ảnh đã commit thì nằm vĩnh viễn trong lịch sử git; xoá file ở commit sau không
   gỡ được nó ra.
4. **Che bằng cách tô đè, không làm mờ.** Làm mờ vẫn có thể đảo ngược một phần.
   Cả một dải giao diện cần biến mất thì cắt (`-Crop`) chứ đừng tô, vì một mảng
   trống lớn trông rõ là đã bị sửa.
