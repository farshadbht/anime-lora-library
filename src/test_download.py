import json

from api import CivitaiAPI
from organizer import create_model_archive, safe_name
from downloader import download_version_assets


def main():
    with open("config/settings.json", encoding="utf-8") as file:
        settings = json.load(file)

    download_settings = settings.get("download") or {}
    download_options = {
        "images": bool(download_settings.get("images", True)),
        "model_files": bool(download_settings.get("model_files", True)),
        "descriptions": bool(download_settings.get("descriptions", True))
    }

    api = CivitaiAPI(settings.get("api_key"))

    url = input("\nPaste the Civitai model URL: ").strip()
    result = api.get_model_from_url(url)

    model = result["model"]
    versions = result["versions"]

    root = create_model_archive(
        model,
        versions,
        settings.get("download_directory", "downloads"),
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

    total_files = sum(len(item["files_downloaded"]) for item in all_results)
    total_images = sum(len(item["images_downloaded"]) for item in all_results)
    total_errors = sum(len(item["errors"]) for item in all_results)
    total_files_skipped = sum(item["files_skipped"] for item in all_results)
    total_images_skipped = sum(item["images_skipped"] for item in all_results)

    print("\n===================================")
    print("DOWNLOAD COMPLETE")
    print("===================================")
    print("Model:", model.get("name"))
    print("Versions:", len(versions))
    print("Files downloaded:", total_files)
    print("Images downloaded:", total_images)
    print("Files skipped:", total_files_skipped)
    print("Images skipped:", total_images_skipped)
    print("Errors:", total_errors)
    print("Settings:", download_options)
    print("Archive:", root)


if __name__ == "__main__":
    main()
