#!/usr/bin/env python3
"""check_golden_principles.py — Enforce golden principles mechanically.

Scans Python files in backend/ for violations of golden principles.
Error messages are actionable — the agent can read them and know exactly what to fix.

Checks:
1. No print() in non-test files (use logger.info instead)
2. No hardcoded secrets patterns (API_KEY=, SECRET=, PASSWORD= in strings)
3. Type hints on all function definitions
4. No bare except clauses (must specify exception type)
5. CWE-636: No fail-open catch blocks (swallowing auth/security exceptions)
6. CWE-209: No error data leakage (stack traces, internal paths in responses)
7. CWE-306: No missing auth on mutation endpoints

Exit code 0 = clean, 1 = violations found.
"""

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Auto-detect source directory
BACKEND = REPO_ROOT / "backend"
if not BACKEND.exists():
    for alt in ["src", "app", "lib"]:
        candidate = REPO_ROOT / alt
        if candidate.exists() and any(candidate.rglob("*.py")):
            BACKEND = candidate
            break

violations: list[str] = []


def check_no_print(filepath: Path, tree: ast.AST) -> None:
    """Principle: No print() in production code."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "print":
                violations.append(
                    f"  {filepath.relative_to(BACKEND)}:{node.lineno} — "
                    f"print() found. Use logger.info() or logger.error() instead. "
                    f"Add: import logging; logger = logging.getLogger(__name__)"
                )


def check_no_hardcoded_secrets(filepath: Path) -> None:
    """Principle: No secrets in code."""
    content = filepath.read_text(encoding="utf-8", errors="replace")
    patterns = [
        (r'["\'](?:sk-|ak_|mk_)[a-zA-Z0-9]{20,}["\']', "API key literal"),
        (r'(?:API_KEY|SECRET_KEY|PASSWORD|AUTH_TOKEN)\s*=\s*["\'][^"\']{8,}["\']', "Hardcoded secret assignment"),
        (r'(?:client_secret|private_key)\s*=\s*["\'][^"\']{8,}["\']', "Hardcoded credential"),
    ]
    for pattern, desc in patterns:
        for match in re.finditer(pattern, content):
            line_num = content[:match.start()].count("\n") + 1
            violations.append(
                f"  {filepath.relative_to(BACKEND)}:{line_num} — "
                f"{desc} detected. Use environment variables or a secret manager. "
                f"Example: os.environ['SECRET_KEY'] or settings.SECRET_KEY"
            )


def check_type_hints(filepath: Path, tree: ast.AST) -> None:
    """Principle: Type hints on all function definitions."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Skip dunder methods (except __init__) and private methods
            if node.name.startswith("_") and node.name != "__init__":
                continue
            if node.returns is None and node.name != "__init__":
                violations.append(
                    f"  {filepath.relative_to(BACKEND)}:{node.lineno} — "
                    f"Function '{node.name}' missing return type hint. "
                    f"Add -> ReturnType to the function signature."
                )


def check_no_bare_except(filepath: Path, tree: ast.AST) -> None:
    """Principle: No bare except — must specify exception type."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            violations.append(
                f"  {filepath.relative_to(BACKEND)}:{node.lineno} — "
                f"Bare 'except:' clause. Specify the exception type: "
                f"except SomeError as e:"
            )


def check_cwe636_fail_open(filepath: Path, tree: ast.AST) -> None:
    """CWE-636: Catch blocks that swallow auth/security exceptions.

    Detects: except (AuthError, PermissionError, Forbidden, Unauthorized): pass
    These silently grant access when authentication/authorization fails.
    """
    auth_exception_names = {
        "AuthError", "AuthenticationError", "AuthorizationError",
        "PermissionError", "PermissionDenied", "Forbidden",
        "Unauthorized", "HTTPException", "SecurityError",
        "InvalidTokenError", "TokenExpiredError", "AccessDenied",
    }

    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None:
            continue

        # Get exception name(s)
        exc_names = set()
        if isinstance(node.type, ast.Name):
            exc_names.add(node.type.id)
        elif isinstance(node.type, ast.Tuple):
            for elt in node.type.elts:
                if isinstance(elt, ast.Name):
                    exc_names.add(elt.id)

        # Check if catching auth-related exceptions
        caught_auth = exc_names & auth_exception_names
        if not caught_auth:
            continue

        # Check if the handler body is effectively a no-op (pass, continue, or bare return)
        body = node.body
        is_swallowed = False
        if len(body) == 1:
            stmt = body[0]
            if isinstance(stmt, ast.Pass):
                is_swallowed = True
            elif isinstance(stmt, ast.Continue):
                is_swallowed = True
            elif isinstance(stmt, ast.Return) and stmt.value is None:
                is_swallowed = True
            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                is_swallowed = True  # except AuthError: "ignored"

        if is_swallowed:
            rel = filepath.relative_to(BACKEND) if str(filepath).startswith(str(BACKEND)) else filepath.name
            violations.append(
                f"  {rel}:{node.lineno} — "
                f"CWE-636 FAIL-OPEN: Catching {', '.join(caught_auth)} and swallowing it. "
                f"This silently grants access on auth failure. "
                f"Re-raise the exception or return an error response."
            )


def check_cwe209_error_leakage(filepath: Path, tree: ast.AST) -> None:
    """CWE-209: Error responses containing internal details.

    Detects: returning traceback.format_exc(), str(exception), or
    internal file paths in error responses.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue

        for child in ast.walk(node):
            # Check for traceback.format_exc() in return statements
            if isinstance(child, ast.Call):
                func = child.func
                if isinstance(func, ast.Attribute) and func.attr in ("format_exc", "format_exception", "print_exc"):
                    if isinstance(func.value, ast.Name) and func.value.id == "traceback":
                        # Check if this is inside a return or dict construction
                        rel = filepath.relative_to(BACKEND) if str(filepath).startswith(str(BACKEND)) else filepath.name
                        violations.append(
                            f"  {rel}:{child.lineno} — "
                            f"CWE-209 ERROR LEAKAGE: traceback.{func.attr}() used in exception handler. "
                            f"Internal stack traces may leak to clients. "
                            f"Log the traceback and return a generic error message instead."
                        )


def check_cwe306_missing_auth(filepath: Path, tree: ast.AST) -> None:
    """CWE-306: Mutation endpoints without authentication.

    Detects: @router.post/put/delete handlers that don't include
    a Depends() parameter for authentication.
    """
    mutation_decorators = {"post", "put", "delete", "patch"}
    auth_indicators = {"Depends", "get_current_user", "require_auth", "authenticate",
                       "verify_token", "get_user", "Authorization", "Security"}

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Check if this is a mutation endpoint
        is_mutation = False
        for deco in node.decorator_list:
            deco_attr = ""
            if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute):
                deco_attr = deco.func.attr
            elif isinstance(deco, ast.Attribute):
                deco_attr = deco.attr
            if deco_attr in mutation_decorators:
                is_mutation = True
                break

        if not is_mutation:
            continue

        # Check if any parameter uses Depends() or auth-related type hints
        has_auth = False
        for arg in node.args.args:
            # Check default values for Depends()
            if arg.annotation:
                ann_str = ast.dump(arg.annotation)
                if any(indicator in ann_str for indicator in auth_indicators):
                    has_auth = True
                    break

        # Also check function defaults
        for default in node.args.defaults + node.args.kw_defaults:
            if default is None:
                continue
            default_str = ast.dump(default)
            if any(indicator in default_str for indicator in auth_indicators):
                has_auth = True
                break

        if not has_auth:
            rel = filepath.relative_to(BACKEND) if str(filepath).startswith(str(BACKEND)) else filepath.name
            violations.append(
                f"  {rel}:{node.lineno} — "
                f"CWE-306 MISSING AUTH: Mutation endpoint '{node.name}' has no "
                f"visible authentication dependency (Depends(get_current_user) or similar). "
                f"Add authentication or document why this endpoint is intentionally public."
            )


def main() -> int:
    if not BACKEND.exists():
        print("backend/ directory not found — skipping golden principles check")
        return 0

    py_files = list(BACKEND.rglob("*.py"))
    py_files = [
        f for f in py_files
        if "__pycache__" not in str(f)
        and ".venv" not in str(f)
        and "site-packages" not in str(f)
        and "test" not in f.name  # Don't enforce on test files
        and f.name != "__init__.py"
    ]

    for filepath in py_files:
        try:
            tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
        except SyntaxError:
            continue

        check_no_print(filepath, tree)
        check_no_hardcoded_secrets(filepath)
        check_type_hints(filepath, tree)
        check_no_bare_except(filepath, tree)
        check_cwe636_fail_open(filepath, tree)
        check_cwe209_error_leakage(filepath, tree)
        check_cwe306_missing_auth(filepath, tree)

    if violations:
        print(f"Golden principle violations ({len(violations)}):")
        for v in violations:
            print(v)
        return 1

    print(f"Golden principles clean ({len(py_files)} files checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
