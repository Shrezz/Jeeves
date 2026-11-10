"""Optional Keenable public web search; never search private policy data implicitly."""

from urllib.parse import urlparse

import httpx

from app.observability.tracing import capture_synthetic_content, observation


class KeenableSearch:
    def __init__(self, api_key: str = "", *, transport=None):
        self.api_key = api_key
        self.transport = transport

    async def search(self, query: str) -> list[dict[str, str]]:
        headers = (
            {"X-API-Key": self.api_key}
            if self.api_key
            else {"X-Keenable-Title": "Jeeves Claim Companion"}
        )
        path = "/v1/search" if self.api_key else "/v1/search/public"
        capture_content = capture_synthetic_content()
        trace_input = {"query": query} if capture_content else {"query_length": len(query)}
        with observation(
            "web-search", as_type="tool", input=trace_input, metadata={"provider": "keenable"}
        ) as span:
            async with httpx.AsyncClient(
                base_url="https://api.keenable.ai", timeout=10, transport=self.transport
            ) as client:
                response = await client.post(
                    path,
                    headers=headers,
                    json={"query": query, "max_results": 3, "snippet_max_length": 500},
                )
                response.raise_for_status()
                data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("results"), list):
                raise TypeError("Invalid search provider response")
            results = []
            for item in data["results"][:3]:
                if not isinstance(item, dict):
                    continue
                url = item.get("url", "")
                if not isinstance(url, str) or any(ord(char) < 32 for char in url):
                    continue
                try:
                    parsed = urlparse(url)
                    hostname = parsed.hostname
                except ValueError:
                    continue
                if (
                    parsed.scheme not in {"https", "http"}
                    or not hostname
                    or parsed.username
                    or parsed.password
                ):
                    continue
                results.append(
                    {
                        "title": str(item.get("title") or "")[:300],
                        "url": url[:2048],
                        "snippet": str(item.get("snippet") or "")[:500],
                    }
                )
            trace_output = {"result_count": len(results)}
            if capture_content:
                trace_output["results"] = results
            span.update(output=trace_output)
            return results
