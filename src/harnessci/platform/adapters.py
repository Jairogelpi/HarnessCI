"""Multi-VCS platform adapters for HarnessCI.

Abstraction layer supporting GitHub, GitLab, Bitbucket, and Azure DevOps.
Each adapter handles: diff fetching, PR metadata, comment posting, status checks.
"""

from __future__ import annotations

import base64
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import requests as _requests


# ---------------------------------------------------------------------------
# VCS Platform enum
# ---------------------------------------------------------------------------


class VCSPlatform(ABC):
    """Abstract base for VCS platform adapters."""

    name: str
    diff_url_pattern: str

    @abstractmethod
    def fetch_diff(self, repo: str, pr_number: int, *, token: str | None = None) -> str:
        """Fetch the unified diff for a PR."""
        ...

    @abstractmethod
    def fetch_pr_metadata(
        self, repo: str, pr_number: int, *, token: str | None = None
    ) -> dict[str, Any]:
        """Fetch PR metadata (title, description, files changed, author)."""
        ...

    @abstractmethod
    def get_pr_files(
        self, repo: str, pr_number: int, *, token: str | None = None
    ) -> list[dict[str, Any]]:
        """Get list of files changed in a PR."""
        ...

    @abstractmethod
    def post_comment(
        self, repo: str, pr_number: int, body: str, *, token: str | None = None
    ) -> bool:
        """Post a comment to the PR."""
        ...

    @abstractmethod
    def update_status(
        self, repo: str, pr_number: int, state: str, description: str, *, token: str | None = None
    ) -> bool:
        """Update the PR status check (success/failure/pending)."""
        ...

    @abstractmethod
    def get_file_content(
        self, repo: str, path: str, ref: str = "main", *, token: str | None = None
    ) -> str | None:
        """Get the content of a file at a given ref."""
        ...


@dataclass
class DiffChunk:
    """Represents a changed file in a diff."""

    path: str
    old_path: str | None = None
    status: str = "modified"  # added, deleted, modified, renamed
    lines_added: int = 0
    lines_deleted: int = 0
    diff_text: str = ""


@dataclass
class PRMetadata:
    """PR metadata from any VCS platform."""

    number: int
    title: str
    description: str
    author: str
    base_branch: str
    head_branch: str
    state: str  # open, closed, merged
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0
    url: str = ""
    platform: str = ""


# ---------------------------------------------------------------------------
# GitHub adapter
# ---------------------------------------------------------------------------


class GitHubAdapter(VCSPlatform):
    """GitHub REST API v3 adapter."""

    name = "github"
    BASE_URL = "https://api.github.com"

    def _headers(self, token: str | None) -> dict[str, str]:
        h = {"Accept": "application/vnd.github.v3+json"}
        if token:
            h["Authorization"] = f"token {token}"
        return h

    def fetch_diff(self, repo: str, pr_number: int, *, token: str | None = None) -> str:
        url = f"{self.BASE_URL}/repos/{repo}/pulls/{pr_number}"
        resp = _requests.get(url, headers=self._headers(token), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("diff", "")

    def fetch_pr_metadata(
        self, repo: str, pr_number: int, *, token: str | None = None
    ) -> dict[str, Any]:
        url = f"{self.BASE_URL}/repos/{repo}/pulls/{pr_number}"
        resp = _requests.get(url, headers=self._headers(token), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return {
            "number": data["number"],
            "title": data["title"],
            "description": data["body"] or "",
            "author": data["user"]["login"],
            "base_branch": data["base"]["ref"],
            "head_branch": data["head"]["ref"],
            "state": data["state"],
            "files_changed": data.get("changed_files", 0),
            "additions": data.get("additions", 0),
            "deletions": data.get("deletions", 0),
            "url": data["html_url"],
            "platform": "github",
        }

    def get_pr_files(
        self, repo: str, pr_number: int, *, token: str | None = None
    ) -> list[dict[str, Any]]:
        url = f"{self.BASE_URL}/repos/{repo}/pulls/{pr_number}/files"
        resp = _requests.get(url, headers=self._headers(token), timeout=30)
        resp.raise_for_status()
        return resp.json()

    def post_comment(
        self, repo: str, pr_number: int, body: str, *, token: str | None = None
    ) -> bool:
        url = f"{self.BASE_URL}/repos/{repo}/issues/{pr_number}/comments"
        resp = _requests.post(url, headers=self._headers(token), json={"body": body}, timeout=30)
        return resp.status_code == 201

    def update_status(
        self, repo: str, pr_number: int, state: str, description: str, *, token: str | None = None
    ) -> bool:
        ind = {"success": "✅", "failure": "❌", "pending": "⏳"}.get(state, "ℹ️")
        return self.post_comment(repo, pr_number, f"{ind} HarnessCI: {description}", token=token)

    def get_file_content(
        self, repo: str, path: str, ref: str = "main", *, token: str | None = None
    ) -> str | None:
        url = f"{self.BASE_URL}/repos/{repo}/contents/{path}"
        resp = _requests.get(url, headers=self._headers(token), params={"ref": ref}, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return None


# ---------------------------------------------------------------------------
# GitLab adapter
# ---------------------------------------------------------------------------


class GitLabAdapter(VCSPlatform):
    """GitLab REST API v4 adapter."""

    name = "gitlab"
    BASE_URL = "https://gitlab.com/api/v4"

    def __init__(self, base_url: str | None = None) -> None:
        if base_url:
            self.BASE_URL = base_url

    def _headers(self, token: str | None) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if token:
            h["PRIVATE-TOKEN"] = token
        return h

    def fetch_diff(self, repo: str, pr_number: int, *, token: str | None = None) -> str:
        enc_repo = repo.replace("/", "%2F")
        url = f"{self.BASE_URL}/projects/{enc_repo}/merge_requests/{pr_number}/changes"
        resp = _requests.get(url, headers=self._headers(token), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        diffs = [c.get("diff", "") for c in data.get("changes", []) if c.get("diff")]
        return "\n".join(diffs)

    def fetch_pr_metadata(
        self, repo: str, pr_number: int, *, token: str | None = None
    ) -> dict[str, Any]:
        enc_repo = repo.replace("/", "%2F")
        url = f"{self.BASE_URL}/projects/{enc_repo}/merge_requests/{pr_number}"
        resp = _requests.get(url, headers=self._headers(token), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return {
            "number": data["iid"],
            "title": data["title"],
            "description": data["description"] or "",
            "author": data["author"]["username"],
            "base_branch": data["target_branch"],
            "head_branch": data["source_branch"],
            "state": data["state"],
            "files_changed": data.get("changes_count", "0"),
            "additions": data.get("changes_num", 0),
            "deletions": 0,
            "url": data["web_url"],
            "platform": "gitlab",
        }

    def get_pr_files(
        self, repo: str, pr_number: int, *, token: str | None = None
    ) -> list[dict[str, Any]]:
        enc_repo = repo.replace("/", "%2F")
        url = f"{self.BASE_URL}/projects/{enc_repo}/merge_requests/{pr_number}/changes"
        resp = _requests.get(url, headers=self._headers(token), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return [
            {"path": c.get("new_path", ""), "status": "modified", "diff": c.get("diff", "")}
            for c in data.get("changes", [])
        ]

    def post_comment(
        self, repo: str, pr_number: int, body: str, *, token: str | None = None
    ) -> bool:
        enc_repo = repo.replace("/", "%2F")
        url = f"{self.BASE_URL}/projects/{enc_repo}/merge_requests/{pr_number}/notes"
        resp = _requests.post(url, headers=self._headers(token), json={"body": body}, timeout=30)
        return resp.status_code == 201

    def update_status(
        self, repo: str, pr_number: int, state: str, description: str, *, token: str | None = None
    ) -> bool:
        ind = {"success": "✅", "failure": "❌", "pending": "⏳"}.get(state, "ℹ️")
        return self.post_comment(repo, pr_number, f"{ind} HarnessCI: {description}", token=token)

    def get_file_content(
        self, repo: str, path: str, ref: str = "main", *, token: str | None = None
    ) -> str | None:
        enc_repo = repo.replace("/", "%2F")
        enc_path = path.replace("/", "%2F")
        url = f"{self.BASE_URL}/projects/{enc_repo}/repository/files/{enc_path}"
        resp = _requests.get(url, headers=self._headers(token), params={"ref": ref}, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return None


# ---------------------------------------------------------------------------
# Bitbucket adapter
# ---------------------------------------------------------------------------


class BitbucketAdapter(VCSPlatform):
    """Bitbucket REST API v2 adapter."""

    name = "bitbucket"
    BASE_URL = "https://api.bitbucket.org/2.0"

    def _headers(self, token: str | None) -> dict[str, str]:
        h: dict[str, str] = {}
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    def fetch_diff(self, repo: str, pr_number: int, *, token: str | None = None) -> str:
        url = f"{self.BASE_URL}/repositories/{repo}/pullrequests/{pr_number}/diff"
        resp = _requests.get(url, headers=self._headers(token), timeout=30)
        return resp.text if resp.status_code == 200 else ""

    def fetch_pr_metadata(
        self, repo: str, pr_number: int, *, token: str | None = None
    ) -> dict[str, Any]:
        url = f"{self.BASE_URL}/repositories/{repo}/pullrequests/{pr_number}"
        resp = _requests.get(url, headers=self._headers(token), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return {
            "number": data["id"],
            "title": data["title"],
            "description": data.get("description", "") or "",
            "author": data["author"]["username"],
            "base_branch": data["destination"]["branch"]["name"],
            "head_branch": data["source"]["branch"]["name"],
            "state": data["state"],
            "files_changed": 0,
            "additions": 0,
            "deletions": 0,
            "url": data["links"]["html"]["href"],
            "platform": "bitbucket",
        }

    def get_pr_files(
        self, repo: str, pr_number: int, *, token: str | None = None
    ) -> list[dict[str, Any]]:
        url = f"{self.BASE_URL}/repositories/{repo}/pullrequests/{pr_number}/diff"
        resp = _requests.get(url, headers=self._headers(token), timeout=30)
        if resp.status_code == 200:
            return self._parse_bitbucket_diff(resp.text)
        return []

    def _parse_bitbucket_diff(self, diff_text: str) -> list[dict[str, Any]]:
        files = []
        current_file = None
        lines_added = 0
        lines_deleted = 0

        for line in diff_text.split("\n"):
            if line.startswith("diff --git"):
                if current_file:
                    files.append(
                        {
                            "path": current_file,
                            "status": "modified",
                            "lines_added": lines_added,
                            "lines_deleted": lines_deleted,
                        }
                    )
                m = re.search(r"b/(.+)", line)
                current_file = m.group(1) if m else None
                lines_added = 0
                lines_deleted = 0
            elif line.startswith("+") and not line.startswith("+++"):
                lines_added += 1
            elif line.startswith("-") and not line.startswith("---"):
                lines_deleted += 1

        if current_file:
            files.append(
                {
                    "path": current_file,
                    "status": "modified",
                    "lines_added": lines_added,
                    "lines_deleted": lines_deleted,
                }
            )

        return files

    def post_comment(
        self, repo: str, pr_number: int, body: str, *, token: str | None = None
    ) -> bool:
        url = f"{self.BASE_URL}/repositories/{repo}/pullrequests/{pr_number}/comments"
        resp = _requests.post(url, headers=self._headers(token), json={"content": body}, timeout=30)
        return resp.status_code in (200, 201)

    def update_status(
        self, repo: str, pr_number: int, state: str, description: str, *, token: str | None = None
    ) -> bool:
        ind = {"success": "✅", "failure": "❌", "pending": "⏳"}.get(state, "ℹ️")
        return self.post_comment(repo, pr_number, f"{ind} HarnessCI: {description}", token=token)

    def get_file_content(
        self, repo: str, path: str, ref: str = "main", *, token: str | None = None
    ) -> str | None:
        url = f"{self.BASE_URL}/repositories/{repo}/src/{ref}/{path}"
        resp = _requests.get(url, headers=self._headers(token), timeout=15)
        return resp.text if resp.status_code == 200 else None


# ---------------------------------------------------------------------------
# Azure DevOps adapter
# ---------------------------------------------------------------------------


class AzureDevOpsAdapter(VCSPlatform):
    """Azure DevOps REST API v7.1 adapter."""

    name = "azure"
    BASE_URL = "https://dev.azure.com"

    def __init__(self, organization: str | None = None) -> None:
        self._org = organization

    def _resolve_org(self, repo: str) -> str:
        if self._org:
            return self._org
        return repo.split("/")[0]

    def _headers(self, token: str | None) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if token:
            h["Authorization"] = f"Basic {token}"
        return h

    def _project_repo(self, repo: str) -> tuple[str, str]:
        parts = repo.split("/", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return repo, ""

    def fetch_diff(self, repo: str, pr_number: int, *, token: str | None = None) -> str:
        org = self._resolve_org(repo)
        project, repo_name = self._project_repo(repo)
        url = (
            f"{self.BASE_URL}/{org}/{project}/_apis/git/repositories/{repo_name}"
            f"/pullRequests/{pr_number}/diffs?diffType=unified"
        )
        resp = _requests.get(url, headers=self._headers(token), timeout=30)
        if resp.status_code == 200:
            return resp.text
        return ""

    def fetch_pr_metadata(
        self, repo: str, pr_number: int, *, token: str | None = None
    ) -> dict[str, Any]:
        org = self._resolve_org(repo)
        proj, rname = self._project_repo(repo)
        url = (
            f"{self.BASE_URL}/{org}/{proj}/_apis/git/repositories/{rname}/pullRequests/{pr_number}"
        )
        resp = _requests.get(url, headers=self._headers(token), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return {
            "number": data["pullRequestId"],
            "title": data["title"],
            "description": data.get("descriptionText", "") or "",
            "author": data["createdBy"]["uniqueName"],
            "base_branch": data["targetRefName"].replace("refs/heads/", ""),
            "head_branch": data["sourceRefName"].replace("refs/heads/", ""),
            "state": data["status"],
            "files_changed": 0,
            "additions": data.get("changeSummary", {}).get("add", 0),
            "deletions": data.get("changeSummary", {}).get("delete", 0),
            "url": data["_links"]["web"]["href"],
            "platform": "azure",
        }

    def get_pr_files(
        self, repo: str, pr_number: int, *, token: str | None = None
    ) -> list[dict[str, Any]]:
        # Azure iterations API — simplified placeholder
        return []

    def post_comment(
        self, repo: str, pr_number: int, body: str, *, token: str | None = None
    ) -> bool:
        org = self._resolve_org(repo)
        proj, rname = self._project_repo(repo)
        url = (
            f"{self.BASE_URL}/{org}/{proj}/_apis/git/repositories/{rname}"
            f"/pullRequests/{pr_number}/threads"
        )
        payload = {"comments": [{"content": body, "parentCommentId": 0, "commentType": 1}]}
        resp = _requests.post(url, headers=self._headers(token), json=payload, timeout=30)
        return resp.status_code in (200, 201)

    def update_status(
        self, repo: str, pr_number: int, state: str, description: str, *, token: str | None = None
    ) -> bool:
        ind = {"success": "✅", "failure": "❌", "pending": "⏳"}.get(state, "ℹ️")
        return self.post_comment(repo, pr_number, f"{ind} HarnessCI: {description}", token=token)

    def get_file_content(
        self, repo: str, path: str, ref: str = "main", *, token: str | None = None
    ) -> str | None:
        org = self._resolve_org(repo)
        proj, rname = self._project_repo(repo)
        enc_path = path.replace(" ", "%20")
        url = (
            f"{self.BASE_URL}/{org}/{proj}/_apis/git/repositories/{rname}"
            f"/items?path={enc_path}&versionDescriptor.version={ref}"
        )
        resp = _requests.get(url, headers=self._headers(token), timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if "content" in data:
                return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            return resp.text
        return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_PLATFORMS: dict[str, type[VCSPlatform]] = {
    "github": GitHubAdapter,
    "gitlab": GitLabAdapter,
    "bitbucket": BitbucketAdapter,
    "azure": AzureDevOpsAdapter,
}


def get_adapter(platform: str, **kwargs: Any) -> VCSPlatform:
    """Get the appropriate adapter for a platform."""
    cls = _PLATFORMS.get(platform.lower())
    if cls is None:
        raise ValueError(f"Unknown platform: {platform}. Supported: {', '.join(_PLATFORMS.keys())}")
    return cls(**kwargs)


def get_platform_from_url(url: str) -> str:
    """Detect VCS platform from a repository URL."""
    if "github.com" in url:
        return "github"
    if "gitlab.com" in url:
        return "gitlab"
    if "bitbucket.org" in url:
        return "bitbucket"
    if "dev.azure.com" in url or "azure.com" in url:
        return "azure"
    # Heuristic from path patterns
    if url.startswith("/") and ":" not in url:
        # Could be git@github.com:org/repo.git style
        if "github" in url.lower():
            return "github"
    return "github"  # default
