<div align="center">
<h1>上游骨架重构路线</h1>
<p><a href="../../README.md">← 返回项目首页</a> 丨 <a href="STRUCTURE.md">项目结构</a> 丨 <a href="CONTRIBUTING.md">开发与提交规范</a></p>
</div>

---

## 这次重构要解决什么

NeoJiYuTrainer 以本地 `D:\Code\Project\JiYuTrainer` 作为行为和功能的上游参考，但运行骨架仍使用当前的 Python 3.13、PySide6-Fluent-Widgets、CLI 和 PyInstaller。这里的“按上游重构”指的是把职责和功能领域对齐，不是把旧的 Visual Studio、Sciter 或 C++ 类直接搬进 Python。

这样安排有两个直接好处：

1. 上游的学生端管理、课堂窗口处理、Hook、防护和报文领域都有清楚的对应位置。
2. 当前项目新增的远程消息、文件传送、反弹终端、工作流、日志、卸载和现代 GUI 不会被旧工程覆盖。

本文件是重构期间的总账。每一阶段只做一小块，先保留旧入口和旧设置格式，验证通过后再移动实现或删除重复代码。

## 功能保留清单

| 上游领域或功能 | 当前实现 | 处理决定 |
| --- | --- | --- |
| StudentMain 定位、路径记忆、启停和状态 | `app/features/student/` | 保留并作为学生端领域入口；行为逐项对照 `TrainerWorker` |
| 用户态关闭与强制结束 | `app/features/student/service.py`、`app/system/windows/process.py` | 保留用户态链；可选驱动失败后再走内核强杀 |
| 课堂广播窗口识别、窗口化、假全屏、置顶 | `app/features/classroom/windows.py`、`service.py` | 保留 Python 窗口规则；Guard DLL 负责进程内菜单和 Hook |
| 极域卸载密码（明文/Knock1） | `app/features/classroom/passwords.py` | 保留算法与 golden/单元测试，不凭猜测改常量 |
| 反监视、防控制、禁止关闭、禁止结束 | `app/system/windows/guard.py`、`pack/native/hooks/` | 保留当前策略协议、DLL、x86/x64 资源和构建夹具 |
| 远程命令逐条允许 | `guard.py` 共享内存、课堂 GUI 服务、Guard DLL | 保留 30 秒超时拒绝、逐条确认和“全部允许”行为 |
| UDP 消息、远程命令、重启/关机/注销 | `app/packets/`、`app/system/net/`、`app/features/send/` | 以当前回归测试为基线；不直接覆盖上游报文实现 |
| 文件传送 | `app/features/files/` | 项目新增能力，保留 HTTP 临时服务、取消、重试和多文件目录树 |
| 反弹终端 | `app/features/shell/` | 项目新增能力，保留本地服务和 UTF-8 交互 |
| 本机信息、防火墙、设备备注、日志 | `app/features/local/`、`firewall/`、`names/`、`logs/` | 保留为 Python GUI/CLI 功能，不强行塞入上游 C++ 模块 |
| 全局热键 | `app/system/windows/hotkey.py`、`app/gui/hotkey.py` | 保留文本解析与 Qt/Win32 接收层分离 |
| 可选自保护/内核强杀驱动 | `app/system/windows/driver.py`、`pack/native/driver/` | 保留当前 IOCTL 和测试签名资源；默认不加载，不替换为上游二进制 |
| 卸载 | `app/features/uninstall/`、设置页、`local uninstall` | 保留快捷方式、驱动服务、可选数据和退出后清理流程 |
| 单实例、使用须知、托盘、主题、设置 | `app/start/`、`app/gui/`、`app/features/settings/` | 保留当前 Qt 生命周期和设置文件格式 |
| 自动更新、崩溃报告、本机电源菜单 | 当前未移植 | 暂不引入；只有确认产品需求后单独设计 |
| 上游 Sciter UI、`wWinMain`、C++ 全局生命周期 | 不适用 | 不复制；映射到现有 Python 启动和 PySide6 页面 |

## 上游到当前结构的映射

| JiYuTrainer 上游位置 | NeoJiYuTrainer 位置 | 迁移边界 |
| --- | --- | --- |
| `JiYuTrainer/JiYuTrainer.cpp`、`App.h` | `app/__main__.py`、`app/start/`、`app/shared/` | 保留 Python/Qt 事件循环，不搬 `wWinMain` 和 Sciter 装载 |
| `JiYuTrainer/TrainerWorker.*` | `app/features/student/`、`app/features/classroom/`、`app/gui/workers/` | 按领域拆开进程、窗口和后台任务，避免重新制造巨型服务 |
| `JiYuTrainer/JyUdpAttack.*` | `app/packets/`、`app/system/net/`、`app/features/send/` | 复用协议行为；保留取消、轮次、进度和送达结果 |
| `JiYuTrainerHooks/` | `pack/native/hooks/`、`app/system/windows/guard.py` | 当前 Guard 协议独立维护；先对照导出、策略、位数和夹具 |
| `JiYuTrainerDriver/` | `pack/native/driver/`、`app/system/windows/driver.py` | 当前设备名、IOCTL、签名和服务生命周期不与上游混用 |
| `JiYuTrainerUI/` | `app/gui/window/`、各 `features/*/gui/` | 迁移页面语义，不迁移 Sciter HTML、DOM 事件和控件实现 |
| `JiYuTrainerUpdater/` | `.github/workflows/`、`pack/` | 当前发布链先保留；自动更新另立需求，不作为隐式迁移项 |
| 上游 `mhook`、`disasm-lib`、许可证 | `pack/native/hooks/mhook/`、`disasm-lib/`、资源许可证 | 原样保留第三方声明，禁止覆盖 GPL-3.0 |

上游部分 C++ 文件不是 UTF-8。迁移时按原始字节或正确代码页读取；没有逐函数证据前，不重写密码、报文、Hook 或驱动常量。

## 目标目录（兼容后收敛）

```text
app/
  start/                         # GUI / CLI 生命周期和入口
  features/                      # 按用户功能组织的领域服务与页面
    student/ classroom/          # 上游核心领域
    send/ message/ command/      # 远程攻击工作流
    files/ shell/ device/        # 本项目扩展工作流
    local/ firewall/ names/      # 本机与设备辅助
    settings/ logs/ home/ about/ uninstall/
  compat/                        # Qt-free 的稳定模型、协议和旧 API shim
  packets/                       # UDP 模板、编解码、脚本托管
  system/
    net/                         # 目标、UDP、探测、送达结果
    windows/                     # 进程、窗口、Guard、Driver、UAC、热键
  gui/                           # PySide6 装配、页面适配、后台任务
  shared/                        # 路径、设置、日志、资源、版本
  resources/native/              # 随包 DLL、SYS 和许可证
pack/native/                     # Guard/Driver 源码与容器构建
 tests/
  contract/                      # compat 协议与 Fake 后端契约
  unit/ integration/ gui/ pack/
```

`app/compat/` 是旁路边界，不在第一阶段搬动现有实现。旧路径继续可用，后续服务逐个接入协议后才删除重复入口。

## 分阶段执行

### S0：冻结基线

- 保存功能矩阵、入口、设置键、报文、资源和删除候选。
- 记录 unit/integration、CLI `--help`、GUI 导入和 EXE 冒烟结果。
- 不修改 `data/`，不删构建产物前先确认是否需要保留。

### S1：兼容契约（当前阶段）

- 新增 Qt-free 的 `app/compat/models.py`、`protocols.py`、`errors.py`、`flags.py`、`constants.py`。
- 新增 `legacy.py` 延迟转发，保持旧服务签名，不在导入时加载 Qt、驱动或真实系统资源。
- 新增 `tests/contract/` Fake 后端测试。
- 本阶段不改 `features/`、GUI、Guard DLL、Driver、报文实现。

### S2：服务接线

按 `send → student → classroom → uninstall` 的顺序，把服务依赖改成协议；先 Fake 后 Windows 实现。结果字典、设置键、CLI 参数和旧函数保留一个兼容周期。

### S3：GUI 渐进迁移

保留 PySide6 主窗口和导航，每次只迁一个页面。页面只处理控件和信号，Win32、`sc.exe`、DLL 注入和文件服务留在后端适配器。

### S4：远程攻击与工作流

抽出 UDP codec、目标解析、文件 HTTP 服务和 shell bootstrap 的可测试流水线；用回环/Fake 传输替代真实目标测试，不覆盖当前协议回归。

### S5：课堂防护原生适配

把 Guard DLL、共享内存、远程命令确认、窗口菜单和可选 Driver 接到契约层；验证缺资源时普通消息/文件/UDP 功能仍可用。

### S6：删除与发布

用 import graph、测试覆盖和构建结果确认旧 shim、重复常量或死代码没有调用后再删。更新 spec、文档和 CI；卸载只做 dry-run 验证，永远保留用户 `data/` 的边界。

## 删除规则

只有同时满足以下条件才允许删除旧代码：

1. `ops_grep`/import graph 证明没有运行时调用；
2. 对应功能已有 compat 契约或明确的新入口；
3. 单元、集成、GUI 和打包测试覆盖等价行为；
4. EXE 能启动，CLI `--help` 和相关功能冒烟通过；
5. `data/`、运行日志、资源许可证和可回滚提交仍保留。

以下内容在重构期间明确保留：`app/start/`、`app/packets/`、`app/system/net/`、学生端/课堂助手/文件/终端服务、Guard/Driver 源码与运行时资源，以及用户数据目录。

## 每阶段验收和回滚

每个阶段一个提交，先跑与改动直接相关的测试，再按 `AGENTS.md` 要求构建并冒烟。发现行为回归时优先 `git revert` 当前阶段提交，或关闭新适配器；不通过删除数据、覆盖上游目录或直接替换原生二进制来“修复”。
