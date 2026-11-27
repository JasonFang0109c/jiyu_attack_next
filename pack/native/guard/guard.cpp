// 课堂防护：注入学生端后按其自身 API 调用拦截监视、控制、关窗与杀进程。
//
// 设计取自 JiYuTrainer（MIT）JiYuTrainerHooks.cpp 的判定思路，但只保留窄接口：
// 策略通过命名共享内存下发，导出 Install/Uninstall/Refresh 三个入口，不加载
// 驱动、不弹窗、不修改目标进程以外的任何状态。
#include <windows.h>

#include <cwchar>

#include "mhook/mhook.h"
#include "policy.h"

namespace {

volatile LONG g_flags = 0;
HWND g_fake_desktop = nullptr;
bool g_installed = false;

using GetDesktopWindowFn = HWND(WINAPI*)();
using GetWindowDCFn = HDC(WINAPI*)(HWND);
using CreateDCWFn = HDC(WINAPI*)(LPCWSTR, LPCWSTR, LPCWSTR, const DEVMODEW*);
using DwmEnableCompositionFn = HRESULT(WINAPI*)(UINT);
using SetWindowsHookExWFn = HHOOK(WINAPI*)(int, HOOKPROC, HINSTANCE, DWORD);
using SetWindowsHookExAFn = HHOOK(WINAPI*)(int, HOOKPROC, HINSTANCE, DWORD);
using SendInputFn = UINT(WINAPI*)(UINT, LPINPUT, int);
using MouseEventFn = void(WINAPI*)(DWORD, DWORD, DWORD, DWORD, ULONG_PTR);
using TerminateProcessFn = BOOL(WINAPI*)(HANDLE, UINT);
using PostMessageWFn = BOOL(WINAPI*)(HWND, UINT, WPARAM, LPARAM);
using SendMessageWFn = LRESULT(WINAPI*)(HWND, UINT, WPARAM, LPARAM);

GetDesktopWindowFn TrueGetDesktopWindow = nullptr;
GetWindowDCFn TrueGetWindowDC = nullptr;
CreateDCWFn TrueCreateDCW = nullptr;
DwmEnableCompositionFn TrueDwmEnableComposition = nullptr;
SetWindowsHookExWFn TrueSetWindowsHookExW = nullptr;
SetWindowsHookExAFn TrueSetWindowsHookExA = nullptr;
SendInputFn TrueSendInput = nullptr;
MouseEventFn TrueMouseEvent = nullptr;
TerminateProcessFn TrueTerminateProcess = nullptr;
PostMessageWFn TruePostMessageW = nullptr;
SendMessageWFn TrueSendMessageW = nullptr;

bool HasFlag(unsigned int flag) {
    return (static_cast<unsigned int>(g_flags) & flag) != 0;
}

bool IsInputHook(int hook) {
    return hook == WH_MOUSE_LL || hook == WH_KEYBOARD_LL || hook == WH_MOUSE ||
           hook == WH_KEYBOARD || hook == WH_CBT;
}

HWND WINAPI HookGetDesktopWindow() {
    if (HasFlag(JIYU_GUARD_ANTI_MONITOR) && g_fake_desktop != nullptr) {
        return g_fake_desktop;
    }
    return TrueGetDesktopWindow ? TrueGetDesktopWindow() : nullptr;
}

HDC WINAPI HookGetWindowDC(HWND window) {
    if (HasFlag(JIYU_GUARD_ANTI_MONITOR) && g_fake_desktop != nullptr &&
        window != nullptr && TrueGetDesktopWindow != nullptr &&
        window == TrueGetDesktopWindow()) {
        return TrueGetWindowDC ? TrueGetWindowDC(g_fake_desktop) : nullptr;
    }
    return TrueGetWindowDC ? TrueGetWindowDC(window) : nullptr;
}

HDC WINAPI HookCreateDCW(LPCWSTR driver, LPCWSTR device, LPCWSTR port,
                         const DEVMODEW* mode) {
    if (HasFlag(JIYU_GUARD_ANTI_MONITOR) && driver != nullptr &&
        _wcsicmp(driver, L"DISPLAY") == 0) {
        SetLastError(ERROR_ACCESS_DENIED);
        return nullptr;
    }
    return TrueCreateDCW ? TrueCreateDCW(driver, device, port, mode) : nullptr;
}

HRESULT WINAPI HookDwmEnableComposition(UINT action) {
    if (HasFlag(JIYU_GUARD_ANTI_MONITOR)) {
        return HRESULT_FROM_WIN32(ERROR_ACCESS_DENIED);
    }
    return TrueDwmEnableComposition ? TrueDwmEnableComposition(action)
                                    : E_NOTIMPL;
}

HHOOK WINAPI HookSetWindowsHookExW(int hook, HOOKPROC procedure,
                                   HINSTANCE module, DWORD thread) {
    if (HasFlag(JIYU_GUARD_ANTI_CONTROL) && IsInputHook(hook)) {
        SetLastError(ERROR_ACCESS_DENIED);
        return nullptr;
    }
    return TrueSetWindowsHookExW
               ? TrueSetWindowsHookExW(hook, procedure, module, thread)
               : nullptr;
}

HHOOK WINAPI HookSetWindowsHookExA(int hook, HOOKPROC procedure,
                                   HINSTANCE module, DWORD thread) {
    if (HasFlag(JIYU_GUARD_ANTI_CONTROL) && IsInputHook(hook)) {
        SetLastError(ERROR_ACCESS_DENIED);
        return nullptr;
    }
    return TrueSetWindowsHookExA
               ? TrueSetWindowsHookExA(hook, procedure, module, thread)
               : nullptr;
}

UINT WINAPI HookSendInput(UINT count, LPINPUT inputs, int size) {
    if (HasFlag(JIYU_GUARD_ANTI_CONTROL)) {
        SetLastError(ERROR_ACCESS_DENIED);
        return 0;
    }
    return TrueSendInput ? TrueSendInput(count, inputs, size) : 0;
}

void WINAPI HookMouseEvent(DWORD flags, DWORD dx, DWORD dy, DWORD data,
                           ULONG_PTR extra) {
    if (HasFlag(JIYU_GUARD_ANTI_CONTROL)) {
        return;
    }
    if (TrueMouseEvent) {
        TrueMouseEvent(flags, dx, dy, data, extra);
    }
}

BOOL WINAPI HookTerminateProcess(HANDLE process, UINT code) {
    if (HasFlag(JIYU_GUARD_BLOCK_TERMINATE) && process != nullptr &&
        process != GetCurrentProcess()) {
        SetLastError(ERROR_ACCESS_DENIED);
        return FALSE;
    }
    return TrueTerminateProcess ? TrueTerminateProcess(process, code) : FALSE;
}

bool IsCloseMessage(UINT message) {
    return message == WM_CLOSE || message == WM_DESTROY;
}

bool TargetsOtherProcess(HWND window) {
    DWORD pid = 0;
    GetWindowThreadProcessId(window, &pid);
    return pid != 0 && pid != GetCurrentProcessId();
}

BOOL WINAPI HookPostMessageW(HWND window, UINT message, WPARAM wparam,
                             LPARAM lparam) {
    if (HasFlag(JIYU_GUARD_BLOCK_CLOSE) && IsCloseMessage(message) &&
        TargetsOtherProcess(window)) {
        SetLastError(ERROR_ACCESS_DENIED);
        return FALSE;
    }
    return TruePostMessageW ? TruePostMessageW(window, message, wparam, lparam)
                            : FALSE;
}

LRESULT WINAPI HookSendMessageW(HWND window, UINT message, WPARAM wparam,
                                LPARAM lparam) {
    if (HasFlag(JIYU_GUARD_BLOCK_CLOSE) && IsCloseMessage(message) &&
        TargetsOtherProcess(window)) {
        SetLastError(ERROR_ACCESS_DENIED);
        return 0;
    }
    return TrueSendMessageW
               ? TrueSendMessageW(window, message, wparam, lparam)
               : 0;
}

void ReadPolicy() {
    wchar_t name[64] = {};
    swprintf_s(name, L"Local\\JiyuGuardPolicy_%lu", GetCurrentProcessId());
    HANDLE mapping = OpenFileMappingW(FILE_MAP_READ, FALSE, name);
    if (mapping == nullptr) {
        return;
    }
    auto* policy = static_cast<JiyuGuardPolicy*>(
        MapViewOfFile(mapping, FILE_MAP_READ, 0, 0, sizeof(JiyuGuardPolicy)));
    if (policy != nullptr) {
        if (policy->magic == JIYU_GUARD_POLICY_MAGIC &&
            policy->version == JIYU_GUARD_POLICY_VERSION) {
            InterlockedExchange(&g_flags, static_cast<LONG>(policy->flags));
        }
        UnmapViewOfFile(policy);
    }
    CloseHandle(mapping);
}

HWND CreateFakeDesktop() {
    return CreateWindowExW(0, L"STATIC", L"JiyuGuardFakeDesktop", WS_POPUP, 0,
                           0, 1, 1, nullptr, nullptr, nullptr, nullptr);
}

unsigned g_hooked = 0;

bool HookOne(PVOID* target, PVOID hook, unsigned int bit) {
    if (*target == nullptr) {
        return false;
    }
    if (!Mhook_SetHook(target, hook)) {
        return false;
    }
    g_hooked |= bit;
    return true;
}

bool HookAll() {
    TrueGetDesktopWindow =
        reinterpret_cast<GetDesktopWindowFn>(GetProcAddress(
            GetModuleHandleW(L"user32.dll"), "GetDesktopWindow"));
    TrueGetWindowDC = reinterpret_cast<GetWindowDCFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "GetWindowDC"));
    TrueCreateDCW = reinterpret_cast<CreateDCWFn>(
        GetProcAddress(GetModuleHandleW(L"gdi32.dll"), "CreateDCW"));
    TrueSetWindowsHookExW = reinterpret_cast<SetWindowsHookExWFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "SetWindowsHookExW"));
    TrueSetWindowsHookExA = reinterpret_cast<SetWindowsHookExAFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "SetWindowsHookExA"));
    TrueSendInput = reinterpret_cast<SendInputFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "SendInput"));
    TrueMouseEvent = reinterpret_cast<MouseEventFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "mouse_event"));
    TrueTerminateProcess = reinterpret_cast<TerminateProcessFn>(
        GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "TerminateProcess"));
    TruePostMessageW = reinterpret_cast<PostMessageWFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "PostMessageW"));
    TrueSendMessageW = reinterpret_cast<SendMessageWFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "SendMessageW"));

    HMODULE dwm = LoadLibraryW(L"dwmapi.dll");
    if (dwm != nullptr) {
        TrueDwmEnableComposition =
            reinterpret_cast<DwmEnableCompositionFn>(
                GetProcAddress(dwm, "DwmEnableComposition"));
    }

    bool ok = true;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueGetDesktopWindow),
                 reinterpret_cast<PVOID>(HookGetDesktopWindow), 1u << 0) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueGetWindowDC),
                 reinterpret_cast<PVOID>(HookGetWindowDC), 1u << 1) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueCreateDCW),
                 reinterpret_cast<PVOID>(HookCreateDCW), 1u << 2) && ok;
    if (TrueDwmEnableComposition != nullptr) {
        // 新版 Windows 可能已移除 DwmEnableComposition，缺这一项不算失败。
        HookOne(reinterpret_cast<PVOID*>(&TrueDwmEnableComposition),
                reinterpret_cast<PVOID>(HookDwmEnableComposition), 1u << 3);
    }
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueSetWindowsHookExW),
                 reinterpret_cast<PVOID>(HookSetWindowsHookExW), 1u << 4) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueSetWindowsHookExA),
                 reinterpret_cast<PVOID>(HookSetWindowsHookExA), 1u << 5) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueSendInput),
                 reinterpret_cast<PVOID>(HookSendInput), 1u << 6) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueMouseEvent),
                 reinterpret_cast<PVOID>(HookMouseEvent), 1u << 7) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueTerminateProcess),
                 reinterpret_cast<PVOID>(HookTerminateProcess), 1u << 8) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TruePostMessageW),
                 reinterpret_cast<PVOID>(HookPostMessageW), 1u << 9) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueSendMessageW),
                 reinterpret_cast<PVOID>(HookSendMessageW), 1u << 10) && ok;
    return ok;
}

void UnhookAll() {
    if ((g_hooked & (1u << 0)) != 0) {
        Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueGetDesktopWindow));
    }
    if ((g_hooked & (1u << 1)) != 0) {
        Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueGetWindowDC));
    }
    if ((g_hooked & (1u << 2)) != 0) {
        Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueCreateDCW));
    }
    if ((g_hooked & (1u << 3)) != 0) {
        Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueDwmEnableComposition));
    }
    if ((g_hooked & (1u << 4)) != 0) {
        Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueSetWindowsHookExW));
    }
    if ((g_hooked & (1u << 5)) != 0) {
        Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueSetWindowsHookExA));
    }
    if ((g_hooked & (1u << 6)) != 0) {
        Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueSendInput));
    }
    if ((g_hooked & (1u << 7)) != 0) {
        Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueMouseEvent));
    }
    if ((g_hooked & (1u << 8)) != 0) {
        Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueTerminateProcess));
    }
    if ((g_hooked & (1u << 9)) != 0) {
        Mhook_Unhook(reinterpret_cast<PVOID*>(&TruePostMessageW));
    }
    if ((g_hooked & (1u << 10)) != 0) {
        Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueSendMessageW));
    }
    g_hooked = 0;
}

}  // namespace

extern "C" __declspec(dllexport) const char* JiyuGuardVersion() {
    return "1.0.0";
}

extern "C" __declspec(dllexport) BOOL JiyuGuardInstall() {
    if (g_installed) {
        ReadPolicy();
        return TRUE;
    }
    ReadPolicy();
    g_fake_desktop = CreateFakeDesktop();
    g_installed = HookAll();
    return g_installed ? TRUE : FALSE;
}

extern "C" __declspec(dllexport) void JiyuGuardUninstall() {
    UnhookAll();
    g_installed = false;
    if (g_fake_desktop != nullptr) {
        DestroyWindow(g_fake_desktop);
        g_fake_desktop = nullptr;
    }
}

extern "C" __declspec(dllexport) void JiyuGuardRefresh() {
    ReadPolicy();
}

// 仅供本机自测夹具使用：没有共享内存时也能切换策略位。
extern "C" __declspec(dllexport) void JiyuGuardSetPolicy(unsigned int flags) {
    InterlockedExchange(&g_flags, static_cast<LONG>(flags));
}

extern "C" __declspec(dllexport) unsigned int JiyuGuardGetPolicy() {
    return static_cast<unsigned int>(g_flags);
}

extern "C" __declspec(dllexport) unsigned int JiyuGuardHookMask() {
    return g_hooked;
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID reserved) {
    (void)module;
    (void)reserved;
    if (reason == DLL_PROCESS_DETACH) {
        JiyuGuardUninstall();
    }
    return TRUE;
}
