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

$t1 = New-ScheduledTaskTrigger -Daily -At 09:30
$t2 = New-ScheduledTaskTrigger -Daily -At 15:30
$t3 = New-ScheduledTaskTrigger -Daily -At 21:30
Set-ScheduledTask -TaskName "BUCM-DEKT-WeChat" -Trigger @($t1, $t2, $t3) | Out-Null
Write-Host "已设置公众号刷新时间：09:30 / 15:30 / 21:30"
