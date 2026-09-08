import concurrent.futures
import logging
import re
from typing import Optional, Dict, Any, List


class VerificationPipeline:
    """Production text claim and news headline verification pipeline.
    Combines live Google News RSS search and Wikipedia reference retrieval
    with autonomous semantic stance, refutation, and consensus evaluation.
    """

    CACHE_VERSION = "dual-stream-factcheck-v2"

    def __init__(self):
        from text_verification.claim_processing.claim_normalizer import (
            normalize_headline_to_claim,
            generate_search_query,
        )
        from text_verification.claim_processing.cleaner import ClaimCleaner
        from text_verification.utils.cache import get_cached_result, set_cached_result
        from text_verification.retrieval.google_news import GoogleNewsRetriever
        from text_verification.retrieval.wikipedia_api import WikipediaRetriever
        from text_verification.verdict.verdict_generator import VerdictGenerator

        self.normalize_headline = normalize_headline_to_claim
        self.generate_query = generate_search_query
        self.cleaner = ClaimCleaner()
        self.get_cached_result = get_cached_result
        self.set_cached_result = set_cached_result
        self.google_news = GoogleNewsRetriever()
        self.wikipedia = WikipediaRetriever()
        self.verdict_generator = VerdictGenerator()
        self.logger = logging.getLogger(__name__)

    def verify_claim(self, headline: str) -> Dict[str, Any]:
        """Verify text claim or headline against live news and encyclopedic records."""
        headline_raw = (headline or "").strip()
        if not headline_raw:
            return {
                "claim": "",
                "normalized_claim": "",
                "verdict": "Not Enough Information",
                "confidence": 0.50,
                "summary": "No headline was provided for verification.",
                "reason": "Input was empty.",
                "explanation": "No text claim was provided for verification.",
                "conflicting_sources": False,
                "sources": [],
            }

        claim = self.normalize_headline(headline_raw)
        if claim == "NOT_A_CLAIM":
            return {
                "claim": headline_raw,
                "normalized_claim": headline_raw,
                "verdict": "UNVERIFIABLE",
                "confidence": 0.50,
                "summary": "Input is not a verifiable factual claim.",
                "reason": "Input lacks concrete factual assertions (e.g. question, opinion, or headline fragment).",
                "explanation": "Input does not contain a verifiable factual claim.",
                "conflicting_sources": False,
                "sources": [],
            }

        normalized_claim = self.cleaner.clean(claim) or claim
        cached = self.get_cached_result(normalized_claim)
        if cached:
            self.logger.info("cache_hit claim=%s", normalized_claim[:50])
            return cached

        # Generate compact search query for maximum recall
        search_query = self.generate_query(normalized_claim)
        if not search_query or len(search_query.split()) < 2:
            search_query = normalized_claim

        # 1. Concurrent dual-stream evidence retrieval
        news_items: List[Dict[str, Any]] = []
        wiki_items: List[Dict[str, Any]] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_news = executor.submit(self.google_news.search, search_query, 6)
            future_wiki = executor.submit(self.wikipedia.search, search_query, 3, normalized_claim)
            try:
                news_items = future_news.result(timeout=4.5)
            except Exception as exc:
                self.logger.warning("google_news_retrieval_failed error=%s", exc)

            try:
                wiki_items = future_wiki.result(timeout=4.5)
            except Exception as exc:
                self.logger.warning("wikipedia_retrieval_failed error=%s", exc)

        combined_sources = news_items + wiki_items

        # If initial query yielded nothing, retry with normalized claim directly
        if not combined_sources and search_query != normalized_claim:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_news = executor.submit(self.google_news.search, normalized_claim, 5)
                future_wiki = executor.submit(self.wikipedia.search, normalized_claim, 2, normalized_claim)
                try:
                    retry_news = future_news.result(timeout=4.0)
                except Exception:
                    retry_news = []
                try:
                    retry_wiki = future_wiki.result(timeout=4.0)
                except Exception:
                    retry_wiki = []
                combined_sources = retry_news + retry_wiki

        # 2. Autonomous semantic stance & veracity evaluation
        verdict_res = self.verdict_generator.evaluate_claim_autonomously(
            normalized_claim, sources=combined_sources
        )

        result = {
            "claim": headline_raw,
            "normalized_claim": normalized_claim,
            "verdict": verdict_res["verdict"],
            "confidence": verdict_res["confidence"],
            "summary": verdict_res["summary"],
            "reason": verdict_res["explanation"],
            "explanation": verdict_res["explanation"],
            "conflicting_sources": verdict_res.get("conflicting_sources", False),
            "sources": verdict_res.get("sources", []),
        }

        self.set_cached_result(normalized_claim, result)
        return result


__all__ = ["VerificationPipeline"]
