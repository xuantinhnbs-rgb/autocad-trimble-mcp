"""
Kiểm tra hợp đồng của toàn bộ tool MCP.
=======================================
Chạy được mà không cần AutoCAD hay Trimble Connect: chỉ nạp server và soi
phần khai báo tool. Đây là lưới an toàn cho việc đổi chữ ký hàm — thứ trực
tiếp sinh ra JSON schema mà AI nhìn thấy.
"""

import re

import pytest
from conftest import chi_tren_windows, list_tools

pytestmark = chi_tren_windows

# Số tool được ghi trong README. Sửa số ở đây thì phải sửa cả README.
EXPECTED_COUNTS = {"autocad": 49, "trimble": 34}

SNAKE_CASE = re.compile(r"^[a-z][a-z0-9_]*$")


@pytest.fixture(scope="session")
def autocad_tools(autocad_server):
    return list_tools(autocad_server)


@pytest.fixture(scope="session")
def trimble_tools(trimble_server):
    return list_tools(trimble_server)


def test_autocad_dung_so_tool_nhu_tai_lieu(autocad_tools):
    assert len(autocad_tools) == EXPECTED_COUNTS["autocad"]


def test_trimble_dung_so_tool_nhu_tai_lieu(trimble_tools):
    assert len(trimble_tools) == EXPECTED_COUNTS["trimble"]


@pytest.mark.parametrize("fixture_name", ["autocad_tools", "trimble_tools"])
def test_ten_tool_khong_trung_va_dung_snake_case(fixture_name, request):
    tools = request.getfixturevalue(fixture_name)
    names = [t.name for t in tools]
    assert len(names) == len(set(names)), "Có tool bị đặt trùng tên"
    sai = [n for n in names if not SNAKE_CASE.match(n)]
    assert not sai, "Tên tool không đúng snake_case: %s" % sai


@pytest.mark.parametrize("fixture_name", ["autocad_tools", "trimble_tools"])
def test_moi_tool_deu_co_mo_ta(fixture_name, request):
    """Không có mô tả thì AI không biết khi nào nên gọi tool."""
    tools = request.getfixturevalue(fixture_name)
    thieu = [t.name for t in tools if not (t.description or "").strip()]
    assert not thieu, "Tool thiếu docstring: %s" % thieu


@pytest.mark.parametrize("fixture_name", ["autocad_tools", "trimble_tools"])
def test_moi_tool_co_input_schema_kieu_object(fixture_name, request):
    tools = request.getfixturevalue(fixture_name)
    for tool in tools:
        schema = tool.input_schema
        assert isinstance(schema, dict), tool.name
        assert schema.get("type") == "object", tool.name
        assert "properties" in schema, tool.name


@pytest.mark.parametrize("fixture_name", ["autocad_tools", "trimble_tools"])
def test_moi_tham_so_bat_buoc_deu_ton_tai_trong_properties(fixture_name, request):
    """Tham số nằm trong `required` mà không có trong `properties` là schema hỏng."""
    tools = request.getfixturevalue(fixture_name)
    for tool in tools:
        schema = tool.input_schema
        props = set(schema.get("properties", {}))
        thieu = [r for r in schema.get("required", []) if r not in props]
        assert not thieu, "%s: %s" % (tool.name, thieu)
