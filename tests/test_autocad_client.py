"""
Kiểm tra hành vi của `autocad_client` bằng đối tượng COM giả.
=============================================================
Bộ test còn lại trong repo kiểm *hợp đồng* của tool (có mô tả, có schema, không
để ngoại lệ lọt ra). Nhóm test này kiểm *hành vi* của ba chỗ mà hợp đồng không
nói được gì, và cả ba đều từng sai trong thực tế:

  * `add_hatch` dồn nhiều biên vào một vòng thay vì mỗi biên một vòng;
  * kích thước tạo ra bỏ qua các biến hệ thống `DIM*` của bản vẽ;
  * lỗi COM tạm thời trong vòng phân giải handle bị ghi thành "không tìm thấy".

Không test nào cần AutoCAD: mọi thứ chạm tới COM đều được thay bằng đối tượng giả.
"""

import sys
from pathlib import Path

import pytest
from conftest import chi_tren_windows

ROOT = Path(__file__).resolve().parent.parent
AUTOCAD_DIR = ROOT / "autocad-mcp"

pytestmark = chi_tren_windows


@pytest.fixture(scope="module")
def acad_module():
    if str(AUTOCAD_DIR) not in sys.path:
        sys.path.insert(0, str(AUTOCAD_DIR))
    import autocad_client

    return autocad_client


@pytest.fixture
def client(acad_module):
    """Một AutoCADClient chưa hề kết nối - đủ để gọi các phương thức thuần."""
    c = acad_module.AutoCADClient.__new__(acad_module.AutoCADClient)
    c.app = object()
    c.doc = None
    c._layer_cache = {}
    return c


def khong_boc(method):
    """Bản gốc của một phương thức, bỏ lớp _guard (retry + dịch lỗi)."""
    return method.__wrapped__


# ----------------------------------------------------------------------
# 1. Hatch: mỗi biên khép kín phải là MỘT vòng riêng
# ----------------------------------------------------------------------

class _HatchGia:
    def __init__(self):
        self.loops = []
        self.Area = 0.0

    def AppendOuterLoop(self, payload):
        self.loops.append(payload)

    def Evaluate(self):
        pass


class _KhongGianGia:
    def __init__(self, hatch):
        self._hatch = hatch
        self.hatch_args = None

    def AddHatch(self, pattern_type, pattern_name, associative):
        self.hatch_args = (pattern_type, pattern_name, associative)
        return self._hatch


class _DocGia:
    def __init__(self, model_space=None, variables=None):
        self.ModelSpace = model_space
        self._vars = variables or {}
        self.Name = "Drawing_gia.dwg"

    def GetVariable(self, name):
        if name not in self._vars:
            raise KeyError(name)
        return self._vars[name]


def test_moi_bien_hatch_la_mot_vong_rieng(client):
    """Ba biên rời rạc phải sinh ra ba lời gọi AppendOuterLoop, mỗi lời gọi một biên.

    AppendOuterLoop nhận MỘT vòng khép kín. Dồn cả ba vào một mảng thì AutoCAD hiểu
    là ba đoạn cong ghép thành một vòng duy nhất - không khép được, và nó trả về
    "Invalid input" chứ không nói gì tới số lượng.
    """
    hatch = _HatchGia()
    client.doc = _DocGia(model_space=_KhongGianGia(hatch))
    client.objects = lambda items: list(items)          # bỏ lớp VARIANT của COM
    client._by_handle = lambda h: f"<bien {h}>"
    client._apply_props = lambda *a, **k: []
    client._result = lambda ent, kind, warn, **extra: dict(extra, type=kind)

    kq = khong_boc(client.add_hatch)(
        client, ["A1", "A2", "A3"], pattern_name="ANSI31", scale=40
    )

    assert len(hatch.loops) == 3, "phải có đúng một vòng cho mỗi biên"
    assert hatch.loops == [["<bien A1>"], ["<bien A2>"], ["<bien A3>"]]
    assert kq["boundaries"] == 3


def test_hatch_khong_co_bien_thi_bao_loi(client):
    client.doc = _DocGia(model_space=_KhongGianGia(_HatchGia()))
    with pytest.raises(ValueError):
        khong_boc(client.add_hatch)(client, [])


# ----------------------------------------------------------------------
# 2. Kích thước: biến hệ thống DIM* phải ăn vào đối tượng
# ----------------------------------------------------------------------

class _KichThuocGia:
    """Giữ nguyên giá trị mặc định của template hệ inch cho tới khi bị ghi đè."""

    def __init__(self):
        self.ScaleFactor = 1.0
        self.TextHeight = 0.18
        self.ArrowheadSize = 0.18
        self.ExtensionLineExtend = 0.18
        self.ExtensionLineOffset = 0.0625
        self.TextGap = 0.09
        self.PrimaryUnitsPrecision = 4


BIEN_MAU = {
    "DIMSCALE": 80.0,
    "DIMTXT": 3.5,
    "DIMASZ": 3.5,
    "DIMEXE": 1.25,
    "DIMEXO": 0.625,
    "DIMGAP": 1.0,
    "DIMDEC": 0,
}


def test_dong_bo_bien_dim_xuong_doi_tuong(client):
    """AddDim* của ActiveX lấy thuộc tính từ dimension style, KHÔNG đọc biến DIM*.

    Với bản vẽ milimet dùng template hệ inch, để nguyên thì chữ số cao 0,18 mm trên
    hình dài vài nghìn mm - trông như kích thước bị mất chữ, mà không có lỗi nào.
    """
    client.doc = _DocGia(variables=dict(BIEN_MAU))
    ent = _KichThuocGia()

    canh_bao = client._sync_dim_vars(ent)

    assert canh_bao == []
    assert ent.ScaleFactor == 80.0
    assert ent.TextHeight == 3.5
    assert ent.ArrowheadSize == 3.5
    assert ent.ExtensionLineExtend == 1.25
    assert ent.ExtensionLineOffset == 0.625
    assert ent.TextGap == 1.0
    assert ent.PrimaryUnitsPrecision == 0
    assert isinstance(ent.PrimaryUnitsPrecision, int), "DIMDEC là số nguyên"

    # Chiều cao chữ hiển thị = DIMTXT × DIMSCALE, phải đọc được ở tỉ lệ bản vẽ.
    assert ent.TextHeight * ent.ScaleFactor == 280.0


def test_bien_dim_thieu_thi_bo_qua_chu_khong_hong(client, acad_module):
    """Bản AutoCAD cũ có thể không có đủ mọi biến - thiếu một biến không được làm hỏng cả lệnh."""
    client.doc = _DocGia(variables={"DIMSCALE": 50.0})
    ent = _KichThuocGia()

    canh_bao = client._sync_dim_vars(ent)

    assert canh_bao == []
    assert ent.ScaleFactor == 50.0
    assert ent.TextHeight == 0.18, "biến không có thì giữ nguyên giá trị của style"


def test_moi_bien_dim_anh_xa_toi_mot_thuoc_tinh_co_that(client, acad_module):
    """Bảng ánh xạ không được chứa tên thuộc tính gõ sai - sai thì im lặng bỏ qua."""
    ent = _KichThuocGia()
    for _, prop in acad_module.AutoCADClient._DIM_VAR_MAP:
        assert hasattr(ent, prop), f"thuộc tính '{prop}' không có trên đối tượng kích thước"


# ----------------------------------------------------------------------
# 3. Lỗi tạm thời không được biến thành "không tìm thấy handle"
# ----------------------------------------------------------------------

def test_loi_tam_thoi_khi_phan_giai_handle_duoc_nem_len(client):
    """AttributeError từ COM = con trỏ chết hoặc AutoCAD bận, KHÔNG phải "handle không có".

    Nuốt nó vào danh sách failures thì cả lô bị báo "không tìm thấy" trong khi đối
    tượng vẫn nằm nguyên trong bản vẽ, và _guard mất luôn cơ hội dựng lại kết nối.
    Vòng phân giải chạy trước mọi thao tác xóa nên chạy lại từ đầu là an toàn.
    """
    def _chet(handle):
        raise AttributeError("<unknown>.HandleToObject")

    client._by_handle = _chet

    with pytest.raises(AttributeError):
        khong_boc(client.delete_entities)(client, handles=["2A3", "2E9"])


def test_handle_that_su_khong_ton_tai_van_vao_danh_sach_failures(client):
    """Ngược lại: lỗi 'không tìm thấy' thật thì phải báo theo từng handle, không ném lên."""
    def _khong_thay(handle):
        raise ValueError(f"Không tìm thấy đối tượng có handle '{handle}'")

    client._by_handle = _khong_thay

    kq = khong_boc(client.delete_entities)(client, handles=["ZZZ1", "ZZZ2"])

    assert kq["deleted"] == 0
    assert kq["failed"] == 2
    assert {f["handle"] for f in kq["failures"]} == {"ZZZ1", "ZZZ2"}


def test_thong_diep_khong_tim_thay_neu_ten_ban_ve(client):
    """Handle chỉ duy nhất trong một bản vẽ, nên thông điệp phải nói đã tìm ở đâu."""
    class _DocKhongCoGi(_DocGia):
        def HandleToObject(self, handle):
            raise ValueError("khong co")

    client.doc = _DocKhongCoGi()

    with pytest.raises(ValueError) as loi:
        client._by_handle("2A3")

    assert "Drawing_gia.dwg" in str(loi.value)
