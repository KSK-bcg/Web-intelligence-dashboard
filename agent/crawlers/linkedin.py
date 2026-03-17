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
        # Normalize sameSite values from Cookie-Editor format to Playwright format
        _same_site_map = {"no_restriction": "None", "lax": "Lax", "strict": "Strict"}
        playwright_cookies = []
        for c in cookies:
            pc = {k: v for k, v in c.items() if k not in ("expirationDate", "hostOnly", "storeId", "session")}
            raw_ss = (pc.get("sameSite") or "").lower()
            pc["sameSite"] = _same_site_map.get(raw_ss, "None")
            if "expirationDate" in c:
                pc["expires"] = c["expirationDate"]
            playwright_cookies.append(pc)
        results = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context()
            await context.add_cookies(playwright_cookies)
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

        # Collect all hrefs as strings before any navigation (handles go stale on navigate)
        profile_links = await page.query_selector_all('a[href*="/in/"]')
        hrefs = []
        for link in profile_links:
            try:
                href = await link.get_attribute("href")
                if href:
                    hrefs.append(href)
            except Exception:
                continue
        seen_ids = set()

        for href in hrefs:
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
        # Try multiple selectors — LinkedIn's DOM changes frequently
        name = (
            await self._safe_text(page, "h1.text-heading-xlarge") or
            await self._safe_text(page, "h1[class*='heading']") or
            await self._safe_text(page, "h1") or
            await self._safe_text(page, ".pv-text-details__left-panel h1")
        )
        title = (
            await self._safe_text(page, "div.text-body-medium.break-words") or
            await self._safe_text(page, ".pv-text-details__left-panel .text-body-medium") or
            await self._safe_text(page, "[data-generated-suggestion-target] .text-body-medium")
        )
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
