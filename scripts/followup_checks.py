"""Follow-up checks after rate-limit window."""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.lawdiver_client import LawDiverClient


def main() -> None:
    for q in ["Brown v. Board of Education", "Miranda v. Arizona", "Gideon v. Wainwright"]:
        t0 = time.perf_counter()
        try:
            with LawDiverClient(timeout=90) as c:
                r = c.retrieve(query=q)
            case = r.get("case") or {}
            name = case.get("caseName") or case.get("name")
            print(
                f"RETRIEVE OK {q!r}: status={r.get('status')} "
                f"ms={(time.perf_counter() - t0) * 1000:.0f} case={name}"
            )
        except Exception as e:
            print(f"RETRIEVE FAIL {q!r}: {e} ms={(time.perf_counter() - t0) * 1000:.0f}")

    print("--- app rate-limit message shape ---")
    body = json.dumps({"functionId": "usage", "inputs": {"days": 1}}).encode()
    for i in range(70):
        req = urllib.request.Request(
            "http://127.0.0.1:8765/api/run",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            d = json.loads(resp.read().decode())
        if not d.get("ok"):
            print("headline:", (d.get("view") or {}).get("headline"))
            print("message:", (d.get("view") or {}).get("message"))
            print("machine_error:", (d.get("machine") or {}).get("error"))
            break
    else:
        print("no rate limit in 70 usage calls via app")


if __name__ == "__main__":
    main()
