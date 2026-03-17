import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from agent.base_agent import BaseAgent
from agent.exceptions import (
    LinkedInRateLimitError, AgentResponseParseError, FirecrawlAuthError
)

class ConcreteAgent(BaseAgent):
    async def run(self, **kwargs):
        return await self._call_with_retry(self._mock_op, **kwargs)
    async def _mock_op(self, **kwargs):
        return {"ok": True}

def test_base_agent_instantiates():
    agent = ConcreteAgent(name="test")
    assert agent.name == "test"

@pytest.mark.asyncio
async def test_retry_on_rate_limit():
    agent = ConcreteAgent(name="test")
    call_count = 0
    async def flaky_op(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise LinkedInRateLimitError("rate limited")
        return {"ok": True}
    agent._mock_op = flaky_op
    result = await agent._call_with_retry(flaky_op, max_retries=3, base_delay=0.01)
    assert result == {"ok": True}
    assert call_count == 3

@pytest.mark.asyncio
async def test_raises_after_max_retries():
    agent = ConcreteAgent(name="test")
    async def always_fails(**kwargs):
        raise LinkedInRateLimitError("rate limited")
    with pytest.raises(LinkedInRateLimitError):
        await agent._call_with_retry(always_fails, max_retries=2, base_delay=0.01)
