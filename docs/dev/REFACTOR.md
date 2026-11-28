<div align="center">
<h1>上游骨架重构路线</h1>
<p><a href="../../README.md">← 返回项目首页</a> 丨 <a href="STRUCTURE.md">项目结构</a> 丨 <a href="CONTRIBUTING.md">开发与提交规范</a></p>
</div>

---

## 这次重构要解决什么

NeoJiYuTrainer 以本地只读目录 `D:\Code\Project\JiYuTrainer` 作为行为与功能的上游参考，运行骨架仍是现有的 Python 3.13、PySide6-Fluent-Widgets、CLI 与 PyInstaller。这里的“按上游重构”指职责划分和功能领域对齐，不是把旧的 Visual Studio 工程、Sciter 页面或 C++ 类搬进 Python。

要解决的是三件事：

1. 上游的四块职责（核心逻辑、课堂防护 DLL、内核驱动、界面）各有位置；当前实现把它们挤在一个 `app/` 包里，原生源码挂在 `pack/native/` 下，界面与业务混在同一棵目录树。
2. 之前插进 `app/` 的中间边界层（共享模型、协议接口、延迟转发）和它的独立测试目录没有真实调用方，已经整体删除；文档不能继续把它写成现存结构。
3. 目录边界和文档要能直接指导后续迁移：先立原生项目，再改核心包，最后拆界面。

重构完成后，仓库只有四个一级项目边界，加 `pack/`、`tests/`、`docs/` 三个辅助目录；每个方向的依赖单一，界面不反向污染核心。

## 上游 JiYuTrainer 参考

### 规模

上游目录共 27 个目录、543 个文件，只作为阅读与行为对照的参考，不参与本项目构建。

### 根目录文件

```text
.gitattributes
.gitignore
LICENSE
README.md
JiYuTrainer.sln
JiYuTrainerBug.ico
JiYuTrainerLogo.ico
JiYuTrainerLogo.psd
JiYuTrainerLogo16.png
JiYuTrainerLogo256.png
JiYuTrainerTitle.png
JiYuTrainerWarn.ico
ScreenShots.png
pchunter1.png
sc0.png
sc1.png
帮助.png
```

### 递归目录树

```text
JiYuTrainer/                      # 上游仓库根，共 27 个目录
|-- JiYuTrainer/
|   |-- Debug/
|   `-- Release/
|-- JiYuTrainerDriver/
|   |-- Debug/
|   `-- Release/
|-- JiYuTrainerHooks/
|   |-- Debug/
|   |-- Release/
|   |-- disasm-lib/
|   `-- mhook-lib/
|-- JiYuTrainerUI/
|   |-- Debug/
|   |-- Release/
|   |-- res/
|   `-- sciter-sdk/
|       `-- include/
|           |-- behaviors/
|           |   `-- camera/
|           `-- curl/
|-- JiYuTrainerUpdater/
|   |-- Debug/
|   |-- Release/
|   `-- curl/
|       |-- curl/
|       `-- vtls/
`-- Release/
```

### 各目录职责与处理方式

| 上游目录 | 内容 | 处理方式 |
| --- | --- | --- |
| `JiYuTrainer/` | `App.*`、`TrainerWorker.*`、`JyUdpAttack.*`、`DriverLoader.*`、`KernelUtils.*`、`NetUtils.*`，以及路径、注册表、设置、日志、压缩、内存加载工具 | 对应核心 Python 项目 `NeoJiYuTrainer/` |
| `JiYuTrainerHooks/` | Hook DLL、窗口处理、输入拦截、远程命令、广播窗口菜单、`mhook-lib`、`disasm-lib` | 对应 `NeoJiYuTrainerHooks/` |
| `JiYuTrainerDriver/` | WDM 驱动、自保护、进程强杀、IOCTL | 对应 `NeoJiYuTrainerDriver/` |
| `JiYuTrainerUI/` | Sciter 主窗口、攻击窗口、设置窗口、帮助窗口、扫描窗口、HTML、资源、Sciter SDK | 对应现代 PySide6 的 `NeoJiYuTrainerUI/` |
| `JiYuTrainerUpdater/` | curl、旧自动更新器 | 排除，不迁移 |
| `Debug/`、`Release/`、根目录 `Release/` | 上游 Visual Studio 中间产物与构建输出 | 排除 |

上游部分 C++ 文件不是 UTF-8。对照或摘取时按原始字节或正确代码页读取；没有逐函数证据前，不重写密码、报文、Hook 或驱动常量。

## 目标根目录结构

四个一级项目边界加三个辅助目录，`__init__.py` 等常规包文件此处省略。

```text
NeoJiYuTrainer/            # Python 核心包，阶段 C 由 app/ 改名
|-- __init__.py            # 重新导出版本号
|-- __main__.py            # python -m 入口
|-- start/                 # 入口分流、CLI 分发、GUI 生命周期
|-- features/              # student classroom send message command device
|                          # files shell local firewall names settings
|                          # logs home about uninstall
|-- packets/               # UDP 报文、命令表、蓝屏脚本托管
|-- system/
|   |-- net/               # 目标解析、UDP、探测、送达结果
|   `-- windows/           # 进程、端口、窗口、Guard、Driver、UAC、热键解析
|-- shared/                # 路径、设置、日志、版本、资源定位
`-- resources/
    |-- icons/             # 静态图标
    `-- native/            # 随包 DLL、SYS 与上游许可证
NeoJiYuTrainerHooks/       # 原生课堂防护 DLL：guard.cpp、menu.cpp、remote.h、policy.h、第三方库
NeoJiYuTrainerDriver/      # 可选 WDM 驱动源码与 IOCTL 头
NeoJiYuTrainerUI/          # PySide6 界面：窗口、导航、页面、控件、后台任务
pack/                      # PyInstaller spec、构建与签名脚本、hooks、版本资源生成器
tests/                     # fixtures/ gui/ integration/ pack/ unit/
docs/                      # dev/ usage/
```

`NeoJiYuTrainerHooks/` 与 `NeoJiYuTrainerDriver/` 已按此路径落在仓库根目录（暂存的重命名，由 `git status` 可见）。核心包已在阶段 C 由 `app/` 改名为 `NeoJiYuTrainer/`；`NeoJiYuTrainerUI/` 在阶段 D 由核心包里的 `gui/` 与各功能 `gui/` 拆出。

## 明确排除清单

下列内容不复制进本项目，也不作为迁移对象。

| 排除项 | 原因 |
| --- | --- |
| `NeoJiYuTrainerUpdater/`、上游 `curl`、旧自动更新器 | 自动更新暂不引入，需要时单独设计 |
| Sciter SDK | 界面统一用 PySide6-Fluent-Widgets |
| 上游 HTML 与 C++ 界面实现 | 只迁移页面语义与交互，不迁移实现 |
| `Debug/`、`Release/`、根目录 `Release/` | 上游构建中间产物与输出 |
| `.sln`、`.vcxproj*`、`.rc`、`.aps` | 旧 Visual Studio 工程文件 |
| 预编译的上游 DLL、SYS、EXE | 原生资源由本项目自己的源码构建 |
| 上游 `LICENSE`、`.gitattributes`、`.gitignore` | 仓库已有自己的版本，第三方许可证另行随资源保留 |

## 当前功能到四个项目的映射

重构后必须保留的能力，按归属落表。核心包负责业务与系统适配，界面只负责装配与交互，原生项目各自独立。

| 功能域 | 目标位置 | 保留的内容 |
| --- | --- | --- |
| 启动与界面 | `NeoJiYuTrainer/start/` + `NeoJiYuTrainerUI/` | `python -m` 入口、无参数 GUI、有参数 CLI、单实例、使用须知、系统托盘、主题与窗口材质、设置保存、日志、PySide6-Fluent-Widgets |
| 学生端 | `features/student/` + `system/windows/{process,driver,elevation}` | 定位 `StudentMain.exe`、路径记忆、PID/路径/端口查询、启动、停止、用户态关闭、失败后可选驱动内核强杀、UAC 提权助手、结束后复查 |
| 课堂助手 | `features/classroom/{windows,passwords,service}` | 广播窗口识别、窗口化、假全屏、还原、置顶、黑屏窗口隐藏、自动看护、极域卸载密码读取与明文解析、Knock1 解密 |
| 课堂防护 | `NeoJiYuTrainerHooks/`（`guard.cpp`、`menu.cpp`、`remote.h`、`policy.h`）+ `system/windows/guard.py` | 阻止屏幕监视、阻止远程控制、禁止关闭窗口、禁止结束进程、远程命令逐条确认与 30 秒超时拒绝、“本次运行期间全部允许”、广播窗口右键菜单（全屏/取消全屏/置顶/关闭） |
| 远程攻击 | `features/{send,message,command,device,files,shell}` + `packets/` + `system/net/` | 文本消息、远程命令、文件传送、设备操作、重启/关机/注销、蓝屏命令、反弹终端、UDP 攻击、局域网目标扫描、取消任务、轮次控制、进度反馈、送达反馈 |
| 本机工具 | `features/{local,firewall,names,logs}` | 本机 IP 与 UDP 端口、防火墙规则、设备备注、运行日志、本地 CLI 信息 |
| 全局热键 | `system/windows/hotkey.py` + `NeoJiYuTrainerUI/gui/hotkey.py` | 显示/隐藏主窗口、假全屏、设置页修改热键、Win32 隐藏窗口接收 `WM_HOTKEY`；纯解析留在核心包，Qt 与 Win32 消息接收留在界面 |
| 可选驱动 | `NeoJiYuTrainerDriver/` + `system/windows/driver.py` | 安装驱动服务、打开设备、保护 PID、取消保护、内核强杀、查询状态、清理保护、停止并删除服务 |
| 卸载 | `features/uninstall/` | 桌面与开始菜单快捷方式、停止并删除驱动服务、可选删除 `data/`、退出后清理安装目录、源码运行跳过真正卸载 |
| 暂不引入 | — | 自动更新、崩溃报告、本机电源菜单、上游 Sciter UI、上游旧网络过滤驱动、上游旧 `Debug/`、`Release/`、旧 Visual Studio 工程 |

## 实际代码迁移顺序

一个阶段一个提交，前一步验证通过再动下一步。顺序固定为：先清痕迹，再立原生项目，再改核心包，最后拆界面。

### 阶段 A：清理已移除边界层的痕迹

- 对应源码包与测试目录的删除已进入暂存，确认不再有文件残留、不再被导入。
- 重写本文件与 `docs/dev/STRUCTURE.md`，按四个一级项目边界描述目标结构。
- 清理其它文档、测试与配置里对已删除路径的引用；确认检索不到失效表述。
- 本阶段只改文本，不移动目录、不改运行代码、不碰 `data/`、`.venv/`、`build/`、`output/`。

### 阶段 B：原生项目根目录迁移

- `pack/native/hooks/` → `NeoJiYuTrainerHooks/`，`pack/native/driver/` → `NeoJiYuTrainerDriver/`，用 `git mv` 保留历史，不复制后删除。
- 同步 `pack/NeoJiYuTrainer.spec`、`build.ps1`、`clean_build.ps1`、`sign-driver.ps1` 的路径，以及 `tests/pack/` 中检查布局的断言。
- 保持第三方裸源码（`disasm-lib`、`mhook`）内容不变，只换位置。

### 阶段 C：Python 核心包 `app/` → `NeoJiYuTrainer/`

- 一次提交内完成包名、全部内部导入、`pyproject.toml`、spec 的入口脚本、工作流的路径过滤与 `tests/integration/test_layout.py` 的导入断言，避免停在半改名状态。
- 入口同步改为 `python -m NeoJiYuTrainer`；`__main__.py`、`start/` 的分流逻辑不变。
- 校验：CLI `--help`、GUI 启动导入、全量单元与集成测试。

### 阶段 D：界面拆出核心包 → `NeoJiYuTrainerUI/`

- 核心包内的 `gui/`（阶段 C 前是 `app/gui/`）整体迁入 `NeoJiYuTrainerUI/gui/`；各功能的 `gui/page.py`、`gui/service.py`、`gui/data.py` 迁入 `NeoJiYuTrainerUI/gui/pages/<功能>/`。
- 核心包不再导入 Qt；界面只调用核心包的服务与数据约定，不反向依赖界面内部实现。
- 全局热键拆分到位：解析留在 `system/windows/hotkey.py`，消息接收留在 `NeoJiYuTrainerUI/gui/hotkey.py`。
- 校验：界面能启动、页面与导航齐全、`tests/gui/` 通过、核心包导入时不加载 Qt。

### 阶段 E：清理与最终验收

- 删除迁移后留下的空目录与历史残留入口，核对 `.gitignore`、CI 过滤路径与全部文档中的路径。
- 全量测试、构建 EXE 并冒烟；确认 `data/` 未被触碰，用户设置与日志仍在原位。
- 冻结版本号与发布说明，之后不再以“重构”为由调整目录。

## 删除和保留规则

只有同时满足下列条件才允许删除旧代码：

1. 用检索与导入关系证明没有运行时调用方；
2. 功能在新位置有等价实现或明确的新入口；
3. 单元、集成、界面与打包测试覆盖等价行为；
4. EXE 能启动，CLI `--help` 与相关功能冒烟通过；
5. 有可回滚的提交，且不触碰用户数据。

以下内容在重构期间始终保留：

| 对象 | 规则 |
| --- | --- |
| `data/` | 用户备注、设置、`runtime.log` 与 `cli.log`。任何阶段都不删除、不改名、不清空；只有用户在设置页主动清除或自行删除 |
| `.venv/`、`build/`、`output/` | 本地环境与产物，由 `.gitignore` 排除，不提交、不在重构中清理 |
| `LICENSE`、第三方裸源码、上游许可证文本 | 不改写、不重新格式化，只随资源移动位置 |
| 提交 | 本阶段改动留在工作区，由 lead 统一核对后提交；不 push |

## 每阶段验收和回滚

| 阶段 | 验收 | 回滚 |
| --- | --- | --- |
| A | `git status --porcelain` 只有本阶段文件；关键词检索无残留；单元测试全绿 | 还原两份文档与引用文件，恢复被误删的文本 |
| B | 原生源码在新路径可构建；spec、构建脚本与布局断言同步；`tests/pack/` 通过 | 回退该阶段提交，源码回到 `pack/native/` |
| C | `python -m NeoJiYuTrainer --help` 正常；GUI 可导入启动；`test_layout.py` 与全量测试通过 | 回退改名提交，恢复 `app/` 包名 |
| D | 界面启动、页面齐全、核心包导入不加载 Qt；`tests/gui/` 通过 | 回退该阶段提交 |
| E | 全量测试、EXE 构建与冒烟、目录与文档路径核对一致 | 回退清理提交 |

发现行为回归时优先 `git revert` 当前阶段提交，或关闭新接入的适配层；不通过删除数据、覆盖上游目录或直接替换原生二进制来“修复”。
