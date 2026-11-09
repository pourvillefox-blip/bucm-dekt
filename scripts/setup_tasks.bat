@echo off
chcp 65001 >nul
setlocal
set "DIR=%~dp0"
echo === 注册定时任务 ===
schtasks /Create /TN "BUCM-DEKT-Update" /TR "%DIR%update_task.bat" /SC DAILY /MO 3 /ST 03:00 /F
schtasks /Create /TN "BUCM-DEKT-Health" /TR "%DIR%health_task.bat" /SC HOURLY /MO 2 /ST 00:15 /F
schtasks /Create /TN "BUCM-DEKT-WeChat" /TR "%DIR%wechat_update_task.bat" /SC HOURLY /MO 12 /ST 09:30 /F

echo === 允许电池供电、错过时间后补跑 ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%DIR%task_settings.ps1"

echo.
echo === 当前任务状态 ===
schtasks /Query /TN "BUCM-DEKT-Update" /FO LIST
schtasks /Query /TN "BUCM-DEKT-Health" /FO LIST
schtasks /Query /TN "BUCM-DEKT-WeChat" /FO LIST
echo.
echo 说明：
echo   - 更新任务每 3 天 03:00 运行（错过会在开机后补跑）
echo   - 健康检查每 2 小时运行
echo   - 任务默认“仅交互式登录时运行”，注销后不会执行
echo   - 删除任务：schtasks /Delete /TN "BUCM-DEKT-Update" /F
pause
