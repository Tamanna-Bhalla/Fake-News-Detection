import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
research_dir = backend_dir.parent / "research" / "research"
sys.path.insert(0, str(research_dir))

from text_verification.retrieval.source_ranker import SourceRanker, SOURCE_TIER_SCORES


class TestSourceRanker(unittest.TestCase):
    def test_classify_source_tiers(self):
        # Official
        self.assertEqual(SourceRanker.classify_source_type("https://www.nasa.gov/news/article"), "official")
        self.assertEqual(SourceRanker.classify_source_type("https://whitehouse.gov/briefing"), "official")
        self.assertEqual(SourceRanker.classify_source_type(None, "Government Press Office"), "official")

        # Institutional
        self.assertEqual(SourceRanker.classify_source_type("https://www.who.int/emergencies"), "institutional")
        self.assertEqual(SourceRanker.classify_source_type("https://www.nature.com/articles/s41586"), "institutional")
        self.assertEqual(SourceRanker.classify_source_type("https://www.nejm.org/data"), "institutional")


        # News
        self.assertEqual(SourceRanker.classify_source_type("https://www.reuters.com/world"), "news")
        self.assertEqual(SourceRanker.classify_source_type("https://apnews.com/article"), "news")
        self.assertEqual(SourceRanker.classify_source_type("https://www.bbc.com/news"), "news")

        # Encyclopedia
        self.assertEqual(SourceRanker.classify_source_type("https://en.wikipedia.org/wiki/Moon"), "encyclopedia")

        # Unknown / Other
        self.assertEqual(SourceRanker.classify_source_type("https://randomblog.wordpress.com/post"), "other")

    def test_freshness_decay(self):
        now = datetime.now(timezone.utc)
        today_iso = now.isoformat()
        two_months_ago_iso = (now - timedelta(days=60)).isoformat()

        fresh_score = SourceRanker.compute_freshness_score(today_iso)
        self.assertGreaterEqual(fresh_score, 0.95)

        aged_score = SourceRanker.compute_freshness_score(two_months_ago_iso)
        # exp(-60 / 30) = exp(-2) ~= 0.135
        self.assertLess(aged_score, 0.20)
        self.assertGreater(fresh_score, aged_score)

    def test_composite_rank_official_vs_blog(self):
        now_iso = datetime.now(timezone.utc).isoformat()
        official_src = {
            "url": "https://www.nasa.gov/press-release",
            "source": "NASA",
            "published_at": now_iso
        }
        blog_src = {
            "url": "https://conspiracyblog123.com/post",
            "source": "My Personal Blog",
            "published_at": now_iso
        }

        official_score, off_meta = SourceRanker.rank_source(official_src, relevance=0.9)
        blog_score, blog_meta = SourceRanker.rank_source(blog_src, relevance=0.9)

        self.assertEqual(off_meta["source_type"], "official")
        self.assertEqual(blog_meta["source_type"], "other")
        self.assertGreater(official_score, blog_score)
        self.assertGreaterEqual(official_score, 0.85)


if __name__ == "__main__":
    unittest.main()
