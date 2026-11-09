$ErrorActionPreference = "Stop"
$names = @("BUCM-DEKT-Update", "BUCM-DEKT-Health", "BUCM-DEKT-WeChat")
foreach ($n in $names) {
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    Set-ScheduledTask -TaskName $n -Settings $settings | Out-Null
    Write-Host "已更新任务设置: $n"
}
