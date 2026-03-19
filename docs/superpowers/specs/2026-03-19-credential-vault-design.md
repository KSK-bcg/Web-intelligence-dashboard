# Credential Vault — Design Spec

## Overview

When a research goal requires a login-protected site (LinkedIn, HIMSS, paywalled journals, etc.), the UI detects the required domains, checks the OS keyring for saved cookies, and — only if something is missing — shows an inline credential collection step between clarification and running. Saved credentials persist across sessions; users are never asked twice for the same site unless cookies expire or are cleared.

---

## User Flow

```
Goal input
    ↓
Clarification questions  (POST /clarify → includes required_auth_domains[])
    ↓
Auth gate  ← ONLY if any required domain has no saved cookies
    ↓
Re-verify auth status  ← GET /auth/status called again before run starts
    ↓
Running (parallel crawl, skipped domains excluded from fan-out)
    ↓
Done (deck opens)
```

When all required domains already have saved cookies, the auth gate is completely invisible and the flow goes directly from clarification to running.

---

## Backend

### 1. `agent/crawlers/cookie_manager.py` — generalize to per-domain

Currently stores one LinkedIn cookie set. Replace with per-domain keyed storage:

```python
SERVICE_NAME = "web-intelligence-agent"

def save_cookies(domain: str, cookies: list) -> None
def load_cookies(domain: str) -> list | None
def clear_cookies(domain: str) -> None
def list_saved_domains() -> list[str]
```

Keyring key: `f"cookies:{domain}"` (e.g. `cookies:linkedin.com`).

**Back-compat / one-time migration:** On `load_cookies("linkedin.com")`, if the new key `cookies:linkedin.com` is absent, check the legacy key `linkedin-session-cookies`. If found: re-save under the new key, then attempt to delete the legacy key. If deletion fails, log a warning and continue — the new key is now canonical and will be found first on all subsequent reads. Return the cookies regardless.

**Note on the legacy deletion test assertion:** Deletion is best-effort. The test must assert that (a) `load_cookies("linkedin.com")` returns the expected cookies and (b) the new key `cookies:linkedin.com` exists. The deletion of the legacy key is not asserted — it may or may not succeed depending on the keyring backend.

### 2. `agent/exceptions.py` — add `AuthExpiredError`

`AuthExpiredError` extends `WebIntelligenceError` (the existing base class in this file):

```python
class AuthExpiredError(WebIntelligenceError):
    """Raised when a crawler detects an expired or revoked session cookie."""
    def __init__(self, domain: str):
        super().__init__(f"Session expired for {domain} — re-connect and retry")
        self.domain = domain
```

**Catch point and HTTP response:** `AuthExpiredError` propagates up through `_crawl_one` → `_crawl` → `Orchestrator.run()`. The `except Exception` block in `Orchestrator.run()` calls `self.store.fail_run(run_id)` and re-raises. In `api/server.py`, the `POST /run` handler wraps `orchestrator.run()` in a try/except; if `AuthExpiredError` is caught, it logs the error and returns HTTP 400:

```json
{ "error": "auth_expired", "domain": "<domain>", "message": "Session expired for <domain> — re-connect and retry" }
```

All other exceptions from `orchestrator.run()` return HTTP 500.

### 3. `agent/orchestrator.py` — extract `_classify_goal` as a module-level function

Move the current `Orchestrator._classify_goal` method body into a module-level function:

```python
def classify_goal(goal: str, client: anthropic.Anthropic) -> dict:
    ...  # current method body verbatim
```

`Orchestrator._classify_goal` becomes a thin wrapper:

```python
def _classify_goal(self, goal: str) -> dict:
    return classify_goal(goal, self.client)
```

`classify_goal` is importable as `from agent.orchestrator import classify_goal`.

### 4. `agent/clarifier.py` — return `required_auth_domains`

Import and call `classify_goal` from `agent.orchestrator`:

```python
from agent.orchestrator import classify_goal
```

Call it using a throwaway Anthropic client created inside `clarify()`:

```python
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
plan = classify_goal(goal, client)
source_types = plan.get("source_types") or []
```

Extend `clarify()` return value to include domain list:

```python
{
  "questions": [...],
  "refined_context": {...},
  "required_auth_domains": ["linkedin.com", "app.himssconference.com"]
}
```

**Detection rules (evaluated in order):**

1. `source_types` contains `"linkedin"` → add `linkedin.com`
2. Explicit URL in the goal text → extract domain:
   - Parse with `urllib.parse.urlparse`; take the `netloc` (hostname)
   - **Keep subdomain** if the first label is in `{app, login, auth, members, portal, secure, my}`; otherwise strip to root domain using this rule: if the second-to-last label is in `{co, com, net, org, gov, edu, ac}` (compound TLD indicator), keep the last three labels (e.g. `careers.bbc.co.uk` → `bbc.co.uk`); otherwise keep the last two labels (e.g. `www.example.com` → `example.com`)
   - **Skip** if the resulting domain matches any entry in the public allowlist: `github.com`, `wikipedia.org`, `arxiv.org`, `pubmed.ncbi.nlm.nih.gov`, `sec.gov`, `bloomberg.com`, `reuters.com`, `ft.com`
3. If `source_types` is empty **or** contains only values from `{financial, market_intel}` (no `linkedin`, `blog`, or other) → return `required_auth_domains: []`

### 5. `api/server.py` — two new endpoints + run schema extension + re-verify

Both new endpoints require the `X-API-Key` header matching `API_SECRET_KEY` (same as all existing endpoints). Missing or wrong key → 401.

**Extend `RunRequest` Pydantic model** with two new optional fields:

```python
class RunRequest(BaseModel):
    goal: str
    run_id: Optional[str] = None
    required_auth_domains: list[str] = []   # domains the clarifier flagged
    skipped_domains: list[str] = []          # domains the user chose to skip
```

**`GET /auth/status`**

```
Header: X-API-Key: <secret>
Query param: domains=linkedin.com,himss.org   (comma-separated)
Response 200: { "results": { "linkedin.com": true, "himss.org": false } }
Response 400: { "error": "too_many_domains" }  ← if > 20 domains
```

Each domain value is validated against `^[a-z0-9.-]+\.[a-z]{2,}$` before checking the keyring. Domains that fail validation return `false` in the results map (never a 400).

**Keyring unavailable:** if the keyring backend raises an exception on any domain lookup, log a warning and return `false` for that domain (auth gate will appear, which is the safe default).

**`POST /auth/cookies`**

```json
{ "domain": "himss.org", "cookies_json": "[{...}]" }
```

Validation (return 400 with `{ "error": "<code>" }` on first failure encountered):

| Check | Error code |
|---|---|
| `domain` does not match `^[a-z0-9.-]+\.[a-z]{2,}$` or length > 100 | `"invalid_domain"` |
| `cookies_json` byte length > 100 000 | `"payload_too_large"` |
| `cookies_json` is not parseable as JSON | `"invalid_json"` |
| `cookies_json` parses as JSON but result is not a list | `"invalid_cookie_format"` |
| Any list item is not a dict | `"invalid_cookie_format"` |
| Any list item's `"domain"` key value, stripped of a leading dot, does not equal or end with a dot + posted `domain` (e.g. `.himss.org` passes for posted domain `himss.org`; `www.himss.org` does **not** pass — only exact match or `.{domain}` form is accepted) | `"domain_mismatch"` |

Returns `{ "saved": true }` on success.

**`POST /run` — updated response table:**

| Condition | Status | Body |
|---|---|---|
| Success | 200 | existing run result shape |
| Missing/wrong API key | 401 | `{ "error": "unauthorized" }` |
| Required domain has no cookies (pre-run re-verify) | 400 | `{ "error": "auth_required", "domains": [...] }` |
| Session cookie expired mid-run | 400 | `{ "error": "auth_expired", "domain": "...", "message": "..." }` |
| All other errors | 500 | `{ "error": "internal_error" }` |

**Re-verify before run:** Before calling `orchestrator.run()`, for each domain in `required_auth_domains` that is not in `skipped_domains`, call `cookie_manager.load_cookies(domain)`. If any returns `None`, return 400 `{ "error": "auth_required", "domains": [...] }`.

### 6. Source-type → domain mapping and `_crawl_one` signature change

`Orchestrator._crawl_one` gains a new parameter:

```python
async def _crawl_one(self, source_type: str, plan: dict, skipped_domains: list[str]) -> list:
```

`Orchestrator._crawl` passes `skipped_domains` through:

```python
tasks = [self._crawl_one(st, plan, skipped_domains) for st in source_types]
```

`Orchestrator.run()` receives `skipped_domains` from the plan dict (set by `api/server.py` before calling `orchestrator.run(goal, ...)`). The API handler stores `skipped_domains` in the plan/context passed to the orchestrator — concretely, `skipped_domains` is an extra parameter added to `Orchestrator.run(goal, run_id_hint, skipped_domains=[])`.

**Domain-to-source-type skip mapping** (checked at the top of `_crawl_one`):

| `source_type` | Skip if domain in `skipped_domains` |
|---|---|
| `"linkedin"` | `"linkedin.com"` in `skipped_domains` |
| `"blog"` or `"generic"` | hostname of `plan.get("url", "")` is in `skipped_domains` |
| `"financial"`, `"market_intel"`, `"synthesis"`, `"board_deck"` | never skipped (public data) |

When skipped: return `[]` immediately and log `"Skipping %s crawler — domain %s was skipped by user" % (source_type, domain)` where `domain` is the specific domain string from `skipped_domains` that triggered the skip.

### 7. `agent/crawlers/linkedin.py` — update to per-domain API

Replace the direct legacy keyring call with `cookie_manager.load_cookies("linkedin.com")`.

---

## Frontend

### New `"auth"` phase in `page.tsx`

Phase order: `"input"` → `"clarifying"` → `"auth"` → `"running"` → `"done"`

**Trigger:** After `clarifyGoal()` returns, if `required_auth_domains` is non-empty, call `GET /auth/status` for those domains. If the call fails (network error, timeout, non-200 response), treat all queried domains as `false` (auth gate appears — safe default). If all domains return `true`, skip `"auth"` phase and proceed directly to `"running"`.

**Re-verify before run:** When the user clicks `Run Research →`, call `GET /auth/status` again for all `required_auth_domains` that are not in the user's skipped set. If the call fails, treat as all `false`. If any domain returns `false`, show inline error on that domain's card: "Credentials lost — please re-paste." Prevent run from starting until all non-skipped domains are `true` or explicitly skipped.

**Auth gate UI:** One card per missing domain, stacked vertically:

```
⚿  Credentials needed to continue

┌─ linkedin.com ────────────────────────────────┐
│  1. Go to linkedin.com (while logged in)       │
│  2. Open Cookie-Editor → Export → Copy All    │
│  3. Paste JSON:                                │
│  [ textarea                                  ] │
│  [ ✓ Saved ] ← appears after successful save  │
└────────────────────────────────────────────────┘

[ Run Research → ]      [ Skip missing sites ]
```

**Card save state machine:**

| State | Meaning | Transition |
|---|---|---|
| `idle` | No action yet (or user edited textarea after a prior save/error) | → `saving` on blur with non-empty content |
| `saving` | `POST /auth/cookies` in flight | → `saved` on 200; → `error` on any failure |
| `saved` | Cookies accepted by backend | → `idle` if user focuses and edits the textarea again |
| `error` | Save failed (validation or network) | → `saving` on next blur with non-empty content |

- **Save trigger:** `POST /auth/cookies` fires on textarea **blur** only. If the textarea is empty on blur, no request is made and the state stays `idle`.
- If the user focuses a `saved` card's textarea and makes any change (keydown event), the card immediately reverts to `idle` and the blur trigger is re-armed.
- **Error state display text:**
  - `"invalid_json"` or `"invalid_cookie_format"`: "Invalid cookie JSON — re-export from Cookie-Editor"
  - `"domain_mismatch"`: "Cookie domain doesn't match {domain} — re-export from the correct site"
  - All other 400 errors: "Invalid cookies — re-export and try again"
  - Network/server error (non-400 failure or fetch exception): "Save failed — check your connection and try again"
- `Run Research →` is enabled once every card is in `saved` state or explicitly skipped
- `Skip missing sites` — sets all `idle` and `error` cards to skipped; includes their domain names in `skipped_domains` on the run request

### Updated `ClarifyResult` interface in `api.ts`

```typescript
interface ClarifyResult {
  questions: string[]
  refined_context: Record<string, unknown>
  required_auth_domains: string[]   // ← new field
}
```

### New `api.ts` functions

```typescript
getAuthStatus(domains: string[]): Promise<Record<string, boolean>>
saveCookies(domain: string, cookiesJson: string): Promise<void>
```

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Pasted JSON not parseable | Inline: "Invalid cookie JSON — re-export from Cookie-Editor" |
| Parsed but not a list | Inline: "Invalid cookie JSON — re-export from Cookie-Editor" |
| Cookie domain mismatch | Inline: "Cookie domain doesn't match {domain} — re-export from the correct site" |
| Network/server error on save | Inline: "Save failed — check your connection and try again" |
| `GET /auth/status` call fails | Treat all queried domains as `false`; auth gate appears |
| Keyring unavailable (backend) | `GET /auth/status` returns `false` per domain; auth gate appears |
| Session cookie expires mid-run | Crawler throws `AuthExpiredError`; `POST /run` returns 400 `auth_expired` |
| User skips a domain | `_crawl_one` returns `[]` for that source type (logged); partial results in synthesis |
| Re-verify fails before run | Frontend shows "Credentials lost — please re-paste" per domain, blocks run |
| `POST /run` re-verify finds missing cookies | 400 `{ "error": "auth_required", "domains": [...] }` |

---

## Files Changed

| File | Change |
|---|---|
| `agent/crawlers/cookie_manager.py` | Generalize to per-domain storage; one-time LinkedIn legacy key migration |
| `agent/exceptions.py` | Add `AuthExpiredError(domain)` extending `WebIntelligenceError` |
| `agent/orchestrator.py` | Extract `_classify_goal` into module-level `classify_goal(goal, client)`; add `skipped_domains` param to `run()` and `_crawl_one()` |
| `agent/clarifier.py` | Import `classify_goal`; add `required_auth_domains` detection with subdomain + compound TLD + allowlist rules |
| `agent/crawlers/linkedin.py` | Replace legacy keyring call with `cookie_manager.load_cookies("linkedin.com")` |
| `api/server.py` | Add `GET /auth/status`, `POST /auth/cookies`; extend `RunRequest` with `required_auth_domains` + `skipped_domains`; add pre-run re-verify; catch `AuthExpiredError` → 400 |
| `frontend/src/lib/api.ts` | Update `ClarifyResult` to include `required_auth_domains`; add `getAuthStatus`, `saveCookies` |
| `frontend/src/app/page.tsx` | Add `"auth"` phase, domain credential cards with state machine, re-verify on run, skip tracking |
| `tests/test_cookie_manager.py` | New — see test cases below |
| `tests/test_auth_api.py` | New — see test cases below |

### Test cases for `tests/test_cookie_manager.py`

1. `save_cookies("example.com", [{"name":"a"}])` then `load_cookies("example.com")` → returns `[{"name":"a"}]`
2. `load_cookies("neverused.com")` → returns `None`
3. `save_cookies("a.com", [{"x":1}])`, `save_cookies("b.com", [{"y":2}])` → `list_saved_domains()` contains both `"a.com"` and `"b.com"`
4. `save_cookies("a.com", [{"x":1}])`, `clear_cookies("a.com")` → `load_cookies("a.com")` returns `None`
5. Legacy migration: write `json.dumps([{"name":"sid"}])` to keyring key `linkedin-session-cookies`; call `load_cookies("linkedin.com")` → returns `[{"name":"sid"}]`; assert keyring key `cookies:linkedin.com` now exists with the same value

### Test cases for `tests/test_auth_api.py`

1. `GET /auth/status?domains=unknown.com` → 200 `{"results": {"unknown.com": false}}`
2. `POST /auth/cookies` with `domain="example.com"`, `cookies_json='[{"name":"sid","value":"x"}]'` → 200 `{"saved": true}`; then `GET /auth/status?domains=example.com` → 200 `{"results": {"example.com": true}}`
3. `POST /auth/cookies` with `cookies_json="not json"` → 400 `{"error": "invalid_json"}`
4. `POST /auth/cookies` with `cookies_json="{}"` (a JSON object, not a list) → 400 `{"error": "invalid_cookie_format"}`
5. `POST /auth/cookies` with `cookies_json` = `"[" + "x" * 100_001` (> 100 KB) → 400 `{"error": "payload_too_large"}`
6. `POST /auth/cookies` with `domain="himss.org"`, `cookies_json='[{"domain":"other.com"}]'` → 400 `{"error": "domain_mismatch"}`
7. `POST /auth/cookies` with `domain="himss.org"`, `cookies_json='[{"domain":"www.himss.org"}]'` → 400 `{"error": "domain_mismatch"}` (subdomain form not accepted; only `.himss.org` form passes)
8. `POST /auth/cookies` with `domain="himss.org"`, `cookies_json='[{"domain":".himss.org"}]'` → 200 `{"saved": true}` (leading-dot form is accepted)
9. `GET /auth/status?domains=linkedin.com` without `X-API-Key` header → 401
10. `POST /auth/cookies` without `X-API-Key` header → 401
11. `GET /auth/status?domains=` + 21 comma-separated valid domains → 400 `{"error": "too_many_domains"}`
12. `POST /auth/cookies` with `domain="not a domain"` → 400 `{"error": "invalid_domain"}`
13. `GET /auth/status?domains=BAD_DOMAIN!!` → 200 `{"results": {"BAD_DOMAIN!!": false}}` (invalid domain returns false, not 400)
