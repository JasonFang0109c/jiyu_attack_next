"""校验 nightly 与发布工作流的触发条件、产物与版本号来源。"""

from pathlib import Path
import re
import unittest

WORKFLOW_DIR = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def read_workflow(name):
    return (WORKFLOW_DIR / name).read_text(encoding="utf-8")


class NightlyWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = read_workflow("nightly-build.yml")
        cls.build = read_workflow("build.yml")

    def test_workflow_has_name_and_triggers(self):
        self.assertIn("name: Nightly Build", self.workflow)
        self.assertIn("push:", self.workflow)
        self.assertIn("- main", self.workflow)
        self.assertIn("workflow_dispatch:", self.workflow)

    def test_workflow_skips_docs_only_changes(self):
        self.assertIn("paths:", self.workflow)
        for pattern in (
            '"app/**"',
            '"packaging/**"',
            '"scripts/**"',
            '"assets/**"',
            '"requirements.txt"',
            '".github/workflows/**"',
        ):
            self.assertIn(pattern, self.workflow)
        self.assertNotIn('"docs/**"', self.workflow)
        self.assertNotIn('"tests/**"', self.workflow)
        self.assertNotIn('"**/*.md"', self.workflow)

    def test_workflow_reuses_shared_build_with_nightly_channel(self):
        self.assertIn("uses: ./.github/workflows/build.yml", self.workflow)
        self.assertIn("channel: nightly", self.workflow)
        self.assertNotIn("build.ps1", self.workflow)

    def test_shared_build_produces_unified_exe(self):
        self.assertIn("runs-on: windows-latest", self.build)
        self.assertIn("packaging\\build.ps1 -Clean", self.build)
        self.assertIn("dist\\JiYuAttackNext.exe", self.build)
        self.assertIn("name: JiYuAttackNext-build", self.build)
        self.assertNotIn("cli\\main.py", self.build)
        self.assertNotIn("JiYuAttackNext-cli", self.build)

    def test_shared_build_appends_nightly_suffix_from_date(self):
        self.assertIn("ToString('yyyyMMdd')", self.build)
        self.assertIn("-nightly.$stamp", self.build)
        self.assertIn('$env:INPUT_CHANNEL -eq "nightly"', self.build)
        self.assertIn("version=$version", self.build)

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
        # 资产行只留文件名，产物说明交给文档，发布说明不再重复解释。
        self.assertIn("- \\`JiYuAttackNext.exe\\`", self.workflow)
        self.assertNotIn("图形界面与命令行共用", self.workflow)
        self.assertNotIn("## Message", self.workflow)
        self.assertNotIn("${commit_message}", self.workflow)
        self.assertNotIn("git log -1 --pretty=%B", self.workflow)
        self.assertNotIn("## 更新日志", self.workflow)

    def test_workflow_lists_commits_in_push_range(self):
        # 路径过滤按整个推送判定，tip 是文档也可能包含代码提交；
        # 发布说明列出 before..head 的全部提交，避免误判构建范围。
        self.assertIn("github.event.before", self.workflow)
        self.assertIn("## Commits", self.workflow)
        self.assertIn("${commit_list}", self.workflow)
        self.assertIn("fetch-depth: 0", self.workflow)
        self.assertGreater(
            self.workflow.index("## Commits"),
            self.workflow.index("## SHA256"),
        )

    def test_workflow_publishes_unified_exe(self):
        self.assertIn("files: |", self.workflow)
        self.assertIn("JiYuAttackNext.exe", self.workflow)
        self.assertIn("EXE:", self.workflow)
        self.assertIn("${exe_sha256}", self.workflow)
        self.assertNotIn("CLI:", self.workflow)
        self.assertNotIn("cli_sha256", self.workflow)

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
        cls.workflow = read_workflow("release.yml")

    def test_release_is_manual_only(self):
        self.assertIn("name: Release", self.workflow)
        self.assertIn("workflow_dispatch:", self.workflow)
        self.assertNotIn("push:", self.workflow)
        self.assertNotIn("schedule:", self.workflow)

    def test_release_builds_stable_channel_and_reuses_shared_build(self):
        self.assertIn("uses: ./.github/workflows/build.yml", self.workflow)
        self.assertIn("channel: stable", self.workflow)
        self.assertIn("version: ${{ inputs.version }}", self.workflow)

    def test_release_guards_against_version_mismatch_and_existing_tag(self):
        self.assertIn("grep -oP '__version__\\s*=\\s*\"\\K[^\"]+'", self.workflow)
        self.assertIn(
            'git rev-parse -q --verify "refs/tags/v${version}"', self.workflow
        )
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
            "JiYuAttackNext-${{ needs.build.outputs.version }}.exe", self.workflow
        )
        self.assertIn("EXE:", self.workflow)
        self.assertNotIn("JiYuAttackNext-cli", self.workflow)
        self.assertNotIn("cli_sha256", self.workflow)


class WorkflowVersionSourceTests(unittest.TestCase):
    def test_workflows_read_version_from_package(self):
        build = read_workflow("build.yml")
        self.assertIn("import app; print(app.__version__)", build)
        self.assertIsNone(re.search(r'__version__\s*=\s*"', build))


if __name__ == "__main__":
    unittest.main()
