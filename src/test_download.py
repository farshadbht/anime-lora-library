import json

from api import CivitaiAPI
from organizer import create_model_archive, safe_name, save_download_report
from downloader import download_version_assets
from page_extractor import extract_model_page


def main():
    with open("config/settings.json", encoding="utf-8") as file:
        settings = json.load(file)

    download_settings = settings.get("download") or {}
    download_options = {
        "images": bool(download_settings.get("images", True)),
        "model_files": bool(download_settings.get("model_files", True)),
        "descriptions": bool(download_settings.get("descriptions", True))
    }

    preferences = settings.get("content_preferences") or {}
    mature_enabled = preferences.get("mature_content_enabled") is True
    api = CivitaiAPI(
        settings.get("api_key"),
        mature_content=mature_enabled
    )

    url = input("\nPaste the Civitai model URL: ").strip()
    result = api.get_model_from_url(url)

    model = result["model"]
    versions = result["versions"]
    selected_version_id = result.get("selected_version_id")
    page_metadata = extract_model_page(
        url, model_data=model, versions=versions
    )
    page_metadata["api_gallery_image_errors"] = (
        result.get("gallery_image_errors") or {}
    )
    print("Civitai webpage extraction:", page_metadata.get("fetch_status"))
    if page_metadata.get("error"):
        print("Webpage extraction note:", page_metadata["error"])

    root = create_model_archive(
        model,
        versions,
        settings.get("download_directory", "downloads"),
        save_descriptions=download_options["descriptions"],
        page_metadata=page_metadata,
        gallery_images_by_version=result.get("gallery_images_by_version")
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
        results["version_id"] = version.get("id")
        results["version_name"] = version.get("name")
        all_results.append(results)

    download_report = save_download_report(
        root, all_results, download_options,
        selected_version_id=selected_version_id
    )

    total_files = sum(len(item["files_downloaded"]) for item in all_results)
    total_images = sum(len(item["images_downloaded"]) for item in all_results)
    total_files_present = sum(len(item.get("files_already_present", [])) for item in all_results)
    total_images_present = sum(len(item.get("images_already_present", [])) for item in all_results)
    total_errors = sum(len(item["errors"]) for item in all_results)
    total_files_skipped = sum(item["files_skipped"] for item in all_results)
    total_images_skipped = sum(item["images_skipped"] for item in all_results)

    print("\n===================================")
    print("DOWNLOAD COMPLETE")
    print("===================================")
    print("Model:", model.get("name"))
    print("Versions:", len(versions))
    print("Selected URL version:", selected_version_id)
    print("All model versions included:", True)
    print("Files downloaded:", total_files)
    print("Files already present:", total_files_present)
    print("Images downloaded:", total_images)
    print("Images already present:", total_images_present)
    print("Files skipped:", total_files_skipped)
    print("Images skipped:", total_images_skipped)
    print("Errors:", total_errors)
    print("Settings:", download_options)
    print("Archive:", root)
    print("Download report:", download_report)


if __name__ == "__main__":
    main()
