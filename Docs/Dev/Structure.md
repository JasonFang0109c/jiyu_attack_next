<div align="center">
<h1>项目结构</h1>
<p>
   <img alt="Python 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=212121">
   <img alt="PySide6" src="https://img.shields.io/badge/GUI-PySide6-41CD52?style=for-the-badge&logo=qt&logoColor=white&labelColor=212121">
</p>
<p><a href="../../README.md">← 返回项目首页</a> 丨 <a href="Build.md">EXE 构建</a> 丨 <a href="Versioning.md">版本规范</a> 丨 <a href="Contributing.md">开发与提交规范</a></p>
</div>

---

仓库按四个一级项目划分：Python 核心包 `NeoJiYuTrainer/`、原生课堂防护 `NeoJiYuTrainerHooks/`、可选内核驱动 `NeoJiYuTrainerDriver/`、PySide6 界面 `NeoJiYuTrainerUI/`；打包、测试与文档分别独立。核心包不依赖 Qt，界面只调用核心服务，原生项目各自独立构建；核心包唯一的 Qt 装配入口是 `NeoJiYuTrainer/Start/Gui.py`。

下面列出主要文件，常规包内的 `__init__.py` 省略。

```text
NeoJiYuTrainer/
|-- .github/workflows/
|   |-- Build.yml                   # 可复用打包流程
|   |-- NightlyBuild.yml           # Nightly 构建与滚动预发布
|   `-- Release.yml                 # 正式版发布（仅手动触发）
|-- README.md                       # 项目介绍与文档导航
|-- AGENTS.md                       # 仓库协作索引：阅读范围与硬性约束
|-- .gitmessage                     # Conventional Commits 提交模板
|-- LICENSE                         # GNU General Public License v3.0
|-- requirements.txt                # GUI 与构建依赖
|-- requirements-dev.txt            # 本地开发工具
|-- pyproject.toml                  # ruff 配置
|-- NeoJiYuTrainer/                 # 核心包：业务、报文、系统适配、公共基础
|   |-- __init__.py                 # 重新导出版本号
|   |-- __main__.py                 # python -m NeoJiYuTrainer 与 PyInstaller 入口
|   |-- Start/
|   |   |-- Service.py              # GUI / CLI 与隐藏助手入口分流
|   |   |-- Parser.py               # 装配功能分组子命令
|   |   |-- Cli.py                  # CLI 分发与日志生命周期
|   |   `-- Console.py              # 接回调用方控制台与标准流
|   |-- Features/                   # 按用户功能组织，全部不依赖 Qt
|   |   |-- About/                  # 无业务逻辑，页面在界面项目
|   |   |-- Home/                   # 无业务逻辑，页面在界面项目
|   |   |-- Command/Cli.py          # 命令
|   |   |-- Device/Cli.py           # 设备操作
|   |   |-- Message/                # Service.py、Cli.py：文本消息
|   |   |-- Files/                  # Service.py、Cli.py：文件传送
|   |   |-- Classroom/              # Data.py、Windows.py、Passwords.py、Service.py
|   |   |-- Student/                # Data.py、Service.py、Cli.py
|   |   |-- Uninstall/Service.py    # 快捷方式、数据目录与驱动服务清理
|   |   |-- Shell/                  # Service.py、Cli.py：反弹终端
|   |   |-- Settings/                   # Data.py、Service.py、Cli.py：发送参数与协调
|   |   |-- Names/                  # Data.py、Service.py：设备备注
|   |   |-- Logs/Data.py            # 日志实体与等级
|   |   `-- Settings/               # Data.py、Service.py：设置键与存储
|   |-- Packets/
|   |   |-- Constants.py            # 报文数组、命令表与容量常量
|   |   |-- Codec.py                # 报文构造、文本编码与消息分片
|   |   |-- BlueScreen.py          # 蓝屏脚本临时托管
|   |   `-- Elevated.py             # 提权助手的报文辅助
|   |-- System/
|   |   |-- Net/
|   |   |   |-- Data.py             # 送达状态与结果数据
|   |   |   |-- Targets.py          # 目标地址解析与计数
|   |   |   |-- Local.py            # 本机地址选择与监听地址校验
|   |   |   |-- Reachability.py     # ICMP 与 ARP 探测
|   |   |   `-- Udp.py              # UDP 发送与送达结果采集
|   |   `-- Windows/
|   |       |-- Command.py          # Windows 命令执行与输出解码
|   |       |-- Process.py          # 进程枚举、路径、存活校验与结束
|   |       |-- Ports.py            # iphlpapi 端口到进程映射
|   |       |-- Guard.py            # 课堂防护 DLL 注入、策略与远程命令共享内存
|   |       |-- DriverLoader.py     # 可选内核驱动服务与 IOCTL 封装
|   |       |-- NetFilter.py        # 卸载极域 TDNetFilter 网络过滤驱动
|   |       |-- Hotkey.py           # 热键文本解析与虚拟键表（纯解析）
|   |       `-- Elevation.py        # UAC 隐藏助手与结果回传
|   |-- Shared/
|   |   |-- Config.py               # JSONC 解析与原子读写
|   |   |-- Crash.py                # 未捕获异常与硬崩溃的报告与待提示标记
|   |   |-- Settings.py             # 通用分组设置存储
|   |   |-- Paths.py                # 项目根目录与便携数据路径
|   |   |-- Resources.py            # resource_path 静态资源定位
|   |   |-- Version.py              # __version__ 唯一来源与显示版本
|   |   |-- BuildInfo.py           # 构建时间与版本文本
|   |   |-- BuildVariant.py        # 正常版与调试版标记
|   |   `-- Logs/
|   |       |-- Cli.py              # 无 Qt 的命令行日志
|   |       `-- Levels.py           # 日志等级与构建变体阈值
|   `-- Resources/
|       |-- Icons/App.svg           # 唯一静态图标源
|       `-- Native/                 # 随包 DLL、SYS 与上游许可证
|           |-- GuardX86.dll
|           |-- GuardX64.dll
|           |-- LICENSE-JiYuTrainer.txt
|           |-- README.md
|           `-- Driver/JiYuGuardDriver.sys
|-- NeoJiYuTrainerHooks/            # 原生课堂防护 DLL，独立构建
|   |-- README.md
|   |-- Build.bat
|   |-- Hooks.cpp                   # 注入、策略与 Hook 主体
|   |-- Menu.cpp                   # 广播窗口右键菜单
|   |-- Menu.h
|   |-- Policy.h                    # 防护位与共享内存约定
|   |-- Remote.h                    # 远程命令确认协议
|   |-- GuardTarget.cpp
|   |-- DisasmLib/                 # 第三方反汇编库，原样保留
|   `-- Mhook/                      # 第三方 Hook 库，原样保留
|-- NeoJiYuTrainerDriver/           # 可选 WDM 驱动，独立构建
|   |-- Build.bat
|   |-- Build.ps1
|   |-- Driver.c                    # 驱动入口、IOCTL 分发与强杀编排
|   |-- Driver.h
|   |-- IoCtl.h                     # 设备名、IOCTL 功能码与请求结构
|   |-- Protect.c                   # ObRegisterCallbacks 保护
|   |-- Protect.h
|   |-- UnExp.c                     # 未导出例程定位与逐线程强杀
|   `-- UnExp.h
|-- NeoJiYuTrainerUI/               # PySide6 界面:只调用核心服务
|   |-- __init__.py
|   |-- Features/                   # 各功能的界面适配,与核心包功能目录同名
|   |   |-- About/Gui/Page.py
|   |   |-- Classroom/Gui/          # Page.py(三个标签页)、Service.py
|   |   |-- Command/Gui/Page.py
|   |   |-- Device/Gui/Page.py
|   |   |-- Files/Gui/              # Page.py、Service.py
|   |   |-- Home/Gui/Page.py
|   |   |-- Logs/Gui/               # Data.py(LogStore)、Page.py、Service.py
|   |   |-- Message/Gui/            # Page.py、Service.py
|   |   |-- Names/Gui/              # Data.py(DeviceAliasStore)、Page.py
|   |   |-- Settings/Gui/Page.py
|   |   |-- Shell/Gui/Page.py
|   |   `-- Student/Gui/            # Page.py、Service.py
|   `-- Gui/                        # 窗口、导航、控件、后台任务与 Qt 适配
|       |-- __main__.py             # python -m NeoJiYuTrainerUI.Gui
|       |-- Data.py                 # 仅 ConnectionState
|       |-- Service.py              # 通用发送交互、提示与结果收尾
|       |-- Resources.py            # QIcon 适配
|       |-- Theme.py                # WinUI 视觉常量
|       |-- Splash.py               # 启动遮罩
|       |-- WindowEffect.py        # 窗口材质适配
|       |-- Hotkey.py               # 全局热键管理器与 Qt 原生事件过滤
|       |-- Widgets/
|       |   |-- Common.py           # 卡片、浮出层圆角与连接参数
|       |   `-- Page.py             # 页面基类、顶部导航容器、文件树与日志表格
|       |-- Menu/
|       |   |-- Sidebar.py          # 侧边栏绘制与宽度动画
|       |   `-- Service.py          # 一级导航、页面路由与返回按钮
|       |-- Workers/
|       |   |-- Tasks.py            # SendWorker / ProbeWorker / TaskWorker
|       |   `-- Service.py          # 任务队列、取消与线程生命周期
|       `-- Window/
|           |-- Data.py             # 窗口、导航与功能分类常量
|           |-- Main.py             # MainWindow 装配、信号与 Qt 槽
|           |-- Service.py          # 主题、材质、位置与窗口设置
|           `-- Tray.py             # 托盘菜单、关闭行为与退出
|-- Pack/
|   |-- Build.ps1                   # EXE 构建脚本
|   |-- CleanBuild.ps1             # 构建产物清理
|   |-- GenVersionInfo.py         # EXE 版本资源生成器
|   |-- SignDriver.ps1             # 驱动签名辅助
|   |-- NeoJiYuTrainer.spec         # PyInstaller 配置
|   `-- Hooks/hook-scipy.special._ufuncs.py
|-- Scripts/
|   |-- RunGui.ps1                 # 使用虚拟环境启动 GUI
|   `-- TestLocalIp.py            # 本机 IPv4 报文收发自测
|-- Tests/
|   |-- Fixtures/Offline.py         # 离线网络替身与共用 fixture
|   |-- Unit/                       # 报文、地址、业务与配置单元测试
|   |-- Integration/                # 入口、CLI 生命周期与跨模块协作
|   |   `-- TestLayout.py          # 依赖方向、显式导入与无 Qt 校验
|   |-- Gui/                        # 窗口、页面、日志与截图工具
|   `-- Pack/                       # 工作流与版本资源测试
`-- Docs/
    |-- Usage/
    |   |-- Cli.md
    |   `-- Gui.md
    `-- Dev/
        |-- Structure.md
        |-- Build.md
        |-- Style.md
        |-- Versioning.md
        `-- Contributing.md
```

## 模块关系

### 入口与命令行

- `NeoJiYuTrainer/__main__.py` 保留 `python -m NeoJiYuTrainer` 与 PyInstaller 入口,交给 `NeoJiYuTrainer/Start/Service.py` 分流。无参数时延迟导入 `NeoJiYuTrainer/Start/Gui.py`;带参数时进入 `NeoJiYuTrainer/Start/Cli.py`,CLI 路径不导入 Qt。
- `NeoJiYuTrainer/Start/Gui.py` 是核心包唯一的 Qt 装配入口:负责 QApplication、单实例、使用须知、主题与窗口材质、启动遮罩、异常日志和事件循环,主窗口与页面从 `NeoJiYuTrainerUI/` 取。这一层之外的核心包模块导入时不加载 Qt 与界面项目,由 `Tests/Integration/TestLayout.py` 断言。
- `NeoJiYuTrainer/Start/Console.py` 的 `_show_cli_console()` 在 CLI 模式下把标准流接回调用方终端或重定向目标，不新建控制台。`--firewall-helper`、`--student-helper` 由启动层转交对应业务服务，不显示控制台。
- `NeoJiYuTrainer/Start/Parser.py` 负责装配解析器，显式调用各功能 `Features/*/Cli.py` 的 `register()`，由功能模块注册自己的参数；`build_group_parser()` 提供与页面对应的分组子命令。
- `NeoJiYuTrainer/Start/Cli.py` 管理解析器选择、日志生命周期和调用分发；功能 CLI 负责终端输入输出并调用自身业务服务或共用发送服务。可复用的业务逻辑不放进参数解析器。

### 业务与基础模块

| 模块 | 职责与依赖边界 |
| --- | --- |
| `NeoJiYuTrainer/Features/<功能>/Service.py` | 与界面无关的业务流程；按需调用报文、系统适配与公共基础，不导入 Qt。并非每个功能都需要单独服务，命令和设备功能共用发送服务。 |
| `NeoJiYuTrainer/Features/<功能>/Data.py` | 功能数据、设置键、默认值与规范化。界面侧的信号适配放在界面项目的对应页面目录，不回流到核心包。 |
| `Features/Settings/` | `SendOptions`、参数校验、报文准备和发送协调；供不同页面与 CLI 发送功能复用。 |
| `Features/Classroom/` | 课堂助手：`Windows.py` 用 `ctypes` 枚举并修复广播、黑屏与全屏窗口，`Passwords.py` 读取并解密极域卸载密码，`Service.py` 组合窗口与学生端状态并保存看护设置。课堂防护通过 `System/Windows/Guard.py` 注入进程内 DLL，支持五个开关，其中“监控远程命令”把 `CreateProcess`/`WinExec` 请求写入命名共享内存，由界面逐条允许或拒绝。窗口规则与密码算法移植自 JiYuTrainer（MIT）；`Classroom/Service.py` 还提供卸载极域网络过滤驱动 `TDNetFilter` 的入口。 |
| `Features/{files,student,shell}/` | 分别承载文件传送、学生端进程与终端业务；平台命令、地址解析和套接字操作复用 `System/`。学生端的常量与设置键在 `Student/Data.py`，进程识别、定位、启停与提权助手在 `Student/Service.py`。 |
| `Features/Uninstall/` | 卸载服务：删除桌面与开始菜单快捷方式、可选删除用户数据，并在退出后清理安装目录；由设置页和 `local uninstall` 共用。 |
| `Packets/` | `Constants.py` 保存报文数组和命令表，`Codec.py` 负责构造、编码与分片；`BlueScreen.py` 临时托管蓝屏脚本；不负责界面。 |
| `System/Net/` | 目标解析、本机地址、UDP 发送、ICMP/ARP 探测与送达结果；结果数据在 `Data.py`。 |
| `System/Windows/` | Windows 命令、进程枚举与结束、端口表、提权助手、热键解析与可选内核驱动接口。进程与端口直接走 `kernel32` 与 `iphlpapi`，不依赖 `tasklist` / `netstat` 的文本输出。`Guard.py` 负责课堂防护 DLL 的注入、策略与远程命令共享内存；`DriverLoader.py` 只封装 `sc.exe` 与 IOCTL，不在导入时加载驱动；`Hotkey.py` 只做文本解析，不创建窗口或消息循环。 |
| `Shared/` | JSONC、设置存储、数据路径、构建信息、版本与日志基础；不依赖界面功能。 |
| `Resources/` | 仅放静态资源。图标源为 `Icons/App.svg`；`Native/` 放课堂防护的 x86/x64 DLL、可选内核驱动 `Driver/JiYuGuardDriver.sys` 与上游许可证。运行时通过 `Shared/Resources.py` 的 `resource_path()` 统一定位源码与解包目录，Qt 图标由界面项目的 `Resources.py` 适配。 |
| `NeoJiYuTrainerHooks/` | 独立原生项目：Hook DLL、窗口处理、输入拦截、远程命令与广播窗口菜单。由 `Build.bat` 单独构建，产物由 `Pack/` 收集进 `Resources/Native/`；Python 侧只通过 `Guard.py` 的注入与共享内存协议交互。`disasm-lib`、`mhook` 是第三方裸源码，原样保留。 |
| `NeoJiYuTrainerDriver/` | 独立原生项目：WDM 驱动、自保护、进程强杀与 IOCTL。由 `Build.bat` 单独构建，产物由 `Pack/SignDriver.ps1` 签名后随包分发；Python 侧只通过 `DriverLoader.py` 调用，默认不加载。 |

版本号唯一来源是 `Shared/Version.py` 的 `__version__`；核心包 `__init__.py` 只重新导出，`Shared/BuildInfo.py` 转调版本读取接口并提供构建时间。`Packets/Constants.py` 只维护报文相关常量，不能把版本号放回该文件。

### GUI 装配与功能适配

- `NeoJiYuTrainerUI/Gui/Window/Main.py` 的 `MainWindow` 显式创建页面和服务、连接信号并保留 Qt 槽与事件入口；具体交互交给 `Gui/Service.py`、`Gui/Menu/Service.py`、`Gui/Workers/Service.py`、`Gui/Window/Service.py`、`Gui/Window/Tray.py` 和各页面目录的 `Service.py`。
- 页面位于 `NeoJiYuTrainerUI/Features/<功能>/Gui/Page.py`,与核心包同名功能目录一一对应;同目录的 `Service.py` 负责页面内交互协调,需要 Qt 信号适配时放同目录的 `Data.py`。界面只调用核心包的服务与数据约定,不导入核心包内部的私有实现,也不把 Qt 对象传回核心包。
- 导航常量位于 `Gui/Window/Data.py`，`Gui/Menu/Service.py` 注册一级入口、页面路由与返回按钮；`Gui/Menu/Sidebar.py` 处理侧边栏绘制、宽度动画与顶部工具按钮排列。侧边栏只有一级入口，组内页面由 `TabbedPage` 用 `Pivot` 承载。
- `Gui/Widgets/Common.py` 提供 `FluentCard`、`FluentDialog`、`FluentComboBox`、浮出层圆角的覆盖函数，连接参数与任务栏；`Gui/Widgets/Page.py` 提供页面基类、文件树和日志表格；`Gui/Theme.py` 集中保存视觉数值。
- `Gui/Workers/Tasks.py` 定义后台线程与结果信号，`Gui/Workers/Service.py` 管理排队、取消和线程收尾。失败信号携带异常消息与堆栈，由 GUI 主线程恢复界面状态。
- 只有 `Gui/Data.py` 的 `ConnectionState` 属于跨页面共用数据；设备备注的数据约定与业务在 `Features/Names/Data.py`、`Service.py`，`Features/Names/Gui/Data.py` 的 `DeviceAliasStore` 只做 Qt 信号适配；日志实体在 `Features/Logs/Data.py`，带线程通知与持久化的 `LogStore` 位于 `Features/Logs/Gui/Data.py`；设置键与存储入口在 `Features/Settings/Data.py`、`Service.py`，页面在 `Features/Settings/Gui/Page.py`。
- `settings.json` 中的 `core`、`gui` 分组是既有持久化格式，不随源代码目录划分改变。通用 JSONC 与分组存储分别由 `Shared/Config.py`、`Shared/Settings.py` 提供。

### 打包与测试

- `Pack/` 只放构建脚本、PyInstaller 配置、版本资源生成器、签名脚本与打包用 hooks；运行时入口为 `NeoJiYuTrainer/__main__.py`，静态图标按 `NeoJiYuTrainer/Resources/Icons/App.svg` 收集。
- `.github/workflows/Build.yml` 为可复用打包流程；`NightlyBuild.yml` 在推送 `main` 且涉及核心包、界面项目、`Pack/`、`Scripts/`、`requirements.txt` 或工作流文件时构建；`Release.yml` 仍仅手动触发，详见[版本规范](Versioning.md)。
- `Tests/Unit/` 检查报文、业务与配置单元;`Tests/Integration/` 检查入口和跨模块协作,其中 `TestLayout.py` 检查底层依赖方向、显式导入、核心包除 `Start/` 外不出现 Qt 与界面项目导入,并确认业务模块能在没有 Qt 的环境里导入;`Tests/Gui/` 检查窗口与页面,`Tests/Pack/` 检查版本、工作流与打包布局。公共离线替身集中在 `Tests/Fixtures/Offline.py`,测试不执行真实目标发送或网络配置变更。
- 全量发现使用 `python -B -m unittest discover -s Tests -t .`，保证按 `Tests` 包导入；单个模块使用完整包名，例如 `python -B -m unittest Tests.Gui.TestWindow -v`。截图工具为 `python -B -m Tests.Gui.VerifyGui --screenshot <截图路径>`。
- `Scripts/` 保留虚拟环境启动与本机自测入口；`TestLocalIp.py` 是真实本机报文收发自测，与离线测试套件分开。

## 新增功能

1. 在 `NeoJiYuTrainer/Features/<功能>/` 建立有独立职责的功能包；业务参数与数据约定按需放入 `Data.py`，可复用流程放入不依赖 Qt 的 `Service.py`。通用编解码、网络/系统接口和配置继续复用各自基础模块。
2. 需要 CLI 时，在功能的 `Cli.py` 定义 `register()` 并注册本功能参数，在 `Start/Parser.py` 的对应分组显式调用；在 `Start/Cli.py` 接入执行分发。
3. 需要界面时,在 `NeoJiYuTrainerUI/Features/<功能>/Gui/` 下定义 `Page.py`,交互协调按需放入同目录的 `Service.py`,Qt 数据通知适配按需放入 `Data.py`。在 `Gui/Window/Main.py` 显式导入、创建页面和服务、连接信号与槽,并更新 `Gui/Window/Data.py` 的导航描述及相关菜单装配;仅有内部服务的功能不必创建页面。
4. 耗时任务交给 `NeoJiYuTrainerUI/Gui/Workers/` 的线程与任务服务；通用控件复用 `Gui/Widgets/`。核心服务保持独立于窗口和 Qt 对象，界面不得反向被核心包导入。
5. 涉及原生行为时，修改 `NeoJiYuTrainerHooks/` 或 `NeoJiYuTrainerDriver/` 的源码与 `Build.bat`，把产物同步到 `NeoJiYuTrainer/Resources/Native/`，并在 `Pack/NeoJiYuTrainer.spec` 里确认收集规则。
6. 业务、报文与参数单元测试放入 `Tests/Unit/`，CLI/跨模块流程放入 `Tests/Integration/`，界面与线程行为放入 `Tests/Gui/`，打包或版本变化补 `Tests/Pack/`，共用替身复用 `Tests/Fixtures/Offline.py`。按影响范围更新 [CLI 文档](../Usage/Cli.md)、[GUI 文档](../Usage/Gui.md) 与本结构说明；新增依赖写入依赖清单并说明打包影响。提交类型与作用域按[项目作用域](Contributing.md#项目作用域)选择。

## 本地生成目录

| 路径 | 用途 | 清理方式 |
| --- | --- | --- |
| `.venv/` | Python 虚拟环境 | 保留供开发和构建使用 |
| `Build/` | 全部生成物：PyInstaller 中间文件、构建资源、测试与截图临时目录、驱动签名临时材料 | 整目录可删，构建脚本按需重建；构建前清理会自动删除 |
| `Output/` | 最终 EXE | 保留需要运行或分发的产物 |
| `Data/` | 便携数据目录：EXE 同级生成，源码运行时位于项目根目录；保存设备备注、关闭窗口行为、界面日志 `runtime.log`、命令行日志 `cli.log`，以及崩溃报告目录 `Crash/`（未捕获异常与硬崩溃各留一份文本，`Fatal.log` 记硬崩溃） | 需要保留配置时随 EXE 一起移动，删除后恢复默认；也可在 GUI“设置”页底部清除；脚本与文档都不删除它 |

以上目录及 `__pycache__/`、工具缓存均由 `.gitignore` 排除（其中用户数据按 `/Data/` 规则排除），不提交 Git。根目录不保留重复的旧入口文件或遗留截图。

## 相关文档

- [CLI 模式使用说明](../Usage/Cli.md)
- [GUI 模式使用说明](../Usage/Gui.md)
- [EXE 构建说明](Build.md)
- [开发与提交规范](Contributing.md)
