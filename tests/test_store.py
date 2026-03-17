import pytest
import tempfile
import os
from datetime import datetime
from agent.store import Store, PersonRecord, RunRecord, ChangeEvent

@pytest.fixture
def tmp_store(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = Store(db_path=db_path)
    store.init_db()
    return store

def test_save_and_retrieve_run(tmp_store):
    run_id = tmp_store.create_run(goal="test goal", target="acme-corp")
    run = tmp_store.get_run(run_id)
    assert run.goal == "test goal"
    assert run.target == "acme-corp"

def test_save_person(tmp_store):
    run_id = tmp_store.create_run(goal="test", target="acme")
    tmp_store.save_person(run_id=run_id, person={
        "name": "Jane Smith",
        "title": "VP Engineering",
        "department": "IT",
        "linkedin_id": "jsmith123",
        "confidence": "high",
    })
    people = tmp_store.get_people(run_id=run_id)
    assert len(people) == 1
    assert people[0].name == "Jane Smith"

def test_change_detection_promotion(tmp_store):
    run1 = tmp_store.create_run(goal="test", target="acme")
    tmp_store.save_person(run_id=run1, person={
        "name": "Jane Smith", "title": "Director", "linkedin_id": "jsmith",
        "department": "IT", "confidence": "high"
    })
    tmp_store.complete_run(run1)

    run2 = tmp_store.create_run(goal="test", target="acme")
    tmp_store.save_person(run_id=run2, person={
        "name": "Jane Smith", "title": "VP", "linkedin_id": "jsmith",
        "department": "IT", "confidence": "high"
    })

    changes = tmp_store.diff_runs(prior_run_id=run1, current_run_id=run2)
    assert len(changes) == 1
    assert changes[0].change_type == "promotion"
    assert changes[0].person_name == "Jane Smith"
    assert changes[0].from_value == "Director"
    assert changes[0].to_value == "VP"

def test_change_detection_new_hire(tmp_store):
    run1 = tmp_store.create_run(goal="test", target="acme")
    tmp_store.complete_run(run1)

    run2 = tmp_store.create_run(goal="test", target="acme")
    tmp_store.save_person(run_id=run2, person={
        "name": "Alex Chen", "title": "Head of Cloud", "linkedin_id": "achen",
        "department": "Cloud", "confidence": "high"
    })

    changes = tmp_store.diff_runs(prior_run_id=run1, current_run_id=run2)
    assert len(changes) == 1
    assert changes[0].change_type == "new_hire"

def test_list_runs(tmp_store):
    tmp_store.create_run(goal="goal 1", target="acme")
    tmp_store.create_run(goal="goal 2", target="bigcorp")
    runs = tmp_store.list_runs()
    assert len(runs) == 2
