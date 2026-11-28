@echo off
setlocal
if "%~1"=="" (
    echo usage: Build.bat WORKDIR OUTDIR
    exit /b 2
)
set "WORK=%~1"
set "OUT=%~2"
set "WDK=C:\wdk\c"
call C:\BuildTools\VC\Auxiliary\Build\vcvars64.bat >nul
if errorlevel 1 exit /b 1
if not exist "%OUT%" mkdir "%OUT%"
pushd "%WORK%"
cl /nologo /kernel /GS- /W4 /O2 /D_AMD64_ /DAMD64 /DWIN32=100 /D_WIN32_WINNT=0x0A00 /DNTDDI_VERSION=0x0A000000 /I"%WDK%\Include\10.0.26100.0\km" /I"%WDK%\Include\10.0.26100.0\shared" /c JiYuGuardDriver.c
if errorlevel 1 goto :fail
link /nologo /DRIVER /SUBSYSTEM:NATIVE /ENTRY:DriverEntry /OUT:JiYuGuardDriver.sys JiYuGuardDriver.obj /LIBPATH:"%WDK%\Lib\10.0.26100.0\km\x64" ntoskrnl.lib
if errorlevel 1 goto :fail
copy /Y JiYuGuardDriver.sys "%OUT%\JiYuGuardDriver.sys" >nul
echo BUILD_OK driver
popd
exit /b 0

:fail
popd
exit /b 1
