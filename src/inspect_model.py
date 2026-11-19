
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from api import CivitaiAPI

with open("config/settings.json", encoding="utf-8") as f:
    settings = json.load(f)

api = CivitaiAPI(settings["api_key"])

url = "https://civitai.red/models/2780996/darkness-konosuba?modelVersionId=3132064"
result = api.get_model_from_url(url)

model = result["model"]

print("\n========== CREATOR ==========")
print(json.dumps(model.get("creator"), indent=2, ensure_ascii=False))

print("\n========== MODEL STATISTICS ==========")
print(json.dumps(model.get("stats"), indent=2, ensure_ascii=False))

print("\n========== MODEL DESCRIPTION ==========")
print(str(model.get("description", ""))[:2000])

for version in result["versions"]:
    print("\n========== VERSION DESCRIPTION ==========")
    print(str(version.get("description", ""))[:2000])

    for index, img in enumerate(version.get("images", []), 1):
        meta = img.get("meta") or {}

        print(f"\n========== IMAGE {index} METADATA ==========")
        print("Metadata available:", bool(meta))
        print("Metadata fields:", list(meta.keys()))

        print(json.dumps(
            meta,
            indent=2,
            ensure_ascii=False
        )[:4000])
