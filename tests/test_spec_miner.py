"""Tests for the LLM spec miner (Groq/Llama)."""

from __future__ import annotations

import json
from unittest.mock import patch

from harnessci.spec.miner import (
    GroqClient,
    _empty_spec,
    _scan_structure,
    _select_key_files,
    _validate_spec,
    create_llm_client,
    mine_spec,
)


class TestGroqClient:
    def test_available_with_key(self):
        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key-123"}):
            client = GroqClient()
            assert client.available is True

    def test_unavailable_without_key(self):
        with patch.dict("os.environ", {}, clear=True):
            client = GroqClient()
            assert client.available is False

    def test_complete_unavailable_returns_error_json(self):
        with patch.dict("os.environ", {}, clear=True):
            client = GroqClient()
            result = client.complete("test prompt")
            assert '"error"' in result


class TestMiningHelpers:
    def test_validate_spec_returns_true_for_valid_spec(self):
        spec = {
            "domain": "test",
            "entities": [],
            "conventions": {},
            "forbidden_paths": [],
            "allowed_test_patterns": [],
        }
        assert _validate_spec(spec) is True

    def test_validate_spec_returns_false_for_missing_fields(self):
        spec = {"domain": "test"}
        assert _validate_spec(spec) is False

    def test_empty_spec_has_all_fields(self):
        spec = _empty_spec()
        assert "domain" in spec
        assert "entities" in spec
        assert "conventions" in spec
        assert "forbidden_paths" in spec
        assert "allowed_test_patterns" in spec
        assert spec["domain"] == "unknown"

    def test_scan_structure_detects_python_project(self, tmp_path):
        (tmp_path / "main.py").touch()
        (tmp_path / "requirements.txt").write_text("pytest>=8")
        structure = _scan_structure(tmp_path)
        assert "python" in structure["languages"]
        assert "requirements.txt" in structure["config"]

    def test_select_key_files_returns_files(self, tmp_path):
        (tmp_path / "main.py").write_text("# main")
        (tmp_path / "config.py").write_text("# config")
        (tmp_path / "test_main.py").write_text("# test")

        files = _select_key_files(tmp_path, n=10)
        assert len(files) >= 1
        paths = [f["path"] for f in files]
        assert any("main.py" in p for p in paths)


class TestMineSpec:
    def test_mine_spec_with_available_client(self, tmp_path):
        (tmp_path / "main.py").write_text("# main")
        (tmp_path / "README.md").write_text("# Test project")

        mock_response = json.dumps(
            {
                "domain": "Test project",
                "entities": [],
                "conventions": {"naming": "snake_case"},
                "forbidden_paths": [],
                "allowed_test_patterns": ["tests/"],
                "architecture": {},
                "security_invariants": [],
                "summary_md": "## Test\n\nA test project.",
            }
        )

        with patch.object(GroqClient, "complete", return_value=mock_response):
            client = GroqClient("fake-key")
            spec, summary = mine_spec(tmp_path, client)
            assert spec["domain"] == "Test project"
            assert spec["conventions"]["naming"] == "snake_case"
            assert summary == "## Test\n\nA test project."

    def test_mine_spec_handles_json_with_markdown_fences(self, tmp_path):
        mock_response = """```json
{
  "domain": "Test",
  "entities": [],
  "conventions": {},
  "forbidden_paths": [],
  "allowed_test_patterns": [],
  "architecture": {},
  "security_invariants": [],
  "summary_md": "Test"
}
```"""
        with patch.object(GroqClient, "complete", return_value=mock_response):
            client = GroqClient("fake-key")
            spec, _ = mine_spec(tmp_path, client)
            assert spec["domain"] == "Test"

    def test_mine_spec_handles_invalid_json(self, tmp_path):
        with patch.object(GroqClient, "complete", return_value="not valid json"):
            client = GroqClient("fake-key")
            spec, _ = mine_spec(tmp_path, client)
            assert spec["domain"] == "unknown"

    def test_mine_spec_handles_incomplete_spec_response(self, tmp_path):
        mock_response = json.dumps({"domain": "Test"})
        with patch.object(GroqClient, "complete", return_value=mock_response):
            client = GroqClient("fake-key")
            spec, _ = mine_spec(tmp_path, client)
            assert spec["domain"] == "unknown"


class TestCreateLLMClient:
    def test_returns_client_when_key_set(self):
        with patch.dict("os.environ", {"GROQ_API_KEY": "test"}):
            client = create_llm_client()
            assert client is not None
            assert isinstance(client, GroqClient)

    def test_returns_none_when_key_not_set(self):
        with patch.dict("os.environ", {}, clear=True):
            client = create_llm_client()
            assert client is None
