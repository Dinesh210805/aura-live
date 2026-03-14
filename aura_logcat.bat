@echo off
echo Fetching PID for com.aura.aura_ui.feature.debug...

for /f %%i in ('adb shell pidof com.aura.aura_ui.feature.debug') do set PID=%%i

if "%PID%"=="" (
    echo ERROR: App is not running.
    echo Please launch the app first.
    pause
    exit /b
)

echo Starting Logcat for PID %PID%...
adb logcat -v time --pid=%PID%
pause
