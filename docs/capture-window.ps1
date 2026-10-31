param([string]$OutPath = "app-window.png",
      [int]$X = 80, [int]$Y = 60, [int]$W = 1280, [int]$H = 820)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Pw {
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdc, uint flags);
    public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
$proc = Get-Process | Where-Object { $_.MainWindowTitle -like "*Klipper for Windows*" } | Select-Object -First 1
if (-not $proc) { Write-Output "window-not-found"; exit 1 }
$hwnd = $proc.MainWindowHandle
[Win32Pw]::SetProcessDPIAware() | Out-Null
$rect = New-Object Win32Pw+RECT
[Win32Pw]::GetWindowRect($hwnd, [ref]$rect) | Out-Null
$w = $rect.Right - $rect.Left; $h = $rect.Bottom - $rect.Top
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
# PW_RENDERFULLCONTENT (2) captures DirectComposition/Mica windows
[Win32Pw]::PrintWindow($hwnd, $hdc, 2) | Out-Null
$g.ReleaseHdc($hdc)
$bmp.Save($OutPath, [System.Drawing.Imaging.ImageFormat]::Png)
Write-Output ("saved " + $w + "x" + $h)
