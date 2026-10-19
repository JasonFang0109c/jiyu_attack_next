# 开发与提交规范

## 本地开发环境

项目使用 Python 3.13，虚拟环境目录为 `.venv`。CLI 只依赖 Python 标准库；GUI 使用 PySide6，EXE 构建使用 PyInstaller。

在项目根目录执行：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

激活后，可查看解释器版本或脚本帮助：

```powershell
python --version
python main.py -h
```

安装 GUI 和构建依赖：

```powershell
python -m pip install -r requirements.txt
```

也可以直接使用虚拟环境解释器，无需激活：

```powershell
.\.venv\Scripts\python.exe main.py -h
```

虚拟环境和缓存文件已通过 `.gitignore` 排除，不提交到仓库。

## 图形界面与构建

启动图形界面：

```powershell
python gui.py
```

构建 Windows EXE：

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1 -Clean
```

构建产物为 `dist\JiyuUdpTest.exe`。`build.ps1` 接受 `-Python` 参数来指定其他虚拟环境解释器；默认使用 `.venv\Scripts\python.exe`。

提交界面或打包配置前，可运行离线检查：

```powershell
.\.venv\Scripts\python.exe -B -m unittest -v test_core test_gui
.\.venv\Scripts\python.exe -X utf8 -m compileall -q main.py gui.py gui_worker.py
```

## 提交信息

本项目参照 [Git Commit Message 规范](https://codeewander.github.io/docs/git-commit) 编写提交信息。标题和正文使用中文，类型使用英文；代码标识符、文件名和命令参数按原样书写。

### 格式

```text
[类型] 中文摘要

说明改动内容与原因，必要时补充实现方式。
```

没有关联任务时不添加任务编号；有关联任务时，可在标题前加上真实编号，例如 `项目-123: [Fix] 修复消息编码错误`。

### 类型

| 类型 | 用途 | 示例 |
| --- | --- | --- |
| `Feat` | 新增功能 | `[Feat] 支持从文本文件读取消息` |
| `Fix` | 修复缺陷 | `[Fix] 修复长消息打包越界` |
| `Docs` | 调整文档 | `[Docs] 补充虚拟环境使用说明` |
| `Style` | 调整格式，不改变程序逻辑 | `[Style] 统一函数间空行` |
| `Refactor` | 重构现有实现 | `[Refactor] 整理消息读取逻辑` |
| `Test` | 新增或调整测试 | `[Test] 补充消息容量边界测试` |
| `Perf` | 优化性能 | `[Perf] 减少报文打包时的重复编码` |
| `CI` | 调整持续集成配置 | `[CI] 配置离线检查流程` |
| `Hotfix` | 紧急修复严重问题 | `[Hotfix] 修复启动异常` |

### 编写要求

- 标题建议不超过 50 个字符，不以句号结尾。
- 类型按上表书写，保持英文首字母大写；中文摘要使用“新增”“修复”“补充”等明确动作。
- 标题与正文之间留一个空行，正文每行不超过 72 个字符。
- 摘要说明改了什么，正文按需要说明为什么改、如何实现。
- 一次提交围绕一个明确目的；不要虚构任务编号或已完成的验证。

### 示例

```text
[Fix] 修复长消息打包越界

原实现直接写入固定大小的报文缓冲区，超长文本会导致越界。
按编码后的字节数拆分消息，并为每条消息保留字符串结束符。
```

## 本仓库配置

初始化时已为当前仓库设置中文路径显示、UTF-8 提交编码和提交模板。使用 `git commit` 可在编辑器中查看模板提示。

克隆到其他位置后，以下配置需要在新仓库中重新执行：

```powershell
git config --local commit.template .gitmessage
git config --local i18n.commitEncoding utf-8
git config --local i18n.logOutputEncoding utf-8
git config --local core.quotepath false
```

`.gitmessage` 用于提供编辑提示，不会自动检查提交信息格式。
