#!/usr/bin/env python3
"""SessionStart hook: recover from compaction using continuation snapshot.

Reads .harness/continuation.md and injects it into context if fresh (< 2 hours).
Stale snapshots (> 2 hours) are ignored — too old to be useful.

This pairs with pre-compact.sh which writes the snapshot before context loss.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONTINUATION = REPO_ROOT / ".harness" / "continuation.md"

# Maximum age of a snapshot before it's considered stale
MAX_AGE_HOURS = 2


def main() -> int:
    if not CONTINUATION.exists():
        return 0

    content = CONTINUATION.read_text(encoding="utf-8", errors="replace")
    if not content.strip():
        return 0

    # Extract timestamp from "Snapshot: {ISO 8601}"
    match = re.search(r"Snapshot:\s*(.+)", content)
    if not match:
        # No timestamp — can't determine freshness, skip
        return 0

    try:
        snapshot_time = datetime.fromisoformat(match.group(1).strip().replace("Z", "+00:00"))
    except ValueError:
        return 0

    now = datetime.now(timezone.utc)
    age_hours = (now - snapshot_time).total_seconds() / 3600

    if age_hours > MAX_AGE_HOURS:
        # Stale snapshot — ignore
        print(
            f"Found continuation snapshot from {age_hours:.1f} hours ago "
            f"(> {MAX_AGE_HOURS}h threshold) — ignoring stale snapshot.",
            file=sys.stderr,
        )
        return 0

    # Fresh snapshot — inject into context
    age_min = int(age_hours * 60)

    # Extract correction summary if present
    corrections = ""
    corr_match = re.search(
        r"## Correction Summary\s*\n(.*?)(?:\n## |\Z)",
        content,
        re.DOTALL,
    )
    if corr_match:
        corrections = corr_match.group(1).strip()

    output = [
        f"📋 RESUMING FROM CONTINUATION SNAPSHOT ({age_min} minutes old)",
        "",
        "The following context was saved before your last context compaction:",
        "",
        content,
        "",
    ]

    if corrections:
        output.extend([
            "⚠ QUALITY CORRECTIONS (avoid repeating these patterns):",
            corrections,
            "",
        ])

    output.append(
        "Resume from the 'Next Steps' section above. "
        "Do NOT restart from scratch — continue where you left off."
    )

    print("\n".join(output), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
