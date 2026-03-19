"""
WebResearchAgent — autonomous Claude agent with native web_search tool + Firecrawl enrichment.

Research pipeline (two stages):
  Stage 1 — Claude agentic loop (web_search_20250305):
    - Receives a research topic + MECE questions to answer
    - Autonomously decides what to search
    - Runs up to _MAX_TOOL_ROUNDS cycles: search → read → follow-up → synthesize
    - Returns structured findings with cited source URLs

  Stage 2 — Firecrawl deep scrape (optional, default ON):
    - Collects unique URLs from Stage 1 findings
    - Scrapes each URL via Firecrawl for full markdown content (not just snippets)
    - Appends scraped content to finding evidence for richer analysis

Combined output feeds directly into SynthesisAgent alongside filings/earnings data.

Output per question:
  {
    "question":  "What is Roche's IT budget as % of revenue?",
    "answer":    "Roche does not publicly disclose IT spend...",
    "evidence":  ["Roche 2024 Annual Report states total OpEx...", ...],
    "sources":   ["https://roche.com/...", ...],
    "confidence": "high" | "medium" | "low",
    "source":    "web_research",
    "scraped_content": {"https://roche.com/...": "<markdown>..."},  # Firecrawl output
  }
"""
import asyncio
import json
import logging
import os
import re
import re as _re
from typing import Any, Dict, List, Optional

import anthropic
import httpx

try:
    import fitz
    _FITZ_AVAILABLE = True
except ImportError:
    _FITZ_AVAILABLE = False

from agent.base_agent import BaseAgent
from agent.exceptions import WebIntelligenceError

logger = logging.getLogger(__name__)

_MAX_TOOL_ROUNDS = 8    # max search → respond cycles
_MAX_SEARCHES = 20      # absolute cap on web_search calls per run
_MAX_FIRECRAWL_URLS = 8  # max URLs to deep-scrape per run (Firecrawl credit limit)

_SYSTEM_PROMPT = """You are a senior research analyst at a top-tier strategy consulting firm.
Your job is to answer specific research questions by searching the internet thoroughly.

Rules:
1. For each question, search multiple angles — don't rely on one result.
2. Prefer primary sources: company websites, SEC filings, press releases, earnings transcripts.
3. Distinguish between confirmed facts and analyst estimates — always note the source.
4. If you cannot find a reliable answer, say so clearly rather than guessing.
5. Be specific: include numbers, dates, and names where available.
6. After gathering evidence, produce a structured answer with citations."""

_RESEARCH_PROMPT = """You are researching: {topic}

Answer the following questions using web search. Be thorough — search multiple times per
question if needed to find high-quality, sourced answers.

Questions to answer:
{questions}

For each question, return your final answer in this JSON array:
[
  {{
    "question": "<exact question text>",
    "answer": "<detailed answer with specific facts, numbers, dates>",
    "evidence": ["<key fact 1 with source>", "<key fact 2 with source>"],
    "sources": ["<url1>", "<url2>"],
    "confidence": "<high|medium|low>"
  }}
]

Search thoroughly before answering. Do not guess. If information is unavailable, state that clearly."""


def _is_pdf_url(url: str) -> bool:
    """Return True if the URL appears to point to a PDF document."""
    return bool(_re.search(r'\.pdf(\?|$)', url, _re.IGNORECASE) or '/pdf/' in url.lower())


async def _jina_fetch(url: str) -> Optional[str]:
    """Fetch a URL via Jina AI Reader for richer extraction."""
    try:
        jina_url = f"https://r.jina.ai/{url}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                jina_url,
                headers={"Accept": "text/plain", "X-No-Cache": "true"},
                follow_redirects=True,
            )
        if resp.status_code == 200 and resp.text:
            return resp.text[:8000]
    except Exception as e:
        logger.debug("Jina fallback failed for %s: %s", url, e)
    return None


class WebResearchAgent(BaseAgent):
    """
    Autonomous Claude agent with web_search_20250305 tool + Firecrawl URL enrichment.

    Stage 1: Claude's agentic search loop finds answers and cites URLs.
    Stage 2: Firecrawl deep-scrapes those URLs for full page content.
    Combined output provides both structured answers and rich primary source text.
    """

    def __init__(self, max_searches: int = _MAX_SEARCHES, use_firecrawl: bool = True):
        super().__init__(name="web-research-agent")
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        self.max_searches = max_searches
        self.use_firecrawl = use_firecrawl
        self._tool_def = {
            "type": "web_search_20250305",
            "name": "web_search",
        }
        self._firecrawl_client = None  # lazy init

    def _get_firecrawl(self):
        """Lazy-initialize Firecrawl client. Returns None if unavailable."""
        if self._firecrawl_client is not None:
            return self._firecrawl_client
        api_key = os.environ.get("FIRECRAWL_API_KEY")
        if not api_key:
            logger.warning("WebResearchAgent: FIRECRAWL_API_KEY not set — Firecrawl enrichment disabled")
            return None
        try:
            import firecrawl
            self._firecrawl_client = firecrawl.FirecrawlApp(api_key=api_key)
            return self._firecrawl_client
        except ImportError:
            logger.warning("WebResearchAgent: firecrawl package not installed — Firecrawl enrichment disabled")
            return None

    def _scrape_pdf(self, url: str) -> Optional[str]:
        """Download and extract text from a PDF URL using pymupdf."""
        try:
            import httpx as _httpx
            resp = _httpx.get(url, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            doc = fitz.open(stream=resp.content, filetype="pdf")
            pages = []
            for page in doc[:20]:  # first 20 pages max
                pages.append(page.get_text())
            doc.close()
            return "\n".join(pages)[:8000]
        except Exception as e:
            logger.debug("WebResearchAgent: PDF scrape failed for %s: %s", url, e)
            return None

    async def run(
        self,
        topic: str,
        questions: List[str],
        max_searches: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Research a topic by answering each question with web search + Firecrawl enrichment.

        Args:
            topic:        High-level research topic (e.g. "Roche IT division and financials").
            questions:    Specific MECE questions to answer.
            max_searches: Override default search cap.

        Returns:
            List of finding dicts, one per question. See module docstring for schema.
        """
        # Stage 1: Claude agentic research loop
        findings = await self._research_loop(topic, questions, max_searches)

        # Stage 2: Firecrawl deep scrape of cited URLs
        if self.use_firecrawl:
            findings = await self._enrich_with_firecrawl(findings)

        return findings

    async def _research_loop(
        self,
        topic: str,
        questions: List[str],
        max_searches: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Stage 1: Claude agentic loop using web_search_20250305."""
        # Sanitize topic to prevent prompt injection
        topic = topic[:300].replace("{", "(").replace("}", ")")

        cap = max_searches or self.max_searches
        questions_text = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
        user_message = _RESEARCH_PROMPT.format(topic=topic, questions=questions_text)

        messages: List[Dict[str, Any]] = [{"role": "user", "content": user_message}]
        search_count = 0
        final_text = ""

        for round_num in range(_MAX_TOOL_ROUNDS):
            try:
                response = self.client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=4096,
                    system=_SYSTEM_PROMPT,
                    tools=[self._tool_def],
                    messages=messages,
                )
            except Exception as e:
                logger.error("WebResearchAgent: API call failed (round %d): %s", round_num, e)
                raise WebIntelligenceError(f"Web research API call failed: {e}") from e

            assistant_content = []
            tool_calls = []
            for block in response.content:
                assistant_content.append(block)
                if block.type == "tool_use" and block.name == "web_search":
                    tool_calls.append(block)
                elif block.type == "text":
                    final_text = block.text

            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason == "end_turn" or not tool_calls:
                logger.info(
                    "WebResearchAgent: done after %d rounds, %d searches",
                    round_num + 1, search_count,
                )
                break

            if search_count + len(tool_calls) > cap:
                logger.warning("WebResearchAgent: search cap (%d) reached", cap)
                messages.append({
                    "role": "user",
                    "content": "You have reached the search limit. Please compile your findings now and return the JSON array.",
                })
                try:
                    final_response = self.client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=2048,
                        system=_SYSTEM_PROMPT,
                        messages=messages,
                    )
                    for block in final_response.content:
                        if hasattr(block, "text"):
                            final_text = block.text
                except Exception:
                    pass
                break

            tool_results = []
            for tc in tool_calls:
                search_count += 1
                logger.debug(
                    "WebResearchAgent: search #%d — query: %s",
                    search_count, tc.input.get("query", "")[:100],
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": "",
                })

            messages.append({"role": "user", "content": tool_results})

        return self._parse_findings(final_text, questions)

    async def _enrich_with_firecrawl(
        self, findings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Stage 2: Deep-scrape cited URLs via Firecrawl for full page content.

        Collects unique URLs across all findings, scrapes up to _MAX_FIRECRAWL_URLS,
        and appends scraped markdown to each finding's evidence list.
        """
        fc = self._get_firecrawl()
        if fc is None:
            return findings

        # Collect unique URLs across all findings (preserve citation order)
        seen = set()
        all_urls: List[str] = []
        for f in findings:
            for url in f.get("sources", []):
                if url and url.startswith("http") and url not in seen:
                    seen.add(url)
                    all_urls.append(url)

        if not all_urls:
            logger.debug("WebResearchAgent: no URLs to Firecrawl-enrich")
            return findings

        urls_to_scrape = all_urls[:_MAX_FIRECRAWL_URLS]
        logger.info(
            "WebResearchAgent: Firecrawl enriching %d/%d URLs",
            len(urls_to_scrape), len(all_urls),
        )

        # Scrape each URL in parallel (asyncio + run_in_executor for sync Firecrawl client)
        loop = asyncio.get_event_loop()
        scraped: Dict[str, str] = {}  # url → markdown

        async def scrape_one(url: str) -> None:
            # PDF: use pymupdf directly
            if _FITZ_AVAILABLE and _is_pdf_url(url):
                text = await loop.run_in_executor(None, lambda: self._scrape_pdf(url))
                if text:
                    scraped[url] = text
                    return

            # HTML: use Firecrawl
            try:
                result = await loop.run_in_executor(None, lambda: fc.scrape(url))
                content = None
                if hasattr(result, "markdown") and result.markdown:
                    content = result.markdown[:8000]
                elif isinstance(result, dict) and result.get("markdown"):
                    content = result["markdown"][:8000]

                if content:
                    scraped[url] = content
                    return

                # Jina fallback for empty Firecrawl result
                logger.debug("WebResearchAgent: Firecrawl returned empty for %s, trying Jina fallback", url)
                jina_content = await _jina_fetch(url)
                if jina_content:
                    scraped[url] = jina_content
            except Exception as e:
                logger.debug("WebResearchAgent: Firecrawl scrape failed for %s: %s", url, e)
                # Try Jina as fallback on Firecrawl error too
                try:
                    jina_content = await _jina_fetch(url)
                    if jina_content:
                        scraped[url] = jina_content
                except Exception:
                    pass

        await asyncio.gather(*[scrape_one(u) for u in urls_to_scrape])
        logger.info("WebResearchAgent: Firecrawl scraped %d/%d URLs", len(scraped), len(urls_to_scrape))

        # Append scraped content to relevant findings
        for f in findings:
            f_scraped: Dict[str, str] = {}
            for url in f.get("sources", []):
                if url in scraped:
                    f_scraped[url] = scraped[url]
                    # Prepend a short excerpt to evidence so SynthesisAgent sees it
                    excerpt = scraped[url][:500].replace("\n", " ")
                    f.setdefault("evidence", []).append(
                        f"[Full page scraped via Firecrawl — {url}]: {excerpt}…"
                    )
            if f_scraped:
                f["scraped_content"] = f_scraped

        return findings

    def _parse_findings(self, text: str, questions: List[str]) -> List[Dict[str, Any]]:
        """Extract structured findings from Claude's final response."""
        json_match = re.search(r"\[[\s\S]*\]", text)
        if json_match:
            try:
                raw = json.loads(json_match.group())
                findings = []
                for item in raw:
                    findings.append({
                        "question": item.get("question", ""),
                        "answer": item.get("answer", ""),
                        "evidence": item.get("evidence") or [],
                        "sources": item.get("sources") or [],
                        "confidence": item.get("confidence", "medium"),
                        "source": "web_research",
                    })
                if findings:
                    return findings
            except json.JSONDecodeError:
                pass

        logger.warning(
            "WebResearchAgent: could not parse JSON findings — returning raw text as single finding"
        )
        return [{
            "question": "; ".join(questions),
            "answer": text.strip() or "No findings returned.",
            "evidence": [],
            "sources": [],
            "confidence": "low",
            "source": "web_research",
        }]
