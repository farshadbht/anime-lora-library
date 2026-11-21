import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from bs4 import BeautifulSoup

from src.api import CivitaiAPI
from src.library_server import _civitai_preview_url, _civitai_preview_urls
from src import library_server as library_server_module
from src.franchise_catalog import add_franchise, find_franchise, load_catalog
from src.downloader import (
    _model_file_destination,
    _session_for_model_download,
    download_file,
    safe_filename,
)
from src.organizer import (
    create_model_archive,
    safe_name,
    save_description,
    save_download_report,
)
from src.page_extractor import (
    _extract_download_cards,
    _extract_generation_panels,
    _extract_image_gallery,
    _extract_version_selector,
)
from src import generate_library as library_generator


class FakeResponse:
    def __init__(self, body=b"", status_code=200, headers=None):
        self.body = body
        self.status_code = status_code
        self.headers = headers or {"Content-Length": str(len(body))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size):
        for start in range(0, len(self.body), chunk_size):
            yield self.body[start:start + chunk_size]


class FakeSession:
    def __init__(self, response=None):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.response is None:
            raise AssertionError("Unexpected network request")
        return self.response


class CivitaiAPITests(unittest.TestCase):
    def test_get_all_versions_retrieves_every_version(self):
        api = CivitaiAPI()
        api.get_version = Mock(side_effect=[
            {"id": 11, "modelId": 100},
            {"id": 12, "modelId": 100},
        ])
        versions = api.get_all_versions({
            "id": 100,
            "modelVersions": [{"id": 11}, {"id": 12}]
        })
        self.assertEqual([item["id"] for item in versions], [11, 12])
        self.assertEqual(api.get_version.call_count, 2)

    def test_get_all_versions_rejects_a_version_from_another_model(self):
        api = CivitaiAPI()
        api.get_version = Mock(return_value={"id": 11, "modelId": 999})
        with self.assertRaises(ValueError):
            api.get_all_versions({
                "id": 100,
                "modelVersions": [{"id": 11}]
            })

    def test_get_all_versions_fails_instead_of_silently_archiving_partially(self):
        api = CivitaiAPI()
        api.get_version = Mock(side_effect=requests.Timeout("fixture timeout"))
        with self.assertRaisesRegex(RuntimeError, "archive was not started"):
            api.get_all_versions({
                "id": 100,
                "modelVersions": [{"id": 11}]
            })

    def test_model_url_tracks_selected_version_and_returns_all_versions(self):
        api = CivitaiAPI()
        api.get_model = Mock(return_value={"id": 100, "name": "Fixture"})
        api.get_all_versions = Mock(return_value=[
            {"id": 11, "images": []},
            {"id": 12, "images": []},
        ])
        result = api.get_model_from_url(
            "https://civitai.com/models/100/fixture?modelVersionId=12"
        )
        self.assertEqual(result["selected_version_id"], 12)
        self.assertEqual([item["id"] for item in result["versions"]], [11, 12])
        self.assertTrue(result["all_versions_included"])

    def test_model_url_rejects_selected_version_not_belonging_to_model(self):
        api = CivitaiAPI()
        api.get_model = Mock(return_value={"id": 100, "name": "Fixture"})
        api.get_all_versions = Mock(return_value=[{"id": 11, "images": []}])
        with self.assertRaisesRegex(ValueError, "not part of this model"):
            api.get_model_from_url(
                "https://civitai.com/models/100/fixture?modelVersionId=12"
            )

    def test_website_search_uses_civitai_index_and_never_sends_personal_api_key(self):
        api = CivitaiAPI(api_key="do-not-send-this-key")
        response = Mock()
        response.json.return_value = {
            "hits": [{"id": 123, "name": "Fixture"}],
            "estimatedTotalHits": 1
        }

        with patch("src.api.requests.Session") as session_factory:
            search_session = session_factory.return_value
            search_session.headers = {}
            search_session.post.return_value = response

            result = api.search_site_models(
                "epsilon",
                offset=100,
                model_type="LORA",
                base_models=["Pony", "SDXL"],
                supports_generation=True,
                tag='anime "style"',
                username="fixture_creator"
            )

        self.assertEqual(result["hits"][0]["id"], 123)
        url, = session_factory.return_value.post.call_args.args
        body = session_factory.return_value.post.call_args.kwargs["json"]
        self.assertEqual(
            url,
            "https://civitai.com/api/search/indexes/models_v9/search"
        )
        self.assertEqual(body["q"], "epsilon")
        self.assertEqual(body["offset"], 100)
        self.assertEqual(body["limit"], 100)
        self.assertNotIn("sort", body)
        # Keep Civitai's complete visible hit shape so nested preview image URLs
        # are not accidentally stripped by an attributes-to-retrieve whitelist.
        self.assertNotIn("attributesToRetrieve", body)
        self.assertEqual(
            body["filter"],
            [
                'type = "LORA"',
                'versions.baseModel IN ["Pony", "SDXL"]',
                "canGenerate = true",
                'tags.name = "anime \\"style\\""',
                'user.username = "fixture_creator"'
            ]
        )
        self.assertNotIn("Authorization", search_session.headers)
        self.assertEqual(
            search_session.headers["Origin"],
            "https://civitai.com"
        )
        search_session.close.assert_called_once()

    def test_website_search_uses_mature_domain_only_when_configured(self):
        api = CivitaiAPI(mature_content=True)
        response = Mock()
        response.json.return_value = {"hits": []}

        with patch("src.api.requests.Session") as session_factory:
            session_factory.return_value.headers = {}
            session_factory.return_value.post.return_value = response
            api.search_site_models("epsilon")

        url = session_factory.return_value.post.call_args.args[0]
        self.assertTrue(url.startswith("https://civitai.red/"))
        self.assertNotIn(
            "Authorization",
            session_factory.return_value.headers
        )

    def test_website_search_rejects_invalid_offsets(self):
        api = CivitaiAPI()
        with self.assertRaisesRegex(ValueError, "cursor"):
            api.search_site_models("epsilon", offset=-1)
        with self.assertRaisesRegex(ValueError, "cursor"):
            api.search_site_models("epsilon", offset="not-an-offset")

    def test_search_preserves_native_relevance_and_passes_supported_filters(self):
        api = CivitaiAPI()
        response = Mock()
        response.json.return_value = {"items": []}
        api.session.get = Mock(return_value=response)

        api.search_models(
            "epsilon",
            model_type="LORA",
            base_models=["Anima", "SDXL"],
            include_nsfw=True,
            supports_generation=True,
            tag="character",
            username="fluxis",
            from_platform=True,
            early_access=True
        )

        params = api.session.get.call_args.kwargs["params"]
        self.assertEqual(params["query"], "epsilon")
        self.assertNotIn("sort", params)
        self.assertEqual(params["baseModels"], ["Anima", "SDXL"])
        self.assertEqual(params["types"], "LORA")
        self.assertEqual(params["nsfw"], "true")
        self.assertEqual(params["supportsGeneration"], "true")
        self.assertEqual(params["tag"], "character")
        self.assertEqual(params["username"], "fluxis")
        self.assertEqual(params["fromPlatform"], "true")
        self.assertEqual(params["earlyAccess"], "true")


class CivitaiSearchServerTests(unittest.TestCase):
    def test_search_uses_official_relevance_api_and_opaque_cursor(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings_path = Path(temporary) / "settings.json"
            settings_path.write_text(json.dumps({
                "api_key": "test-key",
                "content_preferences": {"mature_content_enabled": False}
            }), encoding="utf-8")

            payload = {
                "items": [{
                    "id": 123,
                    "name": "Character LoRA",
                    "type": "LORA",
                    "creator": {"username": "fixture_creator"},
                    "tags": ["character", "anime"],
                    "stats": {
                        "downloadCount": 1200,
                        "thumbsUpCount": 90,
                        "tippedAmountCount": 12,
                        "commentCount": 5,
                        "imageCount": 7
                    },
                    "modelVersions": [{
                        "baseModel": "Pony",
                        "publishedAt": "2026-01-02T00:00:00.000Z",
                        "images": [{
                            "url": "https://image.civitai.com/fixture-preview.jpeg"
                        }]
                    }]
                }],
                "metadata": {"nextCursor": "opaque-next-cursor"}
            }

            with patch.object(library_server_module, "SETTINGS_PATH", settings_path), patch.object(library_server_module, "CivitaiAPI") as api_factory:
                api = api_factory.return_value
                api.search_models.return_value = payload

                result = library_server_module.search_civitai_models(
                    "Character",
                    cursor="opaque-current-cursor",
                    model_type="LORA",
                    filters={
                        "base_models": "Pony, SDXL",
                        "supports_generation": True,
                        "tag": "character",
                        "username": "fixture_creator",
                        "from_platform": True,
                        "early_access": True
                    }
                )

        api_factory.assert_called_once_with("test-key", mature_content=False)
        call = api.search_models.call_args.kwargs
        self.assertEqual(call["cursor"], "opaque-current-cursor")
        self.assertEqual(call["query"], "Character")
        self.assertEqual(call["model_type"], "LORA")
        self.assertEqual(call["base_models"], ["Pony", "SDXL"])
        self.assertFalse(call["include_nsfw"])
        self.assertTrue(call["supports_generation"])
        self.assertTrue(call["from_platform"])
        self.assertTrue(call["early_access"])
        self.assertNotIn("sort", call)
        self.assertEqual(result["nextCursor"], "opaque-next-cursor")
        self.assertEqual(result["searchSource"], "civitai_api_v1_models_query")
        self.assertEqual(result["items"][0]["downloads"], 1200)
        self.assertEqual(result["items"][0]["baseModel"], "Pony")
        self.assertEqual(result["items"][0]["tags"], ["character", "anime"])
        self.assertEqual(result["items"][0]["url"], "https://civitai.com/models/123")


class CivitaiPreviewURLTests(unittest.TestCase):
    def test_search_image_uuid_becomes_cdn_preview_url(self):
        image_uuid = "f548f446-9fc2-429f-a64f-77f96a3b2697"
        self.assertEqual(
            _civitai_preview_url({"url": image_uuid}),
            "https://imagecache.civitai.com/"
            f"xG1nkqKTMzGDvpLrqFT7WA/{image_uuid}/width=450"
        )

    def test_existing_full_image_url_is_preserved(self):
        url = (
            "https://imagecache.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/"
            "f548f446-9fc2-429f-a64f-77f96a3b2697/width=450"
        )
        self.assertEqual(_civitai_preview_url({"url": url}), url)

    def test_invalid_preview_values_are_ignored(self):
        self.assertIsNone(_civitai_preview_url({"url": ""}))
        self.assertIsNone(_civitai_preview_url({"url": "not-a-url-or-uuid"}))
        self.assertIsNone(_civitai_preview_url(None))

    def test_preview_candidates_are_unique_and_skip_invalid_images(self):
        first = "f548f446-9fc2-429f-a64f-77f96a3b2697"
        second = "070792ae-c856-4433-9c01-004c32053fa3"
        urls = _civitai_preview_urls([
            {"url": first},
            {"url": "invalid"},
            {"url": first},
            {"url": second}
        ])
        self.assertEqual(len(urls), 2)
        self.assertIn(first, urls[0])
        self.assertIn(second, urls[1])
        self.assertEqual(_civitai_preview_urls(None), [])


class URLAndMetadataTests(unittest.TestCase):
    def test_parse_model_url_accepts_supported_hosts_and_version(self):
        self.assertEqual(
            CivitaiAPI.parse_model_url(
                "https://civitai.red/models/2780996/example?modelVersionId=3132064"
            ),
            (2780996, 3132064)
        )

    def test_parse_model_url_rejects_untrusted_and_invalid_urls(self):
        for url in (
            "http://civitai.com/models/12/example",
            "https://evil.example/models/12/example",
            "https://civitai.com/users/12",
            "https://civitai.com/models/12/example?modelVersionId=abc",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    CivitaiAPI.parse_model_url(url)

    def test_image_asset_key_normalizes_resized_cdn_urls(self):
        one = "https://image.civitai.com/x/070792ae-c856-4433-9c01-004c32053fa3/anim=false,width=800/preview.jpeg"
        two = "https://image.civitai.com/x/070792ae-c856-4433-9c01-004c32053fa3/anim=false,width=1600/preview.jpeg"
        self.assertEqual(
            CivitaiAPI._image_asset_key(one),
            CivitaiAPI._image_asset_key(two)
        )

    def test_filename_helpers_handle_windows_reserved_names_and_collisions(self):
        self.assertEqual(safe_filename("CON"), "_CON")
        self.assertEqual(safe_name("NUL"), "_NUL")
        with tempfile.TemporaryDirectory() as folder:
            used = set()
            first = _model_file_destination(
                Path(folder), {"name": "weights.safetensors", "id": 1}, 1, used
            )
            second = _model_file_destination(
                Path(folder), {"name": "weights.safetensors", "id": 2}, 2, used
            )
            self.assertEqual(first.name, "weights.safetensors")
            self.assertIn("[2]", second.name)


class DownloadIntegrityTests(unittest.TestCase):
    def test_download_writes_file_and_checks_size_and_sha256(self):
        body = b"small model fixture"
        digest = hashlib.sha256(body).hexdigest()
        session = FakeSession(FakeResponse(body))
        with tempfile.TemporaryDirectory() as folder:
            path, downloaded = download_file(
                session,
                "https://civitai.com/file",
                Path(folder) / "weights.bin",
                expected_size=len(body),
                expected_sha256=digest,
                return_status=True
            )
            self.assertTrue(downloaded)
            self.assertEqual(path.read_bytes(), body)
            self.assertFalse(path.with_name(path.name + ".part").exists())

    def test_existing_valid_file_is_reused_without_network(self):
        body = b"already here"
        session = FakeSession()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "weights.bin"
            path.write_bytes(body)
            result, downloaded = download_file(
                session,
                "https://civitai.com/file",
                path,
                expected_size=len(body),
                expected_sha256=hashlib.sha256(body).hexdigest(),
                return_status=True
            )
            self.assertEqual(result, path)
            self.assertFalse(downloaded)
            self.assertEqual(session.calls, [])

    def test_partial_download_resumes_only_at_valid_content_range(self):
        body = b"abcdef"
        session = FakeSession(FakeResponse(
            b"def",
            status_code=206,
            headers={"Content-Length": "3", "Content-Range": "bytes 3-5/6"}
        ))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "weights.bin"
            path.with_name("weights.bin.part").write_bytes(b"abc")
            result = download_file(
                session,
                "https://civitai.com/file",
                path,
                expected_size=6,
                expected_sha256=hashlib.sha256(body).hexdigest()
            )
            self.assertEqual(result.read_bytes(), body)
            self.assertEqual(
                session.calls[0][1]["headers"]["Range"],
                "bytes=3-"
            )

    def test_invalid_resume_range_is_rejected_without_appending(self):
        session = FakeSession(FakeResponse(
            b"def",
            status_code=206,
            headers={"Content-Length": "3", "Content-Range": "bytes 2-4/5"}
        ))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "weights.bin"
            partial = path.with_name("weights.bin.part")
            partial.write_bytes(b"abc")
            with self.assertRaises(IOError):
                download_file(session, "https://civitai.com/file", path)
            self.assertEqual(partial.read_bytes(), b"abc")
            self.assertFalse(path.exists())

    def test_server_ignoring_range_restarts_instead_of_appending(self):
        session = FakeSession(FakeResponse(b"fresh full body", status_code=200))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "weights.bin"
            path.with_name("weights.bin.part").write_bytes(b"old")
            result = download_file(
                session,
                "https://civitai.com/file",
                path,
                expected_size=len(b"fresh full body")
            )
            self.assertEqual(result.read_bytes(), b"fresh full body")

    def test_bad_hash_removes_invalid_partial(self):
        session = FakeSession(FakeResponse(b"wrong"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "weights.bin"
            partial = path.with_name("weights.bin.part")
            with self.assertRaises(IOError):
                download_file(
                    session,
                    "https://civitai.com/file",
                    path,
                    expected_size=5,
                    expected_sha256="0" * 64
                )
            self.assertFalse(partial.exists())
            self.assertFalse(path.exists())

    def test_credentials_are_not_forwarded_to_external_file_hosts(self):
        api = Mock()
        api.session = Mock()
        trusted, temporary = _session_for_model_download(
            api, "https://civitai.com/api/download/models/1"
        )
        self.assertIs(trusted, api.session)
        self.assertIsNone(temporary)

        external, temporary = _session_for_model_download(
            api, "https://cdn.example.net/model.bin"
        )
        try:
            self.assertIsNot(external, api.session)
            self.assertIs(temporary, external)
            self.assertNotIn("Authorization", external.headers)
        finally:
            temporary.close()


class PageExtractionTests(unittest.TestCase):
    def test_gallery_extraction_keeps_image_id_order_and_alt(self):
        soup = BeautifulSoup(
            '<a href="/images/123"><div style="aspect-ratio: 2 / 3">'
            '<img src="https://image.civitai.com/example.jpg" alt="preview.png">'
            '</div></a>',
            "html.parser"
        )
        images = _extract_image_gallery(
            soup, "https://civitai.com/models/1/example"
        )
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["image_id"], 123)
        self.assertEqual(images[0]["order"], 1)
        self.assertEqual(images[0]["alt"], "preview.png")
        self.assertEqual(images[0]["aspect_ratio"]["text"], "2 / 3")

    def test_version_selector_reads_url_selected_version(self):
        soup = BeautifulSoup(
            '<button data-version-id="3132064">v1.0</button>'
            '<button data-version-id="3132065">v2.0</button>',
            "html.parser"
        )
        result = _extract_version_selector(
            soup,
            "https://civitai.com/models/1/example?modelVersionId=3132065"
        )
        self.assertEqual(result["selected_version_id_from_url"], 3132065)
        self.assertEqual(result["visible_versions"][1]["selected"], True)

    def test_download_card_extracts_file_and_verification_details(self):
        soup = BeautifulSoup(
            '<div><p>1 variant available fp16 SafeTensor '
            'Darkness-Konosuba-anima-v1.safetensors 87.65 MB Verified</p>'
            '<time datetime="2026-07-15T16:14:16+03:30"></time>'
            '<a href="/api/download/models/3132064?fileId=3012668">Download</a></div>',
            "html.parser"
        )
        cards = _extract_download_cards(
            soup, "https://civitai.com/models/1/example"
        )
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["version_id"], 3132064)
        self.assertEqual(cards[0]["file_id"], 3012668)
        self.assertEqual(cards[0]["filename"], "Darkness-Konosuba-anima-v1.safetensors")
        self.assertTrue(cards[0]["verified"])
        self.assertEqual(cards[0]["variant_count"], 1)

    def test_generation_panel_extracts_positive_negative_prompts(self):
        soup = BeautifulSoup(
            '<div class="mantine-Card-root">'
            '<div><p>Prompt</p></div><div data-line-clamp="true">positive prompt words</div>'
            '<div><p>Negative prompt</p></div><div data-line-clamp="true">negative prompt words</div>'
            '<div><p>Other metadata</p></div>'
            '</div>',
            "html.parser"
        )
        panels = _extract_generation_panels(soup)
        self.assertEqual(len(panels), 1)
        self.assertEqual(panels[0]["positive_prompt"], "positive prompt words")
        self.assertEqual(panels[0]["negative_prompt"], "negative prompt words")


class ArchiveTests(unittest.TestCase):
    def test_description_keeps_paragraphs_and_removes_scripts(self):
        with tempfile.TemporaryDirectory() as folder:
            save_description(
                Path(folder) / "Description",
                "<p>First paragraph.</p><p>Second paragraph.</p><script>bad()</script>"
            )
            text = (Path(folder) / "Description" / "Description.txt").read_text(
                encoding="utf-8"
            )
            self.assertEqual(text, "First paragraph.\n\nSecond paragraph.")
            html = (Path(folder) / "Description" / "Description.html").read_text(
                encoding="utf-8"
            )
            self.assertIn("<script>", html)

    def test_archive_includes_all_versions_but_page_fields_only_for_selected(self):
        model = {
            "id": 100,
            "name": "Fixture Character",
            "type": "LORA",
            "description": "<p>Model description.</p>",
            "creator": {"username": "fixture"}
        }
        versions = [
            {
                "id": 11, "name": "v1.0", "baseModel": "Anima",
                "description": "<p>Version one.</p>", "files": [],
                "images": [{"url": "https://image.civitai.com/a/one.jpg", "meta": {"prompt": "one"}}]
            },
            {
                "id": 12, "name": "v2.0", "baseModel": "Anima",
                "description": "<p>Version two.</p>", "files": [],
                "images": [{"url": "https://image.civitai.com/a/two.jpg", "meta": {"prompt": "two"}}]
            }
        ]
        page = {
            "fetch_status": "success",
            "version_selector": {
                "selected_version_id_from_url": 11,
                "displayed_version_id": 11
            },
            "details_section": {"fields": {"air": "civitai:100@11"}},
            "model_header": {"title": "Fixture Character"},
            "gallery_images": [{"image_id": 501, "url": versions[0]["images"][0]["url"]}],
            "generation_panels": [{"positive_prompt": "fixture prompt"}],
            "download_cards": [{"version_id": 11, "file_id": 21}]
        }
        with tempfile.TemporaryDirectory() as folder:
            root = create_model_archive(
                model, versions, folder, save_descriptions=True,
                page_metadata=page,
                gallery_images_by_version={"11": [], "12": []}
            )
            index = json.loads((root / "ArchiveIndex.json").read_text(encoding="utf-8"))
            self.assertEqual(index["version_count"], 2)
            self.assertTrue(index["all_model_versions_included"])

            v1 = root / "Versions" / "v1.0 [11]"
            v2 = root / "Versions" / "v2.0 [12]"
            p1 = json.loads((v1 / "PageMetadata.json").read_text(encoding="utf-8"))
            p2 = json.loads((v2 / "PageMetadata.json").read_text(encoding="utf-8"))
            self.assertTrue(p1["selected_version_on_page"])
            self.assertEqual(p1["details_section"]["fields"]["air"], "civitai:100@11")
            self.assertFalse(p2["selected_version_on_page"])
            self.assertIsNone(p2["details_section"])
            image_meta = json.loads(
                (v1 / "Image_Metadata" / "image_001.json").read_text(encoding="utf-8")
            )
            self.assertEqual(image_meta["civitai_image_id"], 501)
            self.assertEqual(image_meta["generation_summary"]["positive_prompt"], "one")

    def test_download_report_uses_archive_relative_paths_and_present_counts(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "Archive"
            version_dir = root / "Versions" / "v1"
            version_dir.mkdir(parents=True)
            model_file = version_dir / "Files" / "weights.safetensors"
            model_file.parent.mkdir(parents=True)
            model_file.write_bytes(b"x")
            report_path = save_download_report(
                root,
                [{
                    "version_id": 11, "version_name": "v1",
                    "files_downloaded": [str(model_file)],
                    "images_downloaded": [],
                    "files_already_present": [str(model_file)],
                    "images_already_present": [],
                    "files_skipped": 0, "images_skipped": 0, "errors": []
                }],
                {"model_files": True, "images": True},
                selected_version_id=11
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(
                report["versions"][0]["files_downloaded"][0],
                "Versions/v1/Files/weights.safetensors"
            )
            self.assertEqual(report["files_already_present"], 1)
            self.assertEqual(report["status"], "completed")


class FranchiseCatalogTests(unittest.TestCase):
    def test_seed_and_legacy_categories_merge_without_losing_custom_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            seed = root / "seed.json"
            catalog = root / "catalog.json"
            seed.write_text(json.dumps({
                "entries": [
                    {"name": "One Piece", "type": "Anime / Manga", "aliases": []},
                    {"name": "Warcraft", "type": "Video Game", "aliases": []}
                ]
            }), encoding="utf-8")
            catalog.write_text(json.dumps({
                "version": 1,
                "entries": [{
                    "name": "My Custom Universe",
                    "type": "Original Work",
                    "aliases": ["MCU Local"],
                    "custom": True
                }]
            }), encoding="utf-8")

            entries = load_catalog(
                catalog, seed, legacy_names=["Old Anime Category"]
            )

            self.assertIsNotNone(find_franchise(entries, "one piece"))
            self.assertEqual(find_franchise(entries, "Warcraft")["type"], "Video Game")
            self.assertEqual(find_franchise(entries, "Old Anime Category")["type"], "Anime / Manga")
            self.assertEqual(find_franchise(entries, "MCU Local")["name"], "My Custom Universe")
            self.assertEqual(find_franchise(entries, "My Custom Universe")["type"], "Original Work")

    def test_custom_franchise_is_saved_and_duplicate_names_are_case_insensitive(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog = Path(folder) / "catalog.json"
            created = add_franchise(catalog, "My New Game", "Video Game")
            duplicate = add_franchise(catalog, " my new GAME ", "Movie")

            self.assertEqual(created["type"], "Video Game")
            self.assertEqual(duplicate["name"], "My New Game")
            self.assertEqual(duplicate["type"], "Video Game")
            persisted = json.loads(catalog.read_text(encoding="utf-8"))
            self.assertEqual(len(persisted["entries"]), 1)

    def test_unknown_franchise_requires_a_valid_type(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog = Path(folder) / "catalog.json"
            with self.assertRaisesRegex(ValueError, "valid franchise type"):
                add_franchise(catalog, "Unlisted World", "Not a category")

    def test_catalog_search_matches_aliases(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog = Path(folder) / "catalog.json"
            add_franchise(catalog, "World of Warcraft", "Video Game")
            payload = json.loads(catalog.read_text(encoding="utf-8"))
            payload["entries"][0]["aliases"] = ["WoW"]
            catalog.write_text(json.dumps(payload), encoding="utf-8")
            entries = load_catalog(catalog)
            self.assertEqual(find_franchise(entries, "wow")["name"], "World of Warcraft")




class ManageLibraryWorkspaceTests(unittest.TestCase):
    def test_manage_page_renders_workspace_inventory_and_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            downloads = root / "downloads"
            character_folder = downloads / "Fixture Character"
            versions = character_folder / "Versions" / "v1"
            versions.mkdir(parents=True)
            (character_folder / "index.html").write_text(
                "<html>fixture character</html>", encoding="utf-8"
            )
            (character_folder / "Metadata.json").write_text(json.dumps({
                "id": 123, "name": "Fixture Character", "creator": {"username": "artist"}
            }), encoding="utf-8")
            (character_folder / "ArchiveIndex.json").write_text(
                json.dumps({"version_count": 1}), encoding="utf-8"
            )
            (versions / "preview.webp").write_bytes(b"fixture")
            config = downloads / "library.json"
            config.write_text(json.dumps({
                "anime": [{
                    "name": "Fixture Franchise",
                    "characters": [{
                        "name": "Fixture Character",
                        "folder": "Fixture Character"
                    }]
                }]
            }), encoding="utf-8")

            with (
                patch.object(library_generator, "ROOT", downloads),
                patch.object(library_generator, "CONFIG", config),
                patch.object(library_generator, "PROJECT_ROOT", root)
            ):
                library_generator.generate()

            page = (downloads / "manage.html").read_text(encoding="utf-8")
            self.assertIn('id="view-overview"', page)
            self.assertIn('id="view-characters"', page)
            self.assertIn('id="view-franchises"', page)
            self.assertIn('id="view-archives"', page)
            self.assertIn("Fixture Character", page)
            self.assertIn("Fixture Franchise", page)
            self.assertIn("/downloads/Fixture%20Character/Versions/v1/preview.webp", page)
            self.assertNotIn("__FRANCHISE_DATA__", page)
            self.assertNotIn("__CHARACTER_COUNT__", page)
            self.assertIn("inventoryPageSize = 48", page)

    def test_civitai_search_keeps_relevance_as_fixed_search_order(self):
        source = Path(library_generator.__file__).read_text(encoding="utf-8")
        self.assertIn('id="civitai-sort-by"', source)
        self.assertNotIn('<option value="relevance"', source)
        self.assertIn('<option value="" selected disabled hidden>Choose a sorting metric</option>', source)
        self.assertNotIn("Keep Civitai relevance order</option>", source)
        self.assertIn('id="civitai-reset-sort"', source)
        self.assertIn('civitaiResetSortButton.addEventListener("click"', source)
        self.assertIn('<option value="downloads">Most Downloaded</option>', source)
        self.assertNotIn('id="civitai-sort-direction"', source)
        self.assertNotIn("civitaiSortDirection", source)
        # Sorting is outside the search form, so it cannot submit a new search.
        search_form = source.split('<form class="online-search-controls" id="civitai-search-form">', 1)[1].split("</form>", 1)[0]
        self.assertNotIn('id="civitai-sort-by"', search_form)
        self.assertIn('civitaiSortSelect.addEventListener("change",()=>{{if(civitaiSearchItems.length)renderCivitaiResults()}});', source)
        sort_start = source.index('civitaiSortSelect.addEventListener("change"')
        sort_end = source.index(");", sort_start) + 2
        sort_handler = source[sort_start:sort_end]
        self.assertNotIn('requestCivitaiModels', sort_handler)
        self.assertIn('else if(sortBy) {{', source)
        self.assertIn('civitaiSearchItems.push(...(result.items||[]).map', source)
        self.assertEqual(source.count('requestCivitaiModels()'), 1)
        self.assertIn('requestCivitaiModels(civitaiNextCursor)', source)
        self.assertIn('civitaiSortSelect.value="";', source)
        # Result rows must reserve their sorted DOM position before asynchronous preview loading.
        reserve_position = source.index('civitaiResultsElement.appendChild(row);')
        preview_loading = source.index('if(previewCandidates.length<3) await loadCanonicalPreviews();')
        self.assertLess(reserve_position, preview_loading)
        self.assertNotIn('civitaiResultsElement.appendChild(row);', source[preview_loading:])


if __name__ == "__main__":
    unittest.main(verbosity=2)
