"""Build-time client for the public Microsoft Learn MCP server.

Used to (re)ground the catalog on the real, public certification skill outlines. Microsoft
Learn content is read live and never persisted into our knowledge base — only the factual
structure informs the original synthetic prose (see the course-author skill). The Learn MCP
server speaks Streamable HTTP and exposes `microsoft_docs_search` / `microsoft_docs_fetch`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

LEARN_MCP_URL = "https://learn.microsoft.com/api/mcp"


@dataclass
class DocResult:
    title: str
    url: str
    content: str


class MicrosoftLearnMCP:
    """Minimal JSON-RPC client over the Microsoft Learn MCP Streamable-HTTP endpoint."""

    def __init__(self, url: str = LEARN_MCP_URL, timeout: float = 30.0) -> None:
        self._url = url
        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
        )
        self._id = 0

    def __enter__(self) -> MicrosoftLearnMCP:
        return self

    def __exit__(self, *exc: object) -> None:
        self._client.close()

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
        resp = self._client.post(self._url, json=payload)
        resp.raise_for_status()
        text = resp.text.strip()
        # Streamable HTTP may return an SSE frame ("data: {...}") or plain JSON.
        if text.startswith("data:"):
            text = text.split("data:", 1)[1].strip()
        return json.loads(text)

    def search_docs(self, query: str) -> list[DocResult]:
        """Call the microsoft_docs_search tool and return structured results."""
        out = self._rpc(
            "tools/call",
            {"name": "microsoft_docs_search", "arguments": {"query": query}},
        )
        results: list[DocResult] = []
        for item in out.get("result", {}).get("content", []):
            if item.get("type") != "text":
                continue
            try:
                parsed = json.loads(item["text"])
            except (json.JSONDecodeError, KeyError):
                continue
            entries = parsed if isinstance(parsed, list) else [parsed]
            for e in entries:
                results.append(
                    DocResult(
                        title=str(e.get("title", "")),
                        url=str(e.get("contentUrl", e.get("url", ""))),
                        content=str(e.get("content", "")),
                    )
                )
        return results
