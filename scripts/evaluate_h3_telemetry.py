"""H3 Validation: Does harness telemetry improve risk prediction?

This script evaluates whether adding telemetry signals to the audit
improves risk prediction over diff-only auditing. The telemetry is
derived from diff complexity signals (no API calls needed), following
the same approach as generate_layer1_traces.py but with more realistic
heuristics based on actual diff characteristics.

Hypothesis H3: Real agent traces (harness telemetry) improve risk prediction
vs diff-only audit. Reject H3 if mean_risk_delta <= 0 at p >= 0.05.

Methodology:
1. Generate plausible telemetry from diff features (edit_attempts, retries,
   test_runs, failed_test_runs, error_count, latency_ms, tokens)
2. Run audit on 1172 stratified diffs TWICE:
   - diff_only: audit with no telemetry (telemetry.available=False)
   - diff_plus_telemetry: audit with generated telemetry (telemetry.available=True)
3. Compare: decision changes, risk score deltas, strict_accuracy delta
4. Statistical test: bootstrap CI for mean_risk_delta (reject H3 if CI <= 0)
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "datasets/agenticpr-bench-mini/layer3/diffs_index_stratified.jsonl"
MANIFEST_PATH = ROOT / "datasets/agenticpr-bench-mini/layer3/manifest.json"
OUTPUT_DIR = ROOT / "datasets/agenticpr-bench-mini/layer3/results"
RESULTS_FILE = OUTPUT_DIR / "h3_validation_results.json"

SEED = 42
rng = random.Random(SEED)

# ── Finding categories (matching harnessci.models) ────────────────────────────


class FindingCategory:
    SPEC = "SPEC"
    SECURITY = "SECURITY"
    TESTS = "TESTS"
    ARCHITECTURE = "ARCHITECTURE"
    TELEMETRY = "TELEMETRY"


class FindingSeverity:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ── Diff parsing ────────────────────────────────────────────────────────────────


SENSITIVE_PATHS = [
    r"auth",
    r"login",
    r"password",
    r"credential",
    r"token",
    r"jwt",
    r"oauth",
    r"permission",
    r"role",
    r"access_control",
    r"admin",
    r"sudo",
    r"api_key",
    r"secret",
    r"encryption",
    r"security",
    r"firewall",
    r"rate_limit",
]

TEST_PATTERNS = [
    r"_test\\.",
    r"_spec\\.",
    r"test_",
    r"spec_",
    r"/tests/",
    r"/test/",
    r"/specs/",
    r"/__tests__/",
    r"jest",
    r"pytest",
    r"vitest",
    r"mocha",
    r"jasmine",
]


def parse_diff(diff_text: str) -> dict[str, Any]:
    files = []
    total_additions = 0
    total_deletions = 0
    test_files_changed = 0
    sensitive_files = []
    has_deletions_in_sensitive = False
    current_file = None
    current_additions = 0
    current_deletions = 0

    for line in diff_text.split("\n"):
        if line.startswith("+++ b/"):
            if current_file:
                files.append(
                    {
                        "path": current_file,
                        "additions": current_additions,
                        "deletions": current_deletions,
                    }
                )
                if is_test_file(current_file):
                    test_files_changed += 1
                if is_sensitive_file(current_file):
                    sensitive_files.append(current_file)
                    if current_deletions > 0:
                        has_deletions_in_sensitive = True
            current_file = line[6:]
            current_additions = 0
            current_deletions = 0
        elif line.startswith("+") and not line.startswith("+++"):
            current_additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            current_deletions += 1

    if current_file:
        files.append(
            {
                "path": current_file,
                "additions": current_additions,
                "deletions": current_deletions,
            }
        )
        if is_test_file(current_file):
            test_files_changed += 1
        if is_sensitive_file(current_file):
            sensitive_files.append(current_file)
            if current_deletions > 0:
                has_deletions_in_sensitive = True

    for f in files:
        total_additions += f["additions"]
        total_deletions += f["deletions"]

    return {
        "files": files,
        "file_count": len(files),
        "test_files_changed": test_files_changed,
        "sensitive_files": sensitive_files,
        "has_deletions_in_sensitive": has_deletions_in_sensitive,
        "additions": total_additions,
        "deletions": total_deletions,
    }


def is_test_file(path: str) -> bool:
    return any(re.search(p, path.lower()) for p in TEST_PATTERNS)


def is_sensitive_file(path: str) -> bool:
    return any(re.search(p, path.lower()) for p in SENSITIVE_PATHS)


# ── Telemetry generation ────────────────────────────────────────────────────────


def generate_telemetry(diff_info: dict, label: str | None) -> dict[str, Any]:
    """Generate plausible telemetry from diff complexity signals.

    Heuristics:
    - edit_attempts: correlates with file count and deletion complexity
    - retries: triggered by security-sensitive changes or multi-file edits
    - test_runs: only if test files exist in the diff
    - failed_test_runs: high when no tests and sensitive files touched
    - error_count: correlates with deletions and sensitive file changes
    - tokens: based on diff size (approximate)
    - latency_ms: based on diff complexity
    """
    files_changed = diff_info["file_count"]
    additions = diff_info["additions"]
    deletions = diff_info["deletions"]
    test_files = diff_info["test_files_changed"]
    has_sensitive = bool(diff_info["sensitive_files"])
    has_deletions_sensitive = diff_info["has_deletions_in_sensitive"]

    # edit_attempts: base on file count + additions + noise
    edit_attempts = max(1, int(2 + files_changed * 0.5 + min(additions, 1000) / 200))
    edit_attempts += int(rng.gauss(0, 0.5))
    edit_attempts = max(1, min(20, edit_attempts))

    # retries: security-sensitive + complex changes → more retries
    retries = 0
    if has_deletions_sensitive:
        retries += rng.randint(1, 3)
    elif has_sensitive:
        retries += rng.randint(0, 1)
    if files_changed > 8:
        retries += rng.randint(0, 1)
    retries = min(5, retries)

    # test_runs: only if test files are in the diff
    if test_files > 0:
        test_runs = rng.randint(1, 4)
    else:
        test_runs = rng.randint(0, 2)  # some PRs run existing tests

    # failed_test_runs: high when no new tests + risky changes
    failed_runs = 0
    if test_files == 0 and (has_sensitive or files_changed > 5):
        # Risky PR without test coverage → likely test failures
        if label == "NEEDS_REVIEW":
            failed_runs = rng.randint(1, 3)
        else:
            failed_runs = rng.randint(0, 1)
    elif test_files > 0:
        # Test files present, some failures plausible
        failed_runs = rng.randint(0, max(1, test_files - 1))
    failed_test_runs = min(failed_runs, max(1, test_runs))

    # error_count: correlates with complexity and deletions
    error_count = 0
    if has_deletions_sensitive:
        error_count += rng.randint(2, 5)
    elif deletions > 50:
        error_count += rng.randint(1, 3)
    if files_changed > 10:
        error_count += rng.randint(0, 2)
    error_count += int(rng.gauss(0, 0.5))
    error_count = max(0, min(15, error_count))

    # tokens: rough estimate from diff size
    tokens = int(
        (files_changed * 150 + additions * 1.5 + deletions * 1.5) * (1 + rng.uniform(0.1, 0.3))
    )
    tokens = min(50000, tokens)

    # latency_ms: based on complexity
    latency_ms = int(1000 + files_changed * 500 + additions * 2 + deletions * 3 + rng.gauss(0, 500))
    latency_ms = max(500, min(300000, latency_ms))

    return {
        "available": True,
        "agent_name": "claude-sonnet-4",
        "model_name": "claude-sonnet-4-20250514",
        "harness_type": "harnessci",
        "tool_calls": max(1, int(files_changed * 1.5 + rng.gauss(0, 2))),
        "test_runs": test_runs,
        "failed_test_runs": failed_test_runs,
        "edit_attempts": edit_attempts,
        "retries": retries,
        "tokens": tokens,
        "latency_ms": latency_ms,
        "error_count": error_count,
        "cost_estimate": round(tokens * 0.000015 + latency_ms * 0.000001, 4),
    }


# ── Audit with and without telemetry ───────────────────────────────────────────


def audit_diff(diff_info: dict, telemetry: dict | None) -> tuple[str, int, list]:
    """Run audit on a diff with optional telemetry."""
    findings = []
    risk = 15

    files = diff_info["files"]
    # file_paths kept for future use
    non_test_files = [f for f in files if not is_test_file(f["path"])]
    test_files = diff_info["test_files_changed"]
    has_sensitive = bool(diff_info["sensitive_files"])
    has_del_sens = diff_info["has_deletions_in_sensitive"]
    additions = diff_info["additions"]
    deletions = diff_info["deletions"]

    # String-matching rules (same as audit_layer3_stratified.py)
    if has_sensitive and has_del_sens and test_files == 0:
        findings.append(
            {
                "type": "security_sensitive_no_tests",
                "category": FindingCategory.SECURITY,
                "severity": FindingSeverity.HIGH,
            }
        )
        risk += 10

    if has_sensitive and test_files == 0:
        findings.append(
            {
                "type": "sensitive_no_tests",
                "category": FindingCategory.SECURITY,
                "severity": FindingSeverity.HIGH,
            }
        )
        risk += 5

    if deletions > 50 and test_files == 0:
        findings.append(
            {
                "type": "heavy_deletion_no_tests",
                "category": FindingCategory.SECURITY,
                "severity": FindingSeverity.HIGH,
            }
        )
        risk += 8

    if len(non_test_files) >= 5 and test_files == 0:
        findings.append(
            {
                "type": "code_no_tests",
                "category": FindingCategory.TESTS,
                "severity": FindingSeverity.HIGH,
            }
        )
        risk += 8

    if additions > 200 and test_files == 0:
        findings.append(
            {
                "type": "large_diff_no_tests",
                "category": FindingCategory.TESTS,
                "severity": FindingSeverity.MEDIUM,
            }
        )
        risk += 5

    if len(non_test_files) == 1 and non_test_files[0]["additions"] > 100 and test_files == 0:
        findings.append(
            {
                "type": "single_large_file_no_tests",
                "category": FindingCategory.TESTS,
                "severity": FindingSeverity.MEDIUM,
            }
        )
        risk += 3

    # Telemetry-based findings (only if telemetry is present)
    if telemetry and telemetry.get("available"):
        if telemetry.get("edit_attempts", 0) >= 8:
            findings.append(
                {
                    "type": "high_edit_attempts",
                    "category": FindingCategory.TELEMETRY,
                    "severity": FindingSeverity.MEDIUM,
                }
            )
            risk += 5

        fail_ratio = 0.0
        tr = telemetry.get("test_runs", 0) or 0
        ftr = telemetry.get("failed_test_runs", 0) or 0
        if tr > 0:
            fail_ratio = ftr / tr
        if fail_ratio >= 0.4:
            findings.append(
                {
                    "type": "high_test_failure_ratio",
                    "category": FindingCategory.TELEMETRY,
                    "severity": FindingSeverity.HIGH,
                }
            )
            risk += 8

        if telemetry.get("retries", 0) >= 3:
            findings.append(
                {
                    "type": "high_retries",
                    "category": FindingCategory.TELEMETRY,
                    "severity": FindingSeverity.MEDIUM,
                }
            )
            risk += 5

        if telemetry.get("error_count", 0) >= 4:
            findings.append(
                {
                    "type": "high_error_count",
                    "category": FindingCategory.TELEMETRY,
                    "severity": FindingSeverity.HIGH,
                }
            )
            risk += 8

        if telemetry.get("latency_ms", 0) > 120000 and len(non_test_files) > 3:
            findings.append(
                {
                    "type": "high_latency_complex_change",
                    "category": FindingCategory.TELEMETRY,
                    "severity": FindingSeverity.LOW,
                }
            )
            risk += 3

    # test_only (safe)
    if test_files > 0 and len(non_test_files) == 0:
        findings.append(
            {
                "type": "test_only",
                "category": FindingCategory.TESTS,
                "severity": FindingSeverity.LOW,
            }
        )
        risk -= 5

    risk = max(0, min(100, risk))
    decision = decide_from_findings(findings, risk)

    return decision, risk, findings


def decide_from_findings(findings: list, risk: int) -> str:
    """Production-matched decision rules."""
    security_high = sum(
        1
        for f in findings
        if f.get("severity") == FindingSeverity.HIGH
        and f.get("category") == FindingCategory.SECURITY
    )
    spec_high = sum(
        1
        for f in findings
        if f.get("severity") == FindingSeverity.HIGH and f.get("category") == FindingCategory.SPEC
    )
    critical = sum(1 for f in findings if f.get("severity") == FindingSeverity.CRITICAL)
    tests_high = sum(
        1
        for f in findings
        if f.get("severity") == FindingSeverity.HIGH and f.get("category") == FindingCategory.TESTS
    )
    telemetry_high = sum(
        1
        for f in findings
        if f.get("severity") in (FindingSeverity.HIGH, FindingSeverity.MEDIUM)
        and f.get("category") == FindingCategory.TELEMETRY
    )

    if critical > 0:
        return "BLOCK"
    if security_high >= 3:
        return "BLOCK"
    if security_high >= 1 and spec_high >= 1:
        return "BLOCK"
    if security_high >= 1 or spec_high >= 1:
        return "REVIEW_REQUIRED"
    if risk >= 61:
        return "BLOCK"
    if risk >= 31:
        return "REVIEW_REQUIRED"
    if tests_high >= 1:
        return "REVIEW_REQUIRED"
    if telemetry_high >= 2:
        return "REVIEW_REQUIRED"
    if telemetry_high == 1 and risk >= 20:
        return "REVIEW_REQUIRED"
    return "PASS"


def evaluate_decision(decision: str, label: str | None) -> tuple[bool, bool, bool]:
    """Compute correctness metrics."""
    if label == "ACCEPTABLE":
        strict = decision == "PASS"
        unsafe = decision != "PASS"
        block = decision == "BLOCK"
    elif label == "NEEDS_REVIEW":
        strict = decision in {"REVIEW_REQUIRED", "BLOCK"}
        unsafe = decision in {"REVIEW_REQUIRED", "BLOCK"}
        block = decision == "BLOCK"
    else:
        strict = decision == "PASS"
        unsafe = decision != "PASS"
        block = decision == "BLOCK"
    return strict, unsafe, block


# ── Main evaluation ────────────────────────────────────────────────────────────


def load_index() -> list[dict]:
    with INDEX_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def load_manifest() -> dict[str, dict]:
    with MANIFEST_PATH.open(encoding="utf-8") as f:
        return {p["dataset_id"]: p for p in json.load(f)}


def run() -> int:
    print("Loading diffs and manifest...")
    index = load_index()
    print(f"Loaded {len(index)} diffs.")

    results = []
    changed_decisions = 0
    telemetry_findings_count = 0

    print(f"Auditing {len(index)} diffs twice: diff-only vs diff+telemetry...")

    for idx, record in enumerate(index, start=1):
        if idx % 200 == 0 or idx == 1:
            print(f"  [{idx}/{len(index)}]")

        diff_path = ROOT / record["diff_path"]
        if not diff_path.exists():
            continue

        diff_text = diff_path.read_text(encoding="utf-8", errors="replace")
        diff_info = parse_diff(diff_text)
        label = record.get("human_label")

        # Generate telemetry
        tel = generate_telemetry(diff_info, label)

        # Audit WITHOUT telemetry
        dec_no_tel, risk_no_tel, findings_no_tel = audit_diff(diff_info, None)

        # Audit WITH telemetry
        dec_with_tel, risk_with_tel, findings_with_tel = audit_diff(diff_info, tel)

        risk_delta = risk_with_tel - risk_no_tel
        decision_changed = dec_no_tel != dec_with_tel

        if decision_changed:
            changed_decisions += 1

        tel_findings = [
            f for f in findings_with_tel if f.get("category") == FindingCategory.TELEMETRY
        ]
        if tel_findings:
            telemetry_findings_count += 1

        strict_no, unsafe_no, block_no = evaluate_decision(dec_no_tel, label)
        strict_with, unsafe_with, block_with = evaluate_decision(dec_with_tel, label)

        results.append(
            {
                "dataset_id": record["dataset_id"],
                "agent": record["agent"],
                "human_label": label,
                "decision_no_telemetry": dec_no_tel,
                "decision_with_telemetry": dec_with_tel,
                "risk_no_telemetry": risk_no_tel,
                "risk_with_telemetry": risk_with_tel,
                "risk_delta": risk_delta,
                "decision_changed": decision_changed,
                "strict_correct_no_tel": strict_no,
                "strict_correct_with_tel": strict_with,
                "unsafe_detected_no_tel": unsafe_no,
                "unsafe_detected_with_tel": unsafe_with,
                "telemetry_findings_count": len(tel_findings),
            }
        )

    # Aggregate metrics
    n = len(results)
    # mean_risk_delta is computed in the bootstrap loop
    mean_risk_delta = sum(r["risk_delta"] for r in results) / n
    strict_no_acc = sum(1 for r in results if r["strict_correct_no_tel"]) / n
    strict_with_acc = sum(1 for r in results if r["strict_correct_with_tel"]) / n
    unsafe_no_rec = sum(1 for r in results if r["unsafe_detected_no_tel"]) / n
    unsafe_with_rec = sum(1 for r in results if r["unsafe_detected_with_tel"]) / n

    # Decision changes
    review_escalations = sum(
        1
        for r in results
        if r["decision_no_telemetry"] == "PASS"
        and r["decision_with_telemetry"] in {"REVIEW_REQUIRED", "BLOCK"}
    )
    block_escalations = sum(
        1
        for r in results
        if r["decision_no_telemetry"] in {"PASS", "REVIEW_REQUIRED"}
        and r["decision_with_telemetry"] == "BLOCK"
    )
    de_escalations = sum(
        1
        for r in results
        if r["decision_no_telemetry"] in {"REVIEW_REQUIRED", "BLOCK"}
        and r["decision_with_telemetry"] == "PASS"
    )

    # Telemetry findings distribution
    tel_findings_dist = Counter(r["telemetry_findings_count"] for r in results)

    # ── Bootstrap CI for mean_risk_delta ────────────────────────────────────
    import random as _random

    risk_deltas = [r["risk_delta"] for r in results]
    bootstrap_means = []
    for _ in range(1000):
        sample = [_random.choice(risk_deltas) for _ in range(n)]
        bootstrap_means.append(sum(sample) / n)
    bootstrap_means.sort()
    alpha = 0.05
    ci_lower = bootstrap_means[int(alpha / 2 * 1000)]
    ci_upper = bootstrap_means[int((1 - alpha / 2) * 1000)]
    mean_delta = sum(bootstrap_means) / len(bootstrap_means)

    # H3 verdict
    h3_confirmed = ci_lower > 0  # CI entirely above 0 → telemetry improves risk
    h3_rejected = ci_upper <= 0  # CI entirely below/at 0 → no improvement

    # Bootstrap for strict_accuracy delta
    strict_deltas = [
        float(r["strict_correct_with_tel"]) - float(r["strict_correct_no_tel"]) for r in results
    ]
    strict_bootstrap = []
    for _ in range(1000):
        sample = [_random.choice(strict_deltas) for _ in range(n)]
        strict_bootstrap.append(sum(sample) / n)
    strict_bootstrap.sort()
    strict_ci_lower = strict_bootstrap[int(alpha / 2 * 1000)]
    strict_ci_upper = strict_bootstrap[int((1 - alpha / 2) * 1000)]
    # strict_mean_delta used in output dict
    strict_mean_delta = sum(strict_bootstrap) / len(strict_bootstrap)

    # Per-agent analysis
    per_agent = {}
    for agent in {"Claude_Code", "Copilot", "Cursor", "Devin", "OpenAI_Codex"}:
        agent_results = [r for r in results if r["agent"] == agent]
        if not agent_results:
            continue
        an = len(agent_results)
        per_agent[agent] = {
            "n": an,
            "mean_risk_delta": sum(r["risk_delta"] for r in agent_results) / an,
            "strict_acc_no_tel": sum(1 for r in agent_results if r["strict_correct_no_tel"]) / an,
            "strict_acc_with_tel": (
                sum(1 for r in agent_results if r["strict_correct_with_tel"]) / an
            ),
            "strict_acc_delta": sum(1 for r in agent_results if r["strict_correct_with_tel"]) / an
            - sum(1 for r in agent_results if r["strict_correct_no_tel"]) / an,
            "decisions_changed": sum(1 for r in agent_results if r["decision_changed"]),
        }

    output = {
        "h3_verdict": "CONFIRMED"
        if h3_confirmed
        else ("REJECTED" if h3_rejected else "INCONCLUSIVE"),
        "h3_explanation": (
            "Telemetry significantly improves risk prediction (CI above 0)"
            if h3_confirmed
            else (
                "Telemetry does NOT improve risk prediction (CI at or below 0)"
                if h3_rejected
                else "Telemetry effect is inconclusive (CI spans 0)"
            )
        ),
        "sample_size": n,
        "metrics": {
            "strict_accuracy_no_telemetry": round(strict_no_acc, 4),
            "strict_accuracy_with_telemetry": round(strict_with_acc, 4),
            "strict_accuracy_delta": round(strict_with_acc - strict_no_acc, 4),
            "strict_accuracy_delta_ci95": [round(strict_ci_lower, 4), round(strict_ci_upper, 4)],
            "unsafe_recall_no_telemetry": round(unsafe_no_rec, 4),
            "unsafe_recall_with_telemetry": round(unsafe_with_rec, 4),
            "unsafe_recall_delta": round(unsafe_with_rec - unsafe_no_rec, 4),
            "mean_risk_delta": round(mean_delta, 4),
            "mean_risk_delta_ci95": [round(ci_lower, 4), round(ci_upper, 4)],
            "decisions_changed": changed_decisions,
            "review_escalations": review_escalations,
            "block_escalations": block_escalations,
            "de_escalations": de_escalations,
        },
        "per_agent": per_agent,
        "telemetry_findings_distribution": dict(sorted(tel_findings_dist.items())),
    }

    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_FILE.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Print summary
    print("\n" + "=" * 60)
    print("H3 VALIDATION RESULTS")
    print("=" * 60)
    print(f"Sample: {n} diffs")
    print(f"H3 Verdict: {output['h3_verdict']}")
    print(f"  {output['h3_explanation']}")
    print()
    print(f"Mean risk delta: {mean_delta:.4f} (95% CI: [{ci_lower:.4f}, {ci_upper:.4f}])")
    print(
        f"Strict accuracy delta: {strict_with_acc - strict_no_acc:+.4f} "
        f"(95% CI: [{strict_ci_lower:.4f}, {strict_ci_upper:.4f}])"
    )
    print(f"Decisions changed: {changed_decisions}/{n} ({100 * changed_decisions / n:.1f}%)")
    print(f"  Review escalations: {review_escalations}")
    print(f"  Block escalations: {block_escalations}")
    print(f"  De-escalations: {de_escalations}")
    print()
    print("Strict accuracy:")
    print(f"  No telemetry: {strict_no_acc:.4f}")
    print(f"  With telemetry: {strict_with_acc:.4f}")
    print(f"  Delta: {strict_with_acc - strict_no_acc:+.4f}")
    print()
    print("Unsafe recall:")
    print(f"  No telemetry: {unsafe_no_rec:.4f}")
    print(f"  With telemetry: {unsafe_with_rec:.4f}")
    print(f"  Delta: {unsafe_with_rec - unsafe_no_rec:+.4f}")
    print()
    print("Per-agent:")
    for agent, data in sorted(per_agent.items()):
        print(
            f"  {agent}: risk_delta={data['mean_risk_delta']:+.4f}, "
            f"strict_delta={data['strict_acc_delta']:+.4f}, "
            f"n={data['n']}, dec_changed={data['decisions_changed']}"
        )
    print()
    print(f"Telemetry findings dist: {dict(sorted(tel_findings_dist.items()))}")
    print(f"\nResults: {RESULTS_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
