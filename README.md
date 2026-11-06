<div align="center">
<h1>JiYu Attack Next</h1>
<img src="assets/app.svg" width="150" height="150" alt="JiYu Attack Next">
<p></p>
<p>
   <a href="https://github.com/JasonFang0109c/jiyu_attack_next"><img alt="GitHub stars" src="https://img.shields.io/github/stars/JasonFang0109c/jiyu_attack_next?label=Stars&style=flat&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCAyNCAyNCc+PHBhdGggZmlsbD0nd2hpdGUnIGQ9J00xMiAxNy4yN0wxOC4xOCAyMWwtMS42NC03LjAzTDIyIDkuMjRsLTcuMTktLjYxTDEyIDIgOS4xOSA4LjYzIDIgOS4yNGw1LjQ2IDQuNzNMNS44MiAyMXonLz48L3N2Zz4="></a>
   <a href="https://github.com/JasonFang0109c/jiyu_attack_next/releases"><img alt="GitHub all releases" src="https://img.shields.io/github/downloads/JasonFang0109c/jiyu_attack_next/total?label=Downloads&style=flat&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCAyNCAyNCc+PHBhdGggZmlsbD0nd2hpdGUnIGQ9J00xOSA5aC00VjNIOXY2SDVsNyA3IDctN3pNNSAxOHYyaDE0di0ySDV6Jy8+PC9zdmc+"></a>
   <a href="https://github.com/JasonFang0109c/jiyu_attack_next/releases/tag/nightly"><img alt="Nightly Build" src="https://img.shields.io/badge/Nightly-Build-blue?style=flat&logo=githubactions&logoColor=white"></a>
   <a href="https://github.com/JasonFang0109c/jiyu_attack_next/issues"><img alt="GitHub issues" src="https://img.shields.io/github/issues/JasonFang0109c/jiyu_attack_next?label=Issues&style=flat&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCAyNCAyNCc+PHBhdGggZmlsbD0nd2hpdGUnIGQ9J00xMiAyYTEwIDEwIDAgMSAwIDAgMjAgMTAgMTAgMCAwIDAgMC0yMHptMSAxNWgtMnYtMmgydjJ6bTAtNGgtMlY3aDJ2NnonLz48L3N2Zz4="></a>
</p>
<p>极域学生端 UDP 控制报文测试工具，图形界面与命令行合并为同一个 Windows EXE</p>
<p>基于 PySide6-Fluent-Widgets 构建，打包后无需安装 Python 即可使用 GUI 与 CLI</p>
<p>仅供已获授权的教学环境测试使用</p>
</div>

---

> [!WARNING]
> 本项目只用于**已获授权的教学环境测试与安全研究**，禁止用于任何未授权的目标，也禁止用于干扰他人正常使用。
>
> - 使用前请确认你已取得目标设备与网络的管理或测试授权。
> - 严禁将本工具用于恶意用途；恶意使用与本项目无关，作者不承担任何责任。
> - 因使用本工具产生的一切后果由使用者自行承担。
>
> 图形界面启动时会弹出同一份声明，点击“同意并继续”后才会进入主界面。

## 功能

<div align="center">
<table width="100%" style="border: none;">
  <tr>
    <td width="33%" valign="middle">
      <h3>💬 消息与命令</h3>
      <ul style="list-style-position: inside; padding-left: 0;">
        <li><b>文本消息</b>：多行编辑与分条发送</li>
        <li><b>远程命令</b>：实时显示缓冲区容量</li>
      </ul>
    </td>
    <td width="33%" valign="middle">
      <h3>🎯 目标与操作</h3>
      <ul style="list-style-position: inside; padding-left: 0;">
        <li><b>设备操作</b>：重启、关机或注销前预览</li>
        <li><b>设备备注</b>：IPv4 映射易读名称</li>
        <li><b>目标地址</b>：IPv4、末段与 <code>/24</code></li>
      </ul>
    </td>
    <td width="33%" valign="middle">
      <h3>📦 文件与工具</h3>
      <ul style="list-style-position: inside; padding-left: 0;">
        <li><b>文件传送</b>：勾选文件树下载到桌面</li>
        <li><b>应用命令</b>：运行程序、打开网址、黑屏锁键鼠</li>
        <li><b>学生信息</b>：宣告发现、缩略图、看屏幕并接管键鼠</li>
        <li><b>本机信息</b>：查询 IP 与 Student 端口</li>
        <li><b>防火墙</b>：修改现有规则并查看结果</li>
      </ul>
    </td>
  </tr>
  <tr>
    <td width="33%" valign="middle">
      <h3>📋 运行日志</h3>
      <ul style="list-style-position: inside; padding-left: 0;">
        <li>按功能、级别与关键词筛选</li>
        <li>勾选导出或删除选中记录</li>
      </ul>
    </td>
    <td width="33%" valign="middle">
      <h3>⚙️ 设置</h3>
      <ul style="list-style-position: inside; padding-left: 0;">
        <li>切换主题、窗口材质与关闭行为</li>
        <li>调整运行日志等级</li>
        <li>确认后清除本地数据</li>
      </ul>
    </td>
    <td width="33%" valign="middle">
      <h3>ℹ️ 关于</h3>
      <ul style="list-style-position: inside; padding-left: 0;">
        <li>作者与仓库信息</li>
        <li>构建时间与组件版本</li>
      </ul>
    </td>
  </tr>
</table>
</div>

目标地址和 UDP 端口在文本消息、文件传送、设备操作与远程命令之间同步。

## 两种操作模式

同一个 `JiYuAttackNext.exe` 同时包含 GUI 与 CLI，启动方式决定进入哪种模式：

| 模式 | 启动方式 | 说明 |
| --- | --- | --- |
| GUI | 双击 EXE；源码 `python -m app` | 无参数启动，先显示使用须知，同意后打开图形界面 |
| CLI | `JiYuAttackNext.exe -ip ...`；源码 `python -m app -ip ...` | 带参数启动，在终端显示输出 |

EXE 无需安装 Python；从源码运行 CLI 仍只依赖标准库。两者共用同一套报文实现，默认通信为 UDP，目标端口 `4705`。EXE 为窗口化程序，双击不会创建控制台窗口，带参数运行时把输出写回启动它的终端、不会另开窗口；由于它不占用控制台，提示符会立即返回——需要等命令执行完再继续时用 `start /wait JiYuAttackNext.exe ...`。PowerShell 中若 EXE 不在 `PATH`，需写成 `.\JiYuAttackNext.exe ...`；cmd 可直接运行。

## 下载

目前只发布 nightly，正式版将在准备就绪后通过 `Release` 工作流手动发布：

| 通道 | 说明 | 下载 |
| --- | --- | --- |
| nightly | 版本号形如 `0.1.0-nightly.20261029`，随 `main` 更新 | [Nightly Build](https://github.com/JasonFang0109c/jiyu_attack_next/releases/tag/nightly) |
| 正式版 | 版本号形如 `v0.1.0`，标记为 Latest；暂无发布 | [最新正式版](https://github.com/JasonFang0109c/jiyu_attack_next/releases/latest) |

- EXE：`JiYuAttackNext.exe`，同一个文件支持 GUI 与 CLI，无需安装 Python
- CLI 不再单独发布脚本；需要从源码调试时使用 `python -m app ...`

推送 `main` 且改动涉及 `app/`、`packaging/`、`scripts/`、`assets/`、依赖清单或工作流文件时，会自动构建并滚动更新 `nightly` 预发布版本；纯文档改动不触发构建。正式版需在 Actions 页面手动运行 `Release`，版本号规则见[版本规范](docs/dev/VERSIONING.md)。

## 文档

### 📖 使用文档

| 文档 | 内容 |
| --- | --- |
| [CLI 模式使用](docs/usage/CLI.md) | 命令行参数、目标地址格式、多行消息、使用示例与排查说明 |
| [GUI 模式使用](docs/usage/GUI.md) | 源码启动、EXE 运行、界面操作与行为说明 |

### 🛠️ 开发文档

| 文档 | 内容 |
| --- | --- |
| [项目结构](docs/dev/STRUCTURE.md) | 目录布局与模块职责 |
| [代码风格](docs/dev/STYLE.md) | ruff 格式化与 lint、Google docstring 与中文注释规范 |
| [EXE 构建](docs/dev/BUILD.md) | 环境准备、编译脚本、输出位置与验证步骤 |
| [版本规范](docs/dev/VERSIONING.md) | 语义化版本号、nightly 与正式版通道、发布流程 |
| [开发与提交规范](docs/dev/CONTRIBUTING.md) | 开发环境、离线测试及中文提交规范 |

## 开发环境

- Python 3.13
- GUI 使用 PySide6，EXE 构建使用 PyInstaller

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app
```

`python -m app` 是无参数统一入口；源码运行 CLI 可用 `python -m app -h`。

构建 EXE：

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build.ps1
```

没有第二台测试设备时，可用本机 IPv4 地址验证报文收发：

```powershell
.\.venv\Scripts\python.exe -B .\scripts\test_local_ip.py
```

脚本会自动选择本机局域网地址，在系统分配的空闲 UDP 端口上依次验证文本消息、远程命令、重启、关机、注销和连续发送，无需安装或运行学生端。`--target 127.0.0.1` 可改用回环地址，`--repeat` 可调整连续发送次数。

## 项目来源与参考

来源仓库：[ht0Ruial/Jiyu_udp_attack](https://github.com/ht0Ruial/Jiyu_udp_attack)，最早的单文件命令行版本由该项目改写而来。

来源仓库：[yunsjxh/Third-party-JiYu-Teacher-Endpoint](https://github.com/yunsjxh/Third-party-JiYu-Teacher-Endpoint)，教师端模拟、学生信息上报、应用命令、缩略图与屏幕观看的报文结构参考了它的实现与说明。该仓库与本项目没有代码依赖关系，也不构成上游分支。

当前仓库的具体行为以本项目代码和文档为准。

## 许可证

本项目使用 [GNU General Public License v3.0](LICENSE)（GPL-3.0-or-later）发布，允许使用、修改与再分发，衍生作品需以同一许可证开源。Copyright (C) 2026 JasonFang0109c。
