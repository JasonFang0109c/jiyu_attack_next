# 课堂防护 DLL

- `guard_x64.dll` / `guard_x86.dll`：课堂助手注入学生端的进程内防护组件，
  源码与构建说明见 `pack/native/guard/`。
- `LICENSE-JiYuTrainer.txt`：上游 JiYuTrainer 的 MIT 许可证原文。

DLL 由 `pack/native/build-guard.ps1` 在 Windows 构建容器中编译，随
`pack/JiYuAttackNext.spec` 打入 EXE。
