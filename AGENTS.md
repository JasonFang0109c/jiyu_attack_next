# 仓库协作规范

适用于本仓库全部代码、测试、构建与文档修改。以下条目按改动范围判断是否适用：只做与某节无关的改动时，跳过该节，不必为了走流程而执行。

改动请尽量限制在仓库内：尽量不要修改或新建工作区（本仓库根目录）之外的文件。确有必要时先说明原因并取得确认，临时脚本与验证产物放在已被 `.gitignore` 排除的 `build/` 下，用完删除。

不要随意更改 Windows 的系统配置，例如网卡 IP、路由、DNS、防火墙全局策略、系统代理、系统环境变量与电源计划。验证网络行为时优先在本进程内构造数据或使用回环地址，确实需要调整系统状态时先说明原因与恢复办法并取得确认，用完后立即还原。

不要随意在全局环境（系统 Python、`pip install` 到 site-packages、全局 Node/npm 等）中安装库。项目依赖一律装进仓库内的 `.venv`，并通过 `requirements.txt`、`requirements-dev.txt` 记录版本。

## 阅读范围

按改动范围决定读什么，不必通读全部文档：

| 改动范围 | 需要阅读 |
| --- | --- |
| 改文档 | 被改文档，以及引用了同一行为的其他文档 |
| 改 `app/cli/` | `app/cli/main.py`、[CLI 文档](docs/usage/CLI.md) |
| 改 `app/gui/` | [GUI 文档](docs/usage/GUI.md)、[项目结构](docs/dev/STRUCTURE.md)、涉及的模块与测试 |
| 改构建、打包或工作流 | [构建说明](docs/dev/BUILD.md)、[项目结构](docs/dev/STRUCTURE.md) |
| 改代码风格、注释或 docstring | [代码风格规范](docs/dev/STYLE.md)、涉及的模块 |
| 改提交或协作规范 | 本文档、[开发与提交规范](docs/dev/CONTRIBUTING.md) |

只改文档时不需要读源码；只改某一模块时不需要读其他模块。确有必要时再扩大范围，例如改动涉及跨模块行为、或文档与代码不一致。

## 忽略文件约束

`.gitignore` 排除的内容不纳入 Git，也不得出现在 Git 提交信息中。当前排除项：

| 路径 | 说明 |
| --- | --- |
| `.venv/`、`venv/`、`env/` | Python 虚拟环境 |
| `__pycache__/`、`*.py[cod]` | 字节码缓存 |
| `.pytest_cache/`、`.mypy_cache/`、`.ruff_cache/`、`.coverage`、`htmlcov/` | 工具与覆盖率缓存 |
| `build/`、`output/` | 构建缓存与构建产物 |
| `JiYuAttackNextData/` | 便携运行数据（备注、设置、运行日志）；`output/` 下的那一份是用户数据，任何时候都不要删除 |
| `.env`、`.env.*`（`!.env.example` 除外） | 本地环境配置 |
| `Thumbs.db`、`.DS_Store` | 系统生成文件 |

文档规则：

- 需要读者执行或定位的路径可以保留，例如构建产物、运行数据目录、验证截图位置；说明用途时按需写出具体路径。
- 纯内部缓存（字节码、工具缓存、覆盖率）不在文档中列举，统一写“由 `.gitignore` 排除”。
- 命令中的解释器路径（如 `.\.venv\Scripts\python.exe`）按原样书写。
- 提交前用 `git status` 确认改动文件均已被 Git 跟踪或即将被跟踪；`git add` 不使用 `-f`、`-A` 等会带入忽略文件的方式。
- 提交信息只描述源码、文档、测试与构建配置的改动，不描述被排除的产物或缓存。

## GUI 组件

只在新增或改动 `qfluentwidgets` 组件用法时查阅官方资料；调整布局参数、文案或已有控件的调用不必重新查证。

- [QFluidWidgets 文档](https://qfluentwidgets.com/)
- [PySide6 分支源码](https://github.com/zhiyiYo/PyQt-Fluent-Widgets/tree/PySide6)
- [PySide6 示例](https://github.com/zhiyiYo/PyQt-Fluent-Widgets/tree/PySide6/examples)

- 以 PySide6 分支和本项目安装的 `PySide6-Fluent-Widgets` 版本为准，不套用 PyQt5/PyQt6 示例。
- 复用 `qfluentwidgets` 已有组件、主题与样式，不重复实现；亚克力与云母统一调用组件自带的 `windowEffect`，不自行用 ctypes 操作窗口材质。
- 文档、示例与本地版本冲突时，通过导入、源码或最小测试验证后再改。
- GUI 行为或交互变化时同步更新 [GUI 文档](docs/usage/GUI.md) 与 `tests/test_gui.py`。

## 代码约定

- Python 3.13；GUI 使用 PySide6。`app/core/` 与 `app/cli/` 可以使用第三方库（当前用到 `av`/PyAV 解码 H.264、`Pillow` 还原缩略图），新依赖一律写进 `requirements.txt` 并在 `docs/dev/BUILD.md` 说明打包影响。
- 保持目录职责与模块边界，参考 [项目结构](docs/dev/STRUCTURE.md)。
- 改动前检查 `git status`，不回退或提交与任务无关的改动。
- 行为变更补充或更新对应测试；纯文档、注释或格式改动不需要新增测试。
- 用户可见行为、命令参数、构建方式或项目结构变化时同步更新对应文档。

## 代码风格

完整规则见[代码风格规范](docs/dev/STYLE.md)，配置在根目录 `pyproject.toml`（ruff 格式化与 lint、行宽 88、目标版本 `py313`）。

**每写完一处代码就格式化一次，不要攒到提交前统一处理。**

```powershell
.\.venv\Scripts\python.exe -m ruff format .
.\.venv\Scripts\python.exe -m ruff check --fix .
```

- 排版交给 `ruff format`，不手工对齐 `=`、`:` 或续行括号，也不用行尾短注释。
- `app/core/constants.py` 的十六进制报文数组被 ruff 排除，新增报文时沿用现有每行字节数与缩进，不要重排已有行。
- docstring 用 Google 风格（`Args`、`Returns`、`Yields`、`Raises`、`Attributes`，说明文字中文），只写模块、公共类、公共函数与逻辑复杂的函数。
- 注释一律整行中文，解释“为什么”而非复述代码；待办写成 `# TODO(负责人): 具体动作`。
- 提交前用 `ruff format --check .` 与 `ruff check .` 确认没有待格式化或待修复内容；纯排版改动按 `Style` 类型单独提交，不与功能改动混在一起。

## GUI 日志

只在改动 GUI 日志行为或日志调用点时适用。日志规范参考 [日志规范](https://itliwei.github.io/technology/engineer/develop/logger.html)，`warn` 统一写作 `warning`。

- 只使用 `DEBUG`、`INFO`、`WARNING`、`ERROR` 四个等级，不引入中文等级存储值。
- 等级是写入阈值，低于阈值的记录不进入列表与日志文件。正常版本默认 `WARNING`，设置页可以在 `INFO`、`WARNING`、`ERROR` 之间调整，`DEBUG` 记录只存在于 `_Debug` 版本；调试版本固定从 `DEBUG` 起全量记录，设置页的下拉框随之禁用，配置文件里的默认等级也不参与判断。命令行没有开关，按变体默认等级写入。
- `DEBUG` 用于参数快照、进度与返回值；`INFO` 用于启动、关键操作、任务开始与完成；`WARNING` 用于可恢复异常、参数问题与用户取消；`ERROR` 用于任务失败与异常。
- 用户可见的成功 InfoBar 对应 `INFO`，失败对应 `ERROR`，可恢复提示对应 `WARNING`。
- 每条日志包含毫秒时间、线程 ID 与名称、级别、模块与行号、功能分类和消息。
- 关键节点带上定位信息（目标、端口、轮数、文件名、字节数、耗时、异常类型），不写只有“执行失败”的日志。
- 异常日志附完整异常文本或堆栈；`SendWorker`、`TaskWorker` 的 `failed` 信号同时传递消息与堆栈，不只保留 `str(error)`。
- 不记录密码、令牌等敏感信息。
- 使用 `LogStore.debug/info/warning/error` 或带等级的 `LogStore.add`，不在业务代码拼接格式。

日志文件与界面：

- `runtime.log` 格式：`yyyy-MM-dd HH:mm:ss.SSS [线程ID] [线程名] LEVEL   模块:行号 - [功能] 消息`，多行与堆栈以四空格缩进续行。
- 按时间顺序追加；删除或清空时重写文件，保持与界面、内存一致。
- 读取时兼容旧版 JSONL 并迁移为规范文本，不因历史格式导致启动失败。
- 日志页支持功能与精确级别筛选、多选、导出选中、删除选中与表头全选。表头复选框位于时间列之前、样式与行内一致：勾选后选中当前筛选结果，任一行取消即取消表头，取消表头则清空全部选择。导出与删除按钮只处理选中记录，未选择时禁用。
- 修改日志筛选、批量操作或文件格式时，同步更新 [GUI 文档](docs/usage/GUI.md) 与 `tests/test_gui.py`。

## 验证

按改动范围选择检查，不必每次都跑全套：

| 改动范围 | 检查 |
| --- | --- |
| 只改 Markdown | 校验链接与命令可用性，不需要跑测试 |
| 改 `app/`、`packaging/` 或 `scripts/` | 离线测试 + `compileall` |
| 改 GUI 界面或交互 | 上述检查，并按需截图确认 |
| 改构建脚本或工作流 | 上述检查，并实际执行一次构建 |

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -X utf8 -m compileall -q app tests
.\.venv\Scripts\python.exe -B -m tests.verify_gui --screenshot <截图路径>
```

测试结果不稳定时先确认是否与本次改动相关；与改动无关的既有失败如实报告，不要反复重跑掩盖问题。只报告实际执行过的验证，未执行的检查要说明。

测试、`compileall` 与截图验证结束后按“构建 → 残留清理”收尾。

## 构建

只在改动会影响 EXE 内容时构建：`app/`、`packaging/`、`scripts/`、`assets/`、依赖清单。纯文档、注释和测试改动不需要构建。

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build.ps1
```

- 需要构建时，构建失败不得提交。
- 构建产物由 `.gitignore` 排除，不纳入提交。
- 修改构建配置或需排除旧缓存时使用 `-Clean`。

### 残留清理

构建、测试与截图验证结束后立即清理本次产生的残留，仓库里只保留 `output\JiYuAttackNext.exe`：

- 删除 `build\` 整个目录：它是 PyInstaller 的 `--workpath`，含中间文件、图标与版本资源。
- 删除验证用的临时脚本与截图，例如 `output\verify_*.png`、`build\tmp\*`。
- 字节码与工具缓存同样在收尾时删除，不要只靠 `.gitignore` 兜底，避免污染备份与磁盘。
- **不删除 `output\JiYuAttackNextData\`。** 里面的备注、设置与运行日志是用户自己的数据，不管它是构建、测试还是截图验证产生的，收尾时都原样保留；需要干净的验证环境时换用其他目录或临时数据目录，不要删它。

## Git 提交

**改完就提交，不要等用户催。** 代码、测试或文档改完并通过对应验证后，任务还没结束——必须按下面的提交粒度立即提交，再汇报结果。把“验证通过、构建成功”当成收尾、把提交留给用户提醒，属于未完成任务；不提交就把改动留在工作区同样不允许。

提交前完成与改动范围匹配的验证（见“验证”与“构建”）。

### 提交粒度

**一个任务对应一次提交，不是一次对话对应一次提交。**

- “任务”指一个可独立完成、可独立验证的改动目标（例如“修复悬停测试”“精简文档”），与对话轮次无关。
- 一次对话包含多个任务时，每完成一个任务就验证并提交一次，不要在对话结束时合并成一次提交。
- 一个任务只提交一次，不要拆成多次提交，也不要混入其他任务的改动。
- 对话中只完成了部分任务时，已完成的那些任务各自提交，未完成的保持未提交状态。

### 提交步骤

1. 检查 `git status` 与 `git diff`，确认只包含当前任务的改动。
2. 只暂存相关文件，不带入无关改动与忽略文件。
3. 按 [Git Commit Message 规范](https://codeewander.github.io/docs/git-commit) 编写提交信息。

```text
[类型] 中文摘要

说明改动内容与原因，必要时补充实现方式。
```

- 类型：`Feat`、`Fix`、`Docs`、`Style`、`Refactor`、`Test`、`Perf`、`CI`、`Hotfix`。
- 标题不超过 50 个字符、不以句号结尾；标题与正文间留一个空行，正文每行不超过 72 个字符。
- 摘要与正文使用中文；代码标识符、文件名与命令参数按原样书写。
- 提交信息只描述源码、文档、测试与构建配置的改动，不描述被 `.gitignore` 排除的产物或缓存。
- 一个任务对应一个明确提交目的；不虚构任务编号、测试结果或未完成的验证。
- 一次对话中每个任务各自提交，不因为对话只结束一次而只提交一次。
