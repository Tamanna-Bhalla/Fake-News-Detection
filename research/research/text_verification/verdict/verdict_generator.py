import json
import logging
import os
import re
import socket
import time
from urllib.parse import urlparse
from typing import Dict, Any, List, Optional
import requests
from requests.exceptions import ReadTimeout

from text_verification.utils.source_credibility import get_source_credibility


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
        """Autonomous fact-checking evaluation utilizing semantic similarity,
        refutation detection, reporting consensus, and source credibility weighting.
        """
        claim_clean = (claim or "").strip()
        if not sources:
            return {
                "claim": claim_clean,
                "verdict": "Not Enough Information",
                "confidence": 0.50,
                "summary": "No credible news or reference sources were found discussing this claim.",
                "explanation": "Searches across live news coverage and reference archives yielded no corroborating or refuting evidence.",
                "conflicting_sources": False,
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

        evaluated_sources = []
        refuting_sources = []
        corroborating_sources = []

        claim_words = set(re.findall(r"\b\w{3,}\b", claim_clean.lower()))

        for i, item in enumerate(sources):
            full_text = full_texts[i]
            src_name = (item.get("source") or "News Source").strip()

            if similarities is not None:
                similarity = similarities[i]
            else:
                doc_words = set(re.findall(r"\b\w{3,}\b", full_text.lower()))
                similarity = len(claim_words & doc_words) / max(1, len(claim_words))

            credibility = get_source_credibility(item.get("url") or src_name)
            cred_weight = 1.3 if credibility == "High" else (1.0 if credibility == "Medium" else 0.7)

            evaluated_item = dict(item)
            evaluated_item["similarity"] = round(similarity, 3)
            evaluated_item["credibility"] = credibility
            evaluated_sources.append(evaluated_item)

            is_refuting = self._check_is_refuting(full_text, src_name) and similarity >= 0.22
            is_affirming = any(p.search(full_text) for p in self.AFFIRM_PATTERNS) or similarity >= 0.48

            if is_refuting:
                refuting_sources.append(evaluated_item)
            elif similarity >= 0.32:
                corroborating_sources.append(evaluated_item)

        # Compute weighted evidence scores
        refute_score = sum(s["similarity"] * 1.5 * (1.3 if s["credibility"] == "High" else 1.0) for s in refuting_sources)
        support_score = sum(s["similarity"] * (1.3 if s["credibility"] == "High" else 1.0) for s in corroborating_sources)
        top_sim = max((s["similarity"] for s in evaluated_sources), default=0.0)

        # Sort sources by relevance
        evaluated_sources.sort(key=lambda s: s["similarity"], reverse=True)

        # Decision Matrix
        if refute_score >= 0.45 or (refuting_sources and any(s["similarity"] >= 0.38 for s in refuting_sources)):
            verdict = "False"
            confidence = round(min(0.96, 0.72 + (refute_score * 0.12)), 2)
            top_refute = refuting_sources[0]
            refuter_names = ", ".join(dict.fromkeys(s["source"] for s in refuting_sources[:3]))
            summary = f"Refuted by fact-checking and news reporting from {refuter_names}."
            explanation = (
                f"Independent reporting and fact-checking records refute this claim. "
                f"Key evidence from {top_refute['source']}: \"{top_refute['title']}\" "
                f"({top_refute.get('content', '')[:160]}...)"
            )
            has_conflict = len(corroborating_sources) > 0

        elif support_score >= 0.50 and refute_score < 0.20:
            verdict = "True"
            confidence = round(min(0.96, 0.65 + (support_score * 0.12)), 2)
            top_support = corroborating_sources[0]
            supporter_names = ", ".join(dict.fromkeys(s["source"] for s in corroborating_sources[:3]))
            summary = f"Corroborated by independent reporting from {supporter_names}."
            explanation = (
                f"Multiple credible news and reference sources corroborate this claim. "
                f"Primary report from {top_support['source']}: \"{top_support['title']}\" "
                f"({top_support.get('content', '')[:160]}...)"
            )
            has_conflict = False

        elif support_score >= 0.30 and refute_score >= 0.25:
            verdict = "Misleading"
            confidence = 0.75
            summary = "Reporting presents conflicting accounts or indicates key contextual omissions in the claim."
            explanation = (
                f"Available news reports present conflicting or disputed accounts. "
                f"Corroborating reports exist alongside refuting or cautionary statements."
            )
            has_conflict = True

        elif support_score >= 0.32:
            verdict = "True"
            confidence = 0.70
            top_support = corroborating_sources[0]
            summary = f"Corroborated by news coverage from {top_support['source']}."
            explanation = f"Reporting from {top_support['source']} supports the claim: \"{top_support['title']}\""
            has_conflict = False

        else:
            verdict = "Not Enough Information"
            confidence = 0.50
            summary = "Available sources discuss related topics, but do not provide definitive confirmation or refutation."
            explanation = "The claim could not be decisively verified as True or False based on currently available news and reference coverage."
            has_conflict = False

        return {
            "claim": claim_clean,
            "verdict": verdict,
            "confidence": confidence,
            "summary": summary,
            "explanation": explanation,
            "conflicting_sources": has_conflict,
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
