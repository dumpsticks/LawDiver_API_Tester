"""Stress-only follow-up after happy-path suite."""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.lawdiver_client import LawDiverApiError, LawDiverClient  # noqa: E402

BASE = "http://127.0.0.1:8765"
OUT = ROOT / "data" / "stress_report.json"
rows: list[dict] = []


def rec(name: str, ok: bool, detail: str, **extra):
    rows.append({"name": name, "ok": ok, "detail": detail, **extra})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def main():
    # Sequential searches
    seq_times, seq_errors, rate_limited = [], [], 0
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
    rec(
        "sequential_25_searches",
        rate_limited == 0 and len(seq_errors) == 0,
        f"avg={sum(seq_times)/len(seq_times):.0f}ms p50={sorted(seq_times)[len(seq_times)//2]:.0f} "
        f"max={max(seq_times):.0f} errors={seq_errors} rl={rate_limited}",
        times=seq_times,
    )

    # Parallel cite checks
    par_times, par_errors, par_rl = [], [], 0

    def one(i: int):
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
        for f in as_completed([pool.submit(one, i) for i in range(20)]):
            ms, err = f.result()
            par_times.append(ms)
            if err:
                par_errors.append(err)
                if "rate_limited" in err or ":429" in err:
                    par_rl += 1
    rec(
        "parallel_20_citechecks_10_workers",
        True,
        f"avg={sum(par_times)/len(par_times):.0f}ms max={max(par_times):.0f} "
        f"errors={len(par_errors)} rl={par_rl} sample={par_errors[:5]}",
        times=par_times,
        errors=par_errors,
    )

    # Harder parallel searches
    hard_times, hard_errors, hard_rl = [], [], 0

    def hard(i: int):
        t0 = time.perf_counter()
        try:
            with LawDiverClient(timeout=60.0) as client:
                client.search(
                    query=f"contract damages {i}",
                    jurisdiction={"type": "all_federal"},
                    limit=5,
                    searchType="semantic",
                )
            return (time.perf_counter() - t0) * 1000, None
        except LawDiverApiError as e:
            return (time.perf_counter() - t0) * 1000, f"{e.code}:{e.status}"
        except Exception as e:
            return (time.perf_counter() - t0) * 1000, str(e)

    with ThreadPoolExecutor(max_workers=15) as pool:
        for f in as_completed([pool.submit(hard, i) for i in range(30)]):
            ms, err = f.result()
            hard_times.append(ms)
            if err:
                hard_errors.append(err)
                if "rate_limited" in err or ":429" in err:
                    hard_rl += 1
    rec(
        "parallel_30_semantic_searches_15_workers",
        True,
        f"avg={sum(hard_times)/len(hard_times):.0f}ms max={max(hard_times):.0f} "
        f"errors={len(hard_errors)} rl={hard_rl} sample={hard_errors[:8]}",
        times=hard_times,
        errors=hard_errors,
    )

    # Rate limit ceiling with cheap usage calls
    ceiling, hit_rl = [], False
    t0 = time.perf_counter()
    with LawDiverClient(timeout=30.0) as client:
        for i in range(80):
            try:
                client.usage(days=1)
            except LawDiverApiError as e:
                ceiling.append(f"{i}:{e.code}:{e.status}")
                if e.status == 429 or e.code == "rate_limited":
                    hit_rl = True
                    break
            except Exception as e:
                ceiling.append(f"{i}:{e}")
                break
    rec(
        "rate_limit_ceiling_usage",
        True,
        f"hit_rl={hit_rl} after {ceiling[-1] if ceiling else 'no errors'} "
        f"elapsed={(time.perf_counter()-t0)*1000:.0f}ms calls_attempted~{80}",
        errors=ceiling,
    )

    # App proxy burst
    app_err, app_ms = [], []
    for _ in range(15):
        body = json.dumps({"functionId": "resolve", "inputs": {"query": "410 U.S. 113"}}).encode()
        req = urllib.request.Request(
            f"{BASE}/api/run", data=body, headers={"Content-Type": "application/json"}
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
            app_ms.append((time.perf_counter() - t0) * 1000)
            if not data.get("ok"):
                app_err.append((data.get("view") or {}).get("message"))
        except Exception as e:
            app_ms.append((time.perf_counter() - t0) * 1000)
            app_err.append(str(e))
    rec(
        "app_proxy_15_resolves",
        len(app_err) == 0,
        f"avg={sum(app_ms)/len(app_ms):.0f}ms max={max(app_ms):.0f} errors={app_err[:3]}",
    )

    # Retry retrieve that 504'd
    for q in ["Brown v. Board of Education", "410 U.S. 113", "Miranda v. Arizona"]:
        t0 = time.perf_counter()
        try:
            with LawDiverClient(timeout=90.0) as client:
                r = client.retrieve(query=q)
            rec(
                f"retrieve_retry::{q}",
                True,
                f"status={r.get('status')} ms={(time.perf_counter()-t0)*1000:.0f}",
            )
        except Exception as e:
            rec(f"retrieve_retry::{q}", False, f"{e} ms={(time.perf_counter()-t0)*1000:.0f}")

    OUT.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
