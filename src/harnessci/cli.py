"""HarnessCI command-line interface.

Entry point: harnessci audit --base <rev> --head <rev> [options]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .audit import run_audit
from .errors import HarnessCIError
from .report import render_json, render_markdown

# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harnessci",
        description="CI for AI-generated Pull Requests.",
    )
    sub = parser.add_subparsers(dest="command")

    audit_p = sub.add_parser("audit", help="Audit a local git diff against a spec.")
    audit_p.add_argument("--base", required=True, metavar="REV", help="Base git revision.")
    audit_p.add_argument("--head", required=True, metavar="REV", help="Head git revision.")
    audit_p.add_argument("--spec", metavar="PATH", help="Path to spec/task markdown file.")
    audit_p.add_argument("--output", metavar="FILE", help="Write JSON report to FILE.")
    audit_p.add_argument("--markdown-output", metavar="FILE", help="Write Markdown report to FILE.")
    audit_p.add_argument("--config", metavar="FILE", help="Path to harnessci.yaml config file.")

    return parser


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the harnessci CLI."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "audit":
        _cmd_audit(args)


def _cmd_audit(args: argparse.Namespace) -> None:
    """Execute the audit sub-command."""
    from .config import load_config  # local import; avoids circular at module level

    try:
        config = load_config(args.config if args.config else None)
        report = run_audit(
            base_rev=args.base,
            head_rev=args.head,
            spec_path=args.spec,
            config=config,
        )
    except HarnessCIError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # stdout summary
    print(f"Decision: {report.decision}  Risk: {report.overall_agentic_risk}/100")

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
