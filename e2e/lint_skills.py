#!/usr/bin/env python3
"""Static lint for the methodic skills — the cheap, no-secret CI tier.

Runs on every push. Two checks, no LLM and no network:

1. Every `skills/*/SKILL.md` has YAML frontmatter with `name` + `description`.
2. The Codex package mirror under `plugins/chronicle` is in sync for skills and
   the MCP launcher files.
3. No **stale API surface** in any `skills/*/SKILL.md` — the retired scope/auth
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
CODEX_PLUGIN_DIR = ROOT / "plugins" / "chronicle"
CODEX_SKILLS_DIR = CODEX_PLUGIN_DIR / "skills"
CODEX_MCP_DIR = CODEX_PLUGIN_DIR / "mcp"

# (pattern, why) — regex per line, case-sensitive where it matters. Patterns
# are word-bounded where a *sanctioned* phrase shares a prefix with a retired
# one: the recorded `organization_id:` in ~/.methodic/config.yaml is
# legitimately described as a "default organization" (README "Organization
# scope" convention), and must not trip the rule for the retired per-key
# "default org".
FORBIDDEN: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"active_org"), "ambient active-scope override was retired; org is an explicit request field"),
    (re.compile(r"X-Chronicle-Active-Owner"), "the active-owner header was retired (require_active_scope removed)"),
    (re.compile(r"session_search:read"), "capability pseudo-actions were removed; searching is plain read"),
    (re.compile(r"report_writes:write"), "capability pseudo-actions were removed; use a type-qualified write"),
    (re.compile(r"\bdefault org\b"), "per-key 'default org' was abandoned; name the org on the call (the recorded config.yaml organization_id is the one sanctioned default)"),
    (re.compile(r"default_scope"), "per-key default_scope was abandoned"),
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
        for pat, why in FORBIDDEN:
            if pat.search(line):
                errors.append(
                    f"{path.relative_to(ROOT)}:{i}: stale API surface '{pat.pattern}' — {why}"
                )


def _check_codex_mirror(errors: list[str]) -> None:
    """The Codex marketplace requires a plugin subdirectory with real files.

    Keep it byte-for-byte mirrored from the canonical root `skills/` and `mcp/`
    directories so Claude Code and Codex execute the same instructions/tools.
    """
    if not CODEX_PLUGIN_DIR.is_dir():
        errors.append("codex mirror missing: plugins/chronicle")
        return
    if not CODEX_SKILLS_DIR.is_dir():
        errors.append("codex mirror missing: plugins/chronicle/skills")
        return
    if not CODEX_MCP_DIR.is_dir():
        errors.append("codex mirror missing: plugins/chronicle/mcp")
        return

    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        mirrored = CODEX_SKILLS_DIR / skill_md.parent.name / "SKILL.md"
        if not mirrored.is_file():
            errors.append(f"codex mirror missing {mirrored.relative_to(ROOT)}")
            continue
        if skill_md.read_bytes() != mirrored.read_bytes():
            errors.append(
                "codex mirror drift: "
                f"{skill_md.relative_to(ROOT)} != {mirrored.relative_to(ROOT)}"
            )

    root_skill_names = {p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md")}
    mirror_skill_names = {
        p.parent.name for p in CODEX_SKILLS_DIR.glob("*/SKILL.md")
    }
    for extra in sorted(mirror_skill_names - root_skill_names):
        errors.append(f"codex mirror has extra skill plugins/chronicle/skills/{extra}")

    for rel in ("server.js", "server.test.js", "PLAN.md"):
        canonical = ROOT / "mcp" / rel
        mirrored = CODEX_MCP_DIR / rel
        if not mirrored.is_file():
            errors.append(f"codex mirror missing {mirrored.relative_to(ROOT)}")
            continue
        if canonical.read_bytes() != mirrored.read_bytes():
            errors.append(
                "codex mirror drift: "
                f"{canonical.relative_to(ROOT)} != {mirrored.relative_to(ROOT)}"
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
    _check_codex_mirror(errors)
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
