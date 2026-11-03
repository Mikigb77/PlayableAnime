"""B4: the engine is plain Python, with no web framework or model SDK, so its rules can be tested
alone and move between frameworks unchanged."""

import ast
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2] / "engine"
ALLOWED_THIRD_PARTY = {"pydantic", "pydantic_core", "annotated_types", "typing_extensions"}


def imported_top_level_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def test_engine_imports_only_the_standard_library_pydantic_and_itself():
    sources = sorted(ENGINE.rglob("*.py"))
    assert sources, f"no engine sources found under {ENGINE}"

    for path in sources:
        foreign = {
            module
            for module in imported_top_level_modules(path)
            if module != "engine"
            and module not in sys.stdlib_module_names
            and module not in ALLOWED_THIRD_PARTY
        }
        assert not foreign, f"{path.relative_to(ENGINE.parent)} imports {sorted(foreign)}"
