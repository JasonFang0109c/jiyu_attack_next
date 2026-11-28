"""校验 nightly 与发布工作流的触发条件、产物与版本号来源。"""

import re
import unittest
from pathlib import Path

WORKFLOW_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def read_workflow(name):
    return (WORKFLOW_DIR / name).read_text(encoding="utf-8")


class NightlyWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = read_workflow("NightlyBuild.yml")
        cls.build = read_workflow("Build.yml")

    def test_workflow_has_name_and_triggers(self):
        self.assertIn("name: Nightly Build", self.workflow)
        self.assertIn("push:", self.workflow)
        self.assertIn("- main", self.workflow)
        self.assertIn("workflow_dispatch:", self.workflow)

    def test_workflow_skips_docs_only_changes(self):
        self.assertIn("paths:", self.workflow)
        for pattern in (
            '"NeoJiYuTrainer/**"',
            '"Pack/**"',
            '"Scripts/**"',
            '"requirements.txt"',
            '".github/workflows/**"',
        ):
            self.assertIn(pattern, self.workflow)
        self.assertNotIn('"assets/**"', self.workflow)
        self.assertNotIn('"packaging/**"', self.workflow)
        self.assertNotIn('"docs/**"', self.workflow)
        self.assertNotIn('"Tests/**"', self.workflow)
        self.assertNotIn('"**/*.md"', self.workflow)

    def test_workflow_reuses_shared_build_with_nightly_channel(self):
        self.assertIn("uses: ./.github/workflows/Build.yml", self.workflow)
        self.assertIn("channel: nightly", self.workflow)
        self.assertNotIn("Build.ps1", self.workflow)

    def test_shared_build_produces_unified_exe(self):
        self.assertIn("runs-on: windows-latest", self.build)
        self.assertIn("Pack\\Build.ps1 -Clean", self.build)
        # 构建哪些变体由 variants 输入决定：both 产出正常版本与 _Debug 版本，
        # nightly 只传 release，因此只编译正常版本。
        self.assertIn("variants:", self.build)
        self.assertIn("default: both", self.build)
        self.assertIn('-Variant "$env:VARIANTS"', self.build)
        self.assertIn('$names = @("NeoJiYuTrainer")', self.build)
        self.assertIn('if ($env:VARIANTS -ne "release") {', self.build)
        self.assertIn('$names += "NeoJiYuTrainer_Debug"', self.build)
        self.assertIn("name: NeoJiYuTrainer-build", self.build)
        self.assertIn("path: dist/*.exe", self.build)
        self.assertNotIn("cli\\main.py", self.build)
        self.assertNotIn("NeoJiYuTrainer-cli", self.build)

    def test_shared_build_appends_nightly_suffix_from_date(self):
        self.assertIn("ToString('yyyyMMdd')", self.build)
        self.assertIn("-nightly.$stamp", self.build)
        self.assertIn('$env:INPUT_CHANNEL -eq "nightly"', self.build)
        self.assertIn("version=$version", self.build)

    def test_shared_build_appends_commit_hash_to_test_versions(self):
        # 测试版在基础版本号后追加提交哈希，正式版保持纯版本号；
        # 哈希优先取 nightly 选出的构建提交，取不到时回退到 GITHUB_SHA。
        self.assertIn("$base = $version", self.build)
        self.assertIn('$commit = ""', self.build)
        self.assertIn("$sha = $env:BUILD_COMMIT", self.build)
        self.assertIn("if (-not $sha) { $sha = $env:GITHUB_SHA }", self.build)
        self.assertIn("$commit = $sha.Substring(0, 7)", self.build)
        self.assertIn('$display = "$base-$commit"', self.build)
        self.assertIn("base=$base", self.build)
        self.assertIn("commit=$commit", self.build)
        self.assertIn("display=$display", self.build)
        self.assertIn("value: ${{ jobs.build.outputs.display }}", self.build)
        # 构建提交单独作为 build_commit 输出，发布页用它指向同一个提交。
        self.assertIn("value: ${{ jobs.build.outputs.build_commit }}", self.build)
        self.assertIn("build_commit: ${{ steps.build_commit.outputs.sha }}", self.build)
        self.assertIn('-Commit "${{ steps.version.outputs.commit }}"', self.build)
        self.assertIn("VERSION: ${{ steps.version.outputs.display }}", self.build)
        self.assertIn('-Version "${{ steps.version.outputs.base }}"', self.build)

    def test_workflow_notes_keep_date_version_without_commit_hash(self):
        # 版本号与标题用带日期的版本号，资产行用带哈希的显示版本。
        self.assertIn("VERSION: ${{ needs.build.outputs.version }}", self.workflow)
        self.assertIn("DISPLAY: ${{ needs.build.outputs.display }}", self.workflow)
        self.assertIn("- **Version:**", self.workflow)
        self.assertIn("NeoJiYuTrainer-${DISPLAY}.exe", self.workflow)
        self.assertIn(
            "name: Nightly Build ${{ needs.build.outputs.version }}", self.workflow
        )

    def test_workflow_notes_list_version_build_time_commit_and_run(self):
        # 顺序固定为版本号、构建时间、提交、工作流运行，便于开工单时逐项抄录。
        order = [
            "- **Version:**",
            "- **Built at:**",
            "- **Commit:**",
            "- **Workflow run:**",
        ]
        positions = [self.workflow.index(item) for item in order]
        self.assertEqual(positions, sorted(positions))

    def test_workflow_notes_keep_assets_line_plain(self):
        # 资产行只列正常版本，调试版本的说明括在括号里，不再单独占一行。
        self.assertIn(
            "- \\`NeoJiYuTrainer-${DISPLAY}.exe\\`（正常版本；"
            "调试版本只在本次 Actions 运行的产物里）",
            self.workflow,
        )
        self.assertNotIn("- \\`NeoJiYuTrainer.exe\\`", self.workflow)
        self.assertNotIn("图形界面与命令行共用", self.workflow)
        self.assertNotIn("${commit_message}", self.workflow)
        self.assertNotIn("git log -1 --pretty=%B", self.workflow)
        self.assertNotIn("## 更新日志", self.workflow)

    def test_workflow_lists_commits_in_push_range(self):
        # 路径过滤按整个推送判定，tip 是文档也可能包含代码提交；
        # 构建流程在 push 范围内逐个回查，发布说明只列选中的那一行提交。
        self.assertIn("EVENT_BEFORE: ${{ github.event.before }}", self.build)
        self.assertIn('$range = @("$before..$env:GITHUB_SHA")', self.build)
        self.assertIn("## Commits", self.workflow)
        self.assertIn("${commit_list}", self.workflow)
        self.assertIn("fetch-depth: 0", self.workflow)
        self.assertGreater(
            self.workflow.index("## Commits"),
            self.workflow.index("## SHA256"),
        )

    def test_workflow_links_each_commit(self):
        # 提交行把缩写哈希链到 commit 页面，方便从发布说明直接看改动。
        self.assertIn("/commit/%H", self.workflow)
        self.assertIn("git log -1 --pretty=format:", self.workflow)
        self.assertNotIn("--pretty=format:'- `%h` %s'", self.workflow)

    def test_workflow_records_single_build_commit(self):
        # tip 可能只是文档提交，构建流程取范围内最新一个影响构建的提交，
        # 把它写进 build_commit 输出，并作为发布页的 target_commitish。
        self.assertNotIn("## Message", self.workflow)
        self.assertNotIn("commit-messages.md", self.workflow)
        self.assertNotIn("git log -1 --pretty=%B", self.workflow)

        self.assertIn("name: Select build commit", self.build)
        self.assertIn("if: ${{ inputs.channel == 'nightly' }}", self.build)
        self.assertIn("fetch-depth: 0", self.build)
        self.assertIn("$patterns = ", self.build)
        expression = re.search(r"\$patterns = '([^']+)'", self.build).group(1)
        pattern = re.compile(expression)
        for path in (
            "NeoJiYuTrainer/Start/Service.py",
            "NeoJiYuTrainer/Resources/Icons/App.svg",
            "Pack/Build.ps1",
            "Scripts/RunGui.ps1",
            "requirements.txt",
            ".github/workflows/Build.yml",
        ):
            with self.subTest(path=path):
                self.assertIsNotNone(pattern.match(path))
        for path in (
            "Docs/Dev/Build.md",
            "Tests/Integration/TestEntry.py",
            "NeoJiYuTrainerHooks/Build.ps1",
        ):
            with self.subTest(path=path):
                self.assertIsNone(pattern.match(path))

        self.assertIn("foreach ($sha in (git log --format=%H @range)) {", self.build)
        self.assertIn("--name-only", self.build)
        self.assertIn("git checkout --quiet $selected", self.build)
        self.assertIn('"sha=$selected" | Out-File', self.build)
        self.assertIn("if (-not $selected) { $selected = $env:GITHUB_SHA }", self.build)
        self.assertIn("BUILD_COMMIT: ${{ steps.build_commit.outputs.sha }}", self.build)
        self.assertIn(
            "target_commitish: ${{ needs.build.outputs.build_commit }}", self.workflow
        )

    def test_workflow_publishes_unified_exe(self):
        self.assertIn("files: |", self.workflow)
        # 只发布一个带提交哈希的正常版本：调试版本留在 Actions 运行产物里，
        # 固定名副本会让发布页堆出多余资产。
        self.assertIn(
            "dist/NeoJiYuTrainer-${{ needs.build.outputs.display }}.exe",
            self.workflow,
        )
        files_block = self.workflow.split("files: |", 1)[1]
        self.assertNotIn("NeoJiYuTrainer_Debug", files_block)
        self.assertNotIn("NeoJiYuTrainer_Debug-", self.workflow)
        self.assertNotIn("dist/NeoJiYuTrainer.exe", files_block)
        self.assertIn("EXE:", self.workflow)
        self.assertIn("${exe_sha256}", self.workflow)
        self.assertNotIn("${debug_sha256}", self.workflow)
        self.assertNotIn("CLI:", self.workflow)
        self.assertNotIn("cli_sha256", self.workflow)
        # nightly 只让共享构建编译正常版本。
        self.assertIn("variants: release", self.workflow)

    def test_workflow_reuses_same_day_release_and_deletes_on_new_day(self):
        # 同一天只在原预发布上更新资产与说明，跨天才删除重建：
        # 每次删除重建都会推一条 release 事件，关注者的动态会被刷屏。
        self.assertIn("Decide whether to reuse today's nightly release", self.workflow)
        self.assertIn('echo "reuse=true" >> "${GITHUB_OUTPUT}"', self.workflow)
        self.assertIn('echo "reuse=false" >> "${GITHUB_OUTPUT}"', self.workflow)
        state = self.workflow.index("Decide whether to reuse today's nightly release")
        self.assertLess(state, self.workflow.index("Remove previous nightly release"))
        self.assertLess(
            self.workflow.index("Remove previous nightly release"),
            self.workflow.index("Publish Nightly Build pre-release"),
        )

    def test_workflow_skips_removal_when_today_release_exists(self):
        # 删除步骤只在新的一天执行，同一天走 overwrite_files 原地替换。
        self.assertIn(
            "if: ${{ steps.nightly_state.outputs.reuse != 'true' }}",
            self.workflow,
        )
        self.assertIn("gh release delete nightly --yes --cleanup-tag", self.workflow)
        self.assertIn("overwrite_files: true", self.workflow)

    def test_workflow_clears_stale_assets_before_reusing(self):
        # 资产名带提交哈希，复用当天预发布时旧名字的资产不会被覆盖，
        # 发布后统一清理，只保留本次构建的那一个文件。
        self.assertIn("name: Prune unexpected nightly assets", self.workflow)
        self.assertIn(
            "EXPECTED: NeoJiYuTrainer-${{ needs.build.outputs.display }}.exe",
            self.workflow,
        )
        self.assertIn(
            "gh release view nightly --json assets --jq '.assets[].name'",
            self.workflow,
        )
        self.assertIn("gh release delete-asset nightly", self.workflow)
        self.assertIn('if [[ "${asset}" != "${EXPECTED}" ]]; then', self.workflow)
        self.assertGreater(
            self.workflow.index("Prune unexpected nightly assets"),
            self.workflow.index("Publish Nightly Build pre-release"),
        )

    def test_workflow_compares_release_date_from_version_stamp(self):
        # 日期取自构建版本号的 -nightly.YYYYMMDD 后缀，
        # 与产物里记录的日期同源，不依赖运行器本地时区。
        self.assertIn('stamp="${VERSION##*-nightly.}"', self.workflow)
        self.assertIn("gh release view nightly --json name", self.workflow)
        self.assertIn("needs.build.outputs.version", self.workflow)
        self.assertIn("::error::nightly 版本号缺少", self.workflow)

    def test_workflow_moves_nightly_tag_only_when_reusing(self):
        # 复用当天的预发布时是原地更新，标签要挪到本次提交。
        self.assertIn("Point nightly tag at this build", self.workflow)
        self.assertIn(
            "if: ${{ steps.nightly_state.outputs.reuse == 'true' }}",
            self.workflow,
        )
        self.assertIn(
            '"repos/${GITHUB_REPOSITORY}/git/refs/tags/nightly"', self.workflow
        )
        self.assertGreater(
            self.workflow.index("Point nightly tag at this build"),
            self.workflow.index("Publish Nightly Build pre-release"),
        )

    def test_workflow_replaces_prerelease_with_nightly_tag(self):
        self.assertIn("tag_name: nightly", self.workflow)
        self.assertIn("prerelease: true", self.workflow)
        self.assertIn("make_latest: false", self.workflow)


class ReleaseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = read_workflow("Release.yml")

    def test_release_is_manual_only(self):
        self.assertIn("name: Release", self.workflow)
        self.assertIn("workflow_dispatch:", self.workflow)
        self.assertNotIn("push:", self.workflow)
        self.assertNotIn("schedule:", self.workflow)

    def test_release_builds_stable_channel_and_reuses_shared_build(self):
        self.assertIn("uses: ./.github/workflows/Build.yml", self.workflow)
        self.assertIn("channel: stable", self.workflow)
        self.assertIn("version: ${{ inputs.version }}", self.workflow)

    def test_release_guards_against_version_mismatch_and_existing_tag(self):
        self.assertIn("grep -oP '__version__\\s*=\\s*\"\\K[^\"]+'", self.workflow)
        self.assertIn(
            'git rev-parse -q --verify "refs/tags/v${version}"', self.workflow
        )
        self.assertIn("NeoJiYuTrainer/Shared/Version.py", self.workflow)
        self.assertNotIn("NeoJiYuTrainer/core/constants.py", self.workflow)
        self.assertIn("正式版版本号不能带预发布后缀", self.workflow)

    def test_release_creates_semver_tag_and_marks_latest(self):
        self.assertIn("tag_name: v${{ needs.build.outputs.version }}", self.workflow)
        self.assertIn("prerelease: false", self.workflow)
        self.assertIn("make_latest: true", self.workflow)
        self.assertIn("overwrite_files: false", self.workflow)
        self.assertIn("draft: ${{ inputs.draft }}", self.workflow)

    def test_release_notes_list_changes_since_previous_tag(self):
        self.assertIn("git describe --tags --abbrev=0 --match 'v*'", self.workflow)
        self.assertIn("## Changes", self.workflow)
        self.assertIn("## SHA256", self.workflow)

    def test_release_publishes_single_unified_exe(self):
        self.assertIn(
            "NeoJiYuTrainer-${{ needs.build.outputs.version }}.exe", self.workflow
        )
        self.assertIn("EXE:", self.workflow)
        self.assertNotIn("NeoJiYuTrainer-cli", self.workflow)
        self.assertNotIn("cli_sha256", self.workflow)


class WorkflowVersionSourceTests(unittest.TestCase):
    def test_workflows_read_version_from_package(self):
        build = read_workflow("Build.yml")
        self.assertIn("import NeoJiYuTrainer; print(NeoJiYuTrainer.__version__)", build)
        self.assertIsNone(re.search(r'__version__\s*=\s*"', build))


if __name__ == "__main__":
    unittest.main()
