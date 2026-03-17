import pytest
from agent.normalizer import Normalizer

@pytest.fixture
def normalizer():
    return Normalizer()

def test_dedup_by_linkedin_id(normalizer):
    raw = [
        {"linkedin_id": "jsmith", "name": "Jane Smith", "title": "VP IT", "source": "linkedin"},
        {"linkedin_id": "jsmith", "name": "Jane Smith", "title": "VP IT", "source": "linkedin"},
    ]
    result = normalizer.normalize(raw)
    assert len(result) == 1

def test_dedup_by_name_similarity(normalizer):
    raw = [
        {"linkedin_id": None, "name": "Jon Smith", "title": "VP IT", "source": "linkedin"},
        {"linkedin_id": None, "name": "John Smith", "title": "VP IT", "source": "linkedin"},
    ]
    result = normalizer.normalize(raw)
    assert len(result) == 1

def test_confidence_high_with_linkedin_id(normalizer):
    raw = [{"linkedin_id": "jsmith", "name": "Jane Smith", "title": "VP IT", "source": "linkedin"}]
    result = normalizer.normalize(raw)
    assert result[0]["confidence"] == "high"

def test_confidence_low_without_linkedin_id(normalizer):
    raw = [{"linkedin_id": None, "name": "Jane Smith", "title": "VP IT", "source": "inferred"}]
    result = normalizer.normalize(raw)
    assert result[0]["confidence"] == "low"

def test_department_inferred_from_title(normalizer):
    raw = [{"linkedin_id": "jsmith", "name": "Jane", "title": "VP of Cloud Infrastructure", "source": "linkedin"}]
    result = normalizer.normalize(raw)
    assert result[0]["department"] in ("Cloud", "Infrastructure", "IT")

def test_empty_input_returns_empty(normalizer):
    assert normalizer.normalize([]) == []
