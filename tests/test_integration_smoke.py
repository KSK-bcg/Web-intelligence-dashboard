# tests/test_integration_smoke.py
"""
Integration smoke test — validates the full stack can be imported
and the store + normalizer produce valid output together.
Does NOT make external API calls.
"""
import pytest
import tempfile
from agent.store import Store
from agent.normalizer import Normalizer
from agent.analyzers.viz import VizAgent


def test_store_normalizer_viz_pipeline():
    """Full pipeline with local-only components — no external calls."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(db_path=f"{tmpdir}/smoke.db")
        store.init_db()

        run_id = store.create_run(goal="smoke test", target="test-corp")

        raw = [
            {"linkedin_id": "cio1", "name": "Alice Smith", "title": "CIO",
             "source": "linkedin", "about": ""},
            {"linkedin_id": "vp1", "name": "Bob Jones", "title": "VP Cloud",
             "source": "linkedin", "about": ""},
            {"linkedin_id": "dir1", "name": "Carol Lee", "title": "Director Security",
             "source": "linkedin", "about": ""},
        ]
        normalizer = Normalizer()
        people = normalizer.normalize(raw)
        assert len(people) == 3
        assert all(p["confidence"] == "high" for p in people)
        assert any(p["department"] == "Cloud" for p in people)

        for p in people:
            store.save_person(run_id=run_id, person={
                "linkedin_id": p["linkedin_id"],
                "name": p["name"],
                "title": p["title"],
                "department": p.get("department"),
                "confidence": p["confidence"],
            })

        store.complete_run(run_id)
        runs = store.list_runs()
        assert len(runs) == 1
        assert runs[0].status == "complete"

        sample_graph = {
            "nodes": [
                {"linkedin_id": p["linkedin_id"], "name": p["name"],
                 "title": p["title"], "department": p.get("department"),
                 "confidence": p["confidence"],
                 "reports_to": None if i == 0 else "cio1"}
                for i, p in enumerate(people)
            ],
            "edges": [("cio1", "vp1"), ("cio1", "dir1")],
        }
        viz = VizAgent()
        html = viz.render(
            graph=sample_graph,
            qual={
                "executive_summary": "Test team.",
                "key_themes": ["cloud", "security"],
                "technology_signals": ["AWS"],
                "people_insights": [],
            },
            stats={"total_people": 3, "departments": {"Cloud": 1}, "org_depth": 1},
            run_id=run_id,
        )
        assert "Alice Smith" in html
        assert "Bob Jones" in html
        assert "Carol Lee" in html
        assert "d3" in html.lower()
        assert run_id in html

        # Verify change detection works
        run2 = store.create_run(goal="smoke test 2", target="test-corp")
        store.save_person(run_id=run2, person={
            "linkedin_id": "cio1", "name": "Alice Smith",
            "title": "Chief Information Officer",  # title changed
            "department": "IT Leadership", "confidence": "high",
        })
        changes = store.diff_runs(prior_run_id=run_id, current_run_id=run2)
        assert any(c.change_type == "promotion" and c.person_name == "Alice Smith" for c in changes)
