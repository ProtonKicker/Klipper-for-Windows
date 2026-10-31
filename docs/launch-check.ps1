param([string]$Args = "")
$exe = Join-Path $PSScriptRoot "..\app\KlipperForWindows\bin\x64\Release\net8.0-windows10.0.22621.0\win-x64\Klipper for Windows.exe"
$existing = Get-Process | Where-Object { $_.Name -like "*Klipper for Windows*" }
if ($existing) { $existing | Stop-Process -Force; Start-Sleep -Seconds 1 }
if ($Args -ne "") {
    Start-Process -FilePath $exe -ArgumentList $Args
} else {
    Start-Process -FilePath $exe
}
Start-Sleep -Seconds 15
$p = Get-Process | Where-Object { $_.Name -like "*Klipper for Windows*" }
if ($p) { Write-Output ("ALIVE pid=" + $p.Id) } else { Write-Output "DEAD" }
