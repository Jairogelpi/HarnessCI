# platform/__init__.py
from .adapters import (
    VCSPlatform,
    GitHubAdapter,
    GitLabAdapter,
    BitbucketAdapter,
    AzureDevOpsAdapter,
    PRMetadata,
    DiffChunk,
    get_adapter,
    get_platform_from_url,
)

__all__ = [
    "VCSPlatform",
    "GitHubAdapter",
    "GitLabAdapter",
    "BitbucketAdapter",
    "AzureDevOpsAdapter",
    "PRMetadata",
    "DiffChunk",
    "get_adapter",
    "get_platform_from_url",
]
