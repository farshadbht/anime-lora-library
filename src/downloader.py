
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


def download_version_assets(api, version, version_folder):
    """
    Download all model files and original gallery images
    belonging to one specific version.

    Model files are renamed using the main model folder name.
    Original file extensions are preserved.
    """

    version_folder = Path(version_folder)

    files_folder = version_folder / "Files"
    images_folder = version_folder / "Images"

    files_folder.mkdir(parents=True, exist_ok=True)
    images_folder.mkdir(parents=True, exist_ok=True)

    # ModelFolder / Versions / VersionFolder
    model_name = version_folder.parents[1].name
    model_filename = safe_filename(model_name)

    results = {
        "files_downloaded": [],
        "images_downloaded": [],
        "errors": []
    }

    version_name = version.get("name", "Version")
    version_id = version.get("id")

    print(f"\n========== {version_name} ==========")

    # Download model files.
    print("\nDownloading model files...")

    extension_counts = {}

    for index, model_file in enumerate(version.get("files", []), 1):

        original_name = model_file.get("name") or f"model_{index}"

        # First, try to obtain the extension from the original filename.
        extension = Path(unquote(original_name)).suffix.lower()

        # Fall back to the download URL if necessary.
        if not extension or len(extension) > 20:
            url = model_file.get("downloadUrl", "")
            extension = Path(unquote(urlparse(url).path)).suffix.lower()

        # Final fallback: use Civitai's file format metadata.
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

        # Count files with the same extension.
        extension_counts[extension] = (
            extension_counts.get(extension, 0) + 1
        )

        number = extension_counts[extension]

        if number == 1:
            filename = f"{model_filename}{extension}"
        else:
            filename = f"{model_filename} ({number}){extension}"

        filename = safe_filename(filename)

        destination = files_folder / filename
        url = model_file.get("downloadUrl")

        try:
            path = download_file(
                api.session,
                url,
                destination,
                description=f"Model {index}"
            )

            results["files_downloaded"].append(str(path))

        except Exception as error:
            message = f"Model file {filename}: {error}"
            print(f"ERROR: {message}")
            results["errors"].append(message)

    # Download original gallery images.
    print("\nDownloading gallery images...")

    # Separate session: do not send the Civitai API key to the image CDN.
    image_session = requests.Session()
    image_session.headers.update({
        "User-Agent": "CivitaiLoRADownloader/1.0"
    })

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

    image_session.close()

    print(f"\nVersion {version_id} download summary:")
    print(f"Files downloaded: {len(results['files_downloaded'])}")
    print(f"Images downloaded: {len(results['images_downloaded'])}")
    print(f"Errors: {len(results['errors'])}")

    return results
