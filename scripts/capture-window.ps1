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

.PARAMETER ProcessId
    Chỉ đích danh một tiến trình theo PID. Đây là cách chọn DUY NHẤT không mơ hồ khi
    ứng dụng đang mở nhiều phiên: hai phiên ReCap hay hai phiên AutoCAD có cùng tên
    tiến trình VÀ cùng tiêu đề cửa sổ, nên -ProcessName lẫn -TitleLike đều không tách
    được chúng ra.

.PARAMETER Force
    Cho phép chụp khi có nhiều cửa sổ khớp, lấy cửa sổ đầu tiên. Mặc định script BÁO
    LỖI trong tình huống đó thay vì đoán — xem phần ghi chú dưới đây.

.PARAMETER OutFile
    Đường dẫn file PNG cần ghi. Thư mục cha sẽ được tạo nếu chưa có.

.PARAMETER DelaySeconds
    Số giây chờ sau khi đưa cửa sổ lên trước, để ứng dụng vẽ lại xong. Mặc định 2.

.NOTES
    VÌ SAO NHIỀU CỬA SỔ KHỚP LÀ LỖI, KHÔNG PHẢI CẢNH BÁO

    Trước đây script chỉ in cảnh báo rồi chụp cửa sổ đầu tiên. Cảnh báo ấy trôi qua
    giữa những dòng log khác, và thứ nằm trong file PNG là một phiên KHÁC của cùng
    ứng dụng — trong một lần chạy thật, đó là phiên đang mở dữ liệu của một công
    trình có thật, kèm tên tài khoản đăng nhập trên thanh tiêu đề. Ảnh trông hợp lệ,
    kích thước đúng, không có dấu hiệu nào cho thấy đã chụp nhầm.

    Ảnh minh chứng hầu như luôn đi thẳng vào một repo công khai, và một lần commit là
    nằm vĩnh viễn trong lịch sử git. Nên ở đây "đoán rồi cảnh báo" là mặc định sai:
    script dừng lại, liệt kê các ứng viên kèm PID, và để người chạy chọn.

.EXAMPLE
    .\scripts\capture-window.ps1 -TitleLike 'AutoCAD' -OutFile docs\images\autocad-demo.png

.EXAMPLE
    .\scripts\capture-window.ps1 -ProcessName TrimbleConnect -OutFile docs\images\trimble-demo.png -DelaySeconds 3

.EXAMPLE
    # Đang mở hai phiên ReCap; chỉ đích danh phiên cần chụp.
    .\scripts\capture-window.ps1 -ProcessId 15640 -OutFile docs\images\recap-demo.png
#>
[CmdletBinding()]
param(
    [string]$TitleLike,

    [string]$ProcessName,

    [int]$ProcessId,

    [switch]$Force,

    [Parameter(Mandatory = $true)]
    [string]$OutFile,

    [int]$DelaySeconds = 2
)

$ErrorActionPreference = 'Stop'

if (-not $TitleLike -and -not $ProcessName -and -not $ProcessId) {
    throw "Cần ít nhất một trong ba: -TitleLike, -ProcessName hoặc -ProcessId."
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
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
    [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);
    [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);

    // Windows từ chối SetForegroundWindow từ một tiến trình không đang ở tiền cảnh.
    // Cách đi vòng chính thống: gắn tạm hàng đợi nhập liệu của luồng đang giữ tiền
    // cảnh vào luồng này, lúc đó lời gọi mới được chấp nhận.
    public static void ForceForeground(IntPtr hWnd)
    {
        IntPtr fg = GetForegroundWindow();
        if (fg == hWnd) { return; }

        uint pid;
        uint fgThread = GetWindowThreadProcessId(fg, out pid);
        uint thisThread = GetCurrentThreadId();

        bool attached = (fgThread != thisThread) && AttachThreadInput(fgThread, thisThread, true);
        try
        {
            BringWindowToTop(hWnd);
            SetForegroundWindow(hWnd);
        }
        finally
        {
            if (attached) { AttachThreadInput(fgThread, thisThread, false); }
        }
    }
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
$ung_vien = if ($ProcessId) {
    Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
} elseif ($ProcessName) {
    Get-Process -Name $ProcessName -ErrorAction SilentlyContinue
} else {
    Get-Process
}
$ung_vien = @($ung_vien | Where-Object { $_.MainWindowHandle -ne 0 })
if ($TitleLike) {
    $ung_vien = @($ung_vien | Where-Object { $_.MainWindowTitle -like "*$TitleLike*" })
}

$dieu_kien = @()
if ($ProcessId) { $dieu_kien += "PID $ProcessId" }
if ($ProcessName) { $dieu_kien += "tiến trình '$ProcessName'" }
if ($TitleLike) { $dieu_kien += "tiêu đề chứa '$TitleLike'" }
$what = $dieu_kien -join ' và '

if ($ung_vien.Count -eq 0) {
    throw "Không tìm thấy cửa sổ nào khớp $what. Hãy mở ứng dụng rồi chạy lại."
}

# Nhiều ứng viên = DỪNG, không đoán. Lý do đầy đủ ở khối .NOTES đầu file: cửa sổ
# "đầu tiên" có thể là một phiên khác của cùng ứng dụng, đang mở dữ liệu thật, và
# ảnh chụp nhầm ấy không có dấu hiệu nào để nhận ra sau này.
if ($ung_vien.Count -gt 1 -and -not $Force) {
    $danh_sach = ($ung_vien | ForEach-Object {
        "  -ProcessId $($_.Id)  $($_.ProcessName)  $($_.MainWindowTitle)"
    }) -join "`n"
    throw @"
Có $($ung_vien.Count) cửa sổ khớp $what. Script không tự chọn, vì chụp nhầm phiên
là cách thông tin của một dự án thật lọt vào repo công khai.

Chọn đích danh một trong số này:
$danh_sach

Hoặc thêm -Force nếu bạn đã chắc cửa sổ đầu tiên là đúng.
"@
}
if ($ung_vien.Count -gt 1) {
    Write-Warning "-Force: có $($ung_vien.Count) cửa sổ khớp, lấy cửa sổ đầu tiên."
}
$proc = $ung_vien[0]

$hwnd = $proc.MainWindowHandle
Write-Host "Cửa sổ: $($proc.ProcessName) (PID $($proc.Id)) — $($proc.MainWindowTitle)"

# --- Đưa lên trước, rồi KIỂM CHỨNG là nó thật sự lên trước ---------------------
# Ảnh được chụp bằng cách copy vùng màn hình mà cửa sổ đang chiếm, chứ không phải
# hỏi cửa sổ tự vẽ ra (PrintWindow trả về hình chữ nhật đen với nội dung 3D tăng
# tốc phần cứng). Nghĩa là nếu cửa sổ KHÔNG lên được tiền cảnh, script vẫn chụp —
# và thứ nằm trong file PNG là bất cứ cửa sổ nào đang nằm trên. Windows thường
# xuyên từ chối SetForegroundWindow, lời gọi trả về false, và trước đây giá trị
# trả về đó bị bỏ đi. Một lần chạy thật đã cho ra ảnh chụp một ứng dụng khác hẳn,
# đang hiển thị thông tin tài khoản — ảnh vẫn đúng kích thước, vẫn không trống,
# nên không có dấu hiệu nào cho thấy đã chụp nhầm.
if ([WinCap]::IsIconic($hwnd)) { [void][WinCap]::ShowWindow($hwnd, [WinCap]::SW_RESTORE) }

$len_thu = 0
while ($true) {
    $len_thu++
    [WinCap]::ForceForeground($hwnd)
    Start-Sleep -Milliseconds 400
    if ([WinCap]::GetForegroundWindow() -eq $hwnd) { break }
    if ($len_thu -ge 5) {
        $dang_o_tren = [WinCap]::GetForegroundWindow()
        $ten = (Get-Process | Where-Object { $_.MainWindowHandle -eq $dang_o_tren } |
                Select-Object -First 1)
        $mo_ta = if ($ten) { "$($ten.ProcessName) - $($ten.MainWindowTitle)" } else { "khong xac dinh" }
        throw @"
Khong dua duoc cua so len tien canh sau $len_thu lan thu.
Cua so dang o tren: $mo_ta

Script dung lai thay vi chup, vi anh chup luc nay se la anh cua cua so KIA —
dung kich thuoc, khong trong, va khong co dau hieu nao de nhan ra la sai.
Hay bam vao cua so can chup roi chay lai, hoac dong cua so dang che no.
"@
    }
}

# Chờ ứng dụng vẽ lại xong SAU khi đã chắc chắn nó ở tiền cảnh.
Start-Sleep -Seconds $DelaySeconds

# Tiền cảnh có thể đổi trong lúc chờ (thông báo bật lên, một tiến trình khác tự
# đưa mình lên trước). Kiểm lại ngay trước khi copy pixel.
if ([WinCap]::GetForegroundWindow() -ne $hwnd) {
    throw "Mot cua so khac da chiem tien canh trong luc cho $DelaySeconds giay. Chay lai."
}

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
