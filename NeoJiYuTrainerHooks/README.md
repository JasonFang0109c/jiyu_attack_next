# 课堂防护原生组件(NeoJiYuTrainerHooks)

本目录对应 JiYuTrainer 上游的 `JiYuTrainerHooks` 工程,是独立的原生项目边界:只放课堂防护 DLL、广播窗口菜单与自测夹具的 C++ 源码,不依赖 Python 代码即可编译。

`guard.dll` 是课堂助手的可选进程内防护模块，提供五类窄接口拦截与一个广播窗口菜单：

- 阻止屏幕监视：伪造桌面窗口、桌面 DC 与显示 DC，拒绝关闭桌面合成。
- 阻止远程控制：拦截低级鼠标、键盘与 CBT 钩子，拦截 `SendInput` 与 `mouse_event`。
- 禁止关闭窗口：拒绝其它进程发来的 `WM_CLOSE` / `WM_DESTROY`。
- 禁止结束进程：拒绝其它进程对本进程调用 `TerminateProcess`。
- 监控远程命令：拦截 `CreateProcessW/A` 与 `WinExec`，通过命名共享内存与界面逐条确认。
- 广播窗口右键菜单：在注入进程内子类化标题含“广播/演示/共享”的窗口，提供全屏、还原、置顶与关闭。

策略通过命名共享内存 `Local\JiyuGuardPolicy_<pid>` 传递，Python 侧见
`NeoJiYuTrainer/System/Windows/Guard.py`。DLL 不安装驱动、不写注册表、不改系统设置，
卸载时恢复全部钩子并释放自身。

## 构建

需要 Windows x64 环境中的 MSVC 与 Windows SDK。仓库开发环境使用 Windows
容器构建，宿主机不安装编译器：

```powershell
powershell -ExecutionPolicy Bypass -File .\NeoJiYuTrainerHooks\Build.ps1
```

脚本在容器 `jiyu-native` 内分别执行 `Build.bat x64` 与 `Build.bat x86`，产物
写入 `Build/Native/Hooks/`。把 `GuardX64.dll` 与 `GuardX86.dll` 复制到
`NeoJiYuTrainer/Resources/Native/` 后重新打包 EXE。

`guard_fixture_*.exe` 会自动加载同目录的 DLL 并验证每类钩子，`menu_fixture_*.exe`
额外创建“广播测试窗口”验证右键菜单子类化与卸载恢复，二者只在构建容器或隔离
测试环境中运行。

## 第三方代码

- `Mhook/`：Copyright 2007-2008 Marton Anka，MIT 许可证。
- `DisasmLib/`：Copyright 2004 Matt Conover，随 JiYuTrainer 以 MIT 许可证分发。
- 上游项目：JiYuTrainer，Copyright 2019 Mengyu，MIT 许可证，见
  `NeoJiYuTrainer/Resources/Native/LICENSE-JiYuTrainer.txt`。
