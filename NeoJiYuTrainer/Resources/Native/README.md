# 课堂防护 DLL

- `GuardX64.dll` / `GuardX86.dll`:课堂助手注入学生端的进程内防护组件,
  包含防护 Hook、远程命令确认与广播窗口右键菜单;源码与构建说明见
  `NeoJiYuTrainerHooks/`。
- `Driver/JiYuGuardDriver.sys`:可选的 WDM 自保护驱动,提供进程保护与
  内核强杀;源码与构建说明见 `NeoJiYuTrainerDriver/`,默认不加载。当前文件
  已用 `Pack/SignDriver.ps1` 做测试签名,测试签名环境仍需目标机器开启
  `Testsigning` 并关闭 Secure Boot。
- `LICENSE-JiYuTrainer.txt`:上游 JiYuTrainer 的 MIT 许可证原文。

DLL 与驱动由 `NeoJiYuTrainerHooks/Build.ps1`、`NeoJiYuTrainerDriver/Build.ps1`
在 Windows 构建容器中编译,随 `Pack/NeoJiYuTrainer.spec` 打入 EXE。
