<div align="center">
<h1>项目结构</h1>
<p>
   <img alt="Python 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=212121">
   <img alt="PySide6" src="https://img.shields.io/badge/GUI-PySide6-41CD52?style=for-the-badge&logo=qt&logoColor=white&labelColor=212121">
</p>
<p><a href="../../README.md">← 返回项目首页</a> 丨 <a href="BUILD.md">EXE 构建</a> 丨 <a href="VERSIONING.md">版本规范</a> 丨 <a href="CONTRIBUTING.md">开发与提交规范</a></p>
</div>

---

根目录只保留仓库首页、依赖清单与 Git 配置。运行时代码、打包配置、测试与文档按职责分类，运行时代码集中在 `app/` 包内。

```text
jiyu_attack_next/
|-- .github/
|   `-- workflows/
|       |-- build.yml             # 可复用打包流程，供下面两个工作流调用
|       |-- nightly-build.yml     # Nightly 构建与滚动预发布
|       `-- release.yml           # 正式版发布（仅手动触发）
|-- README.md                     # 基础介绍与文档导航
|-- LICENSE                       # GNU General Public License v3.0
|-- requirements.txt              # GUI 与构建依赖
|-- requirements-dev.txt          # 本地开发工具（ruff）
|-- pyproject.toml                # ruff 格式化与 lint 配置
|-- app/             # 唯一运行时代码包
|   |-- __init__.py               # 包入口，导出版本号
|   |-- __main__.py               # 统一入口与 PyInstaller 打包入口
|   |-- core/                     # 与界面无关的标准库核心
|   |   |-- __init__.py           # 汇总导出核心接口
|   |   |-- constants.py          # 报文常量、命令表与版本号唯一来源
|   |   |-- protocol.py           # 报文构造、分片、地址校验
|   |   |-- transport.py          # UDP 发送、文件传送与结果解析
|   |   |-- firewall.py           # 防火墙规则与按需 UAC 提权
|   |   |-- config.py             # JSON with comments 配置读写
|   |   |-- paths.py              # 数据目录与日志文件位置
|   |   |-- cli_log.py            # 命令行运行日志
|   |   |-- local_info.py         # 本机 IP 与端口探测
|   |   |-- appcmd.py             # 应用命令、会话通报文与学生信息解析
|   |   |-- teacher.py            # 教师端模拟会话、宣告与命令投递
|   |   |-- screen.py             # UMSP 桌面分片接收、端口探测与缩略图还原
|   |   |-- video.py              # PyAV 解码 H.264 帧
|   |   `-- shell.py              # 反弹终端：本机监听、脚本分发与命令下发
|   |-- cli/
|   |   |-- __init__.py
|   |   `-- main.py               # argparse、命令分发、终端输出与命令行日志
|   `-- gui/
|       |-- __init__.py
|       |-- __main__.py           # GUI 源码入口
|       |-- app.py                # Fluent 窗口、导航、单实例与交互
|       |-- build_info.py         # 读取打包构建时间与版本号
|       |-- components.py         # 共用目标参数与任务栏
|       |-- models.py             # 连接状态、设备备注与结构化运行日志
|       |-- settings_store.py     # settings.json 的 core/gui 分组读写
|       |-- workers.py            # 后台任务
|       `-- pages/
|           |-- __init__.py       # 汇总导出页面类
|           |-- common.py         # 页面基类、文件树与日志表格组件
|           |-- home.py           # 首页：横幅快捷入口与功能卡片
|           |-- message.py        # 消息页
|           |-- command.py        # 命令页
|           |-- device.py         # 设备页
|           |-- file.py           # 文件传送页
|           |-- alias.py          # 设备备注页
|           |-- local.py          # 本机信息页
|           |-- firewall.py       # 防火墙页
|           |-- log.py            # 日志页
|           |-- settings.py       # 设置页
|           |-- appcmd.py         # 应用命令页
|           |-- students.py       # 学生信息页
|           |-- screen.py         # 屏幕画面页
|           |-- control.py        # 远程接管页
|           |-- chat.py           # 聊天消息页
|           |-- closewindow.py    # 关闭窗口页
|           |-- shell.py          # 反弹终端页
|           |-- screen_window.py  # 屏幕观看窗口
|           `-- about.py          # 关于页
|-- packaging/
|   |-- build.ps1                 # EXE 构建脚本
|   |-- gen_version_info.py       # 生成 EXE 版本资源
|   `-- JiYuAttackNext.spec       # PyInstaller 配置
|-- scripts/
|   |-- run_gui.ps1               # 使用虚拟环境启动 GUI
|   `-- test_local_ip.py          # 本机 IPv4 报文收发自测
|-- tests/
|   |-- __init__.py
|   |-- test_appcmd.py            # 应用命令、教师端模拟与学生信息解析测试
|   |-- test_core.py              # 核心协议、传输与防火墙测试
|   |-- test_entry.py             # 统一入口与命令行启动测试
|   |-- test_gui.py               # 界面与线程生命周期测试
|   |-- test_nightly_workflow.py  # Nightly 与 Release 工作流配置测试
|   |-- test_versioning.py        # 版本号一致性与读取测试
|   `-- verify_gui.py             # 界面截图检查工具
|-- docs/
|   |-- usage/                    # 使用文档
|   |   |-- CLI.md                # CLI 模式使用说明
|   |   `-- GUI.md                # GUI 模式使用说明
|   `-- dev/                      # 开发文档
|       |-- STRUCTURE.md          # 项目结构与模块职责
|       |-- BUILD.md              # 编译、输出与清理
|       |-- STYLE.md              # 代码风格、docstring 与注释规范
|       |-- VERSIONING.md         # 版本号、发布通道与正式版发布流程
|       `-- CONTRIBUTING.md       # 开发与中文提交规范
`-- assets/
    `-- app.svg                    # 图标源文件
```

## 模块关系

- `app/__main__.py` 是唯一入口：无参数时启动 GUI，带参数时调用 `app/cli/main.py`；`--firewall-helper` 由隐藏提权助手直接执行，不显示控制台。打包产物是窗口化子系统，`_show_cli_console()` 负责在 CLI 模式下把标准流接回调用方的终端或重定向目标，不新建控制台窗口。PyInstaller 也从此文件打包。
- `app/core/` 提供报文常量、协议构造、UDP 与文件传送、防火墙规则、本机信息探测，以及应用命令、教师端模拟会话与反弹终端；可按需使用第三方库（`av`、`Pillow`），新增依赖同步写进 `requirements.txt`。CLI 与 GUI 都通过 `from .. import core` 使用这些接口。
- `app/core/appcmd.py` 只拼装和解析字节：应用命令、会话通报文、黑屏与解锁、学生信息。`app/core/teacher.py` 负责套接字：宣告、登录应答、监听上报与按通道投递命令；`comd` 单播应用命令，`mess` 单播会话报文，`session` 发到会话组播（黑屏与解锁只有这条生效）。`app/core/screen.py` 负责 4806 端口的 UMSP 会话：切包、按偏移重组桌面分片、把记录交给回调；H.264 记录交给 `app/core/video.py` 用 PyAV 解成 RGB 位图，JPEG 帧由界面直接显示。`app/core/shell.py` 负责反弹终端：在本机起终端监听与只提供启动脚本的临时 HTTP 服务，再经远程命令通道让目标下载脚本并主动连回，命令行输入输出都走这条回连的 TCP 连接；启动脚本不内联在命令里，因为远程命令通道单条只有 163 个字符。`app/core/teacher.py` 里的 `RemoteControl` 保存远控用的常驻 UDP 套接字，边观看边把键鼠输入发回学生端（学生端只认发出接管请求的那个本地端口，所以套接字不能发完就关）。
- `app/cli/main.py` 负责 argparse、参数校验、单条命令、文件传送、防火墙命令与终端输出；不再作为可单独复制的单文件脚本维护。
- `app/gui/app.py` 基于 `FluentWindow` 实现侧边导航、任务调度、单实例运行与页面联动。导航按“远程攻击／教师端模拟／本机工具”三个可折叠分组组织，分组由 `NAVIGATION_GROUPS` 描述，`_add_navigation_group` 建节点并在创建后重算高度（库把树项压成单行高，必须在 `expand()` 之后 `_fit_navigation_groups()`）。
- `app/gui/pages/` 按首页、消息、命令、设备、文件传送、设备备注、应用命令、学生信息、本机信息、防火墙、日志、设置和关于拆分页面；文件传送页使用带复选框与全选的文件树，公共控件集中在 `common.py`。
- `app/gui/build_info.py` 从打包资源读取构建时间与版本号，源码运行时分别显示“源码运行”和 `app.__version__`。
- `app/gui/components.py` 提供跨页面同步的连接参数和统一任务栏。
- `app/gui/splash.py` 提供启动遮罩：主窗口显示后用项目图标、应用名、版本号与不确定进度条盖住界面，跟随窗口尺寸，最短停留一段时间后自动关闭。
- `app/gui/models.py` 保存连接状态、持久化设备备注，并提供带等级、线程、输出位置和异常详情的结构化日志存储。
- `app/gui/workers.py` 执行后台发送和本机工具任务，通过信号更新界面。
- `packaging/` 存放 PyInstaller 配置、构建脚本与版本资源生成器；EXE 以普通用户权限启动，防火墙操作在需要时通过 UAC 启动隐藏助手。
- `.github/workflows/build.yml` 提供可复用的打包流程，`nightly-build.yml` 与 `release.yml` 分别以 nightly、stable 通道调用它。
- `.github/workflows/nightly-build.yml` 在推送到 `main` 且改动涉及 `app/`、`packaging/`、`scripts/`、`assets/`、依赖清单或工作流文件时构建 EXE，并滚动更新 `nightly` 预发布；纯文档改动不触发。
- `.github/workflows/release.yml` 仅在 Actions 页面手动触发，校验版本号与标签后创建 `vX.Y.Z` 正式发布，规则见[版本规范](VERSIONING.md)。
- `scripts/` 存放启动与本机自测脚本，自动按脚本位置定位项目根目录；`test_local_ip.py` 用本机地址验证真实报文收发。
- `tests/` 使用模拟套接字验证行为，不执行真实目标发送或防火墙变更。

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
