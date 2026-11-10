<div align="center">
<h1>版本规范</h1>
<p>
   <img alt="SemVer 2.0.0" src="https://img.shields.io/badge/版本-SemVer%202.0.0-blue.svg">
   <img alt="Channel" src="https://img.shields.io/badge/通道-stable%20%7C%20nightly-2CA5E0.svg">
</p>
<p><a href="../../README.md">返回项目首页</a> 丨 <a href="BUILD.md">EXE 构建</a> 丨 <a href="STRUCTURE.md">项目结构</a></p>
</div>

---

项目采用 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)（SemVer），当前处于 `0.y.z` 开发阶段：版本可以快速演进，公共接口不承诺稳定。首个正式版为 `0.1.0`，此前只发布过 nightly。正式版与 nightly 共用同一套版本号，nightly 在版本号后追加预发布标识。

## 版本号格式

```text
主版本号.次版本号.修订号                       正式版，例如 0.1.0
主版本号.次版本号.修订号-nightly.YYYYMMDD         nightly，例如 0.1.0-nightly.20261029
主版本号.次版本号.修订号-提交哈希               nightly 的显示版本，例如 0.1.0-1a8ede3
```

测试版的显示版本在基础版本号后追加 7 位提交哈希，不带到日期；只有测试版带哈希，正式版始终是纯版本号。带哈希的形式出现在三处：EXE 文件名（含带版本号的副本）、EXE 属性里的版本资源、GUI 与命令行显示的版本号；发布说明的标题与 `**Version:**` 行只写带日期的版本号，不写哈希。同一天的多次推送因此能靠文件名与界面区分，GitHub 上的发布标题却不会每次都变。

nightly 的后缀符合 SemVer 第 9 条“先行版本号”的约定：标识符只使用 ASCII 字母、数字与连接号，且 `0.1.0-nightly.20261029` 的优先级低于 `0.1.0`。追加提交哈希后 `20261029-1a8ede3` 仍是单个点分标识符，只是同一个先行版本号内的更细标识，不影响与正式版的排序关系。因此同一版本线内的 nightly 永远排在对应正式版之前，GitHub 与包管理工具都能正确排序。显示版本去掉了日期，因为文件名里已经有哈希区分每次构建，夜间版的身份由标签 `nightly` 与发布说明里的带日期版本号承担。

## 起始版本

首个正式版从 `0.1.0` 开始。项目此前只发布过滚动覆盖的 nightly，没有对外承诺过任何版本线，因此不需要为了“看起来成熟”而抬高起始号；SemVer FAQ 也建议以 `0.1.0` 作为初始化开发版本。

- `0.y.z` 表示项目仍处于快速演进阶段，行为与接口都可能调整。
- 在发布 `1.0.0` 之前，递增次版本号即可表达不兼容改动，不必升主版本号。
- 如果将来认为功能与接口已经稳定，发布 `1.0.0` 完成转正。

## 递增规则

| 改动内容 | 递增位置 | 示例 |
| --- | --- | --- |
| 不兼容的改动，或对既有行为的大幅调整 | 次版本号（`0.y.z` 阶段不升主版本号） | `0.1.0` → `0.2.0` |
| 向下兼容的新功能 | 次版本号 | `0.1.0` → `0.2.0` |
| 向下兼容的问题修复 | 修订号 | `0.1.0` → `0.1.1` |
| 文档、注释、测试、工作流等不影响产物的改动 | 不递增 | 保持 `0.1.0` |

- `0.y.z` 阶段升次版本号时修订号归零；升主版本号（`1.0.0`）时次版本号与修订号一并归零。
- 公共接口被认为稳定、可以承诺兼容性时发布 `1.0.0`，此后按 SemVer 第 6～8 条递增。
- 已发布的版本号不得复用：修复只能通过新的修订号发布，不能覆盖同一标签的产物。

提交信息采用 [Conventional Commits](CONTRIBUTING.md#提交信息)：`feat`、`fix`、破坏性变更分别表达 MINOR、PATCH、MAJOR 发布语义，破坏性变更优先于类型判断。当前 `0.y.z` 阶段仍按上表处理不兼容改动，递增次版本号；进入稳定版本后再按 SemVer 递增主版本号。其他类型（包括 `refactor`、`perf`）本身不隐含递增级别，应按实际兼容性与改动内容判断。

这些是发布决策的语义依据，不代表提交后自动修改版本号。版本号仍需按本规范维护，并通过既有发布流程发布；文档、测试等不影响产物的改动沿用上表的不递增规则。

## 版本号唯一来源

| 位置 | 作用 |
| --- | --- |
| `app/shared/version.py` 的 `__version__` | 唯一权威来源，构建脚本与工作流都从这里读取 |
| `app/__init__.py` | 重新导出 `__version__`，供运行时代码和“关于”页使用 |
| `build/assets/version.txt` | 构建时写入并打包进 EXE，供“关于”页与命令行显示；测试版写带提交哈希的显示版本 |

`app/shared/version.py` 负责把提交哈希拼到版本号上（`display_version`）并读取打包内的显示版本（`runtime_version`），`app/shared/build_info.py` 转调它。

`tests/pack/test_versioning.py` 校验版本号格式、包导出值与命令行 `--version` 输出一致；`pack/build.ps1` 会拒绝不符合 SemVer 的版本号，`release.yml` 会拒绝与源码不一致或已存在标签的版本号。

## 发布通道

| 通道 | 触发方式 | 标签 | Release 属性 | 资产文件名 |
| --- | --- | --- | --- | --- |
| 正式版 | Actions 页面手动运行 `Release` | `v0.1.0`（与版本号一致，不复用） | 正式版，`make_latest: true` | `JiYuAttackNext-0.1.0.exe` 与 `JiYuAttackNext_Debug-0.1.0.exe`，另附固定名 `JiYuAttackNext.exe` 与 `JiYuAttackNext_Debug.exe` |
| nightly | 推送到 `main` 且改动影响产物，或手动运行 | `nightly`（同一天原地更新，跨天删除重建） | 预发布，`make_latest: false` | 两个带显示版本的文件：`JiYuAttackNext-<显示版本>.exe`、`JiYuAttackNext_Debug-<显示版本>.exe` |

- 标签名带 `v` 前缀是 Git 的通行写法，但 `v` 不属于 SemVer 版本号本身。
- 正式版与 nightly 都提供正常运行版本与调试版本两个 EXE，两者代码相同，只有日志等级不同：正常运行版本只记录 `WARNING` 与 `ERROR`，`_Debug` 版本从 `DEBUG` 起全量记录，供排查问题使用。正式版的固定名资产保证 README 与文档中的下载链接长期有效，另附带版本号的副本；nightly 只发布带提交哈希的两个文件，不再提供固定名。该资产是同一个 EXE，同时提供 GUI 与 CLI。
- nightly 同一天内重复构建时原地更新同一个预发布，只替换资产与说明，不产生新的发布通知；日期变了才删除旧的预发布与 `nightly` 标签再重新创建，因此历史资产与旧说明不会残留，下载地址仍固定为 `https://github.com/JasonFang0109c/jiyu_attack_next/releases/tag/nightly`。
- 发布说明中的日期使用 ISO 8601 格式（`YYYY-MM-DD`），与 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的建议一致。
- 同一个 EXE 同时提供 GUI 与 CLI，发布资产不再附带独立的命令行脚本。

## 发布正式版

1. 确认 `app/shared/version.py` 的 `__version__` 已改为目标版本，并已提交到 `main`。
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
- [PEP 440](https://packaging.python.org/en/latest/specifications/version-specifiers/)：Python 生态的版本标识规范；若命令行功能将来以 Python 包形式发布，需要以它为准
- [GitHub Releases 文档](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)：预发布、最新版本与标签的行为
