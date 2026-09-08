import requests
import re
from typing import List, Dict, Any


class WikipediaRetriever:
    """Fast, single-request Wikipedia evidence retriever using generator=search."""

    API_URL = "https://en.wikipedia.org/w/api.php"
    HEADERS = {
        "User-Agent": "NewsVerifier/1.0 (text-verification-pipeline; contact@verifier.ai)",
    }

    def __init__(self, timeout: int = 4):
        self.timeout = timeout

    def search(self, query: str, max_results: int = 3, claim: str = None) -> List[Dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []

        limit = max(1, min(int(max_results or 3), 5))

        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": q,
            "gsrlimit": limit,
            "prop": "extracts|info",
            "exintro": 1,
            "explaintext": 1,
            "inprop": "url",
            "format": "json",
            "utf8": 1,
        }

        try:
            response = requests.get(
                self.API_URL,
                params=params,
                headers=self.HEADERS,
                timeout=self.timeout,
            )
            if response.status_code != 200:
                return []
            data = response.json()
            pages_dict = data.get("query", {}).get("pages", {})
        except Exception:
            return []

        results = []
        for page_id, page in pages_dict.items():
            if page.get("missing"):
                continue

            title = (page.get("title") or "").strip()
            if not title or "disambiguation" in title.lower():
                continue

            extract = (page.get("extract") or "").strip()
            if not extract:
                continue

            # Limit extract to first 2-3 sentences (around 600 chars)
            clean_extract = re.sub(r"\s+", " ", extract)
            if len(clean_extract) > 600:
                clean_extract = clean_extract[:597].rstrip() + "..."

            url = page.get("fullurl") or f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"

            results.append({
                "title": title,
                "content": clean_extract,
                "description": clean_extract,
                "source": "Wikipedia",
                "url": url,
            })

            if len(results) >= limit:
                break

        return results


__all__ = ["WikipediaRetriever"]