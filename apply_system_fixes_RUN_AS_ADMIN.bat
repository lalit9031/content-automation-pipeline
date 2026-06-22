@echo off
:: ============================================================
:: AI Pipeline System Safety Fixes
:: RIGHT-CLICK this file and select "Run as Administrator"
:: ============================================================

echo.
echo ====================================================
echo   AI Pipeline System Safety Fixes
echo   Applying 3 registry tweaks...
echo ====================================================
echo.

:: ---- FIX 1: GPU TDR Timeout (prevents display going black) ----
echo [1/3] Setting GPU TDR timeout to 30 seconds...
reg add "HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers" /v TdrDelay    /t REG_DWORD /d 30 /f
reg add "HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers" /v TdrDdiDelay /t REG_DWORD /d 30 /f
echo       DONE - GPU watchdog will now wait 30s before resetting display driver.
echo.

:: ---- FIX 2: TCP Socket Recycle (prevents WinError 10055 crash) ----
echo [2/3] Setting TCP socket recycle time to 30 seconds...
reg add "HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" /v TcpTimedWaitDelay /t REG_DWORD /d 30 /f
echo       DONE - Dead sockets will free up in 30s instead of 120s.
echo.

:: ---- FIX 3: Increase GPU scheduler priority for AI workloads ----
echo [3/3] Tuning GPU scheduler for compute workloads...
reg add "HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers\Scheduler" /v EnablePreemption /t REG_DWORD /d 1 /f
echo       DONE - GPU scheduler optimized for long compute tasks.
echo.

echo ====================================================
echo   ALL FIXES APPLIED SUCCESSFULLY
echo   >>> YOU MUST REBOOT FOR CHANGES TO TAKE EFFECT <<<
echo ====================================================
echo.
choice /C YN /M "Reboot now? (Y=Yes, N=Later)"
if errorlevel 2 goto skip_reboot
if errorlevel 1 shutdown /r /t 10 /c "Applying AI Pipeline system fixes. Rebooting in 10 seconds..."
:skip_reboot
echo.
echo Reboot skipped. Remember to reboot before your next AI session!
pause
