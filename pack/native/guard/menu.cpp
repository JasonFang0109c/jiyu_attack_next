// 在学生端进程内给极域广播窗口加右键菜单，做法对应 JiYuTrainer 的
// VFixGuangBoWindow / JiYuWndProc：保存原窗口过程后子类化，在 WM_RBUTTONUP
// 时弹出“全屏/还原、置顶、关闭”菜单。代码运行在目标进程内，因此 WNDPROC
// 指针有效，不需要跨进程注入函数地址。
#include <windows.h>

#include <cwchar>

#include "menu.h"

namespace {

constexpr UINT_PTR kMenuFull = 0x4A01;
constexpr UINT_PTR kMenuTopmost = 0x4A02;
constexpr UINT_PTR kMenuClose = 0x4A03;
constexpr int kMaxMenuWindows = 64;
constexpr DWORD kMenuPollMs = 600;

struct MenuWindow {
    HWND hwnd;
    WNDPROC original;
    bool fullscreen;
    LONG original_style;
    LONG original_exstyle;
    RECT original_rect;
    bool has_original_rect;
};

MenuWindow g_menu_windows[kMaxMenuWindows] = {};
int g_menu_count = 0;
CRITICAL_SECTION g_menu_lock;
bool g_menu_lock_ready = false;
HANDLE g_menu_thread = nullptr;
volatile LONG g_menu_stop = 0;

bool IsBroadcastTitle(const wchar_t* title) {
    if (title == nullptr) {
        return false;
    }
    return wcsstr(title, L"广播") != nullptr || wcsstr(title, L"演示") != nullptr ||
           wcsstr(title, L"共享") != nullptr || wcscmp(title, L"屏幕演播室窗口") == 0;
}

bool IsCurrentProcessWindow(HWND hwnd) {
    DWORD pid = 0;
    GetWindowThreadProcessId(hwnd, &pid);
    return pid == GetCurrentProcessId();
}

LRESULT CALLBACK MenuWndProc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam);

MenuWindow* FindWindow(HWND hwnd) {
    for (int index = 0; index < g_menu_count; ++index) {
        if (g_menu_windows[index].hwnd == hwnd) {
            return &g_menu_windows[index];
        }
    }
    return nullptr;
}

void RestoreWindow(MenuWindow* item) {
    if (item->original != nullptr && IsWindow(item->hwnd)) {
        SetWindowLongPtrW(item->hwnd, GWLP_WNDPROC,
                          reinterpret_cast<LONG_PTR>(item->original));
    }
    item->original = nullptr;
}

void RemoveWindowAt(int index) {
    RestoreWindow(&g_menu_windows[index]);
    g_menu_windows[index] = g_menu_windows[g_menu_count - 1];
    --g_menu_count;
}

bool ReadWindowTitle(HWND hwnd, wchar_t* title, int capacity) {
    if (title == nullptr || capacity <= 0) {
        return false;
    }
    title[0] = L'\0';
    DWORD_PTR copied = 0;
    // GetWindowTextW 在跨线程窗口无响应时会无限等待；菜单线程改用带超时的
    // WM_GETTEXT，避免一个卡死的窗口把整个右键菜单线程拖住。
    LRESULT result = SendMessageTimeoutW(hwnd, WM_GETTEXT,
                                         static_cast<WPARAM>(capacity),
                                         reinterpret_cast<LPARAM>(title),
                                         SMTO_ABORTIFHUNG | SMTO_BLOCK, 100,
                                         &copied);
    if (result == 0 && copied == 0) {
        return false;
    }
    title[capacity - 1] = L'\0';
    return true;
}

void AddWindow(HWND hwnd) {
    if (hwnd == nullptr || !IsWindow(hwnd) || !IsCurrentProcessWindow(hwnd)) {
        return;
    }
    EnterCriticalSection(&g_menu_lock);
    if (FindWindow(hwnd) == nullptr && g_menu_count < kMaxMenuWindows) {
        wchar_t title[256] = {};
        if (ReadWindowTitle(hwnd, title, 256) && IsBroadcastTitle(title)) {
            MenuWindow* item = &g_menu_windows[g_menu_count];
            item->hwnd = hwnd;
            item->fullscreen = false;
            item->original_style = static_cast<LONG>(GetWindowLongPtrW(hwnd, GWL_STYLE));
            item->original_exstyle =
                static_cast<LONG>(GetWindowLongPtrW(hwnd, GWL_EXSTYLE));
            item->has_original_rect = GetWindowRect(hwnd, &item->original_rect) != FALSE;
            item->original =
                reinterpret_cast<WNDPROC>(GetWindowLongPtrW(hwnd, GWLP_WNDPROC));
            SetWindowLongPtrW(hwnd, GWLP_WNDPROC,
                              reinterpret_cast<LONG_PTR>(MenuWndProc));
            ++g_menu_count;
        }
    }
    LeaveCriticalSection(&g_menu_lock);
}

void ApplyFullscreen(MenuWindow* item, bool fullscreen) {
    if (item == nullptr || !IsWindow(item->hwnd)) {
        return;
    }
    HWND hwnd = item->hwnd;
    if (fullscreen) {
        if (!item->has_original_rect) {
            item->has_original_rect = GetWindowRect(hwnd, &item->original_rect) != FALSE;
        }
        item->original_style = static_cast<LONG>(GetWindowLongPtrW(hwnd, GWL_STYLE));
        item->original_exstyle = static_cast<LONG>(GetWindowLongPtrW(hwnd, GWL_EXSTYLE));
        SetWindowLongPtrW(hwnd, GWL_EXSTYLE,
                          static_cast<LONG_PTR>(item->original_exstyle | WS_EX_TOPMOST));
        SetWindowLongPtrW(hwnd, GWL_STYLE,
                          static_cast<LONG_PTR>((item->original_style ^
                                                 (WS_BORDER | WS_OVERLAPPEDWINDOW)) |
                                                WS_SYSMENU));
        const int width = GetSystemMetrics(SM_CXSCREEN);
        const int height = GetSystemMetrics(SM_CYSCREEN);
        SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, width, height, SWP_SHOWWINDOW);
        SendMessageW(hwnd, WM_SIZE, MAKEWPARAM(width, height), 0);
        item->fullscreen = true;
    } else {
        SetWindowLongPtrW(hwnd, GWL_STYLE,
                          static_cast<LONG_PTR>((item->original_style ^
                                                 (WS_BORDER | WS_OVERLAPPEDWINDOW)) |
                                                WS_SYSMENU));
        SetWindowLongPtrW(hwnd, GWL_EXSTYLE,
                          static_cast<LONG_PTR>(item->original_exstyle & ~WS_EX_TOPMOST));
        const int width = GetSystemMetrics(SM_CXSCREEN) * 3 / 4;
        const int height = GetSystemMetrics(SM_CYSCREEN) * 4 / 5;
        const int left = (GetSystemMetrics(SM_CXSCREEN) - width) / 2;
        const int top = (GetSystemMetrics(SM_CYSCREEN) - height) / 2;
        SetWindowPos(hwnd, HWND_NOTOPMOST, left, top, width, height, SWP_SHOWWINDOW);
        SendMessageW(hwnd, WM_SIZE, MAKEWPARAM(width, height), 0);
        item->fullscreen = false;
    }
}

void ToggleTopmost(MenuWindow* item) {
    if (item == nullptr || !IsWindow(item->hwnd)) {
        return;
    }
    LONG exstyle = static_cast<LONG>(GetWindowLongPtrW(item->hwnd, GWL_EXSTYLE));
    const bool topmost = (exstyle & WS_EX_TOPMOST) != 0;
    exstyle = topmost ? (exstyle & ~WS_EX_TOPMOST) : (exstyle | WS_EX_TOPMOST);
    SetWindowLongPtrW(item->hwnd, GWL_EXSTYLE, static_cast<LONG_PTR>(exstyle));
    SetWindowPos(item->hwnd, topmost ? HWND_NOTOPMOST : HWND_TOPMOST, 0, 0, 0, 0,
                 SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW);
}

void ShowContextMenu(MenuWindow* item, HWND hwnd) {
    if (item == nullptr || !IsWindow(item->hwnd)) {
        return;
    }
    POINT point = {};
    GetCursorPos(&point);
    HMENU menu = CreatePopupMenu();
    if (menu == nullptr) {
        return;
    }
    AppendMenuW(menu, MF_STRING, kMenuFull,
                item->fullscreen ? L"取消广播窗口全屏" : L"广播窗口全屏");
    const bool topmost =
        (GetWindowLongPtrW(item->hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST) != 0;
    AppendMenuW(menu, MF_STRING | (topmost ? MF_CHECKED : 0), kMenuTopmost,
                L"广播窗口置顶");
    AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(menu, MF_STRING, kMenuClose, L"关闭广播窗口");
    UINT command = TrackPopupMenu(menu, TPM_RETURNCMD | TPM_LEFTALIGN | TPM_TOPALIGN,
                                  point.x, point.y, 0, hwnd, nullptr);
    DestroyMenu(menu);
    if (command == kMenuFull) {
        ApplyFullscreen(item, !item->fullscreen);
    } else if (command == kMenuTopmost) {
        ToggleTopmost(item);
    } else if (command == kMenuClose) {
        PostMessageW(item->hwnd, WM_CLOSE, 0, 0);
    }
}

LRESULT CALLBACK MenuWndProc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam) {
    MenuWindow* item = nullptr;
    EnterCriticalSection(&g_menu_lock);
    item = FindWindow(hwnd);
    LeaveCriticalSection(&g_menu_lock);
    if (item != nullptr && message == WM_RBUTTONUP) {
        // 菜单命令在窗口过程里同步处理，和上游 TrackPopupMenu 的做法一致。
        EnterCriticalSection(&g_menu_lock);
        ShowContextMenu(item, hwnd);
        LeaveCriticalSection(&g_menu_lock);
        return 0;
    }
    if (item != nullptr && item->original != nullptr) {
        return CallWindowProcW(item->original, hwnd, message, wparam, lparam);
    }
    return DefWindowProcW(hwnd, message, wparam, lparam);
}

void ScanWindows() {
    EnumWindows(
        [](HWND hwnd, LPARAM) -> BOOL {
            AddWindow(hwnd);
            return TRUE;
        },
        0);
    EnterCriticalSection(&g_menu_lock);
    for (int index = g_menu_count - 1; index >= 0; --index) {
        if (!IsWindow(g_menu_windows[index].hwnd)) {
            RemoveWindowAt(index);
        }
    }
    LeaveCriticalSection(&g_menu_lock);
}

DWORD WINAPI MenuThread(LPVOID) {
    while (InterlockedCompareExchange(&g_menu_stop, 0, 0) == 0) {
        ScanWindows();
        Sleep(kMenuPollMs);
    }
    EnterCriticalSection(&g_menu_lock);
    while (g_menu_count > 0) {
        RemoveWindowAt(g_menu_count - 1);
    }
    LeaveCriticalSection(&g_menu_lock);
    return 0;
}

}  // namespace

void StartGuardMenu() {
    if (g_menu_thread != nullptr) {
        return;
    }
    if (!g_menu_lock_ready) {
        InitializeCriticalSection(&g_menu_lock);
        g_menu_lock_ready = true;
    }
    InterlockedExchange(&g_menu_stop, 0);
    g_menu_thread = CreateThread(nullptr, 0, MenuThread, nullptr, 0, nullptr);
}

void StopGuardMenu() {
    if (g_menu_thread == nullptr) {
        return;
    }
    InterlockedExchange(&g_menu_stop, 1);
    WaitForSingleObject(g_menu_thread, 3000);
    CloseHandle(g_menu_thread);
    g_menu_thread = nullptr;
    if (g_menu_lock_ready) {
        EnterCriticalSection(&g_menu_lock);
        while (g_menu_count > 0) {
            RemoveWindowAt(g_menu_count - 1);
        }
        LeaveCriticalSection(&g_menu_lock);
    }
}
