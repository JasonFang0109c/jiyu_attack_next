<div align="center">
<h1>JiYu Attack Next</h1>
<img src="assets/app.svg" width="150" height="150" alt="JiYu Attack Next">
<p></p>
<p>
   <a href="https://github.com/JasonFang0109c/jiyu_attack_next/releases"><img alt="GitHub all releases" src="https://img.shields.io/github/downloads/JasonFang0109c/jiyu_attack_next/total?label=Downloads"></a>
   <a href="https://github.com/JasonFang0109c/jiyu_attack_next/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/JasonFang0109c/jiyu_attack_next"></a>
   <a href="https://github.com/JasonFang0109c/jiyu_attack_next/issues"><img alt="GitHub issues" src="https://img.shields.io/github/issues/JasonFang0109c/jiyu_attack_next"></a>
   <a href="https://github.com/JasonFang0109c/jiyu_attack_next/releases/tag/nightly"><img alt="Nightly Build" src="https://img.shields.io/badge/Nightly-Build-blue.svg?logo=githubactions"></a>
</p>
<p>极域学生端 UDP 控制报文测试工具，提供图形界面与独立脚本两种形态</p>
<p>基于 PySide6-Fluent-Widgets 构建，支持打包为 Windows 单文件 EXE</p>
<p>仅供已获授权的教学环境测试使用</p>
</div>

---

## 功能

- **文本消息**：编辑、导入和保存多行消息，超长文本自动分条发送
- **远程命令**：发送单条命令，实时显示报文缓冲区容量
- **设备操作**：重启或关机，发送前预览解析后的目标设备
- **文件传送**：勾选文件或文件夹树，通过目标端下载到当前用户桌面
- **设备备注**：为 IPv4 地址映射易读名称，可直接设为当前目标
- **本机信息**：查询本机 IP 与 Student 相关监听端口
- **防火墙**：修改 `StudentMain.exe` 的现有规则并查看逐项结果
- **运行日志**：按功能、级别和关键词筛选，勾选导出或删除
- **设置与关于**：主题、关闭行为、运行日志等级与构建信息

目标地址支持单个 IPv4、末段范围（如 `1-10`）与 `/24` 网段；目标地址和端口在各远程页面之间同步。

## 两种形态

| | 图形界面 | 脚本版 |
| --- | --- | --- |
| 入口 | `python -m app.gui` | `JiYuAttackNext-cli.py` |
| 依赖 | PySide6 与 PySide6-Fluent-Widgets | 仅 Python 标准库 |
| 分发 | Windows 单文件 EXE | 单文件脚本，可独立保存 |

两者共用同一套报文实现，默认通信为 UDP，目标端口 `4705`。

## 下载

图形界面与脚本版均通过 Nightly Build 发布：

- EXE：前往 [Nightly Build](https://github.com/JasonFang0109c/jiyu_attack_next/releases/tag/nightly) 下载 `JiYuAttackNext.exe`
- 脚本：下载 [JiYuAttackNext-cli.py](https://github.com/JasonFang0109c/jiyu_attack_next/releases/download/nightly/JiYuAttackNext-cli.py)

推送到 `main` 后会自动构建并更新 `nightly` 预发布版本。EXE 无需安装 Python 即可运行。

## 文档

| 文档 | 内容 |
| --- | --- |
| [CLI 版使用](docs/CLI.md) | 参数表、目标地址格式、多行消息、使用示例与排查说明 |
| [GUI 使用](docs/GUI.md) | 源码启动、EXE 运行、界面操作与行为说明 |
| [项目结构](docs/STRUCTURE.md) | 目录布局与模块职责 |
| [EXE 构建](docs/BUILD.md) | 环境准备、编译脚本、输出位置与验证步骤 |
| [开发与提交规范](docs/CONTRIBUTING.md) | 开发环境、离线测试及中文提交规范 |

## 开发环境

- Python 3.13
- GUI 使用 PySide6，EXE 构建使用 PyInstaller

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app.gui
```

构建 EXE：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1
```

## 项目来源

上游仓库：[ht0Ruial/Jiyu_udp_attack](https://github.com/ht0Ruial/Jiyu_udp_attack)。当前仓库的具体行为以本项目代码和文档为准。

## 免责声明

- 本工具仅用于已获授权的网络环境与设备测试，不得用于未授权的目标。
- 使用前请确认你拥有相应设备与网络的管理或测试权限。
- 因使用本工具产生的一切后果由使用者自行承担。
