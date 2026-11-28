# 仓库协作规范

适用于本仓库全部代码、测试、构建与文档修改。本文件只放阅读入口、硬性约束与文档索引，细则全部以 `docs/` 下的文档为准；同一规则两处出现时，以 `docs/` 的完整版为准。

| 主题 | 完整版 |
| --- | --- |
| 代码风格、排版、docstring、注释、组件库资料、界面视觉规范 | [代码风格规范](docs/dev/STYLE.md) |
| 验证范围与命令、截图、残留清理、运行日志、提交信息与提交粒度 | [开发与提交规范](docs/dev/CONTRIBUTING.md) |
| 构建、打包、体积控制、运行数据、GitHub Actions 工作流 | [构建说明](docs/dev/BUILD.md) |
| 模块职责、目录结构、新增功能接入 | [项目结构](docs/dev/STRUCTURE.md) |
| 版本号与发布流程 | [版本规范](docs/dev/VERSIONING.md) |
| 界面与命令行使用说明 | [GUI 模式](docs/usage/GUI.md) 丨 [命令行](docs/usage/CLI.md) |

## 阅读范围

按改动范围决定读什么，不必通读全部文档：

| 改动范围 | 需要阅读 |
| --- | --- |
| 改文档 | 被改文档，以及引用了同一行为的其他文档 |
| 改命令行启动或 `NeoJiYuTrainer/features/*/cli.py` | `NeoJiYuTrainer/start/cli.py`、`NeoJiYuTrainer/start/parser.py`、对应功能的 `cli.py` 与 `service.py`（如有）、[CLI 文档](docs/usage/CLI.md) |
| 改 `NeoJiYuTrainerUI/gui/`、`NeoJiYuTrainer/start/gui.py` 或 `NeoJiYuTrainerUI/features/*/gui/` | [GUI 文档](docs/usage/GUI.md)、[项目结构](docs/dev/STRUCTURE.md)、[界面视觉规范](docs/dev/STYLE.md#界面视觉规范)、对应页面与服务、涉及的测试 |
| 改功能业务、报文、系统适配或公共基础 | [项目结构](docs/dev/STRUCTURE.md)、对应 `NeoJiYuTrainer/features/`、`NeoJiYuTrainer/packets/`、`NeoJiYuTrainer/system/`、`NeoJiYuTrainer/shared/` 模块与调用方 |
| 改构建、打包或工作流 | [构建说明](docs/dev/BUILD.md)、[项目结构](docs/dev/STRUCTURE.md) |
| 改代码风格、注释或 docstring | [代码风格规范](docs/dev/STYLE.md)、涉及的模块 |
| 改提交或协作规范 | 本文件、[开发与提交规范](docs/dev/CONTRIBUTING.md) |

只改文档时不需要读源码；只改某一模块时不需要读其他模块。确有必要时再扩大范围，例如改动涉及跨模块行为、或文档与代码不一致。

## 硬性约束

| 约束 | 要求 |
| --- | --- |
| 改动范围 | 只动工作区内的文件；确有必要越界时先说明原因并取得确认，临时脚本与验证产物放 `build/`（由 `.gitignore` 排除）并用完删除 |
| 系统配置 | 不改网卡 IP、路由、DNS、防火墙全局策略、系统代理、环境变量与电源计划；验证网络行为优先在进程内构造数据或走回环地址，确需调整时先说明恢复办法 |
| 依赖安装 | 一律装进仓库内 `.venv`，版本记入 `requirements.txt` 与 `requirements-dev.txt`，不装到全局环境 |
| 忽略文件 | `.gitignore` 排除的内容不进 Git、不写进提交信息；`git add` 不用 `-f`、`-A` |
| 用户数据 | `output/data/` 是用户的备注、设置与日志，任何时候都不删 |
| 提交 | 一个任务一次提交，验证通过后立即提交，不集中到任务收尾时处理，见[提交粒度](docs/dev/CONTRIBUTING.md#提交粒度) |
| 构建 | 改动 `NeoJiYuTrainer/`、`pack/`、`scripts/` 或依赖清单时必须构建并冒烟，命令见[EXE 构建](docs/dev/BUILD.md#构建-exe) |
| 验证 | 只跑这次改动真正能打断的检查，见[验证](docs/dev/CONTRIBUTING.md#验证) |
| 界面视觉 | 数值一律从 `NeoJiYuTrainerUI/gui/theme.py` 取，不写字面量，见[界面视觉规范](docs/dev/STYLE.md#界面视觉规范) |
| 组件库 | 以 PySide6 分支与本项目安装的 `PySide6-Fluent-Widgets` 为准，不套用 PyQt5/PyQt6 示例，见[组件库资料](docs/dev/STYLE.md#组件库资料) |

## 文档规则

- 需要读者执行或定位的路径可以保留，例如构建产物、运行数据目录、验证截图位置；说明用途时按需写出具体路径。
- 纯内部缓存（字节码、工具缓存、覆盖率）不在文档中列举，统一写“由 `.gitignore` 排除”；只有[残留清理](docs/dev/BUILD.md#残留清理)这类需要点名删除对象的段落才写出具体路径。
- 命令中的解释器路径（如 `.\.venv\Scripts\python.exe`）按原样书写。
- 提交前用 `git status` 确认改动文件均已被 Git 跟踪或即将被跟踪；提交信息只描述源码、文档、测试与构建配置的改动，不描述被排除的产物或缓存。

## 沟通与说明规则

- 本规则是给你（用户）用的：所有问答、说明、任务汇报、改动解释和输出结果都要让你能听懂，不只适用于文档。
- 不要从专业代码的角度解释，要按实际操作流程解释；默认你不需要了解仓库结构和源码。
- 先说清楚“这是做什么的、做完会得到什么结果”，再按顺序写操作步骤；每一步写明白在哪里做、输入什么、看到什么算成功。
- 术语第一次出现时用一句白话解释，不要只摆缩写、类名、文件名或“看源码”。
- 涉及驱动、签名、系统设置、卸载等操作时，把“前提条件”“可能影响”和“怎么恢复”单独写出来，不要埋在大段文字里。

## 完成后输出

每个任务收尾时按下面的结构汇报，能用表格就用表格，不复述已写在文档里的规则：

| 项 | 内容 |
| --- | --- |
| 改动摘要 | 一两句话说明做了什么、为什么这么做 |
| 提交 | 按提交顺序编号列出，一行一个，格式 `第 N 个提交：<短哈希> <type(scope): 中文描述>`；一次任务可能包含多个提交，全部列出，并说明这是本次任务的第几个 |
| 修改文件 | 逐个列出路径与一句话说明改了什么 |
| 验证 | 实际执行过的检查及结果（命令、用例数、截图位置、构建产物名与冒烟输出）；未执行的检查说明为什么不需要 |
| 遗留 | 没做完的事项、已知噪声（例如与改动无关的既有 flaky 用例）与下一步建议 |
