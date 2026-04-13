import urllib.request, base64, json

# Try /api/v1/device/screenshot first, then /api/v1/debug/screenshot
urls = [
    "http://127.0.0.1:8000/api/v1/device/screenshot",
    "http://127.0.0.1:8000/api/v1/debug/screenshot",
]

for url in urls:
    try:
        resp = urllib.request.urlopen(url)
        raw = resp.read()
        content_type = resp.headers.get("Content-Type", "")
        print(f"URL: {url}  CT: {content_type}  len={len(raw)}")
        # If JSON, parse it
        if "json" in content_type:
            data = json.loads(raw)
            print("Keys:", list(data.keys()))
            sc = data.get("screenshot", data.get("image", ""))
            if sc:
                with open("current_screen.jpg", "wb") as f:
                    f.write(base64.b64decode(sc))
                print("Saved from JSON field")
                break
        elif raw[:2] == b'\xff\xd8':  # JPEG magic bytes
            with open("current_screen.jpg", "wb") as f:
                f.write(raw)
            print("Saved raw JPEG")
            break
        else:
            print("Raw prefix:", raw[:100])
    except Exception as e:
        print(f"  Error: {e}")
