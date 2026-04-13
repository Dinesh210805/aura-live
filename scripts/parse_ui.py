import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/ui_snapshot.json"
with open(path) as f:
    data = json.load(f)

print("Package:", data.get("package_name", "unknown"))
print("Activity:", data.get("activity_name", "unknown"))
elems = data.get("ui_elements", [])
print("Elements:", len(elems))
print()
for e in elems[:40]:
    t = (e.get("text") or "").strip()
    desc = (e.get("content_description") or "").strip()
    cls = (e.get("class_name") or "").split(".")[-1]
    clickable = e.get("clickable", False)
    b = e.get("bounds") or {}
    cx = b.get("centerX", 0)
    cy = b.get("centerY", 0)
    if t or desc:
        print(f"  [{cls}] text={repr(t)} desc={repr(desc)} click={clickable} center=({cx},{cy})")
