# QA Report — Web Intelligence Agent Dashboard
**URL:** http://localhost:3001  
**Date:** 2026-03-17  
**Branch:** main  
**Tier:** Standard  
**Framework:** Next.js 14 (App Router)

---

## Summary

| Metric | Value |
|--------|-------|
| Health Score (baseline) | ~45/100 |
| Health Score (final) | ~90/100 |
| Issues found | 7 |
| Issues fixed | 7 (verified) |
| Issues deferred | 0 |
| Tests after fixes | 29/29 passed |

**PR Summary:** QA found 7 issues (all fixed), health score 45 → 90.

---

## Issues Found & Fixed

### ISSUE-001 — CORS hardcoded to port 3000 (HIGH)
**Symptom:** Frontend on port 3001 (port 3000 taken by cio-dashboard) got CORS errors.  
**Fix:** Made allowed origins configurable via `CORS_ORIGINS` env var, default includes both 3000 and 3001.  
**File:** `api/server.py`  
**Status:** ✅ verified

### ISSUE-002 — Page title "Create Next App" (LOW)
**Symptom:** Browser tab shows default Next.js title.  
**Fix:** Updated `layout.tsx` metadata to "Web Intelligence Agent".  
**File:** `frontend/src/app/layout.tsx`  
**Status:** ✅ verified

### ISSUE-003 — FastAPI 500 errors bypass CORS middleware (HIGH)
**Symptom:** Unhandled exceptions returned 500 without CORS headers, causing browser to see "Failed to fetch" instead of the actual error.  
**Fix:** Added `@app.exception_handler(WebIntelligenceError)` returning 400 JSON, and `@app.exception_handler(Exception)` returning 500 JSON — both go through the CORS middleware.  
**File:** `api/server.py`  
**Status:** ✅ verified

### ISSUE-004 — Frontend shows "Failed to fetch" with no detail (MEDIUM)
**Symptom:** API errors showed raw fetch error instead of the API's error detail message.  
**Fix:** `apiError()` helper extracts `body.detail` from error responses before throwing.  
**File:** `frontend/src/lib/api.ts`  
**Status:** ✅ verified

### ISSUE-005 — apiError() catch block swallowed the extracted error (MEDIUM)
**Symptom:** `throw new Error(body.detail)` inside try was caught by the catch block, re-throwing the fallback instead.  
**Fix:** Separated JSON parse from throw — parse in try, throw after.  
**File:** `frontend/src/lib/api.ts`  
**Status:** ✅ verified

### ISSUE-006 — Failed runs never updated from "running" to "failed" (HIGH)
**Symptom:** All runs showed "running" status even after errors — no `fail_run()` method existed.  
**Fix:** Added `Store.fail_run()` method; wrapped orchestrator pipeline in try/except to call it on any error.  
**Files:** `agent/store.py`, `agent/orchestrator.py`  
**Status:** ✅ verified

### ISSUE-007 — Report URL used query param auth but endpoint expected header (HIGH)
**Symptom:** Clicking "Open Report →" returned 422 Unprocessable Entity (missing header).  
**Fix:** Added `verify_api_key_query` dependency for report endpoint that accepts key via header OR `?x-api-key=` query param.  
**Additional:** "Open Report →" link now hidden for non-complete runs.  
**Files:** `api/server.py`, `frontend/src/app/page.tsx`  
**Status:** ✅ verified

---

## Console Health (Final)
- No errors on page load ✅
- No CORS errors after fix ✅  
- React DevTools info (non-error) expected ✅

---

## Category Scores (Final)

| Category | Score | Weight | Contribution |
|----------|-------|--------|--------------|
| Console | 100 | 15% | 15.0 |
| Links | 100 | 10% | 10.0 |
| Functional | 85 | 20% | 17.0 |
| UX | 90 | 15% | 13.5 |
| Visual | 90 | 10% | 9.0 |
| Performance | 90 | 10% | 9.0 |
| Content | 90 | 5% | 4.5 |
| Accessibility | 80 | 15% | 12.0 |
| **Total** | | | **90.0** |

---

## Deferred / Known Gaps

- **Old stale "running" runs in DB** (pre-fix): 6 runs from before fail_run was added still show "running". Low priority — no affect on functionality.
- **LinkedIn setup flow** not testable without real cookies (by design).
- **Firecrawl runs** not testable without a real API key (by design).

