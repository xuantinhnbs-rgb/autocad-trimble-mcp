"""
AutoCAD 2022 MCP Server
=======================
Giao tiếp chuẩn Model Context Protocol (MCP) để AI điều khiển trực tiếp AutoCAD 2022.

Hợp đồng trả về: MỌI tool đều trả về một object JSON có khóa "ok".
  * Thành công -> {"ok": true, ...dữ liệu...}
  * Thất bại   -> {"ok": false, "error": "<thông điệp tiếng Việt nói rõ cách khắc phục>"}
Không tool nào ném ngoại lệ ra ngoài, nên phía AI luôn nhận được phản hồi đọc được
thay vì một vệt lỗi COM thô.
"""

import functools
import inspect
from typing import Any, Dict, List, Optional

from mcp.server.mcpserver import MCPServer

from autocad_client import AcadError, AutoCADClient

mcp = MCPServer(
    "AutoCAD-2022-MCP",
    instructions=(
        "Điều khiển AutoCAD đang chạy trên máy này: vẽ hình học, quản lý layer, ghi kích thước "
        "và chú thích, truy vấn đối tượng, chạy AutoLISP, xuất PDF/DXF.\n"
        "Mọi thao tác đều cần AutoCAD đang mở VÀ có ít nhất một bản vẽ — gọi "
        "check_autocad_connection trước để kiểm tra. Đối tượng được định danh bằng handle lấy từ "
        "list_entities hoặc get_selected_entities.\n"
        "Cần vẽ từ vài chục đối tượng trở lên thì dùng batch_draw, đừng gọi lẻ từng tool: mỗi lời "
        "gọi COM tốn khoảng 5 ms."
    ),
)
acad = AutoCADClient()


def safe(fn):
    """Bọc một tool: không bao giờ ném lỗi, luôn trả về dict có khóa 'ok'."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs) -> dict:
        try:
            result = fn(*args, **kwargs)
        except AcadError as exc:
            return {"ok": False, "error": str(exc)}
        except (ValueError, TypeError, KeyError) as exc:
            return {"ok": False, "error": f"Tham số không hợp lệ: {exc}"}
        except Exception as exc:                     # lưới an toàn cuối cùng
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        if isinstance(result, dict):
            return result if "ok" in result else {"ok": True, **result}
        if isinstance(result, list):
            return {"ok": True, "count": len(result), "items": result}
        return {"ok": True, "result": result}

    wrapper.__annotations__ = dict(getattr(fn, "__annotations__", {}))
    wrapper.__annotations__["return"] = dict
    wrapper.__signature__ = inspect.signature(fn).replace(return_annotation=dict)
    return wrapper


# ============================================================================
# Kết nối & tài liệu
# ============================================================================

@mcp.tool()
@safe
def check_autocad_connection() -> dict:
    """Kiểm tra kết nối tới AutoCAD 2022: phiên bản, số bản vẽ đang mở, có đang kẹt lệnh không.

    Nên gọi tool này đầu tiên khi nghi ngờ AutoCAD chưa mở hoặc đang treo.
    """
    return acad.get_status()


@mcp.tool()
@safe
def get_active_document_info() -> dict:
    """Thông tin chi tiết bản vẽ hiện hành: tên file, đường dẫn, số đối tượng, layer, trạng thái lưu."""
    return acad.get_document_info()


@mcp.tool()
@safe
def list_open_documents() -> dict:
    """Liệt kê tất cả bản vẽ đang mở trong AutoCAD, kèm chỉ số và cờ đánh dấu bản vẽ hiện hành."""
    return {"documents": acad.list_open_documents()}


@mcp.tool()
@safe
def switch_document(name_or_index: str) -> dict:
    """Chuyển bản vẽ hiện hành sang một bản vẽ khác đang mở.

    :param name_or_index: Tên file (vd 'Drawing1.dwg') hoặc chỉ số lấy từ list_open_documents.
    """
    return {"message": acad.activate_document(name_or_index)}


@mcp.tool()
@safe
def create_new_document(template_path: Optional[str] = None) -> dict:
    """Tạo bản vẽ mới trong AutoCAD.

    :param template_path: Đường dẫn file template .dwt (tùy chọn).
    """
    return {"message": acad.new_document(template_path)}


@mcp.tool()
@safe
def open_dwg_document(file_path: str) -> dict:
    """Mở một file .dwg / .dxf / .dwt từ ổ đĩa vào AutoCAD 2022.

    :param file_path: Đường dẫn tuyệt đối hoặc tương đối tới file.
    """
    return {"message": acad.open_document(file_path)}


@mcp.tool()
@safe
def save_document(file_path: Optional[str] = None) -> dict:
    """Lưu bản vẽ hiện tại, hoặc lưu thành file mới (Save As).

    :param file_path: Đường dẫn lưu mới. Để trống sẽ lưu đè - bản vẽ chưa từng lưu sẽ báo lỗi rõ ràng.
    """
    return {"message": acad.save_document(file_path)}


@mcp.tool()
@safe
def close_document(save_changes: bool = True, file_path: Optional[str] = None) -> dict:
    """Đóng bản vẽ hiện hành.

    :param save_changes: True = lưu trước khi đóng, False = bỏ thay đổi.
    :param file_path: Nếu có, lưu sang đường dẫn này rồi mới đóng.
    """
    return {"message": acad.close_document(save_changes, file_path)}


# ============================================================================
# Vẽ hình học
# ============================================================================

@mcp.tool()
@safe
def draw_line(
    start_x: float, start_y: float,
    end_x: float, end_y: float,
    start_z: float = 0.0, end_z: float = 0.0,
    layer: Optional[str] = None,
    color_index: Optional[int] = None,
    linetype: Optional[str] = None,
    space: str = "model",
) -> dict:
    """Vẽ một đoạn thẳng (Line).

    :param start_x: Tọa độ X điểm đầu
    :param start_y: Tọa độ Y điểm đầu
    :param end_x: Tọa độ X điểm cuối
    :param end_y: Tọa độ Y điểm cuối
    :param start_z: Tọa độ Z điểm đầu (mặc định 0)
    :param end_z: Tọa độ Z điểm cuối (mặc định 0)
    :param layer: Tên layer, tự tạo nếu chưa có
    :param color_index: Màu AutoCAD Color Index 0-256 (1 đỏ, 2 vàng, 3 lục, 4 cyan, 5 lam, 6 tím, 7 trắng/đen)
    :param linetype: Tên linetype, vd 'DASHED', 'CENTER' - tự nạp từ acadiso.lin
    :param space: 'model' hoặc 'paper'
    """
    return acad.add_line((start_x, start_y, start_z), (end_x, end_y, end_z),
                         layer, color_index, linetype, space)


@mcp.tool()
@safe
def draw_circle(
    center_x: float, center_y: float,
    radius: float = 10.0,
    center_z: float = 0.0,
    layer: Optional[str] = None,
    color_index: Optional[int] = None,
    linetype: Optional[str] = None,
    space: str = "model",
) -> dict:
    """Vẽ hình tròn (Circle).

    :param center_x: Tọa độ X tâm
    :param center_y: Tọa độ Y tâm
    :param radius: Bán kính, phải lớn hơn 0
    :param center_z: Tọa độ Z tâm
    :param layer: Tên layer
    :param color_index: Màu 0-256
    :param linetype: Tên linetype
    :param space: 'model' hoặc 'paper'
    """
    return acad.add_circle((center_x, center_y, center_z), radius,
                           layer, color_index, linetype, space)


@mcp.tool()
@safe
def draw_arc(
    center_x: float, center_y: float,
    radius: float = 10.0,
    start_angle_deg: float = 0.0,
    end_angle_deg: float = 90.0,
    center_z: float = 0.0,
    layer: Optional[str] = None,
    color_index: Optional[int] = None,
    linetype: Optional[str] = None,
    space: str = "model",
) -> dict:
    """Vẽ cung tròn (Arc). Góc tính bằng ĐỘ, ngược chiều kim đồng hồ từ trục X dương.

    :param center_x: Tọa độ X tâm
    :param center_y: Tọa độ Y tâm
    :param radius: Bán kính, phải lớn hơn 0
    :param start_angle_deg: Góc bắt đầu (độ)
    :param end_angle_deg: Góc kết thúc (độ)
    :param center_z: Tọa độ Z tâm
    :param layer: Tên layer
    :param color_index: Màu 0-256
    :param linetype: Tên linetype
    :param space: 'model' hoặc 'paper'
    """
    return acad.add_arc((center_x, center_y, center_z), radius,
                        start_angle_deg, end_angle_deg,
                        layer, color_index, linetype, space)


@mcp.tool()
@safe
def draw_ellipse(
    center_x: float, center_y: float,
    major_axis_x: float, major_axis_y: float,
    radius_ratio: float = 0.5,
    center_z: float = 0.0,
    major_axis_z: float = 0.0,
    layer: Optional[str] = None,
    color_index: Optional[int] = None,
) -> dict:
    """Vẽ hình elip (Ellipse).

    :param center_x: Tọa độ X tâm
    :param center_y: Tọa độ Y tâm
    :param major_axis_x: Thành phần X của VECTOR trục lớn tính từ tâm (không phải tọa độ điểm)
    :param major_axis_y: Thành phần Y của vector trục lớn
    :param radius_ratio: Tỉ số trục nhỏ / trục lớn, trong khoảng (0, 1]
    :param center_z: Tọa độ Z tâm
    :param major_axis_z: Thành phần Z của vector trục lớn
    :param layer: Tên layer
    :param color_index: Màu 0-256
    """
    return acad.add_ellipse((center_x, center_y, center_z),
                            (major_axis_x, major_axis_y, major_axis_z),
                            radius_ratio, layer, color_index)


@mcp.tool()
@safe
def draw_point(
    x: float, y: float, z: float = 0.0,
    layer: Optional[str] = None,
    color_index: Optional[int] = None,
) -> dict:
    """Vẽ một điểm (Point node).

    :param x: Tọa độ X
    :param y: Tọa độ Y
    :param z: Tọa độ Z
    :param layer: Tên layer
    :param color_index: Màu 0-256
    """
    return acad.add_point((x, y, z), layer, color_index)


@mcp.tool()
@safe
def draw_polyline_2d(
    coordinates: List[float],
    closed: bool = False,
    layer: Optional[str] = None,
    color_index: Optional[int] = None,
    linetype: Optional[str] = None,
    width: Optional[float] = None,
    elevation: Optional[float] = None,
    space: str = "model",
) -> dict:
    """Vẽ đường đa tuyến 2D (Lightweight Polyline).

    :param coordinates: Mảng tọa độ phẳng [x1,y1, x2,y2, x3,y3, ...] - số phần tử phải chẵn
    :param closed: Đóng kín đa tuyến hay không
    :param layer: Tên layer
    :param color_index: Màu 0-256
    :param linetype: Tên linetype
    :param width: Bề rộng nét không đổi (ConstantWidth)
    :param elevation: Cao độ Z của mặt phẳng chứa đa tuyến
    :param space: 'model' hoặc 'paper'
    """
    return acad.add_polyline_2d(coordinates, closed, layer, color_index,
                                linetype, width, elevation, space)


@mcp.tool()
@safe
def draw_polyline_3d(
    coordinates: List[float],
    closed: bool = False,
    layer: Optional[str] = None,
    color_index: Optional[int] = None,
) -> dict:
    """Vẽ đường đa tuyến 3D (3D Polyline).

    :param coordinates: Mảng tọa độ phẳng [x1,y1,z1, x2,y2,z2, ...] - số phần tử chia hết cho 3
    :param closed: Đóng kín hay không
    :param layer: Tên layer
    :param color_index: Màu 0-256
    """
    return acad.add_polyline_3d(coordinates, closed, layer, color_index)


@mcp.tool()
@safe
def draw_rectangle(
    x1: float, y1: float,
    x2: float, y2: float,
    layer: Optional[str] = None,
    color_index: Optional[int] = None,
    linetype: Optional[str] = None,
    space: str = "model",
) -> dict:
    """Vẽ hình chữ nhật khép kín từ hai góc đối diện.

    :param x1: X góc thứ nhất
    :param y1: Y góc thứ nhất
    :param x2: X góc đối diện
    :param y2: Y góc đối diện
    :param layer: Tên layer
    :param color_index: Màu 0-256
    :param linetype: Tên linetype
    :param space: 'model' hoặc 'paper'
    """
    if x1 == x2 or y1 == y2:
        raise ValueError(
            f"Hai góc phải khác nhau cả X lẫn Y để tạo hình chữ nhật "
            f"(nhận được ({x1},{y1}) và ({x2},{y2}))."
        )
    coords = [x1, y1, x2, y1, x2, y2, x1, y2]
    return acad.add_polyline_2d(coords, True, layer, color_index,
                                linetype, None, None, space)


@mcp.tool()
@safe
def draw_spline(
    coordinates: List[float],
    layer: Optional[str] = None,
    color_index: Optional[int] = None,
) -> dict:
    """Vẽ đường cong trơn (Spline) đi qua các điểm cho trước.

    :param coordinates: Mảng tọa độ phẳng [x1,y1,z1, x2,y2,z2, ...] - cần ít nhất 2 điểm
    :param layer: Tên layer
    :param color_index: Màu 0-256
    """
    return acad.add_spline(coordinates, None, None, layer, color_index)


@mcp.tool()
@safe
def draw_hatch(
    boundary_handles: List[str],
    pattern_name: str = "SOLID",
    scale: float = 1.0,
    angle_deg: float = 0.0,
    layer: Optional[str] = None,
    color_index: Optional[int] = None,
    associative: bool = True,
) -> dict:
    """Tô mặt cắt (Hatch) vào các biên KHÉP KÍN đã vẽ sẵn.

    Quy trình: vẽ biên bằng draw_polyline_2d(closed=True) hoặc draw_circle,
    lấy 'handle' trong kết quả rồi truyền vào đây.

    :param boundary_handles: Danh sách handle của các đường biên khép kín
    :param pattern_name: Tên mẫu, vd 'SOLID', 'ANSI31', 'AR-CONC', 'EARTH', 'NET'
    :param scale: Tỉ lệ mẫu (bỏ qua khi pattern là SOLID)
    :param angle_deg: Góc xoay mẫu (độ)
    :param layer: Tên layer
    :param color_index: Màu 0-256
    :param associative: Hatch liên kết với biên, tự cập nhật khi biên thay đổi
    """
    return acad.add_hatch(boundary_handles, pattern_name, scale, angle_deg,
                          layer, color_index, associative)


@mcp.tool()
@safe
def insert_block(
    block_name: str,
    insert_x: float, insert_y: float,
    insert_z: float = 0.0,
    x_scale: float = 1.0,
    y_scale: float = 1.0,
    z_scale: float = 1.0,
    rotation_deg: float = 0.0,
    layer: Optional[str] = None,
    space: str = "model",
) -> dict:
    """Chèn một block vào bản vẽ.

    :param block_name: Tên block có sẵn trong bản vẽ, HOẶC đường dẫn tới file .dwg ngoài
    :param insert_x: Tọa độ X điểm chèn
    :param insert_y: Tọa độ Y điểm chèn
    :param insert_z: Tọa độ Z điểm chèn
    :param x_scale: Tỉ lệ theo X
    :param y_scale: Tỉ lệ theo Y
    :param z_scale: Tỉ lệ theo Z
    :param rotation_deg: Góc xoay (độ)
    :param layer: Tên layer
    :param space: 'model' hoặc 'paper'
    """
    return acad.insert_block((insert_x, insert_y, insert_z), block_name,
                             x_scale, y_scale, z_scale, rotation_deg, layer, space)


# ============================================================================
# Chữ & kích thước
# ============================================================================

@mcp.tool()
@safe
def add_text_annotation(
    text: str,
    insert_x: float, insert_y: float,
    insert_z: float = 0.0,
    height: float = 2.5,
    rotation_deg: float = 0.0,
    layer: Optional[str] = None,
    color_index: Optional[int] = None,
    style: Optional[str] = None,
    space: str = "model",
) -> dict:
    """Thêm văn bản đơn dòng (Text).

    :param text: Nội dung chữ (hỗ trợ tiếng Việt nếu text style dùng font Unicode)
    :param insert_x: Tọa độ X điểm đặt
    :param insert_y: Tọa độ Y điểm đặt
    :param insert_z: Tọa độ Z điểm đặt
    :param height: Chiều cao chữ, phải lớn hơn 0
    :param rotation_deg: Góc xoay chữ (độ)
    :param layer: Tên layer
    :param color_index: Màu 0-256
    :param style: Tên text style có sẵn trong bản vẽ
    :param space: 'model' hoặc 'paper'
    """
    return acad.add_text(text, (insert_x, insert_y, insert_z), height, rotation_deg,
                         layer, color_index, style, None, space)


@mcp.tool()
@safe
def add_mtext_annotation(
    text: str,
    insert_x: float, insert_y: float,
    insert_z: float = 0.0,
    width: float = 50.0,
    height: float = 2.5,
    layer: Optional[str] = None,
    color_index: Optional[int] = None,
    style: Optional[str] = None,
    space: str = "model",
) -> dict:
    """Thêm văn bản nhiều dòng (MText). Dùng \\P để xuống dòng trong AutoCAD.

    :param text: Nội dung, có thể nhiều dòng
    :param insert_x: Tọa độ X điểm đặt (góc trên trái)
    :param insert_y: Tọa độ Y điểm đặt
    :param insert_z: Tọa độ Z điểm đặt
    :param width: Bề rộng hộp chữ; 0 = tự động theo nội dung
    :param height: Chiều cao chữ
    :param layer: Tên layer
    :param color_index: Màu 0-256
    :param style: Tên text style
    :param space: 'model' hoặc 'paper'
    """
    return acad.add_mtext(text, (insert_x, insert_y, insert_z), width, height,
                          layer, color_index, style, space)


@mcp.tool()
@safe
def add_aligned_dimension(
    point1_x: float, point1_y: float,
    point2_x: float, point2_y: float,
    dim_line_x: float, dim_line_y: float,
    layer: Optional[str] = None,
    text_override: Optional[str] = None,
) -> dict:
    """Tạo kích thước gióng nghiêng (Aligned Dimension) giữa 2 điểm.

    :param point1_x: X chân kích thước thứ nhất
    :param point1_y: Y chân kích thước thứ nhất
    :param point2_x: X chân kích thước thứ hai
    :param point2_y: Y chân kích thước thứ hai
    :param dim_line_x: X điểm đặt đường kích thước
    :param dim_line_y: Y điểm đặt đường kích thước
    :param layer: Tên layer
    :param text_override: Chuỗi ghi đè lên số đo, vd '150 (điển hình)'
    """
    return acad.add_dimension(
        "aligned",
        [(point1_x, point1_y, 0.0), (point2_x, point2_y, 0.0), (dim_line_x, dim_line_y, 0.0)],
        layer=layer, text_override=text_override)


@mcp.tool()
@safe
def add_dimension(
    kind: str,
    points: List[float],
    layer: Optional[str] = None,
    color_index: Optional[int] = None,
    text_override: Optional[str] = None,
    rotation_deg: float = 0.0,
    leader_length: Optional[float] = None,
    dim_style: Optional[str] = None,
) -> dict:
    """Tạo kích thước mọi loại.

    Số điểm cần trong 'points' (mảng phẳng x,y lần lượt):
      * aligned    : 3 điểm - chân 1, chân 2, vị trí đường kích thước
      * linear     : 3 điểm - chân 1, chân 2, vị trí đường kích thước (dùng rotation_deg)
      * horizontal : 3 điểm - như linear, ép góc 0 độ
      * vertical   : 3 điểm - như linear, ép góc 90 độ
      * angular    : 4 điểm - đỉnh góc, đầu cạnh 1, đầu cạnh 2, vị trí chữ
      * radial     : 2 điểm - tâm, điểm trên cung (dùng leader_length)
      * diametric  : 2 điểm - điểm trên cung, điểm đối xứng qua tâm

    :param kind: aligned | linear | horizontal | vertical | angular | radial | diametric
    :param points: Mảng phẳng [x1,y1, x2,y2, ...] theo đúng số điểm ở trên
    :param layer: Tên layer
    :param color_index: Màu 0-256
    :param text_override: Chuỗi ghi đè số đo
    :param rotation_deg: Góc đường kích thước cho kiểu 'linear'
    :param leader_length: Chiều dài đường dẫn cho radial/diametric
    :param dim_style: Tên dimension style có sẵn
    """
    flat = [float(v) for v in (points or [])]
    if len(flat) < 4 or len(flat) % 2 != 0:
        raise ValueError(
            f"'points' phải là mảng phẳng x,y với ít nhất 2 điểm (4 số); nhận được {len(flat)} số."
        )
    pts = [(flat[i], flat[i + 1], 0.0) for i in range(0, len(flat), 2)]
    return acad.add_dimension(kind, pts, layer, color_index, text_override,
                              rotation_deg, leader_length, dim_style)


@mcp.tool()
@safe
def add_leader(
    coordinates: List[float],
    annotation_text: Optional[str] = None,
    text_height: float = 2.5,
    layer: Optional[str] = None,
    color_index: Optional[int] = None,
) -> dict:
    """Thêm đường dẫn ghi chú (Leader) có mũi tên, kèm chữ ở đầu cuối.

    :param coordinates: Mảng tọa độ phẳng [x1,y1,z1, x2,y2,z2, ...] - mũi tên nằm ở điểm đầu
    :param annotation_text: Nội dung chú thích đặt ở điểm cuối
    :param text_height: Chiều cao chữ chú thích
    :param layer: Tên layer
    :param color_index: Màu 0-256
    """
    return acad.add_leader(coordinates, annotation_text, layer, color_index, text_height)


# ============================================================================
# Hiệu chỉnh đối tượng
# ============================================================================

@mcp.tool()
@safe
def modify_entities(
    handles: List[str],
    action: str,
    from_point: Optional[List[float]] = None,
    to_point: Optional[List[float]] = None,
    base_point: Optional[List[float]] = None,
    center_point: Optional[List[float]] = None,
    point1: Optional[List[float]] = None,
    point2: Optional[List[float]] = None,
    rotation_deg: Optional[float] = None,
    scale_factor: Optional[float] = None,
    distance: Optional[float] = None,
    rows: Optional[int] = None,
    columns: Optional[int] = None,
    levels: Optional[int] = None,
    row_spacing: Optional[float] = None,
    column_spacing: Optional[float] = None,
    level_spacing: Optional[float] = None,
    count: Optional[int] = None,
    fill_angle_deg: Optional[float] = None,
    delete_source: Optional[bool] = None,
) -> dict:
    """Di chuyển / sao chép / xoay / co giãn / lấy đối xứng / offset / tạo mảng / phá khối.

    Tham số cần theo từng 'action':
      * move        : from_point, to_point
      * copy        : (tùy chọn) from_point, to_point để vừa chép vừa dời
      * rotate      : base_point, rotation_deg
      * scale       : base_point, scale_factor
      * mirror      : point1, point2 (trục đối xứng), delete_source
      * offset      : distance (âm = offset về phía ngược lại)
      * array_rect  : rows, columns, levels, row_spacing, column_spacing, level_spacing
      * array_polar : count, center_point, fill_angle_deg
      * explode     : không cần tham số thêm

    :param handles: Danh sách handle đối tượng (lấy từ kết quả lệnh vẽ hoặc list_entities)
    :param action: move | copy | rotate | scale | mirror | offset | array_rect | array_polar | explode
    :param from_point: Điểm gốc phép dời, dạng [x, y, z]
    :param to_point: Điểm đích phép dời, dạng [x, y, z]
    :param base_point: Tâm xoay hoặc tâm co giãn, dạng [x, y, z]
    :param center_point: Tâm mảng tròn, dạng [x, y, z]
    :param point1: Điểm thứ nhất của trục đối xứng
    :param point2: Điểm thứ hai của trục đối xứng
    :param rotation_deg: Góc xoay (độ)
    :param scale_factor: Hệ số co giãn, khác 0
    :param distance: Khoảng cách offset
    :param rows: Số hàng của mảng chữ nhật
    :param columns: Số cột của mảng chữ nhật
    :param levels: Số tầng của mảng chữ nhật (mặc định 1)
    :param row_spacing: Khoảng cách giữa các hàng
    :param column_spacing: Khoảng cách giữa các cột
    :param level_spacing: Khoảng cách giữa các tầng
    :param count: Số bản sao của mảng tròn
    :param fill_angle_deg: Góc quét của mảng tròn (mặc định 360)
    :param delete_source: Xóa đối tượng gốc sau mirror/explode
    """
    kw = {k: v for k, v in {
        "from_point": from_point, "to_point": to_point, "base_point": base_point,
        "center_point": center_point, "point1": point1, "point2": point2,
        "rotation_deg": rotation_deg, "scale_factor": scale_factor, "distance": distance,
        "rows": rows, "columns": columns, "levels": levels,
        "row_spacing": row_spacing, "column_spacing": column_spacing,
        "level_spacing": level_spacing, "count": count,
        "fill_angle_deg": fill_angle_deg, "delete_source": delete_source,
    }.items() if v is not None}
    return acad.transform_entities(handles, action, **kw)


@mcp.tool()
@safe
def set_entity_properties(
    handles: List[str],
    layer: Optional[str] = None,
    color_index: Optional[int] = None,
    linetype: Optional[str] = None,
    lineweight: Optional[int] = None,
    text: Optional[str] = None,
) -> dict:
    """Đổi thuộc tính của các đối tượng đã có trong bản vẽ.

    :param handles: Danh sách handle đối tượng
    :param layer: Chuyển sang layer này (tự tạo nếu chưa có)
    :param color_index: Màu 0-256
    :param linetype: Tên linetype
    :param lineweight: Bề dày nét, đơn vị 1/100 mm (vd 25 = 0.25mm, -1 = ByLayer)
    :param text: Nội dung chữ mới (chỉ áp dụng cho Text/MText/Dimension)
    """
    return acad.set_entity_properties(handles, layer, color_index, linetype, lineweight, text)


@mcp.tool()
@safe
def delete_entities(
    handles: Optional[List[str]] = None,
    layer: Optional[str] = None,
    entity_type: Optional[str] = None,
    delete_all: bool = False,
    space: str = "model",
) -> dict:
    """Xóa đối tượng theo handle, theo layer, theo loại, hoặc xóa sạch không gian vẽ.

    Phải chỉ rõ ít nhất một tiêu chí - gọi rỗng sẽ báo lỗi chứ không xóa nhầm.

    :param handles: Danh sách handle cần xóa (ưu tiên cao nhất)
    :param layer: Xóa mọi đối tượng nằm trên layer này
    :param entity_type: Xóa theo loại, vd 'Line', 'Circle', 'Text', 'Hatch'
    :param delete_all: True = xóa toàn bộ đối tượng trong không gian vẽ
    :param space: 'model' hoặc 'paper'
    """
    return acad.delete_entities(handles, layer, entity_type, delete_all, space)


# ============================================================================
# Truy vấn bản vẽ
# ============================================================================

@mcp.tool()
@safe
def get_drawing_summary(space: str = "model", max_scan: int = 20000) -> dict:
    """Thống kê tổng quan: tổng số đối tượng, phân loại theo kiểu và theo layer, số layer, số block.

    Phải đọc từng đối tượng qua COM (~5ms mỗi cái) nên bản vẽ vài nghìn đối tượng
    mất vài chục giây; tổng số đối tượng luôn chính xác, riêng phần phân loại bị cắt theo max_scan.

    :param space: 'model' hoặc 'paper'
    :param max_scan: Trần số đối tượng được phân loại
    """
    return acad.get_drawing_summary(space, max_scan)


@mcp.tool()
@safe
def list_entities(
    limit: int = 50,
    entity_type_filter: Optional[str] = None,
    layer_filter: Optional[str] = None,
    space: str = "model",
    count_all: bool = False,
    max_scan: int = 20000,
) -> dict:
    """Liệt kê chi tiết các đối tượng: handle, layer, màu, tọa độ, kích thước.

    Mặc định dừng ngay khi đủ 'limit' nên rất nhanh kể cả trên bản vẽ lớn.

    :param limit: Số đối tượng trả về tối đa (1-5000)
    :param entity_type_filter: Lọc theo loại, vd 'Line', 'Circle', 'Text', 'Polyline', 'Hatch'
    :param layer_filter: Chỉ lấy đối tượng trên layer này
    :param space: 'model' hoặc 'paper'
    :param count_all: True = quét hết để biết tổng số khớp chính xác (chậm hơn nhiều)
    :param max_scan: Trần số đối tượng được quét, tránh treo trên bản vẽ khổng lồ
    """
    return acad.list_entities_details(limit, entity_type_filter, layer_filter, space,
                                      count_all, max_scan)


@mcp.tool()
@safe
def get_entity_details(handle: str) -> dict:
    """Đọc đầy đủ thông tin một đối tượng theo handle, kèm hộp bao (bounding box).

    :param handle: Handle của đối tượng, vd '2A7'
    """
    return acad.get_entity(handle)


@mcp.tool()
@safe
def get_selected_entities() -> dict:
    """Đọc các đối tượng mà người dùng đang chọn sẵn trên màn hình AutoCAD.

    Dùng khi người dùng nói 'những cái tôi đang chọn' - hãy bảo họ quét chọn trước rồi gọi tool này.
    """
    return acad.get_selection()


@mcp.tool()
@safe
def get_drawing_extents() -> dict:
    """Lấy giới hạn bao ngoài của toàn bộ đối tượng trong bản vẽ (EXTMIN / EXTMAX) kèm bề rộng, chiều cao."""
    return acad.get_drawing_extents()


@mcp.tool()
@safe
def find_or_replace_text(
    keyword: str,
    replace_with: Optional[str] = None,
    case_sensitive: bool = False,
    space: str = "model",
) -> dict:
    """Tìm chuỗi trong mọi Text / MText / Dimension, tùy chọn thay thế hàng loạt.

    :param keyword: Chuỗi cần tìm
    :param replace_with: Nếu có, thay thế chuỗi tìm được bằng chuỗi này
    :param case_sensitive: Phân biệt hoa thường
    :param space: 'model' hoặc 'paper'
    """
    return acad.find_text(keyword, replace_with, case_sensitive, space)


# ============================================================================
# Layer & bảng ký hiệu
# ============================================================================

@mcp.tool()
@safe
def list_drawing_layers() -> dict:
    """Danh sách toàn bộ layer kèm màu, trạng thái đóng băng / khóa / bật tắt / in được."""
    return {"layers": acad.list_layers()}


@mcp.tool()
@safe
def set_active_or_create_layer(
    layer_name: str,
    color_index: Optional[int] = None,
    set_active: bool = True,
    linetype: Optional[str] = None,
    frozen: Optional[bool] = None,
    locked: Optional[bool] = None,
    on: Optional[bool] = None,
    plottable: Optional[bool] = None,
) -> dict:
    """Tạo layer mới hoặc chỉnh sửa / kích hoạt layer có sẵn.

    :param layer_name: Tên layer (không chứa các ký tự < > / \\ " : ; ? * | , = `)
    :param color_index: Màu layer 1-255
    :param set_active: Đặt làm layer hiện hành
    :param linetype: Tên linetype, tự nạp từ acadiso.lin nếu bản vẽ chưa có
    :param frozen: Đóng băng layer
    :param locked: Khóa layer
    :param on: Bật (True) hay tắt (False) layer
    :param plottable: Cho phép in layer này hay không
    """
    return acad.create_or_set_layer(layer_name, color_index, set_active, linetype,
                                    frozen, locked, on, plottable)


@mcp.tool()
@safe
def delete_layer(layer_name: str, move_entities_to: Optional[str] = None) -> dict:
    """Xóa một layer khỏi bản vẽ.

    :param layer_name: Tên layer cần xóa (không xóa được layer '0')
    :param move_entities_to: Chuyển các đối tượng trên layer đó sang layer này trước khi xóa
    """
    return {"message": acad.delete_layer(layer_name, move_entities_to)}


@mcp.tool()
@safe
def list_blocks() -> dict:
    """Danh sách các block đã định nghĩa trong bản vẽ (bỏ qua block hệ thống và block ẩn danh)."""
    return {"blocks": acad.list_blocks()}


@mcp.tool()
@safe
def list_styles() -> dict:
    """Danh sách text style, dimension style, linetype và layout hiện có trong bản vẽ."""
    return acad.list_styles()


# ============================================================================
# Khung nhìn, biến hệ thống, lệnh AutoCAD
# ============================================================================

@mcp.tool()
@safe
def zoom_view(
    mode: str = "extents",
    point1: Optional[List[float]] = None,
    point2: Optional[List[float]] = None,
    magnification: Optional[float] = None,
) -> dict:
    """Điều khiển khung nhìn AutoCAD.

    :param mode: extents (vừa hết đối tượng) | all | window | center | previous
    :param point1: Góc thứ nhất cho 'window', hoặc tâm cho 'center', dạng [x, y]
    :param point2: Góc thứ hai cho 'window', dạng [x, y]
    :param magnification: Độ phóng cho 'center'
    """
    return {"message": acad.zoom(mode, point1, point2, magnification)}


@mcp.tool()
@safe
def regen_drawing() -> dict:
    """Vẽ lại (Regen) toàn bộ khung nhìn - dùng khi màn hình hiển thị chưa cập nhật."""
    return {"message": acad.regen()}


@mcp.tool()
@safe
def get_system_variable(name: str) -> dict:
    """Đọc một biến hệ thống AutoCAD.

    :param name: Tên biến, vd 'CLAYER', 'INSUNITS', 'DIMSCALE', 'LTSCALE', 'OSMODE'
    """
    return acad.get_variable(name)


@mcp.tool()
@safe
def set_system_variable(name: str, value: str) -> dict:
    """Đặt giá trị một biến hệ thống AutoCAD. Kiểu dữ liệu được suy ra từ giá trị hiện tại.

    :param name: Tên biến, vd 'LTSCALE', 'DIMSCALE', 'OSMODE'
    :param value: Giá trị mới ở dạng chuỗi, vd '50' hoặc '0.5'
    """
    return acad.set_variable(name, value)


@mcp.tool()
@safe
def send_autocad_command(command: str) -> dict:
    """Gửi một câu lệnh vào dòng lệnh AutoCAD (không lấy được giá trị trả về).

    Dùng cho các lệnh không có sẵn trong ActiveX API, vd 'PURGE ALL * N', '_QSAVE', '_REGEN'.
    Nếu cần LẤY KẾT QUẢ trả về thì dùng run_autolisp thay vì tool này.
    Lưu ý: lệnh chờ người dùng nhập liệu sẽ làm AutoCAD treo ở dòng lệnh.

    :param command: Chuỗi lệnh AutoCAD
    """
    return {"message": acad.send_command(command)}


@mcp.tool()
@safe
def run_autolisp(expression: str, timeout: float = 20.0) -> dict:
    """Chạy một biểu thức AutoLISP và LẤY VỀ giá trị trả về.

    Đây là lối thoát vạn năng cho những việc ActiveX API không làm được.
    Ví dụ: '(getvar "CLAYER")', '(+ 1 2)',
    '(vla-get-Count (vla-get-ModelSpace (vla-get-ActiveDocument (vlax-get-acad-object))))'
    Không dùng cho hàm chờ người dùng nhập (getpoint, getstring) - sẽ hết thời gian chờ.

    :param expression: Biểu thức AutoLISP, phải bắt đầu bằng '('
    :param timeout: Thời gian chờ tối đa, tính bằng giây
    """
    return acad.run_lisp(expression, timeout)


@mcp.tool()
@safe
def purge_drawing() -> dict:
    """Purge toàn bộ layer / block / style không còn được dùng, giúp giảm dung lượng file."""
    return {"message": acad.purge_all()}


@mcp.tool()
@safe
def audit_drawing(fix_errors: bool = True) -> dict:
    """Kiểm tra và sửa lỗi cấu trúc bản vẽ (lệnh AUDIT).

    :param fix_errors: True = tự sửa lỗi tìm thấy
    """
    return {"message": acad.audit(fix_errors)}


# ============================================================================
# Xuất file
# ============================================================================

@mcp.tool()
@safe
def export_drawing_to_pdf(
    output_path: str,
    plot_area: str = "extents",
    layout: Optional[str] = None,
    config_name: str = "DWG To PDF.pc3",
) -> dict:
    """Xuất bản vẽ ra PDF qua máy in ảo, có kiểm chứng file đã được tạo.

    :param output_path: Đường dẫn file PDF đích, vd 'D:/XuatBanVe/ban_ve.pdf'
    :param plot_area: display | extents | limits | view | window | layout
    :param layout: Tên layout cần in; để trống sẽ in layout đang hoạt động
    :param config_name: Tên máy in ảo, mặc định 'DWG To PDF.pc3'
    """
    return acad.export_pdf(output_path, plot_area, layout, config_name)


@mcp.tool()
@safe
def export_drawing_to_dxf(output_path: str) -> dict:
    """Xuất bản vẽ hiện tại ra file DXF.

    :param output_path: Đường dẫn file .dxf đích
    """
    return acad.export_dxf(output_path)


# ============================================================================
# Vẽ hàng loạt
# ============================================================================

@mcp.tool()
@safe
def batch_draw(operations: List[Dict[str, Any]], stop_on_error: bool = False) -> dict:
    """Vẽ NHIỀU đối tượng trong MỘT lần gọi - nhanh hơn nhiều lần gọi lẻ hàng chục lần.

    Luôn ưu tiên tool này khi cần vẽ từ vài chục đối tượng trở lên.
    Mỗi phần tử là một object có khóa 'type' cùng các tham số tương ứng:
      {"type":"line", "start":[0,0], "end":[100,0], "layer":"TRUC", "color":1}
      {"type":"circle", "center":[50,50], "radius":25}
      {"type":"arc", "center":[0,0], "radius":10, "start_angle_deg":0, "end_angle_deg":90}
      {"type":"ellipse", "center":[0,0], "major_axis":[20,0], "radius_ratio":0.5}
      {"type":"point", "position":[10,10]}
      {"type":"polyline", "coordinates":[0,0, 10,0, 10,10], "closed":true}
      {"type":"polyline3d", "coordinates":[0,0,0, 10,0,5]}
      {"type":"rectangle", "x1":0, "y1":0, "x2":100, "y2":50}
      {"type":"text", "text":"KM83+075", "insertion":[0,0], "height":2.5, "rotation_deg":0}
      {"type":"mtext", "text":"Ghi chú", "insertion":[0,0], "width":50, "height":2.5}
      {"type":"block", "block_name":"COT", "insertion":[0,0], "rotation_deg":0}
      {"type":"dimension", "kind":"aligned", "points":[[0,0],[100,0],[50,-10]]}
    Khóa dùng chung cho mọi loại: layer, color, linetype.

    :param operations: Danh sách các đối tượng cần vẽ, tối đa 5000 mỗi lần gọi
    :param stop_on_error: True = dừng ngay khi gặp lỗi; False = bỏ qua mục lỗi và vẽ tiếp
    """
    return acad.batch_draw(operations, stop_on_error)


if __name__ == "__main__":
    mcp.run(transport="stdio")
