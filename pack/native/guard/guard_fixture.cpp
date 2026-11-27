// 课堂防护 DLL 的本机自测夹具：加载同目录 guard.dll，逐项验证钩子生效。
// 只在本进程内生效，不注入其它程序，不访问网络。
#include <windows.h>

#include <cstdio>
#include <cwchar>

#include "policy.h"

namespace {

using InstallFn = BOOL(WINAPI*)();
using UninstallFn = void(WINAPI*)();
using SetPolicyFn = void(WINAPI*)(unsigned int);
using GetPolicyFn = unsigned int(WINAPI*)();
using HookMaskFn = unsigned int(WINAPI*)();
using SetWindowsHookExWFn = HHOOK(WINAPI*)(int, HOOKPROC, HINSTANCE, DWORD);
using CreateDCWFn = HDC(WINAPI*)(LPCWSTR, LPCWSTR, LPCWSTR, const DEVMODEW*);
using GetDesktopWindowFn = HWND(WINAPI*)();
using SendInputFn = UINT(WINAPI*)(UINT, LPINPUT, int);

LRESULT CALLBACK DummyHook(int code, WPARAM wparam, LPARAM lparam) {
    return CallNextHookEx(nullptr, code, wparam, lparam);
}

void WriteLine(FILE* file, const char* key, long long value) {
    std::fprintf(file, "%s=%lld\n", key, value);
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc < 2) {
        std::fwprintf(stderr, L"usage: guard_fixture.exe <result-file>\n");
        return 2;
    }
    wchar_t module[MAX_PATH] = {};
    GetModuleFileNameW(nullptr, module, MAX_PATH);
    wchar_t* slash = wcsrchr(module, L'\\');
    if (slash != nullptr) {
        *slash = L'\0';
    }
    wchar_t dll_path[MAX_PATH] = {};
    swprintf_s(dll_path, L"%s\\guard.dll", module);

    HMODULE guard = LoadLibraryW(dll_path);
    if (guard == nullptr) {
        std::fwprintf(stderr, L"LoadLibrary failed: %lu\n", GetLastError());
        return 3;
    }
    auto install = reinterpret_cast<InstallFn>(
        GetProcAddress(guard, "JiyuGuardInstall"));
    auto uninstall = reinterpret_cast<UninstallFn>(
        GetProcAddress(guard, "JiyuGuardUninstall"));
    auto set_policy = reinterpret_cast<SetPolicyFn>(
        GetProcAddress(guard, "JiyuGuardSetPolicy"));
    auto get_policy = reinterpret_cast<GetPolicyFn>(
        GetProcAddress(guard, "JiyuGuardGetPolicy"));
    auto hook_mask = reinterpret_cast<HookMaskFn>(
        GetProcAddress(guard, "JiyuGuardHookMask"));
    auto set_hook = reinterpret_cast<SetWindowsHookExWFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "SetWindowsHookExW"));
    auto create_dc = reinterpret_cast<CreateDCWFn>(
        GetProcAddress(GetModuleHandleW(L"gdi32.dll"), "CreateDCW"));
    auto get_desktop = reinterpret_cast<GetDesktopWindowFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "GetDesktopWindow"));
    auto send_input = reinterpret_cast<SendInputFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "SendInput"));
    if (install == nullptr || uninstall == nullptr || set_policy == nullptr ||
        get_policy == nullptr) {
        return 4;
    }

    FILE* out = nullptr;
    if (_wfopen_s(&out, argv[1], L"w") != 0 || out == nullptr) {
        return 5;
    }

    HWND real_desktop = get_desktop();
    set_policy(JIYU_GUARD_ANTI_MONITOR | JIYU_GUARD_ANTI_CONTROL |
               JIYU_GUARD_BLOCK_TERMINATE);
    BOOL installed = install();
    HWND fake_desktop = get_desktop();
    HDC display_dc = create_dc(L"DISPLAY", nullptr, nullptr, nullptr);
    HHOOK hook = set_hook(WH_KEYBOARD_LL, DummyHook, nullptr, 0);
    UINT send_result = send_input(0, nullptr, 0);

    std::fwprintf(stderr, L"installed=%d\n", installed);
    WriteLine(out, "installed", installed);
    WriteLine(out, "policy", get_policy());
    WriteLine(out, "hook_mask", hook_mask != nullptr ? hook_mask() : 0);
    WriteLine(out, "desktop_changed", fake_desktop != real_desktop);
    WriteLine(out, "fake_desktop_nonnull", fake_desktop != nullptr);
    WriteLine(out, "display_dc_blocked", display_dc == nullptr);
    WriteLine(out, "hook_blocked", hook == nullptr);
    WriteLine(out, "send_input_blocked", send_result == 0);

    // 结束子进程：开启策略时必须失败，清空策略后必须成功。
    STARTUPINFOW startup = {sizeof(startup)};
    PROCESS_INFORMATION child = {};
    wchar_t command[] = L"cmd.exe /c timeout /t 30 >nul";
    BOOL spawned = CreateProcessW(nullptr, command, nullptr, nullptr, FALSE,
                                  CREATE_NO_WINDOW, nullptr, nullptr, &startup,
                                  &child);
    BOOL blocked = FALSE;
    BOOL allowed = FALSE;
    if (spawned) {
        blocked = TerminateProcess(child.hProcess, 1);
        set_policy(0);
        allowed = TerminateProcess(child.hProcess, 1);
        WaitForSingleObject(child.hProcess, 5000);
        CloseHandle(child.hThread);
        CloseHandle(child.hProcess);
    }
    WriteLine(out, "child_spawned", spawned);
    WriteLine(out, "terminate_blocked", blocked == FALSE);
    WriteLine(out, "terminate_allowed_after_reset", allowed == TRUE);

    uninstall();
    WriteLine(out, "desktop_restored", get_desktop() == real_desktop);
    std::fclose(out);
    FreeLibrary(guard);
    return 0;
}
