import re
import xml.etree.ElementTree as ET
import urllib.parse
from typing import List, Dict, Any
import requests
from bs4 import BeautifulSoup


class GoogleNewsRetriever:
    """Fetch near real-time evidence from Google News RSS feeds using standard XML parsing."""

    RSS_URL = "https://news.google.com/rss/search"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    def __init__(self, timeout: int = 4, max_chars: int = 500):
        self.timeout = timeout
        self.max_chars = max(300, min(max_chars, 800))

    def _clean_text(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", (text or "")).strip()
        if len(cleaned) > self.max_chars:
            return cleaned[: self.max_chars]
        return cleaned

    def search(self, query: str, max_results: int = 6) -> List[Dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []

        limit = max(3, min(int(max_results or 6), 10))

        try:
            encoded_query = urllib.parse.quote(q)
            url = f"{self.RSS_URL}?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
            response = requests.get(url, headers=self.HEADERS, timeout=self.timeout)
            if response.status_code != 200:
                return []

            root = ET.fromstring(response.content)
            channel = root.find("channel")
            items = channel.findall("item") if channel is not None else []
        except Exception:
            return []

        articles = []
        seen_links = set()

        for item in items:
            raw_title = item.findtext("title") or ""
            link = (item.findtext("link") or "").strip()
            pub_date = item.findtext("pubDate") or ""
            
            # Extract source publisher
            source_elem = item.find("source")
            source_name = source_elem.text.strip() if source_elem is not None and source_elem.text else "News Source"
            
            # If title ends with " - SourceName", clean it up
            clean_title = raw_title
            if " - " in clean_title:
                parts = clean_title.rsplit(" - ", 1)
                clean_title = parts[0].strip()
                if source_elem is None or not source_elem.text:
                    source_name = parts[1].strip()

            if not link or link in seen_links:
                continue
            seen_links.add(link)

            # Extract snippet from HTML description
            desc_html = item.findtext("description") or ""
            clean_snippet = ""
            if desc_html:
                try:
                    soup = BeautifulSoup(desc_html, "html.parser")
                    clean_snippet = self._clean_text(soup.get_text(" ", strip=True))
                except Exception:
                    clean_snippet = self._clean_text(desc_html)

            content = clean_snippet or clean_title

            articles.append({
                "title": clean_title,
                "description": clean_snippet,
                "content": content,
                "source": source_name,
                "url": link,
                "published_at": pub_date,
            })

            if len(articles) >= limit:
                break

        return articles


__all__ = ["GoogleNewsRetriever"]
