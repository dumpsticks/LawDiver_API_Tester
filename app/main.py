"""
LawDiver API Tester — local-only UI.

Calls the public LawDiver REST API at https://lawdiver.com/api/v1.
Never connects to any LawDiver production database.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, formatters
from .lawdiver_client import LawDiverApiError, LawDiverClient

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)

DOWNLOADS = ROOT / "downloads"
DOWNLOADS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="LawDiver API Tester", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


FUNCTIONS: list[dict[str, Any]] = [
    {
        "id": "discovery",
        "label": "API discovery",
        "group": "Reference",
        "description": "List endpoints and pricing policy. No API key required for the remote call.",
        "fields": [],
    },
    {
        "id": "jurisdictions",
        "label": "Jurisdictions",
        "group": "Reference",
        "description": "Authoritative state codes, circuits, and example jurisdiction payloads.",
        "fields": [],
    },
    {
        "id": "search",
        "label": "Case search",
        "group": "Search & retrieve",
        "description": "Search the caselaw corpus. Jurisdiction is required. Companion fields appear only when the API needs them.",
        "fields": [
            {"name": "query", "label": "Query", "type": "text", "required": True, "placeholder": "qualified immunity excessive force"},
            {
                "name": "jurisdictionType",
                "label": "Jurisdiction type",
                "type": "select",
                "required": True,
                "options": [
                    {"value": "one_state_plus_federal", "label": "One state + federal (practitioner default)"},
                    {"value": "one_state", "label": "One state only"},
                    {"value": "all_federal", "label": "All federal"},
                    {"value": "all_states", "label": "All states"},
                    {"value": "all_states_and_federal", "label": "All states and federal (broadest)"},
                    {"value": "federal_circuit", "label": "One federal circuit"},
                    {"value": "federal_district", "label": "Federal districts in a state"},
                    {"value": "us_supreme_court", "label": "U.S. Supreme Court only"},
                ],
                "default": "one_state_plus_federal",
                "drivesVisibility": True,
            },
            {
                "name": "state",
                "label": "State",
                "type": "select",
                "required": True,
                "optionsSource": "states",
                "default": "FL",
                "showWhen": {"jurisdictionType": ["one_state", "one_state_plus_federal"]},
                "hint": "USPS code — required for this jurisdiction type.",
            },
            {
                "name": "circuit",
                "label": "Circuit",
                "type": "select",
                "required": True,
                "optionsSource": "circuits",
                "default": "11",
                "showWhen": {"jurisdictionType": ["federal_circuit"]},
                "hint": "Required for federal_circuit searches.",
            },
            {
                "name": "districtState",
                "label": "District state",
                "type": "select",
                "required": True,
                "optionsSource": "states",
                "default": "TX",
                "showWhen": {"jurisdictionType": ["federal_district"]},
                "hint": "Federal district courts sitting in this state.",
            },
            {
                "name": "searchType",
                "label": "Search type",
                "type": "select",
                "options": [
                    {"value": "auto", "label": "Auto (recommended)"},
                    {"value": "citation", "label": "Citation"},
                    {"value": "case_name", "label": "Case name"},
                    {"value": "boolean", "label": "Boolean"},
                    {"value": "semantic", "label": "Semantic"},
                    {"value": "hybrid", "label": "Hybrid"},
                ],
                "default": "auto",
            },
            {"name": "limit", "label": "Limit", "type": "number", "default": "5", "min": 1, "max": 50},
            {"name": "dateFrom", "label": "Date from (optional)", "type": "text", "placeholder": "2015-01-01"},
            {"name": "dateTo", "label": "Date to (optional)", "type": "text", "placeholder": "2026-01-01"},
            {"name": "includeUnpublished", "label": "Include unpublished", "type": "checkbox"},
            {"name": "goodLawOnly", "label": "Good law only", "type": "checkbox"},
            {"name": "caseCard", "label": "Include AI case card", "type": "checkbox"},
            {"name": "opinionText", "label": "Include opinion text", "type": "checkbox"},
            {"name": "goodLawReport", "label": "Expand good-law report", "type": "checkbox", "default": True},
        ],
    },
    {
        "id": "cite_check",
        "label": "Cite check (citations)",
        "group": "Cite check",
        "description": "Validate one citation or a list (one per line, max 50).",
        "fields": [
            {
                "name": "citations",
                "label": "Citation(s)",
                "type": "textarea",
                "required": True,
                "placeholder": "410 U.S. 113\n347 U.S. 483\nSmith v. Jones, 123 F.3d 456 (11th Cir. 2020)",
                "rows": 6,
            },
        ],
    },
    {
        "id": "document_cite_check",
        "label": "Cite check (document upload)",
        "group": "Cite check",
        "description": "Upload a PDF/DOCX brief. Starts an async job and polls until complete.",
        "fields": [
            {"name": "file", "label": "Brief (PDF or Word)", "type": "file", "required": True},
            {"name": "emails", "label": "Email results link (optional)", "type": "text", "placeholder": "partner@firm.com, associate@firm.com"},
            {"name": "downloadReport", "label": "Download PDF report when done", "type": "checkbox", "default": True},
        ],
    },
    {
        "id": "document_job",
        "label": "Document job status",
        "group": "Cite check",
        "description": "Poll an existing document cite-check job by ID.",
        "fields": [
            {"name": "jobId", "label": "Job ID", "type": "text", "required": True, "placeholder": "job_..."},
        ],
    },
    {
        "id": "resolve",
        "label": "Citation resolve",
        "group": "Search & retrieve",
        "description": "Map a cite or name to up to five candidates (no PDF).",
        "fields": [
            {"name": "query", "label": "Query", "type": "text", "required": True, "placeholder": "410 U.S. 113"},
        ],
    },
    {
        "id": "retrieve",
        "label": "Case retrieve",
        "group": "Search & retrieve",
        "description": "Resolve and deliver one case, or return did-you-mean candidates.",
        "fields": [
            {"name": "query", "label": "Citation or case name", "type": "text", "required": True, "placeholder": "Roe v. Wade"},
            {"name": "caseId", "label": "Case ID (optional, for did-you-mean follow-up)", "type": "text"},
        ],
    },
    {
        "id": "statute",
        "label": "Statute retrieve",
        "group": "Search & retrieve",
        "description": "Pull statute / regulation / rule text by Bluebook section cite.",
        "fields": [
            {"name": "query", "label": "Bluebook citation", "type": "text", "placeholder": "42 U.S.C. § 1983"},
            {"name": "authorityKey", "label": "Authority key (optional)", "type": "text", "placeholder": "st:federal:usc-42:1983"},
            {"name": "year", "label": "Edition year (optional)", "type": "number", "placeholder": "2024"},
        ],
    },
    {
        "id": "case_metadata",
        "label": "Case metadata",
        "group": "Case details",
        "description": "Metadata for an opinion or cluster id.",
        "fields": [
            {"name": "caseId", "label": "Case ID", "type": "text", "required": True},
        ],
    },
    {
        "id": "case_batch",
        "label": "Case batch",
        "group": "Case details",
        "description": "Look up up to 50 case IDs at once (one per line).",
        "fields": [
            {"name": "caseIds", "label": "Case IDs", "type": "textarea", "required": True, "rows": 5, "placeholder": "4218873\n4218874"},
        ],
    },
    {
        "id": "good_law",
        "label": "Good-law detail",
        "group": "Case details",
        "description": "Status plus negative-treatment citations for a case.",
        "fields": [
            {"name": "caseId", "label": "Case ID", "type": "text", "required": True},
        ],
    },
    {
        "id": "cited_by",
        "label": "Cited by",
        "group": "Case details",
        "description": "Paginated list of citing cases.",
        "fields": [
            {"name": "caseId", "label": "Case ID", "type": "text", "required": True},
            {"name": "limit", "label": "Limit", "type": "number", "default": "25", "min": 1, "max": 100},
            {"name": "offset", "label": "Offset", "type": "number", "default": "0", "min": 0},
        ],
    },
    {
        "id": "case_pdf",
        "label": "Case PDF",
        "group": "Case details",
        "description": "Download the opinion PDF (opinion id required).",
        "fields": [
            {"name": "caseId", "label": "Opinion ID", "type": "text", "required": True},
        ],
    },
    {
        "id": "usage",
        "label": "Usage ledger",
        "group": "Account",
        "description": "Volume by operation and your rate limits.",
        "fields": [
            {"name": "days", "label": "Days", "type": "number", "default": "30", "min": 1, "max": 365},
        ],
    },
    {
        "id": "bulk",
        "label": "Bulk upload",
        "group": "Batch",
        "description": (
            "Upload a JSON list of API calls. Each call is attempted 3 times. "
            "When the job finishes you get one combined result. "
            "Every API call has a time limit; complex searches can time out when usage is high. "
            "When usage is low, the file runs in parallel and can finish faster."
        ),
        "fields": [
            {
                "name": "requestsJson",
                "label": "Bulk JSON",
                "type": "textarea",
                "required": True,
                "rows": 14,
                "default": (
                    '{\n'
                    '  "requests": [\n'
                    '    {"id": "jurisdictions", "method": "GET", "path": "/api/v1/jurisdictions"},\n'
                    '    {"id": "usage", "method": "GET", "path": "/api/v1/usage"}\n'
                    '  ]\n'
                    '}'
                ),
                "hint": "Up to 100 calls. PDF downloads and document uploads stay as their own menu items. The tester waits until the job finishes.",
            },
        ],
    },
]


def _client() -> LawDiverClient:
    return LawDiverClient(
        user_agent="LawDiver-APITester/1.0 (+local; python)",
        timeout=120.0,
    )


def _api_base() -> str:
    return (os.environ.get("LAWDIVER_API_BASE") or "https://lawdiver.com/api/v1").rstrip("/")


def _wire(
    *,
    method: str,
    path: str,
    body: Any = None,
    params: Optional[dict[str, Any]] = None,
    content_type: str = "application/json",
    notes: Optional[str] = None,
) -> dict[str, Any]:
    """Describe the LawDiver HTTP call for the machine panel (API key redacted)."""
    out: dict[str, Any] = {
        "method": method.upper(),
        "url": f"{_api_base()}{path}",
        "path": path,
        "headers": {
            "Authorization": "Bearer <redacted>",
            "User-Agent": "LawDiver-APITester/1.0 (+local; python)",
        },
    }
    if method.upper() != "GET" or body is not None:
        out["headers"]["Content-Type"] = content_type
    if params:
        out["query"] = params
    if body is not None:
        out["body"] = body
    if notes:
        out["notes"] = notes
    return out


def _machine_payload(
    request: Optional[dict[str, Any]],
    response: Any,
    *,
    error: Any = None,
) -> dict[str, Any]:
    return {"request": request, "response": response, "error": error}


def _bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def _build_jurisdiction(body: dict[str, Any]) -> dict[str, Any]:
    """Build jurisdiction object; only include companion fields the API requires for that type."""
    jtype = (body.get("jurisdictionType") or "one_state_plus_federal").strip()
    jur: dict[str, Any] = {"type": jtype}

    if jtype in ("one_state", "one_state_plus_federal"):
        state = (body.get("state") or "").strip().upper()
        if not state:
            raise ValueError(
                "Pick a state. Jurisdiction types one_state and one_state_plus_federal require jurisdiction.state (USPS code)."
            )
        jur["state"] = state
    elif jtype == "federal_circuit":
        circuit = (body.get("circuit") or "").strip().lower()
        if not circuit:
            raise ValueError("Pick a circuit. federal_circuit requires jurisdiction.circuit (1–11, dc, or federal).")
        jur["circuit"] = circuit
    elif jtype == "federal_district":
        district = (body.get("districtState") or "").strip().upper()
        if not district:
            raise ValueError(
                "Pick a district state. federal_district requires jurisdiction.districtState (USPS code)."
            )
        jur["districtState"] = district
    # all_states / all_federal / all_states_and_federal / us_supreme_court: type alone
    return jur


def _fn_meta(function_id: str) -> dict[str, Any]:
    for f in FUNCTIONS:
        if f["id"] == function_id:
            return f
    raise HTTPException(404, f"Unknown function: {function_id}")


class RunBody(BaseModel):
    functionId: str
    inputs: dict[str, Any] = Field(default_factory=dict)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


def _reference_options() -> dict[str, Any]:
    """Load authoritative state/circuit lists for search dropdowns (cached on process)."""
    cached = getattr(_reference_options, "_cache", None)
    if cached is not None:
        return cached
    states: list[dict[str, str]] = []
    circuits: list[dict[str, str]] = []
    try:
        with _client() as client:
            payload = client.jurisdictions()
        for s in payload.get("states") or []:
            if isinstance(s, dict) and s.get("code"):
                states.append({"value": s["code"], "label": f"{s['code']} — {s.get('name') or s['code']}"})
        if not states:
            for code in payload.get("stateCodes") or []:
                states.append({"value": str(code), "label": str(code)})
        for c in payload.get("circuits") or []:
            code = str(c)
            label = {
                "dc": "D.C. Circuit",
                "federal": "Federal Circuit",
            }.get(code, f"{code}th Circuit" if code.isdigit() else code)
            circuits.append({"value": code, "label": label})
    except Exception:
        # Offline fallback so the form still works
        for code in (
            "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN "
            "MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY"
        ).split():
            states.append({"value": code, "label": code})
        for code in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "dc", "federal"]:
            circuits.append({"value": code, "label": code})
    out = {"states": states, "circuits": circuits}
    _reference_options._cache = out  # type: ignore[attr-defined]
    return out


@app.get("/api/functions")
def list_functions() -> dict[str, Any]:
    key_set = bool(
        (os.environ.get("LAWDIVER_API_KEY") or os.environ.get("LAWDIVER_AGENT_API_KEY") or "").strip()
    )
    return {
        "functions": FUNCTIONS,
        "keyConfigured": key_set,
        "baseUrl": os.environ.get("LAWDIVER_API_BASE") or "https://lawdiver.com/api/v1",
        "reference": _reference_options(),
    }


@app.get("/api/history")
def history(limit: int = 40) -> dict[str, Any]:
    return {"items": db.list_history(limit=min(max(limit, 1), 200))}


@app.get("/api/history/{item_id}")
def history_item(item_id: int) -> dict[str, Any]:
    item = db.get_history_item(item_id)
    if not item:
        raise HTTPException(404, "History item not found")
    return item


@app.post("/api/run")
def run_function(body: RunBody) -> dict[str, Any]:
    meta = _fn_meta(body.functionId)
    inputs = body.inputs or {}
    view: dict[str, Any]
    request_id: Optional[str] = None
    ok = True
    error_message: Optional[str] = None
    download: Optional[dict[str, str]] = None
    wire_request: Optional[dict[str, Any]] = None
    wire_response: Any = None
    wire_error: Any = None

    raw: Any = None
    try:
        with _client() as client:
            if body.functionId == "discovery":
                wire_request = _wire(method="GET", path="", notes="Unauthenticated discovery document")
                # discovery hits base URL with no trailing path beyond /api/v1
                wire_request["url"] = _api_base()
                wire_request["path"] = "/"
                wire_request["headers"].pop("Content-Type", None)
                del wire_request["headers"]["Authorization"]
                raw = client.discovery()
                view = formatters.format_discovery(raw)
            elif body.functionId == "jurisdictions":
                wire_request = _wire(method="GET", path="/jurisdictions")
                wire_request["headers"].pop("Content-Type", None)
                raw = client.jurisdictions()
                view = formatters.format_jurisdictions(raw)
            elif body.functionId == "search":
                filters: dict[str, Any] = {}
                if inputs.get("dateFrom"):
                    filters["dateFrom"] = inputs["dateFrom"]
                if inputs.get("dateTo"):
                    filters["dateTo"] = inputs["dateTo"]
                if _bool(inputs.get("includeUnpublished")):
                    filters["includeUnpublished"] = True
                if _bool(inputs.get("goodLawOnly")):
                    filters["goodLawOnly"] = True
                include: dict[str, Any] = {}
                if _bool(inputs.get("caseCard")):
                    include["caseCard"] = True
                if _bool(inputs.get("opinionText")):
                    include["opinionText"] = True
                if "goodLawReport" in inputs:
                    include["goodLawReport"] = _bool(inputs.get("goodLawReport"))
                kwargs: dict[str, Any] = {
                    "query": (inputs.get("query") or "").strip(),
                    "jurisdiction": _build_jurisdiction(inputs),
                    "limit": int(inputs.get("limit") or 5),
                }
                st = inputs.get("searchType") or "auto"
                if st and st != "auto":
                    kwargs["searchType"] = st
                if filters:
                    kwargs["filters"] = filters
                if include:
                    kwargs["include"] = include
                wire_request = _wire(method="POST", path="/search", body=kwargs)
                raw = client.search(**kwargs)
                view = formatters.format_search(raw)
            elif body.functionId == "cite_check":
                cites = _lines(str(inputs.get("citations") or ""))
                if not cites:
                    raise ValueError("Enter at least one citation.")
                cite_body: dict[str, Any] = (
                    {"citation": cites[0]} if len(cites) == 1 else {"citations": cites[:50]}
                )
                wire_request = _wire(method="POST", path="/citecheck/cite", body=cite_body)
                if len(cites) == 1:
                    raw = client.cite_check(citation=cites[0])
                else:
                    raw = client.cite_check(citations=cites[:50])
                view = formatters.format_cite_check(raw)
            elif body.functionId == "document_job":
                job_id = (inputs.get("jobId") or "").strip()
                wire_request = _wire(method="GET", path=f"/citecheck/jobs/{job_id}")
                wire_request["headers"].pop("Content-Type", None)
                raw = client.document_job(job_id)
                view = formatters.format_document_job(raw)
            elif body.functionId == "resolve":
                resolve_body = {"query": (inputs.get("query") or "").strip()}
                wire_request = _wire(method="POST", path="/citations/resolve", body=resolve_body)
                raw = client.resolve_citation(resolve_body["query"])
                view = formatters.format_resolve(raw)
            elif body.functionId == "retrieve":
                case_id = (inputs.get("caseId") or "").strip() or None
                retrieve_body: dict[str, Any] = {"query": (inputs.get("query") or "").strip()}
                if case_id:
                    retrieve_body["caseId"] = case_id
                wire_request = _wire(method="POST", path="/cases/retrieve", body=retrieve_body)
                raw = client.retrieve(query=retrieve_body["query"], case_id=case_id)
                view = formatters.format_retrieve(raw)
            elif body.functionId == "statute":
                year = inputs.get("year")
                year_i = int(year) if year not in (None, "") else None
                q = (inputs.get("query") or "").strip() or None
                ak = (inputs.get("authorityKey") or "").strip() or None
                if not q and not ak:
                    raise ValueError("Provide a Bluebook citation and/or authority key.")
                statute_body: dict[str, Any] = {}
                if q:
                    statute_body["query"] = q
                if ak:
                    statute_body["authorityKey"] = ak
                if year_i is not None:
                    statute_body["year"] = year_i
                wire_request = _wire(method="POST", path="/statutes/retrieve", body=statute_body)
                raw = client.retrieve_statute(query=q, authority_key=ak, year=year_i)
                view = formatters.format_statute(raw)
            elif body.functionId == "case_metadata":
                case_id = (inputs.get("caseId") or "").strip()
                wire_request = _wire(method="GET", path=f"/cases/{case_id}")
                wire_request["headers"].pop("Content-Type", None)
                raw = client.case_metadata(case_id)
                view = formatters.format_case_meta(raw)
            elif body.functionId == "case_batch":
                ids = _lines(str(inputs.get("caseIds") or ""))
                if not ids:
                    raise ValueError("Enter at least one case ID.")
                batch_body = {"caseIds": ids[:50]}
                wire_request = _wire(method="POST", path="/cases/batch", body=batch_body)
                raw = client.case_batch(ids[:50])
                view = formatters.format_batch(raw)
            elif body.functionId == "good_law":
                case_id = (inputs.get("caseId") or "").strip()
                wire_request = _wire(method="GET", path=f"/cases/{case_id}/good-law")
                wire_request["headers"].pop("Content-Type", None)
                raw = client.good_law(case_id)
                view = formatters.format_good_law(raw)
            elif body.functionId == "cited_by":
                case_id = (inputs.get("caseId") or "").strip()
                limit = int(inputs.get("limit") or 25)
                offset = int(inputs.get("offset") or 0)
                wire_request = _wire(
                    method="GET",
                    path=f"/cases/{case_id}/cited-by",
                    params={"limit": limit, "offset": offset},
                )
                wire_request["headers"].pop("Content-Type", None)
                raw = client.cited_by(case_id, limit=limit, offset=offset)
                view = formatters.format_cited_by(raw)
            elif body.functionId == "case_pdf":
                case_id = (inputs.get("caseId") or "").strip()
                wire_request = _wire(
                    method="GET",
                    path=f"/cases/{case_id}/pdf",
                    notes="Response is application/pdf bytes (not JSON).",
                )
                wire_request["headers"].pop("Content-Type", None)
                pdf_bytes = client.case_pdf(case_id)
                safe = re.sub(r"[^A-Za-z0-9_-]+", "_", case_id)[:80]
                path = DOWNLOADS / f"case_{safe}.pdf"
                path.write_bytes(pdf_bytes)
                raw = {
                    "contentType": "application/pdf",
                    "bytes": len(pdf_bytes),
                    "savedAs": path.name,
                    "note": "Binary PDF omitted from this panel; download from the human view.",
                }
                view = {
                    "kind": "download",
                    "headline": "Case PDF ready",
                    "subtitle": f"Saved locally ({len(pdf_bytes):,} bytes).",
                    "filename": path.name,
                    "url": f"/api/downloads/{path.name}",
                    "summaryText": f"Downloaded PDF for case {case_id}.",
                    "meta": {},
                }
                download = {"filename": path.name, "url": f"/api/downloads/{path.name}"}
            elif body.functionId == "bulk":
                raw_text = str(inputs.get("requestsJson") or "").strip()
                if not raw_text:
                    raise ValueError("Paste a JSON object with a requests array.")
                try:
                    parsed = json.loads(raw_text)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Bulk JSON is not valid: {exc}") from exc
                requests = parsed.get("requests") if isinstance(parsed, dict) else parsed
                if not isinstance(requests, list) or not requests:
                    raise ValueError('Expected { "requests": [ ... ] } or a JSON array.')
                wire_request = _wire(method="POST", path="/bulk", body={"requests": requests})
                raw = client.bulk_upload(requests)
                view = formatters.format_bulk(raw)
            elif body.functionId == "usage":
                days = int(inputs.get("days") or 30)
                wire_request = _wire(method="GET", path="/usage", params={"days": days})
                wire_request["headers"].pop("Content-Type", None)
                raw = client.usage(days=days)
                view = formatters.format_usage(raw)
            else:
                raise HTTPException(400, f"Function {body.functionId} must be called via the upload endpoint.")

            wire_response = raw
            request_id = (view.get("meta") or {}).get("requestId")
            if not request_id and isinstance(raw, dict):
                request_id = raw.get("requestId")

    except LawDiverApiError as exc:
        ok = False
        view = formatters.format_error(exc)
        request_id = view.get("requestId")
        error_message = view.get("message")
        wire_error = {
            "httpStatus": exc.status,
            "payload": dict(exc.payload) if isinstance(exc.payload, dict) else exc.payload,
        }
        wire_response = wire_error.get("payload")
    except (ValueError, RuntimeError) as exc:
        ok = False
        view = formatters.format_error(exc)
        request_id = view.get("requestId")
        error_message = view.get("message")
        wire_error = {"message": str(exc), "stage": "local_validation_or_runtime"}
    except Exception as exc:  # noqa: BLE001
        ok = False
        view = formatters.format_error(exc)
        error_message = str(exc)
        wire_error = {"message": str(exc), "stage": "unexpected"}

    # scrub secrets from logged inputs
    safe_inputs = {k: v for k, v in inputs.items() if k.lower() not in {"api_key", "authorization"}}
    if "file" in safe_inputs:
        safe_inputs["file"] = "<uploaded>"

    machine = _machine_payload(wire_request, wire_response, error=wire_error)

    db.log_request(
        function_id=body.functionId,
        function_label=meta["label"],
        inputs=safe_inputs,
        request_id=request_id,
        ok=ok,
        summary=view.get("summaryText") or view.get("headline") or "",
        error_message=error_message,
        machine=machine,
        view=view,
    )

    return {
        "ok": ok,
        "view": view,
        "download": download,
        "requestId": request_id,
        "machine": machine,
    }


@app.post("/api/run/document")
async def run_document_cite_check(
    file: UploadFile = File(...),
    emails: str = Form(""),
    downloadReport: str = Form("true"),
) -> dict[str, Any]:
    meta = _fn_meta("document_cite_check")
    suffix = Path(file.filename or "brief.pdf").suffix or ".pdf"
    dest = DOWNLOADS / f"upload_{os.getpid()}_{Path(file.filename or 'brief').stem[:40]}{suffix}"
    content = await file.read()
    dest.write_bytes(content)

    email_list = [e.strip() for e in re.split(r"[,;]+", emails or "") if e.strip()]
    want_report = _bool(downloadReport)
    view: dict[str, Any]
    ok = True
    request_id: Optional[str] = None
    error_message: Optional[str] = None
    download: Optional[dict[str, str]] = None
    wire_request: Optional[dict[str, Any]] = None
    wire_response: Any = None
    wire_error: Any = None
    result: dict[str, Any] = {}

    form_fields: dict[str, Any] = {"file": file.filename or "brief.pdf"}
    if email_list:
        form_fields["delivery"] = "email_link"
        form_fields["emails"] = email_list
    wire_request = _wire(
        method="POST",
        path="/citecheck/document",
        body=form_fields,
        content_type="multipart/form-data",
        notes="Async job: POST upload, then GET /citecheck/jobs/:id until completed.",
    )

    try:
        with _client() as client:
            result = client.cite_check_document(
                dest,
                emails=email_list or None,
                delivery="email_link" if email_list else None,
                download_report=want_report,
                max_polls=90,
            )
            job = result.get("job") or {}
            started = result.get("started") or {}
            view = formatters.format_document_job(job, started=started)
            request_id = job.get("requestId") or started.get("requestId")
            wire_response = {
                "started": started,
                "finalJob": {k: v for k, v in job.items() if k != "citations"} | {
                    "citations": job.get("citations"),
                    "citationCount": len(job.get("citations") or []),
                },
                "reportDownloaded": bool(result.get("report")),
                "reportBytes": len(result["report"]) if result.get("report") else 0,
            }
            if want_report and result.get("report"):
                report_path = DOWNLOADS / f"report_{job.get('jobId', 'job')}.pdf"
                report_path.write_bytes(result["report"])
                view["reportDownload"] = {
                    "filename": report_path.name,
                    "url": f"/api/downloads/{report_path.name}",
                }
                download = view["reportDownload"]
    except LawDiverApiError as exc:
        ok = False
        view = formatters.format_error(exc)
        request_id = view.get("requestId")
        error_message = view.get("message")
        wire_error = {
            "httpStatus": exc.status,
            "payload": dict(exc.payload) if isinstance(exc.payload, dict) else exc.payload,
        }
        wire_response = wire_error.get("payload")
    except (ValueError, RuntimeError) as exc:
        ok = False
        view = formatters.format_error(exc)
        request_id = view.get("requestId")
        error_message = view.get("message")
        wire_error = {"message": str(exc), "stage": "local_validation_or_runtime"}
    except Exception as exc:  # noqa: BLE001
        ok = False
        view = formatters.format_error(exc)
        error_message = str(exc)
        wire_error = {"message": str(exc), "stage": "unexpected"}
    finally:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass

    machine = _machine_payload(wire_request, wire_response, error=wire_error)
    db.log_request(
        function_id="document_cite_check",
        function_label=meta["label"],
        inputs={"file": file.filename, "emails": email_list, "downloadReport": want_report},
        request_id=request_id,
        ok=ok,
        summary=view.get("summaryText") or view.get("headline") or "",
        error_message=error_message,
        machine=machine,
        view=view,
    )
    return {
        "ok": ok,
        "view": view,
        "download": download,
        "requestId": request_id,
        "machine": machine,
    }


@app.get("/api/downloads/{filename}")
def get_download(filename: str) -> Response:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    path = DOWNLOADS / filename
    if not path.is_file():
        raise HTTPException(404, "File not found")
    media = "application/pdf" if path.suffix.lower() == ".pdf" else "application/octet-stream"
    return FileResponse(path, media_type=media, filename=path.name)
