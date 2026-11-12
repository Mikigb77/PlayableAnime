"""B4: the engine is plain Python, with no web framework or model SDK, so its rules can be tested
alone and move between frameworks unchanged."""

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2] / "engine"
ALLOWED_THIRD_PARTY = {"pydantic", "pydantic_core", "annotated_types", "typing_extensions"}

# Imports each module named on the command line in a fresh copy of this process, a few at a
# time, and says which of them failed.
IMPORT_EACH_FIRST = """
import importlib, os, sys
import pydantic  # loaded once, so each copy only pays for the engine

def first(name):
    pid = os.fork()
    if pid == 0:
        try:
            importlib.import_module(name)
        except BaseException as error:
            sys.stderr.write(f"{name}: {error!r}\\n")
            os._exit(1)
        os._exit(0)
    return pid

names, failed, running = sys.argv[1:], [], {}
while names or running:
    while names and len(running) < (os.cpu_count() or 1):
        name = names.pop()
        running[first(name)] = name
    pid, status = os.wait()
    if status:
        failed.append(running[pid])
    del running[pid]
sys.exit(1 if failed else 0)
"""


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


@pytest.mark.skipif(not hasattr(os, "fork"), reason="imports each module in a forked process")
def test_every_engine_module_can_be_the_first_one_imported():
    """No import cycle that bites in one order only. On 2026-11-12 `engine.encounters` could not
    be imported before `engine.world`, and nothing showed it until one test file ran alone: the
    suite and the API happen to import the engine in an order that worked."""
    names = sorted(
        ".".join(path.relative_to(ENGINE.parent).with_suffix("").parts).removesuffix(".__init__")
        for path in ENGINE.rglob("*.py")
    )
    assert "engine.encounters" in names and "engine" in names

    run = subprocess.run(
        [sys.executable, "-c", IMPORT_EACH_FIRST, *names],
        cwd=ENGINE.parent,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )

    assert run.returncode == 0, run.stderr[-3000:]
