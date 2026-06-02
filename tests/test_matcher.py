"""Minimal, dependency-light tests for scoring. Run: python tests/test_matcher.py"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.matcher import score_job, _contains_any
from core.models import JobPosting


def job(title="", company="", description="", location="", remote_type=""):
    return JobPosting(title=title, company=company, url="https://example.com/x",
                      source="test", description=description, location=location,
                      remote_type=remote_type)


def test_word_boundary_no_false_positive():
    # "lead" must NOT match inside "leadership"
    assert _contains_any("a leadership role", ["lead"]) is False
    assert _contains_any("a lead role", ["lead"]) is True
    # "CPO" must not match inside another token
    assert _contains_any("incorporated cpotato", ["CPO"]) is False
    assert _contains_any("we need a cpo", ["CPO"]) is True


def test_strong_role_scores_high():
    cfg = {"roles": {"strong": ["Head of Product"], "good": [], "avoid": []}}
    assert score_job(job(title="Head of Product"), cfg) >= 30


def test_avoid_penalizes():
    cfg = {"roles": {"strong": [], "good": [], "avoid": ["Junior"]}}
    assert score_job(job(title="Junior Product Manager"), cfg) < 0


def test_feedback_suppresses_title_keyword():
    cfg = {
        "roles": {"strong": ["Engineer"], "good": [], "avoid": []},
        "feedback": {"suppress_title_keywords": ["sales"], "title_keyword_penalty": 20},
    }
    base = score_job(job(title="Sales Engineer"), cfg)
    cfg_no_fb = {"roles": cfg["roles"]}
    assert score_job(job(title="Sales Engineer"), cfg_no_fb) - base == 20


def test_feedback_suppresses_company():
    cfg = {
        "roles": {"strong": [], "good": [], "avoid": []},
        "feedback": {"suppress_companies": ["Crypto Capital"], "company_penalty": 30},
    }
    assert score_job(job(title="Product Lead", company="Crypto Capital Ltd"), cfg) == -30


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
