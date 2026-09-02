"""
Script kiểm tra kết nối giữa Python COM và AutoCAD 2022 trên máy tính.

Chạy trước khi khai báo MCP server để chắc chắn AutoCAD đã sẵn sàng.
"""

import sys

# Đảm bảo in tiếng Việt không lỗi font trên console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from autocad_client import AcadError, AutoCADClient


def test() -> bool:
    print("=" * 60)
    print("ĐANG KIỂM TRA KẾT NỐI TỚI AUTOCAD 2022...")
    print("=" * 60)

    client = AutoCADClient()
    try:
        status = client.get_status()
        print(f" [OK] Đã kết nối tới {status.get('application')} "
              f"phiên bản {status.get('version')}")
        if status.get("command_active"):
            print(" [CẢNH BÁO] AutoCAD đang dở một lệnh - hãy nhấn ESC trong AutoCAD.")
    except AcadError as exc:
        print(f" [LỖI] {exc}")
        print("\n>> Gợi ý: Mở AutoCAD 2022 với ít nhất một bản vẽ rồi chạy lại script này.")
        return False

    try:
        print("\nThông tin bản vẽ hiện tại:")
        for key, value in client.get_document_info().items():
            print(f"  - {key}: {value}")

        print("\nDanh sách layer:")
        for lyr in client.list_layers():
            print(f"  - {lyr['name']} (màu {lyr['color']}"
                  f"{', đang hiện hành' if lyr.get('is_active') else ''})")

        print("\nDanh sách bản vẽ đang mở:")
        for doc in client.list_open_documents():
            print(f"  - [{doc['index']}] {doc['name']}"
                  f"{'  <- hiện hành' if doc.get('is_active') else ''}")

        print("\n" + "=" * 60)
        print("KẾT NỐI AUTOCAD 2022 HOÀN TOÀN SẴN SÀNG CHO MCP SERVER!")
        print("=" * 60)
        return True
    except AcadError as exc:
        print(f" [LỖI] Trong quá trình đọc dữ liệu bản vẽ: {exc}")
        return False


if __name__ == "__main__":
    sys.exit(0 if test() else 1)
