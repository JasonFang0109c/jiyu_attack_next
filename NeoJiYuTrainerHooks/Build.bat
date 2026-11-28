@echo off
rem Build the classroom guard DLL and test fixtures inside a Windows container.
rem Usage: Build.bat ^<x86^|x64^> ^<work-dir^> ^<out-dir^>
setlocal
if "%1"=="" exit /b 2
if "%2"=="" exit /b 2
if "%3"=="" exit /b 2
call C:\BuildTools\VC\Auxiliary\Build\vcvarsall.bat %1 >nul || exit /b 1
cd /d "%~2" || exit /b 1
set "GUARD_NAME=GuardX64.dll"
if /I "%1"=="x86" set "GUARD_NAME=GuardX86.dll"
cl /nologo /LD /MT /EHsc /D_CRT_SECURE_NO_WARNINGS Hooks.cpp Menu.cpp Mhook\mhook.cpp DisasmLib\cpu.c DisasmLib\disasm.c DisasmLib\disasm_x86.c DisasmLib\misc.c /Fe:Hooks.dll user32.lib gdi32.lib advapi32.lib || exit /b 1
cl /nologo /MT /EHsc /D_CRT_SECURE_NO_WARNINGS GuardFixture.cpp /Fe:hooks_fixture.exe user32.lib gdi32.lib || exit /b 1
cl /nologo /MT /EHsc /D_CRT_SECURE_NO_WARNINGS GuardTarget.cpp /Fe:guard_target.exe || exit /b 1
cl /nologo /MT /EHsc /D_CRT_SECURE_NO_WARNINGS MenuFixture.cpp /Fe:menu_fixture.exe user32.lib || exit /b 1
if not exist "%~3" mkdir "%~3"
copy /y Hooks.dll "%~3\%GUARD_NAME%" >nul || exit /b 1
copy /y hooks_fixture.exe "%~3\hooks_fixture_%1.exe" >nul || exit /b 1
copy /y guard_target.exe "%~3\guard_target_%1.exe" >nul || exit /b 1
copy /y menu_fixture.exe "%~3\menu_fixture_%1.exe" >nul || exit /b 1
echo BUILD_OK %1
