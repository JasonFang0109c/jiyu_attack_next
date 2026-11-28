# 原生组件边界

`pack/native/` 对应 JiYuTrainer 上游的原生项目边界，但只保留 NeoJiYuTrainer 实际需要的两部分：

- `hooks/`：对应上游 `JiYuTrainerHooks`。这里构建课堂防护 DLL、广播窗口右键菜单、远程命令确认和隔离自测夹具；实现由当前项目的策略共享内存协议控制。
- `driver/`：对应上游 `JiYuTrainerDriver`。这里构建可选的 WDM 自保护/内核强杀驱动；设备名、IOCTL 和签名流程以当前项目接口为准，不直接复用上游旧 ABI。

上游的 `JiYuTrainerUI`（Sciter 界面）由 `app/gui/` 的 PySide6 界面替代；`JiYuTrainerUpdater` 不纳入当前目录，因为项目暂时没有自动更新功能。上游的 `Debug/`、`Release/`、旧 VS 工程文件和预编译二进制也不复制进仓库。

普通开发不需要原生编译器。只有修改 `hooks/` 或 `driver/` 的源码时，才按
[`docs/dev/BUILD.md`](../../docs/dev/BUILD.md) 在现有 Windows 容器内构建。
