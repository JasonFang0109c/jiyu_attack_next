<div align="center">
<h1>JiYu Attack Next</h1>
<img src="assets/app.svg" width="150" height="150" alt="JiYu Attack Next">
<p></p>
<p>
   <a href="https://github.com/JasonFang0109c/jiyu_attack_next/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/JasonFang0109c/jiyu_attack_next"></a>
   <a href="https://github.com/JasonFang0109c/jiyu_attack_next/releases"><img alt="GitHub all releases" src="https://img.shields.io/github/downloads/JasonFang0109c/jiyu_attack_next/total?label=Downloads"></a>
   <a href="https://github.com/JasonFang0109c/jiyu_attack_next/releases/tag/nightly"><img alt="Nightly Build" src="https://img.shields.io/badge/Nightly-Build-blue.svg?logo=githubactions"></a>
   <a href="https://github.com/JasonFang0109c/jiyu_attack_next/issues"><img alt="GitHub issues" src="https://img.shields.io/github/issues/JasonFang0109c/jiyu_attack_next"></a>
</p>
<p>极域学生端 UDP 控制报文测试工具，提供图形界面与独立脚本两种形态</p>
<p>基于 PySide6-Fluent-Widgets 构建，支持打包为 Windows 单文件 EXE</p>
<p>仅供已获授权的教学环境测试使用</p>
</div>

---

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
        <li><b>设备操作</b>：重启或关机前预览</li>
        <li><b>设备备注</b>：IPv4 映射易读名称</li>
        <li><b>目标地址</b>：IPv4、末段与 <code>/24</code></li>
      </ul>
    </td>
    <td width="33%" valign="middle">
      <h3>📦 文件与工具</h3>
      <ul style="list-style-position: inside; padding-left: 0;">
        <li><b>文件传送</b>：勾选文件树下载到桌面</li>
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
        <li>切换主题与关闭行为</li>
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

目标地址和 UDP 端口在文本消息、远程命令、设备操作与文件传送之间同步。

## 两种形态

| | 图形界面 | 脚本版 |
| --- | --- | --- |
| 入口 | `python -m app.gui` | `JiYuAttackNext-cli.py` |
| 依赖 | PySide6 与 PySide6-Fluent-Widgets | 仅 Python 标准库 |
| 分发 | Windows 单文件 EXE | 单文件脚本，可独立保存 |

两者共用同一套报文实现，默认通信为 UDP，目标端口 `4705`。

## 下载

目前只发布 nightly，正式版将在准备就绪后通过 `Release` 工作流手动发布：

| 通道 | 说明 | 下载 |
| --- | --- | --- |
| nightly | 版本号形如 `0.1.0-nightly.20261029`，随 `main` 更新 | [Nightly Build](https://github.com/JasonFang0109c/jiyu_attack_next/releases/tag/nightly) |
| 正式版 | 版本号形如 `v0.1.0`，标记为 Latest；暂无发布 | [最新正式版](https://github.com/JasonFang0109c/jiyu_attack_next/releases/latest) |

- EXE：`JiYuAttackNext.exe`，无需安装 Python 即可运行
- 脚本：`JiYuAttackNext-cli.py`，仅依赖 Python 3.13 标准库

推送到 `main` 且改动涉及 `app/`、`cli/`、`scripts/`、`assets/`、依赖清单或工作流文件时，会自动构建并滚动更新 `nightly` 预发布版本；纯文档改动不触发构建。正式版需在 Actions 页面手动运行 `Release`，版本号规则见[版本规范](docs/dev/VERSIONING.md)。

## 文档

### 📖 使用文档

| 文档 | 内容 |
| --- | --- |
| [CLI 版使用](docs/usage/CLI.md) | 参数表、目标地址格式、多行消息、使用示例与排查说明 |
| [GUI 使用](docs/usage/GUI.md) | 源码启动、EXE 运行、界面操作与行为说明 |

### 🛠️ 开发文档

| 文档 | 内容 |
| --- | --- |
| [项目结构](docs/dev/STRUCTURE.md) | 目录布局与模块职责 |
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
