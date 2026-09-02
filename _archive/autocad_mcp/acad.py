"""Thin COM wrapper around AutoCAD 2022 (R24.1) automation.

AutoCAD's COM API is only reachable from the thread that initialized the
COM apartment that owns the connection, and the MCP framework may execute
each tool call on a different worker thread. To stay safe we call
``pythoncom.CoInitialize`` at the start of every operation (wrapped in a
context manager) and re-resolve the running Application object each time
instead of caching a COM reference across calls.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional, Sequence

import pythoncom
import win32com.client

# Versioned ProgID so we always talk to AutoCAD 2022 specifically, even
# when other AutoCAD versions (e.g. 2026 = "AutoCAD.Application.25.1")
# are installed on the same machine.
PROG_ID = "AutoCAD.Application.24.1"


class AutoCADError(RuntimeError):
    pass


@contextmanager
def com_apartment() -> Iterator[None]:
    pythoncom.CoInitialize()
    try:
        yield
    finally:
        pythoncom.CoUninitialize()


def get_app(launch_if_needed: bool = True):
    """Attach to a running AutoCAD 2022, optionally launching it."""
    try:
        app = win32com.client.GetActiveObject(PROG_ID)
    except Exception:
        if not launch_if_needed:
            raise AutoCADError(
                "AutoCAD 2022 khong dang chay. Hay mo AutoCAD 2022 truoc, "
                "hoac goi lai voi launch_if_needed=True."
            )
        try:
            app = win32com.client.Dispatch(PROG_ID)
        except Exception as exc:  # pragma: no cover - environment dependent
            raise AutoCADError(f"Khong the khoi dong AutoCAD 2022: {exc}") from exc
        app.Visible = True
    return app


def get_active_document(app=None):
    app = app or get_app()
    try:
        doc = app.ActiveDocument
    except Exception as exc:
        raise AutoCADError(
            "Khong co ban ve nao dang mo trong AutoCAD."
        ) from exc
    return doc


def get_model_space(doc=None):
    doc = doc or get_active_document()
    return doc.ModelSpace


def to_variant_point(x: float, y: float, z: float = 0.0):
    return win32com.client.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(x), float(y), float(z)]
    )


def to_variant_doubles(flat_values: Sequence[float]):
    return win32com.client.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(v) for v in flat_values]
    )


def to_variant_ints(values: Sequence[int]):
    return win32com.client.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_I2, [int(v) for v in values]
    )


ACI_COLORS = {
    "byblock": 0,
    "red": 1,
    "yellow": 2,
    "green": 3,
    "cyan": 4,
    "blue": 5,
    "magenta": 6,
    "white": 7,
    "black": 7,
    "gray": 8,
    "grey": 8,
    "bylayer": 256,
}


def resolve_color(color: Optional[object]) -> Optional[int]:
    """Accept an ACI int, a color name, or None (leave unchanged)."""
    if color is None:
        return None
    if isinstance(color, int):
        return color
    key = str(color).strip().lower()
    if key.isdigit():
        return int(key)
    if key not in ACI_COLORS:
        raise AutoCADError(
            f"Mau khong hop le: {color!r}. Dung so ACI (1-255) hoac ten: "
            f"{', '.join(sorted(set(ACI_COLORS)))}"
        )
    return ACI_COLORS[key]


def apply_layer(entity, layer: Optional[str]) -> None:
    if layer:
        entity.Layer = layer


def get_or_create_layer(doc, name: str, color: Optional[object] = None):
    try:
        layer = doc.Layers.Item(name)
    except Exception:
        layer = doc.Layers.Add(name)
    aci = resolve_color(color)
    if aci is not None:
        layer.color = aci
    return layer


def entity_summary(ent) -> dict:
    data = {
        "handle": ent.Handle,
        "type": ent.ObjectName,
        "layer": ent.Layer,
    }
    obj_name = ent.ObjectName
    try:
        if obj_name == "AcDbLine":
            data["start_point"] = list(ent.StartPoint)
            data["end_point"] = list(ent.EndPoint)
        elif obj_name == "AcDbCircle":
            data["center"] = list(ent.Center)
            data["radius"] = ent.Radius
        elif obj_name == "AcDbArc":
            data["center"] = list(ent.Center)
            data["radius"] = ent.Radius
            data["start_angle"] = ent.StartAngle
            data["end_angle"] = ent.EndAngle
        elif obj_name in ("AcDbText", "AcDbMText"):
            data["text"] = ent.TextString
            data["insertion_point"] = list(ent.InsertionPoint)
            if obj_name == "AcDbText":
                data["height"] = ent.Height
        elif obj_name == "AcDbPolyline":
            data["closed"] = bool(ent.Closed)
            data["num_vertices"] = ent.NumberOfVertices
    except Exception:
        pass
    return data
