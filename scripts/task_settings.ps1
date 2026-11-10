$ErrorActionPreference = "Stop"
$names = @("BUCM-DEKT-Update", "BUCM-DEKT-Health", "BUCM-DEKT-WeChat")
foreach ($n in $names) {
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 10) `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1)
    Set-ScheduledTask -TaskName $n -Settings $settings | Out-Null
    Write-Host "已更新任务设置: $n（失败后每 10 分钟重试，最多 3 次）"
}
