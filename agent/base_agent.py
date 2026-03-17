import asyncio
import logging
import random
from abc import ABC, abstractmethod
from typing import Any, Callable, Awaitable, Optional

from agent.exceptions import LinkedInRateLimitError, FirecrawlRateLimitError

logger = logging.getLogger(__name__)

# Exceptions that trigger retry with backoff
RETRYABLE_ERRORS = (LinkedInRateLimitError, FirecrawlRateLimitError)


class BaseAgent(ABC):
    """
    Base class for all crawl and analysis agents.

    Provides:
    - Structured logging (agent name in every log line)
    - _call_with_retry: exponential backoff for retryable errors
    - Prompt injection guard: wrap_content()
    """

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"agent.{name}")

    @abstractmethod
    async def run(self, **kwargs) -> Any:
        """Execute the agent's primary task."""

    async def _call_with_retry(
        self,
        fn: Callable[..., Awaitable[Any]],
        *,
        max_retries: int = 5,
        base_delay: float = 1.0,
        **kwargs,
    ) -> Any:
        """
        Call fn(**kwargs) with exponential backoff on RETRYABLE_ERRORS.

        Backoff: base_delay * 2^attempt + jitter (0-1s)
        Raises the original exception after max_retries exhausted.
        """
        last_error: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                return await fn(**kwargs)
            except RETRYABLE_ERRORS as e:
                last_error = e
                if attempt == max_retries:
                    break
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                self.logger.warning(
                    "Retryable error on attempt %d/%d — sleeping %.1fs: %s",
                    attempt + 1, max_retries, delay, e,
                )
                await asyncio.sleep(delay)
        raise last_error

    @staticmethod
    def wrap_content(text: str, source: str = "untrusted") -> str:
        """
        SECURITY: Wrap scraped content to prevent prompt injection.
        All crawled text MUST go through this before Claude calls.
        """
        return f"<content source='{source}'>{text}</content>"
