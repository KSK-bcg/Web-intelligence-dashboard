# agent/crawlers/linkedin.py
"""
LinkedIn Crawler — uses Playwright with injected session cookies.

IMPORTANT:
- Personal use only. Max 50 profiles/run (hard limit).
- Human-like delays (2.0-4.5s) between page loads.
- Exponential backoff on rate limits.
- CAPTCHA -> pause and notify user, never auto-solve.
"""
import asyncio
import logging
import random
import re
from typing import AsyncGenerator, Optional

from playwright.async_api import async_playwright, Page

from agent.base_agent import BaseAgent
from agent.crawlers.cookie_manager import load_cookies
from agent.exceptions import (
    LinkedInAuthExpiredError,
    LinkedInCaptchaError,
    LinkedInRateLimitError,
    ProfileNotFoundError,
    InsufficientDataError,
)

logger = logging.getLogger(__name__)

LINKEDIN_BASE = "https://www.linkedin.com"
MAX_PROFILES_HARD_LIMIT = 50


class LinkedInCrawler(BaseAgent):
    def __init__(self, max_profiles: int = 30, min_delay: float = 2.0, max_delay: float = 4.5):
        super().__init__(name="linkedin-crawler")
        if max_profiles > MAX_PROFILES_HARD_LIMIT:
            raise ValueError(f"max_profiles cannot exceed {MAX_PROFILES_HARD_LIMIT}")
        self.max_profiles = max_profiles
        self.min_delay = min_delay
        self.max_delay = max_delay

    async def run(self, company_name: str, department_filter: Optional[str] = None):
        cookies = load_cookies()
        if not cookies:
            raise LinkedInAuthExpiredError(
                "No LinkedIn session cookies found. Run: python run.py --setup-linkedin"
            )
        results = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context()
            await context.add_cookies(cookies)
            page = await context.new_page()
            try:
                async for person in self._crawl_company(page, company_name, department_filter):
                    results.append(person)
                    if len(results) >= self.max_profiles:
                        break
            finally:
                await browser.close()
        if len(results) < 3:
            raise InsufficientDataError(f"Only {len(results)} profiles found.")
        return results

    async def _crawl_company(
        self, page: Page, company_name: str, department_filter: Optional[str]
    ) -> AsyncGenerator:
        search_url = (
            f"{LINKEDIN_BASE}/search/results/people/"
            f"?keywords={company_name.replace(' ', '%20')}"
        )
        if department_filter:
            search_url += f"+{department_filter.replace(' ', '%20')}"
        await page.goto(search_url)
        await self._check_auth(page)
        await self._random_delay()

        profile_links = await page.query_selector_all('a[href*="/in/"]')
        seen_ids = set()

        for link in profile_links:
            href = await link.get_attribute("href")
            if not href:
                continue
            match = re.search(r'/in/([^/?]+)', href)
            if not match:
                continue
            linkedin_id = match.group(1)
            if linkedin_id in seen_ids:
                continue
            seen_ids.add(linkedin_id)
            try:
                person = await self._call_with_retry(
                    self._visit_profile, page=page, linkedin_id=linkedin_id
                )
                if person:
                    yield person
            except ProfileNotFoundError:
                logger.warning("Profile not found: %s — skipping", linkedin_id)
            except LinkedInCaptchaError:
                screenshot = f"output/captcha_{linkedin_id}.png"
                await page.screenshot(path=screenshot)
                raise LinkedInCaptchaError(
                    f"CAPTCHA triggered. Screenshot: {screenshot}. Solve manually and re-run."
                )
            await self._random_delay()

    async def _visit_profile(self, page: Page, linkedin_id: str):
        url = f"{LINKEDIN_BASE}/in/{linkedin_id}"
        await page.goto(url)
        await self._check_auth(page)
        await self._check_rate_limit(page)

        if "captcha" in page.url.lower() or "checkpoint" in page.url.lower():
            raise LinkedInCaptchaError("CAPTCHA checkpoint detected")
        if page.url == f"{LINKEDIN_BASE}/404":
            raise ProfileNotFoundError(f"Profile not found: {linkedin_id}")

        return await self._extract_profile_data(page)

    async def _extract_profile_data(self, page: Page):
        name = await self._safe_text(page, "h1.text-heading-xlarge")
        title = await self._safe_text(page, "div.text-body-medium.break-words")
        about = await self._safe_text(page, "div.pv-shared-text-with-see-more")
        match = re.search(r'/in/([^/?]+)', page.url)
        linkedin_id = match.group(1) if match else "unknown"
        return {
            "linkedin_id": linkedin_id,
            "name": name or "Unknown",
            "title": title or "Unknown",
            "department": None,
            "about": about or "",
            "source": "linkedin",
            "source_url": page.url,
        }

    async def _check_auth(self, page: Page) -> None:
        if "linkedin.com/login" in page.url or "linkedin.com/uas/login" in page.url:
            raise LinkedInAuthExpiredError(
                "Redirected to LinkedIn login. Run: python run.py --setup-linkedin"
            )

    async def _check_rate_limit(self, page: Page) -> None:
        status = await page.evaluate("() => window._lastResponseStatus || 200")
        if status == 429:
            raise LinkedInRateLimitError("LinkedIn returned 429 — rate limited")

    async def _safe_text(self, page: Page, selector: str):
        el = await page.query_selector(selector)
        if not el:
            return None
        return (await el.inner_text()).strip()

    async def _random_delay(self) -> None:
        delay = random.uniform(self.min_delay, self.max_delay)
        await asyncio.sleep(delay)
