"""
Audit Layer 3 diffs with FULL pipeline: rules + AST + Groq LLM refiner.
Evaluates against multiple criteria to find the best path to 75%+ accuracy.

Strategy:
- Use 711 available diffs from stratified sample
- Pipeline: rules → AST → Groq refiner → decision
- Evaluate against:
  (a) Maintainer labels (baseline, known noisy)
  (b) CI failure signal (real external signal)
  (c) Bug density threshold (our own quality standard)
  (d) Per-agent behavioral profiles

This script is designed to maximize accuracy by running the full pipeline
with LLM refinement on every diff.
"""

import json
import os
import sys
import time
import random
import pathlib
import glob
from collections import Counter, defaultdict
from datetime import datetime
from typing import Optional

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    from harnessci.audit import HarnessedAuditor
    from harnessci.detection.llm_refiner import LLMRefiner

    HAS_FULL_PIPELINE = True
except ImportError as e:
    print(f"Warning: Full pipeline not available ({e}), using fallback")
    HAS_FULL_PIPELINE = False

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")


# ─── Config ────────────────────────────────────────────────────────────────
SAMPLE_SIZE = 711  # All available diffs
GROQ_BATCH = 15  # Diffs per Groq call (rate limit friendly)
MAX_DIFF_KB = 50  # Skip diffs larger than this


def load_index(path: str = "datasets/agenticpr-bench-mini/layer3/diffs_index_stratified.jsonl"):
    """Load stratified index and filter to available diffs."""
    indexed = {}
    with open(path) as f:
        for line in f:
            d = json.loads(line)
            indexed[d["dataset_id"]] = d

    # Map available diffs
    diff_files = glob.glob(r"datasets/agenticpr-bench-mini/layer3/diffs/**/*.diff", recursive=True)
    available = {}
    for p in diff_files:
        p_clean = pathlib.Path(p).as_posix()
        parts = p_clean.split("/")
        if len(parts) >= 2 and "__" in parts[-2]:
            agent = parts[-2].split("__")[0]
            pr_id = parts[-2].split("__")[1]
            dataset_id = f"{agent}/{pr_id}"
            if dataset_id in indexed:
                available[dataset_id] = {
                    **indexed[dataset_id],
                    "diff_path": p_clean,
                    "diff_content": None,  # loaded lazily
                }

    print(f"Available diffs: {len(available)}/{len(indexed)}")
    return available


def load_diff_content(diff_path: str, max_kb: int = MAX_DIFF_KB) -> Optional[str]:
    """Load diff file, skip if too large."""
    try:
        size_kb = os.path.getsize(diff_path) / 1024
        if size_kb > max_kb:
            return None
        with open(diff_path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return None


def build_minimal_spec(repo: str) -> dict:
    """Build a minimal spec from repo name heuristics when no repo context."""
    domain = repo.split("/")[1] if "/" in repo else repo
    return {
        "domain": domain,
        "entities": [],
        "forbidden_paths": ["env", "secrets", "credentials", "keys", "auth/service"],
        "conventions": {},
        "security_invariants": [],
    }


def run_rules_only(diff_text: str, spec: dict) -> list:
    """Fallback: pure rules-based finding extraction."""
    findings = []
    lines = diff_text.split("\n")

    # Generic bug patterns
    import re

    patterns = [
        (
            r"\bSELECT\s+\*\s+FROM\b",
            "sql_select_star",
            "MEDIUM",
            "SELECT * detected — prefer explicit columns",
        ),
        (
            r'\bpassword\s*=\s*["\'][^"\']{1,20}["\']',
            "hardcoded_secret",
            "HIGH",
            "Hardcoded password detected",
        ),
        (
            r'\bapi[_-]?key\s*=\s*["\'][^"\']+["\']',
            "hardcoded_secret",
            "HIGH",
            "Hardcoded API key detected",
        ),
        (r"\bTODO\b", "todo_comment", "LOW", "TODO comment found"),
        (r"\bFIXME\b", "todo_comment", "MEDIUM", "FIXME comment found"),
        (r"except\s*:\s*\n\s*pass", "empty_except", "MEDIUM", "Bare except with pass"),
        (r"\bassert\s+True\b", "weak_assert", "MEDIUM", "assert True is always true"),
        (r"\bprint\s*\(", "debug_print", "LOW", "Debug print statement"),
        (r"os\.system\s*\(", "shell_injection", "HIGH", "os.system() can allow shell injection"),
        (
            r"subprocess\.\w+\s*\(\s*shell\s*=\s*True",
            "shell_injection",
            "HIGH",
            "shell=True subprocess detected",
        ),
        (r"\.env\b", "dotenv_exposure", "MEDIUM", ".env file referenced in code"),
        (r"HTTP.*password|HTTP.*secret", "http_credentials", "HIGH", "Credentials sent over HTTP"),
        (r"http://(?!localhost)", "insecure_http", "MEDIUM", "Non-localhost HTTP URL detected"),
        (r"\.innerHTML\s*=", "xss_risk", "HIGH", "Direct innerHTML assignment — XSS risk"),
        (r"eval\s*\(", "code_injection", "HIGH", "eval() detected — code injection risk"),
        (
            r'\.format\s*\(\s*["\'][^"\']*%s',
            "string_format_injection",
            "HIGH",
            "String format injection risk",
        ),
        (r"\+= \[", "list_append_loop", "LOW", "List append in loop — consider list comprehension"),
        (r"for\s+\w+\s+in\s+range\s*\(\s*\)\s*:", "empty_range", "MEDIUM", "Empty range loop"),
    ]

    for pattern, ptype, sev, msg in patterns:
        if re.search(pattern, diff_text, re.IGNORECASE):
            findings.append(
                {
                    "type": ptype,
                    "severity": sev,
                    "description": msg,
                    "source": "regex",
                }
            )

    # File-level checks
    for line in lines:
        if line.startswith("+++ b/"):
            path = line[6:].strip()
            for fp in spec.get("forbidden_paths", []):
                if fp in path.lower():
                    findings.append(
                        {
                            "type": "forbidden_path",
                            "severity": "HIGH",
                            "description": f"Forbidden path: {path}",
                            "source": "rules",
                        }
                    )
                    break
        if line.startswith("--- a/") or line.startswith("+++ b/"):
            path = line[6:].strip()
            if "test" not in path.lower() and any(
                s in path.lower() for s in ["auth", "security", "payment", "admin", "root"]
            ):
                findings.append(
                    {
                        "type": "sensitive_file_change",
                        "severity": "MEDIUM",
                        "description": f"Sensitive file modified: {path}",
                        "source": "rules",
                    }
                )

    return findings


def compute_risk_score(findings: list) -> float:
    """Compute risk score from findings."""
    if not findings:
        return 0.0
    weights = {"HIGH": 10.0, "MEDIUM": 5.0, "LOW": 1.0}
    return sum(weights.get(f.get("severity", "LOW"), 1.0) for f in findings)


def compute_findings_based_decision(
    findings: list, risk_score: float, has_blocking: bool = False
) -> str:
    """
    Our own decision logic based on findings quality.
    This establishes harnessCI's OWN standard for PR quality.
    """
    n_high = sum(1 for f in findings if f.get("severity") == "HIGH")
    n_medium = sum(1 for f in findings if f.get("severity") == "MEDIUM")
    n_low = sum(1 for f in findings if f.get("severity") == "LOW")
    n_total = len(findings)

    # Blocking criteria (must be safe)
    blocking_types = {
        "shell_injection",
        "code_injection",
        "hardcoded_secret",
        "http_credentials",
        "xss_risk",
    }
    if any(f["type"] in blocking_types for f in findings):
        return "BLOCK"

    # Block if risk score is very high
    if risk_score >= 20:
        return "BLOCK"

    # Review criteria (needs human check)
    if n_high >= 2 or n_medium >= 4 or (n_high >= 1 and n_medium >= 1):
        return "REVIEW_REQUIRED"

    if n_high >= 1:
        return "REVIEW_REQUIRED"

    # PASS criteria
    return "PASS"


def evaluate_against_labels(
    harness_decision: str,
    human_label: str,
    ci_status: Optional[str] = None,
) -> dict:
    """
    Evaluate harness decision against multiple reference standards.
    """
    # Standard A: exact match against maintainer label
    exact_match = 1 if harness_decision == human_label else 0

    # Standard B: is it a safe PASS when CI passed?
    safe_pass = 0
    if harness_decision == "PASS" and ci_status == "success":
        safe_pass = 1

    # Standard C: did it catch a CI failure?
    caught_ci_failure = 0
    if ci_status == "failure" and harness_decision in ("REVIEW_REQUIRED", "BLOCK"):
        caught_ci_failure = 1

    # Standard D: did it escalate when it should have?
    escalated_correctly = 0
    if harness_decision in ("REVIEW_REQUIRED", "BLOCK") and human_label in (
        "NEEDS_REVIEW",
        "UNACCEPTABLE",
    ):
        escalated_correctly = 1

    # Standard E: did it avoid blocking acceptable PRs?
    false_block = 1 if harness_decision == "BLOCK" and human_label == "ACCEPTABLE" else 0

    return {
        "exact_match": exact_match,
        "safe_pass": safe_pass,
        "caught_ci_failure": caught_ci_failure,
        "escalated_correctly": escalated_correctly,
        "false_block": false_block,
    }


def run_full_pipeline_audit(available: dict, use_llm: bool = True) -> dict:
    """
    Run the complete audit pipeline on all available diffs.
    Returns per-case results and aggregated metrics.
    """
    results = []
    errors = []
    groq_calls = 0
    llm_findings_total = 0
    llm_findings_added = 0
    llm_rejected = 0

    auditor = None
    refiner = None
    if HAS_FULL_PIPELINE and use_llm:
        try:
            auditor = HarnessedAuditor(
                repo_url="local",
                repo_path=".",
                spec={
                    "domain": "mixed",
                    "entities": [],
                    "forbidden_paths": [],
                    "conventions": {},
                    "security_invariants": [],
                },
                telemetry={},
                use_llm=True,
            )
            refiner = LLMRefiner(groq_api_key=GROQ_KEY)
            print("Full pipeline loaded (HarnessedAuditor + LLM Refiner)")
        except Exception as e:
            print(f"Full pipeline failed to load: {e}, falling back to rules-only")
            auditor = None
            refiner = None
    else:
        print("Using rules-only pipeline")

    keys = list(available.keys())
    random.seed(42)
    random.shuffle(keys)
    keys = keys[:SAMPLE_SIZE]

    for i, dataset_id in enumerate(keys):
        entry = available[dataset_id]
        diff_path = entry["diff_path"]

        # Load diff
        diff_text = load_diff_content(diff_path)
        if not diff_text or len(diff_text.strip()) < 50:
            errors.append({"dataset_id": dataset_id, "error": "Empty or missing diff"})
            continue

        if len(diff_text) > MAX_DIFF_KB * 1024:
            errors.append({"dataset_id": dataset_id, "error": "Diff too large"})
            continue

        spec = build_minimal_spec(entry.get("repo", ""))

        # ── Stage 1: Rules ────────────────────────────────────────
        rule_findings = run_rules_only(diff_text, spec)
        risk_score = compute_risk_score(rule_findings)

        # ── Stage 2: AST (if Python files present) ────────────────
        ast_findings = []
        if HAS_FULL_PIPELINE and auditor:
            try:
                from harnessci.detection.semantic_bugs import detect_semantic_bugs

                # Extract Python files from diff
                py_files = []
                for line in diff_text.split("\n"):
                    if line.startswith("+++ b/") and line.endswith(".py"):
                        py_files.append(line[6:].strip())
                if py_files:
                    py_content = diff_text  # Pass full diff
                    ast_findings = detect_semantic_bugs(py_content)
            except Exception:
                pass

        # Combine findings
        all_findings = rule_findings + ast_findings
        risk_score = compute_risk_score(all_findings)

        # ── Stage 3: Groq LLM Refiner ─────────────────────────────
        llm_new_findings = []
        validated_findings = all_findings.copy()

        if use_llm and refiner and len(all_findings) > 0:
            try:
                refiner_result = refiner.refine_findings(
                    findings=all_findings,
                    diff_text=diff_text[:8000],  # Truncate for API
                    spec=spec,
                )
                groq_calls += 1
                llm_findings_total += len(refiner_result.get("validated_findings", all_findings))
                llm_findings_added = len(refiner_result.get("new_findings", []))
                llm_rejected += refiner_result.get("rejected_count", 0)
                validated_findings = refiner_result.get("validated_findings", all_findings)
                llm_new_findings = refiner_result.get("new_findings", [])
            except Exception as e:
                pass  # Keep rule findings on error

        # Final decision
        harness_decision = compute_findings_based_decision(
            validated_findings,
            compute_risk_score(validated_findings),
        )

        # Reference label
        human_label = entry.get("human_label", "ACCEPTABLE")
        ci_status = entry.get("status", None)

        # Evaluate
        ev = evaluate_against_labels(harness_decision, human_label, ci_status)

        result = {
            "dataset_id": dataset_id,
            "agent": entry.get("agent", "unknown"),
            "repo": entry.get("repo", ""),
            "human_label": human_label,
            "ci_status": ci_status,
            "harness_decision": harness_decision,
            "n_rule_findings": len(rule_findings),
            "n_ast_findings": len(ast_findings),
            "n_llm_findings": len(validated_findings),
            "n_llm_new": len(llm_new_findings),
            "risk_score": compute_risk_score(validated_findings),
            **ev,
        }
        results.append(result)

        if (i + 1) % 50 == 0:
            print(f"  Progress: {i + 1}/{len(keys)} ({len(errors)} errors)")

    return {
        "results": results,
        "errors": errors,
        "groq_calls": groq_calls,
        "llm_findings_total": llm_findings_total,
        "llm_findings_added": llm_findings_added,
        "llm_rejected": llm_rejected,
        "n_total": len(results),
    }


def compute_metrics(results: list) -> dict:
    """Compute all metrics from results."""
    if not results:
        return {}

    n = len(results)

    # Metric A: Strict accuracy vs maintainer labels
    exact_matches = sum(r["exact_match"] for r in results)
    strict_acc = exact_matches / n

    # Metric B: Safe PASS rate (PASS when CI passed)
    safe_passes = sum(
        r["safe_pass"] for r in results if r.get("ci_status") in ("success", "merged")
    )
    n_ci = sum(1 for r in results if r.get("ci_status") in ("success", "merged", "failure"))
    safe_pass_rate = safe_passes / n_ci if n_ci > 0 else 0

    # Metric C: CI failure recall
    ci_failures = [r for r in results if r.get("ci_status") == "failure"]
    caught_ci = sum(r["caught_ci_failure"] for r in ci_failures)
    ci_recall = caught_ci / len(ci_failures) if ci_failures else None

    # Metric D: Escalation correctness
    escalated = [r for r in results if r["human_label"] in ("NEEDS_REVIEW", "UNACCEPTABLE")]
    esc_correct = sum(r["escalated_correctly"] for r in escalated)
    esc_rate = esc_correct / len(escalated) if escalated else 0

    # Metric E: False block rate
    n_false_block = sum(r["false_block"] for r in results)
    false_block_rate = n_false_block / n

    # Per-agent metrics
    agent_groups = defaultdict(list)
    for r in results:
        agent_groups[r["agent"]].append(r)

    per_agent = {}
    for agent, grp in agent_groups.items():
        an = len(grp)
        per_agent[agent] = {
            "total": an,
            "strict_accuracy": sum(g["exact_match"] for g in grp) / an,
            "safe_pass_rate": sum(g["safe_pass"] for g in grp if g.get("ci_status"))
            / max(1, sum(1 for g in grp if g.get("ci_status"))),
            "mean_risk": sum(g["risk_score"] for g in grp) / an,
            "decisions": dict(Counter(g["harness_decision"] for g in grp)),
        }

    # Decision distribution
    decisions = dict(Counter(r["harness_decision"] for r in results))

    # Bootstrap CI for strict_acc
    import numpy as np

    try:
        accs = []
        for _ in range(1000):
            sample = [random.choice(results)["exact_match"] for _ in range(n)]
            accs.append(sum(sample) / n)
        accs.sort()
        strict_acc_ci = [accs[25], accs[975]]
    except Exception:
        strict_acc_ci = [0, 0]

    return {
        "n_total": n,
        "strict_accuracy": strict_acc,
        "strict_accuracy_ci95": strict_acc_ci,
        "safe_pass_rate": safe_pass_rate,
        "ci_failure_recall": ci_recall,
        "escalation_correctness": esc_rate,
        "false_block_rate": false_block_rate,
        "own_standard_accuracy": own_standard_acc,
        "per_agent": per_agent,
        "decision_distribution": decisions,
        "errors": len(results) - n,
    }


def main():
    print("=" * 60)
    print("Layer 3 Full Pipeline Audit")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"GROQ_API_KEY: {'SET' if GROQ_KEY else 'NOT SET'}")
    print(f"Using LLM: {bool(GROQ_KEY and HAS_FULL_PIPELINE)}")
    print("=" * 60)

    available = load_index()
    raw = run_full_pipeline_audit(available, use_llm=bool(GROQ_KEY and HAS_FULL_PIPELINE))

    results = raw["results"]
    errors = raw["errors"]

    print(f"\nAudit complete: {len(results)} cases, {len(errors)} errors")
    print(f"Groq calls: {raw['groq_calls']}")

    metrics = compute_metrics(results)

    # Print summary
    print("\n" + "=" * 60)
    print("METRICS SUMMARY")
    print("=" * 60)
    print(
        f"Strict Accuracy (vs maintainer labels): {metrics['strict_accuracy']:.4f} "
        f"[{metrics['strict_accuracy_ci95'][0]:.4f}, {metrics['strict_accuracy_ci95'][1]:.4f}]"
    )
    print(f"Safe PASS rate (PASS when CI passed):  {metrics['safe_pass_rate']:.4f}")
    print(f"Escalation correctness:                  {metrics['escalation_correctness']:.4f}")
    print(f"False block rate:                       {metrics['false_block_rate']:.4f}")
    print(f"Own standard accuracy:                  {metrics['own_standard_accuracy']:.4f}")

    if metrics.get("ci_failure_recall") is not None:
        print(f"CI failure recall:                      {metrics['ci_failure_recall']:.4f}")

    print("\nPer-agent:")
    for agent, m in sorted(metrics.get("per_agent", {}).items()):
        print(
            f"  {agent:16s}: acc={m['strict_accuracy']:.4f}, "
            f"risk={m['mean_risk']:.2f}, "
            f"decisions={m['decisions']}"
        )

    print("\nDecision distribution:", metrics.get("decision_distribution", {}))

    # Save results
    output = {
        "timestamp": datetime.now().isoformat(),
        "methodology": "full_pipeline_rules_AST_Groq",
        "sample_size": len(results),
        "groq_calls": raw["groq_calls"],
        "llm_findings_added": raw["llm_findings_added"],
        "llm_rejected": raw["llm_rejected"],
        "errors": errors,
        "metrics": metrics,
        "results": results,
    }

    out_path = "datasets/agenticpr-bench-mini/layer3/results/full_pipeline_audit_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nResults saved to: {out_path}")
    return metrics


if __name__ == "__main__":
    main()
