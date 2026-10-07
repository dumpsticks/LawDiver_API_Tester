"""Turn LawDiver JSON payloads into human-readable view models for the UI."""

from __future__ import annotations

from typing import Any, Optional


def _s(value: Any, default: str = "—") -> str:
    if value is None or value == "":
        return default
    return str(value)


def _good_law_label(gl: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not gl:
        return {"status": "unknown", "label": "Good-law status unknown", "tone": "muted"}
    status = (gl.get("status") or "unknown").lower()
    if gl.get("negative"):
        return {
            "status": status,
            "label": f"Negative treatment ({status})",
            "tone": "danger",
            "basis": gl.get("basis"),
            "count": gl.get("negativeTreatmentCount"),
        }
    if gl.get("unknown") or status in ("unknown", ""):
        return {
            "status": status or "unknown",
            "label": "Not yet evaluated (unknown)",
            "tone": "warn",
            "basis": gl.get("basis"),
        }
    return {
        "status": status,
        "label": f"Appears to be good law ({status})",
        "tone": "ok",
        "basis": gl.get("basis"),
    }


def _usage_block(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    usage = payload.get("usage")
    if not usage:
        return None
    parts = []
    if usage.get("operation"):
        parts.append(f"Operation: {usage['operation']}")
    if usage.get("quantity") is not None:
        parts.append(f"{usage['quantity']} unit(s)")
    if usage.get("costCents") is not None:
        parts.append(f"${usage['costCents']/100:.2f} reserved")
    return {
        "title": "Usage for this call",
        "lines": parts,
        "breakdown": usage.get("breakdown"),
        "replayed": bool(usage.get("replayed") or payload.get("replayed")),
    }


def _meta(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "requestId": payload.get("requestId"),
        "usage": _usage_block(payload),
    }


def format_discovery(payload: Any) -> dict[str, Any]:
    endpoints = []
    if isinstance(payload, dict):
        for item in payload.get("endpoints") or payload.get("routes") or []:
            if isinstance(item, dict):
                endpoints.append(
                    {
                        "method": item.get("method") or item.get("httpMethod") or "",
                        "path": item.get("path") or item.get("route") or "",
                        "summary": item.get("summary") or item.get("description") or "",
                    }
                )
            else:
                endpoints.append({"method": "", "path": str(item), "summary": ""})
        pricing = payload.get("pricing") or payload.get("yourPricing") or payload.get("prices")
        return {
            "kind": "discovery",
            "headline": "API discovery",
            "subtitle": "Public surface and pricing policy (no key required for this call).",
            "endpoints": endpoints,
            "pricing": pricing,
            "rawKeys": sorted(payload.keys()) if isinstance(payload, dict) else [],
            "meta": _meta(payload) if isinstance(payload, dict) else {},
            "summaryText": f"Discovery OK — {len(endpoints) or 'surface'} endpoint entries.",
        }
    return {
        "kind": "text",
        "headline": "API discovery",
        "body": str(payload),
        "meta": {},
        "summaryText": "Discovery OK.",
    }


def format_jurisdictions(payload: Any) -> dict[str, Any]:
    types = []
    states = []
    circuits = []
    examples = []
    if isinstance(payload, dict):
        for t in payload.get("types") or payload.get("jurisdictionTypes") or []:
            if isinstance(t, dict):
                types.append(
                    {
                        "type": t.get("type") or t.get("id") or "",
                        "label": t.get("label") or t.get("name") or t.get("description") or "",
                        "requires": t.get("requires") or t.get("extraFields") or [],
                    }
                )
            else:
                types.append({"type": str(t), "label": "", "requires": []})
        for s in payload.get("states") or []:
            if isinstance(s, dict):
                states.append({"code": s.get("code") or "", "name": s.get("name") or ""})
            else:
                states.append({"code": str(s), "name": ""})
        if not states and payload.get("stateCodes"):
            states = [{"code": c, "name": ""} for c in payload["stateCodes"]]
        for c in payload.get("circuits") or payload.get("circuitIds") or []:
            circuits.append(str(c) if not isinstance(c, dict) else (c.get("id") or c.get("circuit") or str(c)))
        examples = payload.get("examples") or []
    return {
        "kind": "jurisdictions",
        "headline": "Jurisdictions reference",
        "subtitle": "Use these codes when building a search.",
        "types": types,
        "states": states,
        "circuits": circuits,
        "examples": examples,
        "meta": _meta(payload) if isinstance(payload, dict) else {},
        "summaryText": f"{len(types)} jurisdiction types, {len(states)} states.",
    }


def format_search(payload: dict[str, Any]) -> dict[str, Any]:
    results = []
    for r in payload.get("results") or []:
        gl = _good_law_label(r.get("goodLaw"))
        card = r.get("caseCard") or {}
        opinion = r.get("opinion") or {}
        results.append(
            {
                "caseId": r.get("caseId"),
                "caseName": r.get("caseName") or "Untitled case",
                "citation": r.get("bluebookCitation") or r.get("citation") or "(no citation)",
                "parallels": r.get("parallelCitations") or [],
                "court": r.get("courtAbbreviation") or r.get("court") or "",
                "dateFiled": r.get("dateFiled") or (str(r.get("year")) if r.get("year") else ""),
                "published": r.get("published"),
                "citedByCount": r.get("citedByCount"),
                "snippet": r.get("snippet"),
                "opinionType": r.get("opinionType"),
                "goodLaw": gl,
                "summaryAi": card.get("summaryAi"),
                "holdings": card.get("holdings") or [],
                "issues": card.get("issuesPresented") or [],
                "opinionText": opinion.get("text") or opinion.get("excerpts") or opinion.get("body"),
            }
        )
    total = payload.get("total")
    available = payload.get("totalAvailable")
    headline = "Case search results"
    if total is not None:
        headline = f"Found {total} case" + ("s" if total != 1 else "")
        if available is not None:
            headline += f" (about {available} available)"
    return {
        "kind": "search",
        "headline": headline,
        "subtitle": (payload.get("searchInfo") or {}).get("routedAs")
        or (payload.get("suggestion") or ""),
        "results": results,
        "meta": _meta(payload),
        "summaryText": f"Search returned {len(results)} case(s).",
    }


_VERDICT_COPY = {
    "valid": ("Valid citation", "ok", "Resolves cleanly; Bluebook form is available."),
    "name_mismatch": (
        "Name mismatch",
        "danger",
        "Real reporter cite, but the caption/year/court as written does not match.",
    ),
    "page_mismatch": ("Page mismatch", "warn", "Looks like a pin/internal page rather than the first page."),
    "likely_valid": ("Likely valid", "warn", "Candidates found — no automatic pick."),
    "implausible": ("Implausible", "danger", "Strong fabrication signal (e.g. impossible volume)."),
    "not_in_corpus": ("Not in corpus", "warn", "Searched a held range; no match. Not proof of fabrication."),
    "not_covered": ("Not covered", "muted", "Range not held or unparseable — absence proves nothing."),
    "unverified": ("Unverified", "muted", "Cannot confirm or deny."),
    "error": ("Error / timed out", "danger", "Row failed; not billed."),
}


def format_cite_check(payload: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for r in payload.get("results") or []:
        verdict = (r.get("verdict") or "unverified").lower()
        title, tone, meaning = _VERDICT_COPY.get(verdict, (verdict, "muted", ""))
        gl = _good_law_label(r.get("goodLaw"))
        candidates = []
        for c in r.get("candidates") or []:
            candidates.append(
                {
                    "caseName": c.get("caseName") or c.get("name"),
                    "citation": c.get("citation") or c.get("bluebookCitation"),
                    "caseId": c.get("caseId") or c.get("id"),
                    "knownCitations": c.get("knownCitations") or [],
                }
            )
        rows.append(
            {
                "inputIndex": r.get("inputIndex"),
                "unitIndex": r.get("unitIndex"),
                "asSent": r.get("citationAsSent") or r.get("citationAsWritten") or "",
                "verdict": verdict,
                "verdictLabel": title,
                "tone": tone,
                "meaning": meaning,
                "corrected": r.get("correctedCitation"),
                "goodLaw": gl,
                "candidates": candidates,
                "coverage": r.get("coverage") or r.get("authorityCoverage"),
                "fieldMatches": r.get("fieldMatches"),
                "lookupStatus": r.get("lookupStatus"),
                "message": r.get("message") or r.get("error") or r.get("detail"),
            }
        )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    return {
        "kind": "cite_check",
        "headline": f"Cite check — {len(rows)} result row(s)",
        "subtitle": "Match rows by input index; one input can expand to multiple units.",
        "counts": counts,
        "rows": rows,
        "meta": _meta(payload),
        "summaryText": f"Cite-checked {len(rows)} row(s).",
    }


def format_resolve(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = []
    for c in payload.get("candidates") or payload.get("results") or []:
        candidates.append(
            {
                "caseId": c.get("caseId") or c.get("id"),
                "caseName": c.get("caseName") or c.get("name") or "Untitled",
                "citation": c.get("bluebookCitation") or c.get("citation") or "",
                "court": c.get("courtAbbreviation") or c.get("court") or "",
                "year": c.get("year") or c.get("dateFiled") or "",
                "score": c.get("score") or c.get("confidence"),
            }
        )
    return {
        "kind": "resolve",
        "headline": f"Citation resolve — {len(candidates)} candidate(s)",
        "subtitle": "Up to five matches; no PDF delivery on this endpoint.",
        "candidates": candidates,
        "meta": _meta(payload),
        "summaryText": f"Resolved to {len(candidates)} candidate(s).",
    }


def format_retrieve(payload: dict[str, Any]) -> dict[str, Any]:
    status = (payload.get("status") or "ok").lower()
    case = payload.get("case") or payload.get("result") or {}
    candidates = []
    for c in payload.get("candidates") or []:
        candidates.append(
            {
                "caseId": c.get("caseId") or c.get("id"),
                "caseName": c.get("caseName") or c.get("name"),
                "citation": c.get("bluebookCitation") or c.get("citation"),
                "court": c.get("courtAbbreviation") or c.get("court"),
            }
        )
    gl = _good_law_label(case.get("goodLaw") if isinstance(case, dict) else None)
    return {
        "kind": "retrieve",
        "headline": {
            "ok": "Case retrieved",
            "did_you_mean": "Did you mean one of these?",
            "not_found": "No matching case found",
        }.get(status, f"Retrieve status: {status}"),
        "status": status,
        "case": {
            "caseId": case.get("caseId") or case.get("id"),
            "caseName": case.get("caseName") or case.get("name"),
            "citation": case.get("bluebookCitation") or case.get("citation"),
            "court": case.get("courtAbbreviation") or case.get("court"),
            "dateFiled": case.get("dateFiled") or case.get("year"),
            "summary": (case.get("caseCard") or {}).get("summaryAi") if isinstance(case, dict) else None,
            "goodLaw": gl,
        }
        if case
        else None,
        "candidates": candidates,
        "meta": _meta(payload),
        "summaryText": f"Retrieve status: {status}.",
    }


def format_statute(payload: dict[str, Any]) -> dict[str, Any]:
    status = (payload.get("status") or "ok").lower()
    statute = payload.get("statute") or {}
    return {
        "kind": "statute",
        "headline": {
            "ok": "Statute section retrieved",
            "not_found": "Statute section not found",
            "unavailable": "Statute body unavailable",
            "not_a_statute": "Not a parseable statute/rule cite",
        }.get(status, f"Status: {status}"),
        "status": status,
        "citation": statute.get("citation") or statute.get("bluebookCitation") or payload.get("query"),
        "title": statute.get("title") or statute.get("heading") or statute.get("name"),
        "body": statute.get("body") or statute.get("text"),
        "authorityKey": statute.get("authorityKey") or payload.get("authorityKey"),
        "year": statute.get("year") or payload.get("year"),
        "meta": _meta(payload),
        "summaryText": f"Statute retrieve: {status}.",
    }


def format_case_meta(payload: dict[str, Any]) -> dict[str, Any]:
    case = payload.get("case") or payload
    gl = _good_law_label(case.get("goodLaw") if isinstance(case, dict) else None)
    return {
        "kind": "case_meta",
        "headline": case.get("caseName") or case.get("name") or "Case metadata",
        "subtitle": case.get("bluebookCitation") or case.get("citation") or "",
        "fields": [
            {"label": "Case ID", "value": _s(case.get("caseId") or case.get("id"))},
            {"label": "Court", "value": _s(case.get("courtAbbreviation") or case.get("court"))},
            {"label": "Filed", "value": _s(case.get("dateFiled") or case.get("year"))},
            {"label": "Published", "value": _s(case.get("published"))},
            {"label": "Cited by", "value": _s(case.get("citedByCount"))},
            {"label": "Jurisdiction", "value": _s(case.get("jurisdiction"))},
            {"label": "Opinion type", "value": _s(case.get("opinionType"))},
        ],
        "parallels": case.get("parallelCitations") or [],
        "goodLaw": gl,
        "meta": _meta(payload),
        "summaryText": f"Metadata for {case.get('caseName') or case.get('caseId') or 'case'}.",
    }


def format_batch(payload: dict[str, Any]) -> dict[str, Any]:
    cases = []
    for c in payload.get("cases") or []:
        cases.append(
            {
                "caseId": c.get("caseId") or c.get("id"),
                "caseName": c.get("caseName") or c.get("name"),
                "citation": c.get("bluebookCitation") or c.get("citation"),
                "court": c.get("courtAbbreviation") or c.get("court"),
            }
        )
    not_found = payload.get("notFound") or []
    return {
        "kind": "batch",
        "headline": f"Batch lookup — {len(cases)} found, {len(not_found)} missing",
        "cases": cases,
        "notFound": not_found,
        "meta": _meta(payload),
        "summaryText": f"Batch: {len(cases)} found / {len(not_found)} not found.",
    }


def format_good_law(payload: dict[str, Any]) -> dict[str, Any]:
    gl_src = payload.get("goodLaw") or payload
    gl = _good_law_label(gl_src if isinstance(gl_src, dict) else None)
    negs = []
    for n in (gl_src.get("negativeCitations") if isinstance(gl_src, dict) else None) or payload.get(
        "negativeCitations"
    ) or []:
        negs.append(
            {
                "caseName": n.get("caseName") or n.get("citingCaseName"),
                "citation": n.get("citation") or n.get("bluebookCitation"),
                "treatment": n.get("treatment") or n.get("type") or n.get("signal"),
                "caseId": n.get("caseId") or n.get("citingCaseId"),
            }
        )
    return {
        "kind": "good_law",
        "headline": gl["label"],
        "subtitle": gl.get("basis") or "",
        "goodLaw": gl,
        "negativeCitations": negs,
        "meta": _meta(payload),
        "summaryText": f"Good-law: {gl['status']} ({len(negs)} negative cite(s)).",
    }


def format_cited_by(payload: dict[str, Any]) -> dict[str, Any]:
    items = []
    for c in payload.get("results") or payload.get("citingCases") or payload.get("cases") or []:
        items.append(
            {
                "caseId": c.get("caseId") or c.get("id"),
                "caseName": c.get("caseName") or c.get("name"),
                "citation": c.get("bluebookCitation") or c.get("citation"),
                "court": c.get("courtAbbreviation") or c.get("court"),
                "dateFiled": c.get("dateFiled") or c.get("year"),
                "treatment": c.get("treatment") or c.get("signal"),
            }
        )
    total = payload.get("total") or payload.get("totalCount") or len(items)
    return {
        "kind": "cited_by",
        "headline": f"Cited by — showing {len(items)} of ~{total}",
        "items": items,
        "meta": _meta(payload),
        "summaryText": f"Cited-by returned {len(items)} case(s).",
    }


def format_usage(payload: dict[str, Any]) -> dict[str, Any]:
    by_op = []
    raw = payload.get("byOperation") or {}
    if isinstance(raw, dict):
        for op, stats in raw.items():
            if isinstance(stats, dict):
                by_op.append(
                    {
                        "operation": op,
                        "calls": stats.get("calls") or stats.get("count") or stats.get("quantity"),
                        "units": stats.get("units") or stats.get("quantity"),
                        "costCents": stats.get("costCents"),
                    }
                )
            else:
                by_op.append({"operation": op, "calls": stats, "units": None, "costCents": None})
    elif isinstance(raw, list):
        for stats in raw:
            by_op.append(
                {
                    "operation": stats.get("operation") or stats.get("name"),
                    "calls": stats.get("calls") or stats.get("count"),
                    "units": stats.get("units") or stats.get("quantity"),
                    "costCents": stats.get("costCents"),
                }
            )
    consumer = payload.get("consumer") or payload.get("account") or {}
    return {
        "kind": "usage",
        "headline": "Usage ledger",
        "subtitle": f"Window: last {payload.get('days', '?')} day(s)",
        "consumer": consumer,
        "byOperation": by_op,
        "pricing": payload.get("yourPricing") or payload.get("pricing"),
        "rateLimit": payload.get("rateLimit") or (payload.get("yourPricing") or {}).get("rateLimit"),
        "meta": _meta(payload),
        "summaryText": f"Usage: {len(by_op)} operation row(s).",
    }


def format_document_job(payload: dict[str, Any], *, started: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    status = (payload.get("status") or "unknown").lower()
    citations = []
    for r in payload.get("citations") or payload.get("results") or []:
        verdict = (r.get("verdict") or "").lower()
        title, tone, meaning = _VERDICT_COPY.get(verdict, (verdict or "—", "muted", ""))
        citations.append(
            {
                "asSent": r.get("citationAsSent") or r.get("citation") or "",
                "verdict": verdict,
                "verdictLabel": title,
                "tone": tone,
                "meaning": meaning,
                "corrected": r.get("correctedCitation"),
                "page": r.get("page") or r.get("pageNumber"),
            }
        )
    return {
        "kind": "document_job",
        "headline": f"Document cite-check — {status}",
        "jobId": payload.get("jobId") or (started or {}).get("jobId"),
        "status": status,
        "statusUrl": payload.get("statusUrl") or (started or {}).get("statusUrl"),
        "reportUrl": payload.get("reportUrl") or (started or {}).get("reportUrl"),
        "resultsUrl": payload.get("resultsUrl") or (started or {}).get("resultsUrl"),
        "emails": payload.get("emails") or (started or {}).get("emails"),
        "counts": payload.get("counts"),
        "pollAfterSeconds": payload.get("pollAfterSeconds") or (started or {}).get("pollAfterSeconds"),
        "error": payload.get("error"),
        "citations": citations,
        "meta": _meta(payload),
        "summaryText": f"Document job {payload.get('jobId') or ''}: {status}.",
    }


def format_error(exc: Exception) -> dict[str, Any]:
    import re

    from .lawdiver_client import LawDiverApiError

    def _retry_seconds(text: str) -> Optional[int]:
        m = re.search(r"[Rr]etry in (\d+)\s*s", text or "")
        if m:
            return int(m.group(1))
        m = re.search(r"[Rr]etry[- ][Aa]fter[:\s]+(\d+)", text or "")
        if m:
            return int(m.group(1))
        return None

    if isinstance(exc, LawDiverApiError):
        details = []
        for d in exc.details or []:
            if isinstance(d, dict):
                details.append(f"{d.get('field', '?')}: {d.get('message', '')}")
            else:
                details.append(str(d))
        headline = f"API error — {exc.code}"
        message = str(exc)
        retry_after = _retry_seconds(message)
        if exc.code == "rate_limited" or exc.status == 429:
            headline = "Rate limited"
            retry_after = retry_after or 20
            message = (
                f"{exc}. The account limit is typically 60 requests/minute. "
                f"Wait about {retry_after}s, then try again."
            )
        return {
            "kind": "error",
            "headline": headline,
            "message": message,
            "details": details,
            "requestId": exc.request_id,
            "status": exc.status,
            "code": exc.code,
            "retryAfterSeconds": retry_after,
            "summaryText": f"Error {exc.code}",
        }
    msg = str(exc)
    headline = "Request failed"
    if "Non-JSON" in msg or "504" in msg or "502" in msg or "503" in msg:
        headline = "Upstream gateway error"
        msg = f"{msg} The tester will auto-retry once on some calls; try Run again if it persists."
    return {
        "kind": "error",
        "headline": headline,
        "message": msg,
        "details": [],
        "requestId": None,
        "status": None,
        "code": None,
        "retryAfterSeconds": None,
        "summaryText": "Request failed",
    }


def format_bulk(payload: dict[str, Any]) -> dict[str, Any]:
    results = payload.get("results") or []
    rows = []
    for row in results:
        response = row.get("response") if isinstance(row.get("response"), dict) else {}
        err = response.get("error") if isinstance(response, dict) else None
        rows.append(
            {
                "id": row.get("id"),
                "method": row.get("method"),
                "path": row.get("path"),
                "attempts": row.get("attempts"),
                "ok": bool(row.get("ok")),
                "httpStatus": row.get("httpStatus"),
                "note": (err or {}).get("message") if isinstance(err, dict) else None,
            }
        )
    succeeded = payload.get("succeeded")
    failed = payload.get("failed")
    return {
        "kind": "bulk",
        "headline": "Bulk result",
        "subtitle": (
            f"{succeeded} succeeded, {failed} failed, up to {payload.get('maxAttempts', 3)} attempts each. "
            "Every API call has a time limit. A row with ok=false still includes its last response in the machine view."
        ),
        "status": payload.get("status"),
        "rows": rows,
        "summaryText": f"Bulk {payload.get('status')}: {succeeded} ok, {failed} failed",
        "meta": {"requestId": payload.get("requestId"), "usage": payload.get("usage")},
    }
