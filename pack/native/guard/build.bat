@echo off
rem Build the classroom guard DLL and test fixtures inside a Windows container.
rem Usage: build.bat ^<x86^|x64^> ^<work-dir^> ^<out-dir^>
setlocal
if "%1"=="" exit /b 2
if "%2"=="" exit /b 2
if "%3"=="" exit /b 2
call C:\BuildTools\VC\Auxiliary\Build\vcvarsall.bat %1 >nul || exit /b 1
cd /d "%~2" || exit /b 1
cl /nologo /LD /MT /EHsc /D_CRT_SECURE_NO_WARNINGS guard.cpp mhook\mhook.cpp disasm-lib\cpu.c disasm-lib\disasm.c disasm-lib\disasm_x86.c disasm-lib\misc.c /Fe:guard.dll user32.lib gdi32.lib advapi32.lib || exit /b 1
cl /nologo /MT /EHsc /D_CRT_SECURE_NO_WARNINGS guard_fixture.cpp /Fe:guard_fixture.exe user32.lib gdi32.lib || exit /b 1
cl /nologo /MT /EHsc /D_CRT_SECURE_NO_WARNINGS guard_target.cpp /Fe:guard_target.exe || exit /b 1
if not exist "%~3" mkdir "%~3"
copy /y guard.dll "%~3\guard_%1.dll" >nul || exit /b 1
copy /y guard_fixture.exe "%~3\guard_fixture_%1.exe" >nul || exit /b 1
copy /y guard_target.exe "%~3\guard_target_%1.exe" >nul || exit /b 1
echo BUILD_OK %1
