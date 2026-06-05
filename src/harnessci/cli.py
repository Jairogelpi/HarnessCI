"""HarnessCI command-line interface.

Entry points:
  harnessci init          Initialize domain learning for a repo
  harnessci audit         Audit a PR
  harnessci update        Re-mine spec if repo changed
  harnessci status        Show current spec learning status
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .errors import HarnessCIError

# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harnessci",
        description="CI for AI-generated Pull Requests.",
    )
    sub = parser.add_subparsers(dest="command")

    # init
    init_p = sub.add_parser("init", help="Initialize HarnessCI domain learning for this repo.")
    init_p.add_argument("--repo", default=".", help="Repo root (default: current directory).")
    init_p.add_argument("--force", action="store_true", help="Re-mine even if spec exists.")

    # update
    update_p = sub.add_parser("update", help="Re-mine spec if repo changed.")
    update_p.add_argument("--repo", default=".", help="Repo root (default: current directory).")

    # audit
    audit_p = sub.add_parser("audit", help="Audit a PR.")
    audit_p.add_argument("--base", required=True, metavar="REV", help="Base git revision.")
    audit_p.add_argument("--head", required=True, metavar="REV", help="Head git revision.")
    audit_p.add_argument("--spec", metavar="PATH", help="Path to spec/task markdown file.")
    audit_p.add_argument("--output", metavar="FILE", help="Write JSON report to FILE.")
    audit_p.add_argument("--markdown-output", metavar="FILE", help="Write Markdown report to FILE.")
    audit_p.add_argument("--config", metavar="FILE", help="Path to harnessci.yaml config file.")
    audit_p.add_argument(
        "--infer",
        action="store_true",
        help="If no spec found, infer lightweight spec from PR context.",
    )

    # status
    status_p = sub.add_parser("status", help="Show HarnessCI domain learning status.")
    status_p.add_argument("--repo", default=".", help="Repo root (default: current directory).")

    # feedback
    feedback_p = sub.add_parser("feedback", help="Record feedback on audit findings.")
    feedback_p.add_argument(
        "--pr", required=True, help="PR identifier (e.g. #123 or owner/repo#123)."
    )
    feedback_p.add_argument(
        "--dismiss",
        metavar="FINDING_KEY",
        nargs="+",
        help="Dismiss finding keys (e.g. 'security:high:sql_injection').",
    )
    feedback_p.add_argument(
        "--accept", metavar="FINDING_KEY", nargs="+", help="Accept finding keys as valid."
    )
    feedback_p.add_argument("--repo", default=".", help="Repo root (default: current directory).")
    feedback_p.add_argument("--reason", help="Reason for dismissal.")
    feedback_p.add_argument("--reviewer", help="Reviewer identifier.")
    feedback_p.add_argument(
        "--summary", action="store_true", help="Show feedback summary for repo."
    )

    return parser


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "init":
        _cmd_init(args)
    elif args.command == "update":
        _cmd_update(args)
    elif args.command == "audit":
        _cmd_audit(args)
    elif args.command == "status":
        _cmd_status(args)
    elif args.command == "feedback":
        _cmd_feedback(args)


def _cmd_init(args: argparse.Namespace) -> None:
    """Initialize domain learning for the repo with Groq spec mining."""
    from .spec.miner import create_llm_client, mine_spec
    from .spec_inference import harnessci_dir as get_harnessci_dir
    from .spec_inference import save_mined_spec, save_spec_hash, spec_exists

    repo = Path(args.repo).resolve()
    hdir = get_harnessci_dir(repo)

    if spec_exists(repo) and not args.force:
        print(f"HarnessCI already initialized at {hdir}")
        print("Run `harnessci init --force` to override.")
        return

    print(f"Initializing HarnessCI for {repo}...")
    print("  Mining spec with Groq Llama 3.1...")

    # Try Groq spec mining
    client = create_llm_client()
    if client is None or not client.available:
        print("  WARNING: GROQ_API_KEY not set. Spec mining skipped.")
        print("  Run `harnessci init --force` with GROQ_API_KEY to mine spec.")
    else:
        spec, summary = mine_spec(repo, client)
        if spec.get("domain") != "unknown":
            save_mined_spec(spec, repo, summary_md=summary)
            # Try semantic indexing
            try:
                from .semantic.indexer import index_repo
                from .semantic.store import is_available as vec_available

                if vec_available():
                    db_path = hdir / "vectors.db"
                    count = index_repo(repo, spec, db_path)
                    print(f"  Indexed {count} domain patterns.")
            except Exception:  # noqa: BLE001
                pass
            print(f"  Domain: {spec.get('domain')}")
            print(f"  Entities: {len(spec.get('entities', []))}")
            print(f"  Conventions: {list(spec.get('conventions', {}).keys())}")
        else:
            print("  WARNING: Spec mining failed (invalid response).")

    # Save git hash
    import subprocess

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    current_hash = result.stdout.strip() if result.returncode == 0 else ""
    if current_hash:
        save_spec_hash(repo, current_hash)

    print(f"\nInitialized at {hdir}")
    print("Run `harnessci status` to check state.")


def _cmd_update(args: argparse.Namespace) -> None:
    """Check if re-mining is needed."""
    from .spec_inference import get_spec_hash, spec_exists

    repo = Path(args.repo).resolve()
    print(f"Checking spec state for {repo}...")

    if not spec_exists(repo):
        print("No spec found. Run `harnessci init` first.")
        return

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    current_hash = result.stdout.strip() if result.returncode == 0 else ""
    saved_hash = get_spec_hash(repo)

    if current_hash == saved_hash:
        print("Repo unchanged since last mining.")
        print("Run `harnessci init --force` to re-mine.")
    else:
        print(f"Repo changed since last mining ({saved_hash} -> {current_hash})")
        print("Run `harnessci init --force` to re-mine spec.")


def _cmd_audit(args: argparse.Namespace) -> None:
    """Execute the audit sub-command."""
    from .audit import run_audit
    from .config import load_config
    from .report import render_json, render_markdown

    try:
        config = load_config(args.config if args.config else None)

        # Let audit auto-detect mined spec (zero-config)
        # Only pass spec_text when explicitly provided via --infer or --spec
        spec_text = None
        if args.infer:
            spec_text = (
                "# Auto-inferred spec\n\n"
                "Inferred from diff context. Run `harnessci init` for full learning."
            )

        report = run_audit(
            base_rev=args.base,
            head_rev=args.head,
            spec_path=args.spec,
            spec_text=spec_text,
            config=config,
        )

    except HarnessCIError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # stdout summary
    print(f"Decision: {report.decision}  Risk: {report.overall_agentic_risk}/100")
    if report.nl_summary:
        print(f"  Summary: {report.nl_summary.get('summary', '')}")
        print(f"  Tests: {report.nl_summary.get('tests', 'unknown')}")
        if report.nl_summary.get("security") and report.nl_summary["security"] != "None":
            print(f"  Security: {report.nl_summary['security']}")
    if report.bug_pattern_matches is not None and report.bug_pattern_matches > 0:
        print(f"  Bug patterns detected: {report.bug_pattern_matches}")
    if report.findings:
        for i, finding in enumerate(report.findings):
            sev = finding.severity.value.upper()
            msg = finding.message
            if finding.explanation:
                print(f"  {i + 1}. [{sev}] {msg}")
                print(f"     → {finding.explanation}")
            else:
                print(f"  {i + 1}. [{sev}] {msg}")

    # JSON output
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_json(report), encoding="utf-8")
        print(f"JSON report: {out_path}", file=sys.stderr)

    # Markdown output
    if hasattr(args, "markdown_output") and args.markdown_output:
        md_path = Path(args.markdown_output)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_markdown(report), encoding="utf-8")
        print(f"Markdown report: {md_path}", file=sys.stderr)


def _cmd_status(args: argparse.Namespace) -> None:
    """Show HarnessCI status."""
    from .spec_inference import get_spec_hash, spec_exists, spec_json_path

    repo = Path(args.repo).resolve()
    harnessci_dir = repo / ".harnessci"

    print(f"HarnessCI status for {repo}")
    print()

    if spec_exists(repo):
        spec_path = spec_json_path(repo)
        saved_hash = get_spec_hash(repo)

        try:
            spec_data = json.loads(spec_path.read_text(encoding="utf-8"))
            print(f"  Domain: {spec_data.get('domain', 'unknown')}")
            print(f"  Entities: {len(spec_data.get('entities', []))}")
            print(f"  Conventions: {list(spec_data.get('conventions', {}).keys())}")
            print(f"  Security invariants: {len(spec_data.get('security_invariants', []))}")
            print(f"  Spec file: {spec_path}")
            print(f"  Last mined: {saved_hash or 'unknown'}")
        except Exception as exc:  # noqa: BLE001
            print(f"  Error reading spec: {exc}")
    else:
        print("  Not initialized (no .harnessci/spec.json)")
        print("  Run `harnessci init` to start domain learning.")

    print()
    inited = harnessci_dir.exists()
    print(f"  .harnessci/ dir: {'exists' if inited else 'missing'}")
    if inited:
        for f in sorted(harnessci_dir.iterdir()):
            print(f"    {f.name}")


def _cmd_feedback(args: argparse.Namespace) -> None:
    """Record or show feedback on audit findings."""
    from .feedback import FeedbackTracker

    repo = Path(args.repo).resolve()
    tracker = FeedbackTracker(repo=str(repo))

    if args.summary:
        summary = tracker.get_summary()
        print(f"Feedback summary for {summary['repo']}")
        print(f"  Total events: {summary['total_events']}")
        print(f"  Dismissed: {summary['total_dismissed']}")
        print(f"  Dismiss rate: {summary['dismiss_rate']:.1%}")
        print(f"  Adapted threshold: {summary['adapted_threshold']}")
        if summary.get("top_dismissed_patterns"):
            print("  Top dismissed patterns:")
            for p in summary["top_dismissed_patterns"]:
                print(f"    {p['finding_key']}: {p['dismissed']} dismissed ({p['rate']:.0%})")
        return

    pr_id = args.pr
    reason = args.reason or ""
    reviewer = args.reviewer

    if args.dismiss:
        for key in args.dismiss:
            tracker.record_dismiss(pr_id=pr_id, finding_key=key, reason=reason, reviewer=reviewer)
            print(f"Dismissed: {key}")
        print("Feedback recorded.")

    if args.accept:
        for key in args.accept:
            tracker.record_accepted(pr_id=pr_id, finding_key=key, reviewer=reviewer)
            print(f"Accepted: {key}")
        print("Feedback recorded.")

    # Adapt threshold based on accumulated feedback
    new_threshold = tracker.adapt_threshold()
    print(f"Adapted risk threshold: {new_threshold}")
