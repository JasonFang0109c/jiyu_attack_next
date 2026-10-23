from pathlib import Path
import unittest


class NightlyWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "nightly-build.yml"
        ).read_text(encoding="utf-8")

    def test_workflow_has_name_and_triggers(self):
        self.assertIn("name: Nightly Build", self.workflow)
        self.assertIn("push:", self.workflow)
        self.assertIn("- main", self.workflow)
        self.assertIn("workflow_dispatch:", self.workflow)

    def test_workflow_builds_and_uploads_windows_exe(self):
        self.assertIn("runs-on: windows-latest", self.workflow)
        self.assertIn("scripts\\build.ps1 -Clean", self.workflow)
        self.assertIn("path: dist/JiYuAttackNext.exe", self.workflow)

    def test_workflow_includes_latest_commit_changelog_last(self):
        self.assertIn("git log -1 --pretty=%B", self.workflow)
        self.assertIn("## Message", self.workflow)
        self.assertIn("${commit_message}", self.workflow)
        self.assertNotIn("## 更新日志", self.workflow)
        self.assertGreater(
            self.workflow.index("## Message"),
            self.workflow.index("## SHA256"),
        )

    def test_workflow_replaces_prerelease_with_nightly_tag(self):
        self.assertIn("tag_name: nightly", self.workflow)
        self.assertIn("name: Nightly Build", self.workflow)
        self.assertIn("prerelease: true", self.workflow)
        self.assertIn("overwrite_files: true", self.workflow)


if __name__ == "__main__":
    unittest.main()
