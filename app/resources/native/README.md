# 课堂防护 DLL

- `guard_x64.dll` / `guard_x86.dll`：课堂助手注入学生端的进程内防护组件，
  源码与构建说明见 `pack/native/guard/`。
- `driver/jiyu_guard_driver.sys`：可选的 WDM 自保护驱动，提供进程保护与
  内核强杀；源码与构建说明见 `pack/native/driver/`，默认不加载。
- `LICENSE-JiYuTrainer.txt`：上游 JiYuTrainer 的 MIT 许可证原文。

DLL 与驱动由 `pack/native/build-guard.ps1`、`pack/native/build-driver.ps1`
在 Windows 构建容器中编译，随 `pack/JiYuAttackNext.spec` 打入 EXE。
