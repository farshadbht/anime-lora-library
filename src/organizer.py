import json
import re
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup


def safe_name(name, max_length=100):
    """Convert a model/version name into a safe Windows folder name."""
    name = re.sub(r'[<>:"/\\|?*]', "_", str(name))
    name = re.sub(r"\s+", " ", name).strip()
    name = name.rstrip(". ")
    return (name or "Unnamed")[:max_length]


def save_json(path, data):
    """Save data as readable UTF-8 JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def save_description(folder, html):
    """Save the original HTML description and a plain-text copy."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    html = html or ""
    (folder / "Description.html").write_text(html, encoding="utf-8")

    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style"]):
        element.decompose()

    text = soup.get_text(separator="\n", strip=True)
    (folder / "Description.txt").write_text(text, encoding="utf-8")


def _available_fields(data, fields):
    """Return requested fields that are actually present in an API response."""
    return {
        field: data[field]
        for field in fields
        if field in data and data[field] is not None
    }


def _creator_summary(model_data):
    creator = model_data.get("creator") or {}
    if not isinstance(creator, dict):
        return creator
    return _available_fields(
        creator,
        ("username", "image", "id", "url")
    )


def _model_summary(model_data):
    """Create a convenient summary without discarding the complete API response."""
    fields = (
        "id", "name", "type", "nsfw", "nsfwLevel", "description",
        "tags", "modelVersions", "mode", "allowNoCredit",
        "allowCommercialUse", "allowDerivatives", "allowDifferentLicenses",
        "license", "createdAt", "updatedAt", "publishedAt",
        "downloadCount", "favoriteCount", "thumbsUpCount",
        "thumbsDownCount", "commentCount", "stats"
    )
    summary = _available_fields(model_data, fields)
    summary["creator"] = _creator_summary(model_data)
    return summary


def _file_summary(model_file):
    """Keep useful file details while retaining the raw response elsewhere."""
    summary = _available_fields(
        model_file,
        (
            "name", "type", "sizeKB", "pickleScanResult",
            "pickleScanMessage", "virusScanResult", "hashes",
            "metadata", "primary", "downloadUrl"
        )
    )
    return summary


def _version_summary(version):
    fields = (
        "id", "modelId", "name", "description", "createdAt",
        "updatedAt", "publishedAt", "baseModel", "baseModelType",
        "trainedWords", "trainingParams", "earlyAccessTimeFrame",
        "availability", "nsfwLevel", "stats"
    )
    summary = _available_fields(version, fields)
    summary["files"] = [
        _file_summary(item)
        for item in version.get("files", [])
        if isinstance(item, dict)
    ]
    summary["image_count"] = len(version.get("images", []))
    return summary


def _write_trigger_words(version_folder, version):
    """Write trained words in a convenient text format when provided by Civitai."""
    words = version.get("trainedWords") or []
    if isinstance(words, str):
        normalized = [words.strip()] if words.strip() else []
    elif isinstance(words, list):
        normalized = []
        for item in words:
            if isinstance(item, str):
                value = item.strip()
            elif isinstance(item, dict):
                value = str(
                    item.get("word")
                    or item.get("text")
                    or item.get("name")
                    or ""
                ).strip()
            else:
                value = str(item).strip()
            if value and value not in normalized:
                normalized.append(value)
    else:
        normalized = []

    if normalized:
        (Path(version_folder) / "TriggerWords.txt").write_text(
            "\n".join(normalized) + "\n",
            encoding="utf-8"
        )


def save_download_report(root, version_results, download_options, selected_version_id=None):
    """Persist the outcome of every version's asset download in the archive."""
    records = []
    for item in version_results:
        records.append({
            "version_id": item.get("version_id"),
            "version_name": item.get("version_name"),
            "files_downloaded": item.get("files_downloaded", []),
            "images_downloaded": item.get("images_downloaded", []),
            "files_skipped": item.get("files_skipped", 0),
            "images_skipped": item.get("images_skipped", 0),
            "errors": item.get("errors", [])
        })

    errors = [error for item in records for error in item["errors"]]
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "download_options": download_options,
        "selected_version_id_from_url": selected_version_id,
        "all_model_versions_included": True,
        "version_count": len(records),
        "files_downloaded": sum(len(item["files_downloaded"]) for item in records),
        "images_downloaded": sum(len(item["images_downloaded"]) for item in records),
        "files_skipped": sum(item["files_skipped"] for item in records),
        "images_skipped": sum(item["images_skipped"] for item in records),
        "error_count": len(errors),
        "status": "completed_with_errors" if errors else "completed",
        "versions": records
    }
    path = Path(root) / "DownloadReport.json"
    save_json(path, report)
    return path


def create_model_archive(model_data, versions, download_directory, save_descriptions=True, page_metadata=None):
    """Create the complete directory structure and useful metadata summaries."""
    model_name = safe_name(model_data.get("name", "Unnamed Model"))
    download_root = Path(download_directory)
    root = download_root / model_name
    model_id = model_data.get("id")

    if root.exists():
        existing_metadata_path = root / "Metadata.json"
        existing_model_id = None
        if existing_metadata_path.is_file():
            try:
                existing_model_id = json.loads(
                    existing_metadata_path.read_text(encoding="utf-8")
                ).get("id")
            except (OSError, json.JSONDecodeError):
                existing_model_id = None

        if existing_model_id != model_id:
            suffix = f" [{model_id}]" if model_id is not None else " [Civitai model]"
            root = download_root / f"{model_name}{suffix}"

            if root.exists():
                collision_metadata = root / "Metadata.json"
                collision_id = None
                if collision_metadata.is_file():
                    try:
                        collision_id = json.loads(
                            collision_metadata.read_text(encoding="utf-8")
                        ).get("id")
                    except (OSError, json.JSONDecodeError):
                        collision_id = None
                if collision_id != model_id:
                    raise FileExistsError(
                        f"Cannot safely choose an archive folder for model "
                        f"{model_id}; {root} already exists."
                    )

    root.mkdir(parents=True, exist_ok=True)

    # Preserve the complete, unmodified Civitai model response.
    save_json(root / "Metadata.json", model_data)
    save_json(root / "ModelInfo.json", _model_summary(model_data))
    if isinstance(page_metadata, dict):
        save_json(root / "WebpageMetadata.json", page_metadata)

    if save_descriptions:
        save_description(
            root / "Description",
            model_data.get("description", "")
        )

    version_records = []

    for version in versions:
        version_id = version.get("id")
        version_name = safe_name(version.get("name", "Unnamed Version"))
        version_folder_name = f"{version_name} [{version_id}]"
        version_folder = root / "Versions" / version_folder_name

        images_folder = version_folder / "Images"
        image_metadata_folder = version_folder / "Image_Metadata"
        files_folder = version_folder / "Files"

        images_folder.mkdir(parents=True, exist_ok=True)
        image_metadata_folder.mkdir(parents=True, exist_ok=True)
        files_folder.mkdir(parents=True, exist_ok=True)

        # Preserve the complete, unmodified Civitai version response.
        save_json(version_folder / "VersionMetadata.json", version)
        save_json(
            version_folder / "VersionInfo.json",
            _version_summary(version)
        )

        if save_descriptions:
            save_description(
                version_folder / "Description",
                version.get("description") or ""
            )
        _write_trigger_words(version_folder, version)

        # Save a separate manifest of model files and their metadata.
        save_json(
            version_folder / "FilesMetadata.json",
            [
                _file_summary(item)
                for item in version.get("files", [])
                if isinstance(item, dict)
            ]
        )

        # Save page-only details for the version selected in the submitted URL.
        selected_page_version = None
        if isinstance(page_metadata, dict):
            selected_page_version = (page_metadata.get("version_selector") or {}).get(
                "selected_version_id_from_url"
            )
        page_images = []
        page_generation_panels = []
        page_download_cards = []
        if isinstance(page_metadata, dict) and selected_page_version == version_id:
            page_images = page_metadata.get("gallery_images") or []
            page_generation_panels = page_metadata.get("generation_panels") or []
            page_download_cards = page_metadata.get("download_cards") or []

        save_json(
            version_folder / "PageMetadata.json",
            {
                "selected_version_on_page": selected_page_version == version_id,
                "gallery_images": page_images,
                "generation_panels": page_generation_panels,
                "download_cards": [
                    item for item in page_download_cards
                    if item.get("version_id") in (None, version_id)
                ]
            }
        )

        # Save each preview image's generation metadata separately.
        for index, image in enumerate(version.get("images", []), 1):
            page_image = page_images[index - 1] if index <= len(page_images) else None
            image_data = {
                "image_number": index,
                "url": image.get("url"),
                "width": image.get("width"),
                "height": image.get("height"),
                "nsfw": image.get("nsfw"),
                "nsfwLevel": image.get("nsfwLevel"),
                "type": image.get("type"),
                "meta": image.get("meta"),
                "civitai_image_id": page_image.get("image_id") if page_image else None,
                "page_gallery": page_image
            }
            save_json(
                image_metadata_folder / f"image_{index:03d}.json",
                image_data
            )

        version_records.append({
            "id": version_id,
            "name": version.get("name"),
            "baseModel": version.get("baseModel"),
            "folder": str(version_folder),
            "image_count": len(version.get("images", [])),
            "file_count": len(version.get("files", []))
        })

    save_json(
        root / "ArchiveIndex.json",
        {
            "model_id": model_data.get("id"),
            "name": model_data.get("name"),
            "creator": model_data.get("creator"),
            "type": model_data.get("type"),
            "version_count": len(version_records),
            "versions": version_records
        }
    )

    return root
