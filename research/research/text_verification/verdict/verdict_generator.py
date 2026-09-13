import json
import logging
import os
import re
import socket
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, Any, List, Optional
import requests
from requests.exceptions import ReadTimeout

# Enable standalone execution
_research_dir = Path(__file__).resolve().parent.parent.parent
if str(_research_dir) not in sys.path:
    sys.path.insert(0, str(_research_dir))

from text_verification.utils.source_credibility import get_source_credibility
from text_verification.retrieval.source_ranker import SourceRanker
from text_verification.verdict.evidence_extractor import EvidenceExtractor



class VerdictGenerator:
    """Hybrid fact-checking verdict generator supporting both local LLM (Ollama)
    and an autonomous semantic stance-and-veracity evaluation engine.
    """

    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")

    REFUTE_PATTERNS = [
        re.compile(r"\b(?:fact[- ]?check(?:ed)?|factcheck)\b", re.IGNORECASE),
        re.compile(r"\b(?:no evidence|lack of evidence|without evidence|no scientific evidence)\b", re.IGNORECASE),
        re.compile(r"\b(?:is false|was false|is a hoax|is fake|debunk(?:ed|s|ing)?|untrue|disproven|disproved|refut(?:ed|es|ing)|deni(?:ed|es|ing))\b", re.IGNORECASE),
        re.compile(r"\b(?:baseless|unfounded|fabricated|myth|unproven|incorrect|disputed|misleading|fringe theory)\b", re.IGNORECASE),
        re.compile(r"\b(?:falsely claimed|falsely reported|falsely stated|falsely accused|false claims?)\b", re.IGNORECASE),
        re.compile(r"\b(?:conspiracy theory|debunking|disputed claim|hoax|scam|rumor|rumour)\b", re.IGNORECASE),
        re.compile(r"\b(?:did not happen|never happened|not true|denies (?:rumors?|claims?|reports?)|warns? against|warned against)\b", re.IGNORECASE),
    ]

    AFFIRM_PATTERNS = [
        re.compile(r"\b(?:confirm(?:s|ed)?|officially|announc(?:es|ed)|report(?:s|ed)|authorities said)\b", re.IGNORECASE),
        re.compile(r"\b(?:elect(?:ed)?|won|signed|approv(?:ed)?|discover(?:ed)?|record high|record low)\b", re.IGNORECASE),
        re.compile(r"\b(?:pass(?:ed)?|verif(?:ied|ies)|records? show|document(?:ed)?|launche[ds]?)\b", re.IGNORECASE),
    ]

    def __init__(self):
        self.model_name = os.getenv("OLLAMA_MODEL", "mistral")
        configured_models = os.getenv("OLLAMA_MODELS", "").strip()
        if configured_models:
            self.model_candidates = [m.strip() for m in configured_models.split(",") if m.strip()]
        else:
            self.model_candidates = [self.model_name, "tinyllama"]
        self.logger = logging.getLogger(__name__)
        self._embedding_model = None

    @property
    def embedding_model(self):
        """Lazy-load the SentenceTransformer embedding model."""
        if self._embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception as e:
                self.logger.warning("failed_to_load_sentence_transformers: %s", e)
                self._embedding_model = False
        return self._embedding_model if self._embedding_model is not False else None

    def _is_ollama_available(self) -> bool:
        """Rapid 150ms socket probe to test whether local Ollama is listening."""
        try:
            parsed = urlparse(self.OLLAMA_URL)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 11434
            sock = socket.create_connection((host, port), timeout=0.15)
            sock.close()
            return True
        except Exception:
            return False

    def _normalize_verdict(self, label: str) -> str:
        value = (label or "").strip().lower()
        if value in {"true", "support", "supports", "supported"}:
            return "True"
        if value in {"false", "refute", "refutes", "refuted"}:
            return "False"
        if value in {"misleading", "mixed", "conflicting", "partially true", "partly true"}:
            return "Misleading"
        return "Not Enough Information"

    def _map_confidence(self, confidence_text: str) -> float:
        token = (confidence_text or "").strip().lower()
        if "high" in token:
            return 0.90
        if "medium" in token:
            return 0.70
        if "low" in token:
            return 0.50
        match = re.search(r"(\d+(?:\.\d+)?)", token)
        if match:
            val = float(match.group(1))
            return val / 100.0 if val > 1.0 else val
        return 0.50

    def _check_is_refuting(self, text: str, source_name: str) -> bool:
        """Context-aware refutation check."""
        if "wikipedia" in source_name.lower():
            wiki_refute = re.search(
                r"\b(?:conspiracy theory|debunked|hoax|common misconception|fringe theory)\b",
                text,
                re.IGNORECASE,
            )
            return bool(wiki_refute)

        for pattern in self.REFUTE_PATTERNS:
            if pattern.search(text):
                return True
        return False

    def evaluate_claim_autonomously(
        self, claim: str, sources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Evidence-based claim evaluation utilizing source quality tiers,
        freshness decay, excerpt extraction, stance classification, and calibrated uncertainty.
        """
        claim_clean = (claim or "").strip()
        if not sources:
            return {
                "claim": claim_clean,
                "status": "unavailable",
                "verdict": "Not Enough Information",
                "confidence": None,
                "summary": "No credible news or reference sources were found discussing this claim.",
                "explanation": "Searches across live news coverage and reference archives yielded no corroborating or refuting evidence.",
                "limitations": ["No search results found across live news feeds or reference archives."],
                "conflicting_sources": False,
                "evidence": [],
                "sources": [],
            }

        embedder = self.embedding_model
        if embedder is not None:
            claim_vec = embedder.encode([claim_clean], normalize_embeddings=True)[0]
        else:
            claim_vec = None

        full_texts = [
            f"{(item.get('title') or '').strip()}. {(item.get('content') or item.get('description') or '').strip()}"
            for item in sources
        ]

        if embedder is not None and claim_vec is not None:
            try:
                doc_vecs = embedder.encode(full_texts, normalize_embeddings=True)
                similarities = [
                    float(sum(c * d for c, d in zip(claim_vec, dv)))
                    for dv in doc_vecs
                ]
            except Exception:
                similarities = None
        else:
            similarities = None

        claim_words = set(re.findall(r"\b\w{3,}\b", claim_clean.lower()))

        evaluated_sources = []
        evidence_items = []
        refuting_evidence = []
        corroborating_evidence = []
        limitations = []

        has_official_or_institutional = False

        for i, item in enumerate(sources):
            full_text = full_texts[i]
            src_name = (item.get("source") or item.get("publisher") or "News Source").strip()

            if similarities is not None:
                similarity = float(similarities[i])
            else:
                doc_words = set(re.findall(r"\b\w{3,}\b", full_text.lower()))
                similarity = float(len(claim_words & doc_words) / max(1, len(claim_words)))

            # Source quality and freshness ranking
            quality_score, source_meta = SourceRanker.rank_source(item, relevance=similarity)
            if source_meta["source_type"] in ("official", "institutional"):
                has_official_or_institutional = True

            # Extract structured citation with stance classification and SHA-256 fingerprint
            evidence_item = EvidenceExtractor.create_evidence_item(
                item,
                claim_clean,
                relevance=similarity,
                source_type=source_meta["source_type"]
            )
            evidence_items.append(evidence_item)

            evaluated_item = dict(item)
            evaluated_item["similarity"] = round(similarity, 3)
            evaluated_item["credibility"] = source_meta["source_type"].capitalize()
            evaluated_item["quality_score"] = quality_score
            evaluated_item["stance"] = evidence_item["stance"]
            evaluated_sources.append(evaluated_item)

            if evidence_item["stance"] == "refutes" and similarity >= 0.22:
                refuting_evidence.append(evidence_item)
            elif evidence_item["stance"] == "supports" and similarity >= 0.30:
                corroborating_evidence.append(evidence_item)

        # Sort evidence by relevance
        evidence_items.sort(key=lambda e: e["relevance"], reverse=True)
        evaluated_sources.sort(key=lambda s: s["similarity"], reverse=True)

        if not has_official_or_institutional:
            limitations.append("No primary government or peer-reviewed institutional source identified.")

        SOURCE_TIER_WEIGHTS = {
            "official": 1.00,
            "institutional": 0.90,
            "news": 0.75,
            "encyclopedia": 0.65,
            "other": 0.15,
        }

        # Compute weighted support and refute scores using source authority tiers
        refute_score = sum(
            e["relevance"] * (1.3 if e["source_type"] in ("official", "institutional", "news", "encyclopedia") else 0.8)
            for e in refuting_evidence
        )
        support_score = sum(
            e["relevance"] * SOURCE_TIER_WEIGHTS.get(e["source_type"], 0.15)
            for e in corroborating_evidence
        )

        has_reputable_corroboration = any(
            e["source_type"] in ("official", "institutional", "news", "encyclopedia")
            for e in corroborating_evidence
        )

        # Check if the claim asserts formal attribution to an authoritative body
        attribution_match = re.search(
            r"\b(NASA|WHO|CDC|FDA|FBI|UN|Pentagon|White House|Supreme Court|Scientists|Researchers|Astronomers|Government)\b\s+(?:confirm(?:s|ed)?|announc(?:es|ed)?|prov(?:es|ed)?|claim(?:s|ed)?|declar(?:es|ed)?)",
            claim_clean,
            re.IGNORECASE
        )
        has_formal_attribution = bool(attribution_match)
        attributed_entity = attribution_match.group(1) if attribution_match else ""

        # Decision Matrix
        has_conflict = len(refuting_evidence) > 0 and len(corroborating_evidence) > 0

        # Case 1: Refuted / Debunked
        if refute_score >= 0.28 or (refuting_evidence and any(e["relevance"] >= 0.30 for e in refuting_evidence)):
            verdict = "False"
            status_val = "completed"
            confidence = round(min(0.96, 0.72 + (refute_score * 0.12)), 2)
            top_refute = refuting_evidence[0]
            refuter_names = ", ".join(dict.fromkeys(e["publisher"] for e in refuting_evidence[:3]))
            summary = f"Refuted by fact-checking, reference, and independent reporting from {refuter_names}."
            explanation = (
                f"Credible reference and reporting sources directly refute or classify this claim as a myth/conspiracy theory. "
                f"Key excerpt from {top_refute['publisher']}: \"{top_refute['excerpt']}\""
            )

        # Case 2: Verified / Supported (Requires reputable institutional, news, or reference corroboration)
        elif support_score >= 0.35 and refute_score < 0.18 and has_reputable_corroboration:
            status_val = "completed"
            top_support = corroborating_evidence[0]
            supporter_names = ", ".join(dict.fromkeys(e["publisher"] for e in corroborating_evidence[:3]))

            # Distinguish high-confidence Verified from Supported
            if len(corroborating_evidence) >= 2 and any(e["relevance"] >= 0.45 and e["source_type"] in ("official", "institutional", "news", "encyclopedia") for e in corroborating_evidence):
                verdict = "True"
                confidence = round(min(0.98, 0.78 + (support_score * 0.10)), 2)
                summary = f"Verified by consistent reporting across multiple independent sources ({supporter_names})."
            else:
                verdict = "True"
                confidence = round(min(0.88, 0.65 + (support_score * 0.10)), 2)
                summary = f"Supported by reporting from {supporter_names}."

            explanation = (
                f"Available credible sources corroborate this claim. "
                f"Primary excerpt from {top_support['publisher']}: \"{top_support['excerpt']}\""
            )

        # Case 3: Conflicting / Disputed context
        elif has_conflict and support_score >= 0.25 and refute_score >= 0.20:
            verdict = "Misleading"
            status_val = "inconclusive"
            confidence = 0.65
            summary = "Reporting presents conflicting accounts or disputed context regarding this claim."
            explanation = (
                "Available news and reference reports present conflicting accounts. "
                "Corroborating statements exist alongside refuting or cautionary assessments."
            )
            limitations.append("Conflicting claims or disputed accounts detected across independent publishers.")

        # Case 4: Insufficient Evidence / Uncorroborated Attribution
        else:
            verdict = "Not Enough Information"
            status_val = "inconclusive"
            confidence = None
            if has_formal_attribution:
                summary = f"Unverified attribution: No official confirmation from {attributed_entity} was found in authoritative sources."
                explanation = f"The claim asserts that {attributed_entity} confirmed or announced this finding, but no direct records from official archives or major news agencies corroborate it."
                limitations.append(f"No direct confirmation found from official {attributed_entity} records.")
            else:
                summary = "Available sources discuss related topics, but do not directly confirm or refute the claim."
                explanation = "Evidence is insufficient to reach a conclusive verdict. Additional authoritative sources are required."
                limitations.append("Retrieved coverage lacks direct confirmation or refutation of the core assertion.")

        return {
            "claim": claim_clean,
            "status": status_val,
            "verdict": verdict,
            "confidence": confidence,
            "summary": summary,
            "explanation": explanation,
            "limitations": limitations,
            "conflicting_sources": has_conflict,
            "evidence": evidence_items[:6],
            "sources": evaluated_sources[:5],
        }


    def generate_direct_claim(self, claim: str) -> Dict[str, Any]:
        """Direct verification via local Ollama if online; raises RuntimeError if offline."""
        if not self._is_ollama_available():
            raise RuntimeError("Ollama server is not available.")

        prompt = (
            "You are a strict fact-checker.\n"
            "Classify the claim into exactly one verdict: TRUE, FALSE, or UNSURE.\n"
            "Return JSON only with this schema:\n"
            "{\n"
            "  \"verdict\": \"TRUE|FALSE|UNSURE\",\n"
            "  \"confidence\": 0.0-1.0,\n"
            "  \"reason\": \"one short sentence\"\n"
            "}\n\n"
            f"Claim: {claim}\n"
        )
        for candidate in self.model_candidates:
            try:
                resp = requests.post(
                    self.OLLAMA_URL,
                    json={"model": candidate, "prompt": prompt, "stream": False},
                    timeout=(1.0, 15.0),
                )
                resp.raise_for_status()
                raw = (resp.json().get("response") or "").strip()
                match = re.search(r"\{[\s\S]*\}", raw)
                if match:
                    obj = json.loads(match.group(0))
                    verdict = str(obj.get("verdict", "UNSURE")).strip().upper()
                    conf = float(obj.get("confidence", 0.5) or 0.5)
                    reason = str(obj.get("reason", ""))
                    return {"verdict": verdict, "confidence": conf, "reason": reason}
            except Exception:
                continue

        raise RuntimeError("No Ollama model responded.")

    def generate(
        self,
        claim: str,
        sources: List[Dict[str, Any]],
        agreement_summary: str = "",
        credibility_summary: str = "",
    ) -> Dict[str, Any]:
        """Generate a structured verdict using autonomous evaluation (or Ollama if configured)."""
        return self.evaluate_claim_autonomously(claim, sources)


__all__ = ["VerdictGenerator"]


if __name__ == "__main__":
    print("=" * 70)
    print("DTI Text Verification Engine — Standalone Verdict Generator Demo")
    print("=" * 70)

    generator = VerdictGenerator()

    # Demo 1: Corroborated / Verified Claim
    sample_claim_1 = "NASA telescope observes water vapor on distant exoplanet"
    sample_sources_1 = [
        {
            "title": "Webb Space Telescope Identifies Atmospheric Water on Exoplanet",
            "url": "https://www.nasa.gov/missions/webb/atmospheric-water-exoplanet",
            "publisher": "NASA",
            "source": "NASA",
            "snippet": "NASA scientists officially confirmed the detection of water vapor in the atmosphere of a giant gas exoplanet using the James Webb Space Telescope.",
            "published_at": "2024-05-12T00:00:00Z"
        },
        {
            "title": "Astronomers verify atmospheric water signatures",
            "url": "https://nature.com/articles/exoplanet-atmosphere-water",
            "publisher": "Nature",
            "source": "Nature",
            "snippet": "Independent peer-reviewed spectroscopic records verify the presence of atmospheric water vapor on the target planet.",
            "published_at": "2024-05-15T00:00:00Z"
        }
    ]

    print(f"\nEvaluating Claim 1: \"{sample_claim_1}\"")
    result_1 = generator.generate(sample_claim_1, sample_sources_1)
    print(f"  Verdict:    {result_1['verdict']} (Confidence: {result_1['confidence']})")
    print(f"  Summary:    {result_1['summary']}")
    print(f"  Evidence:   {len(result_1['evidence'])} citations extracted")
    for ev in result_1['evidence']:
        print(f"    - [{ev['stance'].upper()}] {ev['publisher']}: \"{ev['excerpt'][:70]}...\"")

    # Demo 2: Refuted Claim
    sample_claim_2 = "Scientists announce Moon was completely hollowed out by ancient aliens"
    sample_sources_2 = [
        {
            "title": "Fact Check: Debunking viral hollow moon alien base conspiracy theory",
            "url": "https://reuters.com/fact-check/hollow-moon-aliens-debunked",
            "publisher": "Reuters",
            "source": "Reuters",
            "snippet": "Fact-checking organizations have thoroughly debunked viral social media claims alleging the Moon is hollow. NASA planetary records confirm seismic data showing a solid iron core.",
            "published_at": "2024-06-01T00:00:00Z"
        }
    ]

    print(f"\nEvaluating Claim 2: \"{sample_claim_2}\"")
    result_2 = generator.generate(sample_claim_2, sample_sources_2)
    print(f"  Verdict:    {result_2['verdict']} (Confidence: {result_2['confidence']})")
    print(f"  Summary:    {result_2['summary']}")
    for ev in result_2['evidence']:
        print(f"    - [{ev['stance'].upper()}] {ev['publisher']}: \"{ev['excerpt'][:70]}...\"")

    # Demo 3: Inconclusive Claim (Not Enough Information)
    sample_claim_3 = "New transit line proposed between two neighboring towns"
    sample_sources_3 = [
        {
            "title": "General regional transportation overview and highway report",
            "url": "https://example.com/transit",
            "publisher": "Local Forum",
            "source": "Local Forum",
            "snippet": "Discussion of regional road networks and traffic signals across county routes.",
            "published_at": "2023-01-01T00:00:00Z"
        }
    ]

    print(f"\nEvaluating Claim 3: \"{sample_claim_3}\"")
    result_3 = generator.generate(sample_claim_3, sample_sources_3)
    print(f"  Verdict:    {result_3['verdict']} (Confidence: {result_3['confidence']})")
    print(f"  Summary:    {result_3['summary']}")
    print(f"  Limitations: {result_3['limitations']}")

    print("\n" + "=" * 70)
    print("Standalone execution completed successfully.")
    print("=" * 70)

