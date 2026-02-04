"""
Semantic search client (external endpoint).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import requests


@dataclass
class SemanticSearchResult:
    chainId: int
    agentId: str
    score: float


class SemanticSearchClient:
    def __init__(
        self,
        base_url: str = "https://semantic-search.ag0.xyz",
        timeout_seconds: float = 20.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, *, min_score: Optional[float] = None, top_k: Optional[int] = None) -> List[SemanticSearchResult]:
        if not query or not query.strip():
            return []

        # SDK defaults (applied here so developers don't need to pass them).
        # - minScore: 0.5
        # - topK: 5000 (API expects "limit" not "topK" in v1)
        if min_score is None:
            min_score = 0.5
        if top_k is None:
            top_k = 5000

        body = {"query": query.strip(), "minScore": min_score, "limit": top_k}

        resp = requests.post(
            f"{self.base_url}/api/v1/search",
            json=body,
            headers={"Content-Type": "application/json"},
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results") if isinstance(data, dict) else data
        if not isinstance(results, list):
            return []

        out: List[SemanticSearchResult] = []
        for r in results:
            if not isinstance(r, dict):
                continue
            try:
                chain_id = int(r.get("chainId"))
                agent_id = str(r.get("agentId"))
                score = float(r.get("score"))
            except Exception:
                continue
            if ":" not in agent_id:
                continue
            out.append(SemanticSearchResult(chainId=chain_id, agentId=agent_id, score=score))
        return out

