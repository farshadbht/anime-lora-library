import re
from pathlib import Path
from urllib.parse import urlparse, unquote

import requests
from tqdm import tqdm


CHUNK_SIZE = 1024 * 1024  # 1 MB


def safe_filename(name):
    """Make a filename safe for Windows."""
    name = re.sub(r'[<>:"/\\|?*]', "_", str(name))
    name = name.strip().rstrip(". ")
    return name or "unnamed_file"


def get_image_filename(url, index):
    """Create a filename using the original image extension."""
    parsed = urlparse(url)
    original_name = Path(unquote(parsed.path)).name
    extension = Path(original_name).suffix.lower()

    if not extension or len(extension) > 8:
        extension = ".jpg"

    return f"image_{index:03d}{extension}"


def download_file(session, url, destination, description="Downloading"):
    """
    Download a file with progress reporting and resume support.
    Incomplete downloads are stored as .part files.
    """
    if not url:
        raise ValueError("Download URL is missing.")

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        print(f"Already downloaded: {destination.name}")
        return destination

    partial = destination.with_name(destination.name + ".part")
    existing_size = partial.stat().st_size if partial.exists() else 0
    headers = {}

    if existing_size:
        headers["Range"] = f"bytes={existing_size}-"

    with session.get(
        url,
        headers=headers,
        stream=True,
        timeout=(30, 120)
    ) as response:
        response.raise_for_status()

        if existing_size and response.status_code == 206:
            mode = "ab"
            downloaded = existing_size
        else:
            mode = "wb"
            downloaded = 0

        total = response.headers.get("Content-Length")
        total = int(total) + downloaded if total else None

        with open(partial, mode) as file:
            with tqdm(
                total=total,
                initial=downloaded,
                unit="B",
                unit_scale=True,
                desc=description,
                leave=True
            ) as progress:
                for chunk in response.iter_content(CHUNK_SIZE):
                    if not chunk:
                        continue
                    file.write(chunk)
                    progress.update(len(chunk))

    partial.replace(destination)
    return destination


def download_version_assets(api, version, version_folder, download_options=None):
    """
    Download selected assets for one model version.

    download_options supports:
      - model_files: download model weight files
      - images: download original gallery images

    Missing options default to True to preserve compatibility with older callers.
    """
    options = {
        "model_files": True,
        "images": True
    }
    if isinstance(download_options, dict):
        options.update({
            key: bool(download_options[key])
            for key in options
            if key in download_options
        })

    version_folder = Path(version_folder)
    files_folder = version_folder / "Files"
    images_folder = version_folder / "Images"

    results = {
        "files_downloaded": [],
        "images_downloaded": [],
        "errors": [],
        "files_skipped": 0,
        "images_skipped": 0
    }

    version_name = version.get("name", "Version")
    version_id = version.get("id")
    print(f"\n========== {version_name} ==========")

    if options["model_files"]:
        files_folder.mkdir(parents=True, exist_ok=True)
        print("\nDownloading model files...")
        model_name = version_folder.parents[1].name
        model_filename = safe_filename(model_name)
        extension_counts = {}

        for index, model_file in enumerate(version.get("files", []), 1):
            original_name = model_file.get("name") or f"model_{index}"
            extension = Path(unquote(original_name)).suffix.lower()

            if not extension or len(extension) > 20:
                url = model_file.get("downloadUrl", "")
                extension = Path(unquote(urlparse(url).path)).suffix.lower()

            if not extension or len(extension) > 20:
                file_format = (
                    model_file.get("metadata", {}).get("format", "")
                )
                format_extensions = {
                    "safetensor": ".safetensors",
                    "pickle": ".ckpt",
                    "pickletensor": ".pt"
                }
                extension = format_extensions.get(
                    str(file_format).lower(),
                    ".bin"
                )

            extension_counts[extension] = extension_counts.get(extension, 0) + 1
            number = extension_counts[extension]
            filename = (
                f"{model_filename}{extension}"
                if number == 1
                else f"{model_filename} ({number}){extension}"
            )
            filename = safe_filename(filename)
            destination = files_folder / filename

            try:
                path = download_file(
                    api.session,
                    model_file.get("downloadUrl"),
                    destination,
                    description=f"Model {index}"
                )
                results["files_downloaded"].append(str(path))
            except Exception as error:
                message = f"Model file {filename}: {error}"
                print(f"ERROR: {message}")
                results["errors"].append(message)
    else:
        results["files_skipped"] = len(version.get("files", []))
        print("\nModel file downloads disabled in settings.")

    if options["images"]:
        images_folder.mkdir(parents=True, exist_ok=True)
        print("\nDownloading gallery images...")

        # Never send the authenticated API session to the image CDN.
        image_session = requests.Session()
        image_session.headers.update({
            "User-Agent": "CivitaiLoRADownloader/1.0"
        })

        try:
            for index, image in enumerate(version.get("images", []), 1):
                url = image.get("url")
                if not url:
                    message = f"Image {index}: URL missing"
                    results["errors"].append(message)
                    continue

                filename = get_image_filename(url, index)
                destination = images_folder / filename

                try:
                    path = download_file(
                        image_session,
                        url,
                        destination,
                        description=f"Image {index}"
                    )
                    results["images_downloaded"].append(str(path))
                except Exception as error:
                    message = f"Image {index}: {error}"
                    print(f"ERROR: {message}")
                    results["errors"].append(message)
        finally:
            image_session.close()
    else:
        results["images_skipped"] = len(version.get("images", []))
        print("\nImage downloads disabled in settings.")

    print(f"\nVersion {version_id} download summary:")
    print(f"Files downloaded: {len(results['files_downloaded'])}")
    print(f"Images downloaded: {len(results['images_downloaded'])}")
    print(f"Files skipped: {results['files_skipped']}")
    print(f"Images skipped: {results['images_skipped']}")
    print(f"Errors: {len(results['errors'])}")

    return results
