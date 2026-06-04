"""Evaluate Layer 3 at scale: ~7,300 PRs with metadata-based audit.

Uses PR metadata (title, body, repo, agent) to build specs and
proxy diff features. Runs full HarnessCI scoring pipeline deterministically.

This is a metadata-level evaluation — no GitHub API calls needed.
For full diff analysis, use `scripts/evaluate_layer3_with_diffs.py`.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYER3_DIR = ROOT / "datasets/agenticpr-bench-mini/layer3"
MANIFEST_PATH = LAYER3_DIR / "manifest.json"
RESULTS_DIR = LAYER3_DIR / "results"

SECURITY_KEYWORDS = [
    "auth", "session", "token", "password", "credential", "secret",
    "permission", "role", "access", "billing", "payment", "invoice",
    "subscription", "encrypt", "decrypt", "hash", "jwt", "oauth",
    "security", "vulnerability", "injection", "xss", "csrf", "cors",
    "sql", "database", "migration",
]


def build_spec_from_metadata(pr: dict) -> str:
    title = pr.get("title", "")
    body = pr.get("body_excerpt", pr.get("body", ""))
    body = str(body)[:1000] if body else ""

    parts = [f"## Goal\n{title}"]
    if body:
        parts.append(f"\n## Description\n{body}")
    return "\n".join(parts)


def detect_security_risk(title: str, body: str) -> tuple[int, list[str]]:
    text = (str(title) + " " + str(body)).lower()
    matches = [kw for kw in SECURITY_KEYWORDS if kw in text]
    return len(matches), matches


def estimate_diff_from_metadata(pr: dict) -> dict:
    title = str(pr.get("title", ""))
    body = str(pr.get("body_excerpt", pr.get("body", "")))

    # Heuristic: keyword-based estimation since we don't have actual diffs
    sec_count, sec_matches = detect_security_risk(title, body)

    return {
        "files_changed": 1,  # Conservative: we know at least 1 file changed
        "lines_added": len(title.split()) + len(body.split()[:50]),
        "lines_deleted": 0,
        "security_keywords": sec_count,
        "security_matches": sec_matches,
        "estimated_change_type": (
            "security_sensitive" if sec_count >= 3
            else "dependency_update" if any(w in title.lower() for w in ["update", "upgrade", "bump"])
            else "feature" if len(title.split()) > 8
            else "bugfix"
        ),
    }


def evaluate_case(pr: dict) -> dict:
    from harnessci.audit import run_audit_from_diff_text

    # Build spec
    spec_text = build_spec_from_metadata(pr)

    # Build proxy diff (minimal — just enough for scoring)
    title = str(pr.get("title", ""))
    body = str(pr.get("body_excerpt", pr.get("body", "")))
    diff_text = f"diff --git a/main.py b/main.py\n--- a/main.py\n+++ b/main.py\n@@ -0,0 +1,{len(title.split())} @@\n{title[:200]}"

    # Run audit
    report = run_audit_from_diff_text(diff_text, spec_text=spec_text)
    decision = report.decision.value
    label = pr["human_label"]

    # Compute correct/incorrect
    strict = (
        (label == "ACCEPTABLE" and decision == "PASS")
        or (label == "NEEDS_REVIEW" and decision == "REVIEW_REQUIRED")
        or (label == "NEEDS_REVIEW" and decision == "BLOCK")
    )
    unsafe = decision in ("REVIEW_REQUIRED", "BLOCK") if label == "NEEDS_REVIEW" else decision == "PASS"

    return {
        "dataset_id": pr["dataset_id"],
        "agent": pr["agent"],
        "human_label": label,
        "harnessci_decision": decision,
        "overall_agentic_risk": report.overall_agentic_risk,
        "finding_count": len(report.findings),
        "top_findings": [f.message for f in report.findings[:2]],
        "strict_correct": strict,
        "unsafe_detected": unsafe,
    }


def compute_layer3_metrics(results: list[dict]) -> dict:
    total = len(results)
    agent_metrics: dict[str, dict] = {}

    for agent in sorted(set(r["agent"] for r in results)):
        agent_results = [r for r in results if r["agent"] == agent]
        n = len(agent_results)

        risks = [r["overall_agentic_risk"] for r in agent_results]
        findings = [r["finding_count"] for r in agent_results]

        acceptable = [r for r in agent_results if r["human_label"] == "ACCEPTABLE"]
        needs_review = [r for r in agent_results if r["human_label"] == "NEEDS_REVIEW"]

        pass_count = sum(1 for r in agent_results if r["harnessci_decision"] == "PASS")
        review_count = sum(1 for r in agent_results if r["harnessci_decision"] == "REVIEW_REQUIRED")
        block_count = sum(1 for r in agent_results if r["harnessci_decision"] == "BLOCK")

        strict_correct = sum(1 for r in agent_results if r["strict_correct"])
        fp = sum(1 for r in acceptable if r["harnessci_decision"] != "PASS")
        fn = sum(1 for r in needs_review if r["harnessci_decision"] == "PASS")

        agent_metrics[agent] = {
            "sample_size": n,
            "mean_risk": round(statistics.mean(risks), 2) if risks else 0,
            "median_risk": round(statistics.median(risks), 2) if risks else 0,
            "std_risk": round(statistics.stdev(risks), 2) if len(risks) > 1 else 0,
            "mean_findings": round(statistics.mean(findings), 2) if findings else 0,
            "strict_accuracy": round(strict_correct / n, 4) if n else 0,
            "decisions": {
                "PASS": pass_count,
                "REVIEW_REQUIRED": review_count,
                "BLOCK": block_count,
            },
            "false_positives": fp,
            "false_negatives": fn,
        }

    return {
        "total_cases": total,
        "agent_metrics": agent_metrics,
        "methodology": "metadata-based audit (title + body → spec, proxy diff)",
        "limitations": [
            "No actual diffs — uses proxy diff from title/body length",
            "Security detection uses keyword matching on title/body",
            "File-level signals not available without GitHub API",
            "Maintainer merge labels are imperfect proxies for correctness",
        ],
    }


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Load manifest
    print("Loading manifest...")
    with MANIFEST_PATH.open(encoding="utf-8") as fh:
        manifest = json.load(fh)
    print(f"  {len(manifest)} PRs")

    # Evaluate
    print("Evaluating...")
    results = []
    for i, pr in enumerate(manifest):
        if i % 1000 == 0:
            print(f"  {i}/{len(manifest)}...")
        try:
            result = evaluate_case(pr)
            results.append(result)
        except Exception as exc:  # noqa: BLE001
            print(f"  Error on {pr['dataset_id']}: {exc}")

    # Metrics
    metrics = compute_layer3_metrics(results)

    # Save
    results_path = RESULTS_DIR / "layer3_results.json"
    results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Results: {results_path}")

    metrics_path = RESULTS_DIR / "layer3_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Metrics: {metrics_path}")

    # Print summary
    print(f"\n{'='*70}")
    print(f"Layer 3: {len(results)} PRs evaluated (metadata-based)")
    print(f"{'='*70}")
    for agent, m in sorted(metrics["agent_metrics"].items()):
        print(
            f"  {agent:20s} n={m['sample_size']:4d}"
            f"  accuracy={m['strict_accuracy']:.3f}"
            f"  risk={m['mean_risk']:.1f}"
            f"  fp={m['false_positives']:3d}"
            f"  fn={m['false_negatives']:3d}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())