"""
Tạo lối tắt (Shortcut) ra màn hình Desktop cho Ứng dụng AutoCAD 2022 MCP Controller.
"""

import os

import win32com.client


def create_shortcut():
    desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
    shortcut_path = os.path.join(desktop, "AutoCAD 2022 MCP Controller.lnk")

    current_dir = os.path.dirname(os.path.abspath(__file__))
    target_vbs = os.path.join(current_dir, "run_app_hidden.vbs")
    target_bat = os.path.join(current_dir, "run_app.bat")

    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(shortcut_path)

    # Ưu tiên mở qua wscript với run_app_hidden.vbs để không bị nháy console
    if os.path.exists(target_vbs):
        shortcut.TargetPath = "wscript.exe"
        shortcut.Arguments = f'"{target_vbs}"'
    else:
        shortcut.TargetPath = target_bat

    shortcut.WorkingDirectory = current_dir
    shortcut.Description = "Ứng dụng Bật/Tắt và Quản lý MCP Server kết nối AutoCAD 2022"

    # Tìm icon AutoCAD nếu có
    acad_exe = r"C:\Program Files\Autodesk\AutoCAD 2022\acad.exe"
    if os.path.exists(acad_exe):
        shortcut.IconLocation = f"{acad_exe}, 0"

    shortcut.save()
    print(f"✅ Đã tạo thành công lối tắt trên Desktop: {shortcut_path}")

if __name__ == "__main__":
    create_shortcut()
