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
| `output/JiYu Attack Next.exe` | 单文件窗口程序 | 保留用于运行和分发 |
| `build/JiYu Attack Next/` | 打包中间文件与分析结果 | 构建后可删除 |
| `build/assets/app.ico` | 从 SVG 转换的构建图标 | 构建后可删除 |
| `build/previews/` | 手动生成的界面验证截图 | 检查后可删除 |
| `assets/app.svg` | 图标源文件 | 随源码保留 |

删除 `build/` 不影响已生成的 EXE，下次构建会重新生成所需文件。`build/`、`output/` 和 `.venv/` 均不提交到 Git。

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
