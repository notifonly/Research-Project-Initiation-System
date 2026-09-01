from __future__ import annotations

from typing import Any, Optional

from shared.mcp.base.base_mcp import BaseMCP, MCPResult


class GitHubMCP(BaseMCP):
    """GitHub REST API - repo search for code availability checks."""

    name = "github"
    base_url = "https://api.github.com"
    requires_api_key = False

    def __init__(self, token: Optional[str] = None, semaphore: Optional[Any] = None) -> None:
        super().__init__(api_key=token, semaphore=semaphore)

    def _default_headers(self) -> dict[str, str]:
        h = {"Accept": "application/vnd.github+json", "User-Agent": "AIscience/0.1"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    async def health(self) -> MCPResult:
        return await self._request("GET", "rate_limit")

    async def search_repositories(self, query: str, sort: str = "stars", order: str = "desc", per_page: int = 20) -> MCPResult:
        params: dict[str, Any] = {"q": query, "sort": sort, "order": order, "per_page": min(per_page, 100)}
        return await self._request("GET", "search/repositories", params=params)

    async def get_repo(self, owner: str, repo: str) -> MCPResult:
        return await self._request("GET", f"repos/{owner}/{repo}")

    async def get_readme(self, owner: str, repo: str) -> MCPResult:
        return await self._request("GET", f"repos/{owner}/{repo}/readme", headers={"Accept": "application/vnd.github.raw"})

    async def search_code(self, query: str, per_page: int = 20) -> MCPResult:
        params: dict[str, Any] = {"q": query, "per_page": min(per_page, 100)}
        return await self._request("GET", "search/code", params=params)

    async def get_topics(self, owner: str, repo: str) -> MCPResult:
        return await self._request("GET", f"repos/{owner}/{repo}/topics", headers={"Accept": "application/vnd.github.mercy-preview+json"})


class PapersWithCodeMCP(BaseMCP):
    """Papers with Code API - method/paper/dataset search linking papers to code."""

    name = "papers_with_code"
    base_url = "https://paperswithcode.com/api/v1"
    requires_api_key = False

    async def health(self) -> MCPResult:
        return await self._request("GET", "papers", params={"page": 1, "items_per_page": 1})

    async def search_papers(self, query: str, page: int = 1, items_per_page: int = 20) -> MCPResult:
        params: dict[str, Any] = {"q": query, "page": page, "items_per_page": min(items_per_page, 100)}
        return await self._request("GET", "papers", params=params)

    async def get_paper(self, paper_id: str) -> MCPResult:
        return await self._request("GET", f"papers/{paper_id}")

    async def get_paper_methods(self, paper_id: str) -> MCPResult:
        return await self._request("GET", f"papers/{paper_id}/methods")

    async def get_paper_repositories(self, paper_id: str) -> MCPResult:
        return await self._request("GET", f"papers/{paper_id}/repositories")

    async def search_methods(self, query: str, page: int = 1) -> MCPResult:
        params: dict[str, Any] = {"q": query, "page": page}
        return await self._request("GET", "methods", params=params)

    async def search_datasets(self, query: str, page: int = 1) -> MCPResult:
        params: dict[str, Any] = {"q": query, "page": page}
        return await self._request("GET", "datasets", params=params)


class HuggingFaceMCP(BaseMCP):
    """HuggingFace Hub API - model/dataset search for foundation model availability."""

    name = "huggingface"
    base_url = "https://huggingface.co/api"
    requires_api_key = False

    async def health(self) -> MCPResult:
        return await self._request("GET", "models", params={"limit": 1})

    async def search_models(self, query: str, limit: int = 20, sort: str = "downloads", direction: str = "-1") -> MCPResult:
        params: dict[str, Any] = {"search": query, "limit": min(limit, 100), "sort": sort, "direction": direction}
        return await self._request("GET", "models", params=params)

    async def get_model(self, model_id: str) -> MCPResult:
        return await self._request("GET", f"models/{model_id}")

    async def search_datasets(self, query: str, limit: int = 20) -> MCPResult:
        params: dict[str, Any] = {"search": query, "limit": min(limit, 100)}
        return await self._request("GET", "datasets", params=params)

    async def get_dataset(self, dataset_id: str) -> MCPResult:
        return await self._request("GET", f"datasets/{dataset_id}")

    async def list_papers(self, query: str = "", limit: int = 20) -> MCPResult:
        params: dict[str, Any] = {"q": query, "limit": min(limit, 100)}
        return await self._request("GET", "papers", params=params)
