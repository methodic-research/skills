#!/usr/bin/env python3
"""Static lint for the methodic skills — the cheap, no-secret CI tier.

Runs on every push. Two checks, no LLM and no network:

1. Every `skills/*/SKILL.md` has YAML frontmatter with `name` + `description`.
2. No **stale API surface** in any `skills/*/SKILL.md` — the retired scope/auth
   mechanisms must not creep back into what an agent executes (see
   `runes/chronicle/designs/auth.md` "API key authorization" + ui-scope.md).
   Forbidden: the ambient active-scope override (`active_org`,
   `X-Chronicle-Active-Owner`), the abandoned per-key "default org", and the
   removed `<capability>:<verb>` pseudo-actions (`session_search:read`,
   `report_writes:write`).

Exit non-zero on any violation, printing each with its file:line.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"

# (pattern, why) — substring match, case-sensitive where it matters.
FORBIDDEN: list[tuple[str, str]] = [
    ("active_org", "ambient active-scope override was retired; org is an explicit request field"),
    ("X-Chronicle-Active-Owner", "the active-owner header was retired (require_active_scope removed)"),
    ("session_search:read", "capability pseudo-actions were removed; searching is plain read"),
    ("report_writes:write", "capability pseudo-actions were removed; use a type-qualified write"),
    ("default org", "per-key 'default org' was abandoned; name the org on the call"),
    ("default_scope", "per-key default_scope was abandoned"),
]

# Scan only the SKILL.md files for stale surface — these are what an agent
# actually executes, so a forbidden string here means a skill would *use* the
# retired API. The top-level README is deliberately NOT scanned: its "Active
# scope" convention legitimately *names* the retired mechanisms to forbid them,
# which would be a false positive.
def _scan_targets() -> list[pathlib.Path]:
    return sorted(SKILLS_DIR.glob("*/SKILL.md"))


def _check_frontmatter(skill_md: pathlib.Path, errors: list[str]) -> None:
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        errors.append(f"{skill_md.relative_to(ROOT)}: missing YAML frontmatter (no leading '---')")
        return
    # Frontmatter is between the first two '---' fences.
    parts = text.split("---", 2)
    if len(parts) < 3:
        errors.append(f"{skill_md.relative_to(ROOT)}: unterminated frontmatter")
        return
    fm = parts[1]
    for field in ("name", "description"):
        if not re.search(rf"^{field}\s*:", fm, re.MULTILINE):
            errors.append(f"{skill_md.relative_to(ROOT)}: frontmatter missing '{field}:'")


def _check_stale_surface(path: pathlib.Path, errors: list[str]) -> None:
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        for needle, why in FORBIDDEN:
            if needle in line:
                errors.append(
                    f"{path.relative_to(ROOT)}:{i}: stale API surface '{needle}' — {why}"
                )


def main() -> int:
    if not SKILLS_DIR.is_dir():
        print(f"lint: no skills/ dir at {SKILLS_DIR}", file=sys.stderr)
        return 1

    errors: list[str] = []
    skill_mds = sorted(SKILLS_DIR.glob("*/SKILL.md"))
    if not skill_mds:
        errors.append("lint: no skills/*/SKILL.md found")
    for skill_md in skill_mds:
        _check_frontmatter(skill_md, errors)
    for target in _scan_targets():
        _check_stale_surface(target, errors)

    if errors:
        print("Skill lint FAILED:\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"Skill lint OK — {len(skill_mds)} skills, no stale API surface.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
