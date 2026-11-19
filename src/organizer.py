
import json
import re
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
        json.dump(
            data,
            file,
            indent=4,
            ensure_ascii=False
        )


def save_description(folder, html):
    """Save the original HTML description and a plain-text copy."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    html = html or ""

    html_path = folder / "Description.html"
    text_path = folder / "Description.txt"

    # Preserve the original HTML supplied by the API.
    html_path.write_text(html, encoding="utf-8")

    # Generate a readable text version.
    soup = BeautifulSoup(html, "html.parser")

    for element in soup(["script", "style"]):
        element.decompose()

    text = soup.get_text(separator="\n", strip=True)

    text_path.write_text(text, encoding="utf-8")


def create_model_archive(model_data, versions, download_directory):
    """Create the complete directory structure for a model."""

    model_name = safe_name(model_data.get("name", "Unnamed Model"))

    root = Path(download_directory) / model_name
    root.mkdir(parents=True, exist_ok=True)

    # Save main model metadata.
    save_json(root / "Metadata.json", model_data)

    # Save the model-level description.
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

        # Save the complete version response.
        save_json(
            version_folder / "VersionMetadata.json",
            version
        )

        # Save version description if available.
        save_description(
            version_folder / "Description",
            version.get("description") or ""
        )

        # Save each image's generation metadata separately.
        for index, image in enumerate(version.get("images", []), 1):
            image_data = {
                "image_number": index,
                "url": image.get("url"),
                "width": image.get("width"),
                "height": image.get("height"),
                "nsfw": image.get("nsfw"),
                "meta": image.get("meta")
            }

            metadata_name = f"image_{index:03d}.json"

            save_json(
                image_metadata_folder / metadata_name,
                image_data
            )

        version_records.append({
            "id": version_id,
            "name": version.get("name"),
            "baseModel": version.get("baseModel"),
            "folder": str(version_folder)
        })

    # Save a concise archive index.
    save_json(
        root / "ArchiveIndex.json",
        {
            "model_id": model_data.get("id"),
            "name": model_data.get("name"),
            "creator": model_data.get("creator"),
            "type": model_data.get("type"),
            "versions": version_records
        }
    )

    return root
