<div align="center">

# JiYu Attack Next

<img src="assets/app.svg" width="160" height="160" style="display: block; margin: 0 auto;" alt="JiYu Attack Next 图标">

**简体中文**

<div>
  <a href="https://github.com/JasonFang0109c/jiyu_attack_next/stargazers">
    <img alt="Stars" src="https://img.shields.io/github/stars/JasonFang0109c/jiyu_attack_next?style=for-the-badge&logo=github">
  </a>
  <a href="https://github.com/JasonFang0109c/jiyu_attack_next/releases">
    <img alt="GitHub Downloads" src="https://img.shields.io/github/downloads/JasonFang0109c/jiyu_attack_next/total?style=for-the-badge&logo=github&label=GitHub">
  </a>
  <a href="https://github.com/JasonFang0109c/jiyu_attack_next/releases/tag/nightly">
    <img alt="Nightly" src="https://img.shields.io/badge/Nightly-Build-blue?style=for-the-badge&logo=githubactions&logoColor=white">
  </a>
</div>

<p></p>

极域学生端 UDP 控制报文测试工具，提供独立 Python 脚本与基于 PySide6-Fluent-Widgets 的图形界面，支持生成 Windows 单文件 EXE。

</div>

<table align="center" width="100%" style="border: none;">
  <tr>
    <td width="50%" valign="top">
      <h3>🖥️ 图形界面</h3>
      <ul>
        <li>Fluent 侧边导航，按功能分页</li>
        <li>消息、命令、设备操作与文件传送</li>
        <li>设备备注、运行日志与本机工具</li>
      </ul>
    </td>
    <td width="50%" valign="top">
      <h3>⌨️ 脚本版</h3>
      <ul>
        <li>单文件，仅依赖 Python 标准库</li>
        <li>可独立保存到任意目录运行</li>
        <li>支持范围地址与多轮发送</li>
      </ul>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <h3>📥 下载</h3>
      <ol>
        <li><b>图形界面</b>: 从 <a href="https://github.com/JasonFang0109c/jiyu_attack_next/releases/tag/nightly">Nightly Build</a> 下载 <code>JiYuAttackNext.exe</code></li>
        <li><b>脚本版</b>: 下载 <a href="https://github.com/JasonFang0109c/jiyu_attack_next/releases/download/nightly/JiYuAttackNext-cli.py">JiYuAttackNext-cli.py</a></li>
      </ol>
    </td>
    <td width="50%" valign="top">
      <h3>⚙️ 环境</h3>
      <ul>
        <li>开发环境: Python 3.13</li>
        <li>GUI: PySide6 与 PySide6-Fluent-Widgets</li>
        <li>打包: PyInstaller</li>
        <li>默认通信: UDP，目标端口 <code>4705</code></li>
      </ul>
    </td>
  </tr>
</table>

## 基础说明

| 项目 | 说明 |
| --- | --- |
| CLI 版 | [**JiYuAttackNext-cli.py**](https://github.com/JasonFang0109c/jiyu_attack_next/releases/download/nightly/JiYuAttackNext-cli.py)，单文件、仅依赖 Python 标准库，可独立保存使用 |
| 图形界面 | [app/gui/](app/gui/)，Fluent 侧边导航，按消息、命令、设备操作、文件传送、设备备注与本机工具分页 |
| 编译输出 | `output/JiYuAttackNext.exe`，无需安装 Python 即可运行，不纳入 Git |
| 开发环境 | Python 3.13；GUI 使用 PySide6，EXE 构建使用 PyInstaller |
| 默认通信 | UDP，目标端口 `4705` |
| Nightly Build | 推送到 `main` 后自动构建 Windows EXE 和 CLI Python 脚本，并更新 `nightly` 预发布版本 |

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [CLI 版使用](docs/CLI.md) | 参数表、目标地址格式、多行消息、使用示例与排查说明 |
| [GUI 使用](docs/GUI.md) | 源码启动、EXE 运行、界面操作与行为说明 |
| [项目结构](docs/STRUCTURE.md) | 目录布局与模块职责 |
| [EXE 构建](docs/BUILD.md) | 环境准备、编译脚本、输出位置与验证步骤 |
| [开发与提交规范](docs/CONTRIBUTING.md) | 开发环境、离线测试及中文提交规范 |

## 项目来源

上游仓库：[ht0Ruial/Jiyu_udp_attack](https://github.com/ht0Ruial/Jiyu_udp_attack)。当前仓库的具体行为以本项目代码和文档为准。

使用前请确认已获得相应网络环境与设备的测试授权。

<div align="center">

<a href="https://star-history.com/#JasonFang0109c/jiyu_attack_next&Date">
  <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=JasonFang0109c/jiyu_attack_next&type=Date">
</a>

</div>
