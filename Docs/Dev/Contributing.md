<div align="center">
<h1>开发与提交规范</h1>
<p>
   <img alt="Python 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=212121">
   <img alt="Commit" src="https://img.shields.io/badge/提交信息-中文-2CA5E0?style=for-the-badge&labelColor=212121">
</p>
<p><a href="../../README.md">← 返回项目首页</a> 丨 <a href="Structure.md">项目结构</a> 丨 <a href="Style.md">代码风格</a> 丨 <a href="Build.md">EXE 构建</a> 丨 <a href="Versioning.md">版本规范</a></p>
</div>

---

## 开发环境

Python 3.13，虚拟环境目录为 `.venv`。命令行模式只依赖标准库；GUI 使用 PySide6，EXE 构建使用 PyInstaller。

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` 只放本地开发工具（目前是 ruff），不需要打进 EXE。

激活后可查看解释器版本或脚本帮助，也可直接使用虚拟环境解释器：

```powershell
python --version
python -m NeoJiYuTrainer -h
```

`python -m NeoJiYuTrainer` 是统一入口，由 `NeoJiYuTrainer/Start/Service.py` 分流到命令行或 GUI 启动流程。运行时代码按 `NeoJiYuTrainer/Start/`、`NeoJiYuTrainer/Features/`、`NeoJiYuTrainerUI/Gui/`、`NeoJiYuTrainerUI/Features/`、`NeoJiYuTrainer/Packets/`、`NeoJiYuTrainer/System/`、`NeoJiYuTrainer/Shared/` 与 `NeoJiYuTrainer/Resources/` 划分；功能参数由各自的 `Cli.py` 注册，页面由主窗口显式装配，边界与接入步骤见[项目结构](Structure.md#新增功能)。

## 启动与构建

```powershell
python -m NeoJiYuTrainer
powershell -ExecutionPolicy Bypass -File .\Pack\Build.ps1 -Clean
```

`Pack/Build.ps1` 接受 `-Python` 参数指定其他虚拟环境解释器，`-Version` 覆盖版本号（默认读取 `NeoJiYuTrainer/Shared/Version.py` 的 `__version__`）。构建产物与虚拟环境、缓存文件均由 `.gitignore` 排除，不提交到仓库。

## 版本号

版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)，当前处于 `0.y.z` 阶段，完整规则与发布流程见[版本规范](Versioning.md)。

- 权威来源是 `NeoJiYuTrainer/Shared/Version.py` 的 `__version__`；`NeoJiYuTrainer/__init__.py` 只重新导出该值，命令行 `--version` 也读取同一来源，由 `Tests/Pack/TestVersioning.py` 校验。
- 新增功能升次版本号，修复升修订号，文档、测试、工作流等不影响产物的改动不递增。
- nightly 与正式版共用同一版本号；nightly 的显示版本由工作流在基础版本号后追加 7 位提交哈希，带日期的版本号只出现在发布说明与标签里，都不需要手工维护。
- 正式版通过 Actions 页面的 `Release` 工作流手动发布，不要在本地打标签后手工上传资产。

## 代码风格

排版交给 `ruff format`，静态检查交给 `ruff check`，注释与 Docstring 手写，**每写完一处代码就格式化一次**，不要攒到提交前统一处理。行宽、目标版本、Docstring 与注释写法、界面视觉规范等完整规则见[代码风格规范](Style.md)；提交前用 `ruff format --check .` 与 `ruff check .` 确认没有待格式化或待修复内容，纯排版改动按 `style` 类型单独提交，不与功能改动混在一起。

## 验证

验证跟着改动走：只做这次改动真正能打断的检查，不为“稳妥”跑与改动无关的全套流程。

| 改动内容 | 需要做的事 | 不需要做的事 |
| --- | --- | --- |
| 只改 Markdown、注释、Docstring | 通读一遍，确认示例命令与路径没有写错 | 测试、`compileall`、构建、截图 |
| 只改测试文件 | 跑被改的那个测试文件 | 全量测试、`compileall`、构建 |
| 改 `NeoJiYuTrainer/Features/` 的非界面业务、`NeoJiYuTrainer/Packets/`、`NeoJiYuTrainer/System/`、`NeoJiYuTrainer/Shared/` | 跑对应 `Tests/Unit/`、`Tests/Integration/` 测试；改动跨模块或涉及报文字节布局时跑全量测试 | 截图、构建 |
| 改命令行启动或 `NeoJiYuTrainer/Features/*/Cli.py` | 跑 `Tests.Unit.TestCliParser` 及对应的 `Tests.Integration.TestCliCommands`、`Tests.Integration.TestCliLifecycle`、`Tests.Integration.TestEntry` | 截图、构建 |
| 改 `NeoJiYuTrainerUI/Gui/`、`NeoJiYuTrainer/Start/Gui.py` 或 `NeoJiYuTrainerUI/Features/*/Gui/` 的逻辑（线程、任务分发、信号） | 跑 `Tests.Gui.TestWindow` 加对应界面或业务测试 | 截图（除非外观也变了） |
| 改 GUI 外观、布局、文案或交互（含功能目录中的 GUI） | 跑 `Tests.Gui.TestWindow` 与对应界面测试，并按需截图确认 | 全量测试 |
| 改 `Pack/`、`Scripts/`、依赖清单、构建配置 | 实际执行一次[构建](Build.md#构建-exe)，并用构建出的 EXE 冒烟 | 全量测试（除非同时改了 `NeoJiYuTrainer/`） |
| 同时涉及多类 | 取并集，但每一项只做一次 | — |

```powershell
# 单个文件
.\.venv\Scripts\python.exe -B -m unittest Tests.Unit.TestCliParser -v

# 全量
.\.venv\Scripts\python.exe -B -m unittest discover -s Tests -t . -v
```

- 语法检查用 `compileall` 只在无法运行测试时才有意义（例如改的是入口脚本或打包钩子）；测试能跑起来就不必再单独跑一遍。
- 测试结果不稳定时先确认是否与本次改动相关；与改动无关的既有失败如实报告，不要反复重跑掩盖问题。
- 只报告实际执行过的验证，未执行的检查要说明为什么不需要。
- 截图只在意外观时做，命令是 `.\.venv\Scripts\python.exe -B -m Tests.Gui.VerifyGui --page <页面> --screenshot <截图路径>`，需要深色主题时加 `--theme dark`。验证数据目录固定在 `Build\VerifyGuiData`，不碰 `Output\Data`。测试与截图验证的临时文件都写在 `Build\TestData` 与 `Build\VerifyGuiData` 下，用例结束尽量自删，被占用的残目录由 `Pack\CleanBuild.ps1` 在下次构建前统一删除。
- 测试、构建或截图验证后，按[残留清理](Build.md#残留清理)清掉本次产生的残留；是否构建按上表的改动范围判断，纯文档改动无需构建。

### 本机 IP 自测

没有第二台测试设备时，可用本机 IPv4 地址验证真实报文收发：

```powershell
.\.venv\Scripts\python.exe -B .\Scripts\TestLocalIp.py
```

脚本自动选择本机局域网地址，在系统分配的空闲 UDP 端口上依次发送并校验文本消息、远程命令、重启、关机、注销和连续发送报文，不需要安装或运行学生端。默认使用多网卡环境检测到的可用地址，检测异常时可用 `--target 127.0.0.1` 指定回环地址，用 `--repeat` 调整连续发送次数，用 `--port` 固定接收端口。

该脚本会创建真实 UDP 套接字，不属于 `Tests/` 下的离线测试套件；`unittest` 运行期间仍保持全局禁止真实网络访问。

## 运行日志

仅在改动 GUI 或 CLI 日志行为、调用点时适用。GUI 运行日志遵循 [日志规范](https://itliwei.github.io/technology/engineer/develop/logger.html)，等级统一使用 `DEBUG`、`INFO`、`WARNING`、`ERROR`，其中 `warn` 写作 `warning`。正常版本默认 `WARNING`，可在“设置”页切到 `INFO` 或 `ERROR`；调试版本固定从 `DEBUG` 起全量记录，下拉框不可用。低于写入阈值的记录不会进入列表和 `Log/Runtime.log`。

```text
2026-10-23 12:34:56.789 [12345] [MainThread] INFO    NeoJiYuTrainerUI.Gui.Service.GuiService:183 - [文本消息] 开始发送：[REDACTED]，端口 4705，1 轮
    目标设备数：1
```

新增日志优先调用 `LogStore.debug/info/warning/error`，关键节点携带目标、端口、文件名、耗时等定位信息，异常附带堆栈，不记录密码、令牌等敏感信息。日志页支持功能与级别筛选、多选、导出选中、删除选中和表头全选；相关行为变更需同步更新 [GUI 模式使用说明](../Usage/Gui.md) 和 `Tests/Gui/TestWindow.py`、`Tests/Gui/TestLogPage.py`、`Tests/Gui/TestLogStore.py` 中的对应测试。

命令行模式写自己的日志文件 `Log/Cli.log`，与界面的 `Log/Runtime.log` 分开，两者共用一个数据目录，规则在 `NeoJiYuTrainer/Shared/Paths.py`。实现位于 `NeoJiYuTrainer/Shared/Logs/Cli.py` 的 `CliLog`：只依赖标准库，写入阈值跟构建变体一致（正常版 `WARNING`、调试版 `DEBUG`），命令行没有等级开关，命令行启动层与各功能的 CLI 适配使用它记录日志，而不是 `LogStore`（`LogStore` 依赖 PySide6，命令行入口不允许导入 Qt）。格式与界面日志一致，便于同一套工具阅读：

```text
2026-11-04 13:29:10.527 [10440] [MainThread] DEBUG   NeoJiYuTrainer.Start.Cli.log_arguments:31 - [命令行] 命令行参数
    group=remote；command=message；target=10.49.151.29；port=4705；message=已提供；command_text=未提供；file_count=0；loops=1；interval=22
```

新增命令行日志按功能分类记录目标、端口、报文数量、送达判定与异常等诊断信息；只记录消息和命令正文是否提供，不记录正文内容、密码或令牌。`NeoJiYuTrainer/Start/Cli.py` 的 `main()` 已用 `finally` 关闭句柄，无需在分支里手动关闭。

## 提交信息

采用 [Conventional Commits 1.0.0](https://www.conventionalcommits.org/zh-hans/v1.0.0/)。本项目默认填写 `scope`，**尽可能要有标注scope**，优先选择最相关模块；确实没有合适范围时允许省略，不设硬性校验。`type` 与填写的 `scope` 使用小写英文；description、body 和 footer 的说明文字使用中文。机器识别关键字、代码标识符、文件名、命令参数、issue 编号与提交哈希保留原样。

```text
<type>(<scope>): <中文描述>

<可选正文：说明改动原因、实现方式与实际验证>

<可选 footer：Token: 值 或 Token #值>
```

### 类型与范围

| 类型 | 用途 |
| --- | --- |
| `feat` | 新增功能 |
| `fix` | 修复缺陷，包括紧急修复 |
| `docs` | 调整文档 |
| `style` | 调整格式，不改变程序逻辑 |
| `refactor` | 重构现有实现，不新增功能或修复缺陷 |
| `perf` | 优化性能 |
| `test` | 新增或调整测试 |
| `build` | 调整构建、打包或依赖 |
| `ci` | 调整持续集成配置与工作流 |
| `chore` | 其他维护事项，如开发工具配置 |
| `revert` | 通过新提交撤销既有改动 |

- `type` 仅限上表的小写英文类型；紧急修复统一使用 `fix`。
- `scope` 默认填写，尽可能标明最相关模块或事项，按下面的项目作用域表选择；使用小写英文，多词用 `-` 连接。确实没有合适范围时可省略，Header 使用 `type: 中文描述`，不设硬性校验。
- Header 使用半角圆括号与冒号，冒号后留一个空格；不在 Header 前添加任务编号或其他前缀。

### 项目作用域

| scope | 对应职责 |
| --- | --- |
| `repo` | 全仓结构与协作规范 |
| `start` | 启动与注册 |
| `cli` | 通用命令行 |
| `gui` | 通用界面 |
| `message` | 消息 |
| `command` | 命令 |
| `device` | 设备 |
| `files` | 文件传送 |
| `names` | 设备备注 |
| `local` | 本机信息 |
| `firewall` | 防火墙 |
| `classroom` | 课堂助手 |
| `student` | 学生端 |
| `shell` | 终端 |
| `logs` | 日志 |
| `settings` | 设置 |
| `packets` | 报文 |
| `system` | 系统适配 |
| `shared` | 公共基础 |
| `resources` | 图标资源 |
| `pack` | 打包 |
| `tests` | 测试框架 |
| `docs` | 文档 |
| `ci` | 工作流 |
| `deps` | 依赖 |

- 按主功能选择最具体的作用域；跨模块时选择共同职责，没有更合适的共同范围时用 `repo`。
- 类型与作用域独立：文件传送测试用 `test(files)`，命令行文档用 `docs(cli)`；`tests` 用于测试框架本身，`docs` 用于通用文档事项。
- 不必为每个文件夹设置 scope。GUI 内部的 `widgets`、`menu`、`workers` 归 `gui`，测试 `fixtures` 归 `tests`；作用域表达职责，不强求与目录逐字对应。
- 新增作用域须有独立职责，并同步更新此表，避免为临时文件或实现细节增加名称。

### 描述与长度

- Header 整行不超过 50 个字符，包含类型、可选范围、冒号后的空格；按字符数而非 UTF-8 字节数或终端显示宽度计。描述不以句号结尾，使用“新增”“修复”“补充”等明确动作。
- body 可省略；需要时与 Header 间留一个空行，每行不超过 72 个字符，可分段说明为什么改、如何实现与实际完成的验证。
- 上述 50/72 限制是项目沿用的严格要求，并非 Conventional Commits 强制的通用长度限制。
- description、body 与 footer 的说明文字使用中文；`BREAKING CHANGE`、`Closes`、`Fixes`、`Refs` 等关键字保留英文，必要标识符保留原样。
- 一次提交围绕一个明确目的，不虚构 issue、任务编号、测试结果或未完成的验证。提交信息只描述源码、文档、测试与构建配置的改动，不描述被 `.gitignore` 排除的产物或缓存。

### 破坏性变更与 footer

- 破坏性变更**不在标题加 `!`**：Header 照常写 `type(scope): 中文描述`，在 footer 中添加 `BREAKING CHANGE: 中文说明`。任意类型都可以包含破坏性变更，是否破坏性只由 footer 判断。
- `BREAKING CHANGE` 的值要说明具体影响与迁移方式，不要只写“有破坏性变更”；body 里也可先交代改动原因。`BREAKING CHANGE` 必须大写，`BREAKING-CHANGE` 是官方认可的等价 token。
- footer 位于提交末尾，与 body 间留一个空行；没有 body 时与 Header 间留一个空行。每项使用 `Token: 值` 或 `Token #值`，分隔符分别为半角冒号加空格、空格加 `#`。
- 多词 token 用 `-` 连接，例如 `Reviewed-by`；`BREAKING CHANGE` 是允许空格的特例。值可跨行，下一项 token 与分隔符开始新的 footer。说明文字用中文，真实编号、姓名、哈希等标识值保留原样。
- 关联 issue 放在 footer：关闭问题用 `Closes #<实际编号>` 或 `Fixes #<实际编号>`，仅引用时用 `Refs: #<实际编号>`。这里只展示占位语法，实际使用须将占位符替换为真实关联编号并去掉尖括号；没有关联 issue 就省略，不编造编号。

以下均为格式示例，不表示这些变更或验证已经完成：

```text
fix(Packets): 修复长消息打包越界

原实现直接写入固定大小的报文缓冲区，超长文本会导致越界。
按编码后的字节数拆分消息，并为每条消息保留字符串结束符。
```

```text
feat(cli): 移除旧的参数别名

统一参数名称，减少同一选项的多种写法。

BREAKING CHANGE: 旧别名不再接受，调用方需按帮助信息更新命令。
```

issue footer 的占位示例（按实际关联选择所需项）：

```text
Closes #<实际编号>
Fixes #<实际编号>
Refs: #<实际编号>
```

`revert` 提交的正文应说明撤销原因，并用 `Refs: <真实提交哈希>` 标明被撤销的提交。新增撤销提交，不改写历史。

### 发布语义

`feat`、`fix`、破坏性变更分别对应 SemVer 的 MINOR、PATCH、MAJOR 发布语义；包含破坏性变更时以破坏性变更为准，其他类型本身不隐含递增级别。本项目仍处于 `0.y.z` 阶段，不兼容变更按现有[版本规范](Versioning.md#递增规则)递增次版本号。

这些对应关系用于判断发布影响，不代表执行提交就自动更新版本号。实际版本维护与发布仍遵循[版本规范](Versioning.md)，新规范也不要求追溯改写历史提交。

### 分支与提交位置

默认在当前工作分支直接完成并提交任务；仓库默认工作分支为 `main`，若当前已在 `main`，没有用户另行指定时就直接在 `main` 上提交。不要为了单个任务自行创建、切换或保留临时分支，也不要把提交只留在未合并分支上。若开始时已处于其他分支，默认继续在该当前分支提交，不擅自切回 `main`；只有用户明确要求切换/合并，或任务明确需要并行隔离时才使用其他分支。临时分支完成后按任务要求整合回目标分支，并在验证完成后删除临时分支。

### 提交粒度

**一个任务对应一次提交，不是一次对话对应一次提交。**

“做一点提交一点”以独立任务为单位：完成一个任务，就按改动范围验证、按需构建并立即提交，再继续下一个任务。

- “任务”指一个可独立完成、可独立验证的改动目标（例如“修复悬停测试”“精简文档”），与对话轮次无关。
- 一次对话包含多个任务时，每完成一个任务就验证并提交一次，不要在对话结束时合并成一次提交。
- 一个任务只提交一次，不要拆成多次提交，也不要混入其他任务的改动。
- 对话中只完成了部分任务时，已完成的那些任务各自提交，未完成的保持未提交状态。

提交前检查 `git status` 与 `git diff`，只暂存当前任务的相关文件，不带入无关改动或忽略文件；忽略文件约束见[仓库协作规范](../../AGENTS.md#硬性约束)。新规范仅用于后续提交，保留已有提交历史。

## 仓库配置

初始化时已设置中文路径显示、UTF-8 提交编码和提交模板，使用 `git commit` 可在编辑器中查看模板提示。克隆到其他位置后需重新执行：

```powershell
git config --local commit.template .gitmessage
git config --local i18n.commitEncoding utf-8
git config --local i18n.logOutputEncoding utf-8
git config --local core.quotepath false
```

`.gitmessage` 只提供编辑提示，不会自动检查提交信息格式。
