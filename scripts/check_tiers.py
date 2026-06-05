#!/usr/bin/env python3
"""check_tiers.py — Component D: the tier-audit gate.

Makes the guaranteed / proxied / hoped-for distinction a STANDING CHECK
rather than a one-time judgement buried in prose.

Every gate in this harness sits in one of three tiers:

  - guaranteed  — re-derives ground truth and BLOCKS on failure (a commit,
                  a tool call, a session stop). If the wiring that gives it
                  teeth is missing, the guarantee is a lie.
  - proxied     — checks an artifact that stands in for the real property
                  (e.g. "a test file exists" as a proxy for "a test was
                  seen failing first"). Useful, but foolable.
  - hoped-for   — a principle with no enforcing script. Documentation, not
                  a gate.

The registry (scripts/tier_registry.json) declares each gate, its file,
its tier, what ground truth it re-derives, and how it is wired in.

This gate verifies the declaration matches reality:

  1. Every declared file exists.
  2. Every "guaranteed" entry whose `wired_via` names a settings.json hook
     event (Stop / PreToolUse / PostToolUse / SubagentStop / ...) actually
     HAS a non-empty hook array for that event referencing its file. This
     catches the "Stop": [] class of bug — a guarantee declared on paper
     but wired to nothing.

In --strict mode the gate exits non-zero if any guaranteed entry is
missing its file OR its declared wiring. Default mode just reports.

Usage:
  python scripts/check_tiers.py                 # report, exit 0
  python scripts/check_tiers.py --strict        # enforce, exit non-zero on gaps
  python scripts/check_tiers.py --registry P    # override registry path (tests)
  python scripts/check_tiers.py --settings P    # override settings.json (tests)
  python scripts/check_tiers.py --repo-root P   # override repo root (tests)

Exit codes:
  0 = report-only, or --strict with no guaranteed-tier gaps
  1 = --strict and at least one guaranteed entry is missing file/wiring
  2 = usage / registry load error
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = REPO_ROOT / "scripts" / "tier_registry.json"
DEFAULT_SETTINGS = REPO_ROOT / ".claude" / "settings.json"

VALID_TIERS = {"guaranteed", "proxied", "hoped-for"}

# Hook events that can appear in .claude/settings.json under "hooks".
# A `wired_via` string mentioning one of these (case-insensitive) means the
# entry's teeth come from a settings.json hook and we must verify it.
SETTINGS_EVENTS = [
    "PreToolUse",
    "PostToolUse",
    "SubagentStop",
    "Stop",
    "PreCompact",
    "SessionStart",
]


# ─── Audit model ─────────────────────────────────────────────────────


@dataclass
class AuditEntry:
    name: str
    file: str
    tier: str
    rederives: str
    wired_via: str
    file_exists: bool
    # Wiring is "required" only for guaranteed entries whose wired_via names a
    # settings.json hook event.
    wiring_required: bool = False
    wiring_event: str | None = None
    wiring_ok: bool = True
    notes: list[str] = field(default_factory=list)

    @property
    def missing_file(self) -> bool:
        # An empty file path is legitimate for hoped-for principles with no
        # script. Only treat a *declared* file that is absent as missing.
        return bool(self.file) and not self.file_exists

    @property
    def missing_wiring(self) -> bool:
        return self.wiring_required and not self.wiring_ok

    @property
    def is_guaranteed_gap(self) -> bool:
        """A guaranteed entry that fails its own contract (file or wiring)."""
        if self.tier != "guaranteed":
            return False
        return self.missing_file or self.missing_wiring


# ─── Settings.json wiring inspection ─────────────────────────────────


def _detect_event(wired_via: str) -> str | None:
    """Return the settings.json hook event named in `wired_via`, if any.

    Longest match wins so 'SubagentStop' is not mistaken for 'Stop'.
    """
    text = wired_via.lower()
    if "settings.json" not in text and "settings" not in text:
        # The task wires guaranteed entries via phrases like
        # "'.claude/settings.json Stop'". If neither 'settings' nor a bare
        # event keyword is present, treat as a non-settings wiring.
        # We still allow a bare event keyword (e.g. "Stop hook") to count.
        pass
    for event in sorted(SETTINGS_EVENTS, key=len, reverse=True):
        if event.lower() in text:
            return event
    return None


def _load_settings(settings_path: Path) -> dict:
    try:
        return json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _event_references_file(settings: dict, event: str, file_rel: str) -> bool:
    """True if settings.json has a NON-EMPTY hook array for `event` that
    references `file_rel` (matched by basename, which is robust to the
    $CLAUDE_PROJECT_DIR prefix and path separators used in commands).
    """
    hooks = settings.get("hooks", {})
    event_list = hooks.get(event)
    if not isinstance(event_list, list) or not event_list:
        return False
    basename = Path(file_rel.replace("\\", "/")).name
    for group in event_list:
        if not isinstance(group, dict):
            continue
        for hook in group.get("hooks", []):
            command = hook.get("command", "") if isinstance(hook, dict) else ""
            if basename and basename in command.replace("\\", "/"):
                return True
    return False


# ─── Core audit ──────────────────────────────────────────────────────


def load_registry(registry_path: Path) -> list[dict]:
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("tier registry must be a JSON list of entries")
    return data


def audit(
    registry_path: Path,
    repo_root: Path | None = None,
    settings_path: Path | None = None,
) -> list[AuditEntry]:
    """Audit every registry entry against the filesystem and settings.json."""
    root = Path(repo_root) if repo_root else REPO_ROOT
    settings_p = Path(settings_path) if settings_path else DEFAULT_SETTINGS
    entries = load_registry(registry_path)
    settings = _load_settings(settings_p)

    results: list[AuditEntry] = []
    for raw in entries:
        name = raw.get("name", "<unnamed>")
        file_rel = raw.get("file", "") or ""
        tier = raw.get("tier", "")
        rederives = raw.get("rederives", "") or ""
        wired_via = raw.get("wired_via", "") or ""

        notes: list[str] = []
        if tier not in VALID_TIERS:
            notes.append(f"unknown tier {tier!r} (expected one of {sorted(VALID_TIERS)})")

        file_exists = bool(file_rel) and (root / file_rel).exists()

        entry = AuditEntry(
            name=name,
            file=file_rel,
            tier=tier,
            rederives=rederives,
            wired_via=wired_via,
            file_exists=file_exists,
            notes=notes,
        )

        # Wiring check applies only to guaranteed entries whose wired_via
        # names a settings.json hook event.
        if tier == "guaranteed":
            event = _detect_event(wired_via)
            if event is not None:
                entry.wiring_required = True
                entry.wiring_event = event
                entry.wiring_ok = _event_references_file(settings, event, file_rel)
                if not entry.wiring_ok:
                    entry.notes.append(
                        f'declared wiring via "{event}" is absent or empty in settings.json'
                    )

        results.append(entry)

    return results


# ─── Reporting ───────────────────────────────────────────────────────


def _status_label(entry: AuditEntry) -> str:
    flags = []
    if entry.missing_file:
        flags.append("MISSING FILE")
    if entry.missing_wiring:
        flags.append(f"UNWIRED ({entry.wiring_event})")
    if not flags and not entry.file and entry.tier == "hoped-for":
        return "ok (no script — principle only)"
    if not flags:
        if entry.wiring_required:
            return f"ok (wired via {entry.wiring_event})"
        return "ok"
    return " + ".join(flags)


def render(results: list[AuditEntry], strict: bool) -> None:
    print("=" * 64)
    print("TIER AUDIT — guaranteed / proxied / hoped-for")
    print("=" * 64)

    for tier in ("guaranteed", "proxied", "hoped-for"):
        group = [e for e in results if e.tier == tier]
        print(f"\n[{tier}]  ({len(group)})")
        if not group:
            print("  (none)")
            continue
        for e in group:
            print(f"  - {e.name}: {_status_label(e)}")
            if e.file:
                print(f"      file: {e.file}")
            if e.rederives:
                print(f"      rederives: {e.rederives}")
            if e.wired_via:
                print(f"      wired_via: {e.wired_via}")
            for note in e.notes:
                if "unknown tier" in note:
                    print(f"      NOTE: {note}")

    # Any entries with an unrecognised tier land outside the three groups.
    orphan = [e for e in results if e.tier not in VALID_TIERS]
    if orphan:
        print(f"\n[unknown tier]  ({len(orphan)})")
        for e in orphan:
            print(f"  - {e.name}: tier={e.tier!r} ({_status_label(e)})")

    gaps = [e for e in results if e.is_guaranteed_gap]
    print("\n" + "-" * 64)
    print(f"Totals: {len(results)} entries | guaranteed-tier gaps: {len(gaps)}")
    if gaps:
        print("Guaranteed-tier gaps (these break the guarantee):")
        for e in gaps:
            print(f"  ! {e.name}: {_status_label(e)}")
    if strict:
        print(f"Mode: STRICT — exit {'1 (gaps present)' if gaps else '0 (clean)'}")
    else:
        print("Mode: report-only — exit 0 (run with --strict to enforce)")
    print("-" * 64)


# ─── CLI ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Component D: tier-audit gate")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any guaranteed entry is missing its file or wiring.",
    )
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_REGISTRY),
        help="Path to the tier registry JSON (default: scripts/tier_registry.json).",
    )
    parser.add_argument(
        "--settings",
        default=str(DEFAULT_SETTINGS),
        help="Path to .claude/settings.json (default: repo .claude/settings.json).",
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Repo root for resolving registry file paths (default: detected).",
    )
    args = parser.parse_args(argv)

    registry_path = Path(args.registry)
    if not registry_path.exists():
        print(f"ERROR: registry not found at {registry_path}", file=sys.stderr)
        return 2

    try:
        results = audit(
            registry_path,
            repo_root=Path(args.repo_root),
            settings_path=Path(args.settings),
        )
    except (ValueError, json.JSONDecodeError) as e:
        print(f"ERROR: failed to load registry: {e}", file=sys.stderr)
        return 2

    render(results, strict=args.strict)

    if args.strict:
        gaps = [e for e in results if e.is_guaranteed_gap]
        return 1 if gaps else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
