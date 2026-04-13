import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/ui_v1.json"
with open(path) as f:
    d = json.load(f)

print("App:", d.get("current_app", "?"))
print("Screen:", d.get("screen_width"), "x", d.get("screen_height"))
print("Elements:", d.get("total_count"), "| Clickable:", d.get("clickable_count"))
print()

for e in d.get("elements", []):
    txt = (e.get("text") or "").strip()
    desc = (e.get("content_description") or e.get("description") or "").strip()
    cls = (e.get("class_name") or e.get("class") or "").split(".")[-1]
    click = e.get("clickable") or e.get("is_clickable", False)
    b = e.get("bounds") or {}
    cx = b.get("centerX") or b.get("center_x") or 0
    cy = b.get("centerY") or b.get("center_y") or 0
    if txt or desc:
        print(f"  [{cls}] text={repr(txt)} desc={repr(desc)} click={click} center=({cx},{cy})")
