"""模块边界与无界面导入约定的回归测试。"""

import ast
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ModuleLayoutTests(unittest.TestCase):
    def test_lower_layers_do_not_depend_on_features_or_gui(self):
        for layer in ("packets", "system", "shared"):
            for path in (ROOT / "app" / layer).rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                imports = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        imports.append(node.module or "")
                    elif isinstance(node, ast.Import):
                        imports.extend(alias.name for alias in node.names)
                with self.subTest(path=path.relative_to(ROOT)):
                    self.assertFalse(
                        any(
                            name == prefix or name.startswith(prefix + ".")
                            for name in imports
                            for prefix in (
                                "app.features",
                                "app.gui",
                                "app.start",
                                "PySide6",
                                "qfluentwidgets",
                            )
                        ),
                        imports,
                    )

    def test_runtime_imports_have_no_legacy_aggregation_layer(self):
        for path in (ROOT / "app").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                    names.extend(
                        (node.module + "." + alias.name)
                        for alias in node.names
                        if node.module
                    )
                elif isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                else:
                    continue
                with self.subTest(path=path.relative_to(ROOT), line=node.lineno):
                    self.assertFalse(
                        any(
                            name == prefix or name.startswith(prefix + ".")
                            for name in names
                            for prefix in ("app.core", "app.cli", "app.gui.pages")
                        ),
                        names,
                    )

    def test_business_modules_import_without_gui_or_qt(self):
        modules = []
        for path in (ROOT / "app" / "features").rglob("*.py"):
            if "gui" not in path.parts:
                module = ".".join(path.relative_to(ROOT).with_suffix("").parts)
                if module.endswith(".__init__"):
                    module = module[: -len(".__init__")]
                modules.append(module)
        script = (
            "import importlib,json,sys; "
            f"modules=json.loads({json.dumps(modules)!r}); "
            "[importlib.import_module(name) for name in modules]; "
            "bad=[name for name in sys.modules if "
            "name.split('.')[0] in {'PySide6','qfluentwidgets'} "
            "or name == 'app.gui' or name.startswith('app.gui.')]; "
            "assert not bad, bad"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
