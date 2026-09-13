import re
from typing import Literal, Tuple, Dict, Any

ClaimType = Literal[
    "historical",
    "current_event",
    "numeric",
    "quote",
    "medical",
    "scientific",
    "political",
    "opinion",
    "prediction",
    "satire",
    "non_verifiable",
]


class ClaimClassifier:
    """Classifies claims by epistemic type and checks whether the statement
    is factually verifiable or subjective / non-testable.
    """

    OPINION_PATTERNS = [
        re.compile(r"\b(?:in my opinion|i think|i believe|i feel|personally)\b", re.IGNORECASE),
        re.compile(r"\b(?:the best|the greatest|the worst|the most beautiful|terrible|awesome|horrible)\b", re.IGNORECASE),
        re.compile(r"\b(?:should be|ought to be|is arguably|is overrated|is underrated)\b", re.IGNORECASE),
    ]

    PREDICTION_PATTERNS = [
        re.compile(r"\b(?:will happen|will become|will reach|is predicted to|is expected to|will surpass|by 203\d|by 204\d|by 205\d)\b", re.IGNORECASE),
        re.compile(r"\b(?:future of|might soon|could soon|forecasts suggest)\b", re.IGNORECASE),
    ]

    SATIRE_PATTERNS = [
        re.compile(r"\b(?:the onion|babylon bee|satire|parody|humor|comedian jokes)\b", re.IGNORECASE),
    ]

    QUOTE_PATTERNS = [
        re.compile(r"[\"“][^\"”]{10,}[\"”]", re.IGNORECASE),
        re.compile(r"\b(?:said that|stated that|claimed that|tweeted that|remarked that|quoted as saying)\b", re.IGNORECASE),
    ]

    NUMERIC_PATTERNS = [
        re.compile(r"\b\d+(?:\.\d+)?%\b"),
        re.compile(r"[\$€£¥]\s*\d+"),
        re.compile(r"\b\d+\s*(?:billion|million|trillion|thousand|percent|degrees|celsius|fahrenheit)\b", re.IGNORECASE),
        re.compile(r"\b(?:increased by|decreased by|surged by|dropped by|rose by|fell by)\s*\d+", re.IGNORECASE),
    ]

    MEDICAL_PATTERNS = [
        re.compile(r"\b(?:vaccin(?:e|es|ation)|cure|cancer|covid|virus|fda|clinical trial|treatment|pharmaceutical|disease|hospital)\b", re.IGNORECASE),
    ]

    SCIENTIFIC_PATTERNS = [
        re.compile(r"\b(?:nasa|space|telescope|mars|moon|planet|physics|quantum|galaxy|species|fossil|climate change|greenhouse)\b", re.IGNORECASE),
    ]

    POLITICAL_PATTERNS = [
        re.compile(r"\b(?:president|prime minister|senat(?:e|or)|congress|parliament|election|ballot|governor|democrat|republican|legislation)\b", re.IGNORECASE),
    ]

    HISTORICAL_PATTERNS = [
        re.compile(r"\b(?:in 1[789]\d\d|in 200\d|in 201[0-9]|in the 19th century|in the 20th century|world war|ancient|treaty of)\b", re.IGNORECASE),
    ]

    @classmethod
    def classify(cls, claim: str) -> Tuple[ClaimType, bool, str]:
        """
        Classifies claim and determines whether it represents an empirically verifiable statement.
        
        Returns:
            Tuple of (claim_type, is_verifiable, explanation)
        """
        text = (claim or "").strip()
        if not text or len(text) < 5 or text.endswith("?"):
            return "non_verifiable", False, "Input is a question or conversational fragment rather than a factual assertion."

        # 1. Subjective opinion check
        if any(pattern.search(text) for pattern in cls.OPINION_PATTERNS):
            return "opinion", False, "This is a subjective opinion or value judgment rather than a factually testable claim."

        # 2. Future prediction check
        if any(pattern.search(text) for pattern in cls.PREDICTION_PATTERNS):
            return "prediction", False, "This is a prediction about future events that cannot be empirically verified today."

        # 3. Satire / Parody check
        if any(pattern.search(text) for pattern in cls.SATIRE_PATTERNS):
            return "satire", False, "This claim matches known satire, humor, or parody conventions."

        # 4. Quote attribution
        if any(pattern.search(text) for pattern in cls.QUOTE_PATTERNS):
            return "quote", True, "Quote attribution claim testable against public records and statements."

        # 5. Numerical / Statistical
        if any(pattern.search(text) for pattern in cls.NUMERIC_PATTERNS):
            return "numeric", True, "Quantitative / statistical assertion testable against reported metrics."

        # 6. Domain-specific factual categories
        if any(pattern.search(text) for pattern in cls.MEDICAL_PATTERNS):
            return "medical", True, "Health or medical claim testable against clinical and institutional guidelines."

        if any(pattern.search(text) for pattern in cls.SCIENTIFIC_PATTERNS):
            return "scientific", True, "Scientific or natural phenomenon assertion."

        if any(pattern.search(text) for pattern in cls.POLITICAL_PATTERNS):
            return "political", True, "Political, legislative, or governance assertion."

        if any(pattern.search(text) for pattern in cls.HISTORICAL_PATTERNS):
            return "historical", True, "Historical fact verifiable against reference archives."

        return "current_event", True, "Contemporary event assertion verifiable against live news coverage."
