param([string]$ButtonName = "Stop", [int]$WaitSec = 20)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$exe = Join-Path $PSScriptRoot "..\app\KlipperForWindows\bin\x64\Release\net8.0-windows10.0.22621.0\win-x64\Klipper for Windows.exe"
$existing = Get-Process | Where-Object { $_.Name -like "*Klipper for Windows*" }
if ($existing) { $existing | Stop-Process -Force; Start-Sleep -Seconds 2 }
Start-Process -FilePath $exe -ArgumentList "--page", "dashboard"
$hwnd = [IntPtr]::Zero
for ($i = 0; $i -lt 60; $i++) {
    $p = Get-Process | Where-Object { $_.Name -like "*Klipper for Windows*" -and $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($p) { $hwnd = $p.MainWindowHandle; break }
    Start-Sleep -Milliseconds 500
}
if ($hwnd -eq [IntPtr]::Zero) { Write-Output "no-window"; exit 1 }
Start-Sleep -Seconds 3
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
$item = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
    (New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, $ButtonName)))
if (-not $item) { Write-Output "button-not-found: $ButtonName"; exit 1 }
$invoke = $item.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
$invoke.Invoke()
Write-Output "invoked: $ButtonName"
Start-Sleep -Seconds $WaitSec
