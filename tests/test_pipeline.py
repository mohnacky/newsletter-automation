"""Tests. Run: python -m unittest discover -s tests -v"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from newsletter.config import Config, load_config  # noqa: E402
from newsletter.editor import build_system_prompt, lint, sources_manifest  # noqa: E402
from newsletter.gather import get as get_source  # noqa: E402
from newsletter.gather import rows as rows_source  # noqa: E402
from newsletter.render import render_body, tag_url  # noqa: E402
from newsletter.run import next_send_date  # noqa: E402
from newsletter.schema import SectionSpec, build_issue_model  # noqa: E402

DEMO = ROOT / "examples" / "demo"


def demo_config() -> Config:
    return load_config(DEMO / "newsletter.yaml")


def demo_issue(cfg: Config):
    model = build_issue_model(cfg.sections)
    data = json.loads((DEMO / "fixtures" / "draft.json").read_text())
    return model(**{k: v for k, v in data.items() if not k.startswith("_")})


class TestSchema(unittest.TestCase):
    def test_config_drives_the_schema(self):
        cfg = demo_config()
        model = build_issue_model(cfg.sections)
        for spec in cfg.sections:
            self.assertIn(spec.id, model.model_fields, spec.id)

    def test_unknown_section_type_is_rejected(self):
        with self.assertRaises(ValueError):
            build_issue_model([SectionSpec(id="x", type="carousel")])

    def test_optional_sections_default_empty(self):
        model = build_issue_model([SectionSpec(id="extra", type="story")])
        issue = model(subject="s", preview_text="p", headline="h", thesis="t", read_minutes=3)
        self.assertIsNone(issue.extra)

    def test_table_section_requires_rows_from(self):
        import yaml

        bad = yaml.safe_load((DEMO / "newsletter.yaml").read_text())
        for section in bad["sections"]:
            if section["type"] == "table":
                del section["rows_from"]
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            yaml.safe_dump(bad, fh)
            path = Path(fh.name)
        with self.assertRaises(ValueError):
            load_config(path)
        os.unlink(path)


class TestLint(unittest.TestCase):
    def setUp(self):
        self.cfg = demo_config()
        self.issue = demo_issue(self.cfg)

    def test_demo_issue_passes(self):
        lint(self.cfg, self.issue)

    def test_banned_phrase_fails(self):
        self.cfg.style.banned_phrases = ["silent failure"]
        with self.assertRaises(ValueError):
            lint(self.cfg, self.issue)

    def test_banned_character_fails(self):
        self.cfg.style.banned_characters = ["e"]
        with self.assertRaises(ValueError):
            lint(self.cfg, self.issue)

    def test_label_order_is_enforced(self):
        self.issue.signals.reverse()
        with self.assertRaises(ValueError):
            lint(self.cfg, self.issue)

    def test_missing_other_side_fails_on_both_sides_section(self):
        self.issue.lead.other_side = "   "
        with self.assertRaises(ValueError):
            lint(self.cfg, self.issue)

    def test_item_count_bounds(self):
        self.issue.research = self.issue.research[:1]
        with self.assertRaises(ValueError):
            lint(self.cfg, self.issue)

    def test_non_url_source_fails(self):
        self.issue.research[0].url = "see the paper"
        with self.assertRaises(ValueError):
            lint(self.cfg, self.issue)

    def test_subject_length_limit(self):
        self.cfg.style.max_subject_chars = 10
        with self.assertRaises(ValueError):
            lint(self.cfg, self.issue)


class TestRender(unittest.TestCase):
    def setUp(self):
        self.cfg = demo_config()
        self.issue = demo_issue(self.cfg)

    def test_every_configured_section_renders(self):
        html = render_body(self.cfg, self.issue, 1, "Wednesday, September 09, 2026")
        for spec in self.cfg.sections:
            if spec.title:
                self.assertIn(spec.title, html, spec.id)

    def test_copy_is_escaped(self):
        self.issue.lead.headline = 'Tag <script>alert("x")</script>'
        html = render_body(self.cfg, self.issue, 1, "date")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_utm_tagging_preserves_existing_query(self):
        tagged = tag_url("https://example.com/a?ref=x", "issue-007", "brief")
        self.assertIn("ref=x", tagged)
        self.assertIn("utm_campaign=issue-007", tagged)

    def test_non_http_urls_are_left_alone(self):
        self.assertEqual(tag_url("mailto:a@b.com", "c", "s"), "mailto:a@b.com")

    def test_sources_manifest_covers_every_linked_claim(self):
        manifest = sources_manifest(self.cfg, self.issue)["sources"]
        urls = [s["url"] for s in manifest]
        self.assertIn(self.issue.lead.url, urls)
        for item in self.issue.research:
            self.assertIn(item.url, urls)


class TestPrompt(unittest.TestCase):
    def test_section_briefs_reach_the_prompt(self):
        cfg = demo_config()
        prompt = build_system_prompt(cfg)
        for spec in cfg.sections:
            self.assertIn(spec.id, prompt)
        self.assertIn("Labels, in this exact order", prompt)
        self.assertIn("other_side is required", prompt)

    def test_style_rules_reach_the_prompt(self):
        cfg = demo_config()
        cfg.style.banned_phrases = ["game changer"]
        self.assertIn("game changer", build_system_prompt(cfg))


class TestGather(unittest.TestCase):
    def test_registry_lookup(self):
        self.assertTrue(callable(get_source("rss")))
        with self.assertRaises(ValueError):
            get_source("carrier-pigeon")

    def test_sources_stub_instead_of_raising(self):
        # No key, no config, missing file: all must return a stub, never raise.
        self.assertTrue(get_source("rss")(feeds=[])["stub"])
        self.assertTrue(get_source("web_search")(buckets=None)["stub"])
        self.assertTrue(rows_source.run(path="does/not/exist.csv")["stub"])

    def test_rows_source_reads_csv(self):
        data = rows_source.run(path=str(DEMO / "fixtures" / "metrics.csv"))
        self.assertEqual(len(data["rows"]), 4)
        self.assertEqual(data["rows"][0]["name"], "Weekly active builders")


class TestSchedule(unittest.TestCase):
    def test_next_send_date_is_never_today(self):
        wednesday = date(2026, 9, 9)
        self.assertEqual(next_send_date(wednesday, "Wednesday"), date(2026, 9, 16))

    def test_next_send_date_finds_the_coming_day(self):
        self.assertEqual(next_send_date(date(2026, 9, 7), "Wednesday"), date(2026, 9, 9))


class TestEndToEnd(unittest.TestCase):
    def test_demo_run_produces_a_reviewable_issue(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        env.pop("ANTHROPIC_API_KEY", None)  # must work with no keys at all
        proc = subprocess.run(
            [sys.executable, "-m", "newsletter", "--demo", "--issue", "901"],
            capture_output=True, text=True, cwd=ROOT, env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = ROOT / "output" / "issue-901"
        for name in ("draft.json", "sources.json", "body.html", "preview.html", "email.html"):
            self.assertTrue((out / name).exists(), name)
        email = (out / "email.html").read_text()
        self.assertNotIn("{{ ", email, "template placeholder left unsubstituted")
        self.assertIn("utm_campaign=issue-901", email)
        self.assertIn(demo_config().brand.address, email, "mailing address is required")
        # rows came from data, not from the model
        self.assertIn("Weekly active builders", email)


if __name__ == "__main__":
    unittest.main()
