#!/usr/bin/env python3
"""check_wiring.py — Detect dead code, orphaned files, and circular dependencies.

Catches the most insidious AI agent failure mode: code that LOOKS complete
but isn't connected. Tests pass, lint passes, but the feature is never wired up.

Checks:
  A. Orphaned files — .py files imported by nothing (zero incoming edges)
  B. Unused exports — public functions/classes never referenced elsewhere
  C. Circular dependencies — import cycles (A → B → C → A)
  D. Unwired routes — route decorators in files not registered with the app

Exit code 0 = clean, 1 = violations found.
Error messages are actionable — the agent can read them and self-repair.
"""

import ast
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

# ═══════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories to scan (auto-detected)
SCAN_DIRS = ["backend", "src", "app", "lib"]

# Files that are legitimate entry points (not orphans even if nothing imports them)
ENTRY_POINTS = {
    "__init__.py", "__main__.py", "main.py", "app.py", "wsgi.py", "asgi.py",
    "manage.py", "conftest.py", "setup.py", "settings.py", "config.py",
    "celery.py", "tasks.py", "admin.py", "urls.py", "server.py", "cli.py",
    "routes.py", "deps.py", "schemas.py", "models.py",
}

# Directories to skip
SKIP_DIRS = {
    "__pycache__", ".venv", "venv", "node_modules", ".git",
    "migrations", "alembic", ".mypy_cache", ".pytest_cache",
    "dist", "build", "egg-info",
}

# Route decorator patterns (for unwired route detection)
ROUTE_DECORATORS = {
    "app.get", "app.post", "app.put", "app.delete", "app.patch",
    "router.get", "router.post", "router.put", "router.delete", "router.patch",
    "app.route", "router.route",
    "api_router.get", "api_router.post", "api_router.put", "api_router.delete",
}

# Decorators that make a function "implicitly used" (not dead code)
# These functions are called by frameworks, not by other source files.
IMPLICIT_USE_DECORATORS = {
    # Web frameworks (FastAPI, Flask, Django)
    "app.get", "app.post", "app.put", "app.delete", "app.patch", "app.route",
    "router.get", "router.post", "router.put", "router.delete", "router.patch",
    "router.route", "api_router.get", "api_router.post", "api_router.put",
    "api_router.delete", "api_router.patch",
    "app.middleware", "app.on_event", "app.exception_handler",
    "router.api_route", "app.websocket",
    # CLI frameworks (Click, Typer)
    "app.command", "cli.command", "group.command", "app.callback",
    "click.command", "click.group",
    # Testing
    "pytest.fixture", "pytest.mark",
    # Celery / async tasks
    "celery.task", "app.task", "shared_task",
    # Event handlers
    "app.on_startup", "app.on_shutdown",
    "receiver", "signal",
    # Property decorators
    "property", "staticmethod", "classmethod",
    # Dataclass / pydantic
    "validator", "field_validator", "model_validator",
}

# Simple decorator names (no dot) that mark implicit use
IMPLICIT_USE_SIMPLE_DECORATORS = {
    "property", "staticmethod", "classmethod", "abstractmethod",
    "override", "cached_property", "lru_cache",
    "fixture", "mark",
}

violations: list[str] = []


def find_project_dir() -> Optional[Path]:
    """Auto-detect the project source directory."""
    for dirname in SCAN_DIRS:
        candidate = REPO_ROOT / dirname
        if candidate.is_dir():
            # Check it has Python files
            if any(candidate.rglob("*.py")):
                return candidate
    return None


def collect_python_files(project_dir: Path) -> list[Path]:
    """Collect all Python files, skipping excluded directories."""
    files = []
    for f in project_dir.rglob("*.py"):
        if any(skip in f.parts for skip in SKIP_DIRS):
            continue
        files.append(f)
    return files


def extract_imports(filepath: Path, project_dir: Path) -> set[str]:
    """Extract all imports from a Python file as module paths."""
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()

    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports


def filepath_to_module(filepath: Path, project_dir: Path) -> str:
    """Convert a file path to a Python module path."""
    rel = filepath.relative_to(project_dir)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].replace(".py", "")
    return ".".join(parts)


def _get_decorator_str(deco: ast.expr) -> str:
    """Extract a readable string from a decorator AST node."""
    # @router.get("/path") → "router.get"
    if isinstance(deco, ast.Call):
        return _get_decorator_str(deco.func)
    # @router.get → "router.get"
    if isinstance(deco, ast.Attribute):
        if isinstance(deco.value, ast.Name):
            return f"{deco.value.id}.{deco.attr}"
    # @property → "property"
    if isinstance(deco, ast.Name):
        return deco.id
    return ""


def _is_implicitly_used(node: ast.AST) -> bool:
    """Check if a function/class is implicitly used via decorators."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return False
    for deco in getattr(node, "decorator_list", []):
        deco_str = _get_decorator_str(deco)
        if deco_str in IMPLICIT_USE_DECORATORS:
            return True
        if deco_str in IMPLICIT_USE_SIMPLE_DECORATORS:
            return True
        # Handle @click.command(), @app.command() patterns with any prefix
        if deco_str.endswith((".command", ".task", ".fixture", ".route")):
            return True
    return False


def extract_public_names(filepath: Path) -> list[tuple[str, int, bool]]:
    """Extract public function and class names with line numbers.

    Returns: list of (name, lineno, is_implicitly_used)
    """
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []

    names = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                names.append((node.name, node.lineno, _is_implicitly_used(node)))
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                names.append((node.name, node.lineno, _is_implicitly_used(node)))
    return names


def has_route_decorators(filepath: Path) -> list[tuple[str, int]]:
    """Check if file defines route handlers."""
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []

    routes = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in node.decorator_list:
                deco_str = ""
                if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute):
                    if isinstance(deco.func.value, ast.Name):
                        deco_str = f"{deco.func.value.id}.{deco.func.attr}"
                elif isinstance(deco, ast.Attribute):
                    if isinstance(deco.value, ast.Name):
                        deco_str = f"{deco.value.id}.{deco.attr}"

                if deco_str in ROUTE_DECORATORS:
                    routes.append((node.name, node.lineno))
    return routes


def check_orphaned_files(
    files: list[Path],
    project_dir: Path,
    import_graph: dict[str, set[str]],
) -> None:
    """CHECK A: Find files that nothing imports."""
    # Build set of all modules that are imported by something
    imported_modules: set[str] = set()
    for imports in import_graph.values():
        imported_modules.update(imports)

    for filepath in files:
        if filepath.name in ENTRY_POINTS:
            continue
        # Skip test files — they're entry points for pytest
        if "test" in filepath.name.lower() or "test" in str(filepath.parent).lower():
            continue

        module = filepath_to_module(filepath, project_dir)

        # Check if this module (or any prefix of it) is imported
        is_imported = False
        for imp in imported_modules:
            if imp == module or imp.startswith(module + ".") or module.startswith(imp + "."):
                is_imported = True
                break

        if not is_imported:
            rel = filepath.relative_to(REPO_ROOT)
            violations.append(
                f"  ORPHAN: {rel} — imported by nothing. "
                f"Either import it from another module or delete it."
            )


def _file_has_argparse(filepath: Path) -> bool:
    """Check if a file uses argparse/click for CLI — its functions are entry points."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(kw in content for kw in [
        "argparse", "add_parser", "add_subparsers", "ArgumentParser",
        "click.command", "click.group", "typer.Typer", "@app.command",
    ])


def _file_has_framework_registration(filepath: Path) -> bool:
    """Check if a file defines a factory function (create_app, etc.)."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(kw in content for kw in [
        "FastAPI(", "Flask(", "APIRouter(", "create_app",
        "Starlette(", "Django",
    ])


def check_unused_exports(files: list[Path], project_dir: Path) -> None:
    """CHECK B: Find public functions/classes never referenced elsewhere.

    Skips functions that are implicitly used via:
    - Decorators (routes, CLI commands, fixtures, tasks)
    - Argparse/Click CLI registration (functions in CLI files)
    - Framework factories (create_app patterns)
    """
    # Collect all source text for fast grep
    all_sources: dict[Path, str] = {}
    for f in files:
        try:
            all_sources[f] = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

    # Pre-detect CLI files and framework files
    cli_files: set[Path] = set()
    factory_files: set[Path] = set()
    for f in files:
        if _file_has_argparse(f):
            cli_files.add(f)
        if _file_has_framework_registration(f):
            factory_files.add(f)

    for filepath in files:
        # Skip test files and __init__.py
        if "test" in filepath.name.lower() or filepath.name == "__init__.py":
            continue

        public_names = extract_public_names(filepath)
        for name, lineno, implicitly_used in public_names:
            # Skip functions that are implicitly used via decorators
            if implicitly_used:
                continue

            # Skip functions in CLI files (argparse/click register them)
            if filepath in cli_files and name.startswith(("cmd_", "command_", "handle_", "run_", "build_")):
                continue

            # Skip factory functions in framework files
            if filepath in factory_files and name.startswith(("create_", "make_", "build_", "get_")):
                continue

            # Count references in OTHER files (including same-file for self-references)
            ref_count = 0
            for other_path, source in all_sources.items():
                if other_path == filepath:
                    continue
                if name in source:
                    ref_count += 1

            if ref_count == 0:
                rel = filepath.relative_to(REPO_ROOT)
                violations.append(
                    f"  UNUSED: {rel}:{lineno} — '{name}' is public but never "
                    f"referenced in other files. Make it private (_prefix) or use it."
                )


def check_circular_deps(
    files: list[Path],
    project_dir: Path,
    import_graph: dict[str, set[str]],
) -> None:
    """CHECK C: Detect import cycles."""
    # Build module-level adjacency list
    module_graph: dict[str, set[str]] = defaultdict(set)
    all_modules = set()

    for filepath in files:
        module = filepath_to_module(filepath, project_dir)
        all_modules.add(module)
        imports = import_graph.get(str(filepath), set())

        for imp in imports:
            # Only track internal imports (within project)
            for m in all_modules:
                if imp == m or imp.startswith(m + ".") or m.startswith(imp + "."):
                    if m != module:
                        module_graph[module].add(m)

    # DFS cycle detection
    visited: set[str] = set()
    in_stack: set[str] = set()
    cycles: list[list[str]] = []

    def dfs(node: str, path: list[str]) -> None:
        if node in in_stack:
            cycle_start = path.index(node)
            cycle = path[cycle_start:] + [node]
            cycles.append(cycle)
            return
        if node in visited:
            return

        visited.add(node)
        in_stack.add(node)
        path.append(node)

        for neighbor in module_graph.get(node, set()):
            dfs(neighbor, path)

        path.pop()
        in_stack.discard(node)

    for module in all_modules:
        if module not in visited:
            dfs(module, [])

    for cycle in cycles[:5]:  # Limit to 5 cycles to avoid noise
        cycle_str = " → ".join(cycle)
        violations.append(
            f"  CYCLE: {cycle_str} — circular dependency detected. "
            f"Extract shared code into a separate module to break the cycle."
        )


def check_unwired_routes(files: list[Path], project_dir: Path) -> None:
    """CHECK D: Find route handlers in files that aren't registered."""
    # Find files with route decorators
    route_files: list[tuple[Path, list[tuple[str, int]]]] = []
    for filepath in files:
        routes = has_route_decorators(filepath)
        if routes:
            route_files.append((filepath, routes))

    if not route_files:
        return

    # Find the main app file (look for app creation or include_router calls)
    all_sources: dict[Path, str] = {}
    for f in files:
        try:
            all_sources[f] = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

    for filepath, routes in route_files:
        module_name = filepath.stem
        # Check if this file's router/module is referenced in any other file
        referenced = False
        for other_path, source in all_sources.items():
            if other_path == filepath:
                continue
            if module_name in source:
                referenced = True
                break

        if not referenced:
            rel = filepath.relative_to(REPO_ROOT)
            route_names = ", ".join(f"{name}()" for name, _ in routes[:3])
            violations.append(
                f"  UNWIRED: {rel} defines routes ({route_names}) but is never "
                f"imported or registered with the app. Add it to your router includes."
            )


def main() -> int:
    project_dir = find_project_dir()

    if project_dir is None:
        print("[B8] Wiring check: no Python source directory found (checked: backend/, src/, app/, lib/)")
        return 0  # Skip, not fail

    files = collect_python_files(project_dir)
    if not files:
        print("[B8] Wiring check: no Python files found")
        return 0

    # Build import graph
    import_graph: dict[str, set[str]] = {}
    for filepath in files:
        import_graph[str(filepath)] = extract_imports(filepath, project_dir)

    # Run all checks
    check_orphaned_files(files, project_dir, import_graph)
    check_circular_deps(files, project_dir, import_graph)
    check_unwired_routes(files, project_dir)
    # Note: check_unused_exports is expensive — only run if few files
    if len(files) <= 200:
        check_unused_exports(files, project_dir)
    else:
        print(f"  (Skipping unused export check — {len(files)} files exceeds threshold)")

    if violations:
        print(f"[B8] WIRING CHECK FAILED — {len(violations)} issue(s):\n")
        for v in violations:
            print(v)
        print(
            f"\nWiring violations mean code exists but isn't connected. "
            f"Tests can't catch what's never called."
        )
        return 1

    print("[B8] Wiring check passed — no orphans, no cycles, all routes wired")
    return 0


if __name__ == "__main__":
    sys.exit(main())
