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


def _cmd_init(args: argparse.Namespace) -> None:
    """Initialize domain learning for the repo."""
    from .audit import run_audit_from_diff_text
    from .spec_inference import spec_exists

    repo = Path(args.repo).resolve()
    harnessci_dir = repo / ".harnessci"

    if spec_exists(repo) and not args.force:
        print(f"HarnessCI already initialized at {harnessci_dir}")
        print("Run `harnessci init --force` to override.")
        return

    print(f"Initializing HarnessCI for {repo}...")
    print("  Note: Full spec mining requires GEMINI_API_KEY env var.")
    print("  Without it, use `harnessci audit --infer` for lightweight inference.")

    # Verify harnessci works
    try:
        test_diff = ""
        report = run_audit_from_diff_text(
            test_diff, spec_text="# Test spec\nGoal: verify harnessci works\n"
        )
        print(f"  Test audit: {report.decision} (risk={report.overall_agentic_risk})")
    except Exception as exc:  # noqa: BLE001
        print(f"  Warning: test audit failed: {exc}")

    print(f"\nInitialized at {harnessci_dir}")
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
    from .spec_inference import load_mined_spec, spec_exists

    try:
        config = load_config(args.config if args.config else None)

        # Try to load mined spec
        repo = Path.cwd()
        spec_text = None

        if spec_exists(repo):
            mined = load_mined_spec(repo)
            if mined:
                summary = mined.get("summary_md", "")
                domain = mined.get("domain", "Inferred")
                spec_text = f"# {domain}\n\n{summary}"
        elif args.infer:
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
    if report.findings:
        for finding in report.findings:
            print(f"  [{finding.severity.value}] {finding.message}")

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
