import pytest
from agent.analyzers.pptx_agent import build_output_path


def test_build_output_path_basic():
    path = build_output_path("Roche", "IT Org Chart", "2026-03-19")
    assert path.endswith(".pptx")
    assert "roche" in path.lower()
    assert "it-org-chart" in path.lower()
    assert "2026-03-19" in path


def test_build_output_path_sanitizes_special_chars():
    path = build_output_path("J&J / Pharma", "R&D Overview", "2026-03-19")
    assert "/" not in path.split("/")[-1]  # filename only
    assert "&" not in path


def test_build_output_path_same_company_same_name():
    p1 = build_output_path("Roche", "IT Org", "2026-03-19")
    p2 = build_output_path("Roche", "IT Org", "2026-03-19")
    assert p1 == p2  # same inputs → same file (revision overwrites in-place)


def test_build_output_path_different_dates_differ():
    p1 = build_output_path("Roche", "IT Org", "2026-03-19")
    p2 = build_output_path("Roche", "IT Org", "2026-03-20")
    assert p1 != p2


def test_build_output_path_uses_output_dir():
    path = build_output_path("Roche", "IT", "2026-03-19", output_dir="output")
    assert path.startswith("output/")
