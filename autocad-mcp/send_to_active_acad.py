import sys
import time
import win32gui
import win32con
import win32clipboard
import win32com.client

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Mã AutoLISP vẽ hình vuông 100x100 và ghi chữ
lisp_code = """(command "_COLOR" 1) (command "_LINE" "0,0,0" "100,0,0" "") (command "_COLOR" 2) (command "_LINE" "100,0,0" "100,100,0" "") (command "_COLOR" 3) (command "_LINE" "100,100,0" "0,100,0" "") (command "_COLOR" 4) (command "_LINE" "0,100,0" "0,0,0" "") (command "_COLOR" 2) (command "_TEXT" "10,50,0" "6.0" "0" "HINH VUONG 100x100") (command "_ZOOM" "_E")\n"""

print("Đang tìm cửa sổ AutoCAD đang mở trên màn hình...")

acad_hwnd = None
acad_title = ""

def enum_cb(hwnd, _):
    global acad_hwnd, acad_title
    if win32gui.IsWindowVisible(hwnd):
        title = win32gui.GetWindowText(hwnd)
        if "AutoCAD" in title or "Drawing" in title:
            acad_hwnd = hwnd
            acad_title = title
            return False
    return True

win32gui.EnumWindows(enum_cb, None)

if not acad_hwnd:
    print("[LỖI] Không tìm thấy cửa sổ AutoCAD đang mở trên màn hình!")
    sys.exit(1)

print(f"Đã tìm thấy cửa sổ AutoCAD: '{acad_title}' (HWND: {acad_hwnd})")

# Copy mã AutoLISP vào Clipboard
win32clipboard.OpenClipboard()
win32clipboard.EmptyClipboard()
win32clipboard.SetClipboardText(lisp_code)
win32clipboard.CloseClipboard()

# Kích hoạt cửa sổ AutoCAD
try:
    win32gui.ShowWindow(acad_hwnd, win32con.SW_RESTORE)
    win32gui.SetForegroundWindow(acad_hwnd)
    time.sleep(0.5)

    # Gửi phím Ctrl+V và Enter vào dòng lệnh AutoCAD
    shell = win32com.client.Dispatch("WScript.Shell")
    shell.AppActivate(acad_title)
    time.sleep(0.5)
    shell.SendKeys("^v", True)
    time.sleep(0.3)
    shell.SendKeys("{ENTER}", True)
    print("\n[THÀNH CÔNG] Đã gửi trực tiếp lệnh vẽ vào cửa sổ AutoCAD hiện tại của bạn!")
except Exception as e:
    print(f"[LỖI] Không thể gửi phím tới cửa sổ AutoCAD: {e}")

