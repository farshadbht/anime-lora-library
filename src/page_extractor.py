import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup


ALLOWED_HOSTS = {
    "civitai.com",
    "www.civitai.com",
    "civitai.red",
    "www.civitai.red"
}
MAX_PAGE_BYTES = 15 * 1024 * 1024


def _clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _absolute_url(value, base_url):
    if not value:
        return None
    return urljoin(base_url, value)


def _parse_aspect_ratio(element):
    current = element
    for _ in range(4):
        if current is None:
            break
        style = current.get("style", "")
        match = re.search(
            r"aspect-ratio\s*:\s*([0-9.]+)\s*/\s*([0-9.]+)",
            style,
            re.IGNORECASE
        )
        if match:
            return {
                "width": float(match.group(1)),
                "height": float(match.group(2)),
                "text": f"{match.group(1)} / {match.group(2)}"
            }
        current = current.parent
    return None


def _extract_image_gallery(soup, page_url):
    images = []
    seen_ids = set()

    for anchor in soup.select('a[href*="/images/"]'):
        href = anchor.get("href", "")
        match = re.search(r"/images/(\d+)(?:/|$)", urlparse(href).path)
        if not match:
            continue

        image_id = int(match.group(1))
        if image_id in seen_ids:
            continue

        image = anchor.find("img")
        if image is None:
            continue

        seen_ids.add(image_id)
        src = image.get("src") or image.get("data-src")
        srcset = image.get("srcset") or image.get("data-srcset")

        images.append({
            "image_id": image_id,
            "order": len(images) + 1,
            "page_url": _absolute_url(href, page_url),
            "url": src,
            "srcset": srcset,
            "alt": image.get("alt"),
            "aspect_ratio": _parse_aspect_ratio(image),
            "width_attribute": _safe_int(image.get("width")),
            "height_attribute": _safe_int(image.get("height"))
        })

    return images


def _extract_download_cards(soup, page_url):
    cards = []
    seen = set()

    for anchor in soup.select('a[href*="/api/download/models/"]'):
        href = anchor.get("href", "")
        match = re.search(r"/api/download/models/(\d+)", href)
        if not match:
            continue

        version_id = int(match.group(1))
        if (version_id, href) in seen:
            continue
        seen.add((version_id, href))

        container = anchor
        for _ in range(6):
            if container.parent is None:
                break
            container = container.parent
            text = _clean_text(container.get_text(" ", strip=True))
            if len(text) >= 20:
                break

        card_text = _clean_text(container.get_text(" ", strip=True))
        filename_match = re.search(
            r"[\w .()\-]+\.(?:safetensors|ckpt|pt|pth|bin|gguf)",
            card_text,
            re.IGNORECASE
        )
        size_match = re.search(
            r"\b\d+(?:\.\d+)?\s*(?:KB|MB|GB|TB)\b",
            card_text,
            re.IGNORECASE
        )

        cards.append({
            "version_id": version_id,
            "download_url": _absolute_url(href, page_url),
            "download_endpoint": href,
            "filename": filename_match.group(0).strip() if filename_match else None,
            "size_display": size_match.group(0) if size_match else None,
            "card_text": card_text,
            "verified": bool(re.search(r"\bverified\b", card_text, re.IGNORECASE))
        })

    return cards


def _extract_version_selector(soup, page_url):
    versions = []
    seen = set()
    selected_id = None
    query = parse_qs(urlparse(page_url).query)
    selected_values = query.get("modelVersionId") or []
    if selected_values:
        selected_id = _safe_int(selected_values[0])

    for element in soup.find_all(["a", "button"]):
        label = _clean_text(element.get_text(" ", strip=True))
        if not label or not re.search(r"\bv(?:ersion\s*)?[\w.-]+\b", label, re.IGNORECASE):
            continue

        candidates = [
            element.get("data-version-id"),
            element.get("data-model-version-id")
        ]
        href = element.get("href", "")
        href_query = parse_qs(urlparse(href).query)
        candidates.extend(href_query.get("modelVersionId", []))
        version_id = next(
            (_safe_int(value) for value in candidates if _safe_int(value) is not None),
            None
        )

        key = (label, version_id)
        if key in seen:
            continue
        seen.add(key)

        versions.append({
            "label": label,
            "version_id": version_id,
            "selected": version_id == selected_id if version_id is not None else None
        })

    return {
        "selected_version_id_from_url": selected_id,
        "visible_versions": versions
    }


def _extract_generation_panels(soup):
    panels = []
    for heading in soup.find_all(["p", "h2", "h3", "h4"]):
        if _clean_text(heading.get_text()).casefold() != "prompt":
            continue

        card = heading
        for _ in range(8):
            if card.parent is None:
                break
            card = card.parent
            classes = " ".join(card.get("class", []))
            text = _clean_text(card.get_text(" ", strip=True))
            if "mantine-Card-root" in classes or (
                "Negative prompt" in text and "Other metadata" in text
            ):
                break

        if not card:
            continue

        def text_after_heading(label):
            target = None
            for candidate in card.find_all(["p", "h2", "h3", "h4"]):
                if _clean_text(candidate.get_text()).casefold() == label.casefold():
                    target = candidate
                    break
            if target is None:
                return None
            value = target.find_next(
                lambda node: getattr(node, "name", None) == "div"
                and node is not card
                and node.find_parent(class_=lambda c: c and "mantine-Card-root" in str(c))
            )
            if value is None:
                value = target.find_next("div")
            return _clean_text(value.get_text(" ", strip=True)) if value else None

        prompt_heading = next(
            (
                item for item in card.find_all(["p", "h2", "h3", "h4"])
                if _clean_text(item.get_text()).casefold() == "prompt"
            ),
            None
        )
        negative_heading = next(
            (
                item for item in card.find_all(["p", "h2", "h3", "h4"])
                if _clean_text(item.get_text()).casefold() == "negative prompt"
            ),
            None
        )

        def content_for(heading_node):
            if heading_node is None:
                return None
            candidate = heading_node.find_next("div")
            if candidate is None:
                return None
            return _clean_text(candidate.get_text(" ", strip=True))

        badges = {}
        for badge in card.select(".mantine-Badge-label"):
            parts = [_clean_text(item.get_text(" ", strip=True)) for item in badge.find_all("span")]
            if len(parts) >= 2 and parts[0].endswith(":"):
                badges[parts[0][:-1]] = parts[1]
            elif len(parts) == 1:
                value = parts[0]
                if value not in ("External Generator", "txt2img"):
                    continue
                badges.setdefault("generator_or_mode", []).append(value)

        other_metadata = {}
        for label in card.find_all(string=re.compile(r"^(cfgScale|steps|sampler|seed|width|height):$")):
            key = _clean_text(label).rstrip(":")
            value_node = label.find_next(string=True)
            value = _clean_text(value_node) if value_node else None
            if value:
                other_metadata[key] = value

        panels.append({
            "positive_prompt": content_for(prompt_heading),
            "negative_prompt": content_for(negative_heading),
            "generator_and_mode": badges.get("generator_or_mode", []),
            "parameters": other_metadata or badges,
            "visible_text": _clean_text(card.get_text(" ", strip=True))
        })

    return panels


def _extract_details_section(soup):
    for element in soup.find_all(["div", "section"]):
        text = _clean_text(element.get_text(" ", strip=True))
        if (
            len(text) < 80
            or "Trigger Words" not in text
            or "Base Model" not in text
            or "Published" not in text
        ):
            continue
        classes = " ".join(element.get("class", []))
        if "mantine-Accordion" in classes or element.name == "section":
            return {
                "text": text,
                "html": str(element)
            }
    return None


def _extract_header(soup):
    title = None
    heading = soup.find("h1")
    if heading:
        title = _clean_text(heading.get_text(" ", strip=True))

    categories = []
    for anchor in soup.find_all("a", href=True):
        label = _clean_text(anchor.get_text(" ", strip=True))
        href = anchor.get("href", "")
        if label and (
            "/tags/" in href
            or "/tag/" in href
            or label.casefold() in {"character", "style", "concept", "clothing", "celebrity"}
        ):
            if label not in categories:
                categories.append(label)

    return {
        "title": title,
        "category_tags": categories
    }


def extract_model_page(model_url, model_data=None, versions=None):
    """
    Fetch and parse public Civitai model-page metadata.

    This is deliberately best-effort: API metadata remains authoritative and a
    webpage fetch failure must not prevent a valid API-based archive.
    """
    parsed = urlparse(str(model_url or "").strip())
    if parsed.scheme.lower() != "https" or (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
        raise ValueError("Only HTTPS Civitai model pages can be inspected.")

    result = {
        "source_url": model_url,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "fetch_status": "not_started",
        "page_title": None,
        "canonical_url": None,
        "meta_description": None,
        "open_graph": {},
        "model_header": {},
        "version_selector": {},
        "details_section": None,
        "download_cards": [],
        "gallery_images": [],
        "generation_panels": [],
        "notes": [
            "Civitai may load some page sections dynamically; API metadata is retained as the authoritative fallback."
        ]
    }

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    })

    try:
        response = session.get(model_url, timeout=(15, 35), allow_redirects=True)
        response.raise_for_status()

        content_length = _safe_int(response.headers.get("Content-Length"))
        if content_length is not None and content_length > MAX_PAGE_BYTES:
            raise ValueError("Civitai model page is larger than the extraction size limit.")

        html_text = response.text
        if len(html_text.encode("utf-8", errors="ignore")) > MAX_PAGE_BYTES:
            raise ValueError("Civitai model page is larger than the extraction size limit.")

        soup = BeautifulSoup(html_text, "html.parser")
        result["fetch_status"] = "success"
        result["final_url"] = response.url
        result["page_title"] = _clean_text(soup.title.get_text()) if soup.title else None

        canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
        result["canonical_url"] = canonical.get("href") if canonical else response.url

        description = soup.find("meta", attrs={"name": "description"})
        result["meta_description"] = description.get("content") if description else None

        for key in ("og:title", "og:description", "og:image", "og:url", "og:type"):
            tag = soup.find("meta", property=key)
            if tag and tag.get("content"):
                result["open_graph"][key] = tag["content"]

        result["model_header"] = _extract_header(soup)
        result["version_selector"] = _extract_version_selector(soup, model_url)
        result["details_section"] = _extract_details_section(soup)
        result["download_cards"] = _extract_download_cards(soup, model_url)
        result["gallery_images"] = _extract_image_gallery(soup, model_url)
        result["generation_panels"] = _extract_generation_panels(soup)

        if not result["gallery_images"]:
            result["notes"].append(
                "No gallery image links were present in the initial HTML; the gallery may be client-rendered or lazy-loaded."
            )
        if not result["generation_panels"]:
            result["notes"].append(
                "No expanded generation-data panel was present in the initial HTML; full prompt metadata should be taken from the version API response."
            )

    except Exception as error:
        result["fetch_status"] = "unavailable"
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        session.close()

    # Keep lightweight model/version identifiers beside the scraped page data.
    result["model_id"] = (model_data or {}).get("id")
    result["version_ids"] = [
        item.get("id") for item in (versions or [])
        if isinstance(item, dict) and item.get("id") is not None
    ]

    return result
