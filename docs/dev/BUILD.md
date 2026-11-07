<div align="center">
<h1>EXE 构建说明</h1>
<p>
   <img alt="Python 3.13" src="https://img.shields.io/badge/Python-3.13-blue.svg?logo=python&logoColor=white">
   <img alt="PyInstaller" src="https://img.shields.io/badge/打包-PyInstaller-yellow.svg">
   <img alt="Platform" src="https://img.shields.io/badge/平台-Windows-0078D4.svg?logo=windows&logoColor=white">
</p>
<p><a href="../../README.md">返回项目首页</a> 丨 <a href="STRUCTURE.md">项目结构</a> 丨 <a href="CONTRIBUTING.md">开发与提交规范</a> 丨 <a href="VERSIONING.md">版本规范</a></p>
</div>

---

以下命令均以项目根目录为工作目录。构建脚本位于 `packaging/`，使用 PyInstaller 生成同时包含 GUI 与 CLI 的 Windows 单文件程序。

## 准备环境

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

已有虚拟环境时无需重新创建，GUI 和打包依赖的版本以根目录 [requirements.txt](../../requirements.txt) 为准。若虚拟环境早于 Fluent 组件库引入，重新执行一次安装命令即可。

`requirements.txt` 安装的是 `PySide6-Fluent-Widgets[full]`，比基础包多带 `scipy`、`pillow` 与 `colorthief`，组件库用它们做亚克力控件的高斯模糊与取色。缺这几个包时 `isAcrylicAvailable` 为假，亚克力控件会退化纯色背景。升级组件库时用 `pip install --upgrade` 不会自动补装 extra，需要写明 `[full]`。打包脚本按 `packaging/JiYuAttackNext.spec` 排除 `scipy` 里用不到的子包与 Pillow 的 AVIF、Tk 插件，只保留 `scipy.ndimage` 及其依赖。

`av`（PyAV）随 FFmpeg 动态库一起装进虚拟环境，负责把学生端推来的 H.264 码流解码成位图，打包时由 PyInstaller 的 `av` hook 收集这些 DLL，并额外复制 `av` 的包元数据。查看屏幕画面的体积主要来自这几个 FFmpeg 库，需要精简时优先确认 H.264 是否还要支持。

## 源码运行

| 运行方式 | 命令 |
| --- | --- |
| 图形界面（无参数） | `python -m app` |
| 命令行帮助 | `python -m app -h` |
| 虚拟环境启动脚本 | `powershell -ExecutionPolicy Bypass -File .\scripts\run_gui.ps1` |

`app/__main__.py` 是统一入口：无参数时启动 GUI，带参数时交给 `app/cli/main.py`。运行时代码集中在 `app/`：`core/` 提供协议、传输、防火墙与本机信息等标准库实现，`cli/` 负责参数解析和命令分发，`gui/` 提供 PySide6 界面。EXE 以普通用户权限启动，避免在终端运行 CLI 时另开提升窗口；只有防火墙操作在未提升时按需通过 UAC 启动隐藏助手。

## 构建 EXE

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build.ps1
powershell -ExecutionPolicy Bypass -File .\packaging\build.ps1 -Clean
powershell -ExecutionPolicy Bypass -File .\packaging\build.ps1 -Variant debug
powershell -ExecutionPolicy Bypass -File .\packaging\build.ps1 -Version 0.1.1
powershell -ExecutionPolicy Bypass -File .\packaging\build.ps1 -Python "C:\Python313\python.exe"
```

- 无参数时增量构建，`-Clean` 清理 PyInstaller 缓存后重建，`-Python` 指定其他解释器。
- `-Variant` 取 `both`、`release` 或 `debug`，默认 `both`：一次产出 `JiYuAttackNext.exe` 与 `JiYuAttackNext_Debug.exe`，两份代码完全相同，只有构建变体标记不同。`-Variant debug` 只重建调试版本，调试时不必等两份都打包完。
- 两个变体使用独立的 `--workpath`（`build/release` 与 `build/debug`），避免 PyInstaller 复用另一份变体的分析缓存。
- `-Version` 覆盖版本号；省略时读取 `app/core/constants.py` 的 `__version__`。版本号须符合语义化版本格式，规则见[版本规范](VERSIONING.md)。
- 脚本根据自身路径定位项目根目录，也可从其他目录通过绝对路径调用，默认使用项目虚拟环境。
- 读取 [packaging/JiYuAttackNext.spec](../../packaging/JiYuAttackNext.spec)，并收集 Fluent Widgets 的运行时资源与包元数据。
- 每次构建都把当前本地时间打包进 EXE，“关于”页据此显示构建时间；源码运行时显示“源码运行”。
- 版本号同时写入 `build/assets/version.txt`（供“关于”页显示）与 `build/assets/version_info.txt`（PyInstaller 的 Windows 版本资源，EXE 属性中可见）。

## 输出与生成内容

| 路径 | 内容 | 是否保留 |
| --- | --- | --- |
| `output/JiYuAttackNext.exe` | 单文件程序，GUI 与 CLI 共用；只写 `WARNING` 及以上的日志 | 保留用于运行和分发 |
| `output/JiYuAttackNext_Debug.exe` | 同上，但日志从 `DEBUG` 起记录 | 保留，供排查问题使用 |
| `build/release/`、`build/debug/` | 两个变体各自的打包中间文件与分析结果 | 构建后可删除 |
| `build/assets/variant.txt` | 本次打包的变体标记，运行时打进 EXE | 构建后可删除 |
| `build/assets/app.ico` | 从 SVG 转换的构建图标 | 构建后可删除 |
| `build/assets/build_time.txt` | 本次构建时间，打包进 EXE | 构建后可删除 |
| `build/assets/version.txt` | 本次构建版本号，打包进 EXE | 构建后可删除 |
| `build/assets/version_info.txt` | EXE 版本资源，由 `packaging/gen_version_info.py` 生成 | 构建后可删除 |
| `build/previews/` | 手动生成的界面验证截图 | 检查后可删除 |

删除 `build/` 不影响已生成的 EXE，下次构建会重新生成所需文件。`build/`、`output/` 与 `.venv/` 均由 `.gitignore` 排除，不提交 Git。构建前请关闭正在运行的同名程序。项目生成的是未签名 EXE，首次启动需数秒解压资源；EXE 只允许同时运行一个实例，再次启动会唤醒已有窗口。

## 运行数据

EXE 在其所在目录创建 `JiYuAttackNextData` 子文件夹：`settings.json` 保存设备备注（`core` 组）与界面设置（`gui` 组，含关闭窗口行为、窗口材质和主窗口位置），`runtime.log` 保存界面运行日志，`cli.log` 保存命令行模式的运行日志。日志等级由构建变体决定：正常版本只写 `WARNING` 与 `ERROR`，`JiYuAttackNext_Debug.exe` 从 `DEBUG` 起记录。两个 EXE 放在同一目录时共用这个文件夹，调试版本产生的记录与正常版本写进同一份日志。`settings.json` 使用 JSON with comments，允许手写 `//`、`/* */` 注释与尾逗号，程序保存时会重写整个文件。该目录由 `.gitignore` 排除，源码运行时位于项目根目录。

- 日志包含毫秒时间、规范级别、线程、输出位置、功能分类、消息与异常详情，便于从用户环境回传排查。
- 只移动 EXE 而不移动该文件夹时，新位置按默认配置启动。
- 第一次关闭主窗口时会询问是否最小化到 Windows 系统托盘并保存选择，之后可在“设置”页修改，也可在“设置”页底部清除整个数据目录。
- EXE 所在目录不可写时，备注与日志保存失败并在界面提示，请改放到可写目录运行。

## GitHub Actions 工作流

工作流分为三层，版本号规则见[版本规范](VERSIONING.md)：

| 文件 | 名称 | 触发 | 用途 |
| --- | --- | --- | --- |
| `build.yml` | `Build` | 被下面两个工作流调用 | 复用打包流程：解析版本号、跑离线检查、构建并上传资产 |
| `nightly-build.yml` | `Nightly Build` | 推送到 `main` 且改动影响产物，或手动运行 | 构建 nightly 并滚动更新 `nightly` 预发布 |
| `release.yml` | `Release` | 仅在 Actions 页面手动运行 | 构建正式版并创建 `vX.Y.Z` 正式发布 |

`build.yml` 通过 `channel` 输入决定版本号：`stable` 使用源码版本，`nightly` 追加 `-nightly.YYYYMMDD`（UTC 日期）；`version` 输入可显式覆盖。nightly 还会把 7 位提交哈希拼到版本号后面作为显示版本（例如 `0.1.0-nightly.20261029-1a8ede3`），产物文件名、EXE 版本资源与界面都用这个显示版本，发布说明只用带日期的版本号。`packaging/build.ps1` 收到的 `-Commit` 由工作流传入；本地手工构建测试版时留空，脚本会自己取当前提交的前 7 位。

### Nightly Build

- 推送到 `main` 时按改动路径决定是否运行：只有 `app/`、`packaging/`、`scripts/`、`assets/`、`requirements.txt` 或工作流文件本身发生变化才会触发，纯文档与测试改动不会重新编译 EXE。
- 也可在 Actions 页面选择该工作流并点击 `Run workflow` 手动运行，手动运行需选择 `main` 分支才会发布；手动运行不受路径过滤限制。
- 工作流文件首次进入默认分支后，Actions 页面才会显示手动运行入口。
- 在 `windows-latest` 上使用 Python 3.13 安装依赖、执行离线测试并运行 `packaging/build.ps1 -Clean`。
- 构建成功后更新标签为 `nightly`、标题为 `Nightly Build <版本>` 的预发布版本，资产为 `JiYuAttackNext.exe`、`JiYuAttackNext_Debug.exe` 以及各自带显示版本（含提交哈希）的副本，与正式版一致（GUI 与 CLI 共用同一个 EXE，调试版只差日志等级）。
- 发布说明包含版本号、构建时间、工作流运行记录、两个资产的 SHA256，`Commits` 章节列出本次构建对应的那条提交。
- 路径过滤按整个推送的 `before..head` 判定，因此把文档提交与代码提交一起推送时仍会构建；`Commits` 章节据此说明本次构建实际包含哪些改动。
- 同一天内重复构建不新建发布：先比对现有 `nightly` 预发布的标题是否含本次的日期后缀，相同就原地更新资产与说明，标签 `nightly` 与下载地址 `https://github.com/JasonFang0109c/jiyu_attack_next/releases/tag/nightly` 都保持不变。
- 只有日期变了（例如旧的是 `-nightly.20261103`、新的是 `-nightly.20261104`）才删除旧预发布与 `nightly` 标签再重新创建，保证每天最多一次新的发布通知，不让关注者的动态被每次推送刷屏。
- 日期取自构建版本号的 `-nightly.YYYYMMDD` 后缀，与产物里记录的日期同源；后缀按 UTC 计日，不受运行器时区与本地时区影响。
- 原地更新依赖 `overwrite_files: true` 替换同名资产；同一天内发布维护的历史说明由本次构建的说明整体覆盖，资产始终是四个文件。
- 使用 `nightly-build` 并发组，新的运行会取消尚未完成的旧运行。

### Release

- 只支持手动触发，不随推送自动运行；不会自动递增版本号，需先修改 `app/core/constants.py` 的 `__version__` 并提交。
- 发布前校验版本号与源码一致、正式版不带预发布后缀、标签 `vX.Y.Z` 尚不存在，任一不满足即失败。
- 资产为固定名 `JiYuAttackNext.exe`，另附带版本号的 `JiYuAttackNext-X.Y.Z.exe`；同一文件同时提供 GUI 与 CLI。正式版不带提交哈希，`packaging/build.ps1` 只对带预发布后缀的版本号追加哈希。
- 发布说明的 `Changes` 章节列出上一个 `v*` 标签以来的提交标题；`make_latest: true` 使正式版成为最新版本，nightly 不受影响。
- 可选择以草稿（`draft`）创建，确认后再在 Releases 页面发布；`overwrite_files: false` 保证不会覆盖已发布资产。
- 使用 `release` 并发组且不取消进行中的运行，避免两次发布互相干扰。

两个发布工作流都使用 `GITHUB_TOKEN`，仓库需允许 Actions 写入内容；发布步骤返回 403 时，在 `Settings > Actions > General > Workflow permissions` 中允许读写权限。

## 验证

改动 `app/`、构建脚本或打包配置后执行；纯文档改动不需要。

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B -m tests.verify_gui --screenshot <截图路径>
```

没有第二台测试设备时，可另外运行本机 IP 自测：

```powershell
.\.venv\Scripts\python.exe -B .\scripts\test_local_ip.py
```

生成的 EXE 无参数时打开图形界面，带参数时运行命令行模式；两种模式都无需安装 Python。EXE 打包为窗口化子系统（`console=False`），双击启动不会出现控制台窗口；带参数运行时由 `app/__main__.py` 的 `_show_cli_console()` 把标准流接回调用方的终端：优先沿用调用方传入的句柄（命令提示符的控制台句柄、Windows Terminal 的伪控制台管道、重定向到的文件），取不到时再挂到父进程的控制台，任何情况下都不新建控制台窗口；确实拿不到终端时丢弃输出，命令本身照常执行。因此从终端启动不会阻塞提示符，需要等待命令结束时用 `start /wait`。EXE 不强制请求管理员权限；防火墙操作在需要时单独弹出 UAC，并由隐藏助手执行。
