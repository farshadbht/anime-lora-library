
import json
from pathlib import Path

from api import CivitaiAPI
from organizer import create_model_archive, safe_name
from downloader import download_version_assets


def main():
    with open("config/settings.json", encoding="utf-8") as file:
        settings = json.load(file)

    api = CivitaiAPI(settings["api_key"])

    url = input("\nPaste the Civitai model URL: ").strip()

    result = api.get_model_from_url(url)

    model = result["model"]
    versions = result["versions"]

    root = create_model_archive(
        model,
        versions,
        settings["download_directory"]
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
            version_folder
        )

        all_results.append(results)

    total_files = sum(
        len(item["files_downloaded"])
        for item in all_results
    )

    total_images = sum(
        len(item["images_downloaded"])
        for item in all_results
    )

    total_errors = sum(
        len(item["errors"])
        for item in all_results
    )

    print("\n===================================")
    print("DOWNLOAD COMPLETE")
    print("===================================")
    print("Model:", model.get("name"))
    print("Versions:", len(versions))
    print("Files downloaded:", total_files)
    print("Images downloaded:", total_images)
    print("Errors:", total_errors)
    print("Archive:", root)


if __name__ == "__main__":
    main()
