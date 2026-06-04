"""Build AgenticPR-Bench-mini layer 1.1: weak spec extraction.

For each PR in layer 1, construct a minimal spec from the PR metadata
(title + body excerpt) so HarnessCI can produce meaningful decisions
instead of INSUFFICIENT_INFORMATION.

Spec format per PR (YAML-ish plain text):
    ## Goal
    <PR title>
    ## Motivation
    <body excerpt first 400 chars, or 'No description provided.'>
    ## Acceptance
    - Code changes are syntactically valid
    - Changes are consistent with the task description
    - No obvious security or correctness regressions

Output:
    datasets/agenticpr-bench-mini/raw/layer1.1_specs.jsonl
        (one JSON per line, keys: dataset_id, spec_text)

No API calls — pure text construction from existing manifest.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "agenticpr-bench-mini"
MANIFEST = DATASET_DIR / "raw" / "layer1_real_github_prs.jsonl"
OUTPUT = DATASET_DIR / "raw" / "layer1.1_specs.jsonl"

# Patterns that indicate a weak/no-op spec — these don't tell us what
# the PR is actually doing beyond the title.
WEAK_TITLE_PATTERNS = re.compile(
    r"^(update|fix|patch|bump|typo|cleanup|refactor|dry run|sync)\s*[:\s]",
    re.IGNORECASE,
)


def extract_issue_refs(text: str) -> list[str]:
    """Extract 'Fixes #N' / 'Closes #N' patterns from full body text."""
    return re.findall(r"(?:fixes|closes|resolves|fix|close)\s+#(\d+)", text, re.IGNORECASE)


def classify_pr_type(title: str) -> str:
    """Infer the type of change from the title."""
    t = title.lower()
    if any(k in t for k in ["feat", "feature", "add", "new"]):
        return "feature"
    if any(k in t for k in ["fix", "bug", "patch"]):
        return "bugfix"
    if any(k in t for k in ["doc", "readme", "changelog"]):
        return "docs"
    if any(k in t for k in ["test", "spec"]):
        return "test"
    if any(k in t for k in ["config", "ci", "workflow", "dockerfile"]):
        return "infrastructure"
    if any(k in t for k in ["deprecat", "remov", "breaking"]):
        return "breaking"
    if any(k in t for k in ["refactor", "restructur", "clean"]):
        return "refactor"
    return "unknown"


def build_weak_spec(record: dict) -> str:
    """Construct a minimal spec from PR metadata.

    Uses title as task statement and body_excerpt as motivation.
    Adds a generic acceptance checklist for diff-based verification.
    """
    title = record.get("title", "Untitled PR").strip()
    excerpt = record.get("body_excerpt", "").strip()
    pr_type = classify_pr_type(title)

    spec_parts: list[str] = []

    spec_parts.append("## Goal")
    spec_parts.append(title)

    spec_parts.append("\n## Change Type")
    spec_parts.append(pr_type)

    spec_parts.append("\n## Motivation")
    if excerpt:
        spec_parts.append(excerpt[:400])
    else:
        spec_parts.append("No description provided.")

    # Diff-level acceptance criteria (always applicable)
    spec_parts.append("\n## Acceptance Criteria")
    spec_parts.append("- Changes are syntactically valid for the target language")
    spec_parts.append("- No obvious security vulnerabilities introduced")
    spec_parts.append("- No test coverage removed without replacement")
    spec_parts.append("- No hardcoded secrets or credentials added")
    spec_parts.append("- Changes are consistent with the task description")
    spec_parts.append("- No breaking changes unless explicitly stated")
    spec_parts.append("- Configuration changes are reversible")

    # Type-specific guidance
    if pr_type == "feature":
        spec_parts.append("- New functionality is testable")
    elif pr_type == "bugfix":
        spec_parts.append("- Fix addresses the root cause, not only symptoms")
    elif pr_type == "docs":
        spec_parts.append("- Documentation is accurate and complete")

    return "\n".join(spec_parts)


def main() -> int:
    if not MANIFEST.exists():
        print(f"ERROR: Layer 1 manifest not found: {MANIFEST}")
        return 1

    records = []
    with MANIFEST.open(encoding="utf-8", errors="replace") as fh:
        for line_num, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"WARNING: Skipping line {line_num} — {exc}")
                continue

    print(f"Processing {len(records)} PRs...")

    specs: list[dict] = []
    weak_count = 0
    for record in records:
        dataset_id = record.get("dataset_id", f"unknown-{record.get('number', '?')}")
        spec_text = build_weak_spec(record)
        specs.append(
            {
                "dataset_id": dataset_id,
                "spec_text": spec_text,
                "pr_title": record.get("title", ""),
                "pr_type": classify_pr_type(record.get("title", "")),
                "body_chars": record.get("body_chars", 0),
                "human_label": record.get("human_label", ""),
            }
        )
        # Count titles that are too generic (likely weak specs)
        if WEAK_TITLE_PATTERNS.match(record.get("title", "")):
            weak_count += 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as fh:
        for spec in specs:
            fh.write(json.dumps(spec, ensure_ascii=False) + "\n")

    print(f"Written: {OUTPUT}")
    print(f"Total specs: {len(specs)}")
    print(f"Weak spec titles (generic): {weak_count}")
    print("Spec length stats (chars):")
    lengths = [len(s["spec_text"]) for s in specs]
    lengths.sort()
    print(
        f"  min={lengths[0]}, p25={lengths[len(lengths) // 4]}, "
        f"median={lengths[len(lengths) // 2]}, p75={lengths[3 * len(lengths) // 4]}, "
        f"max={lengths[-1]}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
