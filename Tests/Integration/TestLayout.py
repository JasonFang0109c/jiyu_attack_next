"""模块边界与无界面导入约定的回归测试。"""

import ast
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "NeoJiYuTrainer"
UI = ROOT / "NeoJiYuTrainerUI"

QT_PREFIXES = ("PySide6", "qfluentwidgets", "NeoJiYuTrainerUI")


def imported_names(path):
    """收集模块里的全部导入名,供静态边界检查使用。"""
    names = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
            names.extend(
                (node.module + "." + alias.name) for alias in node.names if node.module
            )
        elif isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
    return names


def matches(name, prefixes):
    """判断导入名是否落在某个前缀下。"""
    return any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes)


class ModuleLayoutTests(unittest.TestCase):
    def test_lower_layers_do_not_depend_on_features_or_ui(self):
        prefixes = (
            "NeoJiYuTrainer.Features",
            "NeoJiYuTrainer.Start",
            "NeoJiYuTrainerUI",
            "PySide6",
            "qfluentwidgets",
        )
        for layer in ("packets", "system", "shared"):
            for path in (CORE / layer).rglob("*.py"):
                imports = imported_names(path)
                with self.subTest(path=path.relative_to(ROOT)):
                    self.assertFalse(
                        any(matches(name, prefixes) for name in imports), imports
                    )

    def test_core_keeps_qt_out_of_everything_but_start(self):
        # 只有 NeoJiYuTrainer/start/ 这层装配入口能拉起 Qt 与界面项目,
        # 业务、报文、系统适配与公共基础都必须能在没有 Qt 的环境里导入。
        offenders = {}
        for path in CORE.rglob("*.py"):
            if path.relative_to(CORE).parts[0] == "Start":
                continue
            imports = [
                name for name in imported_names(path) if matches(name, QT_PREFIXES)
            ]
            if imports:
                offenders[path.relative_to(ROOT).as_posix()] = imports
        self.assertEqual(offenders, {})

    def test_runtime_imports_have_no_legacy_aggregation_layer(self):
        prefixes = (
            "NeoJiYuTrainer.core",
            "NeoJiYuTrainer.cli",
            "NeoJiYuTrainerUI.core",
            "NeoJiYuTrainerUI.cli",
        )
        for path in list(CORE.rglob("*.py")) + list(UI.rglob("*.py")):
            for name in imported_names(path):
                with self.subTest(path=path.relative_to(ROOT)):
                    self.assertFalse(matches(name, prefixes), name)

    def test_business_modules_import_without_gui_or_qt(self):
        modules = []
        for path in (CORE / "Features").rglob("*.py"):
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
            "or name == 'NeoJiYuTrainerUI' or name.startswith('NeoJiYuTrainerUI.')]; "
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
