"""
Trimble Connect Desktop MCP Server
==================================
Giao tiếp chuẩn Model Context Protocol (MCP) để AI điều khiển trực tiếp
Trimble Connect for Desktop đang chạy trên máy.

Hợp đồng trả về: MỌI tool đều trả về một object JSON có khóa "ok".
  * Thành công -> {"ok": true, ...dữ liệu...}
  * Thất bại   -> {"ok": false, "error": "<thông điệp tiếng Việt nói rõ cách khắc phục>"}
Không tool nào ném ngoại lệ ra ngoài, nên phía AI luôn nhận được phản hồi đọc được
thay vì một vệt lỗi .NET thô.

Chạy bằng:  python -m trimble_mcp.server
"""

import functools
from typing import Any, List, Optional

from mcp.server.mcpserver import MCPServer

from .trimble_client import TrimbleError, get_bridge

mcp = MCPServer(
    "Trimble-Connect-MCP",
    instructions=(
        "Điều khiển Trimble Connect for Desktop trên máy này: đọc dự án, nạp/gỡ model, "
        "tìm và tô màu đối tượng, đọc thuộc tính IFC, quản lý view và camera.\n"
        "Mọi thao tác đều cần Trimble Connect for Desktop đang mở VÀ đã mở một project — "
        "gọi get_status trước để kiểm tra. Đối tượng được định danh bằng identifier lấy từ "
        "find_objects hoặc get_selection."
    ),
)


def safe(fn):
    """Bọc một tool: không bao giờ ném lỗi, luôn trả về dict có khóa 'ok'."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs) -> dict:
        try:
            result = fn(*args, **kwargs)
        except TrimbleError as exc:
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

    return wrapper



def call(cmd: str, **args: Any) -> Any:
    """Gửi một lệnh xuống cầu nối .NET đang giữ kết nối tới Trimble Connect."""
    return get_bridge().call(cmd, **args)


# ============================================================================
# Kết nối & dự án
# ============================================================================

@mcp.tool()
@safe
def get_status(auto_connect: bool = True) -> dict:
    """Kiểm tra kết nối tới Trimble Connect for Desktop và dự án đang mở.

    Nên gọi tool này đầu tiên. Trả về trạng thái kết nối, tên instance, ứng dụng
    có đang chạy không, và thông tin dự án đang active (nếu có).
    """
    return call("status", auto_connect=auto_connect)


@mcp.tool()
@safe
def list_connections(timeout: float = 15.0) -> dict:
    """Liệt kê các instance Trimble Connect for Desktop đang mở trên máy."""
    return call("list_connections", timeout=timeout, _timeout=timeout + 30)


@mcp.tool()
@safe
def connect(connection_name: Optional[str] = None, timeout: float = 15.0) -> dict:
    """Kết nối (hoặc kết nối lại) tới một instance Trimble Connect for Desktop.

    Bỏ trống connection_name để dùng instance đầu tiên tìm thấy.
    """
    return call("connect", connection_name=connection_name, timeout=timeout,
                _timeout=timeout + 30)


@mcp.tool()
@safe
def start_desktop_app(connection_name: Optional[str] = None, wait_ms: int = 30000) -> dict:
    """Khởi động một instance Trimble Connect for Desktop mới và trả về tên kết nối."""
    return call("start_app", connection_name=connection_name, wait_ms=wait_ms,
                _timeout=wait_ms / 1000 + 60)


@mcp.tool()
@safe
def refresh() -> dict:
    """Đọc lại dự án đang active. Dùng sau khi đổi dự án trong ứng dụng."""
    return call("refresh")


@mcp.tool()
@safe
def get_project() -> dict:
    """Lấy tên, identifier và thư mục làm việc của dự án đang mở."""
    return call("get_project")


# ============================================================================
# Model
# ============================================================================

@mcp.tool()
@safe
def list_models(state: str = "all") -> dict:
    """Liệt kê model trong dự án.

    state: all | loaded | unloaded. Mỗi model trả về identifier, name, version và
    cờ loaded cho biết có đang được nạp vào khung nhìn 3D hay không.
    """
    return call("list_models", state=state)


@mcp.tool()
@safe
def load_models(model_ids: List[str]) -> dict:
    """Nạp các model (theo identifier lấy từ list_models) vào khung nhìn 3D."""
    return call("load_models", model_ids=model_ids)


@mcp.tool()
@safe
def unload_models(model_ids: List[str], exclude_from_scope: bool = False) -> dict:
    """Gỡ các model khỏi khung nhìn 3D.

    exclude_from_scope=True sẽ loại model khỏi phạm vi làm việc chứ không chỉ ẩn đi.
    """
    return call("unload_models", model_ids=model_ids, exclude_from_scope=exclude_from_scope)


@mcp.tool()
@safe
def get_model_placement(model_id: str) -> dict:
    """Đọc vị trí, cao độ, tỷ lệ và góc xoay của một model."""
    return call("get_model_placement", model_id=model_id)


@mcp.tool()
@safe
def set_model_placement(
    model_id: str,
    position_x: Optional[float] = None,
    position_y: Optional[float] = None,
    elevation: Optional[float] = None,
    scale: Optional[float] = None,
    rotation_angle: Optional[float] = None,
    rotation_axis: str = "Z",
) -> dict:
    """Đặt lại vị trí / tỷ lệ / góc xoay cho một model.

    Chỉ những tham số được truyền mới thay đổi. rotation_axis: X | Y | Z.
    """
    return call(
        "set_model_placement",
        model_id=model_id,
        position_x=position_x,
        position_y=position_y,
        elevation=elevation,
        scale=scale,
        rotation_angle=rotation_angle,
        rotation_axis=rotation_axis,
    )


@mcp.tool()
@safe
def reset_model_placement(model_id: str) -> dict:
    """Trả model về placement gốc."""
    return call("reset_model_placement", model_id=model_id)


@mcp.tool()
@safe
def get_model_content_path(model_id: str) -> dict:
    """Lấy đường dẫn file của model trong thư mục làm việc cục bộ.

    Trả về null với các model đồng bộ từ cloud mà Trimble không phơi ra đường
    dẫn cục bộ — khi đó dùng get_object_attributes để đọc dữ liệu thay vì đọc file.
    """
    return call("get_model_content_path", model_id=model_id)


# ============================================================================
# Đối tượng trong model
# ============================================================================

@mcp.tool()
@safe
def find_objects(
    by: str = "all",
    model_id: Optional[str] = None,
    type_name: Optional[str] = None,
    visual_state: Optional[str] = None,
    attribute_name: Optional[str] = None,
    attribute_value: Optional[str] = None,
    attribute_set: Optional[str] = None,
    ids: Optional[List[str]] = None,
    selection_mode: Optional[str] = None,
    limit: int = 500,
    with_type_name: bool = False,
    with_type_summary: bool = False,
) -> dict:
    """Tìm đối tượng trong toàn dự án hoặc trong một model.

    by:
      all           - mọi đối tượng trong phạm vi
      selected      - đang được chọn
      type          - theo type_name (ví dụ IfcWall, IfcBeam)
      visual_state  - theo visual_state: Visible | Hidden | Highlighted | Unhighlighted
      attribute     - theo attribute_name (kèm attribute_value, attribute_set nếu cần)
      ids           - theo danh sách identifier

    selection_mode: HighestLevelAssembliesAndSystems | IndividualObjects.
    with_type_name lấy thêm tên kiểu cho từng đối tượng (chậm hơn, nên giới hạn limit).
    with_type_summary trả về danh sách các kiểu có mặt trong kết quả.
    """
    return call(
        "find_objects",
        by=by,
        model_id=model_id,
        type_name=type_name,
        visual_state=visual_state,
        attribute_name=attribute_name,
        attribute_value=attribute_value,
        attribute_set=attribute_set,
        ids=ids,
        selection_mode=selection_mode,
        limit=limit,
        with_type_name=with_type_name,
        with_type_summary=with_type_summary,
    )


@mcp.tool()
@safe
def get_selection(
    model_id: Optional[str] = None,
    limit: int = 500,
    with_type_name: bool = False,
) -> dict:
    """Lấy các đối tượng người dùng đang chọn trong khung nhìn 3D."""
    return call("get_selection", model_id=model_id, limit=limit, with_type_name=with_type_name)


@mcp.tool()
@safe
def select_objects(
    ids: List[str],
    selected: bool = True,
    model_id: Optional[str] = None,
) -> dict:
    """Chọn (hoặc bỏ chọn) các đối tượng theo identifier."""
    return call("select_objects", ids=ids, selected=selected, model_id=model_id)


@mcp.tool()
@safe
def set_visual_state(
    ids: List[str],
    visual_state: str = "Visible",
    model_id: Optional[str] = None,
) -> dict:
    """Đặt trạng thái hiển thị: Visible | Hidden | Highlighted | Unhighlighted."""
    return call("set_visual_state", ids=ids, visual_state=visual_state, model_id=model_id)


@mcp.tool()
@safe
def reset_visual_state(ids: List[str], model_id: Optional[str] = None) -> dict:
    """Trả trạng thái hiển thị của các đối tượng về mặc định."""
    return call("reset_visual_state", ids=ids, model_id=model_id)


@mcp.tool()
@safe
def isolate_objects(ids: Optional[List[str]] = None, model_id: Optional[str] = None) -> dict:
    """Ẩn mọi thứ và chỉ hiện lại các đối tượng đã cho.

    Bỏ trống ids để isolate đúng những gì người dùng đang chọn.
    Dùng reset_all để trả lại bình thường.
    """
    return call("isolate_objects", ids=ids, model_id=model_id)


@mcp.tool()
@safe
def set_color(ids: List[str], color: str, model_id: Optional[str] = None) -> dict:
    """Tô màu các đối tượng.

    color nhận "#RRGGBB", "255,0,0" hoặc tên màu tiếng Anh (red, blue...).
    """
    return call("set_color", ids=ids, color=color, model_id=model_id)


@mcp.tool()
@safe
def reset_color(ids: List[str], model_id: Optional[str] = None) -> dict:
    """Trả màu các đối tượng về màu gốc của model."""
    return call("reset_color", ids=ids, model_id=model_id)


@mcp.tool()
@safe
def reset_all(
    model_id: Optional[str] = None,
    visual_state: bool = True,
    color: bool = True,
) -> dict:
    """Trả toàn bộ đối tượng về hiển thị và màu gốc (hủy isolate / tô màu)."""
    return call("reset_all", model_id=model_id, visual_state=visual_state, color=color)


@mcp.tool()
@safe
def get_object_attributes(
    ids: List[str],
    model_id: Optional[str] = None,
    limit: int = 20,
) -> dict:
    """Đọc toàn bộ bộ thuộc tính (property set) của các đối tượng.

    Kết quả có thể rất dài nên mặc định chỉ lấy 20 đối tượng đầu.
    """
    return call("get_object_attributes", ids=ids, model_id=model_id, limit=limit)


@mcp.tool()
@safe
def get_attribute_names(ids: Optional[List[str]] = None, model_id: Optional[str] = None) -> dict:
    """Liệt kê tên các thuộc tính có trên tập đối tượng.

    Bỏ trống ids để dùng những gì đang được chọn. Dùng tool này để biết nên lọc
    theo attribute_name nào trước khi gọi find_objects hoặc get_attribute.
    """
    return call("get_attribute_names", ids=ids, model_id=model_id)


@mcp.tool()
@safe
def get_attribute(
    ids: List[str],
    attribute_name: str,
    attribute_set: Optional[str] = None,
    model_id: Optional[str] = None,
    limit: int = 100,
) -> dict:
    """Đọc một thuộc tính cụ thể trên nhiều đối tượng."""
    return call(
        "get_attribute",
        ids=ids,
        attribute_name=attribute_name,
        attribute_set=attribute_set,
        model_id=model_id,
        limit=limit,
    )


@mcp.tool()
@safe
def get_related_objects(
    ids: List[str],
    relation: str = "Child",
    level: str = "Immediate",
    model_id: Optional[str] = None,
    limit: int = 500,
) -> dict:
    """Duyệt cây phân cấp: relation = Child | Parent, level = Immediate | All."""
    return call(
        "get_related_objects",
        ids=ids,
        relation=relation,
        level=level,
        model_id=model_id,
        limit=limit,
    )


# ============================================================================
# View & camera
# ============================================================================

@mcp.tool()
@safe
def list_views() -> dict:
    """Liệt kê các view đã lưu trong dự án."""
    return call("list_views")


@mcp.tool()
@safe
def activate_view(identifier: Optional[str] = None, name: Optional[str] = None) -> dict:
    """Mở một view đã lưu, theo identifier hoặc theo tên."""
    return call("activate_view", identifier=identifier, name=name)


@mcp.tool()
@safe
def create_view(name: str) -> dict:
    """Lưu trạng thái khung nhìn hiện tại thành một view mới."""
    return call("create_view", name=name)


@mcp.tool()
@safe
def get_camera() -> dict:
    """Đọc camera hiện tại: vị trí, hướng nhìn, vector up, kiểu chiếu."""
    return call("get_camera")


@mcp.tool()
@safe
def set_camera(
    location: Optional[List[float]] = None,
    direction: Optional[List[float]] = None,
    up: Optional[List[float]] = None,
    projection: Optional[str] = None,
    view_angle: Optional[float] = None,
    view_scale: Optional[float] = None,
    duration: float = 0.0,
) -> dict:
    """Đặt camera. Các vector dạng [x, y, z]; tham số bỏ trống sẽ giữ nguyên.

    projection: Perspective | Orthogonal. duration là thời gian chuyển cảnh (giây).

    Lưu ý: chuyển sang Orthogonal thì Trimble tự tính lại location để lấy khung
    hình mới, nên vị trí trả về sẽ khác vị trí yêu cầu. Ngoài ra đừng gọi ngay
    sau zoom_to_objects — hoạt ảnh zoom còn đang chạy sẽ ghi đè camera vừa đặt.
    """
    return call(
        "set_camera",
        location=location,
        direction=direction,
        up=up,
        projection=projection,
        view_angle=view_angle,
        view_scale=view_scale,
        duration=duration,
    )


@mcp.tool()
@safe
def zoom_to_objects(ids: Optional[List[str]] = None, model_id: Optional[str] = None) -> dict:
    """Đưa camera về khung các đối tượng đã cho (bỏ trống ids: dùng vùng đang chọn)."""
    return call("zoom_to_objects", ids=ids, model_id=model_id)


# ============================================================================
# Cài đặt ứng dụng
# ============================================================================

@mcp.tool()
@safe
def get_selection_mode() -> dict:
    """Đọc chế độ chọn đối tượng hiện tại của ứng dụng."""
    return call("get_selection_mode")


@mcp.tool()
@safe
def set_selection_mode(mode: str) -> dict:
    """Đặt chế độ chọn: HighestLevelAssembliesAndSystems | IndividualObjects."""
    return call("set_selection_mode", mode=mode)


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
