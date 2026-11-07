"""Optional Keenable public web search; never search private policy data implicitly."""

from urllib.parse import urlparse

import httpx

from app.observability.tracing import observation


class KeenableSearch:
    def __init__(self, api_key: str = "", *, transport=None):
        self.api_key = api_key
        self.transport = transport

    async def search(self, query: str) -> list[dict[str, str]]:
        headers = {"X-API-Key": self.api_key} if self.api_key else {
            "X-Keenable-Title": "Jeeves Claim Companion"
        }
        path = "/v1/search" if self.api_key else "/v1/search/public"
        with observation("web-search", metadata={"provider": "keenable"}) as span:
            async with httpx.AsyncClient(
                base_url="https://api.keenable.ai", timeout=10, transport=self.transport
            ) as client:
                response = await client.post(path, headers=headers, json={
                    "query": query, "max_results": 3, "snippet_max_length": 500
                })
                response.raise_for_status()
                data = response.json()
            results = []
            for item in data.get("results", [])[:3]:
                url = item.get("url", "")
                if not isinstance(url, str) or urlparse(url).scheme not in {"https", "http"}:
                    continue
                results.append({
                    "title": str(item.get("title") or "")[:300],
                    "url": url[:2048],
                    "snippet": str(item.get("snippet") or "")[:500],
                })
            span.update(output={"result_count": len(results)})
            return results
