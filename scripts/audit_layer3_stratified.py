"""Audit stratified Layer 3 diffs with the real HarnessCI audit pipeline.

This script loads the stratified diff index, parses each diff to extract
features (test coverage, change type, sensitive files), infers specs from
PR metadata, and runs the full audit decision engine.

Output: stratified audit results + bootstrap confidence intervals.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "datasets/agenticpr-bench-mini/layer3/diffs_index_stratified.jsonl"
MANIFEST_PATH = ROOT / "datasets/agenticpr-bench-mini/layer3/manifest.json"
OUTPUT_DIR = ROOT / "datasets/agenticpr-bench-mini/layer3/results"
RESULTS_FILE = OUTPUT_DIR / "stratified_audit_results.json"
BOOTSTRAP_FILE = OUTPUT_DIR / "stratified_bootstrap.json"

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


# Categories for findings (matching harnessci.models.FindingCategory)
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


TEST_PATTERNS = [
    r"_test\.",
    r"_spec\.",
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

PATCH_STATS_RE = re.compile(
    r"(\d+) files? changed.*?(\d+) insertions?.*?(\d+) deletions?",
    re.IGNORECASE,
)


def load_index() -> list[dict]:
    with INDEX_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def load_manifest() -> dict[str, dict]:
    with MANIFEST_PATH.open(encoding="utf-8") as f:
        return {p["dataset_id"]: p for p in json.load(f)}


def parse_diff(diff_text: str) -> dict[str, Any]:
    """Extract file paths, test coverage, and sensitive file signals from diff."""
    files = []
    total_additions = 0
    total_deletions = 0
    test_files_changed = 0
    sensitive_files = []
    has_deletions_in_sensitive = False
    new_tests_added = False

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
            if is_test_pattern(line):
                new_tests_added = True
        elif line.startswith("-") and not line.startswith("---"):
            current_deletions += 1
        elif line.startswith("@@"):
            pass

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
        "new_tests_added": new_tests_added,
        "additions": total_additions,
        "deletions": total_deletions,
    }


def is_test_file(path: str) -> bool:
    return any(re.search(p, path.lower()) for p in TEST_PATTERNS)


def is_sensitive_file(path: str) -> bool:
    return any(re.search(p, path.lower()) for p in SENSITIVE_PATHS)


def is_test_pattern(line: str) -> bool:
    return any(
        p in line.lower()
        for p in [
            "it(",
            "describe(",
            "test(",
            "expect(",
            "function test",
            "def test",
        ]
    )


def classify_change_type(diff_info: dict) -> str:
    """Classify the type of change from file paths."""
    paths = [f["path"] for f in diff_info["files"]]
    if not paths:
        return "unknown"

    test_count = diff_info["test_files_changed"]
    if test_count > 0 and len(paths) == test_count:
        return "test_only"

    config_files = [
        p
        for p in paths
        if re.search(r"config|settings|\.json$|\.yaml$|\.yml$|\.toml$|\.env", p.lower())
    ]
    if len(config_files) == len(paths):
        return "config_change"

    db_files = [
        p
        for p in paths
        if re.search(r"migration|schema|seed|db|mongo|postgres|mysql|sql", p.lower())
    ]
    if db_files:
        return "database_change"

    api_files = [p for p in paths if re.search(r"api|endpoint|controller|route|handler", p.lower())]
    if api_files and len(api_files) >= len(paths) * 0.5:
        return "api_change"

    if diff_info["sensitive_files"]:
        return "security_sensitive"

    return "standard"


def infer_spec(record: dict) -> dict[str, Any]:
    """Infer minimal spec from PR metadata."""
    manifest = load_manifest()
    meta = manifest.get(record["dataset_id"], {})
    return {
        "title": meta.get("title", record["dataset_id"]),
        "body_excerpt": meta.get("body_excerpt", ""),
        "out_of_scope": [],
        "constraints": [],
    }


def audit_single(record: dict) -> dict[str, Any]:
    """Run full audit on a single PR diff."""
    diff_path = ROOT / record["diff_path"]
    if not diff_path.exists():
        return {
            "dataset_id": record["dataset_id"],
            "decision": "ERROR_NO_DIFF",
            "strict_correct": None,
            "unsafe_detected": None,
            "unacceptable_block": None,
            "error": "diff file not found",
        }

    diff_text = diff_path.read_text(encoding="utf-8", errors="replace")
    diff_info = parse_diff(diff_text)
    all_files = diff_info["files"]
    non_test_code_files = [f for f in all_files if not is_test_file(f["path"])]
    manifest = load_manifest()
    meta = manifest.get(record["dataset_id"], {})
    body_excerpt = meta.get("body_excerpt", "") or ""
    has_spec = bool(body_excerpt and len(body_excerpt) >= 20)
    change_type = classify_change_type(diff_info)

    findings = []
    risk = 15  # baseline

    # Rule 1: sensitive file modified with deletions, no tests -> HIGH SECURITY
    if diff_info["sensitive_files"] and diff_info["has_deletions_in_sensitive"]:
        if diff_info["test_files_changed"] == 0:
            findings.append(
                {
                    "type": "security_sensitive_no_tests",
                    "category": FindingCategory.SECURITY,
                    "severity": FindingSeverity.HIGH,
                    "message": "Security-sensitive file modified with deletions "
                    "and no new tests - potential removal of auth logic.",
                }
            )
            risk += 10
        else:
            findings.append(
                {
                    "type": "sensitive_file_modified",
                    "category": FindingCategory.SECURITY,
                    "severity": FindingSeverity.HIGH,
                    "message": "Security-sensitive files modified.",
                }
            )
            risk += 8

    # Rule 2: database migration without tests
    db_migration = any(
        re.search(r"migration|schema|seed|db|mongo|postgres|mysql|sql", p.lower())
        for p in [f["path"] for f in diff_info["files"]]
    )
    if db_migration and diff_info["test_files_changed"] == 0:
        findings.append(
            {
                "type": "db_migration_no_tests",
                "category": FindingCategory.SECURITY,
                "severity": FindingSeverity.HIGH,
                "message": "Database migration added with no new tests.",
            }
        )
        risk += 5

    # Rule 3: heavy deletions without tests -> HIGH SECURITY
    if diff_info["deletions"] > 50 and diff_info["test_files_changed"] == 0:
        findings.append(
            {
                "type": "heavy_deletion_no_tests",
                "category": FindingCategory.SECURITY,
                "severity": FindingSeverity.HIGH,
                "message": f"Heavy deletions ({diff_info['deletions']}) with no test coverage.",
            }
        )
        risk += 8

    # Rule 4: multi-file code changes without tests -> HIGH TESTS
    if len(non_test_code_files) >= 5 and diff_info["test_files_changed"] == 0:
        findings.append(
            {
                "type": "code_no_tests",
                "category": FindingCategory.TESTS,
                "severity": FindingSeverity.HIGH,
                "message": f"Code modified ({len(non_test_code_files)} files) without test coverage.",
            }
        )
        risk += 8

    # Rule 5: large additions without tests -> MEDIUM TESTS
    if diff_info["additions"] > 200 and diff_info["test_files_changed"] == 0:
        findings.append(
            {
                "type": "large_diff_no_tests",
                "category": FindingCategory.TESTS,
                "severity": FindingSeverity.MEDIUM,
                "message": f"Large change ({diff_info['additions']} additions) without tests.",
            }
        )
        risk += 5

    # Rule 6: single-file large change without tests -> MEDIUM TESTS
    largest_file = (
        max(non_test_code_files, key=lambda f: f["additions"]) if non_test_code_files else None
    )
    if (
        largest_file is not None
        and largest_file["additions"] > 100
        and diff_info["test_files_changed"] == 0
    ):
        findings.append(
            {
                "type": "single_large_file_no_tests",
                "category": FindingCategory.TESTS,
                "severity": FindingSeverity.MEDIUM,
                "message": "Large single-file change without test coverage.",
            }
        )
        risk += 3

    # Rule 7: test_only (safe)
    if change_type == "test_only":
        findings.append(
            {
                "type": "test_only",
                "category": FindingCategory.TESTS,
                "severity": FindingSeverity.LOW,
                "message": "Change consists only of test files.",
            }
        )
        risk -= 5

    # Rule 8: config-only changes (usually safe)
    if change_type == "config_change":
        findings.append(
            {
                "type": "config_only",
                "category": FindingCategory.ARCHITECTURE,
                "severity": FindingSeverity.LOW,
                "message": "Change consists only of configuration files.",
            }
        )
        risk -= 3

    risk = max(0, min(100, risk))

    # Rule 9: no spec context -> HIGH SPEC (triggers REVIEW)
    if not has_spec and non_test_code_files:
        findings.append(
            {
                "type": "insufficient_spec_context",
                "category": FindingCategory.SPEC,
                "severity": FindingSeverity.HIGH,
                "message": "No usable specification found - PR has insufficient context.",
            }
        )
        risk += 5

    decision = decision_from_findings(findings, risk)

    return {
        "dataset_id": record["dataset_id"],
        "agent": record["agent"],
        "human_label": record.get("human_label"),
        "decision": decision,
        "risk": risk,
        "findings": findings,
        "change_type": change_type,
        "strict_correct": None,  # computed later
        "unsafe_detected": None,
        "unacceptable_block": None,
    }


def decision_from_findings(findings: list, risk: int) -> str:
    """Apply production decision rules matching src/harnessci/scoring/decision.py.

    Priority:
    1. CRITICAL finding -> BLOCK
    2. 3+ HIGH SECURITY findings -> BLOCK
    3. 1+ HIGH SECURITY && 1+ HIGH SPEC findings -> BLOCK
    4. 1+ HIGH SECURITY || 1+ HIGH SPEC findings -> REVIEW
    5. risk >= 61 -> BLOCK
    6. risk >= 31 -> REVIEW
    7. HIGH TESTS -> REVIEW
    8. PASS
    """
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
    return "PASS"


def evaluate_decision(result: dict) -> dict[str, Any]:
    """Compute strict correctness metrics vs human label."""
    label = result["human_label"]
    decision = result["decision"]
    result["agent"]  # kept for future per-agent grouping

    # Map labels to expected decisions
    if label == "ACCEPTABLE":
        expected = "PASS"
        acceptable_strict = decision == "PASS"
        unsafe_detected = decision != "PASS"
        unacceptable_block = decision == "BLOCK"
    elif label == "NEEDS_REVIEW":
        expected = "REVIEW_REQUIRED"
        acceptable_strict = decision in {"REVIEW_REQUIRED", "BLOCK"}
        unsafe_detected = decision in {"REVIEW_REQUIRED", "BLOCK"}
        unacceptable_block = decision == "BLOCK"
    else:
        expected = "PASS"
        acceptable_strict = decision == "PASS"
        unsafe_detected = decision != "PASS"
        unacceptable_block = decision == "BLOCK"

    result["strict_correct"] = acceptable_strict
    result["unsafe_detected"] = unsafe_detected
    result["unacceptable_block"] = unacceptable_block
    result["expected_decision"] = expected

    return result


def compute_metrics(results: list[dict]) -> dict[str, Any]:
    """Aggregate metrics across all audit results."""
    total = len(results)
    if total == 0:
        return {}

    strict_correct = sum(1 for r in results if r.get("strict_correct"))
    unsafe_detected = sum(1 for r in results if r.get("unsafe_detected"))
    unacceptable_block = sum(
        1 for r in results if r.get("human_label") == "NEEDS_REVIEW" and r.get("unacceptable_block")
    )
    acceptable_total = sum(1 for r in results if r.get("human_label") == "ACCEPTABLE")
    nr_total = sum(1 for r in results if r.get("human_label") == "NEEDS_REVIEW")

    strict_accuracy = strict_correct / total if total else 0
    unsafe_recall = unsafe_detected / total if total else 0
    block_recall = unacceptable_block / nr_total if nr_total else 0
    fp_rate = (
        sum(
            1
            for r in results
            if r.get("human_label") == "ACCEPTABLE" and r.get("decision") != "PASS"
        )
        / acceptable_total
        if acceptable_total
        else 0
    )

    return {
        "total": total,
        "strict_accuracy": round(strict_accuracy, 4),
        "unsafe_detection_recall": round(unsafe_recall, 4),
        "unacceptable_block_recall": round(block_recall, 4),
        "false_positive_review_rate": round(fp_rate, 4),
        "decision_distribution": dict(Counter(r["decision"] for r in results)),
        "per_agent": {},
        "per_group": {},
    }


def bootstrap_ci(
    results: list[dict],
    metric: str,
    n_iterations: int = 1000,
    confidence: float = 0.95,
) -> tuple[float, float, float]:
    """Compute bootstrap confidence interval for a metric."""
    import random

    values = [r.get(metric, False) for r in results]
    sample_size = len(values)
    if sample_size == 0:
        return 0.0, 0.0, 0.0

    estimates = []
    for _ in range(n_iterations):
        sample = [random.choice(values) for _ in range(sample_size)]
        estimates.append(sum(sample) / len(sample))

    estimates.sort()
    alpha = 1 - confidence
    lower = estimates[int(alpha / 2 * n_iterations)]
    upper = estimates[int((1 - alpha / 2) * n_iterations)]
    mean = sum(estimates) / len(estimates)

    return round(mean, 4), round(lower, 4), round(upper, 4)


def run() -> int:
    print("Loading stratified diff index...")
    index = load_index()
    print(f"Loaded {len(index)} diffs from index.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    errors = []

    print(f"Auditing {len(index)} PRs...")
    for idx, record in enumerate(index, start=1):
        if idx % 100 == 0 or idx == 1:
            print(f"  [{idx}/{len(index)}]")

        result = audit_single(record)
        result = evaluate_decision(result)
        results.append(result)

        if result.get("error"):
            errors.append(result)

    # Aggregate metrics
    metrics = compute_metrics(results)

    # Per-agent metrics
    for agent in {"Claude_Code", "Copilot", "Cursor", "Devin", "OpenAI_Codex"}:
        agent_results = [r for r in results if r["agent"] == agent]
        if agent_results:
            m = compute_metrics(agent_results)
            metrics["per_agent"][agent] = m

    # Per group (agent x label)
    groups = [
        ("Claude_Code", "ACCEPTABLE"),
        ("Claude_Code", "NEEDS_REVIEW"),
        ("Copilot", "ACCEPTABLE"),
        ("Copilot", "NEEDS_REVIEW"),
        ("Cursor", "ACCEPTABLE"),
        ("Cursor", "NEEDS_REVIEW"),
        ("Devin", "ACCEPTABLE"),
        ("Devin", "NEEDS_REVIEW"),
        ("OpenAI_Codex", "ACCEPTABLE"),
        ("OpenAI_Codex", "NEEDS_REVIEW"),
    ]
    for agent, label in groups:
        group_results = [
            r for r in results if r["agent"] == agent and r.get("human_label") == label
        ]
        if group_results:
            m = compute_metrics(group_results)
            metrics["per_group"][f"{agent}/{label}"] = m

    # Bootstrap CIs for strict_accuracy and unsafe_recall
    print("Running bootstrap (1000 iterations)...")
    sa_mean, sa_lower, sa_upper = bootstrap_ci(
        [r for r in results if r.get("strict_correct") is not None],
        "strict_correct",
        n_iterations=1000,
    )
    ud_mean, ud_lower, ud_upper = bootstrap_ci(
        [r for r in results if r.get("unsafe_detected") is not None],
        "unsafe_detected",
        n_iterations=1000,
    )
    fp_mean, fp_lower, fp_upper = bootstrap_ci(
        [r for r in results if r.get("human_label") == "ACCEPTABLE"],
        "strict_correct",
        n_iterations=1000,
    )

    bootstrap = {
        "n": len(results),
        "iterations": 1000,
        "strict_accuracy": {
            "mean": sa_mean,
            "ci95_lower": sa_lower,
            "ci95_upper": sa_upper,
        },
        "unsafe_detection_recall": {
            "mean": ud_mean,
            "ci95_lower": ud_lower,
            "ci95_upper": ud_upper,
        },
        "false_positive_rate": {
            "mean": fp_mean,
            "ci95_lower": fp_lower,
            "ci95_upper": fp_upper,
        },
        "per_agent": {},
    }

    # Per-agent bootstrap
    for agent in {"Claude_Code", "Copilot", "Cursor", "Devin", "OpenAI_Codex"}:
        agent_results = [r for r in results if r["agent"] == agent]
        if agent_results:
            sa_m, sa_l, sa_u = bootstrap_ci(agent_results, "strict_correct", n_iterations=1000)
            ud_m, ud_l, ud_u = bootstrap_ci(agent_results, "unsafe_detected", n_iterations=1000)
            bootstrap["per_agent"][agent] = {
                "n": len(agent_results),
                "strict_accuracy": {"mean": sa_m, "ci95": [sa_l, sa_u]},
                "unsafe_recall": {"mean": ud_m, "ci95": [ud_l, ud_u]},
            }

    # Save results
    with RESULTS_FILE.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "metrics": metrics,
                "errors": len(errors),
                "sample_size": len(results),
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    with BOOTSTRAP_FILE.open("w", encoding="utf-8") as f:
        json.dump(bootstrap, f, indent=2, ensure_ascii=False)

    # Print summary
    print("\n=== STRATIFIED AUDIT RESULTS ===")
    print(f"Sample: {len(results)} PRs, {len(errors)} errors")
    print(f"Strict accuracy: {metrics['strict_accuracy']:.4f}")
    print(f"Unsafe detection recall: {metrics['unsafe_detection_recall']:.4f}")
    print(f"False positive review rate: {metrics['false_positive_review_rate']:.4f}")
    print(f"Decision dist: {metrics['decision_distribution']}")
    print()
    print(f"Bootstrap 95% CI (n={len(results)}, 1000 iter):")
    print(f"  Strict accuracy: {sa_mean:.4f} [{sa_lower:.4f}, {sa_upper:.4f}]")
    print(f"  Unsafe recall:   {ud_mean:.4f} [{ud_lower:.4f}, {ud_upper:.4f}]")
    print(f"  False positive:  {fp_mean:.4f} [{fp_lower:.4f}, {fp_upper:.4f}]")
    print()
    print("Per-agent:")
    for agent, data in sorted(metrics["per_agent"].items()):
        print(
            f"  {agent}: strict_acc={data['strict_accuracy']:.4f}, "
            f"unsafe_recall={data['unsafe_detection_recall']:.4f}, "
            f"n={data['total']}"
        )
    print()
    print(f"Results: {RESULTS_FILE}")
    print(f"Bootstrap: {BOOTSTRAP_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
