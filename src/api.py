
import re
import requests
from urllib.parse import urlparse, parse_qs


class CivitaiAPI:
    BASE_URL = "https://civitai.com/api/v1"

    def __init__(self, api_key=None):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "CivitaiLoRADownloader/1.0"
        })

        if api_key:
            self.session.headers["Authorization"] = f"Bearer {api_key}"

    def _get(self, endpoint):
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"

        response = self.session.get(url, timeout=60)
        response.raise_for_status()

        return response.json()

    @staticmethod
    def parse_model_url(url):
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        model_match = re.search(
            r"/models/(\d+)",
            parsed.path
        )

        if not model_match:
            raise ValueError("Could not find a model ID in this URL.")

        model_id = int(model_match.group(1))

        version_id = None

        if "modelVersionId" in query:
            version_id = int(query["modelVersionId"][0])

        return model_id, version_id

    def search_models(
        self,
        query,
        cursor=None,
        limit=100,
        model_type="LORA",
        base_models=None,
        include_nsfw=True,
        supports_generation=False
    ):
        """Search Civitai's model index; callers may re-rank returned matches."""
        query = str(query or "").strip()
        if not query:
            raise ValueError("Enter a search term.")
        if len(query) > 200:
            raise ValueError("Search terms must be 200 characters or fewer.")

        # Keep Civitai's native text-search ranking: when "query" is present,
        # omitting "sort" lets its search engine rank by relevance. Never add
        # a default popularity/rating sort; secondary ranking stays local.
        params = {
            "query": query,
            "limit": max(1, min(int(limit), 100)),
        }
        if cursor not in (None, ""):
            params["cursor"] = str(cursor)
        if model_type and model_type != "All":
            if model_type not in ("LORA", "Checkpoint", "TextualInversion", "Controlnet"):
                raise ValueError("Unsupported model type.")
            params["types"] = model_type

        if isinstance(base_models, str):
            base_models = [part.strip() for part in base_models.split(",")]
        elif base_models is not None and not isinstance(base_models, (list, tuple)):
            raise ValueError("Base models must be text or a list of names.")

        if base_models:
            cleaned_base_models = [
                str(value).strip() for value in base_models
                if str(value).strip()
            ]
            if len(cleaned_base_models) > 20:
                raise ValueError("Choose no more than 20 base models.")
            if any(len(value) > 80 for value in cleaned_base_models):
                raise ValueError("Base model names must be 80 characters or fewer.")
            if cleaned_base_models:
                # Repeated query parameters are supported by the public API
                # for its string-array baseModels filter.
                params["baseModels"] = cleaned_base_models

        if include_nsfw:
            params["nsfw"] = "true"
        if supports_generation:
            params["supportsGeneration"] = "true"

        response = self.session.get(
            f"{self.BASE_URL}/models", params=params, timeout=60
        )
        response.raise_for_status()
        return response.json()

    def get_model(self, model_id):
        return self._get(f"models/{model_id}")

    def get_version(self, version_id):
        return self._get(f"model-versions/{version_id}")

    def get_all_versions(self, model_data):
        versions = model_data.get("modelVersions", [])

        complete_versions = []

        for version in versions:
            version_id = version.get("id")

            if not version_id:
                continue

            print(
                f"Retrieving version: "
                f"{version.get('name', version_id)}"
            )

            try:
                full_version = self.get_version(version_id)
                complete_versions.append(full_version)

            except requests.RequestException as error:
                print(
                    f"Could not retrieve version {version_id}: {error}"
                )

        return complete_versions

    def get_model_from_url(self, model_url):
        model_id, selected_version_id = self.parse_model_url(
            model_url
        )

        print(f"Model ID: {model_id}")

        model_data = self.get_model(model_id)

        print(f"Model name: {model_data.get('name', 'Unknown')}")
        print(f"Model type: {model_data.get('type', 'Unknown')}")

        versions = self.get_all_versions(model_data)

        return {
            "model": model_data,
            "versions": versions,
            "selected_version_id": selected_version_id
        }


if __name__ == "__main__":
    import json
    from pathlib import Path

    settings_path = Path("config/settings.json")

    if not settings_path.exists():
        raise FileNotFoundError(
            "config/settings.json was not found."
        )

    with settings_path.open("r", encoding="utf-8") as file:
        settings = json.load(file)

    api = CivitaiAPI(settings.get("api_key"))

    print("Civitai API module loaded successfully.")
    print("Ready to retrieve model information.")
