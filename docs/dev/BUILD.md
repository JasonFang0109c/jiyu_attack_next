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

以下命令均以项目根目录为工作目录。构建脚本位于 `scripts/`，使用 PyInstaller 生成 Windows 单文件图形程序。

## 准备环境

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

已有虚拟环境时无需重新创建，GUI 和打包依赖的版本以根目录 [requirements.txt](../../requirements.txt) 为准。若虚拟环境早于 Fluent 组件库引入，重新执行一次安装命令即可。

## 源码运行

| 运行方式 | 命令 |
| --- | --- |
| 命令行帮助 | `python cli/main.py -h` |
| 图形界面 | `python -m app.gui` |
| 虚拟环境启动脚本 | `powershell -ExecutionPolicy Bypass -File .\scripts\run_gui.ps1` |

`cli/main.py` 是独立单文件，可直接复制运行，不依赖项目其他文件或第三方库。GUI 实现位于 `app/gui/`，复用脚本版中的标准库接口。

## 构建 EXE

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1 -Clean
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1 -Version 0.4.1
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1 -Python "C:\Python313\python.exe"
```

- 无参数时增量构建，`-Clean` 清理 PyInstaller 缓存后重建，`-Python` 指定其他解释器。
- `-Version` 覆盖版本号；省略时读取 `app/__init__.py` 的 `__version__`。版本号须符合语义化版本格式，规则见[版本规范](VERSIONING.md)。
- 脚本根据自身路径定位项目根目录，也可从其他目录通过绝对路径调用，默认使用项目虚拟环境。
- 读取 [scripts/JiYuAttackNext.spec](../../scripts/JiYuAttackNext.spec)，并收集 Fluent Widgets 的运行时资源与包元数据。
- 每次构建都把当前本地时间打包进 EXE，“关于”页据此显示构建时间；源码运行时显示“源码运行”。
- 版本号同时写入 `build/assets/version.txt`（供“关于”页显示）与 `build/assets/version_info.txt`（PyInstaller 的 Windows 版本资源，EXE 属性中可见）。

## 输出与生成内容

| 路径 | 内容 | 是否保留 |
| --- | --- | --- |
| `output/JiYuAttackNext.exe` | 单文件窗口程序 | 保留用于运行和分发 |
| `build/JiYuAttackNext/` | 打包中间文件与分析结果 | 构建后可删除 |
| `build/assets/app.ico` | 从 SVG 转换的构建图标 | 构建后可删除 |
| `build/assets/build_time.txt` | 本次构建时间，打包进 EXE | 构建后可删除 |
| `build/assets/version.txt` | 本次构建版本号，打包进 EXE | 构建后可删除 |
| `build/assets/version_info.txt` | EXE 版本资源，由 `scripts/gen_version_info.py` 生成 | 构建后可删除 |
| `build/previews/` | 手动生成的界面验证截图 | 检查后可删除 |

删除 `build/` 不影响已生成的 EXE，下次构建会重新生成所需文件。`build/`、`output/` 与 `.venv/` 均由 `.gitignore` 排除，不提交 Git。构建前请关闭正在运行的同名程序。项目生成的是未签名 EXE，首次启动需数秒解压资源；EXE 只允许同时运行一个实例，再次启动会唤醒已有窗口。

## 运行数据

EXE 在其所在目录创建 `JiYuAttackNextData` 子文件夹：`settings.ini` 保存设备备注与关闭窗口行为，`runtime.log` 保存规范文本运行日志。该目录由 `.gitignore` 排除，源码运行时位于项目根目录。

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

`build.yml` 通过 `channel` 输入决定版本号：`stable` 使用源码版本，`nightly` 追加 `-nightly.YYYYMMDD`（UTC 日期）；`version` 输入可显式覆盖。

### Nightly Build

- 推送到 `main` 时按改动路径决定是否运行：只有 `app/`、`cli/`、`scripts/`、`assets/`、`requirements.txt` 或工作流文件本身发生变化才会触发，纯文档与测试改动不会重新编译 EXE。
- 也可在 Actions 页面选择该工作流并点击 `Run workflow` 手动运行，手动运行需选择 `main` 分支才会发布；手动运行不受路径过滤限制。
- 工作流文件首次进入默认分支后，Actions 页面才会显示手动运行入口。
- 在 `windows-latest` 上使用 Python 3.13 安装依赖、执行离线测试并运行 `scripts/build.ps1 -Clean`。
- 构建成功后更新标签为 `nightly`、标题为 `Nightly Build <版本>` 的预发布版本，资产包括 GUI 版 `JiYuAttackNext.exe` 和 CLI 版 `JiYuAttackNext-cli.py`。
- 发布说明包含版本号、构建时间、工作流运行记录、两个资产的 SHA256，并在末尾的英文 `Message` 章节列出最新提交的完整提交信息。
- 复用 `nightly` 标签并通过 `overwrite_files` 覆盖旧资产与说明，下载地址固定为 `https://github.com/JasonFang0109c/jiyu_attack_next/releases/tag/nightly`。
- 使用 `nightly-build` 并发组，新的运行会取消尚未完成的旧运行。

### Release

- 只支持手动触发，不随推送自动运行；不会自动递增版本号，需先修改 `app/__init__.py` 与 `cli/main.py` 的 `__version__` 并提交。
- 发布前校验版本号与源码一致、正式版不带预发布后缀、标签 `vX.Y.Z` 尚不存在，任一不满足即失败。
- 资产为固定名 `JiYuAttackNext.exe`、`JiYuAttackNext-cli.py`，另附带版本号的 `JiYuAttackNext-X.Y.Z.exe`、`JiYuAttackNext-cli-X.Y.Z.py`。
- 发布说明的 `Changes` 章节列出上一个 `v*` 标签以来的提交标题；`make_latest: true` 使正式版成为最新版本，nightly 不受影响。
- 可选择以草稿（`draft`）创建，确认后再在 Releases 页面发布；`overwrite_files: false` 保证不会覆盖已发布资产。
- 使用 `release` 并发组且不取消进行中的运行，避免两次发布互相干扰。

两个发布工作流都使用 `GITHUB_TOKEN`，仓库需允许 Actions 写入内容；发布步骤返回 403 时，在 `Settings > Actions > General > Workflow permissions` 中允许读写权限。

## 验证

改动 `app/`、`cli/`、构建脚本或打包配置后执行；纯文档改动不需要。

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B -m tests.verify_gui --screenshot <截图路径>
```

生成的 EXE 默认打开图形界面，无需安装 Python。
