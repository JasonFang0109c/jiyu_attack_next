<div align="center">
<h1>CLI 版使用说明</h1>
<p>
   <a href="https://github.com/JasonFang0109c/jiyu_attack_next/releases/tag/nightly"><img alt="Nightly Build" src="https://img.shields.io/badge/Nightly-Build-blue?style=for-the-badge&logo=githubactions&labelColor=212121"></a>
   <img alt="Python 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=212121">
   <img alt="Standard Library" src="https://img.shields.io/badge/依赖-仅标准库-3ddc84?style=for-the-badge&labelColor=212121">
</p>
<p><a href="../../README.md">← 返回项目首页</a> 丨 <a href="GUI.md">GUI 使用说明</a></p>
</div>

---

CLI 版目前从 [Nightly Build](https://github.com/JasonFang0109c/jiyu_attack_next/releases/tag/nightly) 下载 **JiYuAttackNext-cli.py**，正式版发布后也可从 [最新正式版](https://github.com/JasonFang0109c/jiyu_attack_next/releases/latest) 获取。该文件仅依赖 Python 标准库，可以单独保存到任意目录使用，无需安装 GUI 依赖。正式版偏稳定，nightly 随 `main` 更新，两者版本号格式见[版本规范](../dev/VERSIONING.md)。

> **提示**
> 单文件即可运行，不需要克隆仓库，也不需要安装 PySide6。相对文件路径按终端当前工作目录解析。

## 快速开始

三步即可发送第一条消息：

<div align="center">
<table width="100%" style="border: none;">
  <tr>
    <td width="33%" valign="top">
      <h3>📥 获取脚本</h3>
      <p>从 Nightly Build 下载 <code>JiYuAttackNext-cli.py</code>，保存到任意目录。</p>
    </td>
    <td width="33%" valign="top">
      <h3>▶️ 运行命令</h3>
      <p>在脚本所在目录打开 PowerShell，带上目标地址与功能参数。</p>
    </td>
    <td width="33%" valign="top">
      <h3>✅ 查看结果</h3>
      <p>终端输出发送状态；目标端是否执行由学生端决定。</p>
    </td>
  </tr>
</table>
</div>

## 运行环境

使用 Python 3.13。以下示例默认在保存 `JiYuAttackNext-cli.py` 的目录中执行 PowerShell；文件位于其他位置时使用其实际路径。

```powershell
python JiYuAttackNext-cli.py -h
python JiYuAttackNext-cli.py --version
```

`--version` 输出脚本自身的版本号（例如 `0.1.0`），用于确认下载到的版本；版本号规则见[版本规范](../dev/VERSIONING.md)。

通用格式：

```text
python JiYuAttackNext-cli.py -ip <目标地址> [-p <目标端口>] <功能参数>
```

发送报文需要指定 `-ip`，默认 UDP 端口为 `4705`；本机功能 `-e g`、`-e break`、`-e continue` 不需要目标地址。GUI 的启动与操作见 [GUI 使用说明](GUI.md)。

## 参数参考

### 通用参数

| 参数 | 类型 | 默认值 | 用途与说明 |
| --- | --- | --- | --- |
| `-h` / `--help` | 开关 | 无 | 显示帮助并退出 |
| `-V` / `--version` | 开关 | 无 | 显示版本号并退出 |
| `-ip` | 字符串 | 无 | 目标地址，支持单个 IPv4、同网段末段范围及 `/24` |
| `-p` | 整数 | `4705` | 目标 UDP 端口 |
| `-msg` | 字符串 | 无 | 发送文本消息，保留多行内容；超长文本自动分条 |
| `--msg-file` | 路径 | 无 | 从 UTF-8 文件读取消息；`-` 表示标准输入；与 `-msg` 互斥 |
| `--file` | 路径 | 无 | 传送本地文件到目标电脑桌面；与 `-msg`、`--msg-file`、`-c` 和 `-e` 互斥 |
| `--file-ip` | IPv4 | 自动检测 | 文件传送时写入命令的本机 IPv4；多网卡或自动检测异常时手动指定 |
| `--file-timeout` | 秒 | `120` | 等待每个目标下载文件的秒数，须大于 0 |
| `-c` | 字符串 | 无 | 发送待执行的命令 |
| `-l` | 整数 | `1` | 发送轮数；每轮遍历全部目标与报文 |
| `-t` | 整数 | `22` | 轮次之间的等待秒数，仅多轮发送时生效 |
| `-e` | 枚举 | 无 | 扩展功能，取值见下表 |

### 扩展功能

| 参数组合 | 功能 | 执行范围 | 条件与说明 |
| --- | --- | --- | --- |
| `-e r` | 发送重启指令 | 目标设备 | 需要指定 `-ip` |
| `-e s` | 发送关机指令 | 目标设备 | 需要指定 `-ip` |
| `-e g` | 查询本机 IP 与学生端可能的监听端口 | 本机 | 尝试匹配 `Student` 相关进程及端口；不需要 `-ip` |
| `-e nc` | 反向 Shell 连接 | 本机与目标设备 | 需要 `-ip`；依赖外部 PowerShell 脚本下载与回连连通性 |
| `--file PATH` | 文件传送到目标桌面 | 本机与目标设备 | 需要 `-ip`；按目标逐个启动本机 HTTP 文件服务并发送 cmd/curl 下载命令，等待下载完成 |
| `-e break` | 尝试阻断学生端网络连接 | 本机 | 修改 Windows 防火墙设置及名为 `StudentMain.exe` 的现有规则，需要管理员权限 |
| `-e continue` | 将学生端防火墙规则改为允许 | 本机 | 修改名为 `StudentMain.exe` 的现有规则，需要管理员权限；不还原全部防火墙设置 |

## 目标地址格式

| 格式 | 参数示例 | 目标范围 |
| --- | --- | --- |
| 单个地址 | `-ip 10.49.151.29` | 仅 `10.49.151.29` |
| 同网段范围 | `-ip 10.49.151.1-10` | `10.49.151.1` 至 `10.49.151.10`，含两端 |
| `/24` 网段 | `-ip 10.49.151.0/24` | `10.49.151.1` 至 `10.49.151.254` |

范围写法右侧仅填写末段数字；仅支持 `/24` 网段，不支持任意 CIDR 前缀。地址会经过 IPv4 格式校验，范围或网段无效时直接提示错误。

## 使用示例

示例中的 `10.49.151.29` 为占位目标地址，运行前请按实际测试环境替换。

### 发送文本消息

```powershell
python JiYuAttackNext-cli.py -ip 10.49.151.29 -msg "Hello"
```

### 发送多行文本

使用 PowerShell 的 Here-String 可保留换行、空行与缩进：

```powershell
$message = @'
第一行通知
第二行通知

第四行通知
'@
python JiYuAttackNext-cli.py -ip 10.49.151.29 -msg $message
```

CLI 版保留传入字符串中的真实换行，不会把字面量 `\n` 转成换行；目标端是否按多行显示取决于学生端消息窗口的实现。

### 从文件读取长文本

文本保存为 UTF-8 文件，可包含多行内容、空行及中文，也支持带 BOM 的 UTF-8。

```powershell
python JiYuAttackNext-cli.py -ip 10.49.151.29 --msg-file "notice.txt"
```

`--msg-file -` 从标准输入读取文本，适合较长内容并避免将全文放入命令行参数；`--msg-file` 与 `-msg` 不可同时使用。

### 消息容量与分条行为

单条报文为 954 字节，正文从偏移 56 开始，每条为字符串结束符预留 2 字节，正文最多 **896 字节，即 448 个 UTF-16 单元**。普通中文、英文字母通常占 1 个单元，部分字符占 2 个单元，换行符也计入容量。这是发送缓冲区的容量，并非已验证的学生端显示上限。

总文本不设固定长度上限，超出单条容量时自动拆成多条独立消息，保留文本内容及换行，不拆开单个 Unicode 码点。总长度受可用内存及输入方式限制，文本不支持内嵌 NUL 字符。

**分条不等于接收端合并。** CLI 版按顺序发送各条报文，但不提供接收端重组、回执或重传机制，不能保证长文本在目标端完整、有序地显示为同一条消息。

### 指定目标端口

```powershell
python JiYuAttackNext-cli.py -ip 10.49.151.29 -p 4705 -msg "Test message"
```

### 发送查询命令

```powershell
python JiYuAttackNext-cli.py -ip 10.49.151.29 -c "cmd.exe /c ipconfig"
```

### 使用包含空格的路径

在 PowerShell 中，用外层单引号包裹整个命令，并用内层双引号包裹路径：

```powershell
python JiYuAttackNext-cli.py -ip 10.49.151.29 -c 'cmd.exe /c dir "C:\Program Files"'
```

### 传送文件到桌面

以下命令选择本机文件，并通过目标学生端的远程命令能力触发系统自带的 `curl` 下载：

```powershell
python JiYuAttackNext-cli.py -ip 10.49.151.1-10 --file "D:\资料\实验报告.pdf" --file-timeout 180
```

CLI 版按目标逐个启动本机 HTTP 文件服务，向目标发送随机令牌的下载命令，目标使用当前登录用户桌面保存同名文件。下载完成后写入正式文件，中断则清理 `.part` 临时文件。UDP 命令未得到目标响应时最多重发 3 次，避免单次丢包造成任务无响应。

- 目标电脑不需要开放入站端口，只需允许执行远程命令、提供 Windows 自带的 `curl.exe`，并允许其主动访问发送端的自动检测 IP 与随机 TCP 端口。
- 发送端 Windows 防火墙需允许 Python、EXE 或临时 HTTP 服务监听；GUI 首次使用时按系统提示允许。
- 目标只保存文件，不会自动打开、通知或回传执行结果。
- 自动检测会忽略 `198.18.0.0/15` 等虚拟或基准测试网段，并在出口地址不可用时选择与目标网段更接近的真实局域网地址。TUN/VPN 或多网卡环境仍检测错误时，使用 `--file-ip 10.49.151.20` 手动指定发送端 IP。
- 多个目标按顺序逐个传送，每个目标单独等待下载，某个目标失败后继续尝试其余目标并汇总失败目标；`--file-timeout` 按单个目标计算。
- 每个目标的文件服务只在该目标等待下载期间运行，超时或任务取消后停止。失败信息会区分“目标未访问文件服务”“目标已取脚本但未下载”和“下载中断”。

### 查询本机信息

```powershell
python JiYuAttackNext-cli.py -e g
```

仅查询运行 CLI 版的本机，不查询远程目标；未匹配到学生端进程或端口时输出可能不完整。

### 控制发送轮数与间隔

以下命令发送 3 轮消息，相邻两轮之间等待 10 秒，最后一轮结束后不再等待：

```powershell
python JiYuAttackNext-cli.py -ip 10.49.151.29 -msg "Test message" -l 3 -t 10
```

### 组合发送消息与命令

```powershell
python JiYuAttackNext-cli.py -ip 10.49.151.29 -msg "Test" -c "cmd.exe /c ipconfig"
```

每轮按消息、命令、重启或关机报文的顺序发送；实际是否执行及执行顺序由目标端决定。

### 发送重启或关机指令

```powershell
# 重启目标
python JiYuAttackNext-cli.py -ip 10.49.151.29 -e r

# 关闭目标
python JiYuAttackNext-cli.py -ip 10.49.151.29 -e s
```

## 行为与限制

- **发送结果**：CLI 版不接收目标执行回执。“发送成功”仅表示本机发送调用未报错，不能据此确认目标已收到报文或完成操作。
- **循环参数**：`-l` 使用正整数，`-t` 使用非负整数。等待发生在两轮之间，不在每台设备之间。
- **功能组合**：`-msg`、`-c` 可与 `-e r` 或 `-e s` 组合。本地功能 `g`、`break`、`continue` 执行后退出；`nc` 使用独立分支，不处理同时传入的 `-msg` 或 `-c`。
- **文本编码**：消息与命令按 `utf-16le` 编码。消息超长时自动分条，命令仍受固定报文缓冲区限制；路径和引号需符合目标命令解释器的规则。
- **输出范围**：使用 `-c` 不会自动将目标命令的标准输出返回到当前终端。

## 问题排查

| 现象 | 可能原因 | 检查建议 |
| --- | --- | --- |
| 提示找不到 CLI 文件 | 终端不在文件所在目录，或仍使用旧文件名 | 检查当前目录及文件名，统一使用 `python JiYuAttackNext-cli.py ...` |
| 提示“发送成功”，目标无响应 | 地址或端口不匹配、报文被拦截、学生端未监听、目标未执行指令 | 核对目标地址、UDP 端口、学生端状态及目标端执行结果 |
| 包含空格的路径处理失败 | 路径未完整加引号，或引号在终端传参时发生变化 | 参考包含空格路径的示例，并核对目标端路径 |
| `-e g` 未显示端口 | 未找到 `Student` 相关进程或其 UDP 监听端口 | 在本机核对进程与监听状态；查询失败时会显示错误原因 |
| 只有 IP、没有功能参数时无法发送 | 没有生成任何待发送报文 | 指定 `-msg`、`-c` 或相应扩展功能 |
| 长命令报错 | 命令超过固定报文缓冲区容量 | 缩短命令，检查终端输出的异常信息 |
| 长消息只显示部分内容或顺序不一致 | 消息被拆成独立报文，未提供接收端重组与可靠交付机制 | 核对目标端实际显示结果；分条发送不能保证合并为单条消息 |
| `--msg-file` 无法读取 | 文件不存在或文件编码不是 UTF-8 | 核对路径，将文件保存为 UTF-8 编码 |
