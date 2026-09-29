import ast
from pathlib import Path


def test_core_does_not_import_modes() -> None:
    for path in Path("core").rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
                assert all(not name.startswith("modes") for name in names), path
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.startswith("modes"), path

