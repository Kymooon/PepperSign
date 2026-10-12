@echo off
rem Avvio di PepperSign con doppio clic.
rem Esegue avvia-peppersign.ps1 senza dover cambiare le policy di PowerShell.
rem Gli argomenti vengono passati allo script, es.:  avvia-peppersign.bat -Ip 192.168.0.50
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0avvia-peppersign.ps1" %*
echo.
pause
