<div align="center">
<h1>项目结构</h1>
<p>
   <img alt="Python 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=212121">
   <img alt="PySide6" src="https://img.shields.io/badge/GUI-PySide6-41CD52?style=for-the-badge&logo=qt&logoColor=white&labelColor=212121">
</p>
<p><a href="../../README.md">← 返回项目首页</a> 丨 <a href="BUILD.md">EXE 构建</a> 丨 <a href="VERSIONING.md">版本规范</a> 丨 <a href="CONTRIBUTING.md">开发与提交规范</a></p>
</div>

---

根目录保留仓库首页、协作规范、依赖清单与 Git 配置。运行时代码集中在 `app/`，按启动、功能、界面基础、报文、系统适配与公共基础划分；打包、测试和文档分别独立。下面列出主要文件，常规包内的 `__init__.py` 省略。

```text
jiyu_attack_next/
|-- .github/workflows/
|   |-- build.yml                   # 可复用打包流程
|   |-- nightly-build.yml           # Nightly 构建与滚动预发布
|   `-- release.yml                 # 正式版发布（仅手动触发）
|-- README.md                       # 项目介绍与文档导航
|-- AGENTS.md                       # 仓库协作与按范围验证规范
|-- .gitmessage                     # Conventional Commits 提交模板
|-- LICENSE                        # GNU General Public License v3.0
|-- requirements.txt               # GUI 与构建依赖
|-- requirements-dev.txt           # 本地开发工具
|-- pyproject.toml                 # ruff 配置
|-- app/
|   |-- __init__.py                # 重新导出版本号
|   |-- __main__.py                # python -m app 与 PyInstaller 入口
|   |-- start/
|   |   |-- service.py             # GUI / CLI 与隐藏助手入口分流
|   |   |-- parser.py              # 装配功能分组子命令
|   |   |-- cli.py                 # CLI 分发与日志生命周期
|   |   |-- console.py             # 接回调用方控制台与标准流
|   |   `-- gui.py                 # Qt 初始化、单实例与 GUI 生命周期
|   |-- features/                  # 按用户功能组织，按需设置适配层
|   |   |-- about/                 # gui/page.py：关于页
|   |   |-- home/                  # gui/page.py：首页
|   |   |-- command/               # cli.py、gui/page.py：命令
|   |   |-- device/                # cli.py、gui/page.py：设备操作
|   |   |-- message/               # service.py、cli.py、gui/：消息
|   |   |-- files/                 # service.py、cli.py、gui/：文件传送
|   |   |-- firewall/              # service.py、cli.py、gui/：防火墙
|   |   |-- local/                 # service.py、cli.py、gui/：本机信息
|   |   |-- student/               # data.py、service.py、cli.py、gui/：学生端进程
|   |   |-- shell/                 # service.py、cli.py、gui/：终端
|   |   |-- send/
|   |   |   |-- data.py            # SendOptions 等发送参数
|   |   |   |-- service.py         # 参数校验、报文准备与发送协调
|   |   |   `-- cli.py             # 共用 CLI 参数与发送结果输出
|   |   |-- names/
|   |   |   |-- data.py            # 设备备注的数据约定
|   |   |   |-- service.py         # 无 Qt 的备注校验与持久化
|   |   |   `-- gui/
|   |   |       |-- data.py        # DeviceAliasStore 信号适配
|   |   |       `-- page.py        # 设备备注页
|   |   |-- logs/
|   |   |   |-- data.py            # LogEntry、LogLevel 与规范化
|   |   |   `-- gui/
|   |   |       |-- data.py        # LogStore、文件存储与线程通知
|   |   |       |-- service.py     # GUI 日志配置、导出与删除
|   |   |       `-- page.py        # 日志页
|   |   `-- settings/
|   |       |-- data.py            # 设置键、默认值与规范化
|   |       |-- service.py         # 便携设置存储的创建
|   |       `-- gui/page.py        # 设置页
|   |-- gui/                       # 跨功能共用的 Qt 基础与装配
|   |   |-- __main__.py            # 转交 start/gui.py
|   |   |-- data.py                # 仅 ConnectionState
|   |   |-- service.py             # 通用发送交互、提示与结果收尾
|   |   |-- resources.py           # QIcon 适配
|   |   |-- theme.py               # WinUI 视觉常量
|   |   |-- splash.py              # 启动遮罩
|   |   |-- window_effect.py       # 窗口材质适配
|   |   |-- widgets/
|   |   |   |-- common.py          # FluentCard、连接参数与任务栏
|   |   |   `-- page.py            # 页面基类、文件树与日志表格
|   |   |-- menu/
|   |   |   |-- sidebar.py         # 侧边栏绘制与宽度动画
|   |   |   `-- service.py         # 导航分组、路由与状态恢复
|   |   |-- workers/
|   |   |   |-- tasks.py           # SendWorker / ProbeWorker / TaskWorker
|   |   |   `-- service.py         # 任务队列、取消与线程生命周期
|   |   `-- window/
|   |       |-- data.py            # 窗口、导航与功能分类常量
|   |       |-- main.py            # MainWindow 装配、信号与 Qt 槽
|   |       |-- service.py         # 主题、材质、位置与窗口设置
|   |       `-- tray.py            # 托盘菜单、关闭行为与退出
|   |-- packets/
|   |   |-- constants.py           # 报文数组、命令表与容量常量
|   |   `-- codec.py               # 报文构造、文本编码与消息分片
|   |-- system/
|   |   |-- net/
|   |   |   |-- data.py            # 送达状态与结果数据
|   |   |   |-- targets.py         # 目标地址解析与计数
|   |   |   |-- local.py           # 本机地址选择与监听地址校验
|   |   |   |-- reachability.py    # ICMP 与 ARP 探测
|   |   |   `-- udp.py             # UDP 发送与送达结果采集
|   |   `-- windows/
|   |       |-- command.py         # Windows 命令执行与输出解码
|   |       |-- process.py         # 进程枚举、路径、存活校验与结束
|   |       |-- ports.py           # iphlpapi 端口到进程映射
|   |       `-- elevation.py       # UAC 隐藏助手与结果回传
|   |-- shared/
|   |   |-- config.py              # JSONC 解析与原子读写
|   |   |-- settings.py            # 通用分组设置存储
|   |   |-- paths.py               # 项目根目录与便携数据路径
|   |   |-- resources.py           # resource_path 静态资源定位
|   |   |-- version.py             # __version__ 唯一来源与显示版本
|   |   |-- build_info.py          # 构建时间与版本文本
|   |   |-- build_variant.py       # 正常版与调试版标记
|   |   `-- logs/
|   |       |-- cli.py             # 无 Qt 的命令行日志
|   |       `-- levels.py          # 日志等级与构建变体阈值
|   `-- resources/icons/app.svg    # 唯一静态图标源
|-- pack/
|   |-- build.ps1                  # EXE 构建脚本
|   |-- gen_version_info.py        # EXE 版本资源生成器
|   `-- JiYuAttackNext.spec        # PyInstaller 配置
|-- scripts/
|   |-- run_gui.ps1                # 使用虚拟环境启动 GUI
|   `-- test_local_ip.py           # 本机 IPv4 报文收发自测
|-- tests/
|   |-- fixtures/offline.py        # 离线网络替身与共用 fixture
|   |-- unit/                     # 报文、地址、业务与配置单元测试
|   |   |-- test_packets.py
|   |   |-- test_targets.py
|   |   |-- test_send.py
|   |   |-- test_windows.py
|   |   |-- test_student.py
|   |   |-- test_firewall.py
|   |   |-- test_local.py
|   |   |-- test_config.py
|   |   |-- test_config_io.py
|   |   `-- test_cli_parser.py
|   |-- integration/              # 入口、CLI 生命周期与跨模块协作
|   |   |-- test_entry.py
|   |   |-- test_layout.py          # 依赖方向、显式导入与无 Qt 校验
|   |   |-- test_cli_lifecycle.py
|   |   |-- test_cli_commands.py
|   |   |-- test_files.py
|   |   `-- test_shell.py
|   |-- gui/
|   |   |-- test_window.py
|   |   |-- test_log_page.py
|   |   |-- test_log_store.py
|   |   `-- verify_gui.py          # 截图检查工具
|   `-- pack/
|       |-- test_workflows.py
|       `-- test_versioning.py
`-- docs/
    |-- usage/
    |   |-- CLI.md
    |   `-- GUI.md
    `-- dev/
        |-- STRUCTURE.md
        |-- BUILD.md
        |-- STYLE.md
        |-- VERSIONING.md
        `-- CONTRIBUTING.md
```

## 模块关系

### 入口与命令行

- `app/__main__.py` 保留 `python -m app` 和 PyInstaller 入口，交给 `app/start/service.py` 分流。无参数时延迟导入 `app/start/gui.py`，带参数时进入 `app/start/cli.py`；CLI 路径不导入 Qt。
- `app/start/console.py` 的 `_show_cli_console()` 在 CLI 模式下把标准流接回调用方终端或重定向目标，不新建控制台。`--firewall-helper`、`--student-helper` 由启动层转交对应业务服务，不显示控制台。
- `app/start/parser.py` 负责装配解析器，显式调用各功能 `app/features/*/cli.py` 的 `register()`，由功能模块注册自己的参数；`build_group_parser()` 提供与页面对应的分组子命令。
- `app/start/cli.py` 管理解析器选择、日志生命周期和调用分发；功能 CLI 负责终端输入输出并调用自身业务服务或共用发送服务。可复用的业务逻辑不放进参数解析器。
- `app/start/gui.py` 负责 Qt 应用初始化、单实例、启动遮罩、异常日志与事件循环；`app/gui/__main__.py` 仅转交这个入口。

### 业务与基础模块

| 模块 | 职责与依赖边界 |
| --- | --- |
| `app/features/<功能>/service.py` | 与界面无关的业务流程；按需调用报文、系统适配与公共基础，不导入 Qt。并非每个功能都需要单独服务，命令和设备功能共用发送服务。 |
| `app/features/<功能>/data.py` | 功能数据、设置键、默认值与规范化；Qt 信号适配另放在功能的 `gui/data.py`。 |
| `app/features/send/` | `SendOptions`、参数校验、报文准备和发送协调；供不同页面与 CLI 发送功能复用。 |
| `app/features/files/`、`firewall/`、`local/`、`student/`、`shell/` | 分别承载文件传送、防火墙、本机信息、学生端进程与终端业务；平台命令、地址解析和套接字操作复用 `app/system/`。学生端的常量与设置键在 `student/data.py`，进程识别、定位、启停与提权助手在 `student/service.py`。 |
| `app/packets/` | `constants.py` 保存报文数组和命令表，`codec.py` 负责构造、编码与分片，不负责界面或网络生命周期。 |
| `app/system/net/` | 目标解析、本机地址、UDP 发送、ICMP/ARP 探测与送达结果；结果数据在 `data.py`。 |
| `app/system/windows/` | Windows 命令、进程枚举与结束、端口表、提权助手等系统接口，供具体功能调用；进程与端口直接走 `kernel32` 与 `iphlpapi`，不依赖 `tasklist` / `netstat` 的文本输出。 |
| `app/shared/` | JSONC、设置存储、数据路径、构建信息、版本与日志基础；不依赖界面功能。 |
| `app/resources/` | 仅放静态资源。唯一图标源为 `icons/app.svg`，运行时通过 `app.shared.resources.resource_path()` 统一定位源码与解包目录，Qt 图标由 `app/gui/resources.py` 适配。 |

版本号唯一来源是 `app/shared/version.py` 的 `__version__`；`app/__init__.py` 只重新导出，`app/shared/build_info.py` 转调版本读取接口并提供构建时间。`app/packets/constants.py` 只维护报文相关常量，不能把版本号放回该文件。

### GUI 装配与功能适配

- `app/gui/window/main.py` 的 `MainWindow` 显式创建页面和服务、连接信号并保留 Qt 槽与事件入口；具体交互交给 `app/gui/service.py`、`app/gui/menu/service.py`、`app/gui/workers/service.py`、`app/gui/window/service.py`、`app/gui/window/tray.py` 和各功能的 `gui/service.py`。
- 页面位于 `app/features/<功能>/gui/page.py`；消息、文件、防火墙、本机信息、学生端和日志功能的 GUI 服务与页面同目录。CLI 与 GUI 复用无 Qt 的业务服务，文件对话框、提示、信号和控件状态保留在 GUI 适配层。
- 导航常量位于 `app/gui/window/data.py`，`app/gui/menu/service.py` 注册页面分组、恢复状态和切换路由；`app/gui/menu/sidebar.py` 处理侧边栏绘制与宽度动画。导航仍按现有三个分组组织。
- `app/gui/widgets/common.py` 提供 `FluentCard`、`FluentDialog`、连接参数与任务栏，`app/gui/widgets/page.py` 提供页面基类、文件树和日志表格；`app/gui/theme.py` 集中保存视觉数值。
- `app/gui/workers/tasks.py` 定义后台线程与结果信号，`app/gui/workers/service.py` 管理排队、取消和线程收尾。失败信号携带异常消息与堆栈，由 GUI 主线程恢复界面状态。
- `app/gui/data.py` 仅保留 `ConnectionState`。设备备注的数据约定与业务在 `app/features/names/data.py`、`service.py`，`gui/data.py` 的 `DeviceAliasStore` 只做 Qt 信号适配；日志实体在 `app/features/logs/data.py`，带线程通知与持久化的 `LogStore` 位于 `gui/data.py`；设置键与存储入口在 `app/features/settings/data.py`、`service.py`，页面在 `gui/page.py`。
- `settings.json` 中的 `core`、`gui` 分组是既有持久化格式，不随源代码目录划分改变。通用 JSONC 与分组存储分别由 `app/shared/config.py`、`app/shared/settings.py` 提供。

### 打包与测试

- `pack/` 只放构建脚本、PyInstaller 配置和版本资源生成器；运行时入口仍为 `app/__main__.py`，静态图标按 `app/resources/icons/app.svg` 收集。
- `.github/workflows/build.yml` 为可复用打包流程；`nightly-build.yml` 在推送 `main` 且涉及 `app/`、`pack/`、`scripts/`、`requirements.txt` 或工作流文件时构建，静态资源已包含在 `app/` 过滤内。`release.yml` 仍仅手动触发，详见[版本规范](VERSIONING.md)。
- `tests/unit/` 检查报文、业务与配置单元，`tests/integration/` 检查入口和跨模块协作，其中 `test_layout.py` 检查底层依赖方向、移除旧聚合入口及业务模块不加载 Qt；`tests/gui/` 检查窗口与日志界面，`tests/pack/` 检查版本和工作流。公共离线替身集中在 `tests/fixtures/offline.py`，测试不执行真实目标发送或防火墙变更。
- 全量发现使用 `python -B -m unittest discover -s tests -t .`，保证按 `tests` 包导入；单个模块使用完整包名，例如 `python -B -m unittest tests.gui.test_window -v`。截图工具为 `python -B -m tests.gui.verify_gui --screenshot <截图路径>`。
- `scripts/` 保留虚拟环境启动与本机自测入口；`test_local_ip.py` 是真实本机报文收发自测，与离线测试套件分开。

## 新增功能

1. 在 `app/features/<功能>/` 建立有独立职责的功能包；业务参数与数据约定按需放入 `data.py`，可复用流程放入无 Qt 的 `service.py`。通用编解码、网络/系统接口和配置继续复用各自基础模块。
2. 需要 CLI 时，在功能的 `cli.py` 定义 `register()` 并注册本功能参数，在 `app/start/parser.py` 的对应分组显式调用；在 `app/start/cli.py` 接入执行分发。
3. 需要 GUI 时，在功能的 `gui/page.py` 定义页面，交互协调按需放入 `gui/service.py`，Qt 数据通知适配按需放入 `gui/data.py`。在 `app/gui/window/main.py` 显式导入、创建页面和服务、连接信号与槽，并更新 `app/gui/window/data.py` 的导航描述及相关菜单装配；仅有内部服务的功能不必创建页面。
4. 耗时任务交给 `app/gui/workers/` 的线程与任务服务；通用控件复用 `app/gui/widgets/`，业务服务保持独立于窗口和 Qt 对象。新静态资源放入 `app/resources/` 并经 `resource_path()` 读取，新增打包资源时同步 `pack/JiYuAttackNext.spec`。
5. 业务、报文与参数单元测试放入 `tests/unit/`，CLI/跨模块流程放入 `tests/integration/`，界面与线程行为放入 `tests/gui/`；打包或版本变化补 `tests/pack/`，共用替身复用 `tests/fixtures/offline.py`。按[验证范围](../../AGENTS.md#验证)选择检查。
6. 按影响范围更新 [CLI 文档](../usage/CLI.md)、[GUI 文档](../usage/GUI.md) 与本结构说明；新增依赖写入依赖清单并说明打包影响。提交类型与作用域继续按[项目作用域](CONTRIBUTING.md#项目作用域)选择，不按每个子目录机械新增 scope。

## 本地生成目录

| 路径 | 用途 | 清理方式 |
| --- | --- | --- |
| `.venv/` | Python 虚拟环境 | 保留供开发和构建使用 |
| `build/` | 构建缓存、转换后的图标、测试临时目录与截图 | 验证结束后可删除，按需重新生成 |
| `output/` | 最终 EXE | 保留需要运行或分发的产物 |
| `JiYuAttackNextData/` | 便携数据目录：EXE 同级生成，保存设备备注、关闭窗口行为、界面日志 `runtime.log` 与命令行日志 `cli.log`；源码运行时位于项目根目录 | 需要保留配置时随 EXE 一起移动，删除后恢复默认；也可在 GUI“设置”页底部清除 |

以上目录及 `__pycache__/`、工具缓存均由 `.gitignore` 排除，不提交 Git。根目录不保留重复的旧入口文件或遗留截图。

## 相关文档

- [CLI 模式使用说明](../usage/CLI.md)
- [GUI 模式使用说明](../usage/GUI.md)
- [EXE 构建说明](BUILD.md)
- [开发与提交规范](CONTRIBUTING.md)
