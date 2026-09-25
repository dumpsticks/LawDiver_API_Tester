import json
import urllib.request

body = json.dumps({"functionId": "discovery", "inputs": {}}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8765/api/run",
    data=body,
    headers={"Content-Type": "application/json"},
)
r = json.load(urllib.request.urlopen(req))
print("run ok", r["ok"], "has_machine", bool(r.get("machine")))
hist = json.load(urllib.request.urlopen("http://127.0.0.1:8765/api/history?limit=1"))
item = hist["items"][0]
print("hist hasMachine", item.get("hasMachine"), "hasView", item.get("hasView"), "id", item["id"])
detail = json.load(urllib.request.urlopen(f"http://127.0.0.1:8765/api/history/{item['id']}"))
print("detail machine keys", list((detail.get("machine") or {}).keys()))
print("detail view kind", (detail.get("view") or {}).get("kind"))
