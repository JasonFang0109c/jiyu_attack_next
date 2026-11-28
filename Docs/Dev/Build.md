<div align="center">
<h1>EXE 构建说明</h1>
<p>
   <img alt="Python 3.13" src="https://img.shields.io/badge/Python-3.13-blue.svg?logo=python&logoColor=white">
   <img alt="PyInstaller" src="https://img.shields.io/badge/打包-PyInstaller-yellow.svg">
   <img alt="Platform" src="https://img.shields.io/badge/平台-Windows-0078D4.svg?logo=windows&logoColor=white">
</p>
<p><a href="../../README.md">返回项目首页</a> 丨 <a href="Structure.md">项目结构</a> 丨 <a href="Contributing.md">开发与提交规范</a> 丨 <a href="Versioning.md">版本规范</a></p>
</div>

---

以下命令均以项目根目录为工作目录。构建脚本位于 `Pack/`，使用 PyInstaller 生成同时包含 GUI 与 CLI 的 Windows 单文件程序。

## 准备环境

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

已有虚拟环境时无需重新创建，GUI 和打包依赖的版本以根目录 [requirements.txt](../../requirements.txt) 为准。若虚拟环境早于 Fluent 组件库引入，重新执行一次安装命令即可。

`requirements.txt` 安装的是 `PySide6-Fluent-Widgets[full]`，比基础包多带 `scipy`、`pillow` 与 `colorthief`，组件库用它们做亚克力控件的高斯模糊与取色。缺这几个包时 `isAcrylicAvailable` 为假，亚克力控件会退化纯色背景。升级组件库时用 `pip install --upgrade` 不会自动补装 extra，需要写明 `[full]`。打包脚本按 `Pack/NeoJiYuTrainer.spec` 排除 `scipy` 里用不到的子包，只保留 `scipy.ndimage` 及其依赖；Qt 与 Pillow 的裁剪见下面的[体积控制](#体积控制)。

## 源码运行

| 运行方式 | 命令 |
| --- | --- |
| 图形界面（无参数） | `python -m NeoJiYuTrainer` |
| 命令行帮助 | `python -m NeoJiYuTrainer -h` |
| 虚拟环境启动脚本 | `powershell -ExecutionPolicy Bypass -File .\Scripts\RunGui.ps1` |

`NeoJiYuTrainer/__main__.py` 保留统一入口，并交给 `NeoJiYuTrainer/Start/Service.py` 分流：无参数时调用 `NeoJiYuTrainer/Start/Gui.py`，带参数时调用 `NeoJiYuTrainer/Start/Cli.py`。运行时代码集中在 `NeoJiYuTrainer/`：`Features/` 按功能组织业务与 CLI/GUI 适配，`Packets/` 负责报文编解码，`System/` 负责网络和 Windows 适配，`Shared/` 保存配置、日志与版本等公共基础，`Gui/` 提供通用界面组件与装配。EXE 以普通用户权限启动，避免在终端运行 CLI 时另开提升窗口；只有防火墙操作在未提升时按需通过 UAC 启动隐藏助手。

## 构建 EXE

```powershell
powershell -ExecutionPolicy Bypass -File .\Pack\Build.ps1
powershell -ExecutionPolicy Bypass -File .\Pack\Build.ps1 -Clean
powershell -ExecutionPolicy Bypass -File .\Pack\Build.ps1 -Variant debug
powershell -ExecutionPolicy Bypass -File .\Pack\Build.ps1 -Version 0.1.1
powershell -ExecutionPolicy Bypass -File .\Pack\Build.ps1 -Python "C:\Python313\python.exe"
```

- `Build.ps1` 会在实际打包前自动调用 `Pack/CleanBuild.ps1`；单独执行清理脚本可提前预清理，使用 `-WhatIf` 仅预览将删除的项目。
- 清理脚本删除旧版 NeoJiYuTrainer EXE、PyInstaller 的 `Build/Release`、`Build/Debug`、`Build/Assets`、工具缓存，以及源码运行目录和 `Output/Data/` 中的 `cli.log`、`runtime.log`。只删除这两个日志文件，`settings.json`、备注和其他用户数据保留；若旧 EXE 正在运行，清理会报错并停止构建。
- 无参数时执行清理后构建；`-Clean` 额外要求 PyInstaller 清理其自身缓存，`-Python` 指定其他解释器。
- `-Variant` 取 `both`、`release` 或 `debug`，默认 `both`：一次产出 `NeoJiYuTrainer-<显示版本>.exe` 与 `NeoJiYuTrainer_Debug-<显示版本>.exe`，两份代码完全相同，只有构建变体标记不同。`-Variant debug` 只重建调试版本，调试时不必等两份都打包完。
- 两个变体使用独立的 `--workpath`（`Build/Release` 与 `Build/Debug`），避免 PyInstaller 复用另一份变体的分析缓存。
- `-Version` 覆盖版本号；省略时读取 `NeoJiYuTrainer/Shared/Version.py` 的 `__version__`。版本号须符合语义化版本格式，规则见[版本规范](Versioning.md)。
- 产物名直接带显示版本，例如 `Output/NeoJiYuTrainer-0.1.0-e1f9608.exe` 与 `Output/NeoJiYuTrainer_Debug-0.1.0-e1f9608.exe`；显示版本是版本号加提交哈希，因此从文件名就能看出对应哪次提交。本地构建不再产出 `NeoJiYuTrainer.exe` 这类不带版本号的固定名，旧版 EXE 会在构建前由清理脚本删除。
- `Output/` 只留最近一次构建所选变体的 EXE：重新构建前删除旧版本产物，避免与当前构建混淆，不保留历史版本。
- 提交哈希省略 `-Commit` 时自动取 `git rev-parse --short=7 HEAD`；显式传 `-Commit ""` 表示不要哈希（正式版发布用它），此时产物名就是 `Output/NeoJiYuTrainer-0.1.0.exe`；不在 Git 仓库内构建时同样只带版本号。
- 脚本根据自身路径定位项目根目录，也可从其他目录通过绝对路径调用，默认使用项目虚拟环境。
- 读取 [Pack/NeoJiYuTrainer.spec](../../Pack/NeoJiYuTrainer.spec)，并收集 Fluent Widgets 的运行时资源与包元数据。
- 每次构建都把当前本地时间打包进 EXE，“关于”页据此显示构建时间；源码运行时显示“源码运行”。
- 版本号同时写入 `Build/Assets/version.txt`（供“关于”页显示）与 `Build/Assets/version_info.txt`（PyInstaller 的 Windows 版本资源，EXE 属性中可见）。

### 课堂防护原生组件

- 源码在 `NeoJiYuTrainerHooks/`（对应上游 JiYuTrainer 的 `JiYuTrainerHooks`）：`Hooks.cpp` 为窄接口 Hook DLL，`Mhook/` 与 `DisasmLib/` 来自 JiYuTrainer 的第三方源码（MIT 与原作者版权，见目录内说明）。
- 仓库提交 `NeoJiYuTrainer/Resources/Native/GuardX86.dll`、`GuardX64.dll` 的预编译产物，普通 EXE 构建不需要编译器；PyInstaller 通过 `Pack/NeoJiYuTrainer.spec` 一并收集。
- 只有修改 `Hooks.cpp` 或升级第三方源码时才需要重新编译：在装有 MSVC 与 Windows SDK 的 Windows 容器内执行 `NeoJiYuTrainerHooks/Build.ps1`，脚本用 `Build.bat` 分别编译 x86/x64，产物落在 `Build/Native/Hooks/`，再复制到 `NeoJiYuTrainer/Resources/Native/`。宿主机不安装编译器与 SDK。需要一次重建两个原生项目时，依次执行 `NeoJiYuTrainerHooks/Build.ps1` 与 `NeoJiYuTrainerDriver/Build.ps1`。
- `Build/Native/Hooks/` 里只有 `GuardX64.dll` 与 `GuardX86.dll` 两个产物，构建脚本不再生成任何自测程序。

### 内核驱动（可选）

- 源码在 `NeoJiYuTrainerDriver/`（对应上游 JiYuTrainer 的 `JiYuTrainerDriver`）：`Driver.c` 是 WDM 驱动入口，`Protect.c` 用 `ObRegisterCallbacks` 阻止其它进程结束受保护进程，`UnExp.c` 定位未导出例程做逐线程强杀，`IoCtl.h` 定义设备名与请求结构。
- 在装有 WDK 10.0.26100 与 MSVC 的 Windows 容器内执行 `NeoJiYuTrainerDriver/Build.ps1`，产物为 `Build/Native/Driver/JiYuGuardDriver.sys`，复制到 `NeoJiYuTrainer/Resources/Native/Driver/` 后由 PyInstaller 收集。
- 驱动默认不加载、不安装服务；只有用户在“设置 → 内核驱动（可选）”里显式启用才调用 `sc.exe` 创建并启动 `JiyuGuardDriver`。测试时必须使用可丢弃的隔离虚拟机或启用了测试签名的环境，宿主机不要加载未通过微软正式签名的驱动。
- 测试签名用 `Pack/SignDriver.ps1`：脚本在当前用户证书库生成 `CN=JiYuGuard Test` 代码签名证书，导出到 `Build/Signing/`，再调用容器内的 x86 `signtool.exe` 给 `NeoJiYuTrainer/Resources/Native/Driver/JiYuGuardDriver.sys` 签名；签名后重新执行 `Pack/Build.ps1` 打包。整个 `Build/` 被删除后重新签名会得到一张新证书（指纹随之改变），目标机器要重新导入新的 cer。目标机器需要管理员导入 `Build/Signing/JiYuGuardTest.cer` 到 `LocalMachine\Root` 与 `LocalMachine\TrustedPublisher`，并以管理员执行 `bcdedit /set Testsigning on` 后重启，Secure Boot 必须关闭。
- 驱动加载失败、系统未开启测试签名或权限不足时，课堂防护与其它纯用户态功能不受影响。

## 输出与生成内容

| 路径 | 内容 | 是否保留 |
| --- | --- | --- |
| `Output/NeoJiYuTrainer-<显示版本>.exe` | 单文件程序，GUI 与 CLI 共用；只写 `WARNING` 及以上的日志 | 保留用于运行和分发，旧版本号的删除 |
| `Output/NeoJiYuTrainer_Debug-<显示版本>.exe` | 同上，但日志从 `DEBUG` 起记录 | 保留，供排查问题使用，旧版本号的删除 |
| `Build/` | 全部生成物：两个变体的 PyInstaller 中间文件（`Release/`、`Debug/`）、打包资源（`Assets/`）、测试与截图临时目录（`TestData/`、`VerifyGuiData/`、`Previews/`），以及驱动签名临时材料（`Signing/`） | 下次构建前整目录删除 |

整个 `Build/` 都是生成物：删除不影响已生成的 EXE，构建会按需重建；其中 `Assets/` 由 `Pack/Build.ps1` 生成，`Signing/` 由 `Pack/SignDriver.ps1` 重新签发测试证书并导出。`Build/`、`Output/` 与 `.venv/` 均由 `.gitignore` 排除，不提交 Git。构建前请关闭正在运行的同名程序。项目生成的是未签名 EXE，首次启动需数秒解压资源；EXE 只允许同时运行一个实例，再次启动会唤醒已有窗口。

### 构建前清理

`Pack/Build.ps1` 在正式构建前会自动运行 `Pack/CleanBuild.ps1`；需要单独预清理时运行：

```powershell
powershell -ExecutionPolicy Bypass -File ./Pack/CleanBuild.ps1

# 只预览清理目标，不删除文件
powershell -ExecutionPolicy Bypass -File ./Pack/CleanBuild.ps1 -WhatIf
```

清理脚本只接受包含 `Pack/Build.ps1` 与 `NeoJiYuTrainer/` 的项目根目录，并按下表删除固定目标。构建前请关闭正在运行的 EXE；若检测到项目旧 EXE 仍在运行，脚本会报错并中止构建。

| 清理目标 | 说明 |
| --- | --- |
| `Output/NeoJiYuTrainer*.exe` | 删除旧版与上一轮 EXE，构建完成后仅留下本轮选中变体的产物 |
| `Build/`（整个目录） | 一次性清除 PyInstaller 中间文件、生成资源、测试与截图临时目录、驱动签名临时材料；下次构建全部重建 |
| `Output/Data/cli.log`、`Output/Data/runtime.log` | 清理 EXE 数据目录中的运行日志 |
| `Data/cli.log`、`Data/runtime.log` | 清理源码运行目录中的运行日志 |
| `.ruff_cache/`、`.pytest_cache/`、`.mypy_cache/`、`.coverage`、`htmlcov/` | 清除工具缓存与覆盖率结果 |
| `NeoJiYuTrainer/`、`Pack/`、`Scripts/`、`Tests/` 下的 `__pycache__/` | 清除源码字节码缓存，不遍历 `.venv/` |

**明确保留 `settings.json`、备注和其他运行数据**：脚本仅删除上表列出的两个日志文件，不删除 `Data/` 目录，也不会递归清理 `Output/`。由于脚本会删除旧 EXE，不要在构建完成后再次运行；验证产生的截图、脚本与数据目录按下一节处理。需要干净的验证环境时改用临时数据目录（截图验证用 `Build/VerifyGuiData`）。

### 残留清理

测试、构建与截图验证结束后，把这次产生的临时东西清掉再提交。`Build/` 与 `Output/` 都由 `.gitignore` 排除，不留 Git 痕迹，但目录会越积越大——一次原生冒烟、一次界面截图、一次 EXE 试跑各留一份，很快就是几百兆。

| 清理对象 | 处理方式 |
| --- | --- |
| 一次性脚本（探针、批量替换、截图、临时校验） | 用完立即删除，不留到下一次改动 |
| `Build/` 整个目录 | 直接删除，或交给 `Pack/CleanBuild.ps1 -WhatIf` 预览后删除；目录里的一切都可由构建脚本重建 |
| 工具缓存与字节码：`.ruff_cache/`、`.pytest_cache/`、`.coverage`、`__pycache__/` | 同上，由清理脚本统一删除 |

**保留**：`Output/Data/`（用户备注、设置与日志，任何时候都不删）。构建产物 `Output/*.exe` 保留最近一轮用于冒烟，下一轮构建前由清理脚本删除。`Build/Signing/` 里是测试签名证书与 `signtool` 批处理，删掉后由 `Pack/SignDriver.ps1` 重新签发，不需要手工备份。

清理完毕用 `git status` 确认工作区只剩本次该提交的改动；被忽略的目录不会出现在里面，需要时用 `ls Build` 看一眼是否还有本次的临时文件。

## 体积控制

单文件程序把 Qt、Python 与依赖一起打包，任何一份多余的 DLL 都会直接进入分发包。`Pack/NeoJiYuTrainer.spec` 在 `a.binaries` 上做了一次过滤，规则集中在四个集合里：

| 集合 | 去掉的内容 | 为什么可以去掉 |
| --- | --- | --- |
| `QT_UNUSED_BINARIES` | 软件 OpenGL 渲染器 `opengl32sw.dll`、QML/Quick 运行时、`Qt6Pdf`、`Qt6OpenGL`、虚拟键盘 | 界面只用 Widgets，运行期不加载 QML、不显示 PDF，也不需要软件渲染兜底 |
| `QT_UNUSED_PLUGINS` | `qdirect2d`、`qminimal`、`qoffscreen`、`qpdf`、`qtiff`、`qwebp`、`qicns`、`qtga`、`qgif`、触摸与虚拟键盘插件 | 只用 `qwindows` 平台插件，图标与位图走 `qico`、`qsvg`、`qjpeg` |
| `PILLOW_UNUSED` | `_avif`、`_imagingtk` | 界面不解码 AVIF，也不使用 Tk |
| `ICU_UNUSED` | 构建机 PATH 上混进来的 ICU DLL | PySide6 使用 Windows 系统自带 ICU |

`_is_qt_translation` 另外滤掉 `PySide6	ranslations` 下的 `.qm`：Qt 自带翻译只有显式 `QTranslator` 加载才生效，界面用的是组件库自带的中文资源。过滤按文件名比对，`_stem` 会去掉扩展名与 ABI 后缀，因此 `_avif.cp313-win_amd64.pyd` 这类带后缀的扩展模块也能命中。

改动这份清单前先确认运行期确实不加载：`pyi-archive_viewer -l Output/NeoJiYuTrainer-<显示版本>.exe` 看打进包里的文件，`pyi-archive_viewer -r -b` 看 Python 模块清单。裁剪后必须启动一次打包版界面，并跑 `-h`、`local info`、`classroom student --list`，确认平台插件、图标与命令行都没坏。按当前清单，两份 EXE 从 84 MB 降到 62 MB 左右。

## 运行数据

EXE 在其所在目录创建 `data` 子文件夹，目录内容与不可写时的表现见[运行数据](../Usage/Gui.md#运行数据)。与构建相关的差异只有日志等级：正常版本默认从 `WARNING` 起记录，GUI 可在设置页选择 `INFO`、`WARNING` 或 `ERROR`，CLI 始终采用默认阈值；调试版本固定从 `DEBUG` 起记录。两个 EXE 放在同一目录时共用这个文件夹，调试版本产生的记录与正常版本写进同一份日志。该目录由 `.gitignore` 排除，源码运行时位于项目根目录。

- 日志包含毫秒时间、规范级别、线程、输出位置、功能分类、消息与异常详情，便于从用户环境回传排查。
- 只移动 EXE 而不移动该文件夹时，新位置按默认配置启动。
- 第一次关闭主窗口时会询问是否最小化到 Windows 系统托盘并保存选择，之后可在“设置”页修改，也可在“设置”页底部清除整个数据目录。
- EXE 所在目录不可写时，备注与日志保存失败并在界面提示，请改放到可写目录运行。

## GitHub Actions 工作流

工作流分为三层，版本号规则见[版本规范](Versioning.md)：

| 文件 | 名称 | 触发 | 用途 |
| --- | --- | --- | --- |
| `Build.yml` | `Build` | 被下面两个工作流调用 | 复用打包流程：解析版本号、跑验证检查、构建并上传资产 |
| `NightlyBuild.yml` | `Nightly Build` | 推送到 `main` 且改动影响产物，或手动运行 | 构建 nightly 并滚动更新 `nightly` 预发布 |
| `Release.yml` | `Release` | 仅在 Actions 页面手动运行 | 构建正式版并创建 `vX.Y.Z` 正式发布 |

`Build.yml` 通过 `channel` 输入决定版本号：`stable` 使用源码版本，`nightly` 追加 `-nightly.YYYYMMDD`（UTC 日期）；`version` 输入可显式覆盖。nightly 另有一个显示版本，由基础版本号加 7 位提交哈希拼成（例如 `0.1.0-1a8ede3`），产物文件名、EXE 版本资源与界面都用它，发布说明与标签只用带日期的版本号。`Pack/Build.ps1` 收到的 `-Commit` 由工作流传入；本地手工构建不传时脚本自己取当前提交的前 7 位，产物名因此也带哈希；正式版工作流传 `-Commit ""` 表示不要哈希。

### Nightly Build

- 推送到 `main` 时按改动路径决定是否运行：只有 `NeoJiYuTrainer/`（含 `NeoJiYuTrainer/Resources/`）、`Pack/`、`Scripts/`、`requirements.txt` 或工作流文件本身发生变化才会触发，纯文档与测试改动不会重新编译 EXE。
- 也可在 Actions 页面选择该工作流并点击 `Run workflow` 手动运行，手动运行需选择 `main` 分支才会发布；手动运行不受路径过滤限制。
- 工作流文件首次进入默认分支后，Actions 页面才会显示手动运行入口。
- 在 `windows-latest` 上使用 Python 3.13 安装依赖、执行离线检查（见[验证](Contributing.md#验证)）并运行 `Pack/Build.ps1 -Clean`；构建脚本直接产出 `Output/NeoJiYuTrainer-<显示版本>.exe` 与对应的调试版本，工作流再据此准备 `dist/` 下的资产。
- 构建成功后更新标签为 `nightly`、标题为 `Nightly Build <版本>` 的预发布版本，资产只有两个：`NeoJiYuTrainer-<显示版本>.exe` 与 `NeoJiYuTrainer_Debug-<显示版本>.exe`，显示版本是基础版本号加提交哈希（如 `0.1.0-1a8ede3`）。不再发布固定名副本，避免每次推送都在发布页额外保留两个文件（GUI 与 CLI 共用同一个 EXE，调试版只差日志等级）。
- 发布说明包含版本号、构建时间、工作流运行记录、两个资产的 SHA256，`Commits` 章节列出本次构建对应的那条提交。
- 路径过滤按整个推送的 `before..head` 判定，因此把文档提交与代码提交一起推送时仍会构建；`Commits` 章节据此说明本次构建实际包含哪些改动。
- 同一天内重复构建不新建发布：先比对现有 `nightly` 预发布的标题是否含本次的日期后缀，相同就原地更新资产与说明，标签 `nightly` 与下载地址 `https://github.com/JasonFang0109c/NeoJiYuTrainer/releases/tag/nightly` 都保持不变。
- 只有日期变了（例如旧的是 `-nightly.20261103`、新的是 `-nightly.20261104`）才删除旧预发布与 `nightly` 标签再重新创建，保证每天最多一次新的发布通知，不让关注者的动态被每次推送刷屏。
- 日期取自构建版本号的 `-nightly.YYYYMMDD` 后缀，与产物里记录的日期同源；后缀按 UTC 计日，不受运行器时区与本地时区影响。
- 资产名带提交哈希，每次构建都是新名字，`overwrite_files` 覆盖不到旧名字，因此复用当天的预发布前会先删掉全部已有资产；同一天内发布维护的历史说明由本次构建的说明整体覆盖，资产始终是两个文件。
- 使用 `nightly-build` 并发组，新的运行会取消尚未完成的旧运行。

### Release

- 只支持手动触发，不随推送自动运行；不会自动递增版本号，需先修改 `NeoJiYuTrainer/Shared/Version.py` 的 `__version__` 并提交。
- 发布前校验版本号与源码一致、正式版不带预发布后缀、标签 `vX.Y.Z` 尚不存在，任一不满足即失败。
- 资产为固定名 `NeoJiYuTrainer.exe` 与 `NeoJiYuTrainer_Debug.exe`，另附版本号副本`NeoJiYuTrainer-X.Y.Z.exe`；同一文件同时提供 GUI 与 CLI。固定名副本由工作流从构建脚本产出的 `Output/NeoJiYuTrainer-X.Y.Z.exe` 复制而来，本地 `Output/` 里只有带版本号的那一份。正式版的产物体内不带提交哈希，工作流以 `-Commit ""` 显式关闭，nightly 则传当前提交哈希。
- 发布说明的 `Changes` 章节列出上一个 `v*` 标签以来的提交标题；`make_latest: true` 使正式版成为最新版本，nightly 不受影响。
- 可选择以草稿（`draft`）创建，确认后再在 Releases 页面发布；`overwrite_files: false` 保证不会覆盖已发布资产。
- 使用 `release` 并发组且不取消进行中的运行，避免两次发布互相干扰。

两个发布工作流都使用 `GITHUB_TOKEN`，仓库需允许 Actions 写入内容；发布步骤返回 403 时，在 `Settings > Actions > General > Workflow permissions` 中允许读写权限。

## 验证

验证按改动范围选择，完整规则、命令与残留清理见[开发与提交规范](Contributing.md#验证)。与构建相关的只有一条硬要求：改动 `Pack/`、`Scripts/`、依赖清单或 `NeoJiYuTrainer/` 后必须实际构建，并用产出的 EXE 冒烟——`Output\NeoJiYuTrainer-<显示版本>.exe --version`、`-h`，再打开一次图形界面确认平台插件、图标与命令行都没坏。

没有第二台测试设备时，可另外运行本机 IP 自测：

```powershell
.\.venv\Scripts\python.exe -B .\Scripts\TestLocalIp.py
```

生成的 EXE 无参数时打开图形界面，带参数时运行命令行模式；两种模式都无需安装 Python。EXE 打包为窗口化子系统（`console=False`），双击启动不会出现控制台窗口；带参数运行时由 `NeoJiYuTrainer/Start/Service.py` 调用 `NeoJiYuTrainer/Start/Console.py` 的 `_show_cli_console()` 把标准流接回调用方的终端：优先沿用调用方传入的句柄（命令提示符的控制台句柄、Windows Terminal 的伪控制台管道、重定向到的文件），取不到时再挂到父进程的控制台，任何情况下都不新建控制台窗口；确实拿不到终端时丢弃输出，命令本身照常执行。因此从终端启动不会阻塞提示符，需要等待命令结束时用 `start /wait`。EXE 不强制请求管理员权限；防火墙操作在需要时单独弹出 UAC，并由隐藏助手执行。
