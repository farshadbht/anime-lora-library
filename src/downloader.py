import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse, unquote

import requests
from tqdm import tqdm


CHUNK_SIZE = 1024 * 1024


def safe_filename(name):
    """Make a filename safe for Windows."""
    name = re.sub(r'[<>:"/\\|?*]', "_", str(name))
    name = name.strip().rstrip(". ")
    return name or "unnamed_file"


def get_image_filename(url, index):
    """Create a stable image filename using its original extension."""
    parsed = urlparse(url)
    original_name = Path(unquote(parsed.path)).name
    extension = Path(original_name).suffix.lower()
    if not extension or len(extension) > 8:
        extension = ".jpg"
    return f"image_{index:03d}{extension}"


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _expected_hash(hashes):
    """Return a usable SHA-256 hash from Civitai's file hash dictionary."""
    if not isinstance(hashes, dict):
        return None
    for key, value in hashes.items():
        if str(key).replace("-", "").casefold() == "sha256" and value:
            return str(value).strip().casefold()
    return None


def _existing_file_matches(path, expected_size=None, expected_sha256=None):
    path = Path(path)
    if not path.is_file():
        return False
    if expected_size is not None and path.stat().st_size != expected_size:
        return False
    if expected_sha256:
        return _sha256_file(path).casefold() == expected_sha256.casefold()
    return True


def download_file(
    session,
    url,
    destination,
    description="Downloading",
    expected_size=None,
    expected_sha256=None,
    return_status=False
):
    """
    Download atomically with validated resume support.

    A failed transfer leaves a .part file for a later retry. Existing files
    are reused only when available size/hash metadata matches.
    """
    if not url:
        raise ValueError("Download URL is missing.")

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")

    if destination.exists():
        if _existing_file_matches(destination, expected_size, expected_sha256):
            print(f"Already present; available validation checks passed: {destination.name}")
            return (destination, False) if return_status else destination
        print(f"Existing file failed validation; downloading again: {destination.name}")
        destination.unlink()

    existing_size = partial.stat().st_size if partial.exists() else 0
    if expected_size is not None and existing_size > expected_size:
        partial.unlink()
        existing_size = 0

    # Recover a transfer that finished writing but was interrupted before
    # the .part file could be atomically renamed.
    if (
        existing_size
        and expected_size is not None
        and existing_size == expected_size
    ):
        if _existing_file_matches(partial, expected_size, expected_sha256):
            partial.replace(destination)
            print(f"Recovered completed partial download: {destination.name}")
            return (destination, True) if return_status else destination
        partial.unlink()
        existing_size = 0

    headers = {}
    if existing_size:
        headers["Range"] = f"bytes={existing_size}-"

    with session.get(
        url,
        headers=headers,
        stream=True,
        timeout=(30, 120)
    ) as response:
        if response.status_code == 416 and existing_size:
            content_range = response.headers.get("Content-Range", "")
            match = re.match(r"bytes\s+\*/(\d+)$", content_range.strip(), re.I)
            reported_total = int(match.group(1)) if match else None
            if (
                reported_total is not None
                and reported_total == existing_size
                and (expected_size is None or reported_total == expected_size)
                and _existing_file_matches(partial, expected_size, expected_sha256)
            ):
                partial.replace(destination)
                print(f"Recovered completed partial download: {destination.name}")
                return (destination, True) if return_status else destination

        response.raise_for_status()

        if existing_size and response.status_code == 206:
            content_range = response.headers.get("Content-Range", "")
            match = re.match(r"bytes\s+(\d+)-(\d+)/(\d+|\*)$", content_range.strip(), re.I)
            if not match or int(match.group(1)) != existing_size:
                raise IOError(
                    f"Server returned an invalid resume range for {destination.name}: "
                    f"{content_range or 'missing Content-Range'}"
                )
            mode = "ab"
            downloaded = existing_size
            range_total = int(match.group(3)) if match.group(3).isdigit() else None
        elif response.status_code == 206:
            raise IOError(
                f"Server returned partial content without a resume request for {destination.name}."
            )
        else:
            # A server that ignores Range returns the full file; restart rather
            # than appending a second copy of its contents.
            mode = "wb"
            downloaded = 0
            range_total = None

        content_length = response.headers.get("Content-Length")
        response_length = int(content_length) if content_length and content_length.isdigit() else None
        total = range_total or (
            downloaded + response_length if response_length is not None else expected_size
        )

        with partial.open(mode) as file:
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
            file.flush()

    actual_size = partial.stat().st_size
    target_size = expected_size if expected_size is not None else range_total
    if target_size is not None and actual_size != target_size:
        raise IOError(
            f"Size validation failed for {destination.name}: "
            f"expected {target_size} bytes, received {actual_size} bytes. "
            "The partial file was retained for a possible retry."
        )

    if expected_sha256:
        actual_hash = _sha256_file(partial)
        if actual_hash.casefold() != expected_sha256.casefold():
            partial.unlink(missing_ok=True)
            raise IOError(
                f"SHA-256 validation failed for {destination.name}; "
                "the invalid partial file was removed."
            )

    partial.replace(destination)
    return (destination, True) if return_status else destination


def _session_for_model_download(api, url):
    """Use API credentials only for HTTPS URLs on Civitai-owned hosts."""
    parsed = urlparse(str(url or ""))
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("Model download URLs must use HTTPS.")

    hostname = parsed.hostname.lower()
    trusted_hosts = {
        "civitai.com",
        "www.civitai.com",
        "civitai.red",
        "www.civitai.red",
        "image.civitai.com"
    }
    if hostname in trusted_hosts:
        return api.session, None

    session = requests.Session()
    session.headers.update({"User-Agent": "CivitaiLoRADownloader/1.0"})
    return session, session


def _model_file_destination(files_folder, model_file, index, used_names):
    """Prefer Civitai's original filename and disambiguate collisions safely."""
    original_name = model_file.get("name") or f"model_{index}.bin"
    filename = safe_filename(Path(unquote(str(original_name))).name)
    if filename in used_names:
        file_id = model_file.get("id")
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        filename = safe_filename(f"{stem} [{file_id or index}]{suffix}")
        counter = 2
        while filename in used_names:
            filename = safe_filename(f"{stem} [{file_id or index}] ({counter}){suffix}")
            counter += 1
    used_names.add(filename)
    return files_folder / filename


def download_version_assets(api, version, version_folder, download_options=None):
    """
    Download selected assets for one model version.

    download_options supports model_files and images. Missing options default
    to True for backwards compatibility with older callers.
    """
    options = {"model_files": True, "images": True}
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
        "files_already_present": [],
        "images_already_present": [],
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
        used_names = set()

        for index, model_file in enumerate(version.get("files", []), 1):
            destination = _model_file_destination(
                files_folder, model_file, index, used_names
            )
            try:
                download_url = model_file.get("downloadUrl")
                expected_size = None
                if model_file.get("sizeKB") is not None:
                    expected_size = int(round(float(model_file["sizeKB"]) * 1024))
                expected_sha256 = _expected_hash(model_file.get("hashes"))

                download_session, temporary_session = _session_for_model_download(
                    api, download_url
                )
                try:
                    path, was_downloaded = download_file(
                        download_session,
                        download_url,
                        destination,
                        description=f"Model {index}",
                        expected_size=expected_size,
                        expected_sha256=expected_sha256,
                        return_status=True
                    )
                finally:
                    if temporary_session is not None:
                        temporary_session.close()

                key = "files_downloaded" if was_downloaded else "files_already_present"
                results[key].append(str(path))
            except Exception as error:
                message = f"Model file {destination.name}: {error}"
                print(f"ERROR: {message}")
                results["errors"].append(message)
    else:
        results["files_skipped"] = len(version.get("files", []))
        print("\nModel file downloads disabled in settings.")

    if options["images"]:
        images_folder.mkdir(parents=True, exist_ok=True)
        print("\nDownloading gallery images...")
        image_session = requests.Session()
        image_session.headers.update({"User-Agent": "CivitaiLoRADownloader/1.0"})

        try:
            for index, image in enumerate(version.get("images", []), 1):
                url = image.get("url")
                if not url:
                    results["errors"].append(f"Image {index}: URL missing")
                    continue

                destination = images_folder / get_image_filename(url, index)
                try:
                    path, was_downloaded = download_file(
                        image_session,
                        url,
                        destination,
                        description=f"Image {index}",
                        return_status=True
                    )
                    key = "images_downloaded" if was_downloaded else "images_already_present"
                    results[key].append(str(path))
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
    print(f"Files already present: {len(results['files_already_present'])}")
    print(f"Images downloaded: {len(results['images_downloaded'])}")
    print(f"Images already present: {len(results['images_already_present'])}")
    print(f"Files skipped: {results['files_skipped']}")
    print(f"Images skipped: {results['images_skipped']}")
    print(f"Errors: {len(results['errors'])}")

    return results
