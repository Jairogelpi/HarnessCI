#!/bin/sh
set -e

# ---------------------------------------------------------------------------
# HarnessCI GitHub Action entrypoint
# ---------------------------------------------------------------------------

REPO_DIR="/github/workspace"

# Resolve base and head refs
BASE_REF="${INPUT_BASE_REF:-${GITHUB_BASE_REF:-}}"
HEAD_REF="${INPUT_HEAD_REF:-${GITHUB_HEAD_REF:-${GITHUB_SHA:-HEAD}}}"

# If running on a PR event, extract from event payload
if [ -z "$BASE_REF" ] && [ -f "$GITHUB_EVENT_PATH" ]; then
  BASE_REF=$(python3 -c "
import json, sys
try:
    e = json.load(open('$GITHUB_EVENT_PATH'))
    base = e.get('pull_request', {}).get('base', {}).get('sha', '')
    head = e.get('pull_request', {}).get('head', {}).get('sha', '')
    print(base + ':' + head)
except Exception as ex:
    print(':')
" 2>/dev/null || echo ":")
  EXTRACTED_HEAD="${BASE_REF##*:}"
  BASE_REF="${BASE_REF%%:*}"
  if [ -n "$EXTRACTED_HEAD" ]; then
    HEAD_REF="$EXTRACTED_HEAD"
  fi
fi

# Fallback: compare HEAD~1 to HEAD if still empty
if [ -z "$BASE_REF" ]; then
  echo "[harnessci] No base ref found, defaulting to HEAD~1"
  BASE_REF="HEAD~1"
fi

if [ -z "$HEAD_REF" ]; then
  HEAD_REF="HEAD"
fi

echo "[harnessci] base=$BASE_REF  head=$HEAD_REF"
echo "[harnessci] spec=${INPUT_SPEC_PATH:-none}  config=${INPUT_CONFIG:-harnessci.yaml}"

# Build CLI command
CMD="python -m harnessci.cli audit --base $BASE_REF --head $HEAD_REF"

if [ -n "$INPUT_SPEC_PATH" ]; then
  CMD="$CMD --spec $INPUT_SPEC_PATH"
fi

if [ -n "$INPUT_CONFIG" ] && [ -f "$REPO_DIR/$INPUT_CONFIG" ]; then
  CMD="$CMD --config $REPO_DIR/$INPUT_CONFIG"
fi

OUTPUT_JSON="${INPUT_OUTPUT_JSON:-harnessci-report.json}"
OUTPUT_MD="${INPUT_OUTPUT_MARKDOWN:-harnessci-report.md}"

CMD="$CMD --output $REPO_DIR/$OUTPUT_JSON --markdown-output $REPO_DIR/$OUTPUT_MD"

# Run audit from the repo directory
cd "$REPO_DIR"
echo "[harnessci] Running: $CMD"
$CMD

# Read decision and risk from JSON report
DECISION=$(python3 -c "
import json, sys
try:
    r = json.load(open('$OUTPUT_JSON'))
    print(r.get('decision', 'INSUFFICIENT_INFORMATION'))
except:
    print('INSUFFICIENT_INFORMATION')
" 2>/dev/null || echo "INSUFFICIENT_INFORMATION")

RISK=$(python3 -c "
import json, sys
try:
    r = json.load(open('$OUTPUT_JSON'))
    print(r.get('overall_agentic_risk', 100))
except:
    print(100)
" 2>/dev/null || echo "100")

echo "[harnessci] Decision: $DECISION  Risk: $RISK/100"

# Set GitHub Action outputs
echo "decision=$DECISION" >> "$GITHUB_OUTPUT"
echo "overall-risk=$RISK" >> "$GITHUB_OUTPUT"
echo "report-json=$REPO_DIR/$OUTPUT_JSON" >> "$GITHUB_OUTPUT"
echo "report-markdown=$REPO_DIR/$OUTPUT_MD" >> "$GITHUB_OUTPUT"

# Post PR comment if token is available
if [ -n "$INPUT_GITHUB_TOKEN" ] && [ -f "$GITHUB_EVENT_PATH" ]; then
  PR_NUMBER=$(python3 -c "
import json, sys
try:
    e = json.load(open('$GITHUB_EVENT_PATH'))
    print(e.get('pull_request', {}).get('number', ''))
except:
    print('')
" 2>/dev/null || echo "")

  if [ -n "$PR_NUMBER" ] && [ -f "$REPO_DIR/$OUTPUT_MD" ]; then
    echo "[harnessci] Posting comment to PR #$PR_NUMBER"
    python3 -c "
import json, os, urllib.request, urllib.error

token = os.environ.get('INPUT_GITHUB_TOKEN', '')
repo  = os.environ.get('GITHUB_REPOSITORY', '')
pr    = '$PR_NUMBER'

if not token or not repo or not pr:
    print('[harnessci] Skipping comment: missing token, repo, or PR number')
    exit(0)

try:
    with open('$REPO_DIR/$OUTPUT_MD', encoding='utf-8') as f:
        body = f.read()
except Exception as e:
    print(f'[harnessci] Could not read markdown report: {e}')
    exit(0)

url  = f'https://api.github.com/repos/{repo}/issues/{pr}/comments'
data = json.dumps({'body': body}).encode('utf-8')
req  = urllib.request.Request(url, data=data, method='POST')
req.add_header('Authorization', f'Bearer {token}')
req.add_header('Content-Type', 'application/json')
req.add_header('Accept', 'application/vnd.github+json')
req.add_header('X-GitHub-Api-Version', '2022-11-28')

try:
    with urllib.request.urlopen(req) as resp:
        print(f'[harnessci] Comment posted (HTTP {resp.status})')
except urllib.error.HTTPError as e:
    print(f'[harnessci] Failed to post comment: HTTP {e.code} {e.reason}')
except Exception as e:
    print(f'[harnessci] Failed to post comment: {e}')
" 2>&1 || true
  fi
fi

# Fail check if decision is BLOCK and fail-on-block is enabled
if [ "$INPUT_FAIL_ON_BLOCK" = "true" ] && [ "$DECISION" = "BLOCK" ]; then
  echo "[harnessci] Decision is BLOCK — failing the check."
  exit 1
fi

exit 0
