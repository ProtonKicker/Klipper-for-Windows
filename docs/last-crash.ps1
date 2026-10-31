Get-WinEvent -LogName Application -MaxEvents 40 |
  Where-Object { $_.ProviderName -eq 'Application Error' -and $_.Message -like '*Klipper for Windows*' } |
  Select-Object -First 2 |
  ForEach-Object {
    $_.TimeCreated
    ($_.Message -split "`r?`n")[0..11] -join "`n"
    '---'
  }
