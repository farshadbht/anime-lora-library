import json
import os
import sys
import shutil
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

PROJECT_ROOT = Path(
    os.environ.get(
        "ANIME_LORA_HOME",
        Path(__file__).resolve().parent.parent
    )
).resolve()
SRC = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC))

from api import CivitaiAPI
from organizer import create_model_archive, safe_name
from downloader import download_version_assets
from offline_site import generate_offline_site
from generate_library import generate


DOWNLOADS = PROJECT_ROOT / "downloads"
SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.json"
LIBRARY_PATH = DOWNLOADS / "library.json"


def initialize_data():
    """Create missing application data without overwriting user files."""
    (PROJECT_ROOT / "config").mkdir(parents=True, exist_ok=True)
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "logs").mkdir(parents=True, exist_ok=True)

    if not LIBRARY_PATH.exists():
        LIBRARY_PATH.write_text(
            json.dumps({"anime": []}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    if not SETTINGS_PATH.exists():
        default_settings = {
            "api_key": "",
            "download_directory": "downloads",
            "browser": {"headless": False},
            "download": {
                "images": True,
                "model_files": True,
                "descriptions": True
            },
            "content_preferences": {"mature_content_enabled": False}
        }
        SETTINGS_PATH.write_text(
            json.dumps(default_settings, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    else:
        current_settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        preferences = current_settings.setdefault("content_preferences", {})
        preferences.setdefault("mature_content_enabled", False)
        SETTINGS_PATH.write_text(
            json.dumps(current_settings, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )


def mature_content_enabled(settings):
    preferences = settings.get("content_preferences") or {}
    return preferences.get("mature_content_enabled") is True


def update_content_preference(enabled, age_confirmed=False):
    if enabled is True and age_confirmed is not True:
        raise ValueError("You must confirm that you are 18 or older before enabling mature content.")
    settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    preferences = settings.setdefault("content_preferences", {})
    preferences["mature_content_enabled"] = enabled is True
    SETTINGS_PATH.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return {"success": True, "mature_content_enabled": preferences["mature_content_enabled"]}


def extract_character_name(model_name):
    """Extract the leading character name from a Civitai model title."""
    name = str(model_name or "Unknown Character").strip()
    name = name.lstrip("#").strip()

    separators = [" (", " - ", " | "]
    positions = [name.find(separator) for separator in separators]
    positions = [position for position in positions if position > 0]

    if positions:
        name = name[:min(positions)]

    return name.strip(" #-\\t") or "Unknown Character"



def add_character(url, anime_name):
    if not url or not anime_name:
        raise ValueError("Both the Civitai URL and anime title are required.")

    settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    library = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))

    # Missing settings retain the previous behavior: download/save everything.
    download_settings = settings.get("download") or {}
    download_options = {
        "images": bool(download_settings.get("images", True)),
        "model_files": bool(download_settings.get("model_files", True)),
        "descriptions": bool(download_settings.get("descriptions", True))
    }

    api = CivitaiAPI(
        settings.get("api_key"),
        mature_content=mature_content_enabled(settings)
    )

    print("\n" + "=" * 55)
    print("ADDING NEW CHARACTER")
    print("=" * 55)

    result = api.get_model_from_url(url)
    model = result["model"]
    versions = result["versions"]

    model_id = model.get("id")
    model_name = model.get("name", "Unknown Model")

    # Prevent adding a model already present in the library.
    for anime in library.get("anime", []):
        for character in anime.get("characters", []):
            existing_folder = DOWNLOADS / character["folder"]
            metadata_path = existing_folder / "Metadata.json"

            if metadata_path.exists():
                metadata = json.loads(
                    metadata_path.read_text(encoding="utf-8")
                )
                if metadata.get("id") == model_id:
                    raise ValueError(
                        f"{model_name} is already in the library "
                        f"under {anime['name']}."
                    )

    if not versions:
        raise ValueError("No model versions were returned by Civitai.")

    # All model archives belong to the selected application directory.
    download_directory = DOWNLOADS

    root = create_model_archive(
        model,
        versions,
        download_directory,
        save_descriptions=download_options["descriptions"]
    )

    all_results = []

    for version in versions:
        folder_name = (
            f"{safe_name(version.get('name', 'Version'))}"
            f" [{version.get('id')}]"
        )

        version_folder = root / "Versions" / folder_name

        results = download_version_assets(
            api,
            version,
            version_folder,
            download_options=download_options
        )
        all_results.append(results)

    # Generate the character's offline page, including its back button.
    character_page = generate_offline_site(root)

    # Find or create the anime section.
    anime_entry = next(
        (
            item for item in library.get("anime", [])
            if item["name"].strip().casefold() == anime_name.strip().casefold()
        ),
        None
    )

    if anime_entry is None:
        anime_entry = {
            "name": anime_name.strip(),
            "characters": []
        }
        library.setdefault("anime", []).append(anime_entry)

    relative_folder = root.relative_to(DOWNLOADS).as_posix()

    character_name = extract_character_name(model_name)

    anime_entry["characters"].append({
        "name": character_name,
        "folder": relative_folder
    })

    LIBRARY_PATH.write_text(
        json.dumps(library, indent=4, ensure_ascii=False),
        encoding="utf-8"
    )

    # Regenerate the main library page.
    generate()

    total_files = sum(len(item["files_downloaded"]) for item in all_results)
    total_images = sum(len(item["images_downloaded"]) for item in all_results)
    total_errors = sum(len(item["errors"]) for item in all_results)

    return {
        "success": True,
        "model": model_name,
        "anime": anime_entry["name"],
        "versions": len(versions),
        "files": total_files,
        "images": total_images,
        "errors": total_errors,
        "files_skipped": sum(item["files_skipped"] for item in all_results),
        "images_skipped": sum(item["images_skipped"] for item in all_results),
        "download_options": download_options,
        "character_page": str(character_page),
        "library_page": str(DOWNLOADS / "index.html")
    }



def search_civitai_models(
    query, cursor=None, model_type="LORA", filters=None
):
    """Return Civitai relevance-ranked matches using supported browse filters."""
    filters = filters if isinstance(filters, dict) else {}
    settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    mature_enabled = mature_content_enabled(settings)
    api = CivitaiAPI(settings.get("api_key"), mature_content=mature_enabled)
    payload = api.search_models(
        query=query,
        cursor=cursor,
        limit=100,
        model_type=model_type,
        base_models=filters.get("base_models"),
        include_nsfw=mature_enabled,
        supports_generation=filters.get("supports_generation") is True,
        tag=filters.get("tag"),
        username=filters.get("username"),
        from_platform=filters.get("from_platform") is True,
        early_access=filters.get("early_access") is True
    )

    items = []
    for model in payload.get("items", []):
        versions = model.get("modelVersions") or []
        latest = versions[0] if versions else {}
        images = latest.get("images") or []
        creator = model.get("creator") or {}
        stats = model.get("stats") or {}

        image_count = sum(
            len(version.get("images") or [])
            for version in versions
        )
        created_at = (
            model.get("createdAt")
            or (latest.get("publishedAt") if latest else None)
            or (latest.get("createdAt") if latest else None)
        )

        items.append({
            "id": model.get("id"),
            "name": model.get("name") or "Unknown model",
            "type": model.get("type") or "Unknown",
            "creator": creator.get("username") or "Unknown",
            "creatorUrl": f"https://{'civitai.red' if mature_enabled else 'civitai.com'}/user/{creator.get('username')}" if creator.get("username") else None,
            "baseModel": latest.get("baseModel") or "Base model unavailable",
            "downloads": int(stats.get("downloadCount") or 0),
            "likes": int(stats.get("thumbsUpCount") or 0),
            "buzz": int(stats.get("tippedAmountCount") or 0),
            "comments": int(stats.get("commentCount") or 0),
            "favorites": int(stats.get("collectedCount", stats.get("favoriteCount")) or 0),
            "imagesCount": image_count,
            "rating": stats.get("rating"),
            "ratingCount": int(stats.get("ratingCount") or 0),
            "createdAt": created_at,
            "url": f"https://{'civitai.red' if mature_enabled else 'civitai.com'}/models/{model.get('id')}",
            "preview": images[0].get("url") if images else None,
            "tags": model.get("tags") or [],
            "updatedAt": model.get("updatedAt")
        })

    metadata = payload.get("metadata") or {}
    return {
        "success": True,
        "items": items,
        "nextCursor": metadata.get("nextCursor"),
        "totalItems": metadata.get("totalItems"),
        "matureContentEnabled": mature_enabled
    }



def remove_character(anime_name, folder_name):
    """Remove a character from the library without deleting its archive."""
    if not anime_name or not folder_name:
        raise ValueError("Select an anime and a character.")

    library = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))

    anime_entry = next(
        (
            item for item in library.get("anime", [])
            if item["name"].strip().casefold() == anime_name.strip().casefold()
        ),
        None
    )

    if anime_entry is None:
        raise ValueError("Anime category not found.")

    characters = anime_entry.get("characters", [])

    character = next(
        (item for item in characters if item.get("folder") == folder_name),
        None
    )

    if character is None:
        raise ValueError("Character not found in this anime category.")

    character_name = character["name"]
    characters.remove(character)

    LIBRARY_PATH.write_text(
        json.dumps(library, indent=4, ensure_ascii=False),
        encoding="utf-8"
    )

    generate()

    return {
        "success": True,
        "character": character_name,
        "anime": anime_entry["name"],
        "archive_preserved": True
    }




def move_character(source_anime, target_anime, folder_name):
    """Move a character between anime categories without touching its archive."""
    if not source_anime or not target_anime or not folder_name:
        raise ValueError("Select the character, its current anime, and destination anime.")

    if source_anime.strip().casefold() == target_anime.strip().casefold():
        raise ValueError("The destination must be a different anime.")

    library = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    categories = library.get("anime", [])

    source = next(
        (item for item in categories
         if item["name"].strip().casefold() == source_anime.strip().casefold()),
        None
    )
    destination = next(
        (item for item in categories
         if item["name"].strip().casefold() == target_anime.strip().casefold()),
        None
    )

    if source is None:
        raise ValueError("The character's current anime category was not found.")
    if destination is None:
        raise ValueError("The destination anime category was not found.")

    character = next(
        (item for item in source.get("characters", [])
         if item.get("folder") == folder_name),
        None
    )

    if character is None:
        raise ValueError("Character not found in the selected anime.")

    if any(
        item.get("folder") == folder_name
        for item in destination.get("characters", [])
    ):
        raise ValueError("This character is already in the destination anime.")

    source["characters"].remove(character)
    destination.setdefault("characters", []).append(character)

    LIBRARY_PATH.write_text(
        json.dumps(library, indent=4, ensure_ascii=False),
        encoding="utf-8"
    )

    generate()

    return {
        "success": True,
        "character": character["name"],
        "source_anime": source["name"],
        "target_anime": destination["name"],
        "archive_preserved": True
    }


def validate_archive_folder(folder_name):
    """Accept only a direct, valid character archive inside downloads."""
    if not isinstance(folder_name, str) or not folder_name.strip():
        raise ValueError("Select an archive.")

    if folder_name in (".", "..") or "/" in folder_name or "\\" in folder_name:
        raise ValueError("Invalid archive folder name.")

    downloads_root = DOWNLOADS.resolve()
    target = (downloads_root / folder_name).resolve()

    if target.parent != downloads_root or target == downloads_root:
        raise ValueError("The selected folder is outside the archive directory.")

    if not target.is_dir():
        raise ValueError("Archive folder does not exist.")

    if not (target / "Metadata.json").is_file():
        raise ValueError("This folder is not a recognized character archive.")

    if not (target / "ArchiveIndex.json").is_file():
        raise ValueError("Archive index is missing.")

    return target


def restore_character(folder_name, anime_name):
    """Restore an existing archive to an anime category without downloading."""
    if not anime_name or not anime_name.strip():
        raise ValueError("Select an anime category.")

    target = validate_archive_folder(folder_name)
    library = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))

    anime_entry = next(
        (
            item for item in library.get("anime", [])
            if item["name"].strip().casefold() == anime_name.strip().casefold()
        ),
        None
    )

    if anime_entry is None:
        raise ValueError("Anime category not found.")

    for category in library.get("anime", []):
        if any(
            item.get("folder") == folder_name
            for item in category.get("characters", [])
        ):
            raise ValueError("This character is already in the library.")

    metadata = json.loads(
        (target / "Metadata.json").read_text(encoding="utf-8")
    )
    raw_name = str(metadata.get("name") or target.name)
    model_name = raw_name.split("/", 1)[0].strip()
    character_name = extract_character_name(model_name)

    anime_entry.setdefault("characters", []).append({
        "name": character_name,
        "folder": folder_name
    })

    LIBRARY_PATH.write_text(
        json.dumps(library, indent=4, ensure_ascii=False),
        encoding="utf-8"
    )
    generate()

    return {
        "success": True,
        "character": character_name,
        "anime": anime_entry["name"]
    }


def delete_character_forever(folder_name):
    """Permanently delete one validated archive and remove library references."""
    target = validate_archive_folder(folder_name)

    metadata = json.loads(
        (target / "Metadata.json").read_text(encoding="utf-8")
    )
    raw_name = str(metadata.get("name") or target.name)
    model_name = raw_name.split("/", 1)[0].strip()
    character_name = extract_character_name(model_name)

    library = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))

    # Delete only after validation. Never accept a path supplied by the browser.
    shutil.rmtree(target)

    for category in library.get("anime", []):
        category["characters"] = [
            item for item in category.get("characters", [])
            if item.get("folder") != folder_name
        ]

    LIBRARY_PATH.write_text(
        json.dumps(library, indent=4, ensure_ascii=False),
        encoding="utf-8"
    )
    generate()

    return {
        "success": True,
        "character": character_name,
        "permanently_deleted": True
    }



class LibraryHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()"
        )
        super().end_headers()

    def _is_allowed_static_path(self):
        """Allow static requests only inside the downloads directory."""
        request_path = urlparse(self.path).path

        if not (
            request_path == "/downloads"
            or request_path.startswith("/downloads/")
        ):
            return False

        try:
            requested_file = Path(
                super().translate_path(self.path)
            ).resolve()
            requested_file.relative_to(DOWNLOADS.resolve())
            return True
        except (OSError, ValueError):
            return False

    def do_GET(self):
        if urlparse(self.path).path == "/app-settings":
            settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            self.send_json(200, {
                "success": True,
                "mature_content_enabled": mature_content_enabled(settings)
            })
            return
        if not self._is_allowed_static_path():
            self.send_error(404, "File not found.")
            return
        super().do_GET()

    def do_HEAD(self):
        if not self._is_allowed_static_path():
            self.send_error(404, "File not found.")
            return
        super().do_HEAD()

    def do_POST(self):
        route = urlparse(self.path).path

        # Reject requests originating from other websites.
        origin = self.headers.get("Origin")
        if origin != "http://127.0.0.1:8765":
            self.send_json(403, {
                "success": False,
                "error": "Forbidden: invalid request origin."
            })
            return

        if route not in (
            "/add-character",
            "/search-models",
            "/content-preference",
            "/remove-character",
            "/restore-character",
            "/delete-character",
            "/move-character"
        ):
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 10000:
                raise ValueError("Request is too large.")

            data = json.loads(self.rfile.read(length).decode("utf-8"))

            if route == "/add-character":
                result = add_character(
                    data.get("url", "").strip(),
                    data.get("anime", "").strip()
                )
            elif route == "/content-preference":
                result = update_content_preference(
                    data.get("enabled") is True,
                    data.get("age_confirmed") is True
                )
            elif route == "/search-models":
                result = search_civitai_models(
                    data.get("query", "").strip(),
                    data.get("cursor"),
                    data.get("model_type", "LORA"),
                    data.get("filters")
                )
            elif route == "/remove-character":
                result = remove_character(
                    data.get("anime", "").strip(),
                    data.get("folder", "").strip()
                )
            elif route == "/restore-character":
                result = restore_character(
                    data.get("folder", ""),
                    data.get("anime", "")
                )
            elif route == "/delete-character":
                result = delete_character_forever(
                    data.get("folder", "")
                )
            else:
                result = move_character(
                    data.get("source_anime", "").strip(),
                    data.get("target_anime", "").strip(),
                    data.get("folder", "").strip()
                )

            self.send_json(200, result)

        except Exception as error:
            print(f"\nERROR: {error}")
            self.send_json(400, {
                "success": False,
                "error": str(error)
            })

    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    address = ("127.0.0.1", 8765)

    server = ThreadingHTTPServer(address, LibraryHandler)

    print("\n======================================")
    print("       ANIME LIBRARY MANAGER")
    print("======================================")
    print("Open this address in your browser:")
    print("http://127.0.0.1:8765/downloads/index.html")
    print("\nKeep this PowerShell window open while using it.")
    print("Press Ctrl+C to stop the server.")
    print("======================================\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping library manager...")
    finally:
        server.server_close()
