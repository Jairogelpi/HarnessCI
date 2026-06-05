"""Mine Layer 2 task specs using Groq and re-evaluate.

For each Layer 2 task, a Groq-generated spec replaces the human-written YAML spec.
The mined spec includes concrete file patterns, entities, and invariants —
enabling SpecVerifier and DriftMatcher to work with real data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYER2_DIR = ROOT / "datasets/agenticpr-bench-mini/layer2"
TASKS_DIR = LAYER2_DIR / "tasks"
MANIFEST_PATH = LAYER2_DIR / "manifest.jsonl"
MINED_SPECS_PATH = LAYER2_DIR / "results/mined_specs.json"

sys.path.insert(0, str(ROOT / "src"))


def load_tasks() -> list[dict]:
    tasks = []
    for yaml_file in sorted(TASKS_DIR.glob("task_*.yaml")):
        import yaml

        with yaml_file.open(encoding="utf-8") as fh:
            data = list(yaml.safe_load_all(fh))[0]
        if isinstance(data, list):
            tasks.extend(data)
        else:
            tasks.append(data)
    return tasks


def mined_spec_to_markdown(spec: dict) -> str:
    """Convert mined spec dict to markdown format that parse_spec_text understands."""
    parts: list[str] = []

    domain = spec.get("domain", "")
    if domain:
        parts.append(f"## Goal\n{domain}")

    entities = spec.get("entities", [])
    if entities:
        parts.append("## Acceptance Criteria")
        for e in entities:
            files = ", ".join(str(f) for f in e.get("files", []))
            invs = ", ".join(str(i) for i in e.get("invariants", []))
            parts.append(f"- {e.get('name', 'entity')}: {files}" + (f" ({invs})" if invs else ""))

    forbidden = spec.get("forbidden_paths", [])
    if forbidden:
        parts.append("## Out of Scope")
        for fp in forbidden:
            parts.append(f"- {fp}")

    arch = spec.get("architecture", {})
    if arch.get("layers"):
        parts.append("## Expected Scope\nmedium_change")

    return "\n".join(parts).strip() + "\n"


def build_mining_prompt(task: dict, acceptable_patch: str) -> str:
    """Build a mining prompt from a Layer 2 task."""
    spec = task.get("spec", {})
    criteria = spec.get("acceptance_criteria", [])
    criteria_str = ", ".join(str(c) for c in criteria)
    out_of_scope = spec.get("out_of_scope", [])
    oos_str = ", ".join(str(o) for o in out_of_scope)
    expected_files = task.get("expected_touched_files", [])
    ef_str = ", ".join(str(f) for f in expected_files)

    return f"""Analyze this code change and extract a structured specification.

Task: {task.get("title", "")}
Repository: {task.get("repository_slice", "")}
Goal: {spec.get("goal", "")}
Acceptance Criteria: {criteria_str}
Out of Scope: {oos_str}
Expected files: {ef_str}
Change type: {task.get("change_type", "")}
Expected scope: {task.get("expected_scope", "")}

Acceptable patch:
{acceptable_patch[:3000]}

Extract JSON with exact keys: domain, entities (name/files/invariants),
conventions (naming/api/auth), forbidden_paths (concrete file paths),
allowed_test_patterns, architecture (layers/dependencies),
security_invariants, summary_md.
Output ONLY the JSON. No markdown, no explanation."""


def mine_task_spec(task: dict, client) -> tuple[dict, str]:
    """Mine a spec for a single task using Groq."""
    from harnessci.spec.miner import MINING_SYSTEM

    patch_dir = LAYER2_DIR / "patches"
    task_id = task["id"]

    # Read the acceptable variant patch for context
    acceptable_patch = ""
    patch_files = sorted(patch_dir.glob(f"{task_id}_acceptable*.diff"))
    if patch_files:
        acceptable_patch = patch_files[0].read_text(encoding="utf-8", errors="replace")

    prompt = build_mining_prompt(task, acceptable_patch)
    response = client.complete(prompt, system=MINING_SYSTEM)

    # Parse response
    try:
        text = response.strip()
        if text.startswith("```"):
            for marker in ["```json", "```"]:
                if text.startswith(marker):
                    text = text[len(marker) :]
                    text = text.rstrip("`").strip()
        spec = json.loads(text)
        summary = spec.pop("summary_md", "")
        return spec, summary
    except (json.JSONDecodeError, KeyError):
        return {"domain": str(task.get("title", ""))}, ""


def mine_all_tasks(tasks: list[dict], api_key: str) -> dict[str, dict]:
    """Mine specs for all tasks."""
    from harnessci.spec.miner import GroqClient

    client = GroqClient(api_key)
    if not client.available:
        print("ERROR: Groq client not available")
        return {}

    mined_specs: dict[str, dict] = {}
    for task in tasks:
        tid = task["id"]
        title = task.get("title", tid)
        print(f"  Mining spec for {tid}: {title[:60]}...")
        try:
            spec, summary = mine_task_spec(task, client)
            mined_specs[tid] = {"spec": spec, "summary": summary, "title": title}
            print(f"    Domain: {spec.get('domain', 'unknown')}")
            print(f"    Entities: {len(spec.get('entities', []))}")
            print(f"    Forbidden paths: {spec.get('forbidden_paths', [])}")
        except Exception as exc:  # noqa: BLE001
            print(f"    ERROR: {exc}")
            mined_specs[tid] = {"spec": {"domain": title}, "summary": "", "title": title}

    return mined_specs


def main() -> int:
    import os

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        print("ERROR: GROQ_API_KEY not set")
        return 1

    print("Loading tasks...")
    tasks = load_tasks()
    print(f"  {len(tasks)} tasks loaded")

    print("Mining specs with Groq...")
    mined = mine_all_tasks(tasks, api_key)

    # Save mined specs
    MINED_SPECS_PATH.parent.mkdir(parents=True, exist_ok=True)
    MINED_SPECS_PATH.write_text(json.dumps(mined, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Mined specs saved to {MINED_SPECS_PATH}")
    print(f"  {len(mined)} tasks with mined specs")

    # Now re-evaluate with mined specs
    print("Re-evaluating with mined specs...")
    from harnessci.audit import run_audit_from_diff_text

    manifest = []
    with MANIFEST_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            manifest.append(json.loads(line.strip()))

    results = []
    for case in manifest:
        task_id = case.get("task_id", "")
        case_id = case.get("case_id", "")
        patch_path = LAYER2_DIR / str(case.get("patch_path", ""))

        if not patch_path.exists():
            print(f"  WARNING: patch not found for {case_id}")
            continue

        diff_text = patch_path.read_text(encoding="utf-8", errors="replace")

        # Build markdown-compatible spec text from mined spec
        task_spec = mined.get(task_id, {}).get("spec", {})
        spec_text = mined_spec_to_markdown(task_spec)

        report = run_audit_from_diff_text(diff_text, spec_text=spec_text)

        decision = report.decision.value
        primary_label = str(case.get("primary_label", ""))
        strict_correct = _is_strict_correct(primary_label, decision)
        unsafe_detected = _is_unsafe_detected(primary_label, decision)
        unacceptable_block = (
            decision in ("REVIEW_REQUIRED", "BLOCK") and primary_label == "UNACCEPTABLE"
        )

        results.append(
            {
                "case_id": case_id,
                "task_id": task_id,
                "variant": case.get("variant", ""),
                "primary_label": primary_label,
                "harnessci_decision": decision,
                "strict_correct": strict_correct,
                "unsafe_detected": unsafe_detected,
                "unacceptable_block": unacceptable_block,
                "overall_agentic_risk": report.overall_agentic_risk,
                "finding_count": len(report.findings),
                "top_findings": [f.message for f in report.findings[:3]],
            }
        )

    # Compute metrics
    total = len(results)
    strict = sum(1 for r in results if r["strict_correct"])
    unsafe = [r for r in results if r["primary_label"] != "ACCEPTABLE"]
    unsafe_detected = sum(1 for r in unsafe if r["unsafe_detected"])
    unacceptable = [r for r in results if r["primary_label"] == "UNACCEPTABLE"]
    unacc_block = sum(1 for r in unacceptable if r["unacceptable_block"])

    decision_counts: dict[str, int] = {}
    for r in results:
        decision_counts[r["harnessci_decision"]] = (
            decision_counts.get(r["harnessci_decision"], 0) + 1
        )

    print(f"\nMetrics ({total} cases with Groq-mined specs):")
    print(f"  strict_accuracy={strict / total:.4f}")
    print(
        f"  unsafe_detection_recall={unsafe_detected}/{len(unsafe)}="
        f"{unsafe_detected / len(unsafe):.4f}"
    )
    print(
        f"  unacceptable_block_recall={unacc_block}/{len(unacceptable)}="
        f"{unacc_block / len(unacceptable):.4f}"
    )
    print(f"  decision_distribution={decision_counts}")

    # Compare with old
    old_strict = 17
    change = strict - old_strict
    print("\nVs old (diff-only):")
    print(
        f"  strict_accuracy: {old_strict}/{total}={old_strict / total:.4f}"
        f" -> {strict}/{total}={strict / total:.4f} (delta={change:+d})"
    )
    if change > 0:
        print(f"  Improved by {change} cases!")

    # Save results
    out_path = LAYER2_DIR / "results/layer2_groq_results.json"
    out_path.write_text(
        json.dumps(
            {
                "metrics": {
                    "total_cases": total,
                    "strict_accuracy": strict / total if total else 0,
                    "unsafe_detection_recall": unsafe_detected / len(unsafe) if unsafe else 0,
                    "unacceptable_block_recall": unacc_block / len(unacceptable)
                    if unacceptable
                    else 0,
                    "decision_distribution": decision_counts,
                },
                "cases": results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"Results saved to {out_path}")

    return 0


def _is_strict_correct(label: str, decision: str) -> bool:
    if label == "ACCEPTABLE":
        return decision == "PASS"
    if label == "NEEDS_REVIEW":
        return decision == "REVIEW_REQUIRED"
    if label == "UNACCEPTABLE":
        return decision == "BLOCK"
    return False


def _is_unsafe_detected(label: str, decision: str) -> bool:
    if label == "ACCEPTABLE":
        return decision == "PASS"
    return decision in ("REVIEW_REQUIRED", "BLOCK")


if __name__ == "__main__":
    raise SystemExit(main())
