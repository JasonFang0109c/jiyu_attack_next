# 课堂防护原生组件

`guard.dll` 是课堂助手的可选进程内防护模块，只提供四类窄接口拦截：

- 阻止屏幕监视：伪造桌面窗口、桌面 DC 与显示 DC，拒绝关闭桌面合成。
- 阻止远程控制：拦截低级鼠标、键盘与 CBT 钩子，拦截 `SendInput` 与 `mouse_event`。
- 禁止关闭窗口：拒绝其它进程发来的 `WM_CLOSE` / `WM_DESTROY`。
- 禁止结束进程：拒绝其它进程对本进程调用 `TerminateProcess`。

策略通过命名共享内存 `Local\JiyuGuardPolicy_<pid>` 传递，Python 侧见
`app/system/windows/guard.py`。DLL 不安装驱动、不写注册表、不改系统设置，
卸载时恢复全部钩子并释放自身。

## 构建

需要 Windows x64 环境中的 MSVC 与 Windows SDK。仓库开发环境使用 Windows
容器构建，宿主机不安装编译器：

```powershell
powershell -ExecutionPolicy Bypass -File .\pack\native\build-guard.ps1
```

脚本在容器 `jiyu-native` 内分别执行 `build.bat x64` 与 `build.bat x86`，产物
写入 `build/native/guard/`。把 `guard_x64.dll` 与 `guard_x86.dll` 复制到
`app/resources/native/` 后重新打包 EXE。

`guard_fixture_*.exe` 会自动加载同目录的 DLL 并验证每类钩子，只在构建容器
或隔离测试环境中运行。

## 第三方代码

- `mhook/`：Copyright 2007-2008 Marton Anka，MIT 许可证。
- `disasm-lib/`：Copyright 2004 Matt Conover，随 JiYuTrainer 以 MIT 许可证分发。
- 上游项目：JiYuTrainer，Copyright 2019 Mengyu，MIT 许可证，见
  `app/resources/native/LICENSE-JiYuTrainer.txt`。
