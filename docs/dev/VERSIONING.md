<div align="center">
<h1>版本规范</h1>
<p>
   <img alt="SemVer 2.0.0" src="https://img.shields.io/badge/版本-SemVer%202.0.0-blue.svg">
   <img alt="Channel" src="https://img.shields.io/badge/通道-stable%20%7C%20nightly-2CA5E0.svg">
</p>
<p><a href="../../README.md">返回项目首页</a> 丨 <a href="BUILD.md">EXE 构建</a> 丨 <a href="STRUCTURE.md">项目结构</a></p>
</div>

---

项目采用 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)（SemVer），当前处于 `0.y.z` 开发阶段：版本可以快速演进，公共接口不承诺稳定。正式版与 nightly 共用同一套版本号，nightly 在版本号后追加预发布标识。

## 版本号格式

```text
主版本号.次版本号.修订号            正式版，例如 0.4.0
主版本号.次版本号.修订号-nightly.YYYYMMDD   nightly，例如 0.4.0-nightly.20261029
```

nightly 的后缀符合 SemVer 第 9 条“先行版本号”的约定：标识符只使用 ASCII 字母、数字与连接号，且 `0.4.0-nightly.20261029` 的优先级低于 `0.4.0`。因此同一版本线内的 nightly 永远排在对应正式版之前，GitHub 与包管理工具都能正确排序。

## 递增规则

| 改动内容 | 递增位置 | 示例 |
| --- | --- | --- |
| 不兼容的改动，或对既有行为的大幅调整 | 次版本号（`0.y.z` 阶段不升主版本号） | `0.4.0` → `0.5.0` |
| 向下兼容的新功能 | 次版本号 | `0.4.0` → `0.5.0` |
| 向下兼容的问题修复 | 修订号 | `0.4.0` → `0.4.1` |
| 文档、注释、测试、工作流等不影响产物的改动 | 不递增 | 保持 `0.4.0` |

- `0.y.z` 阶段升次版本号时修订号归零；升主版本号（`1.0.0`）时次版本号与修订号一并归零。
- 公共接口被认为稳定、可以承诺兼容性时发布 `1.0.0`，此后按 SemVer 第 6～8 条递增。
- 已发布的版本号不得复用：修复只能通过新的修订号发布，不能覆盖同一标签的产物。

提交类型与递增位置基本对应：`Feat` 对应次版本号，`Fix`、`Refactor`、`Perf`、`Hotfix` 对应修订号，`Docs`、`Test`、`Style`、`CI` 通常不递增。

## 版本号唯一来源

| 位置 | 作用 |
| --- | --- |
| `app/__init__.py` 的 `__version__` | 权威来源，构建脚本与工作流都从这里读取 |
| `cli/main.py` 的 `__version__` | 镜像值；该文件需可单独复制运行，因此不导入 `app` |
| `build/assets/version.txt` | 构建时写入并打包进 EXE，供“关于”页显示 |

两处 `__version__` 必须一致，由 `tests/test_versioning.py` 校验；`scripts/build.ps1` 会拒绝不符合 SemVer 的版本号，`release.yml` 会拒绝与源码不一致或已存在标签的版本号。

## 发布通道

| 通道 | 触发方式 | 标签 | Release 属性 | 资产文件名 |
| --- | --- | --- | --- | --- |
| 正式版 | Actions 页面手动运行 `Release` | `v0.4.0`（与版本号一致，不复用） | 正式版，`make_latest: true` | `JiYuAttackNext-0.4.0.exe`、`JiYuAttackNext-cli-0.4.0.py`，另附固定名 |
| nightly | 推送到 `main` 且改动影响产物，或手动运行 | `nightly`（滚动覆盖） | 预发布，`make_latest: false` | `JiYuAttackNext.exe`、`JiYuAttackNext-cli.py` |

- 标签名带 `v` 前缀是 Git 的通行写法，但 `v` 不属于 SemVer 版本号本身。
- 正式版额外提供带版本号的资产名，便于归档；固定名资产保证 README 与文档中的下载链接长期有效。
- nightly 沿用滚动覆盖：复用 `nightly` 标签与同名预发布，覆盖旧资产与说明，下载地址固定为 `https://github.com/JasonFang0109c/jiyu_attack_next/releases/tag/nightly`。
- 发布说明中的日期使用 ISO 8601 格式（`YYYY-MM-DD`），与 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的建议一致。

## 发布正式版

1. 确认 `app/__init__.py` 与 `cli/main.py` 的 `__version__` 已改为目标版本，并已提交到 `main`。
2. 打开仓库的 `Actions` 页面，左侧选择 `Release`，点击 `Run workflow`。
3. 分支选择 `main`；`version` 留空表示使用源码中的 `__version__`，需要覆盖时再填写。
4. 需要先自检时勾选 `draft`，Release 会以草稿创建，确认无误后在 Releases 页面发布。
5. 运行结束后，`Releases` 页面出现 `JiYu Attack Next vX.Y.Z`，标签为 `vX.Y.Z`，并成为最新正式版。

工作流会在发布前校验：版本号与源码一致、正式版不带预发布后缀、标签 `vX.Y.Z` 尚不存在。任一条件不满足即失败，不会覆盖已发布内容。

## 参考规范

- [语义化版本 2.0.0（中文）](https://semver.org/lang/zh-CN/)：版本号格式、先行版本号与优先级比较规则
- [SemVer 官方站点（英文）](https://semver.org/)：原始规范与正则表达式
- [Calendar Versioning](https://calver.org/)：日期版本方案；本项目未采用，仅供对比
- [Keep a Changelog 1.1.0（中文）](https://keepachangelog.com/zh-CN/1.1.0/)：更新日志的组织方式与日期格式
- [PEP 440](https://packaging.python.org/en/latest/specifications/version-specifiers/)：Python 生态的版本标识规范；若 CLI 版将来发布到 PyPI，需要以它为准
- [GitHub Releases 文档](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)：预发布、最新版本与标签的行为
