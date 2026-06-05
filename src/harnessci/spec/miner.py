"""LLM-based spec extraction for HarnessCI.

Uses Groq's Llama 3.1 8B for fast, cheap spec mining from repository code.
Fallback: returns empty spec when no API key available.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.1-8b-instant"
SKIP_DIRS = {".venv", "node_modules", "__pycache__", ".git"}

MINING_SYSTEM = (
    "You are a code analysis expert. Extract structured specs from codebases. "
    "Output ONLY valid JSON with exact keys: domain, entities (list with name/files/invariants), "
    "conventions (object with naming/api/auth), forbidden_paths (list), "
    "allowed_test_patterns (list), architecture (object with layers/dependencies), "
    "security_invariants (list), summary_md (string). "
    "No markdown fences, no explanation, just the JSON object."
)


# ---------------------------------------------------------------------------
# LLM client (Groq)
# ---------------------------------------------------------------------------


class GroqClient:
    """Lightweight Groq client using requests — OpenAI-compatible API."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        self._available = bool(self.api_key)

    @property
    def available(self) -> bool:
        return self._available and bool(self.api_key)

    def complete(self, prompt: str, system: str = "") -> str:
        """Call Groq API and return text response."""
        if not self.available:
            return '{"error": "GROQ_API_KEY not set"}'

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict = {
            "model": MODEL,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1024,
        }

        try:
            resp = requests.post(
                GROQ_API_URL,
                json=payload,
                headers=headers,
                timeout=30,
            )
            if resp.status_code != 200:
                return f'{{"error": "API error {resp.status_code}: {resp.text[:200]}"}}'

            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                return '{"error": "No choices in response"}'

            return choices[0].get("message", {}).get("content", '{"error": "No content"}')

        except requests.Timeout:
            return '{"error": "Request timed out"}'
        except Exception:  # noqa: BLE001
            return '{"error": "Request failed"}'


def create_llm_client(provider: str = "groq") -> GroqClient | None:
    """Factory: create LLM client for the given provider."""
    if provider == "groq":
        key = os.environ.get("GROQ_API_KEY", "")
        if key:
            return GroqClient(key)
    return None


# ---------------------------------------------------------------------------
# Spec mining
# ---------------------------------------------------------------------------


def _scan_structure(root: Path) -> dict:
    """Scan repository structure and extract key metadata."""
    structure: dict = {
        "files": [],
        "readme": "",
        "config": {},
        "languages": [],
    }

    try:
        for entry in root.iterdir():
            if entry.name.startswith("."):
                continue
            if entry.is_file():
                ext = entry.suffix.lower()
                if ext in [".py", ".js", ".ts", ".go", ".rs", ".java", ".cpp"]:
                    structure["files"].append(entry.name)
                if entry.name.lower() in ["readme.md", "readme.txt"]:
                    try:
                        content = entry.read_text(encoding="utf-8", errors="replace")
                        structure["readme"] = content[:2000]
                    except Exception:  # noqa: BLE001
                        pass
            elif entry.is_dir():
                structure["files"].append(f"{entry.name}/")
    except Exception:  # noqa: BLE001
        pass

    for cfg_name in ["pyproject.toml", "package.json", "requirements.txt", "go.mod"]:
        cfg_path = root / cfg_name
        if cfg_path.exists():
            try:
                content = cfg_path.read_text(encoding="utf-8", errors="replace")
                structure["config"][cfg_name] = content[:500]
            except Exception:  # noqa: BLE001
                pass

    if any(root.rglob("*.py")):
        structure["languages"].append("python")
    if any(root.rglob("*.js")) or any(root.rglob("*.ts")):
        structure["languages"].append("javascript/typescript")
    if any(root.rglob("*.go")):
        structure["languages"].append("go")
    if any(root.rglob("*.rs")):
        structure["languages"].append("rust")

    return structure


def _select_key_files(root: Path, n: int = 20) -> list[dict]:
    """Select most important files with content snippets."""
    key_files: list[dict] = []
    seen: set[str] = set()

    patterns = [
        ("main", ["main.py", "app.py", "server.py", "index.py", "main.go"]),
        ("config", ["pyproject.toml", "package.json", "config.py", "settings.py"]),
        ("test", ["test_", "_test.py", ".test.ts", "spec.ts"]),
        ("readme", ["README.md", "SPEC.md"]),
        ("module", ["src/", "lib/", "internal/", "core/"]),
    ]

    for priority, pattern_list in patterns:
        if len(key_files) >= n:
            break
        for pattern in pattern_list:
            if len(key_files) >= n:
                break
            for match in root.rglob(pattern):
                if match.name in seen:
                    continue
                if any(skip in str(match) for skip in SKIP_DIRS):
                    continue
                try:
                    rel = match.relative_to(root)
                    content = ""
                    if match.is_file() and match.stat().st_size < 50000:
                        text = match.read_text(encoding="utf-8", errors="replace")
                        content = text[:800]
                    key_files.append(
                        {
                            "path": str(rel),
                            "priority": priority,
                            "content": content,
                        }
                    )
                    seen.add(match.name)
                except Exception:  # noqa: BLE001
                    pass

    return key_files[:n]


def _build_mining_prompt(structure: dict, key_files: list[dict]) -> str:
    """Build the spec mining prompt for LLM."""
    prompt = (
        f"Analyze this codebase and extract a structured specification.\n"
        f"Languages: {', '.join(structure.get('languages', [])) or 'unknown'}\n"
        f"Files: {', '.join(structure.get('files', [])[:30])}"
    )

    if structure.get("readme"):
        prompt += f"\n\nREADME:\n{structure['readme'][:1000]}"

    if structure.get("config"):
        prompt += "\n\nConfig:"
        for cfg, content in structure["config"].items():
            prompt += f"\n- {cfg}: {content[:200]}"

    prompt += "\n\nKey files:"
    for kf in key_files[:15]:
        prompt += f"\n\n=== {kf['path']} ===\n{kf['content'][:500]}"

    prompt += """
Extract JSON with exact keys: domain, entities (name/files/invariants),
conventions (naming/api/auth), forbidden_paths, allowed_test_patterns,
architecture (layers/dependencies), security_invariants, summary_md.
Output ONLY the JSON. No markdown, no explanation."""
    return prompt


def _validate_spec(spec_dict: dict) -> bool:
    """Validate that mined spec has required fields."""
    required = ["domain", "entities", "conventions", "forbidden_paths", "allowed_test_patterns"]
    return all(k in spec_dict for k in required)


def mine_spec(
    root: Path,
    llm_client: GroqClient | None = None,
) -> tuple[dict, str]:
    """Full spec mining pipeline using Groq Llama.

    Returns:
        Tuple of (spec_dict, summary_md). On failure, returns empty spec.
    """
    if llm_client is None:
        llm_client = create_llm_client()
        if llm_client is None or not llm_client.available:
            return _empty_spec(), ""

    try:
        structure = _scan_structure(root)
        key_files = _select_key_files(root, n=20)

        prompt = _build_mining_prompt(structure, key_files)
        response = llm_client.complete(prompt, system=MINING_SYSTEM)

        # Parse JSON response
        try:
            text = response.strip()
            if text.startswith("```"):
                for marker in ["```json", "```"]:
                    if text.startswith(marker):
                        text = text[len(marker) :]
                        text = text.rstrip("`").strip()

            spec = json.loads(text)
        except json.JSONDecodeError:
            return _empty_spec(), ""

        if not _validate_spec(spec):
            return _empty_spec(), ""

        summary_md = spec.pop("summary_md", "")
        return spec, summary_md

    except Exception:  # noqa: BLE001
        return _empty_spec(), ""


def _empty_spec() -> dict:
    """Return an empty/minimal spec when mining fails."""
    return {
        "domain": "unknown",
        "entities": [],
        "conventions": {},
        "forbidden_paths": [],
        "allowed_test_patterns": [],
        "architecture": {},
        "security_invariants": [],
    }
