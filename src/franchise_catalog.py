"""Local, offline-first catalog for franchise/source categories."""
import json
import re
from pathlib import Path

FRANCHISE_TYPES = (
    "Anime / Manga",
    "Video Game",
    "Movie",
    "TV Series",
    "Book / Novel",
    "Comic",
    "Original Work",
    "Other",
)


def _clean_name(value):
    if not isinstance(value, str):
        raise ValueError("A franchise name is required.")
    name = re.sub(r"\s+", " ", value).strip()
    if not name or len(name) > 120 or any(ord(char) < 32 for char in name):
        raise ValueError("Franchise names must contain 1–120 printable characters.")
    return name


def _key(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def load_catalog(catalog_path, seed_path=None, legacy_names=()):
    """Load the user's catalog, merge missing seed entries, and migrate old categories."""
    path = Path(catalog_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise ValueError("The franchise catalog file is unreadable; it was not overwritten.")
    else:
        payload = {"version": 1, "entries": []}

    entries = payload.get("entries", []) if isinstance(payload, dict) else []
    if not isinstance(entries, list):
        raise ValueError("The franchise catalog has an invalid entries list.")

    normalized = []
    seen = set()
    for item in entries:
        if not isinstance(item, dict):
            continue
        try:
            name = _clean_name(item.get("name"))
        except ValueError:
            continue
        key = _key(name)
        if key in seen:
            continue
        kind = item.get("type")
        if kind not in FRANCHISE_TYPES:
            kind = "Other"
        aliases = item.get("aliases", [])
        if not isinstance(aliases, list):
            aliases = []
        aliases = list(dict.fromkeys(
            _clean_name(alias) for alias in aliases
            if isinstance(alias, str) and alias.strip() and _key(alias) != key
        ))
        normalized.append({
            "name": name,
            "type": kind,
            "aliases": aliases,
            "parent": item.get("parent") if isinstance(item.get("parent"), str) else None,
            "custom": bool(item.get("custom", False)),
        })
        seen.add(key)

    if seed_path and Path(seed_path).is_file():
        seed = json.loads(Path(seed_path).read_text(encoding="utf-8"))
        seed_entries = seed.get("entries", []) if isinstance(seed, dict) else []
        for item in seed_entries:
            if not isinstance(item, dict):
                continue
            key = _key(item.get("name"))
            if key and key not in seen:
                normalized.append({
                    "name": _clean_name(item.get("name")),
                    "type": item.get("type") if item.get("type") in FRANCHISE_TYPES else "Other",
                    "aliases": item.get("aliases", []) if isinstance(item.get("aliases", []), list) else [],
                    "parent": item.get("parent") if isinstance(item.get("parent"), str) else None,
                    "custom": False,
                })
                seen.add(key)

    for legacy_name in legacy_names:
        try:
            name = _clean_name(legacy_name)
        except ValueError:
            continue
        key = _key(name)
        if key not in seen:
            normalized.append({
                "name": name,
                "type": "Anime / Manga",
                "aliases": [],
                "parent": None,
                "custom": True,
            })
            seen.add(key)

    normalized.sort(key=lambda item: item["name"].casefold())
    result = {"version": 1, "entries": normalized}
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def find_franchise(entries, value):
    key = _key(value)
    if not key:
        return None
    for item in entries:
        if _key(item.get("name")) == key:
            return item
        if any(_key(alias) == key for alias in item.get("aliases", [])):
            return item
    return None


def add_franchise(catalog_path, name, franchise_type, seed_path=None):
    """Create a local entry, or return the existing canonical entry."""
    entries = load_catalog(catalog_path, seed_path)
    clean_name = _clean_name(name)
    existing = find_franchise(entries, clean_name)
    if existing:
        return existing

    if franchise_type not in FRANCHISE_TYPES:
        raise ValueError("Choose a valid franchise type before adding a new entry.")

    entry = {
        "name": clean_name,
        "type": franchise_type,
        "aliases": [],
        "parent": None,
        "custom": True,
    }
    entries.append(entry)
    entries.sort(key=lambda item: item["name"].casefold())
    Path(catalog_path).write_text(
        json.dumps({"version": 1, "entries": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return entry
