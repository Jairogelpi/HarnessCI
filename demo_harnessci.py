#!/usr/bin/env python3
"""
HarnessCI Demo: Complete feature showcase

Run with: py demo_harnessci.py

Shows:
1. Audit with NL explanations and PR summary
2. Bug pattern detection
3. Multi-platform adapters
4. Feedback learning system
"""

from src.harnessci.audit import run_audit_from_diff_text
from src.harnessci.detection import BugPatternDetector, detect_bugs
from src.harnessci.feedback import FeedbackTracker, load_tracker
from src.harnessci.platform import get_adapter, VCSPlatform
from src.harnessci.nlp import NLGenerator, generate_explanations, generate_pr_summary

print("=" * 60)
print("HARNESSCI FEATURE DEMO")
print("=" * 60)

# ---------------------------------------------------------------------------
# 1. Audit with NL explanations and PR summary
# ---------------------------------------------------------------------------
print("\n[1] AUDIT WITH NL EXPLANATIONS + PR SUMMARY")
print("-" * 40)

diff_security = """diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -1,8 +1,10 @@
 def authenticate(user, password):
+    secret_key = "hunter2"
     if user == 'admin' and password == 'secret':
         return True
     return False

 def get_user_data(user_id):
     query = f"SELECT * FROM users WHERE id={user_id}"
     os.system("rm -rf /tmp/cache")
     return data
"""

report = run_audit_from_diff_text(diff_security)
print(f"  Decision: {report.decision}")
print(f"  Risk: {report.overall_agentic_risk}/100")
print(f"  Bug patterns detected: {report.bug_pattern_matches}")
if report.nl_summary:
    print(f"  NL Summary: {report.nl_summary.get('summary', 'N/A')}")
    print(f"  Tests: {report.nl_summary.get('tests', 'N/A')}")
    print(f"  Security: {report.nl_summary.get('security', 'N/A')}")
print(f"  Findings ({len(report.findings)}):")
for i, f in enumerate(report.findings):
    print(f"    {i+1}. [{f.severity.value}] {f.message}")
    if f.explanation:
        print(f"       -> {f.explanation}")

# ---------------------------------------------------------------------------
# 2. Bug pattern detection
# ---------------------------------------------------------------------------
print("\n[2] BUG PATTERN DETECTION")
print("-" * 40)

diff_bugs = """diff --git a/src/api.py b/src/api.py
--- a/src/api.py
+++ b/src/api.py
@@ -1,15 +1,20 @@
 import os
 import subprocess

 def process_input(user_input):
     # TODO: fix this later
     cmd = f"echo {user_input}"
     os.system(cmd)
     password = "hunter2"
     exec(user_input)
     return

 def broken():
     try:
         x = 1/0
     except:
         pass
"""

detector = BugPatternDetector()
report = detector.detect(diff_bugs, file_paths=["src/api.py"])
print(f"  Total matches: {report.total}")
print(f"  Summary: {report.summary}")
for m in report.matches:
    print(f"  [{m.severity.upper()}] {m.pattern_name} in {m.file_path}")
    print(f"      -> {m.matched_text[:80]}")

# ---------------------------------------------------------------------------
# 3. Multi-platform adapters
# ---------------------------------------------------------------------------
print("\n[3] MULTI-PLATFORM ADAPTERS")
print("-" * 40)

platforms = ["github", "gitlab", "bitbucket", "azure"]
for p in platforms:
    try:
        adapter = get_adapter(p)
        print(f"  OK: {p} - {adapter.name}")
        print(f"      Base URL: {adapter.BASE_URL}")
    except Exception as e:
        print(f"  FAIL: {p} - {e}")

# ---------------------------------------------------------------------------
# 4. Feedback learning system
# ---------------------------------------------------------------------------
print("\n[4] FEEDBACK LEARNING SYSTEM")
print("-" * 40)

tracker = FeedbackTracker(repo="demo-repo")

# Record some fake feedback
tracker.record_dismiss(
    pr_id="123",
    finding_key="security:high:hardcoded_secret",
    reason="False positive — test credential",
    reviewer="jairo"
)
tracker.record_accepted(
    pr_id="123",
    finding_key="security:critical:command_injection",
    reviewer="jairo"
)

# Show summary
summary = tracker.get_summary()
print(f"  Total events: {summary['total_events']}")
print(f"  Dismissed: {summary['total_dismissed']}")
print(f"  Dismiss rate: {summary['dismiss_rate']:.1%}")
print(f"  Adapted threshold: {summary['adapted_threshold']}")

# Adapt threshold
new_threshold = tracker.adapt_threshold()
print(f"  New adapted threshold: {new_threshold}")

# ---------------------------------------------------------------------------
# 5. NL Generator standalone
# ---------------------------------------------------------------------------
print("\n[5] NL GENERATOR (standalone)")
print("-" * 40)

findings = [
    {"severity": "high", "category": "security", "message": "Hardcoded secret detected", "evidence": "src/auth.py:3"},
    {"severity": "critical", "category": "security", "message": "SQL injection vulnerability", "evidence": "src/api.py:10"},
    {"severity": "medium", "category": "quality", "message": "Empty except block", "evidence": "src/utils.py:25"},
]

explanations = generate_explanations(findings)
print(f"  Generated {len(explanations)} explanations:")
for i, exp in enumerate(explanations):
    print(f"    {i+1}. {exp[:100]}...")

pr_summary = generate_pr_summary(
    diff_text="[truncated diff...]",
    decision="REVIEW_REQUIRED",
    risk_score=45,
    findings=findings
)
print(f"\n  PR Summary:")
for key, val in pr_summary.items():
    print(f"    {key}: {val}")

print("\n" + "=" * 60)
print("DEMO COMPLETE")
print("=" * 60)
print("""
Next steps:
  harnessci init --repo .        # Mine spec with Groq
  harnessci audit --base HEAD~1 --head HEAD  # Audit current PR
  harnessci feedback --pr #123 --dismiss security:high:hardcoded_secret
  harnessci feedback --summary     # Show feedback summary
""")