<div align="center">
<h1>项目结构</h1>
<p>
   <img alt="Python 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=212121">
   <img alt="PySide6" src="https://img.shields.io/badge/GUI-PySide6-41CD52?style=for-the-badge&logo=qt&logoColor=white&labelColor=212121">
</p>
<p><a href="../../README.md">← 返回项目首页</a> 丨 <a href="BUILD.md">EXE 构建</a> 丨 <a href="VERSIONING.md">版本规范</a> 丨 <a href="CONTRIBUTING.md">开发与提交规范</a> 丨 <a href="REFACTOR.md">上游骨架重构路线</a></p>
</div>

---

仓库按四个一级项目边界划分：Python 核心包 `NeoJiYuTrainer/`、原生课堂防护 `NeoJiYuTrainerHooks/`、可选内核驱动 `NeoJiYuTrainerDriver/`、PySide6 界面 `NeoJiYuTrainerUI/`；打包、测试与文档分别独立。核心包不依赖 Qt，界面只调用核心服务，原生项目各自独立构建。

> **界面已拆到 `NeoJiYuTrainerUI/`:窗口、导航、控件、后台任务与各功能页面都在该项目的 `gui/` 与 `features/<功能>/gui/` 下。唯一的 Qt 装配入口是核心包的 `NeoJiYuTrainer/start/gui.py`,核心包其余部分导入时不加载 Qt。** `NeoJiYuTrainerHooks/`、`NeoJiYuTrainerDriver/` 已在仓库根目录。

下面列出主要文件，常规包内的 `__init__.py` 省略。

```text
NeoJiYuTrainer/
|-- .github/workflows/
|   |-- build.yml                   # 可复用打包流程
|   |-- nightly-build.yml           # Nightly 构建与滚动预发布
|   `-- release.yml                 # 正式版发布（仅手动触发）
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
|   |-- start/
|   |   |-- service.py              # GUI / CLI 与隐藏助手入口分流
|   |   |-- parser.py               # 装配功能分组子命令
|   |   |-- cli.py                  # CLI 分发与日志生命周期
|   |   `-- console.py              # 接回调用方控制台与标准流
|   |-- features/                   # 按用户功能组织，全部不依赖 Qt
|   |   |-- about/                  # 无业务逻辑，页面在界面项目
|   |   |-- home/                   # 无业务逻辑，页面在界面项目
|   |   |-- command/cli.py          # 命令
|   |   |-- device/cli.py           # 设备操作
|   |   |-- message/                # service.py、cli.py：文本消息
|   |   |-- files/                  # service.py、cli.py：文件传送
|   |   |-- classroom/              # data.py、windows.py、passwords.py、service.py
|   |   |-- firewall/               # service.py、cli.py
|   |   |-- local/                  # service.py、cli.py
|   |   |-- student/                # data.py、service.py、cli.py
|   |   |-- uninstall/service.py    # 快捷方式、数据目录与驱动服务清理
|   |   |-- shell/                  # service.py、cli.py：反弹终端
|   |   |-- send/                   # data.py、service.py、cli.py：发送参数与协调
|   |   |-- names/                  # data.py、service.py：设备备注
|   |   |-- logs/data.py            # 日志实体与等级
|   |   `-- settings/               # data.py、service.py：设置键与存储
|   |-- packets/
|   |   |-- constants.py            # 报文数组、命令表与容量常量
|   |   |-- codec.py                # 报文构造、文本编码与消息分片
|   |   |-- blue_screen.py          # 蓝屏脚本临时托管
|   |   `-- elevated.py             # 提权助手的报文辅助
|   |-- system/
|   |   |-- net/
|   |   |   |-- data.py             # 送达状态与结果数据
|   |   |   |-- targets.py          # 目标地址解析与计数
|   |   |   |-- local.py            # 本机地址选择与监听地址校验
|   |   |   |-- reachability.py     # ICMP 与 ARP 探测
|   |   |   `-- udp.py              # UDP 发送与送达结果采集
|   |   `-- windows/
|   |       |-- command.py          # Windows 命令执行与输出解码
|   |       |-- process.py          # 进程枚举、路径、存活校验与结束
|   |       |-- ports.py            # iphlpapi 端口到进程映射
|   |       |-- guard.py            # 课堂防护 DLL 注入、策略与远程命令共享内存
|   |       |-- driver.py           # 可选内核驱动服务与 IOCTL 封装
|   |       |-- hotkey.py           # 热键文本解析与虚拟键表（纯解析）
|   |       `-- elevation.py        # UAC 隐藏助手与结果回传
|   |-- shared/
|   |   |-- config.py               # JSONC 解析与原子读写
|   |   |-- settings.py             # 通用分组设置存储
|   |   |-- paths.py                # 项目根目录与便携数据路径
|   |   |-- resources.py            # resource_path 静态资源定位
|   |   |-- version.py              # __version__ 唯一来源与显示版本
|   |   |-- build_info.py           # 构建时间与版本文本
|   |   |-- build_variant.py        # 正常版与调试版标记
|   |   `-- logs/
|   |       |-- cli.py              # 无 Qt 的命令行日志
|   |       `-- levels.py           # 日志等级与构建变体阈值
|   `-- resources/
|       |-- icons/app.svg           # 唯一静态图标源
|       `-- native/                 # 随包 DLL、SYS 与上游许可证
|           |-- guard_x86.dll
|           |-- guard_x64.dll
|           |-- LICENSE-JiYuTrainer.txt
|           |-- README.md
|           `-- driver/jiyu_guard_driver.sys
|-- NeoJiYuTrainerHooks/            # 原生课堂防护 DLL，独立构建
|   |-- README.md
|   |-- build.bat
|   |-- guard.cpp                   # 注入、策略与 Hook 主体
|   |-- menu.cpp                   # 广播窗口右键菜单
|   |-- menu.h
|   |-- policy.h                    # 防护位与共享内存约定
|   |-- remote.h                    # 远程命令确认协议
|   |-- guard_fixture.cpp           # 构建夹具
|   |-- guard_target.cpp
|   |-- menu_fixture.cpp
|   |-- disasm-lib/                 # 第三方反汇编库，原样保留
|   `-- mhook/                      # 第三方 Hook 库，原样保留
|-- NeoJiYuTrainerDriver/           # 可选 WDM 驱动，独立构建
|   |-- build.bat
|   |-- driver_ioctl.h
|   `-- jiyu_guard_driver.c
|-- NeoJiYuTrainerUI/               # PySide6 界面:只调用核心服务
|   |-- __init__.py
|   |-- features/                   # 各功能的界面适配,与核心包功能目录同名
|   |   |-- about/gui/page.py
|   |   |-- classroom/gui/          # page.py、service.py
|   |   |-- command/gui/page.py
|   |   |-- device/gui/page.py
|   |   |-- files/gui/              # page.py、service.py
|   |   |-- firewall/gui/           # page.py、service.py
|   |   |-- home/gui/page.py
|   |   |-- local/gui/              # page.py、service.py
|   |   |-- logs/gui/               # data.py(LogStore)、page.py、service.py
|   |   |-- message/gui/            # page.py、service.py
|   |   |-- names/gui/              # data.py(DeviceAliasStore)、page.py
|   |   |-- settings/gui/page.py
|   |   |-- shell/gui/page.py
|   |   `-- student/gui/            # page.py、service.py
|   `-- gui/                        # 窗口、导航、控件、后台任务与 Qt 适配
|       |-- __main__.py             # python -m NeoJiYuTrainerUI.gui
|       |-- data.py                 # 仅 ConnectionState
|       |-- service.py              # 通用发送交互、提示与结果收尾
|       |-- resources.py            # QIcon 适配
|       |-- theme.py                # WinUI 视觉常量
|       |-- splash.py               # 启动遮罩
|       |-- window_effect.py        # 窗口材质适配
|       |-- hotkey.py               # 全局热键管理器与 Qt 原生事件过滤
|       |-- widgets/
|       |   |-- common.py           # 卡片、浮出层圆角与连接参数
|       |   `-- page.py             # 页面基类、顶部导航容器、文件树与日志表格
|       |-- menu/
|       |   |-- sidebar.py          # 侧边栏绘制与宽度动画
|       |   `-- service.py          # 一级导航、页面路由与返回按钮
|       |-- workers/
|       |   |-- tasks.py            # SendWorker / ProbeWorker / TaskWorker
|       |   `-- service.py          # 任务队列、取消与线程生命周期
|       `-- window/
|           |-- data.py             # 窗口、导航与功能分类常量
|           |-- main.py             # MainWindow 装配、信号与 Qt 槽
|           |-- service.py          # 主题、材质、位置与窗口设置
|           `-- tray.py             # 托盘菜单、关闭行为与退出
|-- pack/
|   |-- build.ps1                   # EXE 构建脚本
|   |-- clean_build.ps1             # 构建产物清理
|   |-- gen_version_info.py         # EXE 版本资源生成器
|   |-- sign-driver.ps1             # 驱动签名辅助
|   |-- NeoJiYuTrainer.spec         # PyInstaller 配置
|   `-- hooks/hook-scipy.special._ufuncs.py
|-- scripts/
|   |-- run_gui.ps1                 # 使用虚拟环境启动 GUI
|   `-- test_local_ip.py            # 本机 IPv4 报文收发自测
|-- tests/
|   |-- fixtures/offline.py         # 离线网络替身与共用 fixture
|   |-- unit/                       # 报文、地址、业务与配置单元测试
|   |-- integration/                # 入口、CLI 生命周期与跨模块协作
|   |   `-- test_layout.py          # 依赖方向、显式导入与无 Qt 校验
|   |-- gui/                        # 窗口、页面、日志与截图工具
|   `-- pack/                       # 工作流与版本资源测试
`-- docs/
    |-- usage/
    |   |-- CLI.md
    |   `-- GUI.md
    `-- dev/
        |-- STRUCTURE.md
        |-- REFACTOR.md
        |-- BUILD.md
        |-- STYLE.md
        |-- VERSIONING.md
        `-- CONTRIBUTING.md
```

## 模块关系

### 入口与命令行

- `NeoJiYuTrainer/__main__.py` 保留 `python -m NeoJiYuTrainer` 与 PyInstaller 入口,交给 `NeoJiYuTrainer/start/service.py` 分流。无参数时延迟导入 `NeoJiYuTrainer/start/gui.py`;带参数时进入 `NeoJiYuTrainer/start/cli.py`,CLI 路径不导入 Qt。
- `NeoJiYuTrainer/start/gui.py` 是核心包唯一的 Qt 装配入口:负责 QApplication、单实例、使用须知、主题与窗口材质、启动遮罩、异常日志和事件循环,主窗口与页面从 `NeoJiYuTrainerUI/` 取。这一层之外的核心包模块导入时不加载 Qt 与界面项目,由 `tests/integration/test_layout.py` 断言。
- `NeoJiYuTrainer/start/console.py` 的 `_show_cli_console()` 在 CLI 模式下把标准流接回调用方终端或重定向目标，不新建控制台。`--firewall-helper`、`--student-helper` 由启动层转交对应业务服务，不显示控制台。
- `NeoJiYuTrainer/start/parser.py` 负责装配解析器，显式调用各功能 `features/*/cli.py` 的 `register()`，由功能模块注册自己的参数；`build_group_parser()` 提供与页面对应的分组子命令。
- `NeoJiYuTrainer/start/cli.py` 管理解析器选择、日志生命周期和调用分发；功能 CLI 负责终端输入输出并调用自身业务服务或共用发送服务。可复用的业务逻辑不放进参数解析器。

### 业务与基础模块

| 模块 | 职责与依赖边界 |
| --- | --- |
| `NeoJiYuTrainer/features/<功能>/service.py` | 与界面无关的业务流程；按需调用报文、系统适配与公共基础，不导入 Qt。并非每个功能都需要单独服务，命令和设备功能共用发送服务。 |
| `NeoJiYuTrainer/features/<功能>/data.py` | 功能数据、设置键、默认值与规范化。界面侧的信号适配放在界面项目的对应页面目录，不回流到核心包。 |
| `features/send/` | `SendOptions`、参数校验、报文准备和发送协调；供不同页面与 CLI 发送功能复用。 |
| `features/classroom/` | 课堂助手：`windows.py` 用 `ctypes` 枚举并修复广播、黑屏与全屏窗口，`passwords.py` 读取并解密极域卸载密码，`service.py` 组合窗口与学生端状态并保存看护设置。课堂防护通过 `system/windows/guard.py` 注入进程内 DLL，支持五个开关，其中“监控远程命令”把 `CreateProcess`/`WinExec` 请求写入命名共享内存，由界面逐条允许或拒绝。窗口规则与密码算法移植自 JiYuTrainer（MIT）。 |
| `features/{files,firewall,local,student,shell}/` | 分别承载文件传送、防火墙、本机信息、学生端进程与终端业务；平台命令、地址解析和套接字操作复用 `system/`。学生端的常量与设置键在 `student/data.py`，进程识别、定位、启停与提权助手在 `student/service.py`。 |
| `features/uninstall/` | 卸载服务：删除桌面与开始菜单快捷方式、可选删除用户数据，并在退出后清理安装目录；由设置页和 `local uninstall` 共用。 |
| `packets/` | `constants.py` 保存报文数组和命令表，`codec.py` 负责构造、编码与分片；`blue_screen.py` 临时托管蓝屏脚本；不负责界面。 |
| `system/net/` | 目标解析、本机地址、UDP 发送、ICMP/ARP 探测与送达结果；结果数据在 `data.py`。 |
| `system/windows/` | Windows 命令、进程枚举与结束、端口表、提权助手、热键解析与可选内核驱动接口。进程与端口直接走 `kernel32` 与 `iphlpapi`，不依赖 `tasklist` / `netstat` 的文本输出。`guard.py` 负责课堂防护 DLL 的注入、策略与远程命令共享内存；`driver.py` 只封装 `sc.exe` 与 IOCTL，不在导入时加载驱动；`hotkey.py` 只做文本解析，不创建窗口或消息循环。 |
| `shared/` | JSONC、设置存储、数据路径、构建信息、版本与日志基础；不依赖界面功能。 |
| `resources/` | 仅放静态资源。图标源为 `icons/app.svg`；`native/` 放课堂防护的 x86/x64 DLL、可选内核驱动 `driver/jiyu_guard_driver.sys` 与上游许可证。运行时通过 `shared/resources.py` 的 `resource_path()` 统一定位源码与解包目录，Qt 图标由界面项目的 `resources.py` 适配。 |
| `NeoJiYuTrainerHooks/` | 独立原生项目：Hook DLL、窗口处理、输入拦截、远程命令与广播窗口菜单。由 `build.bat` 单独构建，产物由 `pack/` 收集进 `resources/native/`；Python 侧只通过 `guard.py` 的注入与共享内存协议交互。`disasm-lib`、`mhook` 是第三方裸源码，原样保留。 |
| `NeoJiYuTrainerDriver/` | 独立原生项目：WDM 驱动、自保护、进程强杀与 IOCTL。由 `build.bat` 单独构建，产物由 `pack/sign-driver.ps1` 签名后随包分发；Python 侧只通过 `driver.py` 调用，默认不加载。 |

版本号唯一来源是 `shared/version.py` 的 `__version__`；核心包 `__init__.py` 只重新导出，`shared/build_info.py` 转调版本读取接口并提供构建时间。`packets/constants.py` 只维护报文相关常量，不能把版本号放回该文件。

### GUI 装配与功能适配

- `NeoJiYuTrainerUI/gui/window/main.py` 的 `MainWindow` 显式创建页面和服务、连接信号并保留 Qt 槽与事件入口；具体交互交给 `gui/service.py`、`gui/menu/service.py`、`gui/workers/service.py`、`gui/window/service.py`、`gui/window/tray.py` 和各页面目录的 `service.py`。
- 页面位于 `NeoJiYuTrainerUI/features/<功能>/gui/page.py`,与核心包同名功能目录一一对应;同目录的 `service.py` 负责页面内交互协调,需要 Qt 信号适配时放同目录的 `data.py`。界面只调用核心包的服务与数据约定,不导入核心包内部的私有实现,也不把 Qt 对象传回核心包。
- 导航常量位于 `gui/window/data.py`，`gui/menu/service.py` 注册一级入口、页面路由与返回按钮；`gui/menu/sidebar.py` 处理侧边栏绘制、宽度动画与顶部工具按钮排列。侧边栏只有一级入口，组内页面由 `TabbedPage` 用 `Pivot` 承载。
- `gui/widgets/common.py` 提供 `FluentCard`、`FluentDialog`、`FluentComboBox`、浮出层圆角的覆盖函数，连接参数与任务栏；`gui/widgets/page.py` 提供页面基类、文件树和日志表格；`gui/theme.py` 集中保存视觉数值。
- `gui/workers/tasks.py` 定义后台线程与结果信号，`gui/workers/service.py` 管理排队、取消和线程收尾。失败信号携带异常消息与堆栈，由 GUI 主线程恢复界面状态。
- 只有 `gui/data.py` 的 `ConnectionState` 属于跨页面共用数据；设备备注的数据约定与业务在 `features/names/data.py`、`service.py`，`features/names/gui/data.py` 的 `DeviceAliasStore` 只做 Qt 信号适配；日志实体在 `features/logs/data.py`，带线程通知与持久化的 `LogStore` 位于 `features/logs/gui/data.py`；设置键与存储入口在 `features/settings/data.py`、`service.py`，页面在 `features/settings/gui/page.py`。
- `settings.json` 中的 `core`、`gui` 分组是既有持久化格式，不随源代码目录划分改变。通用 JSONC 与分组存储分别由 `shared/config.py`、`shared/settings.py` 提供。

### 打包与测试

- `pack/` 只放构建脚本、PyInstaller 配置、版本资源生成器、签名脚本与打包用 hooks；原生源码已独立为 `NeoJiYuTrainerHooks/`、`NeoJiYuTrainerDriver/`，不再放在 `pack` 下。运行时入口为 `NeoJiYuTrainer/__main__.py`，静态图标按 `NeoJiYuTrainer/resources/icons/app.svg` 收集；当前不复制上游 Sciter UI、Updater、`Debug/`、`Release/` 或旧 VS 工程文件。
- `.github/workflows/build.yml` 为可复用打包流程；`nightly-build.yml` 在推送 `main` 且涉及核心包、界面项目、`pack/`、`scripts/`、`requirements.txt` 或工作流文件时构建；`release.yml` 仍仅手动触发，详见[版本规范](VERSIONING.md)。路径过滤已按核心包与界面项目的路径同步更新。
- `tests/unit/` 检查报文、业务与配置单元;`tests/integration/` 检查入口和跨模块协作,其中 `test_layout.py` 检查底层依赖方向、显式导入、核心包除 `start/` 外不出现 Qt 与界面项目导入,并确认业务模块能在没有 Qt 的环境里导入;`tests/gui/` 检查窗口与页面,`tests/pack/` 检查版本、工作流与打包布局。公共离线替身集中在 `tests/fixtures/offline.py`,测试不执行真实目标发送或防火墙变更。
- 全量发现使用 `python -B -m unittest discover -s tests -t .`，保证按 `tests` 包导入；单个模块使用完整包名，例如 `python -B -m unittest tests.gui.test_window -v`。截图工具为 `python -B -m tests.gui.verify_gui --screenshot <截图路径>`。
- `scripts/` 保留虚拟环境启动与本机自测入口；`test_local_ip.py` 是真实本机报文收发自测，与离线测试套件分开。

## 新增功能

1. 在 `NeoJiYuTrainer/features/<功能>/` 建立有独立职责的功能包；业务参数与数据约定按需放入 `data.py`，可复用流程放入不依赖 Qt 的 `service.py`。通用编解码、网络/系统接口和配置继续复用各自基础模块。
2. 需要 CLI 时，在功能的 `cli.py` 定义 `register()` 并注册本功能参数，在 `start/parser.py` 的对应分组显式调用；在 `start/cli.py` 接入执行分发。
3. 需要界面时,在 `NeoJiYuTrainerUI/features/<功能>/gui/` 下定义 `page.py`,交互协调按需放入同目录的 `service.py`,Qt 数据通知适配按需放入 `data.py`。在 `gui/window/main.py` 显式导入、创建页面和服务、连接信号与槽,并更新 `gui/window/data.py` 的导航描述及相关菜单装配;仅有内部服务的功能不必创建页面。
4. 耗时任务交给 `NeoJiYuTrainerUI/gui/workers/` 的线程与任务服务；通用控件复用 `gui/widgets/`。核心服务保持独立于窗口和 Qt 对象，界面不得反向被核心包导入。
5. 涉及原生行为时，修改 `NeoJiYuTrainerHooks/` 或 `NeoJiYuTrainerDriver/` 的源码与 `build.bat`，把产物同步到 `NeoJiYuTrainer/resources/native/`，并在 `pack/NeoJiYuTrainer.spec` 里确认收集规则。
6. 业务、报文与参数单元测试放入 `tests/unit/`，CLI/跨模块流程放入 `tests/integration/`，界面与线程行为放入 `tests/gui/`，打包或版本变化补 `tests/pack/`，共用替身复用 `tests/fixtures/offline.py`。按影响范围更新 [CLI 文档](../usage/CLI.md)、[GUI 文档](../usage/GUI.md) 与本结构说明；新增依赖写入依赖清单并说明打包影响。提交类型与作用域按[项目作用域](CONTRIBUTING.md#项目作用域)选择。

## 本地生成目录

| 路径 | 用途 | 清理方式 |
| --- | --- | --- |
| `.venv/` | Python 虚拟环境 | 保留供开发和构建使用 |
| `build/` | 构建缓存、转换后的图标、测试临时目录与截图 | 验证结束后可删除，按需重新生成 |
| `output/` | 最终 EXE | 保留需要运行或分发的产物 |
| `data/` | 便携数据目录：EXE 同级生成，源码运行时位于项目根目录；保存设备备注、关闭窗口行为、界面日志 `runtime.log` 与命令行日志 `cli.log` | 需要保留配置时随 EXE 一起移动，删除后恢复默认；也可在 GUI“设置”页底部清除；任何重构阶段都不主动删除 |

以上目录及 `__pycache__/`、工具缓存均由 `.gitignore` 排除（其中用户数据按 `/data/` 规则排除），不提交 Git。根目录不保留重复的旧入口文件或遗留截图。

## 相关文档

- [CLI 模式使用说明](../usage/CLI.md)
- [GUI 模式使用说明](../usage/GUI.md)
- [上游骨架重构路线](REFACTOR.md)
- [EXE 构建说明](BUILD.md)
- [开发与提交规范](CONTRIBUTING.md)
