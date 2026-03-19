import pytest
from unittest.mock import patch, MagicMock
from agent.clarifier import Clarifier


def _mock_response(text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def test_clarify_returns_questions():
    c = Clarifier()
    with patch.object(c.client.messages, "create", return_value=_mock_response(
        '{"questions": ["Which specific department?", "VP-level and above only?"], '
        '"refined_context": {"company": "Roche", "scope": "IT", "level": null, '
        '"time_horizon": null, "output_preference": null}}'
    )):
        result = c.clarify("Map Roche IT")
    assert len(result["questions"]) == 2
    assert "company" in result["refined_context"]


def test_clarify_returns_empty_when_goal_is_specific():
    c = Clarifier()
    with patch.object(c.client.messages, "create", return_value=_mock_response(
        '{"questions": [], "refined_context": {"company": "Roche", "scope": "IT", '
        '"level": "VP+", "time_horizon": null, "output_preference": null}}'
    )):
        result = c.clarify("Map the IT division of Roche on LinkedIn, VP level and above")
    assert result["questions"] == []


def test_build_refined_goal():
    c = Clarifier()
    goal = "Map Roche IT"
    answers = {"Which department?": "IT", "Level?": "VP and above"}
    with patch.object(c.client.messages, "create", return_value=_mock_response(
        "Map the IT division of Roche on LinkedIn, VP level and above, producing a board deck."
    )):
        refined = c.build_refined_goal(goal, answers)
    assert "Roche" in refined
    assert "VP" in refined


def test_clarify_handles_bad_json_gracefully():
    c = Clarifier()
    with patch.object(c.client.messages, "create", return_value=_mock_response("not json")):
        result = c.clarify("some goal")
    assert result["questions"] == []
    assert result["refined_context"] == {}


def test_build_refined_goal_no_answers_returns_original():
    c = Clarifier()
    original = "Map Roche IT"
    result = c.build_refined_goal(original, {})
    assert result == original
