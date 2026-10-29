# 开发与提交规范

## 开发环境

Python 3.13，虚拟环境目录为 `.venv`。CLI 只依赖标准库；GUI 使用 PySide6，EXE 构建使用 PyInstaller。

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

激活后可查看解释器版本或脚本帮助，也可直接使用虚拟环境解释器：

```powershell
python --version
python cli/main.py -h
```

## 启动与构建

```powershell
python -m app.gui
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1 -Clean
```

`scripts/build.ps1` 接受 `-Python` 参数指定其他虚拟环境解释器。构建产物与虚拟环境、缓存文件均由 `.gitignore` 排除，不提交到仓库。

## 离线检查

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -X utf8 -m compileall -q cli app tests
```

## 运行日志

GUI 运行日志遵循 [日志规范](https://itliwei.github.io/technology/engineer/develop/logger.html)，等级统一使用 `DEBUG`、`INFO`、`WARNING`、`ERROR`，其中 `warn` 写作 `warning`。默认运行等级为 `INFO`，可在“设置”页切换；低于当前等级的记录不会写入列表和 `runtime.log`。

```text
2026-10-23 12:34:56.789 [12345] [MainThread] INFO    app.gui.app.MainWindow:123 - [文本消息] 开始发送：192.168.1.20，端口 4705，1 轮
    目标设备数：1
```

新增日志优先调用 `LogStore.debug/info/warning/error`，关键节点携带目标、端口、文件名、耗时等定位信息，异常附带堆栈，不记录密码、令牌等敏感信息。日志页支持功能与级别筛选、多选、导出选中、删除选中和表头全选；相关行为变更需同步更新 [GUI 说明](GUI.md) 和 `tests/test_gui.py`。

## 提交信息

参照 [Git Commit Message 规范](https://codeewander.github.io/docs/git-commit)。标题和正文使用中文，类型使用英文；代码标识符、文件名和命令参数按原样书写。

```text
[类型] 中文摘要

说明改动内容与原因，必要时补充实现方式。
```

没有关联任务时不添加任务编号；有关联任务时可写成 `项目-123: [Fix] 修复消息编码错误`。

| 类型 | 用途 |
| --- | --- |
| `Feat` | 新增功能 |
| `Fix` | 修复缺陷 |
| `Docs` | 调整文档 |
| `Style` | 调整格式，不改变程序逻辑 |
| `Refactor` | 重构现有实现 |
| `Test` | 新增或调整测试 |
| `Perf` | 优化性能 |
| `CI` | 调整持续集成配置 |
| `Hotfix` | 紧急修复严重问题 |

编写要求：

- 标题不超过 50 个字符，不以句号结尾；类型英文首字母大写，摘要使用“新增”“修复”“补充”等明确动作。
- 标题与正文之间留一个空行，正文每行不超过 72 个字符。
- 摘要说明改了什么，正文按需说明为什么改、如何实现。
- 一次提交围绕一个明确目的，不虚构任务编号或已完成的验证。
- 不描述、列举或链接被 `.gitignore` 排除的文件与目录。

```text
[Fix] 修复长消息打包越界

原实现直接写入固定大小的报文缓冲区，超长文本会导致越界。
按编码后的字节数拆分消息，并为每条消息保留字符串结束符。
```

## 仓库配置

初始化时已设置中文路径显示、UTF-8 提交编码和提交模板，使用 `git commit` 可在编辑器中查看模板提示。克隆到其他位置后需重新执行：

```powershell
git config --local commit.template .gitmessage
git config --local i18n.commitEncoding utf-8
git config --local i18n.logOutputEncoding utf-8
git config --local core.quotepath false
```

`.gitmessage` 只提供编辑提示，不会自动检查提交信息格式。
