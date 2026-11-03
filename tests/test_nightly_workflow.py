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

    def test_workflow_includes_latest_commit_changelog_last(self):
        self.assertIn("git log -1 --pretty=%B", self.workflow)
        self.assertIn("## Message", self.workflow)
        self.assertIn("${commit_message}", self.workflow)
        self.assertNotIn("## 更新日志", self.workflow)
        self.assertGreater(
            self.workflow.index("## Message"),
            self.workflow.index("## SHA256"),
        )

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
        self.assertLess(
            self.workflow.index("## Commits"),
            self.workflow.index("## Message"),
        )

    def test_workflow_publishes_unified_exe(self):
        self.assertIn("files: |", self.workflow)
        self.assertIn("JiYuAttackNext.exe", self.workflow)
        self.assertIn("EXE:", self.workflow)
        self.assertIn("${exe_sha256}", self.workflow)
        self.assertNotIn("CLI:", self.workflow)
        self.assertNotIn("cli_sha256", self.workflow)

    def test_workflow_removes_stale_cli_asset_before_publish(self):
        # overwrite_files 只覆盖同名文件，遗留的命令行脚本需按名字显式删除，
        # 否则 nightly 会一直挂着已停止发布的资产。
        self.assertIn("JiYuAttackNext-cli.py", self.workflow)
        self.assertIn('gh release delete-asset nightly "${name}" --yes', self.workflow)
        self.assertIn("--json assets --jq", self.workflow)
        self.assertLess(
            self.workflow.index("Remove stale release assets"),
            self.workflow.index("Publish Nightly Build pre-release"),
        )

    def test_workflow_replaces_prerelease_with_nightly_tag(self):
        self.assertIn("tag_name: nightly", self.workflow)
        self.assertIn("prerelease: true", self.workflow)
        self.assertIn("overwrite_files: true", self.workflow)
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
