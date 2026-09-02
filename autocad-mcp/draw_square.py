import sys
from autocad_client import AutoCADClient

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    client = AutoCADClient()
    print("Đang kết nối tới AutoCAD...")
    info = client.get_document_info()
    print(f"Đã kết nối thành công tới bản vẽ: {info['name']}")

    # Tọa độ 4 góc của hình vuông 100x100
    # Corner 1: (0, 0)
    # Corner 2: (100, 0)
    # Corner 3: (100, 100)
    # Corner 4: (0, 100)
    
    print("\n--- ĐANG VẼ 4 ĐƯỜNG THẲNG TẠO HÌNH VUÔNG 100x100 ---")
    
    # Cạnh 1: Đáy (0,0) -> (100,0) - Màu Đỏ (1)
    res1 = client.add_line((0, 0, 0), (100, 0, 0), color=1)
    print(f"  + Cạnh 1 (Đáy): (0,0) -> (100,0) | Mã màu 1 (Đỏ) | Handle: {res1.get('handle')}")

    # Cạnh 2: Phải (100,0) -> (100,100) - Màu Vàng (2)
    res2 = client.add_line((100, 0, 0), (100, 100, 0), color=2)
    print(f"  + Cạnh 2 (Phải): (100,0) -> (100,100) | Mã màu 2 (Vàng) | Handle: {res2.get('handle')}")

    # Cạnh 3: Đỉnh (100,100) -> (0,100) - Màu Xanh lá (3)
    res3 = client.add_line((100, 100, 0), (0, 100, 0), color=3)
    print(f"  + Cạnh 3 (Đỉnh): (100,100) -> (0,100) | Mã màu 3 (Xanh lá) | Handle: {res3.get('handle')}")

    # Cạnh 4: Trái (0,100) -> (0,0) - Màu Cyan (4)
    res4 = client.add_line((0, 100, 0), (0, 0, 0), color=4)
    print(f"  + Cạnh 4 (Trái): (0,100) -> (0,0) | Mã màu 4 (Cyan) | Handle: {res4.get('handle')}")

    # Thêm văn bản nhãn ở tâm hình vuông
    client.add_text("HINH VUONG 100x100", (10, 50, 0), height=6.0, color=2)

    # Zoom extents để hình vuông hiển thị chính giữa màn hình
    client.zoom_extents()
    print("\n[THÀNH CÔNG] Đã vẽ hoàn tất hình vuông 100x100 và Zoom Extents trên AutoCAD!")

except Exception as e:
    print(f"\n[LỖI] {e}")
    sys.exit(1)

