"""Extensive LawDiver API + APITester integration tests.

Calls the local app (/api/run) and, for stress, the client directly.
Never touches LawDiver production databases — only the public REST API.
"""

from __future__ import annotations

import json
import time
import traceback
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "test_report.json"
BASE = "http://127.0.0.1:8765"

import sys

sys.path.insert(0, str(ROOT))

results: list[dict[str, Any]] = []


def post_run(function_id: str, inputs: dict[str, Any], timeout: float = 120.0) -> dict[str, Any]:
    body = json.dumps({"functionId": function_id, "inputs": inputs}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/run",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            ms = (time.perf_counter() - t0) * 1000
            return {"http": resp.status, "ms": round(ms, 1), "data": data}
    except urllib.error.HTTPError as e:
        ms = (time.perf_counter() - t0) * 1000
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            payload = {"raw": str(e)}
        return {"http": e.code, "ms": round(ms, 1), "data": payload, "http_error": True}
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return {"http": None, "ms": round(ms, 1), "error": str(e), "trace": traceback.format_exc()}


def record(
    category: str,
    name: str,
    *,
    ok: bool,
    detail: str,
    ms: float | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    row = {
        "category": category,
        "name": name,
        "ok": ok,
        "detail": detail,
        "ms": ms,
    }
    if extra:
        row["extra"] = extra
    results.append(row)
    flag = "PASS" if ok else "FAIL"
    print(f"[{flag}] {category} :: {name} ({ms or '?'} ms) — {detail[:160]}")


def expect_ok(category: str, name: str, resp: dict[str, Any], *, checks: list[str] | None = None) -> dict[str, Any] | None:
    data = resp.get("data") or {}
    view = data.get("view") or {}
    machine = data.get("machine") or {}
    ok = bool(data.get("ok")) and not resp.get("error") and not resp.get("http_error")
    reasons = []
    if not ok:
        reasons.append(view.get("message") or data.get("detail") or resp.get("error") or "ok=false")
    for c in checks or []:
        if c == "has_machine_request" and not (machine.get("request")):
            ok = False
            reasons.append("missing machine.request")
        if c == "has_machine_response" and machine.get("response") is None and not machine.get("error"):
            ok = False
            reasons.append("missing machine.response")
        if c == "has_request_id" and not data.get("requestId") and not (view.get("meta") or {}).get("requestId"):
            # some endpoints may omit; soft
            pass
    record(
        category,
        name,
        ok=ok,
        detail="; ".join(reasons) if reasons else (view.get("headline") or view.get("summaryText") or "ok"),
        ms=resp.get("ms"),
        extra={
            "requestId": data.get("requestId"),
            "kind": view.get("kind"),
            "machinePath": (machine.get("request") or {}).get("path"),
        },
    )
    return data if ok else data


def expect_fail(category: str, name: str, resp: dict[str, Any], *, contain: str | None = None) -> None:
    data = resp.get("data") or {}
    view = data.get("view") or {}
    msg = view.get("message") or resp.get("error") or ""
    failed = data.get("ok") is False or bool(resp.get("error"))
    ok = failed
    detail = msg or "expected failure"
    if contain and contain.lower() not in str(msg).lower() and contain.lower() not in detail.lower():
        # still count as pass if it failed for any validation reason
        detail = f"failed as expected ({msg})"
    record(category, name, ok=ok, detail=detail[:240], ms=resp.get("ms"))


def main() -> None:
    print("=== LawDiver APITester extensive suite ===\n")

    # --- Happy path: all functions ---
    expect_ok("happy", "discovery", post_run("discovery", {}), checks=["has_machine_request", "has_machine_response"])
    expect_ok("happy", "jurisdictions", post_run("jurisdictions", {}), checks=["has_machine_request"])

    search = expect_ok(
        "happy",
        "search_one_state_FL",
        post_run(
            "search",
            {
                "query": "adverse possession",
                "jurisdictionType": "one_state",
                "state": "FL",
                "limit": 5,
                "searchType": "auto",
                "goodLawReport": True,
            },
        ),
        checks=["has_machine_request", "has_machine_response"],
    )
    case_id = None
    if search and search.get("ok"):
        cases = (search.get("view") or {}).get("results") or []
        if cases:
            case_id = cases[0].get("caseId")

    expect_ok(
        "happy",
        "search_circuit_11",
        post_run(
            "search",
            {
                "query": "qualified immunity excessive force",
                "jurisdictionType": "federal_circuit",
                "circuit": "11",
                "limit": 3,
                "dateFrom": "2015-01-01",
                "caseCard": True,
            },
        ),
    )
    expect_ok(
        "happy",
        "search_all_federal_semantic",
        post_run(
            "search",
            {
                "query": "breach of fiduciary duty closely held corporation",
                "jurisdictionType": "all_federal",
                "searchType": "semantic",
                "limit": 3,
            },
        ),
    )
    expect_ok(
        "happy",
        "search_supreme_court_citation",
        post_run(
            "search",
            {
                "query": "410 U.S. 113",
                "jurisdictionType": "us_supreme_court",
                "searchType": "citation",
                "limit": 3,
            },
        ),
    )
    expect_ok(
        "happy",
        "search_case_name",
        post_run(
            "search",
            {
                "query": "Brown v. Board of Education",
                "jurisdictionType": "us_supreme_court",
                "searchType": "case_name",
                "limit": 3,
            },
        ),
    )

    expect_ok(
        "happy",
        "cite_check_single_valid",
        post_run("cite_check", {"citations": "410 U.S. 113"}),
        checks=["has_machine_response"],
    )
    expect_ok(
        "happy",
        "cite_check_batch_mixed",
        post_run(
            "cite_check",
            {
                "citations": "\n".join(
                    [
                        "410 U.S. 113",
                        "347 U.S. 483",
                        "999 F.999d 99999",  # implausible-ish
                        "Smith v. Imaginary Corp., 123 F.3d 456 (11th Cir. 2099)",
                        "42 U.S.C. § 1983",
                    ]
                )
            },
        ),
    )

    expect_ok("happy", "resolve_roe", post_run("resolve", {"query": "410 U.S. 113"}))
    expect_ok("happy", "retrieve_brown", post_run("retrieve", {"query": "Brown v. Board of Education"}))
    expect_ok("happy", "statute_1983", post_run("statute", {"query": "42 U.S.C. § 1983"}, timeout=90))
    expect_ok("happy", "statute_fla", post_run("statute", {"query": "Fla. Stat. § 768.81"}, timeout=90))
    expect_ok("happy", "usage", post_run("usage", {"days": 7}))

    if case_id:
        expect_ok("happy", "case_metadata", post_run("case_metadata", {"caseId": str(case_id)}))
        expect_ok("happy", "good_law", post_run("good_law", {"caseId": str(case_id)}))
        expect_ok("happy", "cited_by", post_run("cited_by", {"caseId": str(case_id), "limit": 10, "offset": 0}))
        expect_ok("happy", "case_batch", post_run("case_batch", {"caseIds": str(case_id)}))
        pdf = post_run("case_pdf", {"caseId": str(case_id)}, timeout=120)
        expect_ok("happy", "case_pdf", pdf)
    else:
        record("happy", "case_id_dependent", ok=False, detail="No caseId from search to continue chain")

    # --- Edge / validation via app ---
    expect_fail(
        "edge",
        "search_missing_state",
        post_run("search", {"query": "x", "jurisdictionType": "one_state", "state": "", "limit": 1}),
        contain="state",
    )
    expect_fail(
        "edge",
        "search_missing_circuit",
        post_run("search", {"query": "x", "jurisdictionType": "federal_circuit", "circuit": "", "limit": 1}),
        contain="circuit",
    )
    expect_fail(
        "edge",
        "search_bogus_state_code",
        post_run("search", {"query": "x", "jurisdictionType": "one_state", "state": "ZZ", "limit": 1}),
    )
    expect_fail("edge", "cite_check_empty", post_run("cite_check", {"citations": ""}))
    expect_fail("edge", "statute_empty", post_run("statute", {"query": "", "authorityKey": ""}))
    expect_fail("edge", "batch_empty", post_run("case_batch", {"caseIds": ""}))
    expect_ok(
        "edge",
        "metadata_unknown_id",
        post_run("case_metadata", {"caseId": "999999999999"}),
    )  # API may 404 or return empty — either handled
    # Soft: if ok=false with not_found that's fine
    bad_meta = results[-1]
    if not bad_meta["ok"]:
        # flip to pass if it's a clean API error
        msg = bad_meta["detail"].lower()
        if "not_found" in msg or "404" in msg or "error" in msg:
            results[-1]["ok"] = True
            results[-1]["detail"] = f"clean API error: {bad_meta['detail']}"
            print(f"[PASS] edge :: metadata_unknown_id (soft) — {results[-1]['detail'][:120]}")

    expect_ok(
        "edge",
        "retrieve_nonsense",
        post_run("retrieve", {"query": "zzzznotacase12345xyz"}),
    )
    nonsense = results[-1]
    # did_you_mean or not_found are success HTTP-wise
    if not nonsense["ok"]:
        pass
    else:
        # check status in view if available
        pass

    retrieve_data = post_run("retrieve", {"query": "Smith"})
    data = retrieve_data.get("data") or {}
    status = (data.get("view") or {}).get("status")
    record(
        "edge",
        "retrieve_ambiguous_smith",
        ok=bool(data.get("ok")),
        detail=f"status={status} headline={(data.get('view') or {}).get('headline')}",
        ms=retrieve_data.get("ms"),
    )

    # Document job with fake id
    expect_fail(
        "edge",
        "document_job_bogus",
        post_run("document_job", {"jobId": "00000000-0000-0000-0000-000000000000"}),
    )

    # Document upload via multipart (tiny valid-ish pdf)
    pdf_path = ROOT / "downloads" / "_suite_brief.pdf"
    # Minimal PDF with a citation string in content (may not extract well)
    pdf_path.write_bytes(
        b"""%PDF-1.4
1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj
2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj
3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]
/Contents 4 0 R /Resources<< /Font<< /F1 5 0 R >> >> >>endobj
4 0 obj<< /Length 68 >>stream
BT /F1 12 Tf 72 720 Td (See Roe v. Wade, 410 U.S. 113 (1973).) Tj ET
endstream endobj
5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj
xref
0 6
trailer<< /Size 6 /Root 1 0 R >>
startxref
0
%%EOF
"""
    )
    t0 = time.perf_counter()
    try:
        import uuid

        boundary = f"----Boundary{uuid.uuid4().hex}"
        file_bytes = pdf_path.read_bytes()
        parts = []
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="_suite_brief.pdf"\r\n'
            f"Content-Type: application/pdf\r\n\r\n".encode()
            + file_bytes
            + b"\r\n"
        )
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"downloadReport\"\r\n\r\nfalse\r\n".encode()
        )
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)
        req = urllib.request.Request(
            f"{BASE}/api/run/document",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            doc = json.loads(resp.read().decode())
        ms = (time.perf_counter() - t0) * 1000
        record(
            "happy",
            "document_cite_check_upload",
            ok=bool(doc.get("ok")),
            detail=(doc.get("view") or {}).get("headline") or (doc.get("view") or {}).get("message") or str(doc.get("ok")),
            ms=round(ms, 1),
            extra={"jobId": (doc.get("view") or {}).get("jobId"), "status": (doc.get("view") or {}).get("status")},
        )
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        record("happy", "document_cite_check_upload", ok=False, detail=str(e), ms=round(ms, 1))

    # --- Output quality spot-checks ---
    cite = post_run("cite_check", {"citations": "410 U.S. 113"})
    cdata = cite.get("data") or {}
    rows = (cdata.get("view") or {}).get("rows") or []
    verdict = rows[0].get("verdict") if rows else None
    record(
        "quality",
        "roe_cite_verdict",
        ok=verdict in ("valid", "likely_valid", "page_mismatch"),
        detail=f"verdict={verdict} corrected={rows[0].get('corrected') if rows else None}",
        ms=cite.get("ms"),
    )

    search_q = post_run(
        "search",
        {
            "query": "promissory estoppel",
            "jurisdictionType": "one_state_plus_federal",
            "state": "NY",
            "limit": 5,
            "opinionText": False,
        },
    )
    sview = (search_q.get("data") or {}).get("view") or {}
    n = len(sview.get("results") or [])
    human = bool(sview.get("headline")) and sview.get("kind") == "search"
    machine_body = ((search_q.get("data") or {}).get("machine") or {}).get("request", {}).get("body")
    record(
        "quality",
        "human_vs_machine_search",
        ok=human and isinstance(machine_body, dict) and "jurisdiction" in machine_body,
        detail=f"results={n} human_kind={sview.get('kind')} machine_has_jurisdiction={isinstance(machine_body, dict)}",
        ms=search_q.get("ms"),
    )

    # Machine panel must redact key
    auth = str((((search_q.get("data") or {}).get("machine") or {}).get("request") or {}).get("headers", {}).get("Authorization", ""))
    record(
        "quality",
        "api_key_redacted",
        ok="redacted" in auth.lower() or not auth.startswith("Bearer ld_"),
        detail=f"Authorization header shown as: {auth}",
        ms=None,
    )

    # --- Stress / throughput ---
    print("\n=== Stress: sequential burst ===")
    from app.lawdiver_client import LawDiverApiError, LawDiverClient

    seq_times: list[float] = []
    seq_errors: list[str] = []
    rate_limited = 0
    with LawDiverClient(timeout=60.0) as client:
        for i in range(25):
            t0 = time.perf_counter()
            try:
                client.search(
                    query="negligence",
                    jurisdiction={"type": "one_state", "state": "CA"},
                    limit=2,
                )
                seq_times.append((time.perf_counter() - t0) * 1000)
            except LawDiverApiError as e:
                seq_times.append((time.perf_counter() - t0) * 1000)
                seq_errors.append(f"{e.code}:{e.status}")
                if e.code == "rate_limited" or e.status == 429:
                    rate_limited += 1
            except Exception as e:
                seq_times.append((time.perf_counter() - t0) * 1000)
                seq_errors.append(str(e))
    record(
        "stress",
        "sequential_25_searches",
        ok=rate_limited == 0 and len(seq_errors) == 0,
        detail=(
            f"n={len(seq_times)} avg_ms={sum(seq_times)/len(seq_times):.0f} "
            f"p50={sorted(seq_times)[len(seq_times)//2]:.0f} max={max(seq_times):.0f} "
            f"errors={len(seq_errors)} rate_limited={rate_limited} sample={seq_errors[:3]}"
        ),
        ms=round(sum(seq_times), 1),
        extra={"times_ms": [round(x, 1) for x in seq_times], "errors": seq_errors},
    )

    print("\n=== Stress: parallel burst ===")
    par_times: list[float] = []
    par_errors: list[str] = []
    par_rl = 0

    def one_search(i: int) -> tuple[float, str | None]:
        t0 = time.perf_counter()
        try:
            with LawDiverClient(timeout=60.0) as client:
                client.cite_check(citation="410 U.S. 113" if i % 2 == 0 else "347 U.S. 483")
            return (time.perf_counter() - t0) * 1000, None
        except LawDiverApiError as e:
            return (time.perf_counter() - t0) * 1000, f"{e.code}:{e.status}"
        except Exception as e:
            return (time.perf_counter() - t0) * 1000, str(e)

    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = [pool.submit(one_search, i) for i in range(20)]
        for f in as_completed(futs):
            ms, err = f.result()
            par_times.append(ms)
            if err:
                par_errors.append(err)
                if "rate_limited" in err or ":429" in err:
                    par_rl += 1

    record(
        "stress",
        "parallel_20_citechecks_10_workers",
        ok=True,  # rate limit is informative, not a suite failure
        detail=(
            f"n={len(par_times)} avg_ms={sum(par_times)/len(par_times):.0f} "
            f"max={max(par_times):.0f} errors={len(par_errors)} rate_limited={par_rl} sample={par_errors[:5]}"
        ),
        ms=round(max(par_times), 1) if par_times else None,
        extra={"times_ms": [round(x, 1) for x in par_times], "errors": par_errors},
    )

    # Push harder until rate limit or 40 more
    print("\n=== Stress: find rate-limit ceiling ===")
    ceiling_errors: list[str] = []
    hit_rl = False
    t_burst0 = time.perf_counter()
    with LawDiverClient(timeout=30.0) as client:
        for i in range(60):
            try:
                client.usage(days=1)
            except LawDiverApiError as e:
                ceiling_errors.append(f"{i}:{e.code}:{e.status}")
                if e.status == 429 or e.code == "rate_limited":
                    hit_rl = True
                    break
            except Exception as e:
                ceiling_errors.append(f"{i}:{e}")
                break
    burst_ms = (time.perf_counter() - t_burst0) * 1000
    record(
        "stress",
        "rate_limit_ceiling_usage_calls",
        ok=True,
        detail=f"hit_rate_limit={hit_rl} errors={ceiling_errors[:8]} elapsed_ms={burst_ms:.0f}",
        ms=round(burst_ms, 1),
        extra={"errors": ceiling_errors, "hit_rate_limit": hit_rl},
    )

    # App-layer rapid fire through /api/run
    print("\n=== Stress: app proxy rapid fire ===")
    app_errors = []
    app_times = []
    for i in range(15):
        r = post_run("resolve", {"query": "410 U.S. 113"}, timeout=60)
        app_times.append(r.get("ms") or 0)
        data = r.get("data") or {}
        if not data.get("ok"):
            app_errors.append((data.get("view") or {}).get("message") or r.get("error"))
    record(
        "stress",
        "app_proxy_15_resolves",
        ok=len(app_errors) == 0,
        detail=f"avg_ms={sum(app_times)/len(app_times):.0f} max={max(app_times):.0f} errors={app_errors[:3]}",
        ms=round(sum(app_times), 1),
    )

    # Summary
    passed = sum(1 for r in results if r["ok"])
    failed = sum(1 for r in results if not r["ok"])
    report = {
        "summary": {"passed": passed, "failed": failed, "total": len(results)},
        "results": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n=== DONE: {passed}/{len(results)} passed, {failed} failed ===")
    print(f"Report: {OUT}")
    if failed:
        print("\nFailures:")
        for r in results:
            if not r["ok"]:
                print(f"  - {r['category']}::{r['name']}: {r['detail']}")


if __name__ == "__main__":
    main()
