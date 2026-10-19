# 项目结构

根目录只保留仓库首页、依赖清单与 Git 配置。应用实现、独立脚本、测试、构建脚本及详细文档按用途分类。

```text
jiyu_attack_next/
|-- README.md                     # 基础介绍与文档导航
|-- requirements.txt              # GUI 与构建依赖
|-- cli/
|   `-- main.py                    # 独立脚本版，仅使用标准库
|-- app/                          # 图形应用包
|   |-- __init__.py
|   |-- __main__.py                # 应用包入口
|   `-- gui/
|       |-- __init__.py
|       |-- __main__.py            # GUI 与打包入口
|       |-- app.py                 # Fluent 窗口、导航与交互
|       |-- components.py          # 共用目标参数与任务栏
|       |-- models.py              # 连接状态与日志存储
|       |-- pages.py               # 七个功能页面
|       `-- workers.py             # 后台任务
|-- tests/
|   |-- __init__.py
|   |-- test_core.py               # 协议与发送接口测试
|   |-- test_entry.py              # 独立脚本与启动入口测试
|   |-- test_gui.py                # 界面与线程生命周期测试
|   `-- verify_gui.py              # 界面截图检查工具
|-- scripts/
|   |-- build.ps1                  # EXE 构建脚本
|   |-- run_gui.ps1                # 使用虚拟环境启动 GUI
|   `-- JiyuUdpTest.spec           # PyInstaller 配置
|-- docs/
|   |-- CLI.md                    # 独立脚本使用说明
|   |-- GUI.md                    # GUI 使用说明
|   |-- STRUCTURE.md              # 项目结构与模块职责
|   |-- BUILD.md                  # 编译、输出与清理
|   `-- CONTRIBUTING.md           # 开发与中文提交规范
|-- assets/
|   `-- app.svg                    # 图标源文件
`-- output/                       # 本机编译输出，不提交 Git
    `-- JiyuUdpTest.exe
```

## 模块关系

- `cli/main.py` 同时提供独立 CLI 和可复用的报文接口，不依赖 `app/` 或 PySide6。
- `app/gui/app.py` 基于 `FluentWindow` 实现侧边导航、任务调度与页面联动。
- `app/gui/pages.py` 按消息、命令、设备、本机信息、防火墙、日志和设置拆分页面。
- `app/gui/components.py` 提供跨页面同步的连接参数和统一任务栏。
- `app/gui/models.py` 保存连接状态，并提供可筛选的日志记录。
- `app/gui/workers.py` 执行后台发送和本机工具任务，通过信号更新界面。
- `scripts/` 统一存放启动脚本及 EXE 构建配置，自动按脚本位置定位项目根目录。
- `tests/` 使用模拟套接字验证行为，不执行真实目标发送或防火墙变更。

## 本地生成目录

| 路径 | 用途 | 清理方式 |
| --- | --- | --- |
| `.venv/` | Python 虚拟环境 | 保留供开发和构建使用 |
| `build/` | 构建缓存、转换后的图标、测试临时目录与截图 | 验证结束后可删除，按需重新生成 |
| `output/` | 最终 EXE | 保留需要运行或分发的产物 |
| `__pycache__/` | Python 字节码缓存 | 可删除，不影响源码 |

这些生成目录均已通过 `.gitignore` 排除。根目录不保留重复的旧入口文件或遗留截图。

## 相关文档

- [脚本版使用说明](CLI.md)
- [GUI 使用说明](GUI.md)
- [EXE 构建说明](BUILD.md)
- [开发与提交规范](CONTRIBUTING.md)
