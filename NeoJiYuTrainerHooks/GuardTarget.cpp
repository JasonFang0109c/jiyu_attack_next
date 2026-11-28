// 课堂防护注入测试目标：只保持进程存活，供 Python 注入与卸载 DLL。
#include <windows.h>

int wmain() {
    Sleep(15000);
    return 0;
}