param([int]$ClickX = -1, [int]$ClickY = -1, [string]$OutPath = "shot.png")
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Cap2 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
$proc = Get-Process | Where-Object { $_.MainWindowTitle -like "*Klipper for Windows*" } | Select-Object -First 1
if (-not $proc) { Write-Output "window-not-found"; exit 1 }
$hwnd = $proc.MainWindowHandle
[Win32Cap2]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Milliseconds 400
if ($ClickX -ge 0) {
    [Win32Cap2]::SetCursorPos($ClickX, $ClickY) | Out-Null
    Start-Sleep -Milliseconds 200
    [Win32Cap2]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
    [Win32Cap2]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 1200
}
$rect = New-Object Win32Cap2+RECT
[Win32Cap2]::GetWindowRect($hwnd, [ref]$rect) | Out-Null
$w = $rect.Right - $rect.Left; $h = $rect.Bottom - $rect.Top
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($rect.Left, $rect.Top, 0, 0, (New-Object System.Drawing.Size($w, $h)))
$bmp.Save($OutPath, [System.Drawing.Imaging.ImageFormat]::Png)
Write-Output ("saved " + $OutPath)
