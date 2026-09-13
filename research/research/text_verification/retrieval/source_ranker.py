import math
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Dict, Any, List, Optional, Tuple, Literal

SourceType = Literal["official", "institutional", "news", "encyclopedia", "other"]

# Reliability weighting policy
SOURCE_TIER_SCORES: Dict[SourceType, float] = {
    "official": 1.00,        # Primary government / international official archives (.gov, .mil, un.org)
    "institutional": 0.90,   # Major scientific / institutional / peer-reviewed (who.int, cdc.gov, nature.com)
    "news": 0.75,            # Established primary news organizations (Reuters, AP, BBC, NYT, etc.)
    "encyclopedia": 0.65,    # Structured encyclopedic reference (Wikipedia, Wikidata)
    "other": 0.25,           # Unknown blogs, social platforms, general aggregator
}

OFFICIAL_DOMAINS = {
    "gov", "mil", "europa.eu", "un.org", "nasa.gov", "whitehouse.gov",
    "state.gov", "defense.gov", "parliament.uk", "gov.uk"
}

INSTITUTIONAL_DOMAINS = {
    "who.int", "cdc.gov", "nature.com", "science.org", "nejm.org",
    "thelancet.com", "iea.org", "imf.org", "worldbank.org", "noaa.gov", "nih.gov"
}

ESTABLISHED_NEWS_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "bloomberg.com",
    "wsj.com", "nytimes.com", "washingtonpost.com", "theguardian.com",
    "ft.com", "aljazeera.com", "afp.com", "npr.org", "cnn.com", "abcnews.go.com"
}

ENCYCLOPEDIA_DOMAINS = {
    "wikipedia.org", "wikidata.org", "britannica.com"
}


class SourceRanker:
    """Evaluates source credibility, freshness decay, and consensus ranking."""

    HALF_LIFE_DAYS = 30.0  # Freshness score decays to 0.5 after 30 days for breaking claims

    @classmethod
    def classify_source_type(cls, url: Optional[str], source_name: Optional[str] = None) -> SourceType:
        """Determines the epistemic source type based on URL domain or publisher name."""
        domain = ""
        if url:
            try:
                parsed = urlparse(url)
                domain = (parsed.hostname or "").lower()
            except Exception:
                domain = ""

        src_lower = (source_name or "").lower()

        # Check official
        if any(domain.endswith("." + d) or domain == d for d in OFFICIAL_DOMAINS) or "government" in src_lower:
            return "official"

        # Check institutional
        if any(d in domain for d in INSTITUTIONAL_DOMAINS) or any(d in src_lower for d in ["who", "cdc", "nih", "nature", "science"]):
            return "institutional"

        # Check encyclopedia
        if any(d in domain for d in ENCYCLOPEDIA_DOMAINS) or "wikipedia" in src_lower or "britannica" in src_lower:
            return "encyclopedia"

        # Check established news
        if any(d in domain for d in ESTABLISHED_NEWS_DOMAINS) or any(
            d in src_lower for d in ["reuters", "associated press", "ap news", "bbc", "bloomberg", "wall street journal", "new york times", "the guardian"]
        ):
            return "news"

        return "other"

    @classmethod
    def compute_freshness_score(cls, published_at: Optional[str], is_time_sensitive: bool = True) -> float:
        """
        Computes exponential freshness decay: exp(-age_in_days / half_life_days).
        For historical/encyclopedic claims, decay is relaxed.
        """
        if not is_time_sensitive:
            return 1.0

        if not published_at:
            return 0.70  # Default for undated sources

        try:
            # Parse ISO or standard date formats
            date_clean = published_at.strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(date_clean)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
            return float(math.exp(-age_days / cls.HALF_LIFE_DAYS))
        except Exception:
            return 0.70

    @classmethod
    def rank_source(
        cls,
        source: Dict[str, Any],
        relevance: float = 1.0,
        is_time_sensitive: bool = True
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Ranks a single source item based on credibility tier, freshness, and relevance.
        
        Returns:
            Tuple of (composite_quality_score, metadata_dict)
        """
        url = source.get("url") or ""
        name = source.get("source") or source.get("publisher") or "Unknown"
        pub_date = source.get("published_at")

        src_type = cls.classify_source_type(url, name)
        base_credibility = SOURCE_TIER_SCORES[src_type]
        freshness = cls.compute_freshness_score(pub_date, is_time_sensitive=is_time_sensitive)

        # Composite score weighted: 50% credibility, 30% relevance, 20% freshness
        composite = (0.50 * base_credibility) + (0.30 * min(1.0, relevance)) + (0.20 * freshness)
        composite = round(min(1.0, max(0.0, composite)), 3)

        meta = {
            "source_type": src_type,
            "credibility_score": base_credibility,
            "freshness_score": round(freshness, 3),
            "composite_score": composite,
            "publisher": name,
        }
        return composite, meta
