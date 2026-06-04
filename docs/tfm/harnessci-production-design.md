# HarnessCI: Spec Inference + Semantic Domain Learning

> Production design. June 2026.
> **Goal:** Zero-config for any project. Connect repo → learn domain → audit PRs.

## Problem

Current HarnessCI uses hardcoded keywords for:
- Architecture drift detection (only matches known domains: auth, billing, frontend)
- Spec violation detection (string matching against out_of_scope in YAML)

**Consequences:** 4/13 errors in Layer 2 from wrong drift detection. System only works for pre-configured domains.

**Root cause:** No domain learning. The system doesn't understand the repo it's auditing.

## Vision

```
git clone repo
harnessci init --repo .
# → LLM extracts spec from code + docs + patterns
# → Embeddings index domain knowledge
# → PR arrives → diff verified against learned spec + embeddings

Zero manual spec authoring. Works on any project.
```

---

## Architecture

### Components

```
src/harnessci/
  spec/
    miner.py          # LLM extracts spec from repo (one-shot or incremental)
    store.py          # Persist spec to .harnessci/spec.json + .harnessci/spec.md
    verifier.py       # Verify diff against mined spec (deterministic rules)
    loader.py         # Load spec for audit (from file, or inference on the fly)
  semantic/
    indexer.py        # Generate embeddings from domain patterns
    matcher.py        # Cosine similarity → drift score
    store.py          # sqlite-vec local vector store
  audit.py            # Extended: uses spec miner + semantic indexer
  cli.py              # harnessci init / audit / status commands
.github/
  workflows/
    harnessci.yml    # GitHub Action: run audit on PR

docs/
  SPEC.md             # Human-readable spec (from miner output)
datasets/             # (unchanged)
tests/                # (unchanged)
```

### Data flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     harnessci init --repo .                      │
│                                                                  │
│  Repo files ──► Miner (LLM) ──► spec.json + spec.md            │
│       │                    │                                     │
│       └─► Indexer ──► sqlite-vec (embeddings)                  │
│                      │                                          │
│                      ▼                                          │
│               .harnessci/ (local state)                         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                       PR arrives                                 │
│                                                                  │
│  Diff ──► Verifier (spec.json) ──► spec findings                │
│      └─► Matcher (embeddings) ──► drift score                   │
│      └─► Audit existing rules ──► all findings                  │
│                                                                  │
│      └─► Decision: PASS / REVIEW_REQUIRED / BLOCK              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Spec Miner

### What it extracts

The LLM analyzes the repo and produces a structured JSON spec:

```json
{
  "version": "1.0",
  "domain": "e-commerce platform with FastAPI + React",
  "entities": [
    {"name": "Product", "files": ["models/product.py", "api/products.py"], " invariants": ["id is UUID", "price > 0"]},
    {"name": "Order", "files": ["models/order.py", "services/checkout.py"], "invariants": ["total = sum(items)"]}
  ],
  "conventions": {
    "naming": "snake_case for Python, kebab-case for React",
    "api": "REST with /api/v{version}/ prefix",
    "auth": "JWT in Authorization header"
  },
  "forbidden_paths": [
    "src/admin/secrets.py",
    "config/production.yaml"
  ],
  "allowed_test_patterns": ["tests/", "*_test.py", "*.spec.ts"],
  "architecture": {
    "layers": ["api", "services", "models", "db"],
    "dependencies": "api → services → models → db"
  },
  "security_invariants": [
    "never expose raw SQL",
    "auth required for /api/*",
    "no secrets in code"
  ],
  "summary_md": "## Domain Overview\n\nThis is an e-commerce platform..."
}
```

### Extraction prompt

```
Analyze this codebase and extract a structured specification.

Focus on:
1. **Domain**: What does this project do?
2. **Entities**: Core domain objects and their files
3. **Invariants**: Rules that must always hold (e.g., price > 0)
4. **Conventions**: Naming, API patterns, directory structure
5. **Forbidden paths**: Files that should never be modified
6. **Architecture**: Layer boundaries and dependencies
7. **Security rules**: Non-negotiable security requirements

Output valid JSON matching the schema. Be concise.
Repository root: {root_path}
```

### Implementation

```python
def mine_spec(root: Path, llm_client) -> tuple[SpecDict, str]:
    # Phase 1: Quick scan (files, structure, README, package.json)
    repo_summary = _scan_structure(root)
    
    # Phase 2: Deep analysis on key files (top 20 by importance)
    key_files = _select_key_files(root, n=20)
    
    # Phase 3: LLM extraction
    prompt = _build_mining_prompt(repo_summary, key_files)
    response = llm_client.complete(prompt)
    
    spec = json.loads(response)
    summary_md = spec.pop("summary_md", "")
    
    return spec, summary_md
```

### Incremental updates

- On `harnessci init`: full extraction
- On `harnessci update`: re-run if repo changed (detect via git hash)
- On PR audit: if no spec found, infer from PR context (title, description, diff)

---

## Semantic Indexer

### What it indexes

Pattern embeddings from:
- Entity file paths and their content summary
- Function/variable naming patterns
- Directory structure semantics
- README + documentation
- Test file patterns

### Implementation (sqlite-vec)

```python
import sqlite_vec

def index_repo(root: Path, embedder) -> None:
    db_path = root / ".harnessci" / "vectors.db"
    
    with sqlite_vec.connect(db_path) as conn:
        sqlite_vec.load_module(conn)
        
        # Index entity patterns
        for entity in spec["entities"]:
            path_embedding = embedder.embed(entity["name"] + " " + " ".join(entity["files"]))
            sqlite_vec.execute(
                conn,
                "INSERT INTO embeddings VALUES (?)",
                [path_embedding.tolist()]
            )
        
        # Index convention patterns
        for convention in spec["conventions"]:
            conv_embedding = embedder.embed(str(convention))
            sqlite_vec.execute(...)
```

### Drift detection

```python
def detect_drift(diff: DiffFeatures, index_db: Path, embedder, threshold=0.7) -> list[DriftSignal]:
    # Embed changed files
    changed_text = " ".join(f.path for f in diff.files)
    diff_embedding = embedder.embed(changed_text)
    
    # Query for similar patterns
    with sqlite_vec.connect(index_db) as conn:
        results = sqlite_vec.execute(
            conn,
            "SELECT rowid, distance FROM embeddings WHERE embedding MATCH ? ORDER BY distance LIMIT 5",
            [diff_embedding.tolist()]
        )
    
    # If no similar patterns found → potential drift
    if not results or results[0]["distance"] > threshold:
        return [DriftSignal(type="new_pattern", severity="medium", evidence=changed_text)]
    
    return []
```

---

## Spec Verifier

Deterministic rules check diff against mined spec:

```python
def verify_diff(diff: DiffFeatures, spec: SpecDict) -> list[Finding]:
    findings = []
    
    # Forbidden path violations
    for path in spec.get("forbidden_paths", []):
        if any(path in f.path for f in diff.files):
            findings.append(Finding(severity=CRITICAL, category=SECURITY,
                message=f"Forbidden path modified: {path}"))
    
    # Architecture layer violations
    expected_deps = spec.get("architecture", {}).get("dependencies", "")
    layers = spec.get("architecture", {}).get("layers", [])
    # Check: no layer imports a layer below it
    
    # Entity invariant violations (via LLM check)
    for entity in spec.get("entities", []):
        entity_files = [f for f in diff.files if any(ef in f.path for ef in entity["files"])]
        if entity_files:
            # Light LLM check: does this change violate {entity.invariants}?
            violation = _check_invariant(entity, entity_files, llm_client)
            if violation:
                findings.append(Finding(severity=HIGH, category=ARCHITECTURE,
                    message=f"{entity['name']} invariant violated: {violation}"))
    
    # Naming convention violations
    naming = spec.get("conventions", {}).get("naming", "")
    if naming == "snake_case":
        violations = [f for f in diff.files if _has_camel_case(f.path) and not f.is_test]
        if violations:
            findings.append(Finding(severity=LOW, category=STYLE,
                message=f"Naming convention violated: {violations}"))
    
    return findings
```

---

## CLI

```bash
# Initialize repo (extract spec + index)
harnessci init --repo .

# Run audit on PR (local diff)
harnessci audit --diff ./mychanges.diff

# Update spec (re-mine if repo changed)
harnessci update --repo .

# Show current spec
harnessci spec --show

# Show domain embeddings status
harnessci status
```

### GitHub Action

```yaml
name: HarnessCI Audit
on: [pull_request]
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install HarnessCI
        run: pip install harnessci
      - name: Init (if not done)
        run: harnessci init || echo "Already initialized"
      - name: Audit PR
        run: harnessci audit --pr ${{ github.event.pull_request.number }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
      - name: Comment results
        uses: actions/github-script@v7
        with:
          script: |
            // Post comment with decision + findings
```

---

## Cost Analysis

### Per repo initialization (one-time)

| Step | Tokens | Cost |
|---|---|---|
| Repo scan (structure) | ~500 | negligible |
| Key files analysis (20 files) | ~15K | $0.001 (Gemini Flash-Lite) |
| LLM spec extraction | ~5K input | $0.0004 |
| Embedding generation (50 patterns) | ~5K tokens | $0.0004 (Nomic local) |
| **Total** | **~25K tokens** | **~$0.002** |

### Per PR audit

| Step | Tokens | Cost |
|---|---|---|
| Verifier (deterministic) | 0 | $0 |
| Embedding diff (50 vectors) | ~2K | $0 (Nomic local) |
| LLM invariant check (if entity changed) | ~2K | $0.0002 |
| **Total per PR** | **~4K tokens** | **~$0.0003** |

### Monthly cost estimate

| Scenario | PRs/month | Init | Audits | Total |
|---|---|---|---|---|
| Solo project | 30 | $0.002 | $0.009 | **$0.01** |
| Small team | 100 | $0.002 | $0.03 | **$0.03** |
| Mid-size | 500 | $0.002 | $0.15 | **$0.15** |
| Enterprise | 2000 | $0.002 | $0.60 | **$0.60** |

**Total: ~$0.60/month for 2000 PRs.** Essentially free.

---

## Tool choices (June 2026)

| Layer | Tool | Reason |
|---|---|---|
| Embeddings | **Nomic Embed Text v2** (local, CPU) | Free, 137M params, runs on any machine, 768-dim |
| Vector store | **sqlite-vec** (embedded) | Zero server, Windows-compatible, ~50 line setup, pre-v1 but stable |
| LLM (extraction) | **Gemini 2.0 Flash-Lite** ($0.075/M in) | Cheapest production LLM, sufficient for spec mining |
| LLM (verification) | **Gemini 2.0 Flash-Lite** | Same model, only called on entity changes |
| Spec format | **JSON + Markdown** | Machine-parseable + human-readable |
| State | **Local files in .harnessci/** | Git-tracked, portable, no external DB |

**Alternative:** DeepSeek V3.2 ($0.14/M) if Gemini not available. BGE-M3 for embeddings if GPU available.

---

## Implementation order

### Phase 1: Core infrastructure (this session)
1. `src/harnessci/spec/miner.py` — LLM spec extraction
2. `src/harnessci/spec/store.py` — persist to .harnessci/spec.json
3. `src/harnessci/semantic/store.py` — sqlite-vec integration
4. `src/harnessci/semantic/indexer.py` — Nomic embedding generation
5. `src/harnessci/semantic/matcher.py` — drift detection
6. `src/harnessci/spec/verifier.py` — deterministic diff verification

### Phase 2: Audit integration
7. Extend `src/harnessci/audit.py` to use miner + matcher
8. Extend `src/harnessci/scoring/decision.py` to incorporate spec findings + drift signals
9. `src/harnessci/cli.py` — harnessci init / audit / status

### Phase 3: Deployment
10. GitHub Action workflow
11. Spec inference on PR context (if no .harnessci/ spec)
12. Re-evaluation of Layer 2 with improved drift detection

### Phase 4: Production hardening
13. Incremental spec updates (git-based change detection)
14. Spec versioning and rollback
15. Multi-repo support (centralized dashboard)

---

## TFM Claim upgrade

**Before:**  
"HarnessCI uses string matching to detect spec violations and hardcoded keywords for architecture drift."

**After:**  
"HarnessCI learns the domain of any repository automatically via LLM spec extraction and semantic embeddings, enabling zero-config audit of PRs against patterns inferred from code, docs, and conventions — without manual spec authoring."

**New metrics to add:**
- `spec_coverage`: % of diff files covered by mined spec entities
- `drift_detection_rate`: % of architectural violations detected (vs keywords baseline)
- `domain_learning_cost`: $ per repo initialization

---

## Migration path

Existing HarnessCI users: `harnessci init` runs automatically on first audit if no spec exists. No breaking changes. Backward compatible.

```python
def run_audit(diff_text: str, spec_text: str = ""):
    if not spec_text:
        # Try to load .harnessci/spec.json
        spec_dict = load_mined_spec(Path.cwd() / ".harnessci")
        if not spec_dict:
            # Infer from PR context (title, description, diff patterns)
            spec_dict = infer_from_pr_context(diff_text)
    # ... rest unchanged
```

---

## Appendix: Why not other tools?

| Tool | Why not replace with it |
|---|---|
| SpecMap | Doesn't infer specs — requires existing documentation |
| archspec | Requires manual YAML authoring |
| pr-to-spec | Requires manual intent declaration |
| floe | TypeScript-only, no spec inference |
| plumb | Hook-based, requires conversation with agent |
| SpecGuard | Pre-generation only, no post-hoc review |

**HarnessCI differentiator:** All-in-one: infers + verifies + audits + provenance. Zero manual work. Works on any repo from day one.