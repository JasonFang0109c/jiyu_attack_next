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

## 运行环境

Windows 10/11。EXE 已包含 Python 运行时，命令行模式无需安装 Python 或 PySide6；只有从源码运行 CLI 时才需要 Python 3.13，在项目根目录执行 `python -m app ...` 即可。

以下示例默认在保存 `JiYuAttackNext.exe` 的目录中执行 PowerShell。PowerShell 需要 `.\` 前缀；命令提示符（cmd）可直接写 `JiYuAttackNext.exe`。

```powershell
.\JiYuAttackNext.exe -h
.\JiYuAttackNext.exe --version
```

`--version` 输出程序版本号（例如 `0.1.0`），用于确认下载到的版本；版本号规则见[版本规范](../dev/VERSIONING.md)。

通用格式：

```text
JiYuAttackNext.exe -ip <目标地址> [-p <目标端口>] <功能参数>
```

发送报文需要指定 `-ip`，默认 UDP 端口为 `4705`；本机功能 `-e g`、`-e break`、`-e continue` 不需要目标地址。无参数启动会打开 GUI，带 `-h`、`--version` 或其他参数时运行 CLI；GUI 的启动与操作见 [GUI 模式使用说明](GUI.md)。

在命令提示符（cmd）中可直接运行：

```bat
JiYuAttackNext.exe -ip 10.49.151.29 -msg "Hello"
```

EXE 是窗口化程序，双击无参数启动只打开 GUI，不会创建控制台窗口。从终端带参数启动时，程序把输出写回当前终端，不会另开控制台窗口；由于它不占用控制台，提示符会立即返回，需要等命令执行完再继续时用 `start /wait`：

```bat
start /wait JiYuAttackNext.exe -ip 10.49.151.29 -msg "Hello"
```

重定向输出（`> 结果.txt`）与管道仍然有效。

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
| `--file` | 路径 | 无 | 传送一个或多个文件、文件夹到目标电脑桌面，文件夹按原结构递归；与 `-msg`、`--msg-file`、`-c` 和 `-e` 互斥 |
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
| `-e l` | 注销当前登录用户 | 目标设备 | 需要指定 `-ip`；通过远程命令通道执行 `shutdown /l`，依赖目标允许执行远程命令 |
| `-e g` | 查询本机 IP 与学生端可能的监听端口 | 本机 | 尝试匹配 `Student` 相关进程及端口；不需要 `-ip` |
| `--file PATH [PATH ...]` | 文件与文件夹传送到目标桌面 | 本机与目标设备 | 需要 `-ip`；可以一次给多个路径，文件夹按原结构递归展开；按目标逐个启动本机 HTTP 文件服务并发送 cmd/curl 下载命令，等待下载完成 |
| `-e break` | 尝试阻断学生端网络连接 | 本机 | 修改 Windows 防火墙设置及名为 `StudentMain.exe` 的现有规则，需要管理员权限；未提升时按需弹出 UAC |
| `-e continue` | 将学生端防火墙规则改为允许 | 本机 | 修改名为 `StudentMain.exe` 的现有规则，需要管理员权限；未提升时按需弹出 UAC；不还原全部防火墙设置 |

`-e break` 和 `-e continue` 会修改本机防火墙。EXE 默认以普通用户权限启动，普通命令直接在当前终端执行；只有这两项操作在未提升时会弹出 UAC，由隐藏的管理员助手完成修改后返回结果，不会另开一个显示输出的终端窗口。

### 应用命令与教师端模拟

这些参数彼此互斥，也不能与 `-msg`、`--msg-file`、`-c`、`--file`、`-e` 同时使用；`-ip` 展开后的每个地址都会收到同一条命令。

| 参数 | 类型 | 默认值 | 用途与说明 |
| --- | --- | --- | --- |
| `--run PATH` | 路径 | 无 | 在目标电脑上运行指定程序（应用命令 cmdId `0x0F`） |
| `--run-args TEXT` | 字符串 | 空 | `--run` 的启动参数 |
| `--run-show MODE` | `0`/`1`/`2` | `0` | `--run` 的窗口状态：正常、最小化、最大化 |
| `--url URL` | 字符串 | 无 | 在目标电脑上打开网址（cmdId `0x18`）；缺协议时按 `http://` 补全 |
| `--kill PID` | 整数 | 无 | 结束目标电脑上的指定进程，走 MESS 上报请求的进程号模式 |
| `--blackscreen [SECONDS]` | 整数 | `10` | 让目标黑屏并按秒数自动解除；黑屏走会话频道组播 |
| `--no-lock` | 开关 | 关 | `--blackscreen` 只黑屏，不锁定键盘与鼠标 |
| `--blackout-text TEXT` | 字符串 | 空 | 黑屏期间显示的提示文字 |
| `--unlock` | 开关 | 无 | 解除黑屏与键鼠锁，走会话频道组播 |
| `--exit-student` | 开关 | 无 | 让目标电脑退出学生端（cmdId `0x15`） |
| `--close-apps` | 开关 | 无 | 关闭目标电脑上的所有程序（cmdId `0x02`） |
| `--channel N` | 整数 | `1` | 会话频道号，取值 1–32；黑屏、解锁与宣告都按该频道寻址 |
| `--teacher-name NAME` | 字符串 | `1` | 宣告里携带的教师名，也是学生端屏幕上显示的名称 |
| `--announce [SECONDS]` | 整数 | `10` | 以教师端模拟身份发送在线宣告并监听登录，超时后打印发现的路由信息 |
| `--students [SECONDS]` | 整数 | `8` | 发现学生机后拉取并打印其系统信息、进程与窗口 |

`--blackscreen` 与 `--unlock` 必须让 `--channel` 与学生端所在频道一致：这两条报文只在会话组播上被处理，单播不生效。锁键鼠的解除不能靠再发一次黑屏并把锁参数去掉，学生端只把 `lock_input=1` 当作上锁。

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
.\JiYuAttackNext.exe -ip 10.49.151.29 -msg "Hello"
```

### 发送多行文本

使用 PowerShell 的 Here-String 可保留换行、空行与缩进：

```powershell
$message = @'
第一行通知
第二行通知

第四行通知
'@
.\JiYuAttackNext.exe -ip 10.49.151.29 -msg $message
```

CLI 模式保留传入字符串中的真实换行，不会把字面量 `\n` 转成换行；目标端是否按多行显示取决于学生端消息窗口的实现。

### 从文件读取长文本

文本保存为 UTF-8 文件，可包含多行内容、空行及中文，也支持带 BOM 的 UTF-8。

```powershell
.\JiYuAttackNext.exe -ip 10.49.151.29 --msg-file "notice.txt"
```

`--msg-file -` 从标准输入读取文本，适合较长内容并避免将全文放入命令行参数；`--msg-file` 与 `-msg` 不可同时使用。

### 消息容量与分条行为

单条报文为 954 字节，正文从偏移 56 开始，每条为字符串结束符预留 2 字节，正文最多 **896 字节，即 448 个 UTF-16 单元**。普通中文、英文字母通常占 1 个单元，部分字符占 2 个单元，换行符也计入容量。这是发送缓冲区的容量，并非已验证的学生端显示上限。

总文本不设固定长度上限，超出单条容量时自动拆成多条独立消息，保留文本内容及换行，不拆开单个 Unicode 码点。总长度受可用内存及输入方式限制，文本不支持内嵌 NUL 字符。

**分条不等于接收端合并。** CLI 模式按顺序发送各条报文，但不提供接收端重组、回执或重传机制，不能保证长文本在目标端完整、有序地显示为同一条消息。

发送结束后会逐个目标打印结果：`[成功] 192.168.1.10：已送达（1 个报文）` 或 `[-] [失败] 192.168.1.10：失败：目标端口未响应`，最后一行汇总成功与失败数量。判定依据只有网络反馈：目标端口或主机返回 ICMP 不可达时判为“失败：目标端口未响应”或“失败：目标不可达”；没有收到错误时再主动发一次 ICMP 回显，主机有回应、或同网段能通过 ARP 解析到它时判为“已送达”，两者都没有则判为“失败：目标未响应”。因此“成功”只表示报文没有被网络拒绝、对方在线，仍不能证明学生端已经执行。

### 指定目标端口

```powershell
.\JiYuAttackNext.exe -ip 10.49.151.29 -p 4705 -msg "Test message"
```

### 发送查询命令

```powershell
.\JiYuAttackNext.exe -ip 10.49.151.29 -c "cmd.exe /c ipconfig"
```

### 使用包含空格的路径

在 PowerShell 中，用外层单引号包裹整个命令，并用内层双引号包裹路径：

```powershell
.\JiYuAttackNext.exe -ip 10.49.151.29 -c 'cmd.exe /c dir "C:\Program Files"'
```

### 传送文件到桌面

以下命令选择本机文件，并通过目标学生端的远程命令能力触发系统自带的 `curl` 下载：

```powershell
.\JiYuAttackNext.exe -ip 10.49.151.1-10 --file "D:\资料\实验报告.pdf" --file-timeout 180
```

CLI 模式按目标逐个启动本机 HTTP 文件服务，向目标发送随机令牌的下载命令，目标使用当前登录用户桌面保存同名文件。下载完成后写入正式文件，中断则清理 `.part` 临时文件。UDP 命令未得到目标响应时最多重发 3 次，避免单次丢包造成任务无响应。

`--file` 可以一次给多个路径，文件与文件夹可以混用：

```powershell
.\JiYuAttackNext.exe -ip 10.49.151.29 --file "D:\资料\实验报告.pdf" "D:\课件" "readme.txt"
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
.\JiYuAttackNext.exe -e g
```

仅查询运行 CLI 模式的本机，不查询远程目标；未匹配到学生端进程或端口时输出可能不完整。

### 用本机 IP 测试

没有第二台测试设备时，可以把 `-ip` 指向运行程序的本机 IPv4 地址，例如 `-ip 192.168.1.20`。CLI 会照常发送 UDP 报文；本机没有学生端监听对应端口时不会产生可见效果。

```powershell
.\JiYuAttackNext.exe -ip 192.168.1.20 -msg "本机测试"
```

仓库提供的 `scripts/test_local_ip.py` 会自动选择本机地址，在空闲 UDP 端口上接收并校验消息、命令、重启、关机、注销和连续发送报文，适合验证协议与发送流程；运行方式见[开发与提交规范](../dev/CONTRIBUTING.md#本机-ip-自测)。

### 控制发送轮数与间隔

以下命令发送 3 轮消息，相邻两轮之间等待 10 秒，最后一轮结束后不再等待：

```powershell
.\JiYuAttackNext.exe -ip 10.49.151.29 -msg "Test message" -l 3 -t 10
```

### 组合发送消息与命令

```powershell
.\JiYuAttackNext.exe -ip 10.49.151.29 -msg "Test" -c "cmd.exe /c ipconfig"
```

每轮按消息、命令、重启、关机或注销报文的顺序发送；实际是否执行及执行顺序由目标端决定。

### 发送重启、关机或注销指令

```powershell
# 重启目标
.\JiYuAttackNext.exe -ip 10.49.151.29 -e r

# 关闭目标
.\JiYuAttackNext.exe -ip 10.49.151.29 -e s

# 注销目标当前登录用户
.\JiYuAttackNext.exe -ip 10.49.151.29 -e l
```

注销没有独立的极域报文，CLI 模式会通过 `-c` 相同的远程命令通道发送 `shutdown /l`；目标是否执行仍取决于学生端的远程命令能力。

### 远程运行程序与打开网址

```powershell
JiYuAttackNext.exe -ip 10.49.151.29 --run "C:/Windows/System32/notepad.exe"
JiYuAttackNext.exe -ip 10.49.151.1-10 --url example.com
JiYuAttackNext.exe -ip 10.49.151.29 --run "C:/Program Files/App/app.exe" --run-args "--silent" --run-show 1
```

### 黑屏、解锁与退出学生端

```powershell
JiYuAttackNext.exe -ip 10.49.151.29 --blackscreen 30 --blackout-text "请回到座位"
JiYuAttackNext.exe -ip 10.49.151.29 --blackscreen 60 --no-lock
JiYuAttackNext.exe -ip 10.49.151.29 --unlock
JiYuAttackNext.exe -ip 10.49.151.29 --exit-student
JiYuAttackNext.exe -ip 10.49.151.29 --kill 4321
```

### 发现学生机

```powershell
JiYuAttackNext.exe --students 12
JiYuAttackNext.exe --announce 15 --channel 2 --teacher-name "实验教师"
```

宣告不需要 `-ip`：报文发到会话组播地址，学生端收到后主动登录。发现阶段会先回会话应答与缩略图策略，再请求一次全量上报，因此终端里能直接看到计算机名、登录用户、系统、CPU、内存以及进程与窗口列表。没有任何学生登录时，命令会提示确认网段与频道是否一致。

## 行为与限制

- **发送结果**：CLI 模式不接收目标执行回执。“发送成功”仅表示本机发送调用未报错，不能据此确认目标已收到报文或完成操作。
- **循环参数**：`-l` 使用正整数，`-t` 使用非负整数。等待发生在两轮之间，不在每台设备之间。
- **功能组合**：`-msg`、`-c` 可与 `-e r`、`-e s` 或 `-e l` 组合。本地功能 `g`、`break`、`continue` 执行后退出；`nc` 使用独立分支，不处理同时传入的 `-msg` 或 `-c`。
- **文本编码**：消息与命令按 `utf-16le` 编码。消息超长时自动分条，命令仍受固定报文缓冲区限制；路径和引号需符合目标命令解释器的规则。
- **输出范围**：使用 `-c` 不会自动将目标命令的标准输出返回到当前终端。

## 运行日志

CLI 模式也会写运行日志，文件是数据目录下的 `cli.log`，与 GUI 的 `runtime.log` 分开，两个模式可以同时运行、各写各的文件。数据目录与 GUI 相同：EXE 所在目录下的 `JiYuAttackNextData`，源码运行时位于项目根目录。

- 等级固定为 `DEBUG`，不提供开关：命令行做的事比界面少，全部记录下来也不会淹没信息。参数快照、目标与报文数量、每个目标的送达判定、文件传送的路径与监听端口、异常都会写入。
- 只查帮助或版本号（`-h`、`--help`、`-V`、`--version`）不会创建数据目录，也不写日志：这类调用没有副作用，不留下空目录与只有一行的日志文件。
- 格式与 GUI 日志一致，可以直接用同一个查看器阅读：`2026-11-04 13:29:10.527 [10440] [MainThread] DEBUG   app.cli.main.main:318 - [命令行] 命令行参数`，多行内容以缩进续行写入。
- 文件在本次运行期间保持打开，每条记录写入后立即刷盘；进程被结束或崩溃时，已写入的记录不会丢。
- 目录不可写时只在终端提示一次“命令行日志保存失败”，命令本身照常执行，不会因为写日志失败而中断。

## 问题排查

| 现象 | 可能原因 | 检查建议 |
| --- | --- | --- |
| 提示找不到命令或程序 | 终端不在 EXE 所在目录，或 PowerShell 未加 `.\` 前缀 | 切换到 EXE 所在目录；PowerShell 使用 `.\JiYuAttackNext.exe ...`，cmd 可直接写 `JiYuAttackNext.exe ...`，也可使用绝对路径 |
| 双击后只打开 GUI | 无参数启动按设计进入 GUI | 在终端带功能参数启动 CLI，例如 `.\JiYuAttackNext.exe -ip 10.49.151.29 -msg "Hello"` |
| 提示“发送成功”，目标无响应 | 地址或端口不匹配、报文被拦截、学生端未监听、目标未执行指令 | 核对目标地址、UDP 端口、学生端状态及目标端执行结果 |
| 包含空格的路径处理失败 | 路径未完整加引号，或引号在终端传参时发生变化 | 参考包含空格路径的示例，并核对目标端路径 |
| `-e g` 未显示端口 | 未找到 `Student` 相关进程或其 UDP 监听端口 | 在本机核对进程与监听状态；查询失败时会显示错误原因 |
| 只有 IP、没有功能参数时无法发送 | 没有生成任何待发送报文 | 指定 `-msg`、`-c` 或相应扩展功能 |
| 长命令报错 | 命令超过固定报文缓冲区容量 | 缩短命令，检查终端输出的异常信息 |
| 长消息只显示部分内容或顺序不一致 | 消息被拆成独立报文，未提供接收端重组与可靠交付机制 | 核对目标端实际显示结果；分条发送不能保证合并为单条消息 |
| `--msg-file` 无法读取 | 文件不存在或文件编码不是 UTF-8 | 核对路径，将文件保存为 UTF-8 编码 |
