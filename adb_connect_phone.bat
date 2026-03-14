@echo off
echo ==============================
echo Connecting to Android device
echo IP: 100.123.167.96
echo Port: 5555
echo ==============================
echo.

adb kill-server
adb start-server

echo Connecting...
adb connect 100.123.167.96:5555

echo.
echo Connected devices:
adb devices

echo.
pause

