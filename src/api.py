
import json
import re
import requests
from urllib.parse import urlparse, parse_qs


class CivitaiAPI:
    BASE_URL = "https://civitai.com/api/v1"
    MATURE_BASE_URL = "https://civitai.red/api/v1"

    def __init__(self, api_key=None, mature_content=False):
        self.base_url = self.MATURE_BASE_URL if mature_content is True else self.BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "CivitaiLoRADownloader/1.0"
        })

        if api_key:
            self.session.headers["Authorization"] = f"Bearer {api_key}"

    def _get(self, endpoint):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        response = self.session.get(url, timeout=60)
        response.raise_for_status()

        return response.json()

    @staticmethod
    def parse_model_url(url):
        parsed = urlparse(str(url or "").strip())
        query = parse_qs(parsed.query)

        if parsed.scheme.lower() != "https":
            raise ValueError("Use a secure HTTPS Civitai model URL.")

        hostname = (parsed.hostname or "").lower()
        if hostname not in ("civitai.com", "www.civitai.com", "civitai.red", "www.civitai.red"):
            raise ValueError("The URL must belong to civitai.com or civitai.red.")

        model_match = re.search(
            r"/models/(\d+)(?:/|$)",
            parsed.path
        )

        if not model_match:
            raise ValueError("Could not find a model ID in this URL.")

        model_id = int(model_match.group(1))

        version_id = None

        if "modelVersionId" in query:
            try:
                version_id = int(query["modelVersionId"][0])
            except (TypeError, ValueError):
                raise ValueError("The modelVersionId in this URL is invalid.")

        return model_id, version_id

    def search_models(
        self,
        query,
        cursor=None,
        limit=100,
        model_type="LORA",
        base_models=None,
        include_nsfw=False,
        supports_generation=False,
        tag=None,
        username=None,
        from_platform=False,
        early_access=False
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

        for filter_name, filter_value in (("tag", tag), ("username", username)):
            if filter_value is not None:
                filter_value = str(filter_value).strip()
                if len(filter_value) > 100:
                    raise ValueError(
                        f"{filter_name.capitalize()} filter must be 100 characters or fewer."
                    )
                if filter_value:
                    params[filter_name] = filter_value

        if from_platform:
            params["fromPlatform"] = "true"
        if early_access:
            params["earlyAccess"] = "true"

        response = self.session.get(
            f"{self.base_url}/models", params=params, timeout=60
        )
        response.raise_for_status()
        return response.json()

    def search_site_models(
        self,
        query,
        offset=0,
        limit=100,
        model_type="LORA",
        base_models=None,
        supports_generation=False,
        tag=None,
        username=None
    ):
        """
        Search through Civitai's own website-search route.

        This is the same models_v9 Meilisearch index used by Civitai's model
        search UI. The site proxy applies its own viewer, privacy, region and
        browsing-level rules. Do not send the user's personal API key here.
        """
        query = str(query or "").strip()
        if not query:
            raise ValueError("Enter a search term.")
        if len(query) > 200:
            raise ValueError("Search terms must be 200 characters or fewer.")

        try:
            offset = int(offset or 0)
        except (TypeError, ValueError):
            raise ValueError("The search cursor is invalid.")
        if offset < 0 or offset > 1000:
            raise ValueError("The search cursor is outside Civitai's search window.")

        limit = max(1, min(int(limit), 100))
        if model_type and model_type != "All":
            if model_type not in ("LORA", "Checkpoint", "TextualInversion", "Controlnet"):
                raise ValueError("Unsupported model type.")

        def quoted(value):
            return json.dumps(str(value), ensure_ascii=False)

        filters = []
        if model_type and model_type != "All":
            filters.append(f"type = {quoted(model_type)}")

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
                values = ", ".join(quoted(value) for value in cleaned_base_models)
                filters.append(f"versions.baseModel IN [{values}]")

        if supports_generation:
            filters.append("canGenerate = true")

        for field, value in (("tags.name", tag), ("user.username", username)):
            if value is not None:
                value = str(value).strip()
                if len(value) > 100:
                    raise ValueError("Tag and creator filters must be 100 characters or fewer.")
                if value:
                    filters.append(f"{field} = {quoted(value)}")

        payload = {
            "q": query,
            "limit": limit,
            "offset": offset
        }
        if filters:
            payload["filter"] = filters

        site_root = self.base_url.rsplit("/api/v1", 1)[0].rstrip("/")
        search_url = (
            f"{site_root}/api/search/indexes/models_v9/search"
        )

        # The site-search route is anonymous-capable. Keep the account's
        # personal Civitai API key out of this separate website-search request.
        search_session = requests.Session()
        search_session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "CivitaiLoRADownloader/1.0",
            "Origin": site_root,
            "Referer": f"{site_root}/search/models"
        })
        try:
            response = search_session.post(
                search_url,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
        finally:
            search_session.close()

        if not isinstance(result, dict) or not isinstance(result.get("hits"), list):
            raise RuntimeError("Civitai returned an unexpected website-search response.")
        return result

    @staticmethod
    def _image_asset_key(url):
        """Normalize resized Civitai CDN URLs to their underlying asset ID."""
        value = str(url or "")
        match = re.search(
            r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
            value,
            re.IGNORECASE
        )
        if match:
            return match.group(1).lower()
        return urlparse(value).path

    def get_version_images(
        self, version_id, expected_image_urls=None, limit=200, max_pages=5
    ):
        """
        Find image IDs for the version's own preview images.

        The public images endpoint can also return community generations using
        this version, so only records matching the version preview URLs are kept.
        """
        expected_keys = {
            self._image_asset_key(url)
            for url in (expected_image_urls or [])
            if url
        }
        if not expected_keys:
            return []

        images = []
        found_keys = set()
        seen_ids = set()
        cursor = None
        seen_cursors = set()

        for _ in range(max_pages):
            params = {
                "modelVersionId": int(version_id),
                "limit": max(1, min(int(limit), 200)),
                "withMeta": "true"
            }
            if cursor:
                params["cursor"] = cursor

            response = self.session.get(
                f"{self.base_url}/images",
                params=params,
                timeout=60
            )
            response.raise_for_status()
            payload = response.json()

            for item in payload.get("items", []):
                asset_key = self._image_asset_key(item.get("url"))
                if asset_key not in expected_keys:
                    continue

                image_id = item.get("id")
                if image_id is not None and image_id in seen_ids:
                    continue
                if image_id is not None:
                    seen_ids.add(image_id)
                found_keys.add(asset_key)

                # Deliberately omit reaction statistics; they are not part
                # of this archive's requested image metadata.
                images.append({
                    key: item[key]
                    for key in (
                        "id", "url", "hash", "width", "height", "nsfw",
                        "nsfwLevel", "createdAt", "postId", "meta",
                        "username", "modelVersionIds", "browsingLevel"
                    )
                    if key in item
                })

            if expected_keys.issubset(found_keys):
                break

            metadata = payload.get("metadata") or {}
            next_cursor = metadata.get("nextCursor")
            if not next_cursor or next_cursor in seen_cursors:
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        return images

    def get_model(self, model_id):
        return self._get(f"models/{model_id}")

    def get_version(self, version_id):
        return self._get(f"model-versions/{version_id}")

    def get_all_versions(self, model_data):
        versions = model_data.get("modelVersions", [])

        complete_versions = []
        failures = []

        for version in versions:
            version_id = version.get("id")

            if not version_id:
                failures.append("A model version entry did not contain an ID.")
                continue

            print(
                f"Retrieving version: "
                f"{version.get('name', version_id)}"
            )

            try:
                full_version = self.get_version(version_id)
                returned_id = full_version.get("id")
                returned_model_id = full_version.get("modelId")
                if returned_id != version_id:
                    raise ValueError(
                        f"Civitai returned version {returned_id} when {version_id} was requested."
                    )
                if returned_model_id is not None and returned_model_id != model_data.get("id"):
                    raise ValueError(
                        f"Version {version_id} belongs to a different model."
                    )
                complete_versions.append(full_version)

            except requests.RequestException as error:
                message = f"Version {version_id}: {error}"
                failures.append(message)
                print(f"ERROR: Could not retrieve {message}")

        if failures:
            details = "\n".join(failures)
            raise RuntimeError(
                "The archive was not started because Civitai did not return "
                "every model version successfully:\n" + details
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

        version_ids = {version.get("id") for version in versions}
        if selected_version_id is not None and selected_version_id not in version_ids:
            raise ValueError(
                f"Version {selected_version_id} is not part of this model, "
                "or Civitai no longer makes it available."
            )

        gallery_images_by_version = {}
        gallery_image_errors = {}
        for version in versions:
            version_id = version.get("id")
            expected_urls = [
                image.get("url")
                for image in version.get("images", [])
                if isinstance(image, dict) and image.get("url")
            ]
            try:
                found_images = self.get_version_images(
                    version_id,
                    expected_image_urls=expected_urls
                )
                gallery_images_by_version[str(version_id)] = found_images

                expected_keys = {
                    self._image_asset_key(url) for url in expected_urls
                }
                found_keys = {
                    self._image_asset_key(item.get("url"))
                    for item in found_images if item.get("url")
                }
                missing_count = len(expected_keys - found_keys)
                if missing_count:
                    gallery_image_errors[str(version_id)] = (
                        f"Image IDs were unavailable for {missing_count} of "
                        f"{len(expected_keys)} preview images."
                    )
            except requests.RequestException as error:
                gallery_images_by_version[str(version_id)] = []
                gallery_image_errors[str(version_id)] = str(error)

        return {
            "model": model_data,
            "versions": versions,
            "selected_version_id": selected_version_id,
            "all_versions_included": True,
            "gallery_images_by_version": gallery_images_by_version,
            "gallery_image_errors": gallery_image_errors
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
