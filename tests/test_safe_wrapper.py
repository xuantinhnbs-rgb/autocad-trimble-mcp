"""
Kiểm tra decorator `safe()` — trái tim của hợp đồng {"ok": ...}.
================================================================
Cả hai server đều bọc mọi tool bằng `safe()`. Nếu decorator này để lọt một
ngoại lệ thì AI nhận về vệt lỗi COM/.NET thô thay vì thông điệp đọc được, nên
nó xứng đáng có test riêng. Test không cần AutoCAD hay Trimble Connect.
"""

import pytest
from conftest import chi_tren_windows

pytestmark = chi_tren_windows


@pytest.fixture(params=["autocad", "trimble"])
def safe(request, autocad_server, trimble_server):
    """Lấy `safe()` của từng server để chắc chắn cả hai bản đều đúng."""
    return autocad_server.safe if request.param == "autocad" else trimble_server.safe


def test_dict_khong_co_khoa_ok_thi_duoc_them_ok_true(safe):
    @safe
    def fn() -> dict:
        return {"handle": "2A7"}

    assert fn() == {"ok": True, "handle": "2A7"}


def test_dict_da_co_khoa_ok_thi_giu_nguyen(safe):
    @safe
    def fn() -> dict:
        return {"ok": False, "error": "loi cu the"}

    assert fn() == {"ok": False, "error": "loi cu the"}


def test_list_duoc_goi_thanh_count_va_items(safe):
    @safe
    def fn() -> dict:
        return [1, 2, 3]

    assert fn() == {"ok": True, "count": 3, "items": [1, 2, 3]}


def test_gia_tri_don_duoc_boc_vao_result(safe):
    @safe
    def fn() -> dict:
        return "TRUC"

    assert fn() == {"ok": True, "result": "TRUC"}


def test_valueerror_thanh_thong_diep_tham_so_khong_hop_le(safe):
    @safe
    def fn() -> dict:
        raise ValueError("ban kinh phai lon hon 0")

    out = fn()
    assert out["ok"] is False
    assert "ban kinh phai lon hon 0" in out["error"]


def test_ngoai_le_la_khong_bao_gio_thoat_ra_ngoai(safe):
    """Lưới an toàn cuối cùng: kể cả lỗi không lường trước cũng phải thành {"ok": false}."""

    class LoiLa(Exception):
        pass

    @safe
    def fn() -> dict:
        raise LoiLa("hong bat ngo")

    out = fn()
    assert out["ok"] is False
    assert "LoiLa" in out["error"]


def test_giu_nguyen_chu_ky_ham_de_mcp_sinh_dung_schema(safe):
    """MCP sinh JSON schema từ chữ ký hàm, nên `safe()` phải giữ nguyên nó."""
    import inspect

    @safe
    def fn(ten: str, so: int = 5) -> dict:
        """Mo ta ngan."""
        return {}

    sig = inspect.signature(fn)
    assert list(sig.parameters) == ["ten", "so"]
    assert sig.parameters["so"].default == 5
    assert sig.return_annotation is dict
    assert fn.__doc__ == "Mo ta ngan."
