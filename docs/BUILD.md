# EXE 构建说明

以下命令均以项目根目录为工作目录。构建脚本位于 `scripts/`，使用 PyInstaller 生成 Windows 单文件图形程序。

## 准备环境

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

已有虚拟环境时无需重新创建。GUI 和打包依赖的版本以根目录 [requirements.txt](../requirements.txt) 为准。

GUI 使用 Fluent 组件库；若已有旧虚拟环境，请重新执行一次 `python -m pip install -r requirements.txt`，安装 `PySide6-Fluent-Widgets` 及其依赖。

## 源码运行

| 运行方式 | 命令 |
| --- | --- |
| 命令行帮助 | `python cli/main.py -h` |
| 图形界面 | `python -m app.gui` |
| 虚拟环境启动脚本 | `powershell -ExecutionPolicy Bypass -File .\scripts\run_gui.ps1` |

脚本版 `cli/main.py` 是独立单文件，可直接复制运行，不依赖项目其他文件或第三方库。GUI 实现位于 `app/gui/`，复用脚本版中的标准库接口。

## 构建 EXE

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1
```

清理 PyInstaller 缓存后重新构建：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1 -Clean
```

使用其他解释器：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1 -Python "C:\Python313\python.exe"
```

脚本根据自身路径定位项目根目录，也可从其他目录通过绝对路径调用。默认使用项目 `.venv`，并读取 [scripts/JiYuAttackNext.spec](../scripts/JiYuAttackNext.spec)。打包配置会一并收集 Fluent Widgets 的运行时资源与包元数据。

## 输出与清理

| 路径 | 内容 | 是否保留 |
| --- | --- | --- |
| `output/JiYuAttackNext.exe` | 单文件窗口程序 | 保留用于运行和分发 |
| `build/JiYuAttackNext/` | 打包中间文件与分析结果 | 构建后可删除 |
| `build/assets/app.ico` | 从 SVG 转换的构建图标 | 构建后可删除 |
| `build/previews/` | 手动生成的界面验证截图 | 检查后可删除 |
| `assets/app.svg` | 图标源文件 | 随源码保留 |
| `JiYuAttackNextData/`（EXE 同级） | 运行后生成的设备备注与日志 | 需要保留配置时随 EXE 一起移动 |

删除 `build/` 不影响已生成的 EXE，下次构建会重新生成所需文件。`build/`、`output/` 和 `.venv/` 均不提交到 Git。

运行 EXE 后，程序会在其所在目录创建 `JiYuAttackNextData` 子文件夹：`settings.ini` 保存设备备注与关闭窗口行为，`runtime.log` 保存规范文本运行日志。日志包含毫秒时间、规范级别、线程、输出位置、功能分类、消息与异常详情，便于从用户环境回传排查。只移动 EXE 而不移动该文件夹时，新位置会按默认配置启动。第一次关闭主窗口时会询问是否最小化到 Windows 系统托盘并保存选择，之后可在“设置”页修改；也可从“关于”页清除整个 `JiYuAttackNextData` 文件夹。

## GitHub Actions Nightly Build

工作流文件为 `.github/workflows/nightly-build.yml`，工作流名称为 `Nightly Build`：

- 推送到 `main` 时自动运行；也可在仓库的 Actions 页面选择该工作流并点击 `Run workflow` 手动运行。手动运行需选择 `main` 分支才会发布。
- 工作流文件首次进入默认分支后，Actions 页面才会显示手动运行入口。
- 在 `windows-latest` 上使用 Python 3.13 安装依赖、执行离线测试并运行 `scripts/build.ps1 -Clean`。
- 构建成功后更新标签为 `nightly`、标题为 `Nightly Build` 的预发布版本，资产包括 GUI 版 `JiYuAttackNext.exe` 和 CLI 版 `JiYuAttackNext-cli.py`。
- 发布说明包含构建时间、工作流运行记录、两个资产的 SHA256，并在末尾的英文 `Message` 章节列出最新提交的完整提交信息。
- 发布复用 `nightly` 标签，并通过 `overwrite_files` 覆盖旧资产和发布说明，因此下载地址保持为 `https://github.com/JasonFang0109c/jiyu_attack_next/releases/tag/nightly`。
- 为避免并发发布，工作流使用 `nightly-build` 并发组；新的运行会取消尚未完成的旧运行。
- 工作流使用 `GITHUB_TOKEN`。仓库需要允许 Actions 写入内容；若发布步骤返回 403，请在 `Settings > Actions > General > Workflow permissions` 中允许读写权限。

## 验证

运行离线测试：

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

生成界面截图：

```powershell
.\.venv\Scripts\python.exe -B -m tests.verify_gui --screenshot build/previews/desktop.png
```

生成的 EXE 默认打开图形界面，无需安装 Python。首次启动可能需要数秒以解压资源；构建前请关闭正在运行的同名程序。项目生成的是未签名 EXE。
