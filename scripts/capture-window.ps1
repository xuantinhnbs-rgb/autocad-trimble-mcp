<#
.SYNOPSIS
    Chụp ảnh một cửa sổ ứng dụng ra file PNG — dùng để tạo lại ảnh minh chứng trong docs/images/.

.DESCRIPTION
    Đưa cửa sổ lên trước rồi chụp đúng vùng nó chiếm trên màn hình. Cách này chụp được cả
    nội dung tăng tốc phần cứng (khung nhìn 3D của AutoCAD và Trimble Connect), thứ mà
    PrintWindow của Win32 thường trả về một hình chữ nhật đen.

    Kích thước lấy từ DwmGetWindowAttribute chứ không phải GetWindowRect: từ Windows 10,
    GetWindowRect trả về cả viền bóng vô hình rộng vài pixel quanh cửa sổ, chụp theo nó thì
    ảnh dính một dải nền desktop ở ba cạnh.

.PARAMETER TitleLike
    Một phần tiêu đề cửa sổ, không phân biệt hoa thường. Ví dụ 'AutoCAD', 'Trimble Connect'.

.PARAMETER ProcessName
    Tên tiến trình. Ví dụ 'acad', 'TrimbleConnect', 'powershell'.

    Dùng được đồng thời với TitleLike, và nên dùng cả hai khi tiêu đề cần tìm là một
    chuỗi phổ biến: một tab trình duyệt đang mở trang GitHub của chính dự án cũng khớp
    với tên dự án, và nó thường đứng trước trong danh sách tiến trình.

.PARAMETER OutFile
    Đường dẫn file PNG cần ghi. Thư mục cha sẽ được tạo nếu chưa có.

.PARAMETER DelaySeconds
    Số giây chờ sau khi đưa cửa sổ lên trước, để ứng dụng vẽ lại xong. Mặc định 2.

.EXAMPLE
    .\scripts\capture-window.ps1 -TitleLike 'AutoCAD' -OutFile docs\images\autocad-demo.png

.EXAMPLE
    .\scripts\capture-window.ps1 -ProcessName TrimbleConnect -OutFile docs\images\trimble-demo.png -DelaySeconds 3
#>
[CmdletBinding()]
param(
    [string]$TitleLike,

    [string]$ProcessName,

    [Parameter(Mandatory = $true)]
    [string]$OutFile,

    [int]$DelaySeconds = 2
)

$ErrorActionPreference = 'Stop'

if (-not $TitleLike -and -not $ProcessName) {
    throw "Cần ít nhất một trong hai: -TitleLike hoặc -ProcessName."
}

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

Add-Type @'
using System;
using System.Runtime.InteropServices;

public static class WinCap
{
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }

    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
    [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(
        IntPtr hWnd, int attr, out RECT value, int size);

    public const int SW_RESTORE = 9;
    public const int DWMWA_EXTENDED_FRAME_BOUNDS = 9;

    // Viền bóng vô hình quanh cửa sổ khiến GetWindowRect rộng hơn phần nhìn thấy.
    // DWM biết kích thước thật; chỉ khi nó từ chối mới quay về GetWindowRect.
    public static RECT VisibleBounds(IntPtr hWnd)
    {
        RECT r;
        int hr = DwmGetWindowAttribute(hWnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                                       out r, Marshal.SizeOf(typeof(RECT)));
        if (hr != 0) { GetWindowRect(hWnd, out r); }
        return r;
    }
}
'@

# --- Tìm cửa sổ ---------------------------------------------------------------
$ung_vien = if ($ProcessName) {
    Get-Process -Name $ProcessName -ErrorAction SilentlyContinue
} else {
    Get-Process
}
$ung_vien = @($ung_vien | Where-Object { $_.MainWindowHandle -ne 0 })
if ($TitleLike) {
    $ung_vien = @($ung_vien | Where-Object { $_.MainWindowTitle -like "*$TitleLike*" })
}

$dieu_kien = @()
if ($ProcessName) { $dieu_kien += "tiến trình '$ProcessName'" }
if ($TitleLike) { $dieu_kien += "tiêu đề chứa '$TitleLike'" }
$what = $dieu_kien -join ' và '

if ($ung_vien.Count -eq 0) {
    throw "Không tìm thấy cửa sổ nào khớp $what. Hãy mở ứng dụng rồi chạy lại."
}
if ($ung_vien.Count -gt 1) {
    Write-Warning "Có $($ung_vien.Count) cửa sổ khớp $what, lấy cửa sổ đầu tiên:"
    $ung_vien | ForEach-Object {
        Write-Warning "  $($_.ProcessName) (PID $($_.Id)) - $($_.MainWindowTitle)"
    }
}
$proc = $ung_vien[0]

$hwnd = $proc.MainWindowHandle
Write-Host "Cửa sổ: $($proc.ProcessName) (PID $($proc.Id)) — $($proc.MainWindowTitle)"

# --- Đưa lên trước và chờ vẽ lại ----------------------------------------------
if ([WinCap]::IsIconic($hwnd)) { [void][WinCap]::ShowWindow($hwnd, [WinCap]::SW_RESTORE) }
[void][WinCap]::SetForegroundWindow($hwnd)
Start-Sleep -Seconds $DelaySeconds

$r = [WinCap]::VisibleBounds($hwnd)
$w = $r.Right - $r.Left
$h = $r.Bottom - $r.Top
if ($w -le 0 -or $h -le 0) { throw "Cửa sổ báo kích thước không hợp lệ (${w}x${h})." }

# --- Chụp ----------------------------------------------------------------------
$bmp = New-Object System.Drawing.Bitmap $w, $h
$gfx = [System.Drawing.Graphics]::FromImage($bmp)
try {
    $gfx.CopyFromScreen($r.Left, $r.Top, 0, 0, $bmp.Size)
} finally {
    $gfx.Dispose()
}

$dir = Split-Path -Parent $OutFile
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
$full = if ([System.IO.Path]::IsPathRooted($OutFile)) { $OutFile }
        else { Join-Path (Get-Location).Path $OutFile }
$bmp.Save($full, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()

$kb = [math]::Round((Get-Item $full).Length / 1KB)
Write-Host "Đã ghi $full (${w}x${h}, ${kb} KB)"
