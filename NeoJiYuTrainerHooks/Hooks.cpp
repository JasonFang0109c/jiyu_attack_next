// 课堂防护：注入学生端后按上游 JiYuTrainerHooks 的判定逻辑拦截监视、控制、
// 关窗、关机与杀进程，并在被控进程内提供确认对话框与运行白名单。
//
// 上游参考：JiYuTrainer/JiYuTrainerHooks/JiYuTrainerHooks.cpp（MIT）。
// 这里只保留 Win10+ 可用的用户态钩子，不加载驱动、不改系统设置。
#include <windows.h>

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cwchar>
#include <cwctype>
#include <initializer_list>
#include <list>
#include <new>
#include <string>
#include <vector>

#ifndef DWM_EC_DISABLECOMPOSITION
#define DWM_EC_DISABLECOMPOSITION 0
#endif

#include "Menu.h"
#include "Mhook/mhook.h"
#include "Policy.h"
#include "Remote.h"

namespace {

// ---------------------------------------------------------------------------
// 全局状态
// ---------------------------------------------------------------------------

volatile LONG g_flags = 0;
volatile LONG g_allow_all_session = 0;
volatile LONG g_locked = 0;
volatile LONG g_is_gb_founded = 0;
HWND g_fake_desktop = nullptr;
bool g_installed = false;
HMODULE g_module = nullptr;
DWORD g_current_pid = 0;

int g_screen_width = 0;
int g_screen_height = 0;

CRITICAL_SECTION g_window_lock;
bool g_window_lock_ready = false;
std::list<HWND> g_windows;
std::list<HWND> g_can_size_windows;
HANDLE g_scan_thread = nullptr;
volatile LONG g_scan_stop = 0;

CRITICAL_SECTION g_whitelist_lock;
bool g_whitelist_lock_ready = false;
std::vector<std::wstring> g_whitelist;

HANDLE g_device_tdkeybd = INVALID_HANDLE_VALUE;
HANDLE g_device_tdprochook = INVALID_HANDLE_VALUE;
HANDLE g_device_tdnetfilter = INVALID_HANDLE_VALUE;

using GetDesktopWindowFn = HWND(WINAPI*)();
using GetWindowDCFn = HDC(WINAPI*)(HWND);
using CreateDCWFn = HDC(WINAPI*)(LPCWSTR, LPCWSTR, LPCWSTR, const DEVMODEW*);
using DwmEnableCompositionFn = HRESULT(WINAPI*)(UINT);
using SetWindowsHookExWFn = HHOOK(WINAPI*)(int, HOOKPROC, HINSTANCE, DWORD);
using SetWindowsHookExAFn = HHOOK(WINAPI*)(int, HOOKPROC, HINSTANCE, DWORD);
using CallNextHookExFn = LRESULT(WINAPI*)(HHOOK, int, WPARAM, LPARAM);
using UnhookWindowsHookExFn = BOOL(WINAPI*)(HHOOK);
using SendInputFn = UINT(WINAPI*)(UINT, LPINPUT, int);
using MouseEventFn = void(WINAPI*)(DWORD, DWORD, DWORD, DWORD, ULONG_PTR);
using TerminateProcessFn = BOOL(WINAPI*)(HANDLE, UINT);
using PostMessageWFn = BOOL(WINAPI*)(HWND, UINT, WPARAM, LPARAM);
using SendMessageWFn = LRESULT(WINAPI*)(HWND, UINT, WPARAM, LPARAM);
using CreateProcessWFn = BOOL(WINAPI*)(
    LPCWSTR, LPWSTR, LPSECURITY_ATTRIBUTES, LPSECURITY_ATTRIBUTES, BOOL, DWORD,
    LPVOID, LPCWSTR, LPSTARTUPINFOW, LPPROCESS_INFORMATION);
using CreateProcessAFn = BOOL(WINAPI*)(
    LPCSTR, LPSTR, LPSECURITY_ATTRIBUTES, LPSECURITY_ATTRIBUTES, BOOL, DWORD,
    LPVOID, LPCSTR, LPSTARTUPINFOA, LPPROCESS_INFORMATION);
using WinExecFn = UINT(WINAPI*)(LPCSTR, UINT);
using SetForegroundWindowFn = BOOL(WINAPI*)(HWND);
using SetWindowPosFn = BOOL(WINAPI*)(HWND, HWND, int, int, int, int, UINT);
using DeferWindowPosFn = HDWP(WINAPI*)(HDWP, HWND, HWND, int, int, int, int, UINT);
using MoveWindowFn = BOOL(WINAPI*)(HWND, int, int, int, int, BOOL);
using ShowWindowFn = BOOL(WINAPI*)(HWND, int);
using SetWindowLongWFn = LONG(WINAPI*)(HWND, int, LONG);
using SetWindowLongAFn = LONG(WINAPI*)(HWND, int, LONG);
using SetClassLongWFn = DWORD(WINAPI*)(HWND, int, LONG);
using SetClassLongAFn = DWORD(WINAPI*)(HWND, int, LONG);
using BringWindowToTopFn = BOOL(WINAPI*)(HWND);
using CreateFileWFn = HANDLE(WINAPI*)(LPCWSTR, DWORD, DWORD, LPSECURITY_ATTRIBUTES,
                                      DWORD, DWORD, HANDLE);
using CreateFileAFn = HANDLE(WINAPI*)(LPCSTR, DWORD, DWORD, LPSECURITY_ATTRIBUTES,
                                      DWORD, DWORD, HANDLE);
using DeviceIoControlFn = BOOL(WINAPI*)(HANDLE, DWORD, LPVOID, DWORD, LPVOID,
                                        DWORD, LPDWORD, LPOVERLAPPED);
using ExitWindowsExFn = BOOL(WINAPI*)(UINT, DWORD);
using GetForegroundWindowFn = HWND(WINAPI*)();
using EnableMenuItemFn = BOOL(WINAPI*)(HMENU, UINT, UINT);
using OpenInputDesktopFn = HDESK(WINAPI*)(DWORD, BOOL, ACCESS_MASK);
using OpenDesktopAFn = HDESK(WINAPI*)(LPCSTR, DWORD, BOOL, ACCESS_MASK);
using ChangeDisplaySettingsWFn = LONG(WINAPI*)(DEVMODEW*, DWORD);
using EncodeToJPEGBufferFn = int(__cdecl*)(int, int, int, int, int, DWORD*, int, int, int);
using FilterConnectCommunicationPortFn = HRESULT(WINAPI*)(
    LPCWSTR, DWORD, LPCVOID, WORD, LPSECURITY_ATTRIBUTES, HANDLE*);

GetDesktopWindowFn TrueGetDesktopWindow = nullptr;
GetWindowDCFn TrueGetWindowDC = nullptr;
CreateDCWFn TrueCreateDCW = nullptr;
DwmEnableCompositionFn TrueDwmEnableComposition = nullptr;
SetWindowsHookExWFn TrueSetWindowsHookExW = nullptr;
SetWindowsHookExAFn TrueSetWindowsHookExA = nullptr;
CallNextHookExFn TrueCallNextHookEx = nullptr;
UnhookWindowsHookExFn TrueUnhookWindowsHookEx = nullptr;
SendInputFn TrueSendInput = nullptr;
MouseEventFn TrueMouseEvent = nullptr;
TerminateProcessFn TrueTerminateProcess = nullptr;
PostMessageWFn TruePostMessageW = nullptr;
SendMessageWFn TrueSendMessageW = nullptr;
CreateProcessWFn TrueCreateProcessW = nullptr;
CreateProcessAFn TrueCreateProcessA = nullptr;
WinExecFn TrueWinExec = nullptr;
SetForegroundWindowFn TrueSetForegroundWindow = nullptr;
SetWindowPosFn TrueSetWindowPos = nullptr;
DeferWindowPosFn TrueDeferWindowPos = nullptr;
MoveWindowFn TrueMoveWindow = nullptr;
ShowWindowFn TrueShowWindow = nullptr;
SetWindowLongWFn TrueSetWindowLongW = nullptr;
SetWindowLongAFn TrueSetWindowLongA = nullptr;
SetClassLongWFn TrueSetClassLongW = nullptr;
SetClassLongAFn TrueSetClassLongA = nullptr;
BringWindowToTopFn TrueBringWindowToTop = nullptr;
CreateFileWFn TrueCreateFileW = nullptr;
CreateFileAFn TrueCreateFileA = nullptr;
DeviceIoControlFn TrueDeviceIoControl = nullptr;
ExitWindowsExFn TrueExitWindowsEx = nullptr;
GetForegroundWindowFn TrueGetForegroundWindow = nullptr;
EnableMenuItemFn TrueEnableMenuItem = nullptr;
OpenInputDesktopFn TrueOpenInputDesktop = nullptr;
OpenDesktopAFn TrueOpenDesktopA = nullptr;
ChangeDisplaySettingsWFn TrueChangeDisplaySettingsW = nullptr;
EncodeToJPEGBufferFn TrueEncodeToJPEGBuffer = nullptr;
FilterConnectCommunicationPortFn TrueFilterConnectCommunicationPort = nullptr;

HMODULE g_libjpeg_module = nullptr;
HMODULE g_fltlib_module = nullptr;

HHOOK g_mouse_hook = nullptr;
HHOOK g_keyboard_hook = nullptr;
HOOKPROC g_saved_mouse_proc = nullptr;
HOOKPROC g_saved_keyboard_proc = nullptr;

HANDLE g_remote_mapping = nullptr;
JiyuGuardRemoteHeader* g_remote_header = nullptr;
JiyuGuardRemoteEntry* g_remote_entries = nullptr;

// 伪句柄：极域拿到的不是真实 HHOOK，真正 hook 由本 DLL 持有。
const ULONG_PTR kPseudoMouseHook = 0x0001;
const ULONG_PTR kPseudoKeyboardHook = 0x0002;

// ---------------------------------------------------------------------------
// 基础工具
// ---------------------------------------------------------------------------

bool HasFlag(unsigned int flag) {
    return (static_cast<unsigned int>(g_flags) & flag) != 0;
}

bool SessionAllowsAll() {
    return InterlockedCompareExchange(&g_allow_all_session, 0, 0) != 0;
}

std::wstring ToLowerString(const std::wstring& text) {
    std::wstring result(text);
    for (wchar_t& ch : result) {
        ch = static_cast<wchar_t>(towlower(ch));
    }
    return result;
}

bool ContainsText(const std::wstring& text, const wchar_t* needle) {
    return text.find(needle) != std::wstring::npos;
}

bool EqualsNoCase(const wchar_t* left, const wchar_t* right) {
    return left != nullptr && right != nullptr && _wcsicmp(left, right) == 0;
}

std::wstring TrimString(const std::wstring& text) {
    const size_t first = text.find_first_not_of(L" \t\r\n");
    if (first == std::wstring::npos) {
        return std::wstring();
    }
    const size_t last = text.find_last_not_of(L" \t\r\n");
    return text.substr(first, last - first + 1);
}

int ScreenWidth() {
    if (g_screen_width <= 0) {
        g_screen_width = GetSystemMetrics(SM_CXSCREEN);
    }
    return g_screen_width;
}

int ScreenHeight() {
    if (g_screen_height <= 0) {
        g_screen_height = GetSystemMetrics(SM_CYSCREEN);
    }
    return g_screen_height;
}

std::wstring GetWindowTitle(HWND window) {
    if (window == nullptr || !IsWindow(window)) {
        return std::wstring();
    }
    if (GetWindowTextLengthW(window) <= 0) {
        return std::wstring();
    }
    wchar_t buffer[512] = {};
    DWORD_PTR copied = 0;
    SendMessageTimeoutW(window, WM_GETTEXT,
                        static_cast<WPARAM>(_countof(buffer)),
                        reinterpret_cast<LPARAM>(buffer),
                        SMTO_ABORTIFHUNG | SMTO_BLOCK, 100, &copied);
    return std::wstring(buffer);
}

bool IsBroadcastTitle(const std::wstring& raw_title) {
    if (raw_title.empty()) {
        return false;
    }
    const std::wstring title = ToLowerString(raw_title);
    return ContainsText(title, L"广播") || ContainsText(title, L"演示") ||
           ContainsText(title, L"共享") || ContainsText(title, L"共享屏幕") ||
           _wcsicmp(raw_title.c_str(), L"屏幕演播室窗口") == 0;
}

bool IsBlackScreenTitle(const std::wstring& raw_title) {
    return _wcsicmp(raw_title.c_str(), L"BlackScreen Window") == 0;
}

bool WindowIsBroadcastOrBlack(HWND window) {
    const std::wstring title = GetWindowTitle(window);
    if (title.empty()) {
        return false;
    }
    return IsBroadcastTitle(title) || IsBlackScreenTitle(title);
}

void SetLockState(HWND window, bool locked) {
    if (window == nullptr) {
        return;
    }
    if (!WindowIsBroadcastOrBlack(window)) {
        return;
    }
    if (locked) {
        if (InterlockedCompareExchange(&g_locked, 1, 0) == 0) {
            if (IsBroadcastTitle(GetWindowTitle(window))) {
                InterlockedExchange(&g_is_gb_founded, 1);
            }
        }
    } else {
        if (InterlockedCompareExchange(&g_locked, 0, 1) == 1) {
            if (IsBroadcastTitle(GetWindowTitle(window))) {
                InterlockedExchange(&g_is_gb_founded, 0);
            }
        }
    }
}

// ---------------------------------------------------------------------------
// 窗口扫描：EnumWindows 只遍历顶层窗口，广播子窗口需要 EnumChildWindows 补上。
// ---------------------------------------------------------------------------

bool IsTrackedWindow(HWND window) {
    if (!g_window_lock_ready) {
        return false;
    }
    EnterCriticalSection(&g_window_lock);
    const bool found =
        std::find(g_windows.begin(), g_windows.end(), window) != g_windows.end();
    LeaveCriticalSection(&g_window_lock);
    return found;
}

bool IsCanSizeWindow(HWND window) {
    if (!g_window_lock_ready) {
        return false;
    }
    EnterCriticalSection(&g_window_lock);
    const bool found = std::find(g_can_size_windows.begin(),
                                 g_can_size_windows.end(),
                                 window) != g_can_size_windows.end();
    LeaveCriticalSection(&g_window_lock);
    return found;
}

void AddTrackedWindow(HWND window) {
    if (window == nullptr || !g_window_lock_ready) {
        return;
    }
    EnterCriticalSection(&g_window_lock);
    if (std::find(g_windows.begin(), g_windows.end(), window) == g_windows.end()) {
        g_windows.push_back(window);
    }
    LeaveCriticalSection(&g_window_lock);
}

void AddCanSizeWindow(HWND window) {
    if (window == nullptr || !g_window_lock_ready) {
        return;
    }
    EnterCriticalSection(&g_window_lock);
    if (std::find(g_can_size_windows.begin(), g_can_size_windows.end(), window) ==
        g_can_size_windows.end()) {
        g_can_size_windows.push_back(window);
    }
    LeaveCriticalSection(&g_window_lock);
}

void RemoveCanSizeWindow(HWND window) {
    if (!g_window_lock_ready) {
        return;
    }
    EnterCriticalSection(&g_window_lock);
    g_can_size_windows.remove(window);
    LeaveCriticalSection(&g_window_lock);
}

bool IsIllegalWindow(HWND window) {
    // 与上游 VIsInIllegalWindows 一致，只查扫描线程维护的名单；窗口标题
    // 读取要走 SendMessageTimeoutW，不能在高频的窗口定位路径里反复做。
    return IsTrackedWindow(window);
}

BOOL CALLBACK CollectChildWindow(HWND window, LPARAM param) {
    auto* found = reinterpret_cast<std::vector<HWND>*>(param);
    if (WindowIsBroadcastOrBlack(window)) {
        found->push_back(window);
    }
    return TRUE;
}

BOOL CALLBACK CollectTopWindow(HWND window, LPARAM param) {
    DWORD process_id = 0;
    GetWindowThreadProcessId(window, &process_id);
    if (process_id != g_current_pid) {
        return TRUE;
    }
    auto* found = reinterpret_cast<std::vector<HWND>*>(param);
    if (WindowIsBroadcastOrBlack(window)) {
        found->push_back(window);
    }
    EnumChildWindows(window, CollectChildWindow, param);
    return TRUE;
}

void RefreshTrackedWindows() {
    if (!g_window_lock_ready) {
        return;
    }
    std::vector<HWND> found;
    EnumWindows(CollectTopWindow, reinterpret_cast<LPARAM>(&found));

    EnterCriticalSection(&g_window_lock);
    for (auto it = g_windows.begin(); it != g_windows.end();) {
        if (!IsWindow(*it)) {
            it = g_windows.erase(it);
        } else {
            ++it;
        }
    }
    for (auto it = g_can_size_windows.begin(); it != g_can_size_windows.end();) {
        if (!IsWindow(*it)) {
            it = g_can_size_windows.erase(it);
        } else {
            ++it;
        }
    }
    for (HWND window : found) {
        if (std::find(g_windows.begin(), g_windows.end(), window) == g_windows.end()) {
            g_windows.push_back(window);
        }
        // 对应上游窗口子类里的 WM_SHOWWINDOW(FALSE)：隐藏过的广播窗口进入
        // “可改尺寸”名单，下一次全屏定位时去掉 SWP_NOZORDER 并补 WM_SIZE。
        if (!IsWindowVisible(window)) {
            if (std::find(g_can_size_windows.begin(), g_can_size_windows.end(),
                          window) == g_can_size_windows.end()) {
                g_can_size_windows.push_back(window);
            }
        } else {
            g_can_size_windows.remove(window);
        }
    }
    LeaveCriticalSection(&g_window_lock);
}

DWORD WINAPI WindowScanThread(LPVOID parameter) {
    (void)parameter;
    while (InterlockedCompareExchange(&g_scan_stop, 0, 0) == 0) {
        g_screen_width = GetSystemMetrics(SM_CXSCREEN);
        g_screen_height = GetSystemMetrics(SM_CYSCREEN);
        RefreshTrackedWindows();
        for (int tick = 0; tick < 7; ++tick) {
            if (InterlockedCompareExchange(&g_scan_stop, 0, 0) != 0) {
                break;
            }
            Sleep(100);
        }
    }
    return 0;
}

// ---------------------------------------------------------------------------
// 运行白名单：DLL 同目录 JiYuKillerOpWhiteList.txt，UTF-8，每行一条。
// ---------------------------------------------------------------------------

std::wstring ModuleDirectory() {
    wchar_t path[MAX_PATH] = {};
    HMODULE module = g_module != nullptr ? g_module : GetModuleHandleW(nullptr);
    const DWORD length = GetModuleFileNameW(module, path, _countof(path));
    std::wstring directory(path, length);
    const size_t slash = directory.find_last_of(L"\\/");
    if (slash != std::wstring::npos) {
        directory.erase(slash);
    }
    return directory;
}

std::wstring WhitelistPath() {
    return ModuleDirectory() + L"\\JiYuKillerOpWhiteList.txt";
}

std::string ReadAllBytes(const std::wstring& path) {
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ,
                              FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr,
                              OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        return std::string();
    }
    LARGE_INTEGER size = {};
    if (!GetFileSizeEx(file, &size) || size.QuadPart <= 0 ||
        size.QuadPart > 4 * 1024 * 1024) {
        CloseHandle(file);
        return std::string();
    }
    std::string bytes(static_cast<size_t>(size.QuadPart), '\0');
    DWORD read = 0;
    if (!ReadFile(file, &bytes[0], static_cast<DWORD>(bytes.size()), &read, nullptr)) {
        CloseHandle(file);
        return std::string();
    }
    bytes.resize(read);
    CloseHandle(file);
    return bytes;
}

std::wstring Utf8ToWide(const std::string& bytes) {
    if (bytes.empty()) {
        return std::wstring();
    }
    int length = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, bytes.data(),
                                     static_cast<int>(bytes.size()), nullptr, 0);
    UINT code_page = CP_UTF8;
    DWORD flags = MB_ERR_INVALID_CHARS;
    if (length <= 0) {
        code_page = CP_ACP;
        flags = 0;
        length = MultiByteToWideChar(code_page, flags, bytes.data(),
                                     static_cast<int>(bytes.size()), nullptr, 0);
    }
    if (length <= 0) {
        return std::wstring();
    }
    std::wstring text(static_cast<size_t>(length), L'\0');
    MultiByteToWideChar(code_page, flags, bytes.data(),
                        static_cast<int>(bytes.size()), &text[0], length);
    return text;
}

std::string WideToUtf8(const std::wstring& text) {
    if (text.empty()) {
        return std::string();
    }
    const int length = WideCharToMultiByte(CP_UTF8, 0, text.data(),
                                           static_cast<int>(text.size()), nullptr,
                                           0, nullptr, nullptr);
    if (length <= 0) {
        return std::string();
    }
    std::string bytes(static_cast<size_t>(length), '\0');
    WideCharToMultiByte(CP_UTF8, 0, text.data(), static_cast<int>(text.size()),
                        &bytes[0], length, nullptr, nullptr);
    return bytes;
}

std::wstring NormalizePath(const std::wstring& path) {
    if (path.empty()) {
        return std::wstring();
    }
    wchar_t buffer[MAX_PATH * 2] = {};
    const DWORD length = GetFullPathNameW(path.c_str(), _countof(buffer), buffer,
                                          nullptr);
    if (length > 0 && length < _countof(buffer)) {
        return std::wstring(buffer, length);
    }
    return path;
}

void LoadWhitelist() {
    if (!g_whitelist_lock_ready) {
        return;
    }
    std::vector<std::wstring> loaded;
    const std::string bytes = ReadAllBytes(WhitelistPath());
    std::wstring text = Utf8ToWide(bytes);
    if (!text.empty() && text[0] == 0xFEFF) {
        text.erase(0, 1);
    }
    size_t start = 0;
    while (start <= text.size()) {
        const size_t end = text.find(L'\n', start);
        const std::wstring line = TrimString(
            text.substr(start, end == std::wstring::npos ? std::wstring::npos
                                                         : end - start));
        if (!line.empty() && line[0] != L'#') {
            const std::wstring lower = ToLowerString(line);
            if (std::find(loaded.begin(), loaded.end(), lower) == loaded.end()) {
                loaded.push_back(lower);
            }
        }
        if (end == std::wstring::npos) {
            break;
        }
        start = end + 1;
    }
    EnterCriticalSection(&g_whitelist_lock);
    g_whitelist.swap(loaded);
    LeaveCriticalSection(&g_whitelist_lock);
}

bool IsWhitelisted(const std::wstring& path) {
    if (!g_whitelist_lock_ready || path.empty()) {
        return false;
    }
    const std::wstring normalized = ToLowerString(NormalizePath(path));
    const std::wstring raw = ToLowerString(path);
    EnterCriticalSection(&g_whitelist_lock);
    bool found = false;
    for (const std::wstring& item : g_whitelist) {
        if (item == normalized || item == raw) {
            found = true;
            break;
        }
    }
    LeaveCriticalSection(&g_whitelist_lock);
    return found;
}

void AddWhitelist(const std::wstring& path) {
    if (!g_whitelist_lock_ready || path.empty()) {
        return;
    }
    const std::wstring normalized = ToLowerString(NormalizePath(path));
    if (normalized.empty()) {
        return;
    }
    EnterCriticalSection(&g_whitelist_lock);
    const bool exists =
        std::find(g_whitelist.begin(), g_whitelist.end(), normalized) !=
        g_whitelist.end();
    if (!exists) {
        g_whitelist.push_back(normalized);
    }
    LeaveCriticalSection(&g_whitelist_lock);
    if (exists) {
        return;
    }

    const std::wstring file_path = WhitelistPath();
    HANDLE file = CreateFileW(file_path.c_str(), FILE_APPEND_DATA,
                              FILE_SHARE_READ, nullptr, OPEN_ALWAYS,
                              FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        return;
    }
    const std::string line = WideToUtf8(normalized) + "\r\n";
    DWORD written = 0;
    WriteFile(file, line.data(), static_cast<DWORD>(line.size()), &written, nullptr);
    CloseHandle(file);
}

// ---------------------------------------------------------------------------
// 被控进程内确认对话框：独立线程 + 手搭窗口 + 单一队列。
// ---------------------------------------------------------------------------

enum ConfirmDecision {
    kConfirmDeny = 0,
    kConfirmAllow = 1,
    kConfirmAllowAll = 2,
    kConfirmUnavailable = 3,
};

struct ConfirmResult {
    HANDLE done;
    volatile LONG state;     // 0 等待，2 已完成
    volatile LONG decision;  // ConfirmDecision
};

struct ConfirmRequest {
    wchar_t path[512];
    wchar_t params[1024];
    ConfirmResult* result;
    ConfirmRequest* next;
};

const wchar_t kConfirmClass[] = L"JiyuGuardConfirmWindow";
const int kConfirmButtonAllow = 1001;
const int kConfirmButtonDeny = 1002;
const int kConfirmButtonAllowAll = 1003;
const int kConfirmCheckSession = 1004;

CRITICAL_SECTION g_confirm_lock;
bool g_confirm_lock_ready = false;
HANDLE g_confirm_event = nullptr;
HANDLE g_confirm_thread = nullptr;
DWORD g_confirm_thread_id = 0;
volatile LONG g_confirm_stop = 0;
ConfirmRequest* g_confirm_head = nullptr;
ConfirmRequest* g_confirm_tail = nullptr;
ConfirmRequest* g_confirm_current = nullptr;
HWND g_confirm_hwnd = nullptr;
bool g_confirm_finalized = false;
bool g_confirm_class_registered = false;

void SetControlFont(HWND control) {
    SendMessageW(control, WM_SETFONT,
                 reinterpret_cast<WPARAM>(GetStockObject(DEFAULT_GUI_FONT)), TRUE);
}

void CompleteConfirmRequest(ConfirmRequest* request, ConfirmDecision decision) {
    if (request == nullptr || request->result == nullptr) {
        return;
    }
    request->result->decision = decision;
    InterlockedExchange(&request->result->state, 2);
    SetEvent(request->result->done);
}

void FinalizeConfirm(ConfirmDecision decision) {
    if (g_confirm_current == nullptr || g_confirm_finalized) {
        return;
    }
    g_confirm_finalized = true;
    ConfirmRequest* request = g_confirm_current;
    if (decision != kConfirmDeny) {
        if (IsDlgButtonChecked(g_confirm_hwnd, kConfirmCheckSession) == BST_CHECKED) {
            InterlockedExchange(&g_allow_all_session, 1);
        }
        if (decision == kConfirmAllowAll) {
            AddWhitelist(request->path);
        }
    }
    CompleteConfirmRequest(request, decision);
    if (g_confirm_hwnd != nullptr) {
        DestroyWindow(g_confirm_hwnd);
    }
}

void LayoutConfirmControls(HWND window) {
    const int margin = 18;
    const int width = 590;
    HWND path = CreateWindowExW(0, L"STATIC", L"", WS_CHILD | WS_VISIBLE | SS_LEFT,
                                margin, 44, width, 34, window, nullptr,
                                g_module, nullptr);
    HWND params = CreateWindowExW(0, L"STATIC", L"", WS_CHILD | WS_VISIBLE | SS_LEFT,
                                  margin, 82, width, 54, window, nullptr,
                                  g_module, nullptr);
    HWND hint = CreateWindowExW(0, L"STATIC",
                                L"程序路径：", WS_CHILD | WS_VISIBLE | SS_LEFT,
                                margin, 22, width, 20, window, nullptr,
                                g_module, nullptr);
    HWND param_hint = CreateWindowExW(0, L"STATIC",
                                      L"启动参数：", WS_CHILD | WS_VISIBLE | SS_LEFT,
                                      margin, 66, width, 18, window, nullptr,
                                      g_module, nullptr);
    HWND session = CreateWindowExW(0, L"BUTTON", L"本次运行期间全部允许",
                                   WS_CHILD | WS_VISIBLE | BS_AUTOCHECKBOX,
                                   margin, 148, 300, 24, window,
                                   reinterpret_cast<HMENU>(
                                       static_cast<INT_PTR>(kConfirmCheckSession)),
                                   g_module, nullptr);
    HWND allow = CreateWindowExW(0, L"BUTTON", L"允许本次",
                                 WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                                 292, 190, 90, 32, window,
                                 reinterpret_cast<HMENU>(
                                     static_cast<INT_PTR>(kConfirmButtonAllow)),
                                 g_module, nullptr);
    HWND deny = CreateWindowExW(0, L"BUTTON", L"拒绝",
                                WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                                392, 190, 90, 32, window,
                                reinterpret_cast<HMENU>(
                                    static_cast<INT_PTR>(kConfirmButtonDeny)),
                                g_module, nullptr);
    HWND allow_all = CreateWindowExW(0, L"BUTTON", L"允许全部运行",
                                     WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                                     492, 190, 100, 32, window,
                                     reinterpret_cast<HMENU>(
                                         static_cast<INT_PTR>(kConfirmButtonAllowAll)),
                                     g_module, nullptr);

    for (HWND control : {hint, param_hint, path, params, session, allow, deny,
                         allow_all}) {
        SetControlFont(control);
    }
    if (g_confirm_current != nullptr) {
        SetWindowTextW(path, g_confirm_current->path);
        SetWindowTextW(params, g_confirm_current->params);
    }
}

LRESULT CALLBACK ConfirmWindowProc(HWND window, UINT message, WPARAM wparam,
                                   LPARAM lparam) {
    switch (message) {
    case WM_CREATE:
        g_confirm_hwnd = window;
        LayoutConfirmControls(window);
        return 0;
    case WM_COMMAND:
        switch (LOWORD(wparam)) {
        case kConfirmButtonAllow:
            FinalizeConfirm(kConfirmAllow);
            return 0;
        case kConfirmButtonDeny:
            FinalizeConfirm(kConfirmDeny);
            return 0;
        case kConfirmButtonAllowAll:
            FinalizeConfirm(kConfirmAllowAll);
            return 0;
        default:
            break;
        }
        return 0;
    case WM_CLOSE:
        FinalizeConfirm(kConfirmDeny);
        return 0;
    case WM_DESTROY:
        g_confirm_hwnd = nullptr;
        PostQuitMessage(0);
        return 0;
    default:
        break;
    }
    return DefWindowProcW(window, message, wparam, lparam);
}

bool RegisterConfirmClass() {
    if (g_confirm_class_registered) {
        return true;
    }
    WNDCLASSEXW window_class = {};
    window_class.cbSize = sizeof(window_class);
    window_class.lpfnWndProc = ConfirmWindowProc;
    window_class.hInstance = g_module;
    window_class.hCursor = LoadCursorW(nullptr, MAKEINTRESOURCEW(32512));
    window_class.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
    window_class.lpszClassName = kConfirmClass;
    if (RegisterClassExW(&window_class) == 0 &&
        GetLastError() != ERROR_CLASS_ALREADY_EXISTS) {
        return false;
    }
    g_confirm_class_registered = true;
    return true;
}

void PushConfirmRequest(ConfirmRequest* request) {
    EnterCriticalSection(&g_confirm_lock);
    request->next = nullptr;
    if (g_confirm_tail != nullptr) {
        g_confirm_tail->next = request;
    } else {
        g_confirm_head = request;
    }
    g_confirm_tail = request;
    LeaveCriticalSection(&g_confirm_lock);
    SetEvent(g_confirm_event);
}

ConfirmRequest* PopConfirmRequest() {
    EnterCriticalSection(&g_confirm_lock);
    ConfirmRequest* request = g_confirm_head;
    if (request != nullptr) {
        g_confirm_head = request->next;
        if (g_confirm_head == nullptr) {
            g_confirm_tail = nullptr;
        }
        request->next = nullptr;
    }
    LeaveCriticalSection(&g_confirm_lock);
    return request;
}

void DrainConfirmQueue() {
    for (;;) {
        ConfirmRequest* request = PopConfirmRequest();
        if (request == nullptr) {
            break;
        }
        CompleteConfirmRequest(request, kConfirmDeny);
        delete request;
    }
}

DWORD WINAPI ConfirmThreadProc(LPVOID parameter) {
    (void)parameter;
    while (InterlockedCompareExchange(&g_confirm_stop, 0, 0) == 0) {
        WaitForSingleObject(g_confirm_event, 100);
        if (InterlockedCompareExchange(&g_confirm_stop, 0, 0) != 0) {
            break;
        }
        ConfirmRequest* request = PopConfirmRequest();
        if (request == nullptr) {
            continue;
        }
        g_confirm_current = request;
        g_confirm_finalized = false;
        if (!RegisterConfirmClass()) {
            // 窗口类注册失败通常意味着当前会话没有可用桌面；交给远程通道兜底。
            CompleteConfirmRequest(request, kConfirmUnavailable);
            delete request;
            g_confirm_current = nullptr;
            continue;
        }

        const int width = 626;
        const int height = 280;
        const int x = (ScreenWidth() - width) / 2;
        const int y = (ScreenHeight() - height) / 2;
        HWND window = CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TOOLWINDOW, kConfirmClass,
            L"JiYu Guard 防护警告",
            WS_POPUP | WS_CAPTION | WS_SYSMENU, x, y, width, height, nullptr,
            nullptr, g_module, nullptr);
        if (window == nullptr) {
            CompleteConfirmRequest(request, kConfirmUnavailable);
            delete request;
            g_confirm_current = nullptr;
            continue;
        }

        ShowWindow(window, SW_SHOWNORMAL);
        SetWindowPos(window, HWND_TOPMOST, 0, 0, 0, 0,
                     SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW);
        if (TrueSetForegroundWindow != nullptr) {
            TrueSetForegroundWindow(window);
        }
        FLASHWINFO flash = {sizeof(flash), window, FLASHW_ALL | FLASHW_TIMERNOFG,
                            3, 0};
        FlashWindowEx(&flash);
        MessageBeep(MB_ICONEXCLAMATION);

        MSG message = {};
        while (GetMessageW(&message, nullptr, 0, 0) > 0) {
            if (!IsDialogMessageW(window, &message)) {
                TranslateMessage(&message);
                DispatchMessageW(&message);
            }
        }
        // WM_QUIT 可能来自 StopConfirmThread；此时窗口还没走 WM_CLOSE，
        // 必须把当前请求按拒绝收尾，并销毁窗口，避免调用方永久等待。
        if (g_confirm_current != nullptr) {
            if (!g_confirm_finalized) {
                CompleteConfirmRequest(g_confirm_current, kConfirmDeny);
            }
            if (g_confirm_hwnd != nullptr && IsWindow(g_confirm_hwnd)) {
                DestroyWindow(g_confirm_hwnd);
            }
            delete g_confirm_current;
            g_confirm_current = nullptr;
        }
        g_confirm_hwnd = nullptr;
        g_confirm_finalized = false;
    }
    return 0;
}

bool StartConfirmThread() {
    if (g_confirm_thread != nullptr) {
        return true;
    }
    if (!g_confirm_lock_ready) {
        return false;
    }
    InterlockedExchange(&g_confirm_stop, 0);
    g_confirm_event = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    if (g_confirm_event == nullptr) {
        return false;
    }
    g_confirm_thread = CreateThread(nullptr, 0, ConfirmThreadProc, nullptr, 0,
                                    &g_confirm_thread_id);
    if (g_confirm_thread == nullptr) {
        g_confirm_thread_id = 0;
        CloseHandle(g_confirm_event);
        g_confirm_event = nullptr;
        return false;
    }
    return true;
}

void StopConfirmThread() {
    if (g_confirm_thread != nullptr) {
        InterlockedExchange(&g_confirm_stop, 1);
        if (g_confirm_event != nullptr) {
            SetEvent(g_confirm_event);
        }
        if (g_confirm_hwnd != nullptr && IsWindow(g_confirm_hwnd)) {
            PostMessageW(g_confirm_hwnd, WM_CLOSE, 0, 0);
        }
        // 对话框线程可能正卡在创建窗口或消息循环里，补一个线程级 WM_QUIT，
        // 让它走统一的收尾路径；线程内的当前请求会按拒绝完成。
        if (g_confirm_thread_id != 0) {
            PostThreadMessageW(g_confirm_thread_id, WM_QUIT, 0, 0);
        }
        WaitForSingleObject(g_confirm_thread, 5000);
        CloseHandle(g_confirm_thread);
        g_confirm_thread = nullptr;
        g_confirm_thread_id = 0;
    }
    if (g_confirm_event != nullptr) {
        CloseHandle(g_confirm_event);
        g_confirm_event = nullptr;
    }
    DrainConfirmQueue();
}

ConfirmDecision ShowCommandConfirm(const std::wstring& path,
                                   const std::wstring& params) {
    if (g_confirm_thread == nullptr ||
        InterlockedCompareExchange(&g_confirm_stop, 0, 0) != 0) {
        return kConfirmUnavailable;
    }
    auto* result = new (std::nothrow) ConfirmResult();
    if (result == nullptr) {
        return kConfirmUnavailable;
    }
    result->done = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    result->state = 0;
    result->decision = kConfirmDeny;
    if (result->done == nullptr) {
        delete result;
        return kConfirmUnavailable;
    }
    auto* request = new (std::nothrow) ConfirmRequest();
    if (request == nullptr) {
        CloseHandle(result->done);
        delete result;
        return kConfirmUnavailable;
    }
    wcsncpy_s(request->path, path.c_str(), _TRUNCATE);
    wcsncpy_s(request->params, params.c_str(), _TRUNCATE);
    request->result = result;
    request->next = nullptr;
    PushConfirmRequest(request);

    // 与上游一致：没有超时，没人处理就一直等。注入线程退出时
    // StopConfirmThread 会把队列里的请求按拒绝收尾。
    WaitForSingleObject(result->done, INFINITE);
    const ConfirmDecision decision =
        static_cast<ConfirmDecision>(result->decision);
    CloseHandle(result->done);
    delete result;
    return decision;
}

// ---------------------------------------------------------------------------
// 远程命令共享内存通道（保留给无人值守/无会话场景）
// ---------------------------------------------------------------------------

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

bool EnsureRemoteChannel() {
    if (g_remote_header != nullptr) {
        return true;
    }
    wchar_t name[64] = {};
    swprintf_s(name, L"Local\\JiyuGuardRemote_%lu", GetCurrentProcessId());
    g_remote_mapping = OpenFileMappingW(FILE_MAP_ALL_ACCESS, FALSE, name);
    if (g_remote_mapping == nullptr) {
        g_remote_mapping = CreateFileMappingW(
            INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0,
            JiyuGuardRemoteSize(), name);
    }
    if (g_remote_mapping == nullptr) {
        return false;
    }
    auto* view = static_cast<unsigned char*>(
        MapViewOfFile(g_remote_mapping, FILE_MAP_ALL_ACCESS, 0, 0, 0));
    if (view == nullptr) {
        CloseHandle(g_remote_mapping);
        g_remote_mapping = nullptr;
        return false;
    }
    g_remote_header = reinterpret_cast<JiyuGuardRemoteHeader*>(view);
    g_remote_entries = reinterpret_cast<JiyuGuardRemoteEntry*>(
        view + sizeof(JiyuGuardRemoteHeader));
    if (g_remote_header->magic != JIYU_GUARD_REMOTE_MAGIC ||
        g_remote_header->version != JIYU_GUARD_REMOTE_VERSION) {
        g_remote_header->magic = JIYU_GUARD_REMOTE_MAGIC;
        g_remote_header->version = JIYU_GUARD_REMOTE_VERSION;
        g_remote_header->slots = JIYU_GUARD_REMOTE_SLOTS;
        g_remote_header->reserved = 0;
    }
    return true;
}

void CloseRemoteChannel() {
    if (g_remote_header != nullptr) {
        UnmapViewOfFile(g_remote_header);
        g_remote_header = nullptr;
        g_remote_entries = nullptr;
    }
    if (g_remote_mapping != nullptr) {
        CloseHandle(g_remote_mapping);
        g_remote_mapping = nullptr;
    }
}

bool RequestRemoteCommand(LPCWSTR application, LPCWSTR command_line) {
    if (!HasFlag(JIYU_GUARD_BLOCK_REMOTE)) {
        return true;
    }
    if (!EnsureRemoteChannel()) {
        SetLastError(ERROR_ACCESS_DENIED);
        return false;
    }
    wchar_t text[JIYU_GUARD_REMOTE_COMMAND_CHARS] = {};
    if (application != nullptr && *application != L'\0') {
        wcsncpy_s(text, application, _TRUNCATE);
    }
    if (command_line != nullptr && *command_line != L'\0') {
        if (text[0] != L'\0') {
            wcsncat_s(text, L" ", _TRUNCATE);
        }
        wcsncat_s(text, command_line, _TRUNCATE);
    }
    if (text[0] == L'\0') {
        return true;
    }

    JiyuGuardRemoteEntry* slot = nullptr;
    for (unsigned int index = 0; index < JIYU_GUARD_REMOTE_SLOTS; ++index) {
        JiyuGuardRemoteEntry* candidate = &g_remote_entries[index];
        if (InterlockedCompareExchange(&candidate->state,
                                       JIYU_GUARD_REMOTE_PENDING,
                                       JIYU_GUARD_REMOTE_EMPTY) ==
            JIYU_GUARD_REMOTE_EMPTY) {
            slot = candidate;
            break;
        }
    }
    if (slot == nullptr) {
        SetLastError(ERROR_ACCESS_DENIED);
        return false;
    }

    slot->process_id = GetCurrentProcessId();
    slot->command_length = 0;
    wcsncpy_s(slot->command, text, _TRUNCATE);
    slot->command_length = static_cast<unsigned int>(wcslen(slot->command));
    MemoryBarrier();

    const DWORD started = GetTickCount();
    while (GetTickCount() - started < 30000) {
        LONG state = slot->state;
        if (state == JIYU_GUARD_REMOTE_ALLOW) {
            InterlockedExchange(&slot->state, JIYU_GUARD_REMOTE_EMPTY);
            return true;
        }
        if (state == JIYU_GUARD_REMOTE_DENY) {
            InterlockedExchange(&slot->state, JIYU_GUARD_REMOTE_EMPTY);
            SetLastError(ERROR_ACCESS_DENIED);
            return false;
        }
        Sleep(25);
    }
    InterlockedCompareExchange(&slot->state, JIYU_GUARD_REMOTE_EMPTY,
                               JIYU_GUARD_REMOTE_PENDING);
    SetLastError(ERROR_ACCESS_DENIED);
    return false;
}

// 对话框优先；没有会话（对话框线程未起来）时才走共享内存。
bool ConfirmOrRemote(const std::wstring& path, const std::wstring& params) {
    const ConfirmDecision decision = ShowCommandConfirm(path, params);
    if (decision == kConfirmUnavailable) {
        return RequestRemoteCommand(path.c_str(), params.c_str());
    }
    return decision != kConfirmDeny;
}

// ---------------------------------------------------------------------------
// 进程启动判定
// ---------------------------------------------------------------------------

std::wstring FirstCommandToken(const std::wstring& command_line) {
    size_t begin = command_line.find_first_not_of(L" \t");
    if (begin == std::wstring::npos) {
        return std::wstring();
    }
    if (command_line[begin] == L'"') {
        const size_t end = command_line.find(L'"', begin + 1);
        return command_line.substr(begin + 1, end == std::wstring::npos
                                                  ? std::wstring::npos
                                                  : end - begin - 1);
    }
    size_t end = begin;
    while (end < command_line.size() && command_line[end] != L' ' &&
           command_line[end] != L'\t') {
        ++end;
    }
    return command_line.substr(begin, end - begin);
}

std::wstring ResolveExecutablePath(LPCWSTR application, LPCWSTR command_line) {
    const std::wstring app = application != nullptr ? application : L"";
    const std::wstring command = command_line != nullptr ? command_line : L"";
    if (!app.empty() && GetFileAttributesW(app.c_str()) != INVALID_FILE_ATTRIBUTES) {
        return app;
    }
    const std::wstring token = FirstCommandToken(command);
    if (!token.empty() &&
        GetFileAttributesW(token.c_str()) != INVALID_FILE_ATTRIBUTES) {
        return token;
    }
    if (!app.empty()) {
        return app;
    }
    return token;
}

bool IsBenignProcess(const std::wstring& lower_path) {
    return ContainsText(lower_path, L"jiyutrainer.exe") ||
           ContainsText(lower_path, L"explorer") ||
           ContainsText(lower_path, L"sogouinput") ||
           ContainsText(lower_path, L"ime") ||
           ContainsText(lower_path, L"baidupinyin");
}

bool EvaluateProcessStart(LPCWSTR application, LPCWSTR command_line) {
    const std::wstring exe = ResolveExecutablePath(application, command_line);
    const std::wstring lower = ToLowerString(exe);
    const std::wstring params = command_line != nullptr ? command_line : L"";

    // tdchalk.exe 是极域的课堂画笔工具，任何模式下都直接拒绝。
    if (ContainsText(lower, L"tdchalk.exe")) {
        return false;
    }
    if (SessionAllowsAll()) {
        return true;
    }
    if (ContainsText(lower, L"shutdown.exe")) {
        return ConfirmOrRemote(L"shutdown.exe", params);
    }
    if (IsBenignProcess(lower) || IsWhitelisted(exe)) {
        return true;
    }
    return ConfirmOrRemote(exe.empty() ? L"(unknown)" : exe, params);
}

std::wstring AnsiToWideString(LPCSTR text) {
    if (text == nullptr) {
        return std::wstring();
    }
    const int length = MultiByteToWideChar(CP_ACP, 0, text, -1, nullptr, 0);
    if (length <= 1) {
        return std::wstring();
    }
    std::wstring result(static_cast<size_t>(length), L'\0');
    MultiByteToWideChar(CP_ACP, 0, text, -1, &result[0], length);
    result.resize(static_cast<size_t>(length - 1));
    return result;
}

// ---------------------------------------------------------------------------
// 原有策略钩子
// ---------------------------------------------------------------------------

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
    if (InterlockedCompareExchange(&g_is_gb_founded, 1, 1) == 1) {
        // 广播窗口已建立时放行显示 DC，避免极域自身的广播渲染被误伤。
        return TrueCreateDCW ? TrueCreateDCW(driver, device, port, mode)
                             : nullptr;
    }
    if (HasFlag(JIYU_GUARD_ANTI_MONITOR) && driver != nullptr &&
        _wcsicmp(driver, L"DISPLAY") == 0) {
        SetLastError(ERROR_ACCESS_DENIED);
        return nullptr;
    }
    return TrueCreateDCW ? TrueCreateDCW(driver, device, port, mode) : nullptr;
}

HRESULT WINAPI HookDwmEnableComposition(UINT action) {
    if (HasFlag(JIYU_GUARD_ANTI_MONITOR) && action == DWM_EC_DISABLECOMPOSITION) {
        return S_OK;
    }
    return TrueDwmEnableComposition ? TrueDwmEnableComposition(action) : E_NOTIMPL;
}

UINT WINAPI HookSendInput(UINT count, LPINPUT inputs, int size) {
    if (HasFlag(JIYU_GUARD_ANTI_CONTROL)) {
        SetLastError(ERROR_ACCESS_DENIED);
        // 上游按“已吞掉的输入条数”返回，调用方据此判断输入是否生效。
        return count;
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
    return TrueSendMessageW ? TrueSendMessageW(window, message, wparam, lparam)
                            : 0;
}

// ---------------------------------------------------------------------------
// 窗口位置/显示钩子
// ---------------------------------------------------------------------------

BOOL WINAPI HookSetForegroundWindow(HWND window) {
    (void)window;
    if (g_installed) {
        // 上游语义：启用防护后无条件返回 TRUE，不转调原函数。
        return TRUE;
    }
    return TrueSetForegroundWindow ? TrueSetForegroundWindow(window) : FALSE;
}

BOOL WINAPI HookSetWindowPos(HWND window, HWND insert_after, int x, int y,
                             int cx, int cy, UINT flags) {
    if (!g_installed || !HasFlag(JIYU_GUARD_ANTI_MONITOR)) {
        return TrueSetWindowPos
                   ? TrueSetWindowPos(window, insert_after, x, y, cx, cy, flags)
                   : FALSE;
    }
    if ((flags & SWP_NOSIZE) == 0) {
        const bool full_screen =
            x == 0 && y == 0 && cx == ScreenWidth() && cy == ScreenHeight();
        if (full_screen) {
            SetLockState(window, true);
            if (HasFlag(JIYU_GUARD_ANTI_MONITOR) && WindowIsBroadcastOrBlack(window)) {
                return TrueSetWindowPos
                           ? TrueSetWindowPos(window, insert_after, x, y, cx, cy,
                                              flags)
                           : FALSE;
            }
            if (IsCanSizeWindow(window)) {
                RemoveCanSizeWindow(window);
                const BOOL result =
                    TrueSetWindowPos
                        ? TrueSetWindowPos(window, insert_after, x, y, cx, cy,
                                           flags | SWP_NOZORDER)
                        : FALSE;
                if (TrueSendMessageW != nullptr) {
                    TrueSendMessageW(window, WM_SIZE, 0, 0);
                }
                return TRUE;
            }
            return TRUE;
        }
        SetLockState(window, false);
        if (HasFlag(JIYU_GUARD_ANTI_MONITOR)) {
            return TrueSetWindowPos
                       ? TrueSetWindowPos(window, HWND_NOTOPMOST, x, y, cx, cy,
                                          flags)
                       : FALSE;
        }
        if (IsIllegalWindow(window)) {
            return TRUE;
        }
        return TrueSetWindowPos
                   ? TrueSetWindowPos(window, insert_after, x, y, cx, cy, flags)
                   : FALSE;
    }
    if (IsIllegalWindow(window)) {
        return TRUE;
    }
    return TrueSetWindowPos
               ? TrueSetWindowPos(window, insert_after, x, y, cx, cy, flags)
               : FALSE;
}

HDWP WINAPI HookDeferWindowPos(HDWP position, HWND window, HWND insert_after,
                               int x, int y, int cx, int cy, UINT flags) {
    if (!g_installed || !HasFlag(JIYU_GUARD_ANTI_MONITOR)) {
        return TrueDeferWindowPos
                   ? TrueDeferWindowPos(position, window, insert_after, x, y, cx,
                                        cy, flags)
                   : nullptr;
    }
    if ((flags & SWP_NOSIZE) == 0) {
        const bool full_screen =
            x == 0 && y == 0 && cx == ScreenWidth() && cy == ScreenHeight();
        if (full_screen) {
            SetLockState(window, true);
            if (HasFlag(JIYU_GUARD_ANTI_MONITOR) && WindowIsBroadcastOrBlack(window)) {
                return TrueDeferWindowPos
                           ? TrueDeferWindowPos(position, window, insert_after, x,
                                                y, cx, cy, flags)
                           : nullptr;
            }
            if (IsCanSizeWindow(window)) {
                RemoveCanSizeWindow(window);
                HDWP result =
                    TrueDeferWindowPos
                        ? TrueDeferWindowPos(position, window, insert_after, x, y,
                                             cx, cy, flags | SWP_NOZORDER)
                        : nullptr;
                if (TrueSendMessageW != nullptr) {
                    TrueSendMessageW(window, WM_SIZE, 0, 0);
                }
                return result;
            }
            return nullptr;
        }
        SetLockState(window, false);
        if (HasFlag(JIYU_GUARD_ANTI_MONITOR)) {
            return TrueDeferWindowPos
                       ? TrueDeferWindowPos(position, window, HWND_NOTOPMOST, x,
                                            y, cx, cy, flags)
                       : nullptr;
        }
        if (IsIllegalWindow(window)) {
            return nullptr;
        }
        return TrueDeferWindowPos
                   ? TrueDeferWindowPos(position, window, insert_after, x, y,
                                        cx, cy, flags)
                   : nullptr;
    }
    if (IsIllegalWindow(window)) {
        return nullptr;
    }
    return TrueDeferWindowPos
               ? TrueDeferWindowPos(position, window, insert_after, x, y, cx, cy,
                                    flags)
               : nullptr;
}

BOOL WINAPI HookMoveWindow(HWND window, int x, int y, int cx, int cy,
                           BOOL repaint) {
    if (!g_installed || !HasFlag(JIYU_GUARD_ANTI_MONITOR)) {
        return TrueMoveWindow ? TrueMoveWindow(window, x, y, cx, cy, repaint)
                              : FALSE;
    }
    const bool full_screen =
        x == 0 && y == 0 && cx == ScreenWidth() && cy == ScreenHeight();
    if (full_screen) {
        SetLockState(window, true);
        if (HasFlag(JIYU_GUARD_ANTI_MONITOR) && WindowIsBroadcastOrBlack(window)) {
            return TrueMoveWindow ? TrueMoveWindow(window, x, y, cx, cy, repaint)
                                  : FALSE;
        }
        if (IsCanSizeWindow(window)) {
            RemoveCanSizeWindow(window);
            return TrueMoveWindow ? TrueMoveWindow(window, x, y, cx, cy, repaint)
                                  : FALSE;
        }
        return TRUE;
    }
    SetLockState(window, false);
    if (HasFlag(JIYU_GUARD_ANTI_MONITOR)) {
        return TrueMoveWindow ? TrueMoveWindow(window, x, y, cx, cy, repaint)
                              : FALSE;
    }
    if (IsIllegalWindow(window)) {
        return TRUE;
    }
    return TrueMoveWindow ? TrueMoveWindow(window, x, y, cx, cy, repaint) : FALSE;
}

bool IsShowCommand(int command) {
    switch (command) {
    case SW_SHOW:
    case SW_SHOWNORMAL:
    case SW_MAXIMIZE:  // 与 SW_SHOWMAXIMIZED 同值
    case SW_MAX:       // 与 SW_SHOWDEFAULT 同值
    case SW_SHOWNA:
    case SW_SHOWNOACTIVATE:
        return true;
    default:
        return false;
    }
}

BOOL WINAPI HookShowWindow(HWND window, int command) {
    if (g_installed && HasFlag(JIYU_GUARD_ANTI_MONITOR) &&
        WindowIsBroadcastOrBlack(window)) {
        const std::wstring title = GetWindowTitle(window);
        if (IsShowCommand(command)) {
            if (IsBroadcastTitle(title)) {
                InterlockedExchange(&g_is_gb_founded, 1);
            }
            SetLockState(window, true);
        } else if (command == SW_HIDE) {
            if (IsBroadcastTitle(title)) {
                InterlockedExchange(&g_is_gb_founded, 0);
            }
            SetLockState(window, false);
            // 与上游窗口子类的 WM_SHOWWINDOW(FALSE) 一致：隐藏窗口下次允许改尺寸。
            AddCanSizeWindow(window);
        }
    }
    return TrueShowWindow ? TrueShowWindow(window, command) : FALSE;
}

LONG WINAPI HookSetWindowLongW(HWND window, int index, LONG new_value) {
    if (g_installed && HasFlag(JIYU_GUARD_ANTI_MONITOR)) {
        if (WindowIsBroadcastOrBlack(window)) {
            return TrueSetWindowLongW
                       ? TrueSetWindowLongW(window, index, new_value)
                       : 0;
        }
        if (IsIllegalWindow(window)) {
            return GetWindowLongW(window, index);
        }
    }
    return TrueSetWindowLongW ? TrueSetWindowLongW(window, index, new_value) : 0;
}

LONG WINAPI HookSetWindowLongA(HWND window, int index, LONG new_value) {
    if (g_installed && HasFlag(JIYU_GUARD_ANTI_MONITOR)) {
        if (WindowIsBroadcastOrBlack(window)) {
            return TrueSetWindowLongA
                       ? TrueSetWindowLongA(window, index, new_value)
                       : 0;
        }
        if (IsIllegalWindow(window)) {
            return GetWindowLongA(window, index);
        }
    }
    return TrueSetWindowLongA ? TrueSetWindowLongA(window, index, new_value) : 0;
}

DWORD WINAPI HookSetClassLongW(HWND window, int index, LONG new_value) {
    if (g_installed && HasFlag(JIYU_GUARD_BLOCK_CLOSE) &&
        index == GCL_STYLE && (new_value & CS_NOCLOSE) == CS_NOCLOSE) {
        return TrueSetClassLongW
                   ? TrueSetClassLongW(window, index, new_value ^ CS_NOCLOSE)
                   : 0;
    }
    return TrueSetClassLongW ? TrueSetClassLongW(window, index, new_value) : 0;
}

DWORD WINAPI HookSetClassLongA(HWND window, int index, LONG new_value) {
    if (g_installed && HasFlag(JIYU_GUARD_BLOCK_CLOSE) &&
        index == GCL_STYLE && (new_value & CS_NOCLOSE) == CS_NOCLOSE) {
        return TrueSetClassLongA
                   ? TrueSetClassLongA(window, index, new_value ^ CS_NOCLOSE)
                   : 0;
    }
    return TrueSetClassLongA ? TrueSetClassLongA(window, index, new_value) : 0;
}

BOOL WINAPI HookEnableMenuItem(HMENU menu, UINT item, UINT enable) {
    if (g_installed && HasFlag(JIYU_GUARD_BLOCK_CLOSE) && item == SC_CLOSE) {
        return 0;
    }
    return TrueEnableMenuItem ? TrueEnableMenuItem(menu, item, enable) : 0;
}

BOOL WINAPI HookBringWindowToTop(HWND window) {
    if (g_installed && HasFlag(JIYU_GUARD_ANTI_MONITOR) &&
        IsIllegalWindow(window)) {
        return TRUE;
    }
    return TrueBringWindowToTop ? TrueBringWindowToTop(window) : FALSE;
}

// ---------------------------------------------------------------------------
// 设备与文件钩子
// ---------------------------------------------------------------------------

bool IsBlockedDeviceName(const wchar_t* name) {
    if (name == nullptr) {
        return false;
    }
    return _wcsicmp(name, L"\\\\.\\TDKeybd") == 0 ||
           _wcsicmp(name, L"\\\\.\\TDProcHook") == 0 ||
           _wcsicmp(name, L"\\\\.\\TDNetFilter") == 0;
}

bool IsBlockedDeviceNameA(const char* name) {
    if (name == nullptr) {
        return false;
    }
    return _stricmp(name, "\\\\.\\TDKeybd") == 0 ||
           _stricmp(name, "\\\\.\\TDProcHook") == 0 ||
           _stricmp(name, "\\\\.\\TDNetFilter") == 0;
}

HANDLE WINAPI HookCreateFileW(LPCWSTR name, DWORD access, DWORD share,
                              LPSECURITY_ATTRIBUTES attributes,
                              DWORD disposition, DWORD flags, HANDLE template_file) {
    if (g_installed && HasFlag(JIYU_GUARD_ANTI_CONTROL) &&
        IsBlockedDeviceName(name)) {
        SetLastError(ERROR_ACCESS_DENIED);
        return INVALID_HANDLE_VALUE;
    }
    return TrueCreateFileW
               ? TrueCreateFileW(name, access, share, attributes, disposition,
                                 flags, template_file)
               : INVALID_HANDLE_VALUE;
}

HANDLE WINAPI HookCreateFileA(LPCSTR name, DWORD access, DWORD share,
                              LPSECURITY_ATTRIBUTES attributes,
                              DWORD disposition, DWORD flags, HANDLE template_file) {
    if (g_installed && HasFlag(JIYU_GUARD_ANTI_CONTROL) &&
        IsBlockedDeviceNameA(name)) {
        SetLastError(ERROR_ACCESS_DENIED);
        return INVALID_HANDLE_VALUE;
    }
    return TrueCreateFileA
               ? TrueCreateFileA(name, access, share, attributes, disposition,
                                 flags, template_file)
               : INVALID_HANDLE_VALUE;
}

BOOL WINAPI HookDeviceIoControl(HANDLE device, DWORD code, LPVOID input,
                                DWORD input_size, LPVOID output,
                                DWORD output_size, LPDWORD returned,
                                LPOVERLAPPED overlapped) {
    if (g_installed && HasFlag(JIYU_GUARD_ANTI_CONTROL) &&
        device != INVALID_HANDLE_VALUE &&
        (device == g_device_tdkeybd || device == g_device_tdprochook ||
         device == g_device_tdnetfilter)) {
        SetLastError(ERROR_ACCESS_DENIED);
        return FALSE;
    }
    return TrueDeviceIoControl
               ? TrueDeviceIoControl(device, code, input, input_size, output,
                                     output_size, returned, overlapped)
               : FALSE;
}

// ---------------------------------------------------------------------------
// 关机与进程启动钩子
// ---------------------------------------------------------------------------

BOOL WINAPI HookExitWindowsEx(UINT flags, DWORD reason) {
    if (!g_installed || !HasFlag(JIYU_GUARD_BLOCK_REMOTE)) {
        return TrueExitWindowsEx ? TrueExitWindowsEx(flags, reason) : FALSE;
    }
    const wchar_t* action = L"注销您的计算机";
    if ((flags & EWX_POWEROFF) == EWX_POWEROFF) {
        action = L"关闭您的计算机";
    } else if ((flags & EWX_REBOOT) == EWX_REBOOT) {
        action = L"重启您的计算机";
    }
    if (!ConfirmOrRemote(L"ExitWindowsEx", action)) {
        SetLastError(ERROR_ACCESS_DENIED);
        return FALSE;
    }
    return TrueExitWindowsEx ? TrueExitWindowsEx(flags, reason) : FALSE;
}

BOOL WINAPI HookCreateProcessW(
    LPCWSTR application, LPWSTR command_line,
    LPSECURITY_ATTRIBUTES process_attributes,
    LPSECURITY_ATTRIBUTES thread_attributes, BOOL inherit_handles,
    DWORD creation_flags, LPVOID environment, LPCWSTR current_directory,
    LPSTARTUPINFOW startup_info, LPPROCESS_INFORMATION process_information) {
    if (g_installed && HasFlag(JIYU_GUARD_BLOCK_REMOTE) &&
        !EvaluateProcessStart(application, command_line)) {
        // 上游约定：拒绝启动时返回 TRUE，避免极域重试弹框。
        return TRUE;
    }
    return TrueCreateProcessW
               ? TrueCreateProcessW(application, command_line, process_attributes,
                                    thread_attributes, inherit_handles,
                                    creation_flags, environment, current_directory,
                                    startup_info, process_information)
               : FALSE;
}

BOOL WINAPI HookCreateProcessA(
    LPCSTR application, LPSTR command_line,
    LPSECURITY_ATTRIBUTES process_attributes,
    LPSECURITY_ATTRIBUTES thread_attributes, BOOL inherit_handles,
    DWORD creation_flags, LPVOID environment, LPCSTR current_directory,
    LPSTARTUPINFOA startup_info, LPPROCESS_INFORMATION process_information) {
    if (g_installed && HasFlag(JIYU_GUARD_BLOCK_REMOTE)) {
        const std::wstring wide_application = AnsiToWideString(application);
        const std::wstring wide_command = AnsiToWideString(command_line);
        if (!EvaluateProcessStart(wide_application.empty() ? nullptr
                                                           : wide_application.c_str(),
                                  wide_command.empty() ? nullptr
                                                       : wide_command.c_str())) {
            return TRUE;
        }
    }
    return TrueCreateProcessA
               ? TrueCreateProcessA(application, command_line, process_attributes,
                                    thread_attributes, inherit_handles,
                                    creation_flags, environment, current_directory,
                                    startup_info, process_information)
               : FALSE;
}

UINT WINAPI HookWinExec(LPCSTR command_line, UINT show_command) {
    if (g_installed && HasFlag(JIYU_GUARD_BLOCK_REMOTE)) {
        const std::wstring wide = AnsiToWideString(command_line);
        if (!EvaluateProcessStart(nullptr, wide.c_str())) {
            return 32;
        }
    }
    return TrueWinExec ? TrueWinExec(command_line, show_command) : 0;
}

// ---------------------------------------------------------------------------
// 钩子链与输入钩子伪句柄
// ---------------------------------------------------------------------------

LRESULT CALLBACK GuardLowLevelMouseProc(int code, WPARAM wparam, LPARAM lparam) {
    LRESULT result = TrueCallNextHookEx
                         ? TrueCallNextHookEx(g_mouse_hook, code, wparam, lparam)
                         : 0;
    if (g_saved_mouse_proc != nullptr) {
        g_saved_mouse_proc(code, wparam, lparam);
    }
    return result;
}

LRESULT CALLBACK GuardLowLevelKeyboardProc(int code, WPARAM wparam,
                                           LPARAM lparam) {
    LRESULT result = TrueCallNextHookEx
                         ? TrueCallNextHookEx(g_keyboard_hook, code, wparam, lparam)
                         : 0;
    if (g_saved_keyboard_proc != nullptr) {
        g_saved_keyboard_proc(code, wparam, lparam);
    }
    return result;
}

HHOOK InstallInputHook(int hook, HOOKPROC procedure, HINSTANCE module,
                       DWORD thread, bool wide) {
    HMODULE td_master = GetModuleHandleW(L"LibTDMaster.dll");
    // 只有 LibTDMaster 发起的低速输入钩子才接管；null 或其它模块一律拒绝，
    // 避免把普通进程自己的钩子也换成伪句柄。
    if (td_master == nullptr || module != td_master) {
        SetLastError(ERROR_ACCESS_DENIED);
        return nullptr;
    }
    if (hook == WH_KEYBOARD_LL) {
        g_saved_keyboard_proc = procedure;
        g_keyboard_hook =
            wide ? (TrueSetWindowsHookExW
                        ? TrueSetWindowsHookExW(hook, GuardLowLevelKeyboardProc,
                                                module, thread)
                        : nullptr)
                 : (TrueSetWindowsHookExA
                        ? TrueSetWindowsHookExA(hook, GuardLowLevelKeyboardProc,
                                                module, thread)
                        : nullptr);
        return reinterpret_cast<HHOOK>(kPseudoKeyboardHook);
    }
    if (hook == WH_MOUSE_LL || hook == WH_MOUSE) {
        g_saved_mouse_proc = procedure;
        g_mouse_hook =
            wide ? (TrueSetWindowsHookExW
                        ? TrueSetWindowsHookExW(hook, GuardLowLevelMouseProc,
                                                module, thread)
                        : nullptr)
                 : (TrueSetWindowsHookExA
                        ? TrueSetWindowsHookExA(hook, GuardLowLevelMouseProc,
                                                module, thread)
                        : nullptr);
        return reinterpret_cast<HHOOK>(kPseudoMouseHook);
    }
    return nullptr;
}

HHOOK WINAPI HookSetWindowsHookExW(int hook, HOOKPROC procedure,
                                   HINSTANCE module, DWORD thread) {
    if (g_installed && HasFlag(JIYU_GUARD_ANTI_CONTROL)) {
        if (hook == WH_CBT) {
            SetLastError(ERROR_ACCESS_DENIED);
            return nullptr;
        }
        if (hook == WH_MOUSE_LL || hook == WH_MOUSE || hook == WH_KEYBOARD_LL) {
            return InstallInputHook(hook, procedure, module, thread, true);
        }
    }
    return TrueSetWindowsHookExW
               ? TrueSetWindowsHookExW(hook, procedure, module, thread)
               : nullptr;
}

HHOOK WINAPI HookSetWindowsHookExA(int hook, HOOKPROC procedure,
                                   HINSTANCE module, DWORD thread) {
    if (g_installed && HasFlag(JIYU_GUARD_ANTI_CONTROL)) {
        if (hook == WH_CBT) {
            SetLastError(ERROR_ACCESS_DENIED);
            return nullptr;
        }
        if (hook == WH_MOUSE_LL || hook == WH_MOUSE || hook == WH_KEYBOARD_LL) {
            return InstallInputHook(hook, procedure, module, thread, false);
        }
    }
    return TrueSetWindowsHookExA
               ? TrueSetWindowsHookExA(hook, procedure, module, thread)
               : nullptr;
}

LRESULT WINAPI HookCallNextHookEx(HHOOK hook, int code, WPARAM wparam,
                                  LPARAM lparam) {
    const ULONG_PTR value = reinterpret_cast<ULONG_PTR>(hook);
    if (value == kPseudoMouseHook || value == kPseudoKeyboardHook) {
        return 0;
    }
    return TrueCallNextHookEx ? TrueCallNextHookEx(hook, code, wparam, lparam)
                              : 0;
}

BOOL WINAPI HookUnhookWindowsHookEx(HHOOK hook) {
    const ULONG_PTR value = reinterpret_cast<ULONG_PTR>(hook);
    if (value == kPseudoMouseHook) {
        if (g_mouse_hook != nullptr && TrueUnhookWindowsHookEx != nullptr) {
            TrueUnhookWindowsHookEx(g_mouse_hook);
        }
        g_mouse_hook = nullptr;
        g_saved_mouse_proc = nullptr;
        return TRUE;
    }
    if (value == kPseudoKeyboardHook) {
        if (g_keyboard_hook != nullptr && TrueUnhookWindowsHookEx != nullptr) {
            TrueUnhookWindowsHookEx(g_keyboard_hook);
        }
        g_keyboard_hook = nullptr;
        g_saved_keyboard_proc = nullptr;
        return TRUE;
    }
    return TrueUnhookWindowsHookEx ? TrueUnhookWindowsHookEx(hook) : FALSE;
}

// ---------------------------------------------------------------------------
// 桌面、显示与过滤驱动钩子
// ---------------------------------------------------------------------------

HWND WINAPI HookGetForegroundWindow() {
    // 与上游 allowMonitor 对齐：只有反监视策略开启时才隐藏前台窗口。
    if (g_installed && HasFlag(JIYU_GUARD_ANTI_MONITOR) &&
        !SessionAllowsAll()) {
        return nullptr;
    }
    return TrueGetForegroundWindow ? TrueGetForegroundWindow() : nullptr;
}

HDESK WINAPI HookOpenInputDesktop(DWORD flags, BOOL inherit,
                                  ACCESS_MASK access) {
    if (g_installed && HasFlag(JIYU_GUARD_ANTI_MONITOR)) {
        SetLastError(ERROR_ACCESS_DENIED);
        return nullptr;
    }
    return TrueOpenInputDesktop
               ? TrueOpenInputDesktop(flags, inherit, access)
               : nullptr;
}

HDESK WINAPI HookOpenDesktopA(LPCSTR name, DWORD flags, BOOL inherit,
                              ACCESS_MASK access) {
    if (g_installed && HasFlag(JIYU_GUARD_ANTI_MONITOR)) {
        SetLastError(ERROR_ACCESS_DENIED);
        return nullptr;
    }
    return TrueOpenDesktopA ? TrueOpenDesktopA(name, flags, inherit, access)
                            : nullptr;
}

LONG WINAPI HookChangeDisplaySettingsW(DEVMODEW* mode, DWORD flags) {
    if (g_installed && HasFlag(JIYU_GUARD_ANTI_MONITOR)) {
        return DISP_CHANGE_SUCCESSFUL;
    }
    return TrueChangeDisplaySettingsW
               ? TrueChangeDisplaySettingsW(mode, flags)
               : DISP_CHANGE_FAILED;
}

int __cdecl HookEncodeToJPEGBuffer(int a1, int a2, int a3, int a4, int a5,
                                   DWORD* a6, int a7, int a8, int a9) {
    if (HasFlag(JIYU_GUARD_ANTI_MONITOR)) {
        return FALSE;
    }
    return TrueEncodeToJPEGBuffer
               ? TrueEncodeToJPEGBuffer(a1, a2, a3, a4, a5, a6, a7, a8, a9)
               : FALSE;
}

HRESULT WINAPI HookFilterConnectCommunicationPort(
    LPCWSTR port_name, DWORD options, LPCVOID context, WORD context_size,
    LPSECURITY_ATTRIBUTES security, HANDLE* port) {
    if (g_installed && HasFlag(JIYU_GUARD_ANTI_CONTROL) &&
        port_name != nullptr && _wcsicmp(port_name, L"\\TDFileFilterPort") == 0) {
        return S_FALSE;
    }
    return TrueFilterConnectCommunicationPort
               ? TrueFilterConnectCommunicationPort(port_name, options, context,
                                                    context_size, security, port)
               : E_FAIL;
}

// ---------------------------------------------------------------------------
// 安装/卸载
// ---------------------------------------------------------------------------

HWND CreateFakeDesktop() {
    return CreateWindowExW(0, L"STATIC", L"JiyuGuardFakeDesktop", WS_POPUP, 0, 0,
                           1, 1, nullptr, nullptr, nullptr, nullptr);
}

void OpenProtectedDeviceHandles() {
    if (g_device_tdkeybd == INVALID_HANDLE_VALUE) {
        g_device_tdkeybd = CreateFileW(
            L"\\\\.\\TDKeybd", GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL, nullptr);
    }
    if (g_device_tdprochook == INVALID_HANDLE_VALUE) {
        g_device_tdprochook = CreateFileW(
            L"\\\\.\\TDProcHook", GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL, nullptr);
    }
    if (g_device_tdnetfilter == INVALID_HANDLE_VALUE) {
        g_device_tdnetfilter = CreateFileW(
            L"\\\\.\\TDNetFilter", GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL, nullptr);
    }
}

void CloseProtectedDeviceHandles() {
    if (g_device_tdkeybd != INVALID_HANDLE_VALUE) {
        CloseHandle(g_device_tdkeybd);
        g_device_tdkeybd = INVALID_HANDLE_VALUE;
    }
    if (g_device_tdprochook != INVALID_HANDLE_VALUE) {
        CloseHandle(g_device_tdprochook);
        g_device_tdprochook = INVALID_HANDLE_VALUE;
    }
    if (g_device_tdnetfilter != INVALID_HANDLE_VALUE) {
        CloseHandle(g_device_tdnetfilter);
        g_device_tdnetfilter = INVALID_HANDLE_VALUE;
    }
}

uint64_t g_hooked = 0;

bool HookOne(PVOID* target, PVOID hook, uint64_t bit) {
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
    TrueGetDesktopWindow = reinterpret_cast<GetDesktopWindowFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "GetDesktopWindow"));
    TrueGetWindowDC = reinterpret_cast<GetWindowDCFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "GetWindowDC"));
    TrueCreateDCW = reinterpret_cast<CreateDCWFn>(
        GetProcAddress(GetModuleHandleW(L"gdi32.dll"), "CreateDCW"));
    TrueSetWindowsHookExW = reinterpret_cast<SetWindowsHookExWFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "SetWindowsHookExW"));
    TrueSetWindowsHookExA = reinterpret_cast<SetWindowsHookExAFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "SetWindowsHookExA"));
    TrueCallNextHookEx = reinterpret_cast<CallNextHookExFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "CallNextHookEx"));
    TrueUnhookWindowsHookEx = reinterpret_cast<UnhookWindowsHookExFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "UnhookWindowsHookEx"));
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
    TrueCreateProcessW = reinterpret_cast<CreateProcessWFn>(
        GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "CreateProcessW"));
    TrueCreateProcessA = reinterpret_cast<CreateProcessAFn>(
        GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "CreateProcessA"));
    TrueWinExec = reinterpret_cast<WinExecFn>(
        GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "WinExec"));
    TrueSetForegroundWindow = reinterpret_cast<SetForegroundWindowFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "SetForegroundWindow"));
    TrueSetWindowPos = reinterpret_cast<SetWindowPosFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "SetWindowPos"));
    TrueDeferWindowPos = reinterpret_cast<DeferWindowPosFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "DeferWindowPos"));
    TrueMoveWindow = reinterpret_cast<MoveWindowFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "MoveWindow"));
    TrueShowWindow = reinterpret_cast<ShowWindowFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "ShowWindow"));
    TrueSetWindowLongW = reinterpret_cast<SetWindowLongWFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "SetWindowLongW"));
    TrueSetWindowLongA = reinterpret_cast<SetWindowLongAFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "SetWindowLongA"));
    TrueSetClassLongW = reinterpret_cast<SetClassLongWFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "SetClassLongW"));
    TrueSetClassLongA = reinterpret_cast<SetClassLongAFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "SetClassLongA"));
    TrueBringWindowToTop = reinterpret_cast<BringWindowToTopFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "BringWindowToTop"));
    TrueCreateFileW = reinterpret_cast<CreateFileWFn>(
        GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "CreateFileW"));
    TrueCreateFileA = reinterpret_cast<CreateFileAFn>(
        GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "CreateFileA"));
    TrueDeviceIoControl = reinterpret_cast<DeviceIoControlFn>(
        GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "DeviceIoControl"));
    TrueExitWindowsEx = reinterpret_cast<ExitWindowsExFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "ExitWindowsEx"));
    TrueGetForegroundWindow = reinterpret_cast<GetForegroundWindowFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "GetForegroundWindow"));
    TrueEnableMenuItem = reinterpret_cast<EnableMenuItemFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "EnableMenuItem"));
    TrueOpenInputDesktop = reinterpret_cast<OpenInputDesktopFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "OpenInputDesktop"));
    TrueOpenDesktopA = reinterpret_cast<OpenDesktopAFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "OpenDesktopA"));
    TrueChangeDisplaySettingsW = reinterpret_cast<ChangeDisplaySettingsWFn>(
        GetProcAddress(GetModuleHandleW(L"user32.dll"), "ChangeDisplaySettingsW"));

    HMODULE dwm = LoadLibraryW(L"dwmapi.dll");
    if (dwm != nullptr) {
        TrueDwmEnableComposition = reinterpret_cast<DwmEnableCompositionFn>(
            GetProcAddress(dwm, "DwmEnableComposition"));
    }
    g_libjpeg_module = LoadLibraryW(L"LibJPEG20.dll");
    if (g_libjpeg_module != nullptr) {
        TrueEncodeToJPEGBuffer = reinterpret_cast<EncodeToJPEGBufferFn>(
            GetProcAddress(g_libjpeg_module, "EncodeToJPEGBuffer"));
    }
    g_fltlib_module = LoadLibraryW(L"FltLib.dll");
    if (g_fltlib_module != nullptr) {
        TrueFilterConnectCommunicationPort =
            reinterpret_cast<FilterConnectCommunicationPortFn>(
                GetProcAddress(g_fltlib_module,
                               "FilterConnectCommunicationPort"));
    }

    bool ok = true;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueGetDesktopWindow),
                 reinterpret_cast<PVOID>(HookGetDesktopWindow), 1ull << 0) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueGetWindowDC),
                 reinterpret_cast<PVOID>(HookGetWindowDC), 1ull << 1) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueCreateDCW),
                 reinterpret_cast<PVOID>(HookCreateDCW), 1ull << 2) && ok;
    if (TrueDwmEnableComposition != nullptr) {
        // 新版 Windows 可能已移除 DwmEnableComposition，缺这一项不算失败。
        HookOne(reinterpret_cast<PVOID*>(&TrueDwmEnableComposition),
                reinterpret_cast<PVOID>(HookDwmEnableComposition), 1ull << 3);
    }
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueSetWindowsHookExW),
                 reinterpret_cast<PVOID>(HookSetWindowsHookExW), 1ull << 4) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueSetWindowsHookExA),
                 reinterpret_cast<PVOID>(HookSetWindowsHookExA), 1ull << 5) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueSendInput),
                 reinterpret_cast<PVOID>(HookSendInput), 1ull << 6) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueMouseEvent),
                 reinterpret_cast<PVOID>(HookMouseEvent), 1ull << 7) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueTerminateProcess),
                 reinterpret_cast<PVOID>(HookTerminateProcess), 1ull << 8) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TruePostMessageW),
                 reinterpret_cast<PVOID>(HookPostMessageW), 1ull << 9) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueSendMessageW),
                 reinterpret_cast<PVOID>(HookSendMessageW), 1ull << 10) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueCreateProcessW),
                 reinterpret_cast<PVOID>(HookCreateProcessW), 1ull << 11) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueCreateProcessA),
                 reinterpret_cast<PVOID>(HookCreateProcessA), 1ull << 12) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueWinExec),
                 reinterpret_cast<PVOID>(HookWinExec), 1ull << 13) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueSetForegroundWindow),
                 reinterpret_cast<PVOID>(HookSetForegroundWindow), 1ull << 14) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueSetWindowPos),
                 reinterpret_cast<PVOID>(HookSetWindowPos), 1ull << 15) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueDeferWindowPos),
                 reinterpret_cast<PVOID>(HookDeferWindowPos), 1ull << 16) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueMoveWindow),
                 reinterpret_cast<PVOID>(HookMoveWindow), 1ull << 17) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueShowWindow),
                 reinterpret_cast<PVOID>(HookShowWindow), 1ull << 18) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueSetWindowLongW),
                 reinterpret_cast<PVOID>(HookSetWindowLongW), 1ull << 19) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueSetWindowLongA),
                 reinterpret_cast<PVOID>(HookSetWindowLongA), 1ull << 20) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueSetClassLongW),
                 reinterpret_cast<PVOID>(HookSetClassLongW), 1ull << 21) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueSetClassLongA),
                 reinterpret_cast<PVOID>(HookSetClassLongA), 1ull << 22) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueEnableMenuItem),
                 reinterpret_cast<PVOID>(HookEnableMenuItem), 1ull << 23) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueBringWindowToTop),
                 reinterpret_cast<PVOID>(HookBringWindowToTop), 1ull << 24) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueCreateFileW),
                 reinterpret_cast<PVOID>(HookCreateFileW), 1ull << 25) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueCreateFileA),
                 reinterpret_cast<PVOID>(HookCreateFileA), 1ull << 26) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueDeviceIoControl),
                 reinterpret_cast<PVOID>(HookDeviceIoControl), 1ull << 27) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueExitWindowsEx),
                 reinterpret_cast<PVOID>(HookExitWindowsEx), 1ull << 28) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueCallNextHookEx),
                 reinterpret_cast<PVOID>(HookCallNextHookEx), 1ull << 29) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueUnhookWindowsHookEx),
                 reinterpret_cast<PVOID>(HookUnhookWindowsHookEx), 1ull << 30) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueGetForegroundWindow),
                 reinterpret_cast<PVOID>(HookGetForegroundWindow), 1ull << 31) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueOpenInputDesktop),
                 reinterpret_cast<PVOID>(HookOpenInputDesktop), 1ull << 32) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueOpenDesktopA),
                 reinterpret_cast<PVOID>(HookOpenDesktopA), 1ull << 33) && ok;
    ok = HookOne(reinterpret_cast<PVOID*>(&TrueChangeDisplaySettingsW),
                 reinterpret_cast<PVOID>(HookChangeDisplaySettingsW), 1ull << 34) && ok;
    if (TrueEncodeToJPEGBuffer != nullptr) {
        HookOne(reinterpret_cast<PVOID*>(&TrueEncodeToJPEGBuffer),
                reinterpret_cast<PVOID>(HookEncodeToJPEGBuffer), 1ull << 35);
    }
    if (TrueFilterConnectCommunicationPort != nullptr) {
        HookOne(reinterpret_cast<PVOID*>(&TrueFilterConnectCommunicationPort),
                reinterpret_cast<PVOID>(HookFilterConnectCommunicationPort),
                1ull << 36);
    }
    return ok;
}

void UnhookAll() {
    for (int bit = 0; bit <= 36; ++bit) {
        if ((g_hooked & (1ull << bit)) == 0) {
            continue;
        }
        switch (bit) {
        case 0: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueGetDesktopWindow)); break;
        case 1: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueGetWindowDC)); break;
        case 2: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueCreateDCW)); break;
        case 3: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueDwmEnableComposition)); break;
        case 4: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueSetWindowsHookExW)); break;
        case 5: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueSetWindowsHookExA)); break;
        case 6: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueSendInput)); break;
        case 7: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueMouseEvent)); break;
        case 8: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueTerminateProcess)); break;
        case 9: Mhook_Unhook(reinterpret_cast<PVOID*>(&TruePostMessageW)); break;
        case 10: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueSendMessageW)); break;
        case 11: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueCreateProcessW)); break;
        case 12: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueCreateProcessA)); break;
        case 13: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueWinExec)); break;
        case 14: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueSetForegroundWindow)); break;
        case 15: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueSetWindowPos)); break;
        case 16: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueDeferWindowPos)); break;
        case 17: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueMoveWindow)); break;
        case 18: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueShowWindow)); break;
        case 19: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueSetWindowLongW)); break;
        case 20: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueSetWindowLongA)); break;
        case 21: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueSetClassLongW)); break;
        case 22: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueSetClassLongA)); break;
        case 23: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueEnableMenuItem)); break;
        case 24: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueBringWindowToTop)); break;
        case 25: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueCreateFileW)); break;
        case 26: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueCreateFileA)); break;
        case 27: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueDeviceIoControl)); break;
        case 28: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueExitWindowsEx)); break;
        case 29: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueCallNextHookEx)); break;
        case 30: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueUnhookWindowsHookEx)); break;
        case 31: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueGetForegroundWindow)); break;
        case 32: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueOpenInputDesktop)); break;
        case 33: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueOpenDesktopA)); break;
        case 34: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueChangeDisplaySettingsW)); break;
        case 35: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueEncodeToJPEGBuffer)); break;
        case 36: Mhook_Unhook(reinterpret_cast<PVOID*>(&TrueFilterConnectCommunicationPort)); break;
        default: break;
        }
    }
    g_hooked = 0;
}

void EnsureLocks() {
    if (!g_window_lock_ready) {
        InitializeCriticalSection(&g_window_lock);
        g_window_lock_ready = true;
    }
    if (!g_whitelist_lock_ready) {
        InitializeCriticalSection(&g_whitelist_lock);
        g_whitelist_lock_ready = true;
    }
    if (!g_confirm_lock_ready) {
        InitializeCriticalSection(&g_confirm_lock);
        g_confirm_lock_ready = true;
    }
}

}  // namespace

// ---------------------------------------------------------------------------
// 导出接口（符号名与 Python 侧保持一致）
// ---------------------------------------------------------------------------

extern "C" __declspec(dllexport) const char* JiyuGuardVersion() {
    return "1.3.0";
}

extern "C" __declspec(dllexport) BOOL JiyuGuardInstall() {
    if (g_installed) {
        ReadPolicy();
        LoadWhitelist();
        return TRUE;
    }
    g_current_pid = GetCurrentProcessId();
    EnsureLocks();
    ReadPolicy();
    LoadWhitelist();
    EnsureRemoteChannel();
    g_fake_desktop = CreateFakeDesktop();
    OpenProtectedDeviceHandles();
    StartConfirmThread();
    g_scan_stop = 0;
    g_scan_thread = CreateThread(nullptr, 0, WindowScanThread, nullptr, 0, nullptr);
    g_installed = HookAll();
    if (!g_installed) {
        if (g_scan_thread != nullptr) {
            InterlockedExchange(&g_scan_stop, 1);
            WaitForSingleObject(g_scan_thread, 2000);
            CloseHandle(g_scan_thread);
            g_scan_thread = nullptr;
        }
        StopConfirmThread();
        UnhookAll();
        CloseProtectedDeviceHandles();
        CloseRemoteChannel();
        if (g_fake_desktop != nullptr) {
            DestroyWindow(g_fake_desktop);
            g_fake_desktop = nullptr;
        }
        return FALSE;
    }
    // 右键菜单与防护同生命周期：guard 已注入学生端时才能安全子类化窗口。
    StartGuardMenu();
    return TRUE;
}

extern "C" __declspec(dllexport) void JiyuGuardUninstall() {
    g_installed = false;
    if (g_scan_thread != nullptr) {
        InterlockedExchange(&g_scan_stop, 1);
        WaitForSingleObject(g_scan_thread, 2000);
        CloseHandle(g_scan_thread);
        g_scan_thread = nullptr;
    }
    StopConfirmThread();
    StopGuardMenu();
    UnhookAll();
    CloseProtectedDeviceHandles();
    CloseRemoteChannel();
    if (g_fake_desktop != nullptr) {
        DestroyWindow(g_fake_desktop);
        g_fake_desktop = nullptr;
    }
    if (g_window_lock_ready) {
        EnterCriticalSection(&g_window_lock);
        g_windows.clear();
        g_can_size_windows.clear();
        LeaveCriticalSection(&g_window_lock);
    }
    InterlockedExchange(&g_locked, 0);
    InterlockedExchange(&g_is_gb_founded, 0);
    InterlockedExchange(&g_allow_all_session, 0);
}

extern "C" __declspec(dllexport) void JiyuGuardRefresh() {
    ReadPolicy();
    LoadWhitelist();
}

// 仅供本机自测夹具使用：没有共享内存时也能切换策略位。
extern "C" __declspec(dllexport) void JiyuGuardSetPolicy(unsigned int flags) {
    InterlockedExchange(&g_flags, static_cast<LONG>(flags));
}

extern "C" __declspec(dllexport) unsigned int JiyuGuardGetPolicy() {
    return static_cast<unsigned int>(g_flags);
}

extern "C" __declspec(dllexport) unsigned int JiyuGuardHookMask() {
    return static_cast<unsigned int>(g_hooked & 0xFFFFFFFFull);
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        g_module = module;
        g_current_pid = GetCurrentProcessId();
        DisableThreadLibraryCalls(module);
    } else if (reason == DLL_PROCESS_DETACH) {
        JiyuGuardUninstall();
    }
    return TRUE;
}
