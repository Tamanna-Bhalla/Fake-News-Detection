import hashlib
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Literal

StanceType = Literal["supports", "refutes", "neutral", "unrelated"]


class EvidenceExtractor:
    """Extracts concise, high-relevance evidence excerpts, computes content hashes,
    and classifies stance against the claim.
    """

    REFUTE_KEYWORDS = [
        re.compile(r"\b(?:fact[- ]?check(?:ed)?|debunk(?:ed|s|ing)?|hoax|untrue|false|fake|disproven|disproved|unproven|myth|fabricat(?:ed|ion))\b", re.IGNORECASE),
        re.compile(r"\b(?:conspiracy(?:\s+theory)?|pseudoscientific|pseudoscience|fringe theory|urban legend|folklore)\b", re.IGNORECASE),
        re.compile(r"\b(?:no evidence|lack of evidence|without evidence|baseless|unfounded|refut(?:ed|es|ing)|deni(?:ed|es|ing))\b", re.IGNORECASE),
        re.compile(r"\b(?:falsely claimed|falsely reported|misleading|disputed claim|did not happen|never happened|denies)\b", re.IGNORECASE),
        re.compile(r"\b(?:movie|film|fictional|sci-fi|science fiction|entertainment|spoof|satire)\b", re.IGNORECASE),
    ]

    SUPPORT_KEYWORDS = [
        re.compile(r"\b(?:confirm(?:s|ed)?|officially|verified|announced?|announces|reported?|reports|authorities said)\b", re.IGNORECASE),
        re.compile(r"\b(?:succeed(?:ed|s)?|land(?:ed|s|ing)?|launched?|discover(?:ed|y)|discoveries|record high|record low|elected|won)\b", re.IGNORECASE),
        re.compile(r"\b(?:passed|signed|approved|established|corroborat(?:ed|es)|demonstrat(?:ed|es)|documented|shows? that|evidence shows?)\b", re.IGNORECASE),
        re.compile(r"\b(?:is the \w+ (?:planet|president|country|largest|first|second|third|fourth|fifth|longest|highest|fastest))\b", re.IGNORECASE),
        re.compile(r"\b(?:eradicated|eliminated|approved by|concluded that|records? show|findings show)\b", re.IGNORECASE),
    ]

    @classmethod
    def compute_content_hash(cls, text: str) -> str:
        """Generates deterministic SHA-256 content fingerprint for auditability and snapshot verification."""
        clean = (text or "").strip().encode("utf-8")
        return hashlib.sha256(clean).hexdigest()[:16]

    @classmethod
    def extract_salient_excerpt(cls, full_text: str, claim: str, max_chars: int = 240) -> str:
        """Extracts the most contextually relevant sentence or excerpt from source content."""
        if not full_text:
            return ""

        sentences = re.split(r"(?<=[.!?])\s+", full_text.strip())
        claim_tokens = set(re.findall(r"\b\w{3,}\b", claim.lower()))

        best_sentence = sentences[0]
        best_overlap = -1

        for sentence in sentences:
            s_tokens = set(re.findall(r"\b\w{3,}\b", sentence.lower()))
            overlap = len(claim_tokens & s_tokens)
            # Bonus if refutation or confirmation keywords are present
            if any(p.search(sentence) for p in cls.REFUTE_KEYWORDS + cls.SUPPORT_KEYWORDS):
                overlap += 2

            if overlap > best_overlap:
                best_overlap = overlap
                best_sentence = sentence

        excerpt = best_sentence.strip()
        if len(excerpt) > max_chars:
            excerpt = excerpt[: max_chars - 3].rstrip() + "..."
        return excerpt

    @classmethod
    def classify_stance(cls, text: str, relevance: float, source_type: str = "news") -> StanceType:
        """Classifies the stance of an excerpt relative to the claim.
        Balances strict debunking protection with reliable confirmation of factual records.
        """
        if relevance < 0.22:
            return "unrelated"

        # Check if lead sentence or headline is an inquisitive/rhetorical question
        first_sentence = text.strip().split(".")[0].split("\n")[0]
        is_question = bool(re.search(r"\?\s*$", first_sentence))

        has_refute = any(pattern.search(text) for pattern in cls.REFUTE_KEYWORDS)
        has_support = any(pattern.search(text) for pattern in cls.SUPPORT_KEYWORDS)

        # 1. Refutation and debunking take highest precedence
        if has_refute and relevance >= 0.20:
            return "refutes"

        # 2. Rhetorical questions or conflicting phrasing denote neutral context
        if is_question or (has_refute and has_support):
            return "neutral"

        # 3. Explicit affirming confirmation keywords
        if has_support and relevance >= 0.28:
            return "supports"

        # 4. High-confidence authoritative reference corroboration
        # When an established encyclopedia (Wikipedia) or institutional/official source
        # has high relevance (>= 0.48) with zero refutation/conspiracy markers, it corroborates the fact
        if source_type in ("encyclopedia", "official", "institutional", "news") and relevance >= 0.48:
            return "supports"

        return "neutral"

    @classmethod
    def create_evidence_item(
        cls,
        source: Dict[str, Any],
        claim: str,
        relevance: float,
        source_type: str = "news"
    ) -> Dict[str, Any]:
        """Builds a standardized evidence citation item."""
        title = (source.get("title") or "Untitled Source").strip()
        content = (source.get("content") or source.get("description") or title).strip()
        full_text = f"{title}. {content}"

        excerpt = cls.extract_salient_excerpt(full_text, claim)
        stance = cls.classify_stance(full_text, relevance, source_type=source_type)
        content_hash = cls.compute_content_hash(full_text)
        retrieved_at = datetime.now(timezone.utc).isoformat()

        return {
            "url": source.get("url") or "https://news.google.com",
            "title": title,
            "publisher": source.get("source") or source.get("publisher") or "News Source",
            "published_at": source.get("published_at"),
            "excerpt": excerpt,
            "stance": stance,
            "relevance": round(float(relevance), 3),
            "source_type": source_type,
            "content_hash": content_hash,
            "retrieved_at": retrieved_at,
        }
