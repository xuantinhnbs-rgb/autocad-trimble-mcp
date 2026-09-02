"""MCP server that drives AutoCAD 2022 through COM automation.

Run with:  python -m autocad_mcp.server
Requires AutoCAD 2022 to be installed on this machine (it will be
launched automatically if not already running).
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from mcp.server.fastmcp import FastMCP

from . import acad
from .acad import (
    AutoCADError,
    com_apartment,
    entity_summary,
    get_active_document,
    get_app,
    get_model_space,
    get_or_create_layer,
    resolve_color,
    to_variant_doubles,
    to_variant_point,
)

mcp = FastMCP("autocad-2022")


# ---------------------------------------------------------------------------
# Connection / document info
# ---------------------------------------------------------------------------

@mcp.tool()
def get_status() -> dict:
    """Kiem tra ket noi toi AutoCAD 2022: phien ban, ban ve dang active."""
    with com_apartment():
        app = get_app()
        info = {
            "connected": True,
            "version": app.Version,
            "full_name": app.FullName,
            "visible": bool(app.Visible),
            "document_count": app.Documents.Count,
        }
        try:
            doc = app.ActiveDocument
            info["active_document"] = doc.Name
            info["active_document_path"] = doc.FullName
        except Exception:
            info["active_document"] = None
        return info


@mcp.tool()
def list_documents() -> List[dict]:
    """Liet ke tat ca ban ve (.dwg) dang mo trong AutoCAD."""
    with com_apartment():
        app = get_app()
        docs = []
        for i in range(app.Documents.Count):
            d = app.Documents.Item(i)
            docs.append({"name": d.Name, "full_path": d.FullName, "saved": bool(d.Saved)})
        return docs


@mcp.tool()
def new_drawing(template_path: Optional[str] = None) -> dict:
    """Tao mot ban ve moi. template_path la duong dan file .dwt (tuy chon)."""
    with com_apartment():
        app = get_app()
        doc = app.Documents.Add(template_path) if template_path else app.Documents.Add()
        return {"name": doc.Name, "full_path": doc.FullName}


@mcp.tool()
def open_drawing(path: str, read_only: bool = False) -> dict:
    """Mo mot file .dwg co san."""
    with com_apartment():
        app = get_app()
        doc = app.Documents.Open(path, read_only)
        return {"name": doc.Name, "full_path": doc.FullName}


@mcp.tool()
def save_drawing(path: Optional[str] = None) -> dict:
    """Luu ban ve dang active. Neu co path se 'Save As' toi duong dan do."""
    with com_apartment():
        doc = get_active_document()
        if path:
            doc.SaveAs(path)
        else:
            doc.Save()
        return {"name": doc.Name, "full_path": doc.FullName}


# ---------------------------------------------------------------------------
# Drawing primitives
# ---------------------------------------------------------------------------

@mcp.tool()
def draw_line(
    x1: float, y1: float, x2: float, y2: float,
    z1: float = 0.0, z2: float = 0.0,
    layer: Optional[str] = None, color: Optional[str] = None,
) -> dict:
    """Ve mot doan thang tu (x1,y1,z1) den (x2,y2,z2) trong Model Space."""
    with com_apartment():
        doc = get_active_document()
        ms = get_model_space(doc)
        line = ms.AddLine(
            acad.to_variant_point(x1, y1, z1), acad.to_variant_point(x2, y2, z2)
        )
        acad.apply_layer(line, layer)
        aci = resolve_color(color)
        if aci is not None:
            line.color = aci
        return entity_summary(line)


@mcp.tool()
def draw_circle(
    cx: float, cy: float, radius: float, cz: float = 0.0,
    layer: Optional[str] = None, color: Optional[str] = None,
) -> dict:
    """Ve mot hinh tron tam (cx,cy,cz) ban kinh radius."""
    with com_apartment():
        doc = get_active_document()
        ms = get_model_space(doc)
        circle = ms.AddCircle(to_variant_point(cx, cy, cz), float(radius))
        acad.apply_layer(circle, layer)
        aci = resolve_color(color)
        if aci is not None:
            circle.color = aci
        return entity_summary(circle)


@mcp.tool()
def draw_arc(
    cx: float, cy: float, radius: float, start_angle_deg: float, end_angle_deg: float,
    cz: float = 0.0, layer: Optional[str] = None, color: Optional[str] = None,
) -> dict:
    """Ve mot cung tron. Goc tinh bang do, nguoc chieu kim dong ho tu truc X."""
    import math

    with com_apartment():
        doc = get_active_document()
        ms = get_model_space(doc)
        arc = ms.AddArc(
            to_variant_point(cx, cy, cz),
            float(radius),
            math.radians(start_angle_deg),
            math.radians(end_angle_deg),
        )
        acad.apply_layer(arc, layer)
        aci = resolve_color(color)
        if aci is not None:
            arc.color = aci
        return entity_summary(arc)


@mcp.tool()
def draw_polyline(
    points: List[List[float]], closed: bool = False,
    layer: Optional[str] = None, color: Optional[str] = None,
) -> dict:
    """Ve polyline (2D) qua danh sach diem [[x1,y1], [x2,y2], ...]."""
    with com_apartment():
        doc = get_active_document()
        ms = get_model_space(doc)
        flat: list[float] = []
        for p in points:
            flat.extend([float(p[0]), float(p[1])])
        pl = ms.AddLightWeightPolyline(to_variant_doubles(flat))
        pl.Closed = bool(closed)
        acad.apply_layer(pl, layer)
        aci = resolve_color(color)
        if aci is not None:
            pl.color = aci
        return entity_summary(pl)


@mcp.tool()
def draw_rectangle(
    x1: float, y1: float, x2: float, y2: float, z: float = 0.0,
    layer: Optional[str] = None, color: Optional[str] = None,
) -> dict:
    """Ve hinh chu nhat qua 2 goc doi dien (x1,y1) va (x2,y2)."""
    return draw_polyline(
        points=[[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
        closed=True, layer=layer, color=color,
    )


@mcp.tool()
def add_text(
    text: str, x: float, y: float, height: float, z: float = 0.0,
    layer: Optional[str] = None, color: Optional[str] = None, rotation_deg: float = 0.0,
) -> dict:
    """Chen doan text tai (x,y,z) voi chieu cao chu height."""
    import math

    with com_apartment():
        doc = get_active_document()
        ms = get_model_space(doc)
        t = ms.AddText(text, to_variant_point(x, y, z), float(height))
        t.Rotation = math.radians(rotation_deg)
        acad.apply_layer(t, layer)
        aci = resolve_color(color)
        if aci is not None:
            t.color = aci
        return entity_summary(t)


# ---------------------------------------------------------------------------
# Layers
# ---------------------------------------------------------------------------

@mcp.tool()
def list_layers() -> List[dict]:
    """Liet ke tat ca layer trong ban ve dang active."""
    with com_apartment():
        doc = get_active_document()
        layers = []
        for i in range(doc.Layers.Count):
            l = doc.Layers.Item(i)
            layers.append({
                "name": l.Name, "color": l.color, "locked": bool(l.Lock),
                "frozen": bool(l.Freeze), "on": bool(l.LayerOn),
            })
        return layers


@mcp.tool()
def create_layer(name: str, color: Optional[str] = None) -> dict:
    """Tao layer moi (hoac cap nhat mau neu da ton tai). color: ten mau hoac ma ACI (1-255)."""
    with com_apartment():
        doc = get_active_document()
        layer = get_or_create_layer(doc, name, color)
        return {"name": layer.Name, "color": layer.color}


@mcp.tool()
def set_current_layer(name: str) -> dict:
    """Dat layer hien hanh (layer moi ve them vao se dung layer nay)."""
    with com_apartment():
        doc = get_active_document()
        layer = get_or_create_layer(doc, name)
        doc.ActiveLayer = layer
        return {"current_layer": doc.ActiveLayer.Name}


# ---------------------------------------------------------------------------
# Query / edit entities
# ---------------------------------------------------------------------------

@mcp.tool()
def list_entities(limit: int = 200) -> List[dict]:
    """Liet ke cac doi tuong trong Model Space (toi da 'limit' doi tuong)."""
    with com_apartment():
        ms = get_model_space()
        results = []
        count = min(ms.Count, limit)
        for i in range(count):
            ent = ms.Item(i)
            results.append(entity_summary(ent))
        return results


@mcp.tool()
def get_entity(handle: str) -> dict:
    """Lay chi tiet mot doi tuong theo handle (xem tu list_entities)."""
    with com_apartment():
        doc = get_active_document()
        try:
            ent = doc.HandleToObject(handle)
        except Exception as exc:
            raise AutoCADError(f"Khong tim thay doi tuong voi handle {handle!r}") from exc
        return entity_summary(ent)


@mcp.tool()
def delete_entity(handle: str) -> dict:
    """Xoa mot doi tuong theo handle."""
    with com_apartment():
        doc = get_active_document()
        try:
            ent = doc.HandleToObject(handle)
        except Exception as exc:
            raise AutoCADError(f"Khong tim thay doi tuong voi handle {handle!r}") from exc
        summary = entity_summary(ent)
        ent.Delete()
        return {"deleted": True, "entity": summary}


@mcp.tool()
def get_selected_entities() -> List[dict]:
    """Lay danh sach doi tuong dang duoc chon (selection) tren AutoCAD."""
    with com_apartment():
        app = get_app()
        doc = get_active_document(app)
        results = []
        try:
            sel = doc.PickfirstSelectionSet
            for i in range(sel.Count):
                results.append(entity_summary(sel.Item(i)))
        except Exception:
            pass
        return results


# ---------------------------------------------------------------------------
# View / variables / raw command escape hatch
# ---------------------------------------------------------------------------

@mcp.tool()
def zoom_extents() -> dict:
    """Zoom to toan bo ban ve (ZOOM EXTENTS)."""
    with com_apartment():
        app = get_app()
        app.ZoomExtents()
        return {"ok": True}


@mcp.tool()
def get_variable(name: str) -> dict:
    """Doc gia tri mot system variable cua AutoCAD (vd: 'CLAYER', 'DIMSCALE')."""
    with com_apartment():
        doc = get_active_document()
        value = doc.GetVariable(name)
        return {"name": name, "value": value}


@mcp.tool()
def set_variable(name: str, value: object) -> dict:
    """Ghi gia tri mot system variable cua AutoCAD."""
    with com_apartment():
        doc = get_active_document()
        doc.SetVariable(name, value)
        return {"name": name, "value": doc.GetVariable(name)}


@mcp.tool()
def run_command(command: str) -> dict:
    """Gui truc tiep mot chuoi lenh AutoCAD (nhu go tren command line).

    Vi du: "CIRCLE\\n0,0\\n10\\n" hoac "(princ (+ 1 2))\\n" cho AutoLISP.
    Lenh se duoc gui bat dong bo (fire-and-forget), khong tra ve gia tri.
    """
    with com_apartment():
        doc = get_active_document()
        text = command if command.endswith("\n") else command + "\n"
        doc.SendCommand(text)
        return {"sent": True, "command": command}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
