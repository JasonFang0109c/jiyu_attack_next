# JiYu Attack Next

极域学生端 UDP 控制报文测试工具，提供独立 Python 脚本与基于 PySide6-Fluent-Widgets 的图形界面，支持生成 Windows 单文件 EXE。

## 基础说明

| 项目 | 说明 |
| --- | --- |
| 脚本版 | [cli/main.py](cli/main.py)，单文件、仅依赖 Python 标准库，可独立复制使用 |
| 图形界面 | [app/gui/](app/gui/)，Fluent 侧边导航，按消息、命令、设备操作、设备备注与本机工具分页 |
| 编译输出 | `output/JiYu Attack Next.exe`，无需安装 Python 即可运行 |
| 开发环境 | Python 3.13；GUI 使用 PySide6，EXE 构建使用 PyInstaller |
| 默认通信 | UDP，目标端口 `4705` |

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [脚本版使用](docs/CLI.md) | 参数表、目标地址格式、多行消息、使用示例与排查说明 |
| [GUI 使用](docs/GUI.md) | 源码启动、EXE 运行、界面操作与行为说明 |
| [项目结构](docs/STRUCTURE.md) | 目录布局、模块职责及生成文件的清理 |
| [EXE 构建](docs/BUILD.md) | 环境准备、编译脚本、输出位置与验证步骤 |
| [开发与提交规范](docs/CONTRIBUTING.md) | 开发环境、离线测试及中文提交规范 |

## 项目来源

上游仓库：[ht0Ruial/Jiyu_udp_attack](https://github.com/ht0Ruial/Jiyu_udp_attack)。当前仓库的具体行为以本项目代码和文档为准。

使用前请确认已获得相应网络环境与设备的测试授权。
