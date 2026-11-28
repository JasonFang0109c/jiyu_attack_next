// 广播窗口右键菜单自测夹具：创建带“广播”标题的窗口，加载 Hooks.dll，
// 验证菜单线程完成子类化，并在卸载后恢复原窗口过程。
// 只在本进程内运行，不注入其它程序，不访问网络。
#include <windows.h>

#include <cstdio>

namespace {

using InstallFn = BOOL(WINAPI*)();
using UninstallFn = void(WINAPI*)();

void PumpMessages(DWORD milliseconds) {
    const DWORD deadline = GetTickCount() + milliseconds;
    MSG message = {};
    while (GetTickCount() < deadline) {
        while (PeekMessageW(&message, nullptr, 0, 0, PM_REMOVE)) {
            TranslateMessage(&message);
            DispatchMessageW(&message);
        }
        Sleep(20);
    }
}

void WriteLine(FILE* file, const char* key, long long value) {
    std::fprintf(file, "%s=%lld\n", key, value);
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc < 2) {
        return 2;
    }

    WNDCLASSW window_class = {};
    window_class.lpfnWndProc = DefWindowProcW;
    window_class.hInstance = GetModuleHandleW(nullptr);
    window_class.lpszClassName = L"JiyuGuardMenuFixture";
    if (RegisterClassW(&window_class) == 0) {
        return 3;
    }
    HWND window = CreateWindowExW(0, window_class.lpszClassName, L"广播测试窗口",
                                  WS_OVERLAPPEDWINDOW | WS_VISIBLE, 100, 100, 480, 320,
                                  nullptr, nullptr, window_class.hInstance, nullptr);
    if (window == nullptr) {
        return 4;
    }

    wchar_t module[MAX_PATH] = {};
    GetModuleFileNameW(nullptr, module, MAX_PATH);
    wchar_t* slash = wcsrchr(module, L'\\');
    if (slash != nullptr) {
        *slash = L'\0';
    }
    wchar_t dll_path[MAX_PATH] = {};
    swprintf_s(dll_path, L"%s\\Hooks.dll", module);

    HMODULE guard = LoadLibraryW(dll_path);
    if (guard == nullptr) {
        return 5;
    }
    auto install = reinterpret_cast<InstallFn>(GetProcAddress(guard, "JiyuGuardInstall"));
    auto uninstall =
        reinterpret_cast<UninstallFn>(GetProcAddress(guard, "JiyuGuardUninstall"));
    if (install == nullptr || uninstall == nullptr) {
        return 6;
    }

    FILE* out = nullptr;
    if (_wfopen_s(&out, argv[1], L"w") != 0 || out == nullptr) {
        return 7;
    }

    const LONG_PTR original =
        static_cast<LONG_PTR>(GetWindowLongPtrW(window, GWLP_WNDPROC));
    const BOOL installed = install();
    PumpMessages(1200);
    const LONG_PTR subclassed =
        static_cast<LONG_PTR>(GetWindowLongPtrW(window, GWLP_WNDPROC));

    WriteLine(out, "installed", installed);
    WriteLine(out, "subclassed", subclassed != original);

    uninstall();
    PumpMessages(900);
    const LONG_PTR restored =
        static_cast<LONG_PTR>(GetWindowLongPtrW(window, GWLP_WNDPROC));
    WriteLine(out, "restored", restored == original);

    std::fclose(out);
    DestroyWindow(window);
    FreeLibrary(guard);
    return 0;
}
