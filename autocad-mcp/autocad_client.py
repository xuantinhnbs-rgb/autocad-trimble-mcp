"""
AutoCAD COM Automation Client
==============================
Lớp giao tiếp COM tới AutoCAD. Được phát triển và kiểm thử trên AutoCAD 2022
(ProgID AutoCAD.Application.24.1); bản mới hơn kết nối được qua ProgID chung
AutoCAD.Application (xem PROG_IDS bên dưới), nhưng chưa được kiểm chứng đầy đủ.

Nguyên tắc thiết kế:
  * Mọi lỗi COM thô được dịch sang AcadError kèm thông điệp tiếng Việt rõ nghĩa.
  * Tự động thử lại khi AutoCAD báo bận (RPC_E_CALL_REJECTED) và tự kết nối lại
    khi con trỏ COM chết (AutoCAD bị đóng rồi mở lại).
  * Việc gán thuộc tính sau khi tạo đối tượng (layer, màu, linetype) không bao giờ
    làm hỏng cả thao tác - nó chỉ sinh cảnh báo. Nhờ vậy retry toàn hàm là an toàn,
    không sinh đối tượng trùng lặp.
"""

from __future__ import annotations

import functools
import math
import os
import queue
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional, Sequence

import pythoncom
import win32com.client
from win32com.client import VARIANT


class AcadError(Exception):
    """Lỗi đã được diễn giải sang thông điệp thân thiện cho người dùng."""


class _ComThread:
    """Thực thi mọi thao tác COM trên ĐÚNG MỘT luồng chuyên trách.

    Máy chủ MCP chạy các tool đồng bộ trong thread pool, nên mỗi lần gọi có thể rơi
    vào một luồng khác nhau. COM lại đòi CoInitialize riêng cho từng luồng và không
    cho dùng con trỏ giao diện chéo luồng - hệ quả là lỗi "CoInitialize has not been
    called". Dồn hết về một luồng vừa khử triệt để lỗi đó, vừa tuần tự hóa các lời
    gọi tới AutoCAD (bản thân AutoCAD cũng chỉ xử lý được một yêu cầu tại một thời điểm).
    """

    def __init__(self) -> None:
        self._queue: "queue.Queue[Optional[tuple]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def _ensure_started(self) -> threading.Thread:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="autocad-com",
                                                daemon=True)
                self._thread.start()
            return self._thread

    def _run(self) -> None:
        pythoncom.CoInitialize()
        try:
            while True:
                item = self._queue.get()
                if item is None:
                    return
                fn, args, kwargs, box, done = item
                try:
                    box.append((True, fn(*args, **kwargs)))
                except BaseException as exc:          # chuyển nguyên vẹn về luồng gọi
                    box.append((False, exc))
                finally:
                    done.set()
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    def call(self, fn, *args, **kwargs):
        thread = self._ensure_started()
        if threading.current_thread() is thread:
            return fn(*args, **kwargs)        # lời gọi lồng nhau - chạy thẳng, tránh kẹt
        box: List[tuple] = []
        done = threading.Event()
        self._queue.put((fn, args, kwargs, box, done))
        done.wait()
        ok, value = box[0]
        if ok:
            return value
        raise value


# --------------------------------------------------------------------------
# Bảng mã HRESULT của COM
# --------------------------------------------------------------------------
# AutoCAD đang bận (đang trong lệnh, đang mở hộp thoại, đang regen...) -> thử lại
_BUSY_HRESULTS = {
    -2147418111,  # 0x80010001 RPC_E_CALL_REJECTED
    -2147417846,  # 0x8001010A RPC_E_SERVERCALL_RETRYLATER
    -2147417851,  # 0x80010105 RPC_E_SERVERFAULT
}
# Con trỏ COM đã chết (AutoCAD đóng / khởi động lại) -> kết nối lại rồi thử lại
_DEAD_HRESULTS = {
    -2147417848,  # 0x80010108 RPC_E_DISCONNECTED
    -2147023174,  # 0x800706BA RPC_S_SERVER_UNAVAILABLE
    -2147220995,  # 0x800401FD CO_E_OBJNOTCONNECTED
    -2147221021,  # 0x800401E3 MK_E_UNAVAILABLE
}

PROG_IDS = ("AutoCAD.Application.24.1", "AutoCAD.Application.24", "AutoCAD.Application")

MAX_ATTEMPTS = 6
RETRY_DELAY = 0.35
CONNECTION_TTL = 1.0      # giây - trong khoảng này coi kết nối COM vẫn còn sống
MAX_SCAN = 20000          # trần quét ModelSpace để không treo trên bản vẽ khổng lồ


def _hresult(exc: BaseException) -> Optional[int]:
    """Trích mã HRESULT từ một pythoncom.com_error."""
    if isinstance(exc, pythoncom.com_error):
        try:
            return int(exc.args[0])
        except Exception:
            return None
    return None


def _com_description(exc: BaseException) -> str:
    """Lấy mô tả lỗi mà chính AutoCAD trả về (nằm trong EXCEPINFO)."""
    if isinstance(exc, pythoncom.com_error):
        try:
            excep = exc.args[2]
            if excep and len(excep) > 2 and excep[2]:
                return str(excep[2]).strip()
        except Exception:
            pass
        try:
            return str(exc.args[1] or "").strip()
        except Exception:
            pass
    return str(exc)


def _explain(exc: BaseException) -> str:
    """Dịch một ngoại lệ COM thành thông điệp tiếng Việt có tính hành động."""
    hr = _hresult(exc)
    desc = _com_description(exc)
    if hr in _BUSY_HRESULTS:
        return ("AutoCAD đang bận (đang thực hiện một lệnh hoặc đang mở hộp thoại). "
                "Hãy nhấn ESC trong AutoCAD rồi thử lại.")
    if hr in _DEAD_HRESULTS:
        return ("Mất kết nối tới AutoCAD (AutoCAD đã bị đóng hoặc khởi động lại). "
                "Hãy mở lại AutoCAD với ít nhất một bản vẽ.")
    if hr == -2147352571:  # 0x80020005 DISP_E_TYPEMISMATCH
        return f"Sai kiểu dữ liệu truyền vào AutoCAD: {desc}"
    if hr == -2147352567:  # 0x80020009 DISP_E_EXCEPTION
        return f"AutoCAD từ chối thao tác: {desc}"
    if hr == -2147352562:  # 0x8002000E DISP_E_BADPARAMCOUNT
        return f"Sai số lượng tham số gọi vào AutoCAD: {desc}"
    if hr == -2147352570:  # 0x80020006 DISP_E_UNKNOWNNAME
        return f"AutoCAD không hỗ trợ thuộc tính/phương thức này: {desc}"
    return desc or f"Lỗi COM không xác định (HRESULT={hr})"


def _reraise_if_transient(exc: BaseException) -> None:
    """Ném lại các lỗi CHỈ mang tính tạm thời để _guard còn cơ hội thử lại.

    Dùng trong những khối `except` vốn dịch lỗi thành "không tìm thấy X": nếu không
    lọc, một lần AutoCAD bận sẽ bị báo nhầm thành "biến/layer/handle không tồn tại"
    và mất luôn cơ chế thử lại.
    """
    hr = _hresult(exc)
    if hr in _BUSY_HRESULTS or hr in _DEAD_HRESULTS:
        raise exc
    # pywin32 phát AttributeError cho cả hai tình huống tạm thời: con trỏ dispatch
    # đã chết ("<unknown>.Layers") và AutoCAD bận từ chối phân giải tên phương thức
    # ("AutoCAD.Application.24.1.ZoomWindow"). Không bao giờ là tín hiệu "không tồn tại".
    if isinstance(exc, AttributeError):
        raise exc


class AutoCADClient:
    """Bọc toàn bộ AutoCAD ActiveX API. Mọi phương thức public đều tự phục hồi."""

    def __init__(self) -> None:
        self.app = None
        self.doc = None
        self._verified_at = 0.0                      # lần cuối ping COM thành công
        self._layer_cache: Dict[str, Any] = {}       # tên layer (lower) -> đối tượng Layer
        self._worker = _ComThread()                  # mọi COM chạy trên luồng này
        self._connect_lock = threading.RLock()       # reentrant lock for recursive connect() calls

    # ==================================================================
    # Kết nối & tự phục hồi
    # ==================================================================

    def _coinit(self) -> None:
        """Luong COM chuyen trach da CoInitialize san; day chi la luoi an toan
        cho truong hop co ai do goi connect() truc tiep tu mot luong khac."""
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass

    def connect(self, launch_if_needed: bool = False) -> None:
        """Bám vào phiên AutoCAD đang chạy; tùy chọn khởi động mới nếu chưa có."""
        with self._connect_lock:
            self._coinit()
            self.app = None
            self.doc = None
            errors: List[str] = []

            # 1) win32com - bám vào tiến trình AutoCAD đang chạy
            for prog_id in PROG_IDS:
                try:
                    self.app = win32com.client.GetActiveObject(prog_id)
                    break
                except Exception as exc:
                    errors.append(f"{prog_id}: {exc}")

            # 2) comtypes - một số bản build chỉ trả về qua comtypes
            if self.app is None:
                try:
                    import comtypes.client
                    for prog_id in PROG_IDS:
                        try:
                            self.app = comtypes.client.GetActiveObject(prog_id)
                            break
                        except Exception as exc:
                            errors.append(f"comtypes {prog_id}: {exc}")
                except Exception:
                    pass

            # 3) Khởi động AutoCAD mới (chỉ khi được phép - rất chậm)
            if self.app is None and launch_if_needed:
                for prog_id in PROG_IDS:
                    try:
                        self.app = win32com.client.Dispatch(prog_id)
                        break
                    except Exception as exc:
                        errors.append(f"Dispatch {prog_id}: {exc}")

            if self.app is None:
                raise AcadError(
                    "Không kết nối được tới AutoCAD. Hãy mở AutoCAD (2022 trở lên) và mở "
                    "ít nhất một bản vẽ, sau đó thử lại. Chi tiết: " + " | ".join(errors[:3])
                )

            try:
                self.app.Visible = True
            except Exception:
                pass  # một số phiên bản khóa thuộc tính này, không quan trọng

    def ensure_connected(self) -> None:
        """Bảo đảm self.app / self.doc còn sống. Gọi trước mọi thao tác COM."""
        with self._connect_lock:
            self._coinit()
            # Trong một loạt thao tác liên tiếp (batch_draw) không cần ping lại COM mỗi
            # lần - _guard vẫn tự phục hồi nếu con trỏ chết giữa chừng.
            if (self.app is not None and self.doc is not None
                    and time.time() - self._verified_at < CONNECTION_TTL):
                return
            last: Optional[BaseException] = None
            for attempt in range(MAX_ATTEMPTS):
                try:
                    if self.app is None:
                        self.connect()
                    count = self.app.Documents.Count      # ping COM, phát hiện con trỏ chết
                    if count == 0:
                        self.doc = self.app.Documents.Add()
                    else:
                        self.doc = self.app.ActiveDocument
                    # bản vẽ hiện hành có thể đã đổi giữa hai lần ping -> bỏ cache layer
                    self._layer_cache.clear()
                    self._verified_at = time.time()
                    return
                except Exception as exc:
                    last = exc
                    hr = _hresult(exc)
                    if hr in _BUSY_HRESULTS:
                        time.sleep(RETRY_DELAY * (attempt + 1))
                        continue
                    # con trỏ chết hoặc lỗi lạ -> dựng lại kết nối từ đầu
                    self._reset_connection()
                if attempt < MAX_ATTEMPTS - 1:
                    time.sleep(RETRY_DELAY)
                    continue
        raise AcadError(_explain(last) if last else "Không thể kết nối tới AutoCAD.")

    def _reset_connection(self) -> None:
        """Vứt bỏ mọi con trỏ COM đang giữ để lần gọi sau kết nối lại từ đầu."""
        self.app = None
        self.doc = None
        self._verified_at = 0.0
        self._layer_cache.clear()

    @staticmethod
    def _guard(fn):
        """Bọc một phương thức public: ensure_connected + retry + dịch lỗi."""
        def body(self: "AutoCADClient", *args, **kwargs):
            last: Optional[BaseException] = None
            revived = 0
            for attempt in range(MAX_ATTEMPTS):
                try:
                    self.ensure_connected()
                    return fn(self, *args, **kwargs)
                except AcadError:
                    raise                       # đã là thông điệp thân thiện
                except AttributeError as exc:
                    # Xem chú thích ở _reraise_if_transient: AttributeError từ một đối
                    # tượng COM luôn là lỗi tạm thời, không phải "thuộc tính không có".
                    last = exc
                    revived += 1
                    if revived <= 3:
                        if "<unknown>" in str(exc):
                            self._reset_connection()
                        time.sleep(RETRY_DELAY * revived)
                        continue
                    raise AcadError(
                        f"Không truy cập được đối tượng AutoCAD ({exc}). AutoCAD có thể "
                        "đang bận hoặc bản vẽ đã bị đóng - hãy kiểm tra AutoCAD rồi thử lại."
                    ) from exc
                except pythoncom.com_error as exc:
                    last = exc
                    hr = _hresult(exc)
                    if hr in _BUSY_HRESULTS:
                        time.sleep(RETRY_DELAY * (attempt + 1))
                        continue
                    if hr in _DEAD_HRESULTS:
                        self._reset_connection()
                        time.sleep(RETRY_DELAY)
                        continue
                    raise AcadError(_explain(exc)) from exc
                except (ValueError, TypeError, FileNotFoundError, OSError) as exc:
                    raise AcadError(str(exc)) from exc
            raise AcadError(_explain(last) if last else "Thao tác thất bại sau nhiều lần thử.")

        @functools.wraps(fn)
        def wrapper(self: "AutoCADClient", *args, **kwargs):
            return self._worker.call(body, self, *args, **kwargs)

        return wrapper

    # ==================================================================
    # Helper chuyển đổi kiểu
    # ==================================================================

    @staticmethod
    def point3d(x: float, y: float, z: float = 0.0):
        return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(x), float(y), float(z)])

    @staticmethod
    def doubles(values: Sequence[float]):
        return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(v) for v in values])

    @staticmethod
    def objects(items: Sequence[Any]):
        return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, list(items))

    @staticmethod
    def _num(value: Any, name: str) -> float:
        """Ép về float, báo lỗi rõ ràng nếu không hợp lệ."""
        try:
            f = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"Tham số '{name}' phải là số, nhận được: {value!r}")
        if math.isnan(f) or math.isinf(f):
            raise ValueError(f"Tham số '{name}' không hợp lệ (NaN/Infinity).")
        return f

    def _pt(self, x, y, z=0.0, prefix: str = "point"):
        return self.point3d(self._num(x, f"{prefix}_x"),
                            self._num(y, f"{prefix}_y"),
                            self._num(z, f"{prefix}_z"))

    def _with_retry(self, fn, *args, **kwargs):
        """Chay MOT loi goi COM don le, tu thu lai khi AutoCAD bao ban.

        Cac vong lap xu ly tung doi tuong (xoa, doi cho, doi thuoc tinh) khong di qua
        _guard, nen neu khong co lop nay thi mot nhip AutoCAD ban se lam hong toan bo
        phan con lai cua lo. Boc quanh TUNG loi goi - khong phai ca than vong lap -
        de lan thu lai khong tao ra doi tuong trung lap.
        """
        last: Optional[BaseException] = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last = exc
                hr = _hresult(exc)
                if hr in _BUSY_HRESULTS or isinstance(exc, AttributeError):
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                raise
        raise last if last else AcadError("Thao tac COM that bai sau nhieu lan thu.")

    @staticmethod
    def _probe(getter, default=None):
        """Doc mot thuoc tinh COM kieu "co thi tot".

        Loi TAM THOI van duoc nem len de _guard con thu lai duoc; chi thuoc tinh
        that su khong ton tai moi tra ve default. Neu nuot tat ca, tool se bao
        thanh cong voi du lieu rong - kieu that bai am tham te nhat.
        """
        try:
            return getter()
        except Exception as exc:
            _reraise_if_transient(exc)
            return default

    @staticmethod
    def _coords(com_point) -> List[float]:
        try:
            return [round(float(v), 8) for v in com_point]
        except Exception:
            return []

    @staticmethod
    def _flat(values: Sequence[float], stride: int, name: str) -> List[float]:
        """Kiểm tra một mảng tọa độ phẳng có đúng bội số stride và đủ điểm."""
        if values is None:
            raise ValueError(f"Thiếu tham số '{name}'.")
        try:
            nums = [float(v) for v in values]
        except (TypeError, ValueError):
            raise ValueError(f"'{name}' phải là mảng số, ví dụ [0,0, 100,0, 100,50].")
        if len(nums) < stride * 2:
            raise ValueError(
                f"'{name}' cần ít nhất 2 điểm ({stride * 2} số), hiện có {len(nums)} số."
            )
        if len(nums) % stride != 0:
            raise ValueError(
                f"'{name}' phải có số phần tử chia hết cho {stride} "
                f"({'x,y' if stride == 2 else 'x,y,z'} mỗi điểm), hiện có {len(nums)} số."
            )
        return nums

    # ------------------------------------------------------------------
    # Layer / thuộc tính đối tượng
    # ------------------------------------------------------------------

    INVALID_LAYER_CHARS = '<>/\\":;?*|,=`'

    def ensure_layer(self, name: str):
        """Trả về đối tượng Layer, tạo mới nếu chưa tồn tại."""
        name = str(name).strip()
        if not name:
            raise ValueError("Tên layer không được để trống.")
        if len(name) > 255:
            raise ValueError("Tên layer vượt quá 255 ký tự.")
        bad = sorted({c for c in name if c in self.INVALID_LAYER_CHARS})
        if bad:
            raise ValueError(
                f"Tên layer '{name}' chứa ký tự AutoCAD không cho phép: {''.join(bad)}"
            )
        key = name.lower()
        cached = self._layer_cache.get(key)
        if cached is not None:
            try:
                _ = cached.Name              # con trỏ còn sống thì dùng lại luôn
                return cached
            except Exception:
                self._layer_cache.pop(key, None)
        try:
            layer = self.doc.Layers.Item(name)
        except Exception as exc:
            _reraise_if_transient(exc)
            layer = self.doc.Layers.Add(name)
        self._layer_cache[key] = layer
        return layer

    def ensure_linetype(self, name: str) -> str:
        """Nạp linetype từ acadiso.lin nếu bản vẽ chưa có."""
        name = str(name).strip()
        try:
            self.doc.Linetypes.Item(name)
            return name
        except Exception as exc:
            _reraise_if_transient(exc)
        for lin_file in ("acadiso.lin", "acad.lin"):
            try:
                self.doc.Linetypes.Load(name, lin_file)
                return name
            except Exception:
                continue
        raise ValueError(f"Không tìm thấy linetype '{name}' trong acadiso.lin / acad.lin")

    def _apply_props(self, entity, layer: Optional[str] = None, color: Optional[int] = None,
                     linetype: Optional[str] = None,
                     lineweight: Optional[int] = None) -> List[str]:
        """Gán layer/màu/linetype. Không bao giờ ném lỗi - chỉ trả về cảnh báo.

        Nhờ vậy đối tượng đã tạo luôn được giữ lại và việc retry toàn hàm là an toàn.
        """
        warnings: List[str] = []
        if layer:
            try:
                self._with_retry(setattr, entity, "Layer", self.ensure_layer(layer).Name)
            except Exception as exc:
                warnings.append(f"Không gán được layer '{layer}': {_explain(exc)}")
        if color is not None:
            try:
                ci = int(color)
                if not 0 <= ci <= 256:
                    raise ValueError("color_index phải nằm trong 0..256")
                self._with_retry(setattr, entity, "Color", ci)
            except Exception as exc:
                warnings.append(f"Không gán được màu {color}: {exc}")
        if linetype:
            try:
                self._with_retry(setattr, entity, "Linetype", self.ensure_linetype(linetype))
            except Exception as exc:
                warnings.append(f"Không gán được linetype '{linetype}': {exc}")
        if lineweight is not None:
            try:
                self._with_retry(setattr, entity, "Lineweight", int(lineweight))
            except Exception as exc:
                warnings.append(f"Không gán được lineweight {lineweight}: {exc}")
        return warnings

    def _result(self, entity, kind: str, warnings: Optional[List[str]] = None,
                **extra) -> Dict[str, Any]:
        out: Dict[str, Any] = {"type": kind}
        try:
            out["handle"] = entity.Handle
        except Exception:
            out["handle"] = ""
        try:
            out["layer"] = entity.Layer
        except Exception:
            out["layer"] = ""
        out.update(extra)
        if warnings:
            out["warnings"] = warnings
        return out

    def _by_handle(self, handle: Any):
        """Lấy đối tượng theo Handle, thông điệp lỗi rõ ràng nếu không thấy."""
        raw = str(handle).strip()
        if not raw:
            raise ValueError("Thiếu 'handle' của đối tượng.")
        candidates = [raw, raw.upper(), raw.upper().lstrip("0") or "0", raw.lower()]
        seen = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                obj = self.doc.HandleToObject(candidate)
                if obj is not None:
                    return obj
            except Exception as exc:
                _reraise_if_transient(exc)
                continue
        # Handle chi duy nhat TRONG MOT ban ve. Server bam theo ban ve hien hanh, nen
        # nguoi dung chuyen tab giua hai lenh la handle cu tro thanh vo nghia - neu
        # thong diep khong noi ro da tim o dau thi loi nay rat de bi doc nham thanh
        # "doi tuong da bi xoa".
        raise ValueError(
            f"Không tìm thấy đối tượng có handle '{handle}' trong bản vẽ "
            f"'{self._doc_name()}'. Nếu bạn vừa chuyển sang bản vẽ khác, "
            f"handle của bản vẽ cũ không còn dùng được."
        )

    def _doc_name(self) -> str:
        """Tên bản vẽ hiện hành, dùng trong thông điệp lỗi - không bao giờ ném."""
        try:
            return str(self.doc.Name)
        except Exception:
            return "hiện hành"

    def _space(self, space: str = "model"):
        """Trả về ModelSpace hoặc PaperSpace theo tên."""
        s = (space or "model").strip().lower()
        if s in ("paper", "paperspace", "layout"):
            return self.doc.PaperSpace
        if s in ("model", "modelspace", ""):
            return self.doc.ModelSpace
        raise ValueError("Tham số 'space' chỉ nhận 'model' hoặc 'paper'.")

    def _iter_space(self, space_obj, max_scan: int = MAX_SCAN):
        """Duyệt an toàn các đối tượng trong một không gian, bỏ qua phần tử lỗi."""
        try:
            total = int(space_obj.Count)
        except Exception as exc:
            raise AcadError(_explain(exc))
        limit = min(total, max_scan)
        for i in range(limit):
            try:
                yield i, space_obj.Item(i)
            except Exception:
                continue

    # ==================================================================
    # Trạng thái & tài liệu
    # ==================================================================

    @_guard
    def get_status(self) -> Dict[str, Any]:
        """Thông tin phiên AutoCAD đang kết nối."""
        info: Dict[str, Any] = {"connected": True}
        for key, getter in (
            ("application", lambda: self.app.Name),
            ("version", lambda: self.app.Version),
            ("visible", lambda: bool(self.app.Visible)),
            ("documents_open", lambda: int(self.app.Documents.Count)),
            ("active_document", lambda: self.doc.Name),
        ):
            info[key] = self._probe(getter)
        info["command_active"] = self._probe(
            lambda: int(self.doc.GetVariable("CMDACTIVE")) != 0)
        return info

    @_guard
    def get_document_info(self) -> Dict[str, Any]:
        """Thông tin chi tiết bản vẽ hiện hành."""
        safe = self._probe

        return {
            "name": safe(lambda: self.doc.Name, "Unknown"),
            "path": safe(lambda: self.doc.Path, ""),
            "full_name": safe(lambda: self.doc.FullName, ""),
            "saved": safe(lambda: bool(self.doc.Saved), True),
            "read_only": safe(lambda: bool(self.doc.ReadOnly), False),
            "total_documents_open": safe(lambda: int(self.app.Documents.Count), 0),
            "model_space_entities_count": safe(lambda: int(self.doc.ModelSpace.Count), 0),
            "paper_space_entities_count": safe(lambda: int(self.doc.PaperSpace.Count), 0),
            "layers_count": safe(lambda: int(self.doc.Layers.Count), 0),
            "active_layer": safe(lambda: self.doc.ActiveLayer.Name, ""),
            "units_insunits": safe(lambda: int(self.doc.GetVariable("INSUNITS")), None),
        }

    @_guard
    def list_open_documents(self) -> List[Dict[str, Any]]:
        """Danh sách tất cả bản vẽ đang mở trong phiên AutoCAD."""
        docs: List[Dict[str, Any]] = []
        active_name = ""
        try:
            active_name = self.doc.Name
        except Exception:
            pass
        for i in range(int(self.app.Documents.Count)):
            try:
                d = self.app.Documents.Item(i)
            except Exception:
                continue
            entry = {"index": i}
            for key, getter in (
                ("name", lambda d=d: d.Name),
                ("full_path", lambda d=d: d.FullName),
                ("saved", lambda d=d: bool(d.Saved)),
                ("read_only", lambda d=d: bool(d.ReadOnly)),
            ):
                entry[key] = self._probe(getter)
            entry["is_active"] = (entry.get("name") == active_name)
            docs.append(entry)
        return docs

    @_guard
    def activate_document(self, name_or_index: Any) -> str:
        """Chuyển bản vẽ hiện hành sang bản vẽ khác đang mở (theo tên hoặc chỉ số)."""
        target = None
        if isinstance(name_or_index, int) or str(name_or_index).strip().isdigit():
            idx = int(name_or_index)
            if not 0 <= idx < int(self.app.Documents.Count):
                raise ValueError(
                    f"Chỉ số bản vẽ {idx} nằm ngoài phạm vi 0..{int(self.app.Documents.Count) - 1}."
                )
            target = self.app.Documents.Item(idx)
        else:
            wanted = str(name_or_index).strip().lower()
            names = []
            for i in range(int(self.app.Documents.Count)):
                d = self.app.Documents.Item(i)
                names.append(d.Name)
                if d.Name.lower() == wanted or os.path.basename(str(d.Name)).lower() == wanted:
                    target = d
                    break
            if target is None:
                raise ValueError(
                    f"Không có bản vẽ nào tên '{name_or_index}'. Đang mở: {', '.join(names)}"
                )
        target.Activate()
        self.doc = self.app.ActiveDocument
        self._layer_cache.clear()
        return f"Đã chuyển sang bản vẽ: {self.doc.Name}"

    @_guard
    def new_document(self, template: Optional[str] = None) -> str:
        """Tạo bản vẽ mới, tùy chọn từ file template .dwt."""
        if template:
            if not os.path.exists(template):
                raise FileNotFoundError(f"Không tìm thấy template: {template}")
            doc = self.app.Documents.Add(os.path.abspath(template))
        else:
            doc = self.app.Documents.Add()
        self.doc = doc
        self._layer_cache.clear()
        return f"Đã tạo bản vẽ mới: {doc.Name}"

    @_guard
    def open_document(self, file_path: str) -> str:
        """Mở một file DWG/DXF."""
        if not file_path or not str(file_path).strip():
            raise ValueError("Thiếu đường dẫn file cần mở.")
        abs_path = os.path.abspath(str(file_path).strip().strip('"'))
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"File không tồn tại: {abs_path}")
        ext = os.path.splitext(abs_path)[1].lower()
        if ext not in (".dwg", ".dxf", ".dwt"):
            raise ValueError(f"AutoCAD chỉ mở được .dwg/.dxf/.dwt, nhận được '{ext}'.")
        doc = self.app.Documents.Open(abs_path)
        self.doc = doc
        self._layer_cache.clear()
        return f"Đã mở bản vẽ: {doc.FullName}"

    @_guard
    def save_document(self, file_path: Optional[str] = None) -> str:
        """Lưu bản vẽ hiện tại, hoặc Save As nếu có file_path."""
        if file_path:
            abs_path = os.path.abspath(str(file_path).strip().strip('"'))
            parent = os.path.dirname(abs_path)
            if parent and not os.path.isdir(parent):
                raise FileNotFoundError(f"Thư mục đích không tồn tại: {parent}")
            self.doc.SaveAs(abs_path)
            return f"Đã lưu bản vẽ tại: {abs_path}"
        try:
            full = self.doc.FullName
        except Exception:
            full = ""
        if not full:
            raise AcadError(
                "Bản vẽ chưa từng được lưu nên không có đường dẫn. "
                "Hãy gọi lại và truyền 'file_path' để lưu thành file mới (Save As)."
            )
        self.doc.Save()
        return f"Đã lưu bản vẽ hiện tại: {full}"

    @_guard
    def close_document(self, save_changes: bool = True,
                       file_path: Optional[str] = None) -> str:
        """Đóng bản vẽ hiện hành."""
        name = self.doc.Name
        if file_path:
            self.doc.Close(True, os.path.abspath(str(file_path)))
        else:
            self.doc.Close(bool(save_changes))
        self._reset_connection()
        return f"Đã đóng bản vẽ: {name}"

    # ==================================================================
    # Vẽ đối tượng
    # ==================================================================

    @_guard
    def add_line(self, start_pt, end_pt, layer=None, color=None,
                 linetype=None, space="model") -> Dict[str, Any]:
        sx, sy, sz = (list(start_pt) + [0.0, 0.0, 0.0])[:3]
        ex, ey, ez = (list(end_pt) + [0.0, 0.0, 0.0])[:3]
        if (self._num(sx, "start_x"), self._num(sy, "start_y"), self._num(sz, "start_z")) == \
           (self._num(ex, "end_x"), self._num(ey, "end_y"), self._num(ez, "end_z")):
            raise ValueError("Điểm đầu và điểm cuối trùng nhau - không tạo được đoạn thẳng.")
        ent = self._space(space).AddLine(self._pt(sx, sy, sz, "start"),
                                        self._pt(ex, ey, ez, "end"))
        warn = self._apply_props(ent, layer, color, linetype)
        length = math.dist((float(sx), float(sy), float(sz)),
                           (float(ex), float(ey), float(ez)))
        return self._result(ent, "Line", warn,
                            start=[float(sx), float(sy), float(sz)],
                            end=[float(ex), float(ey), float(ez)],
                            length=round(length, 8))

    @_guard
    def add_circle(self, center_pt, radius, layer=None, color=None,
                   linetype=None, space="model") -> Dict[str, Any]:
        r = self._num(radius, "radius")
        if r <= 0:
            raise ValueError(f"Bán kính phải lớn hơn 0, nhận được {r}.")
        cx, cy, cz = (list(center_pt) + [0.0, 0.0, 0.0])[:3]
        ent = self._space(space).AddCircle(self._pt(cx, cy, cz, "center"), r)
        warn = self._apply_props(ent, layer, color, linetype)
        return self._result(ent, "Circle", warn,
                            center=[float(cx), float(cy), float(cz)], radius=r,
                            area=round(math.pi * r * r, 8))

    @_guard
    def add_arc(self, center_pt, radius, start_angle_deg, end_angle_deg,
                layer=None, color=None, linetype=None, space="model") -> Dict[str, Any]:
        """Góc truyền vào tính bằng ĐỘ; hàm này là nơi duy nhất đổi sang radian."""
        r = self._num(radius, "radius")
        if r <= 0:
            raise ValueError(f"Bán kính phải lớn hơn 0, nhận được {r}.")
        a0 = self._num(start_angle_deg, "start_angle_deg")
        a1 = self._num(end_angle_deg, "end_angle_deg")
        if abs((a1 - a0) % 360.0) < 1e-9 and abs(a1 - a0) > 1e-9:
            raise ValueError("Góc đầu và góc cuối lệch đúng bội số 360° - hãy dùng draw_circle.")
        if abs(a1 - a0) < 1e-9:
            raise ValueError("Góc đầu và góc cuối trùng nhau - cung có độ dài bằng 0.")
        cx, cy, cz = (list(center_pt) + [0.0, 0.0, 0.0])[:3]
        ent = self._space(space).AddArc(self._pt(cx, cy, cz, "center"), r,
                                        math.radians(a0), math.radians(a1))
        warn = self._apply_props(ent, layer, color, linetype)
        return self._result(ent, "Arc", warn,
                            center=[float(cx), float(cy), float(cz)], radius=r,
                            start_angle_deg=a0, end_angle_deg=a1)

    @_guard
    def add_ellipse(self, center_pt, major_axis_vector, radius_ratio=0.5,
                    layer=None, color=None, linetype=None, space="model") -> Dict[str, Any]:
        ratio = self._num(radius_ratio, "radius_ratio")
        if not 0 < ratio <= 1:
            raise ValueError("radius_ratio phải nằm trong khoảng (0, 1].")
        mx, my, mz = (list(major_axis_vector) + [0.0, 0.0, 0.0])[:3]
        if abs(float(mx)) < 1e-12 and abs(float(my)) < 1e-12 and abs(float(mz)) < 1e-12:
            raise ValueError("Vector trục lớn không được bằng 0.")
        cx, cy, cz = (list(center_pt) + [0.0, 0.0, 0.0])[:3]
        ent = self._space(space).AddEllipse(self._pt(cx, cy, cz, "center"),
                                           self._pt(mx, my, mz, "major_axis"), ratio)
        warn = self._apply_props(ent, layer, color, linetype)
        return self._result(ent, "Ellipse", warn,
                            center=[float(cx), float(cy), float(cz)], radius_ratio=ratio)

    @_guard
    def add_point(self, pt, layer=None, color=None, space="model") -> Dict[str, Any]:
        x, y, z = (list(pt) + [0.0, 0.0, 0.0])[:3]
        ent = self._space(space).AddPoint(self._pt(x, y, z, "point"))
        warn = self._apply_props(ent, layer, color)
        return self._result(ent, "Point", warn, position=[float(x), float(y), float(z)])

    @_guard
    def add_polyline_2d(self, coordinates, closed=False, layer=None, color=None,
                        linetype=None, width=None, elevation=None,
                        space="model") -> Dict[str, Any]:
        nums = self._flat(coordinates, 2, "coordinates")
        ent = self._space(space).AddLightWeightPolyline(self.doubles(nums))
        try:
            ent.Closed = bool(closed)
        except Exception:
            pass
        warn = self._apply_props(ent, layer, color, linetype)
        if width is not None:
            try:
                ent.ConstantWidth = self._num(width, "width")
            except Exception as exc:
                warn.append(f"Không gán được bề rộng {width}: {exc}")
        if elevation is not None:
            try:
                ent.Elevation = self._num(elevation, "elevation")
            except Exception as exc:
                warn.append(f"Không gán được cao độ {elevation}: {exc}")
        extra: Dict[str, Any] = {"points_count": len(nums) // 2, "closed": bool(closed)}
        for key, attr in (("length", "Length"), ("area", "Area")):
            try:
                extra[key] = round(float(getattr(ent, attr)), 8)
            except Exception:
                pass
        return self._result(ent, "Polyline2D", warn, **extra)

    @_guard
    def add_polyline_3d(self, coordinates, closed=False, layer=None,
                        color=None, space="model") -> Dict[str, Any]:
        nums = self._flat(coordinates, 3, "coordinates")
        ent = self._space(space).Add3DPoly(self.doubles(nums))
        try:
            ent.Closed = bool(closed)
        except Exception:
            pass
        warn = self._apply_props(ent, layer, color)
        return self._result(ent, "Polyline3D", warn,
                            points_count=len(nums) // 3, closed=bool(closed))

    @_guard
    def add_spline(self, coordinates, start_tangent=None, end_tangent=None,
                   layer=None, color=None, space="model") -> Dict[str, Any]:
        nums = self._flat(coordinates, 3, "coordinates")
        st = list(start_tangent) if start_tangent else [0.0, 0.0, 0.0]
        et = list(end_tangent) if end_tangent else [0.0, 0.0, 0.0]
        ent = self._space(space).AddSpline(self.doubles(nums),
                                           self._pt(*(st + [0, 0, 0])[:3], prefix="start_tangent"),
                                           self._pt(*(et + [0, 0, 0])[:3], prefix="end_tangent"))
        warn = self._apply_props(ent, layer, color)
        return self._result(ent, "Spline", warn, fit_points=len(nums) // 3)

    @_guard
    def add_hatch(self, boundary_handles, pattern_name="SOLID", scale=1.0, angle_deg=0.0,
                  layer=None, color=None, associative=True) -> Dict[str, Any]:
        """Tô mặt cắt vào các biên khép kín đã có (truyền handle của chúng)."""
        if isinstance(boundary_handles, (str, bytes)):
            boundary_handles = [boundary_handles]
        handles = [h for h in (boundary_handles or []) if str(h).strip()]
        if not handles:
            raise ValueError("Cần ít nhất một handle biên khép kín để tô hatch.")
        objs = [self._by_handle(h) for h in handles]
        # 0 = acHatchPatternTypePreDefined
        hatch = self.doc.ModelSpace.AddHatch(0, str(pattern_name).upper(), bool(associative))
        # MOT loi goi AppendOuterLoop = MOT vong khep kin. Don ca N bien roi rac vao
        # cung mot mang thi AutoCAD hieu la N doan cong ghep thanh mot vong duy nhat,
        # khong khep duoc nen tra ve "Invalid input". Moi bien phai la mot vong rieng.
        for obj in objs:
            hatch.AppendOuterLoop(self.objects([obj]))
        warn = self._apply_props(hatch, layer, color)
        if str(pattern_name).upper() != "SOLID":
            try:
                hatch.PatternScale = self._num(scale, "scale")
                hatch.PatternAngle = math.radians(self._num(angle_deg, "angle_deg"))
            except Exception as exc:
                warn.append(f"Không gán được tỉ lệ/góc mẫu hatch: {exc}")
        hatch.Evaluate()
        extra: Dict[str, Any] = {"pattern": str(pattern_name).upper(),
                                 "boundaries": len(objs)}
        try:
            extra["area"] = round(float(hatch.Area), 8)
        except Exception:
            pass
        return self._result(hatch, "Hatch", warn, **extra)

    @_guard
    def insert_block(self, insertion_pt, block_name, x_scale=1.0, y_scale=1.0,
                     z_scale=1.0, rotation_deg=0.0, layer=None,
                     space="model") -> Dict[str, Any]:
        """Chèn block đã định nghĩa trong bản vẽ, hoặc chèn từ một file .dwg."""
        name = str(block_name).strip().strip('"')
        if not name:
            raise ValueError("Thiếu tên block hoặc đường dẫn file .dwg.")
        looks_like_path = name.lower().endswith(".dwg") or os.path.sep in name or "/" in name
        if looks_like_path:
            abs_path = os.path.abspath(name)
            if not os.path.exists(abs_path):
                raise FileNotFoundError(f"Không tìm thấy file block: {abs_path}")
            name = abs_path
        else:
            try:
                self.doc.Blocks.Item(name)
            except Exception as exc:
                _reraise_if_transient(exc)
                available = []
                try:
                    for i in range(min(int(self.doc.Blocks.Count), 40)):
                        bn = self.doc.Blocks.Item(i).Name
                        if not bn.startswith("*"):
                            available.append(bn)
                except Exception:
                    pass
                raise ValueError(
                    f"Bản vẽ không có block tên '{name}'. "
                    f"Các block hiện có: {', '.join(available) or '(không có)'}"
                )
        x, y, z = (list(insertion_pt) + [0.0, 0.0, 0.0])[:3]
        ent = self._space(space).InsertBlock(
            self._pt(x, y, z, "insertion"), name,
            self._num(x_scale, "x_scale"), self._num(y_scale, "y_scale"),
            self._num(z_scale, "z_scale"), math.radians(self._num(rotation_deg, "rotation_deg")))
        warn = self._apply_props(ent, layer, None)
        return self._result(ent, "BlockReference", warn, block_name=str(block_name),
                            insertion=[float(x), float(y), float(z)])

    # ------------------------------------------------------------------
    # Chữ & kích thước
    # ------------------------------------------------------------------

    @_guard
    def add_text(self, text, insertion_pt, height=2.5, rotation_deg=0.0,
                 layer=None, color=None, style=None, alignment=None,
                 space="model") -> Dict[str, Any]:
        content = "" if text is None else str(text)
        if not content:
            raise ValueError("Nội dung chữ không được để trống.")
        h = self._num(height, "height")
        if h <= 0:
            raise ValueError(f"Chiều cao chữ phải lớn hơn 0, nhận được {h}.")
        x, y, z = (list(insertion_pt) + [0.0, 0.0, 0.0])[:3]
        ent = self._space(space).AddText(content, self._pt(x, y, z, "insertion"), h)
        warn = self._apply_props(ent, layer, color)
        rot = self._num(rotation_deg, "rotation_deg")
        if rot:
            try:
                ent.Rotation = math.radians(rot)
            except Exception as exc:
                warn.append(f"Không xoay được chữ: {exc}")
        if style:
            try:
                ent.StyleName = str(style)
            except Exception as exc:
                warn.append(f"Không gán được text style '{style}': {exc}")
        if alignment is not None:
            try:
                ent.Alignment = int(alignment)
                ent.TextAlignmentPoint = self._pt(x, y, z, "insertion")
            except Exception as exc:
                warn.append(f"Không gán được căn lề {alignment}: {exc}")
        return self._result(ent, "Text", warn, text=content,
                            insertion=[float(x), float(y), float(z)], height=h)

    @_guard
    def add_mtext(self, text, insertion_pt, width=50.0, height=2.5,
                  layer=None, color=None, style=None, space="model") -> Dict[str, Any]:
        content = "" if text is None else str(text)
        if not content:
            raise ValueError("Nội dung MText không được để trống.")
        w = self._num(width, "width")
        if w < 0:
            raise ValueError("Bề rộng hộp chữ không được âm (0 = tự động).")
        x, y, z = (list(insertion_pt) + [0.0, 0.0, 0.0])[:3]
        ent = self._space(space).AddMText(self._pt(x, y, z, "insertion"), w, content)
        warn = self._apply_props(ent, layer, color)
        if height is not None:
            h = self._num(height, "height")
            if h <= 0:
                raise ValueError(f"Chiều cao chữ phải lớn hơn 0, nhận được {h}.")
            try:
                ent.Height = h
            except Exception as exc:
                warn.append(f"Không gán được chiều cao chữ: {exc}")
        if style:
            try:
                ent.StyleName = str(style)
            except Exception as exc:
                warn.append(f"Không gán được text style '{style}': {exc}")
        return self._result(ent, "MText", warn, text=content,
                            insertion=[float(x), float(y), float(z)], width=w)

    # Bien he thong DIM* -> thuoc tinh tuong ung tren doi tuong Dimension.
    # Ten thuoc tinh ActiveX khong trung ten bien, nen phai anh xa tay.
    _DIM_VAR_MAP = (
        ("DIMSCALE", "ScaleFactor"),
        ("DIMTXT", "TextHeight"),
        ("DIMASZ", "ArrowheadSize"),
        ("DIMEXE", "ExtensionLineExtend"),
        ("DIMEXO", "ExtensionLineOffset"),
        ("DIMGAP", "TextGap"),
        ("DIMDEC", "PrimaryUnitsPrecision"),
    )

    def _sync_dim_vars(self, ent) -> List[str]:
        """Ep cac bien DIM* cua ban ve xuong doi tuong kich thuoc vua tao.

        AddDim* cua ActiveX KHONG doc cac bien he thong DIM*: no lay thuoc tinh tu
        dimension style dang hien hanh. Nguoi dung goi set_system_variable('DIMSCALE', 80)
        roi ve kich thuoc thi bien doi thanh 80 that, nhung doi tuong sinh ra van giu
        ScaleFactor = 1 cua style. Voi ban ve don vi milimet dung template he inch
        (DIMTXT = 0.18), chu so cao 0,18 mm tren hinh dai vai nghin mm - nhin nhu kich
        thuoc bi mat chu, khong co thong bao loi nao.

        Dong bo o day de bien he thong tro thanh dieu khien that su, dung nhu tai lieu
        cua tool set_system_variable ngu y.
        """
        warn: List[str] = []
        for var, prop in self._DIM_VAR_MAP:
            try:
                value = self.doc.GetVariable(var)
            except Exception:
                continue                      # ban AutoCAD nay khong co bien do
            try:
                setattr(ent, prop, int(value) if prop.endswith("Precision") else float(value))
            except Exception as exc:
                warn.append(f"Không áp được {var} lên kích thước ({prop}): {exc}")
        return warn

    @_guard
    def add_dimension(self, kind, points, layer=None, color=None,
                      text_override=None, rotation_deg=0.0,
                      leader_length=None, dim_style=None) -> Dict[str, Any]:
        """Tạo kích thước. 'kind' thuộc: aligned | linear | angular | radial | diametric."""
        k = str(kind).strip().lower()
        ms = self.doc.ModelSpace

        def p(idx, name):
            if idx >= len(points):
                raise ValueError(f"Kiểu kích thước '{k}' cần điểm '{name}' (points[{idx}]).")
            xyz = (list(points[idx]) + [0.0, 0.0, 0.0])[:3]
            return self._pt(xyz[0], xyz[1], xyz[2], name)

        if k in ("aligned", "align"):
            ent = ms.AddDimAligned(p(0, "ext1"), p(1, "ext2"), p(2, "text_pos"))
        elif k in ("linear", "rotated", "horizontal", "vertical"):
            angle = self._num(rotation_deg, "rotation_deg")
            if k == "vertical":
                angle = 90.0
            elif k == "horizontal":
                angle = 0.0
            ent = ms.AddDimRotated(p(0, "ext1"), p(1, "ext2"), p(2, "dim_line"),
                                   math.radians(angle))
        elif k == "angular":
            ent = ms.AddDimAngular(p(0, "vertex"), p(1, "end1"), p(2, "end2"), p(3, "text_pos"))
        elif k == "radial":
            ll = self._num(leader_length if leader_length is not None else 5.0, "leader_length")
            ent = ms.AddDimRadial(p(0, "center"), p(1, "chord"), ll)
        elif k in ("diametric", "diameter"):
            ll = self._num(leader_length if leader_length is not None else 5.0, "leader_length")
            ent = ms.AddDimDiametric(p(0, "chord"), p(1, "far_chord"), ll)
        else:
            raise ValueError(
                "kind phải là một trong: aligned, linear, angular, radial, diametric "
                f"- nhận được '{kind}'."
            )
        warn = self._apply_props(ent, layer, color)
        warn += self._sync_dim_vars(ent)
        if text_override:
            try:
                ent.TextOverride = str(text_override)
            except Exception as exc:
                warn.append(f"Không ghi đè được text kích thước: {exc}")
        if dim_style:
            try:
                ent.StyleName = str(dim_style)
            except Exception as exc:
                warn.append(f"Không gán được dim style '{dim_style}': {exc}")
        extra = {}
        try:
            extra["measurement"] = round(float(ent.Measurement), 8)
        except Exception:
            pass
        return self._result(ent, f"Dim{k.capitalize()}", warn, **extra)

    @_guard
    def add_leader(self, coordinates, annotation_text=None, layer=None,
                   color=None, text_height=2.5) -> Dict[str, Any]:
        nums = self._flat(coordinates, 3, "coordinates")
        ms = self.doc.ModelSpace
        annotation = None
        warn: List[str] = []
        if annotation_text:
            tail = nums[-3:]
            annotation = ms.AddMText(self._pt(tail[0], tail[1], tail[2], "annotation"),
                                     0.0, str(annotation_text))
            try:
                annotation.Height = self._num(text_height, "text_height")
            except Exception as exc:
                warn.append(f"Không gán được chiều cao chú thích: {exc}")
        try:
            ent = ms.AddLeader(self.doubles(nums), annotation, 0)  # 0 = acLineWithArrow
        except Exception:
            # Chú thích được tạo TRƯỚC đường dẫn. AddLeader hỏng (toa độ thiếu chiều Z,
            # dưới hai điểm...) thì MText đã nằm trong bản vẽ và không còn ai trỏ tới nó:
            # người dùng thấy một dòng chữ trôi nổi giữa bản vẽ mà không hiểu từ đâu ra.
            if annotation is not None:
                try:
                    annotation.Delete()
                except Exception:
                    pass
            raise
        warn += self._apply_props(ent, layer, color)
        if annotation is not None:
            warn += self._apply_props(annotation, layer, color)
        return self._result(ent, "Leader", warn, vertices=len(nums) // 3,
                            annotation=str(annotation_text) if annotation_text else None)

    # ==================================================================
    # Hiệu chỉnh đối tượng
    # ==================================================================

    @_guard
    def transform_entities(self, handles, action, **kw) -> Dict[str, Any]:
        """move | copy | rotate | scale | mirror | offset | array_rect | array_polar | explode."""
        if isinstance(handles, (str, bytes)):
            handles = [handles]
        handles = [str(h) for h in (handles or []) if str(h).strip()]
        if not handles:
            raise ValueError("Cần ít nhất một 'handle' đối tượng để hiệu chỉnh.")
        act = str(action).strip().lower()
        valid = ("move", "copy", "rotate", "scale", "mirror", "offset",
                 "array_rect", "array_polar", "explode")
        if act not in valid:
            raise ValueError(
                f"action phải thuộc: {', '.join(valid)} - nhận được '{action}'."
            )
        results: List[Dict[str, Any]] = []
        failures: List[Dict[str, str]] = []

        def need_pt(name):
            val = kw.get(name)
            if val is None:
                raise ValueError(f"Thao tác '{act}' cần tham số '{name}' dạng [x, y, z].")
            xyz = (list(val) + [0.0, 0.0, 0.0])[:3]
            return self._pt(xyz[0], xyz[1], xyz[2], name)

        def need_num(name, default=None):
            val = kw.get(name, default)
            if val is None:
                raise ValueError(f"Thao tác '{act}' cần tham số số '{name}'.")
            return self._num(val, name)

        # Kiểm tra tham số MỘT LẦN trước vòng lặp: thiếu tham số là lỗi của lời gọi,
        # phải báo hỏng cả thao tác chứ không âm thầm ghi vào 'failures' từng đối tượng.
        if act == "move":
            need_pt("from_point"), need_pt("to_point")
        elif act == "copy":
            if (kw.get("from_point") is None) != (kw.get("to_point") is None):
                raise ValueError(
                    "Thao tác 'copy' cần cả 'from_point' và 'to_point', hoặc bỏ trống cả hai "
                    "để chép tại chỗ."
                )
        elif act == "rotate":
            need_pt("base_point"), need_num("rotation_deg")
        elif act == "scale":
            need_pt("base_point")
            if need_num("scale_factor") == 0:
                raise ValueError("scale_factor không được bằng 0.")
        elif act == "mirror":
            need_pt("point1"), need_pt("point2")
        elif act == "offset":
            if need_num("distance") == 0:
                raise ValueError("distance của offset không được bằng 0.")
        elif act == "array_rect":
            rows, cols, levels = (int(need_num("rows", 1)), int(need_num("columns", 1)),
                                  int(need_num("levels", 1)))
            if rows < 1 or cols < 1 or levels < 1:
                raise ValueError("rows/columns/levels phải >= 1.")
            if rows * cols * levels > 10000:
                raise ValueError("Mảng vượt quá 10000 phần tử - hãy chia nhỏ.")
            if rows == 1 and cols == 1 and levels == 1:
                raise ValueError("array_rect với 1 hàng x 1 cột x 1 tầng không tạo ra bản sao nào.")
        elif act == "array_polar":
            if int(need_num("count")) < 2:
                raise ValueError("count của array_polar phải >= 2.")
            need_pt("center_point")

        for h in handles:
            try:
                obj = self._by_handle(h)
                new_handles: List[str] = []
                if act == "move":
                    self._with_retry(obj.Move, need_pt("from_point"), need_pt("to_point"))
                elif act == "copy":
                    dup = self._with_retry(obj.Copy)
                    if kw.get("from_point") is not None and kw.get("to_point") is not None:
                        self._with_retry(dup.Move, need_pt("from_point"), need_pt("to_point"))
                    new_handles.append(dup.Handle)
                elif act == "rotate":
                    self._with_retry(obj.Rotate, need_pt("base_point"),
                                    math.radians(need_num("rotation_deg")))
                elif act == "scale":
                    self._with_retry(obj.ScaleEntity, need_pt("base_point"),
                                    need_num("scale_factor"))
                elif act == "mirror":
                    dup = self._with_retry(obj.Mirror, need_pt("point1"), need_pt("point2"))
                    new_handles.append(dup.Handle)
                    if kw.get("delete_source"):
                        self._with_retry(obj.Delete)
                elif act == "offset":
                    produced = self._with_retry(obj.Offset, need_num("distance"))
                    for item in (produced or []):
                        new_handles.append(item.Handle)
                elif act == "array_rect":
                    produced = self._with_retry(
                        obj.ArrayRectangular,
                        int(need_num("rows", 1)), int(need_num("columns", 1)),
                        int(need_num("levels", 1)),
                        need_num("row_spacing", 0.0), need_num("column_spacing", 0.0),
                        need_num("level_spacing", 0.0))
                    for item in (produced or []):
                        try:
                            new_handles.append(item.Handle)
                        except Exception:
                            pass
                elif act == "array_polar":
                    produced = self._with_retry(
                        obj.ArrayPolar,
                        int(need_num("count")),
                        math.radians(need_num("fill_angle_deg", 360.0)),
                        need_pt("center_point"))
                    for item in (produced or []):
                        try:
                            new_handles.append(item.Handle)
                        except Exception:
                            pass
                elif act == "explode":
                    produced = self._with_retry(obj.Explode)
                    for item in (produced or []):
                        try:
                            new_handles.append(item.Handle)
                        except Exception:
                            pass
                    if kw.get("delete_source", True):
                        self._with_retry(obj.Delete)
                results.append({"handle": h, "new_handles": new_handles})
            except AcadError as exc:
                failures.append({"handle": h, "error": str(exc)})
            except Exception as exc:
                failures.append({"handle": h, "error": _explain(exc)})

        return {
            "action": act,
            "succeeded": len(results),
            "failed": len(failures),
            "results": results,
            "failures": failures,
        }

    @_guard
    def set_entity_properties(self, handles, layer=None, color=None, linetype=None,
                              lineweight=None, text=None) -> Dict[str, Any]:
        """Đổi layer/màu/linetype/nội dung chữ của các đối tượng có sẵn."""
        if isinstance(handles, (str, bytes)):
            handles = [handles]
        handles = [str(h) for h in (handles or []) if str(h).strip()]
        if not handles:
            raise ValueError("Cần ít nhất một 'handle'.")
        updated, failures = [], []
        for h in handles:
            try:
                obj = self._by_handle(h)
                warn = self._apply_props(obj, layer, color, linetype, lineweight)
                if text is not None:
                    try:
                        self._with_retry(setattr, obj, "TextString", str(text))
                    except Exception as exc:
                        warn.append(f"Đối tượng này không đổi được nội dung chữ: {_explain(exc)}")
                entry = {"handle": h}
                if warn:
                    entry["warnings"] = warn
                updated.append(entry)
            except Exception as exc:
                failures.append({"handle": h, "error": _explain(exc)})
        return {"updated": len(updated), "failed": len(failures),
                "results": updated, "failures": failures}

    @_guard
    def delete_entities(self, handles=None, layer=None, entity_type=None,
                        delete_all=False, space="model") -> Dict[str, Any]:
        """Xóa theo handle, theo layer, theo loại, hoặc xóa sạch không gian vẽ."""
        targets = []
        failures: List[Dict[str, str]] = []

        if handles:
            if isinstance(handles, (str, bytes)):
                handles = [handles]
            for h in handles:
                try:
                    targets.append((str(h), self._by_handle(h)))
                except Exception as exc:
                    # Loi tam thoi (AutoCAD ban, con tro dispatch chet) phai bay len
                    # _guard de no dung lai ket noi roi chay lai ca lenh; nuot vao day
                    # thi ca lo bi bao "khong tim thay handle" trong khi doi tuong van
                    # nam nguyen trong ban ve. Vong lap nay chay TRUOC moi thao tac
                    # xoa, nen chay lai tu dau hoan toan an toan.
                    _reraise_if_transient(exc)
                    failures.append({"handle": str(h), "error": _explain(exc)})
        elif delete_all or layer or entity_type:
            space_obj = self._space(space)
            lyr = str(layer).strip().lower() if layer else None
            etype = str(entity_type).strip().lower() if entity_type else None
            for _, item in self._iter_space(space_obj):
                try:
                    if lyr and str(item.Layer).lower() != lyr:
                        continue
                    if etype and etype not in str(item.ObjectName).replace("AcDb", "").lower():
                        continue
                    targets.append((getattr(item, "Handle", ""), item))
                except Exception:
                    continue
        else:
            raise ValueError(
                "Cần chỉ rõ 'handles', hoặc 'layer', hoặc 'entity_type', "
                "hoặc đặt delete_all=True."
            )

        deleted = 0
        for h, obj in targets:
            try:
                self._with_retry(obj.Delete)
                deleted += 1
            except Exception as exc:
                failures.append({"handle": h, "error": _explain(exc)})
        return {"deleted": deleted, "failed": len(failures), "failures": failures}

    # ==================================================================
    # Truy vấn bản vẽ
    # ==================================================================

    @_guard
    def get_drawing_summary(self, space="model", max_scan=MAX_SCAN) -> Dict[str, Any]:
        space_obj = self._space(space)
        counts: Dict[str, int] = {}
        by_layer: Dict[str, int] = {}
        scanned = 0
        for _, item in self._iter_space(space_obj, max_scan):
            scanned += 1
            try:
                name = str(item.ObjectName).replace("AcDb", "")
            except Exception:
                name = "Unknown"
            counts[name] = counts.get(name, 0) + 1
            try:
                lname = str(item.Layer)
            except Exception:
                lname = "?"
            by_layer[lname] = by_layer.get(lname, 0) + 1

        total = int(space_obj.Count)
        out: Dict[str, Any] = {
            "drawing_name": self.doc.Name,
            "space": space,
            "total_entities": total,
            "entity_breakdown": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
            "entities_by_layer": dict(sorted(by_layer.items(), key=lambda kv: -kv[1])),
            "layers_count": int(self.doc.Layers.Count),
            "blocks_count": int(self.doc.Blocks.Count),
        }
        if scanned < total:
            out["note"] = (f"Chỉ thống kê {scanned}/{total} đối tượng đầu tiên (giới hạn max_scan="
                           f"{max_scan}). Mỗi đối tượng tốn vài mili giây qua COM nên bản vẽ rất lớn "
                           "sẽ lâu; tăng max_scan nếu cần thống kê đầy đủ.")
        return out

    @_guard
    def list_entities_details(self, limit=50, entity_type_filter=None, layer_filter=None,
                              space="model", count_all=False,
                              max_scan=MAX_SCAN) -> Dict[str, Any]:
        space_obj = self._space(space)
        try:
            limit = max(1, min(int(limit), 5000))
        except Exception:
            limit = 50
        etype = str(entity_type_filter).strip().lower() if entity_type_filter else None
        lyr = str(layer_filter).strip().lower() if layer_filter else None

        entities: List[Dict[str, Any]] = []
        scanned = 0
        matched = 0
        stopped_early = False
        for i, item in self._iter_space(space_obj, max_scan):
            # Mỗi đối tượng tốn vài lời gọi COM (~5ms), nên khi đã đủ 'limit' thì dừng
            # ngay thay vì quét nốt cả bản vẽ. Muốn biết tổng chính xác thì count_all=True.
            if len(entities) >= limit and not count_all:
                stopped_early = True
                break
            scanned += 1
            try:
                otype = str(item.ObjectName).replace("AcDb", "")
            except Exception:
                otype = "Unknown"
            if etype and etype not in otype.lower():
                continue
            try:
                item_layer = str(item.Layer)
            except Exception:
                item_layer = ""
            if lyr and item_layer.lower() != lyr:
                continue
            matched += 1
            if len(entities) < limit:      # count_all vẫn quét tiếp để đếm, nhưng
                                           # danh sách trả về luôn tôn trọng 'limit'
                entities.append(self._describe(item, index=i, otype=otype, layer=item_layer))

        out: Dict[str, Any] = {
            "space": space,
            "scanned": scanned,
            "returned": len(entities),
            "entities": entities,
        }
        if stopped_early:
            out["more_available"] = True
            out["note"] = ("Đã dừng ngay khi đủ 'limit' đối tượng. Muốn biết tổng số khớp "
                           "chính xác thì gọi lại với count_all=True, hoặc dùng "
                           "get_drawing_summary.")
        else:
            out["matched"] = matched
            out["more_available"] = False
        return out

    def _describe(self, item, index=None, otype=None, layer=None) -> Dict[str, Any]:
        """Mô tả một đối tượng - không bao giờ ném lỗi."""
        if otype is None:
            try:
                otype = str(item.ObjectName).replace("AcDb", "")
            except Exception:
                otype = "Unknown"
        info: Dict[str, Any] = {"type": otype}
        if index is not None:
            info["index"] = index
        for key, getter in (("handle", lambda: item.Handle),
                            ("layer", lambda: layer if layer is not None else item.Layer),
                            ("color", lambda: int(item.Color))):
            try:
                info[key] = getter()
            except Exception:
                info[key] = None
        low = otype.lower()
        probes = []
        if "line" in low and "polyline" not in low and "spline" not in low:
            probes = [("start", lambda: self._coords(item.StartPoint)),
                      ("end", lambda: self._coords(item.EndPoint)),
                      ("length", lambda: round(float(item.Length), 8))]
        elif "circle" in low:
            probes = [("center", lambda: self._coords(item.Center)),
                      ("radius", lambda: round(float(item.Radius), 8)),
                      ("area", lambda: round(float(item.Area), 8))]
        elif "arc" in low:
            probes = [("center", lambda: self._coords(item.Center)),
                      ("radius", lambda: round(float(item.Radius), 8)),
                      ("start_angle_deg", lambda: round(math.degrees(float(item.StartAngle)), 6)),
                      ("end_angle_deg", lambda: round(math.degrees(float(item.EndAngle)), 6))]
        elif "polyline" in low:
            probes = [("closed", lambda: bool(item.Closed)),
                      ("length", lambda: round(float(item.Length), 8)),
                      ("area", lambda: round(float(item.Area), 8)),
                      ("coordinates", lambda: self._coords(item.Coordinates))]
        elif "text" in low:
            probes = [("text", lambda: str(item.TextString)),
                      ("height", lambda: round(float(item.Height), 8)),
                      ("insertion", lambda: self._coords(item.InsertionPoint))]
        elif "blockreference" in low:
            probes = [("block_name", lambda: str(item.Name)),
                      ("insertion", lambda: self._coords(item.InsertionPoint)),
                      ("rotation_deg", lambda: round(math.degrees(float(item.Rotation)), 6))]
        elif "hatch" in low:
            probes = [("pattern", lambda: str(item.PatternName)),
                      ("area", lambda: round(float(item.Area), 8))]
        elif "dimension" in low:
            probes = [("measurement", lambda: round(float(item.Measurement), 8)),
                      ("text", lambda: str(item.TextOverride))]
        for key, getter in probes:
            try:
                value = getter()
                if key == "coordinates" and len(value) > 60:
                    info[key] = value[:60]
                    info["coordinates_truncated"] = True
                else:
                    info[key] = value
            except Exception:
                pass
        return info

    @_guard
    def get_entity(self, handle) -> Dict[str, Any]:
        obj = self._by_handle(handle)
        info = self._describe(obj)
        try:
            mn, mx = obj.GetBoundingBox()
            info["bounding_box"] = {"min": self._coords(mn), "max": self._coords(mx)}
        except Exception:
            pass
        return info

    @_guard
    def get_selection(self) -> Dict[str, Any]:
        """Đọc các đối tượng người dùng đang chọn sẵn trên màn hình AutoCAD."""
        sel = self.doc.PickfirstSelectionSet
        items = []
        count = int(sel.Count)
        for i in range(min(count, 500)):
            try:
                items.append(self._describe(sel.Item(i), index=i))
            except Exception:
                continue
        return {"selected_count": count, "returned": len(items), "entities": items}

    @_guard
    def get_drawing_extents(self) -> Dict[str, Any]:
        try:
            self.doc.Regen(1)   # acAllViewports - cập nhật EXTMIN/EXTMAX
        except Exception as exc:
            _reraise_if_transient(exc)
        out: Dict[str, Any] = {}
        for key, var in (("min", "EXTMIN"), ("max", "EXTMAX")):
            try:
                out[key] = self._coords(self.doc.GetVariable(var))
            except Exception as exc:
                _reraise_if_transient(exc)
                raise AcadError(f"Không đọc được biến {var} của bản vẽ: {_explain(exc)}")
        if not out["min"] or not out["max"]:
            raise AcadError(
                "AutoCAD trả về giới hạn bản vẽ rỗng. Hãy gọi regen_drawing rồi thử lại."
            )
        out["width"] = round(out["max"][0] - out["min"][0], 8)
        out["height"] = round(out["max"][1] - out["min"][1], 8)
        return out

    @_guard
    def find_text(self, keyword, replace_with=None, case_sensitive=False,
                  space="model") -> Dict[str, Any]:
        """Tìm (và tùy chọn thay thế) chuỗi trong mọi Text/MText/Dimension."""
        needle = str(keyword)
        if not needle:
            raise ValueError("Từ khóa tìm kiếm không được để trống.")
        probe = needle if case_sensitive else needle.lower()
        matches, replaced = [], 0
        for i, item in self._iter_space(self._space(space)):
            try:
                current = str(item.TextString)
            except Exception:
                continue
            hay = current if case_sensitive else current.lower()
            if probe not in hay:
                continue
            entry = {"index": i, "text": current}
            try:
                entry["handle"] = item.Handle
                entry["layer"] = item.Layer
            except Exception:
                pass
            if replace_with is not None:
                try:
                    if case_sensitive:
                        new_text = current.replace(needle, str(replace_with))
                    else:
                        # thay thế không phân biệt hoa thường, giữ nguyên phần còn lại
                        out, low, start = [], current.lower(), 0
                        while True:
                            pos = low.find(probe, start)
                            if pos < 0:
                                out.append(current[start:])
                                break
                            out.append(current[start:pos])
                            out.append(str(replace_with))
                            start = pos + len(needle)
                        new_text = "".join(out)
                    self._with_retry(setattr, item, "TextString", new_text)
                    entry["new_text"] = new_text
                    replaced += 1
                except Exception as exc:
                    entry["error"] = _explain(exc)
            matches.append(entry)
            if len(matches) >= 500:
                break
        return {"keyword": needle, "found": len(matches),
                "replaced": replaced, "matches": matches}

    # ==================================================================
    # Layer & bảng ký hiệu
    # ==================================================================

    @_guard
    def list_layers(self) -> List[Dict[str, Any]]:
        layers: List[Dict[str, Any]] = []
        active = ""
        try:
            active = self.doc.ActiveLayer.Name
        except Exception:
            pass
        for i in range(int(self.doc.Layers.Count)):
            try:
                lyr = self.doc.Layers.Item(i)
            except Exception:
                continue
            entry: Dict[str, Any] = {"index": i}
            for key, getter in (
                ("name", lambda ly=lyr: str(ly.Name)),
                ("color", lambda ly=lyr: int(ly.Color)),
                ("frozen", lambda ly=lyr: bool(ly.Freeze)),
                ("locked", lambda ly=lyr: bool(ly.Lock)),
                ("on", lambda ly=lyr: bool(ly.LayerOn)),
                ("plottable", lambda ly=lyr: bool(ly.Plottable)),
                ("linetype", lambda ly=lyr: str(ly.Linetype)),
            ):
                entry[key] = self._probe(getter)
            entry["is_active"] = (entry.get("name") == active)
            layers.append(entry)
        return layers

    @_guard
    def create_or_set_layer(self, name, color=None, set_active=True, linetype=None,
                            frozen=None, locked=None, on=None,
                            plottable=None) -> Dict[str, Any]:
        lyr = self.ensure_layer(name)
        warnings: List[str] = []
        if color is not None:
            try:
                ci = int(color)
                if not 1 <= ci <= 255:
                    raise ValueError("color_index của layer phải nằm trong 1..255")
                lyr.Color = ci
            except Exception as exc:
                warnings.append(f"Không đổi được màu layer: {exc}")
        if linetype:
            try:
                lyr.Linetype = self.ensure_linetype(linetype)
            except Exception as exc:
                warnings.append(f"Không gán được linetype: {exc}")
        for value, attr, label in ((frozen, "Freeze", "đóng băng"),
                                   (locked, "Lock", "khóa"),
                                   (on, "LayerOn", "bật/tắt"),
                                   (plottable, "Plottable", "in")):
            if value is None:
                continue
            try:
                setattr(lyr, attr, bool(value))
            except Exception as exc:
                warnings.append(f"Không đổi được trạng thái {label}: {_explain(exc)}")
        if set_active:
            try:
                if getattr(lyr, "Freeze", False):
                    lyr.Freeze = False
                    warnings.append("Đã bỏ đóng băng vì layer đang được đặt làm hiện hành.")
                self.doc.ActiveLayer = lyr
            except Exception as exc:
                warnings.append(f"Không đặt được làm layer hiện hành: {_explain(exc)}")
        out = {"name": str(lyr.Name), "active": bool(set_active)}
        try:
            out["color"] = int(lyr.Color)
        except Exception:
            pass
        if warnings:
            out["warnings"] = warnings
        return out

    @_guard
    def delete_layer(self, name, move_entities_to=None) -> str:
        target = str(name).strip()
        if target.lower() == "0":
            raise ValueError("Không thể xóa layer '0' - đây là layer hệ thống của AutoCAD.")
        try:
            lyr = self.doc.Layers.Item(target)
        except Exception as exc:
            _reraise_if_transient(exc)
            raise ValueError(f"Bản vẽ không có layer tên '{target}'.")
        try:
            if self.doc.ActiveLayer.Name == lyr.Name:
                self.doc.ActiveLayer = self.doc.Layers.Item("0")
        except Exception:
            pass
        moved = 0
        if move_entities_to:
            dest = self.ensure_layer(move_entities_to).Name
            for _, item in self._iter_space(self.doc.ModelSpace):
                try:
                    if str(item.Layer) == lyr.Name:
                        item.Layer = dest
                        moved += 1
                except Exception:
                    continue
        try:
            lyr.Delete()
        except Exception as exc:
            raise AcadError(
                f"Không xóa được layer '{target}': {_explain(exc)}. "
                "Layer vẫn còn đối tượng tham chiếu - hãy truyền 'move_entities_to' "
                "hoặc xóa các đối tượng trên layer trước."
            )
        suffix = f" (đã chuyển {moved} đối tượng sang '{move_entities_to}')" if moved else ""
        return f"Đã xóa layer '{target}'{suffix}."

    @_guard
    def list_blocks(self) -> List[Dict[str, Any]]:
        blocks = []
        for i in range(int(self.doc.Blocks.Count)):
            try:
                blk = self.doc.Blocks.Item(i)
                name = str(blk.Name)
            except Exception:
                continue
            if name.startswith("*"):
                continue        # bỏ qua ModelSpace/PaperSpace/anonymous
            entry = {"name": name}
            for key, getter in (("entities", lambda b=blk: int(b.Count)),
                                ("is_xref", lambda b=blk: bool(b.IsXRef)),
                                ("is_layout", lambda b=blk: bool(b.IsLayout))):
                entry[key] = self._probe(getter)
            blocks.append(entry)
        return blocks

    @_guard
    def list_styles(self) -> Dict[str, Any]:
        """Liệt kê text style, dim style, linetype, layout của bản vẽ."""
        def names(collection):
            out = []
            try:
                for i in range(int(collection.Count)):
                    try:
                        out.append(str(collection.Item(i).Name))
                    except Exception:
                        continue
            except Exception:
                pass
            return out

        return {
            "text_styles": names(self.doc.TextStyles),
            "dim_styles": names(self.doc.DimStyles),
            "linetypes": names(self.doc.Linetypes),
            "layouts": names(self.doc.Layouts),
        }

    # ==================================================================
    # Khung nhìn, biến hệ thống, lệnh AutoCAD
    # ==================================================================

    @_guard
    def zoom(self, mode="extents", point1=None, point2=None, magnification=None) -> str:
        m = str(mode or "extents").strip().lower()
        if m in ("extents", "extent", "e"):
            self.app.ZoomExtents()
            return "Đã Zoom Extents."
        if m in ("all", "a"):
            self.app.ZoomAll()
            return "Đã Zoom All."
        if m in ("window", "w"):
            if not point1 or not point2:
                raise ValueError("Zoom Window cần cả 'point1' và 'point2' dạng [x, y].")
            p1 = (list(point1) + [0.0, 0.0, 0.0])[:3]
            p2 = (list(point2) + [0.0, 0.0, 0.0])[:3]
            self.app.ZoomWindow(self._pt(*p1, prefix="point1"), self._pt(*p2, prefix="point2"))
            return "Đã Zoom Window."
        if m in ("center", "c"):
            if not point1:
                raise ValueError("Zoom Center cần 'point1' là tâm khung nhìn.")
            p1 = (list(point1) + [0.0, 0.0, 0.0])[:3]
            mag = self._num(magnification if magnification is not None else 1.0, "magnification")
            self.app.ZoomCenter(self._pt(*p1, prefix="point1"), mag)
            return "Đã Zoom Center."
        if m in ("previous", "p"):
            self.app.ZoomPrevious()
            return "Đã Zoom Previous."
        raise ValueError(
            "mode chỉ nhận: extents, all, window, center, previous "
            f"- nhận được '{mode}'."
        )

    def zoom_extents(self) -> str:
        """Giữ nguyên tên cũ cho các script sẵn có (app.py, draw_square.py)."""
        return self.zoom("extents")

    def zoom_all(self) -> str:
        """Giữ nguyên tên cũ cho các script sẵn có."""
        return self.zoom("all")

    @_guard
    def regen(self) -> str:
        self.doc.Regen(1)   # acAllViewports
        return "Đã Regen toàn bộ khung nhìn."

    @_guard
    def get_variable(self, name) -> Dict[str, Any]:
        var = str(name).strip().upper()
        if not var:
            raise ValueError("Thiếu tên biến hệ thống.")
        try:
            value = self.doc.GetVariable(var)
        except Exception as exc:
            _reraise_if_transient(exc)
            raise ValueError(f"AutoCAD không có biến hệ thống tên '{var}'.")
        if not isinstance(value, (str, int, float, bool)) and value is not None:
            value = self._coords(value) or str(value)
        return {"name": var, "value": value}

    @_guard
    def set_variable(self, name, value) -> Dict[str, Any]:
        var = str(name).strip().upper()
        if not var:
            raise ValueError("Thiếu tên biến hệ thống.")
        try:
            current = self.doc.GetVariable(var)
        except Exception as exc:
            _reraise_if_transient(exc)
            raise ValueError(f"AutoCAD không có biến hệ thống tên '{var}'.")
        if isinstance(current, (int,)) and not isinstance(current, bool):
            new_value = int(value)
        elif isinstance(current, float):
            new_value = float(value)
        elif isinstance(current, str):
            new_value = str(value)
        else:
            xyz = (list(value) + [0.0, 0.0, 0.0])[:3] if not isinstance(value, str) else None
            if xyz is None:
                raise ValueError(f"Biến '{var}' cần giá trị dạng tọa độ [x, y, z].")
            new_value = self.point3d(*xyz)
        self.doc.SetVariable(var, new_value)
        return {"name": var, "old_value": current, "new_value": value}

    def _assert_idle(self) -> None:
        """Chặn SendCommand khi AutoCAD còn đang trong một lệnh khác."""
        try:
            if int(self.doc.GetVariable("CMDACTIVE")) != 0:
                raise AcadError(
                    "AutoCAD đang dở một lệnh khác nên không nhận lệnh mới. "
                    "Hãy nhấn ESC trong AutoCAD rồi thử lại."
                )
        except AcadError:
            raise
        except Exception:
            pass    # không đọc được CMDACTIVE thì cứ thử gửi

    @_guard
    def send_command(self, command_str) -> str:
        cmd = str(command_str)
        if not cmd.strip():
            raise ValueError("Chuỗi lệnh rỗng.")
        self._assert_idle()
        if not cmd.endswith(("\n", " ")):
            cmd += "\n"
        self.doc.SendCommand(cmd)
        return f"Đã gửi lệnh tới AutoCAD: {cmd.strip()}"

    @_guard
    def run_lisp(self, expression, timeout=20.0) -> Dict[str, Any]:
        """Chạy một biểu thức AutoLISP và LẤY VỀ giá trị trả về.

        Kết quả được AutoCAD ghi ra file tạm rồi đọc lại, nên khác với
        send_command (vốn không trả về gì).
        """
        expr = str(expression).strip()
        if not expr:
            raise ValueError("Biểu thức AutoLISP rỗng.")
        if not expr.startswith("("):
            raise ValueError(
                "Biểu thức AutoLISP phải bắt đầu bằng '(' - ví dụ: (+ 1 2) hoặc (getvar \"CLAYER\")."
            )
        self._assert_idle()

        fd, out_path = tempfile.mkstemp(prefix="acad_lisp_", suffix=".txt")
        os.close(fd)
        os.remove(out_path)
        lisp_path = out_path.replace("\\", "/")

        script = (
            '(vl-load-com)'
            f'(setq _mcpR (vl-catch-all-apply (quote (lambda () {expr}))))'
            f'(setq _mcpF (open "{lisp_path}" "w"))'
            '(princ (if (vl-catch-all-error-p _mcpR)'
            ' (strcat "__ERR__" (vl-catch-all-error-message _mcpR))'
            ' (vl-princ-to-string _mcpR)) _mcpF)'
            '(close _mcpF)(setq _mcpR nil _mcpF nil)(princ)\n'
        )
        self.doc.SendCommand(script)

        deadline = time.time() + max(1.0, float(timeout))
        while time.time() < deadline:
            if os.path.exists(out_path):
                time.sleep(0.05)        # để AutoCAD kịp flush và đóng file
                break
            time.sleep(0.05)
        else:
            raise AcadError(
                f"AutoLISP không trả kết quả trong {timeout}s. Biểu thức có thể đang chờ "
                "người dùng nhập liệu (getpoint, getstring...) - hãy kiểm tra dòng lệnh AutoCAD."
            )

        raw = ""
        try:
            with open(out_path, "rb") as fh:
                data = fh.read()
            for enc in ("utf-8", "mbcs", "latin-1"):
                try:
                    raw = data.decode(enc)
                    break
                except Exception:
                    continue
        finally:
            try:
                os.remove(out_path)
            except Exception:
                pass

        if raw.startswith("__ERR__"):
            raise AcadError(f"AutoLISP báo lỗi: {raw[len('__ERR__'):].strip()}")
        return {"expression": expr, "result": raw.strip()}

    @_guard
    def purge_all(self) -> str:
        self.doc.PurgeAll()
        return "Đã Purge toàn bộ đối tượng không dùng đến."

    @_guard
    def audit(self, fix_errors=True) -> str:
        self.doc.AuditInfo(bool(fix_errors))
        return f"Đã Audit bản vẽ (fix_errors={bool(fix_errors)})."

    # ==================================================================
    # Xuất file
    # ==================================================================

    @_guard
    def export_pdf(self, output_path, plot_area="extents", layout=None,
                   config_name="DWG To PDF.pc3") -> Dict[str, Any]:
        """Xuất PDF qua đối tượng Plot (tin cậy hơn nhiều so với gửi lệnh -EXPORT)."""
        abs_path = os.path.abspath(str(output_path).strip().strip('"'))
        if not abs_path.lower().endswith(".pdf"):
            abs_path += ".pdf"
        parent = os.path.dirname(abs_path)
        if parent and not os.path.isdir(parent):
            raise FileNotFoundError(f"Thư mục đích không tồn tại: {parent}")

        warnings: List[str] = []
        if layout:
            try:
                self.doc.ActiveLayout = self.doc.Layouts.Item(str(layout))
            except Exception as exc:
                raise ValueError(f"Không tìm thấy layout '{layout}': {_explain(exc)}")

        lay = self.doc.ActiveLayout
        area_map = {"display": 0, "extents": 1, "limits": 2, "view": 3, "window": 4, "layout": 5}
        area = str(plot_area).strip().lower()
        if area not in area_map:
            raise ValueError(
                f"plot_area chỉ nhận: {', '.join(area_map)} - nhận được '{plot_area}'."
            )
        try:
            lay.ConfigName = str(config_name)
        except Exception as exc:
            warnings.append(f"Không đặt được máy in '{config_name}': {_explain(exc)}")
        for attr, value in (("PlotType", area_map[area]),
                            ("UseStandardScale", True),
                            ("StandardScale", 0),      # acScaleToFit
                            ("CenterPlot", True),
                            ("PlotWithLineweights", True)):
            try:
                setattr(lay, attr, value)
            except Exception as exc:
                warnings.append(f"Không đặt được {attr}: {_explain(exc)}")

        try:
            self.doc.SetVariable("BACKGROUNDPLOT", 0)   # in đồng bộ, biết chắc khi nào xong
        except Exception:
            pass
        try:
            self.doc.Plot.QuietErrorMode = True
        except Exception:
            pass

        # In ra file tạm rồi mới chuyển vào chỗ đích: máy in ảo của AutoCAD từ chối
        # ghi đè lên file PDF nó vừa tạo, và cách này cũng bảo đảm không bao giờ
        # báo thành công trong khi thực chất chỉ còn lại file cũ.
        tmp_path = os.path.join(parent or os.getcwd(),
                                f".mcp_plot_{os.getpid()}_{int(time.time() * 1000)}.pdf")
        plotted = False
        for attempt in range(2):
            try:
                plotted = bool(self.doc.Plot.PlotToFile(tmp_path, str(config_name)))
            except Exception as exc:
                warnings.append(f"Lần in thứ {attempt + 1} lỗi: {_explain(exc)}")
                plotted = False
            if plotted and os.path.exists(tmp_path):
                break
            time.sleep(0.6)

        if not plotted or not os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            raise AcadError(
                f"AutoCAD không xuất được PDF. Kiểm tra máy in ảo '{config_name}' đã được "
                "cài đặt và bản vẽ có nội dung nằm trong vùng in. "
                + (" | ".join(warnings) if warnings else "")
            )
        # File đích có thể còn bị khóa trong chốc lát (driver PDF, phần mềm diệt
        # virus, trình xem PDF) - thử lại vài nhịp trước khi bỏ cuộc.
        last_exc: Optional[OSError] = None
        for attempt in range(5):
            try:
                os.replace(tmp_path, abs_path)
                last_exc = None
                break
            except OSError as exc:
                last_exc = exc
                time.sleep(0.4 * (attempt + 1))
        if last_exc is not None:
            raise AcadError(
                f"Đã in xong PDF nhưng không ghi đè được '{abs_path}' - file đang bị "
                f"chương trình khác mở ({last_exc}). Hãy đóng file đó rồi thử lại; "
                f"bản vừa in tạm nằm tại: {tmp_path}"
            )
        result = {"output": abs_path, "plot_area": area, "layout": str(lay.Name),
                  "exists": True, "size_bytes": os.path.getsize(abs_path)}
        if warnings:
            result["warnings"] = warnings
        return result

    @_guard
    def export_dxf(self, output_path) -> Dict[str, Any]:
        abs_path = os.path.abspath(str(output_path).strip().strip('"'))
        if not abs_path.lower().endswith(".dxf"):
            abs_path += ".dxf"
        parent = os.path.dirname(abs_path)
        if parent and not os.path.isdir(parent):
            raise FileNotFoundError(f"Thư mục đích không tồn tại: {parent}")
        # Dùng Document.Export chứ KHÔNG dùng SaveAs: SaveAs sẽ đổi luôn tên bản vẽ
        # đang mở sang file .dxf, gây bất ngờ cho người dùng.
        # Lưu ý: Export TỰ NỐI thêm phần mở rộng, nên phải truyền đường dẫn đã bỏ đuôi.
        base = os.path.splitext(abs_path)[0]
        try:
            try:
                empty = self.doc.SelectionSets.Item("MCP_EXPORT_EMPTY")
            except Exception:
                empty = self.doc.SelectionSets.Add("MCP_EXPORT_EMPTY")
            empty.Clear()
            self.doc.Export(base, "dxf", empty)
        except Exception as exc:
            raise AcadError(
                f"Không xuất được DXF: {_explain(exc)}. Nếu muốn chuyển hẳn bản vẽ "
                "sang định dạng DXF thì dùng save_document với đường dẫn đuôi .dxf."
            )

        produced = next((p for p in (abs_path, base + ".dxf", base + ".DXF")
                         if os.path.exists(p)), None)
        if produced is None:
            raise AcadError(
                f"AutoCAD không báo lỗi nhưng không sinh ra file DXF tại '{abs_path}'. "
                "Kiểm tra quyền ghi vào thư mục đích."
            )
        if produced != abs_path:
            try:
                os.replace(produced, abs_path)      # chuẩn hóa về đúng đuôi .dxf
                produced = abs_path
            except Exception:
                pass
        return {"output": produced, "exists": True,
                "size_bytes": os.path.getsize(produced)}

    # ==================================================================
    # Vẽ hàng loạt
    # ==================================================================

    #: ánh xạ "type" trong batch -> (phương thức, hàm dựng tham số)
    def _batch_dispatch(self, op: Dict[str, Any]) -> Dict[str, Any]:
        kind = str(op.get("type", "")).strip().lower()
        common = {k: op.get(k) for k in ("layer", "color", "linetype") if op.get(k) is not None}
        if kind == "line":
            return self.add_line(op["start"], op["end"], **common)
        if kind == "circle":
            return self.add_circle(op["center"], op["radius"], **common)
        if kind == "arc":
            return self.add_arc(op["center"], op["radius"],
                                op.get("start_angle_deg", 0.0),
                                op.get("end_angle_deg", 90.0), **common)
        if kind == "ellipse":
            return self.add_ellipse(op["center"], op["major_axis"],
                                    op.get("radius_ratio", 0.5), **common)
        if kind == "point":
            return self.add_point(op["position"],
                                  **{k: v for k, v in common.items() if k != "linetype"})
        if kind in ("polyline", "polyline2d"):
            return self.add_polyline_2d(op["coordinates"], op.get("closed", False), **common)
        if kind == "polyline3d":
            return self.add_polyline_3d(op["coordinates"], op.get("closed", False),
                                        **{k: v for k, v in common.items() if k != "linetype"})
        if kind == "rectangle":
            x1, y1 = float(op["x1"]), float(op["y1"])
            x2, y2 = float(op["x2"]), float(op["y2"])
            return self.add_polyline_2d([x1, y1, x2, y1, x2, y2, x1, y2], True, **common)
        if kind == "text":
            return self.add_text(op["text"], op["insertion"], op.get("height", 2.5),
                                 op.get("rotation_deg", 0.0),
                                 **{k: v for k, v in common.items() if k != "linetype"})
        if kind == "mtext":
            return self.add_mtext(op["text"], op["insertion"], op.get("width", 50.0),
                                  op.get("height", 2.5),
                                  **{k: v for k, v in common.items() if k != "linetype"})
        if kind == "block":
            return self.insert_block(op["insertion"], op["block_name"],
                                     op.get("x_scale", 1.0), op.get("y_scale", 1.0),
                                     op.get("z_scale", 1.0), op.get("rotation_deg", 0.0),
                                     layer=op.get("layer"))
        if kind == "dimension":
            return self.add_dimension(op.get("kind", "aligned"), op["points"],
                                      layer=op.get("layer"), color=op.get("color"),
                                      text_override=op.get("text_override"),
                                      rotation_deg=op.get("rotation_deg", 0.0),
                                      leader_length=op.get("leader_length"))
        raise ValueError(
            f"Loại '{op.get('type')}' không được hỗ trợ trong batch. Hỗ trợ: line, circle, "
            "arc, ellipse, point, polyline, polyline3d, rectangle, text, mtext, block, dimension."
        )

    @_guard
    def batch_draw(self, operations, stop_on_error=False) -> Dict[str, Any]:
        """Vẽ nhiều đối tượng trong một lần gọi. Lỗi ở một mục không dừng cả lô."""
        if not isinstance(operations, list) or not operations:
            raise ValueError("'operations' phải là danh sách không rỗng các đối tượng cần vẽ.")
        if len(operations) > 5000:
            raise ValueError(
                f"Batch tối đa 5000 đối tượng mỗi lần gọi, nhận được {len(operations)}. "
                "Hãy chia thành nhiều lô."
            )
        created: List[Dict[str, Any]] = []
        failures: List[Dict[str, Any]] = []
        started = time.time()
        for i, op in enumerate(operations):
            try:
                if not isinstance(op, dict):
                    raise ValueError("Mỗi phần tử của 'operations' phải là một object JSON.")
                created.append(self._batch_dispatch(op))
            except KeyError as exc:
                failures.append({"index": i, "type": op.get("type") if isinstance(op, dict) else None,
                                 "error": f"Thiếu tham số bắt buộc: {exc}"})
                if stop_on_error:
                    break
            except AcadError as exc:
                failures.append({"index": i, "type": op.get("type") if isinstance(op, dict) else None,
                                 "error": str(exc)})
                if stop_on_error:
                    break
            except Exception as exc:
                failures.append({"index": i, "type": op.get("type") if isinstance(op, dict) else None,
                                 "error": _explain(exc)})
                if stop_on_error:
                    break
        return {
            "requested": len(operations),
            "created": len(created),
            "failed": len(failures),
            "elapsed_seconds": round(time.time() - started, 3),
            "handles": [c.get("handle") for c in created],
            "failures": failures,
        }
