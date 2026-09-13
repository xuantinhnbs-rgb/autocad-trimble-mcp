<#
.SYNOPSIS
    Che vùng chữ nhận diện trong ảnh chụp màn hình trước khi đưa vào repo công khai.

.DESCRIPTION
    Ảnh chụp một ứng dụng đang chạy mang theo danh tính của máy chụp: tên người dùng
    trong đường dẫn, tên dự án của khách hàng, tên tài khoản đăng nhập, số hiệu bản quyền.
    Một khi đã commit thì nó nằm vĩnh viễn trong lịch sử git, xoá file ở commit sau
    không gỡ được. Script này tô đè vùng cần che bằng màu nền của chính giao diện đó
    (chứ không phải làm mờ — làm mờ mạnh tay vẫn có thể đảo ngược được phần nào) và
    viết đè chữ thay thế lên trên, nên ảnh vẫn đọc được như một ảnh minh hoạ bình thường.

    Toạ độ vùng che tính bằng pixel trên ảnh gốc, gốc toạ độ ở góc trên trái.

.PARAMETER InFile
    Ảnh PNG nguồn.

.PARAMETER OutFile
    Ảnh PNG kết quả. Bằng InFile thì ghi đè.

.PARAMETER Region
    Một hoặc nhiều vùng, mỗi vùng là chuỗi 'x,y,w,h[,#RRGGBB[,chữ thay thế]]'.
    Không nêu màu thì lấy màu của pixel ngay sát mép trái vùng — thường chính là màu nền.

.PARAMETER Crop
    Vùng giữ lại, dạng 'x,y,w,h'. Cắt bỏ phần thừa thay vì tô đè lên nó — dùng khi cả
    một dải giao diện cần biến mất (danh sách file gần đây, thanh view đã lưu), vì tô
    một mảng lớn để lại một khoảng trống vô nghĩa trông rõ là đã bị sửa. Cắt được thực
    hiện SAU khi tô, nên toạ độ vùng che vẫn tính trên ảnh gốc.

.EXAMPLE
    .\scripts\redact-image.ps1 -InFile shot.png -OutFile docs\images\shot.png `
        -Region '850,20,200,30,#FFFFFF,DU-AN-DEMO' , '1400,195,260,26' -Crop '0,0,1942,752'
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InFile,
    [Parameter(Mandatory = $true)][string]$OutFile,
    [string[]]$Region,

    [string]$Crop
)

if (-not $Region -and -not $Crop) {
    throw "Cần ít nhất một trong hai: -Region (tô che) hoặc -Crop (cắt bỏ)."
}

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$src = if ([System.IO.Path]::IsPathRooted($InFile)) { $InFile }
       else { Join-Path (Get-Location).Path $InFile }
if (-not (Test-Path $src)) { throw "Không thấy ảnh nguồn: $src" }

# Đọc qua MemoryStream: Bitmap::FromFile giữ khoá file, không ghi đè lên chính nó được.
$bytes = [System.IO.File]::ReadAllBytes($src)
$ms = New-Object System.IO.MemoryStream (, $bytes)
$bmp = [System.Drawing.Bitmap]::FromStream($ms)
$gfx = [System.Drawing.Graphics]::FromImage($bmp)
$gfx.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit

try {
    foreach ($spec in @($Region)) {
        $p = $spec -split ',', 6
        if ($p.Count -lt 4) { throw "Vùng '$spec' thiếu tham số, cần tối thiểu x,y,w,h" }

        $x = [int]$p[0]; $y = [int]$p[1]; $w = [int]$p[2]; $h = [int]$p[3]
        if ($x -lt 0 -or $y -lt 0 -or $x + $w -gt $bmp.Width -or $y + $h -gt $bmp.Height) {
            throw "Vùng '$spec' nằm ngoài ảnh $($bmp.Width)x$($bmp.Height)"
        }

        $fill = if ($p.Count -ge 5 -and $p[4]) {
            [System.Drawing.ColorTranslator]::FromHtml($p[4])
        } else {
            # Pixel sát ngoài mép trái vùng: gần như luôn là màu nền của thành phần đó.
            $bmp.GetPixel([Math]::Max(0, $x - 2), $y + [int]($h / 2))
        }

        $brush = New-Object System.Drawing.SolidBrush $fill
        $gfx.FillRectangle($brush, $x, $y, $w, $h)
        $brush.Dispose()

        if ($p.Count -ge 6 -and $p[5]) {
            # Chữ thay thế lấy màu tương phản với nền vừa tô, để không tự làm mình biến mất.
            $lum = (0.299 * $fill.R + 0.587 * $fill.G + 0.114 * $fill.B) / 255
            $ink = if ($lum -gt 0.5) { [System.Drawing.Color]::FromArgb(90, 90, 90) }
                   else { [System.Drawing.Color]::FromArgb(220, 220, 220) }

            $size = [Math]::Max(8, [int]($h * 0.55))
            $font = New-Object System.Drawing.Font 'Segoe UI', $size, ([System.Drawing.FontStyle]::Regular), ([System.Drawing.GraphicsUnit]::Pixel)
            $ib = New-Object System.Drawing.SolidBrush $ink
            $fmt = New-Object System.Drawing.StringFormat
            $fmt.Alignment = [System.Drawing.StringAlignment]::Near
            $fmt.LineAlignment = [System.Drawing.StringAlignment]::Center
            $rect = New-Object System.Drawing.RectangleF $x, $y, $w, $h
            $gfx.DrawString($p[5], $font, $ib, $rect, $fmt)
            $fmt.Dispose(); $ib.Dispose(); $font.Dispose()
        }

        Write-Host "Đã che ${w}x${h} tại ($x,$y)$(if ($p.Count -ge 6 -and $p[5]) { " -> '$($p[5])'" })"
    }
} finally {
    $gfx.Dispose()
}

if ($Crop) {
    $q = $Crop -split ','
    if ($q.Count -ne 4) { throw "Crop '$Crop' phải có đúng 4 số: x,y,w,h" }
    $cx = [int]$q[0]; $cy = [int]$q[1]; $cw = [int]$q[2]; $ch = [int]$q[3]
    if ($cx -lt 0 -or $cy -lt 0 -or $cw -le 0 -or $ch -le 0 -or
        $cx + $cw -gt $bmp.Width -or $cy + $ch -gt $bmp.Height) {
        throw "Crop '$Crop' nằm ngoài ảnh $($bmp.Width)x$($bmp.Height)"
    }
    $rect = New-Object System.Drawing.Rectangle $cx, $cy, $cw, $ch
    $cut = $bmp.Clone($rect, $bmp.PixelFormat)
    $bmp.Dispose()
    $bmp = $cut
    Write-Host "Đã cắt còn ${cw}x${ch} từ ($cx,$cy)"
}

$dst = if ([System.IO.Path]::IsPathRooted($OutFile)) { $OutFile }
       else { Join-Path (Get-Location).Path $OutFile }
$dir = Split-Path -Parent $dst
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }

$bmp.Save($dst, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose(); $ms.Dispose()
Write-Host "Đã ghi $dst"
