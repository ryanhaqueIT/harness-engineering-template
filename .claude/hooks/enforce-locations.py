#!/usr/bin/env python3
"""PreToolUse hook: blocks writes to wrong file locations.

Enforces that plans go in docs/exec-plans/ and specs go in docs/product-specs/.
Prevents agents from following competing instruction sources that suggest
different locations (e.g., superpowers skills putting plans elsewhere).
"""

import json
import re
import sys


def main() -> int:
    input_data = json.load(sys.stdin)
    tool_input = input_data.get("tool_input", {})

    # Extract file path from Write/Edit tool input
    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    # Normalize path separators
    file_path_normalized = file_path.replace("\\", "/")

    # Rule 1: Plans/exec-plans must go in docs/exec-plans/
    if re.search(r"(exec.?plan|plan.?of.?work)", file_path_normalized, re.IGNORECASE):
        if "/exec-plans/" not in file_path_normalized and file_path_normalized.endswith(".md"):
            # Allow PLANS.md at root (the template file)
            if not file_path_normalized.endswith("PLANS.md"):
                print(json.dumps({
                    "decision": "block",
                    "reason": (
                        f"LOCATION BLOCKED: ExecPlans must go in docs/exec-plans/active/, "
                        f"not {file_path}. See AGENTS.md section 'ExecPlans'. "
                        f"AGENTS.md is the governing authority for this repo."
                    )
                }))
                sys.exit(0)

    # Rule 2: Product specs must go in docs/product-specs/
    if re.search(r"(product.?spec|prd|requirement)", file_path_normalized, re.IGNORECASE):
        if "/product-specs/" not in file_path_normalized and file_path_normalized.endswith(".md"):
            print(json.dumps({
                "decision": "block",
                "reason": (
                    f"LOCATION BLOCKED: Product specs must go in docs/product-specs/, "
                    f"not {file_path}. See AGENTS.md section 'Progressive Disclosure'. "
                    f"AGENTS.md is the governing authority for this repo."
                )
            }))
            sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
