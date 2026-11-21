import json
import os
from pathlib import Path
from urllib.parse import quote
from html import escape

PROJECT_ROOT = Path(
    os.environ.get(
        "ANIME_LORA_HOME",
        Path(__file__).resolve().parent.parent
    )
).resolve()

ROOT = PROJECT_ROOT / "downloads"
CONFIG = ROOT / "library.json"


def local_url(path):
    return "/".join(quote(part) for part in path.parts)


def get_model_info(folder):
    metadata_path = folder / "Metadata.json"

    if not metadata_path.exists():
        return [], "Unknown", None

    data = json.loads(metadata_path.read_text(encoding="utf-8"))

    checkpoints = data.get("baseModels", [])

    if not checkpoints:
        versions_folder = folder / "Versions"
        if versions_folder.exists():
            for version_file in versions_folder.glob("*/VersionMetadata.json"):
                version_data = json.loads(
                    version_file.read_text(encoding="utf-8")
                )
                base = version_data.get("baseModel")
                if base and base not in checkpoints:
                    checkpoints.append(base)

    artist = data.get("creator", {}).get("username", "Unknown")

    return checkpoints, artist, data


def generate():
    data = json.loads(CONFIG.read_text(encoding="utf-8"))

    anime_sections = []
    total_characters = 0

    for anime in data.get("anime", []):
        character_rows = []
        valid_count = 0

        for character in anime.get("characters", []):
            folder = ROOT / character["folder"]
            index_page = folder / "index.html"
            versions_folder = folder / "Versions"

            if not index_page.exists():
                print(f"WARNING: Missing index.html: {folder}")
                continue

            checkpoints, artist, metadata = get_model_info(folder)

            checkpoint_text = (
                " / ".join(checkpoints) if checkpoints else "Unknown"
            )

            images = []
            if versions_folder.exists():
                images = sorted(
                    p for p in versions_folder.rglob("*")
                    if p.is_file() and p.suffix.lower()
                    in (".png", ".jpg", ".jpeg", ".webp")
                )

            preview_html = ""
            if images:
                image_url = local_url(images[0].relative_to(ROOT))
                preview_html = (
                    f'<img class="hover-preview" '
                    f'src="{escape(image_url, quote=True)}" '
                    f'alt="" loading="lazy">'
                )

            link = local_url(
                Path(character["folder"]) / "index.html"
            )

            search_text = (
                character["name"] + " " +
                anime["name"] + " " +
                checkpoint_text + " " + artist
            ).lower()

            character_rows.append(f"""
                <a class="character-row"
                   href="{escape(link, quote=True)}"
                   data-search="{escape(search_text, quote=True)}">

                    <span class="character-name">
                        {escape(character["name"])}
                    </span>

                    <span class="checkpoint">
                        {escape(checkpoint_text)}
                    </span>

                    <span class="artist">
                        {escape(artist)}
                    </span>

                    {preview_html}
                </a>
            """)

            valid_count += 1
            total_characters += 1

        if not character_rows:
            continue

        anime_sections.append(f"""
            <details class="anime-section">
                <summary>
                    <span class="anime-title">
                        {escape(anime["name"])}
                    </span>
                    <span class="count">
                        {valid_count}
                    </span>
                </summary>

                <div class="column-headings">
                    <span>Character Name</span>
                    <span>Checkpoints</span>
                    <span>Artist Name</span>
                </div>

                <div class="character-list">
                    {''.join(character_rows)}
                </div>
            </details>
        """)

    anime_options = "".join(
        f'<option value="{escape(anime["name"], quote=True)}"></option>'
        for anime in data.get("anime", [])
    )

    manage_data = json.dumps([
        {
            "anime": anime["name"],
            "characters": [
                {"name": character["name"], "folder": character["folder"]}
                for character in anime.get("characters", [])
            ]
        }
        for anime in data.get("anime", [])
    ], ensure_ascii=False).replace("<", "\\u003c")

    manage_anime_options = "".join(
        f'<option value="{escape(anime["name"], quote=True)}">{escape(anime["name"])}</option>'
        for anime in data.get("anime", [])
        if anime.get("characters")
    )


    archived_models = []
    library_folders = {
        character.get("folder")
        for anime in data.get("anime", [])
        for character in anime.get("characters", [])
    }

    for folder in sorted(ROOT.iterdir(), key=lambda item: item.name.casefold()):
        if not folder.is_dir():
            continue
        if not (folder / "Metadata.json").is_file():
            continue
        if not (folder / "ArchiveIndex.json").is_file():
            continue

        try:
            metadata = json.loads(
                (folder / "Metadata.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            continue

        raw_name = str(metadata.get("name") or folder.name)
        display_name = raw_name.split("/", 1)[0].strip()
        if not display_name:
            display_name = folder.name

        archived_models.append({
            "name": display_name,
            "folder": folder.name,
            "in_library": folder.name in library_folders
        })

    archive_options = "".join(
        f'<option value="{escape(item["folder"], quote=True)}">'
        f'{escape(item["name"])}'
        f'{" ? IN LIBRARY" if item["in_library"] else " ? ARCHIVED"}</option>'
        for item in archived_models
    )

    archive_data = json.dumps(
        archived_models, ensure_ascii=False
    ).replace("<", "\\u003c")

    restore_anime_options = "".join(
        f'<option value="{escape(anime["name"], quote=True)}">'
        f'{escape(anime["name"])}</option>'
        for anime in data.get("anime", [])
    )


    manage_page = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Manage Library</title>
<style>
* { box-sizing: border-box; }
body {
    margin: 0;
    background: #17171d;
    color: #eeeef4;
    font-family: Arial, sans-serif;
    font-size: 14px;
}
header {
    background: #22222b;
    border-bottom: 1px solid #383842;
    padding: 22px 4%;
}
.header-inner {
    max-width: 1100px;
    margin: auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 15px;
}
h1 { margin: 0 0 5px; font-size: 23px; }
.subtitle { color: #999; font-size: 12px; }
.back-link {
    color: #d8c2f4;
    text-decoration: none;
    background: #302a3a;
    border: 1px solid #51465f;
    border-radius: 7px;
    padding: 10px 14px;
    white-space: nowrap;
}
.back-link:hover { background: #40344f; }
main {
    max-width: 1100px;
    margin: 30px auto;
    padding: 0 4%;
}
.intro { color: #aaa; margin: 0 0 22px; line-height: 1.6; }
.panel {
    background: #22222b;
    border: 1px solid #383842;
    border-radius: 10px;
    padding: 22px;
    margin-bottom: 20px;
    box-shadow: 0 8px 25px #0002;
}
.panel h2 { margin: 0 0 8px; font-size: 17px; }
.panel-description {
    color: #999;
    font-size: 12px;
    line-height: 1.6;
    margin: 0 0 18px;
}
.remove-panel { border-top: 3px solid #bd727d; }
.remove-panel h2 { color: #e6a0a0; }
.archive-panel { border-top: 3px solid #a77bea; }
.archive-panel h2 { color: #c9a7ff; }
.form-grid {
    display: grid;
    grid-template-columns: 1fr 1fr auto;
    gap: 10px;
}
select {
    min-width: 0;
    padding: 11px;
    background: #17171d;
    border: 1px solid #494956;
    border-radius: 6px;
    color: white;
    font-size: 13px;
}
button {
    padding: 11px 16px;
    border: 0;
    border-radius: 6px;
    color: white;
    cursor: pointer;
    font-size: 12px;
    font-weight: bold;
    white-space: nowrap;
}
button:disabled { opacity: .4; cursor: not-allowed; }
.remove-button { background: #843f4b; }
.remove-button:hover:not(:disabled) { background: #a34f5d; }
.restore-button { background: #68449a; }
.restore-button:hover:not(:disabled) { background: #8059b5; }
.delete-button { background: #9b2525; }
.delete-button:hover:not(:disabled) { background: #bd3030; }
.status {
    margin-top: 14px;
    color: #aaa;
    font-size: 12px;
    line-height: 1.6;
    white-space: pre-wrap;
}
.warning {
    margin-top: 16px;
    padding: 12px 14px;
    background: #30272a;
    border: 1px solid #594044;
    border-radius: 6px;
    color: #d5a4a4;
    font-size: 12px;
    line-height: 1.6;
}
.move-panel { border-top: 3px solid #65a9a0; }
.move-panel h2 { color: #8ed4c9; }
.move-actions {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr auto;
    gap: 10px;
}
.move-button { background: #347e75; }
.move-button:hover:not(:disabled) { background: #41988d; }

.archive-actions {
    display: grid;
    grid-template-columns: 1fr 1fr auto auto;
    gap: 10px;
}
footer {
    text-align: center;
    padding: 25px;
    color: #666;
    font-size: 11px;
}
@media (max-width: 760px) {
    .form-grid, .archive-actions, .move-actions { grid-template-columns: 1fr; }
    .header-inner { align-items: flex-start; flex-direction: column; }
}
</style>
</head>
<body>
<header>
    <div class="header-inner">
        <div>
            <h1>Manage Library</h1>
            <div class="subtitle">Organize characters, restore archives, and manage storage</div>
        </div>
        <a class="back-link" href="index.html">&#8592; Back to Library</a>
    </div>
</header>

<main>
    <p class="intro">
        Manage the characters in your collection. Removing a character from the library
        keeps its downloaded archive safe. Permanent deletion is a separate action.
    </p>

    <section class="panel remove-panel">
        <h2>Manage Characters</h2>
        <p class="panel-description">
            Remove a character from an anime category without deleting its downloaded
            LoRA files, images, descriptions, or offline page.
        </p>
        <form class="form-grid" id="remove-character-form">
            <select id="remove-anime" required>
                <option value="">Select anime...</option>
                __MANAGE_ANIME_OPTIONS__
            </select>
            <select id="remove-character" required disabled>
                <option value="">Select character...</option>
            </select>
            <button class="remove-button" type="submit" id="remove-button" disabled>
                Remove Character
            </button>
        </form>
        <div class="status" id="remove-status">
            Your downloaded archives are preserved when you remove a character here.
        </div>
    </section>

    <section class="panel move-panel">
        <h2>Move Character</h2>
        <p class="panel-description">
            Move a character from one anime category to another without changing
            or moving any downloaded files.
        </p>
        <div class="move-actions">
            <select id="move-source-anime">
                <option value="">From anime...</option>
            </select>
            <select id="move-character" disabled>
                <option value="">Select character...</option>
            </select>
            <select id="move-target-anime" disabled>
                <option value="">To anime...</option>
            </select>
            <button class="move-button" type="button" id="move-button" disabled>
                Move Character
            </button>
        </div>
        <div class="status" id="move-status">
            Your archive, LoRA files, images, and metadata will remain untouched.
        </div>
    </section>

    <section class="panel archive-panel">
        <h2>Archive &amp; Trash</h2>
        <p class="panel-description">
            Restore archived characters to your library, or permanently delete an
            archive and all of its contents.
        </p>
        <div class="archive-actions">
            <select id="archive-character">
                <option value="">Select an archived character...</option>
                __ARCHIVE_OPTIONS__
            </select>
            <select id="restore-anime">
                <option value="">Restore into anime...</option>
                __RESTORE_ANIME_OPTIONS__
            </select>
            <button class="restore-button" type="button" id="restore-button" disabled>
                Restore to Library
            </button>
            <button class="delete-button" type="button" id="delete-forever-button" disabled>
                Delete Forever
            </button>
        </div>
        <div class="status" id="archive-status">
            Restoring does not download anything again. Permanent deletion cannot be undone.
        </div>
        <div class="warning">
            Permanent deletion removes the selected archive folder, including its LoRA
            files, images, descriptions, metadata, and offline character page.
            You will be asked to confirm twice.
        </div>
    </section>
</main>

<footer>Personal Offline LoRA Library</footer>

<script type="application/json" id="manage-data">__MANAGE_DATA__</script>
<script type="application/json" id="archive-data">__ARCHIVE_DATA__</script>
<script>
const manageData = JSON.parse(document.getElementById("manage-data").textContent);
const archiveData = JSON.parse(document.getElementById("archive-data").textContent);

const animeSelect = document.getElementById("remove-anime");
const characterSelect = document.getElementById("remove-character");
const removeButton = document.getElementById("remove-button");
const removeStatus = document.getElementById("remove-status");

function updateCharacterOptions() {
    const selectedAnime = manageData.find(item => item.anime === animeSelect.value);
    characterSelect.innerHTML = '<option value="">Select character...</option>';

    if (selectedAnime) {
        selectedAnime.characters.forEach(character => {
            const option = document.createElement("option");
            option.value = character.folder;
            option.textContent = character.name;
            characterSelect.appendChild(option);
        });
    }

    characterSelect.disabled = !selectedAnime || selectedAnime.characters.length === 0;
    removeButton.disabled = true;
}
animeSelect.addEventListener("change", updateCharacterOptions);
characterSelect.addEventListener("change", () => {
    removeButton.disabled = !characterSelect.value;
});

document.getElementById("remove-character-form").addEventListener("submit", async event => {
    event.preventDefault();
    const anime = animeSelect.value;
    const folder = characterSelect.value;
    const character = characterSelect.options[characterSelect.selectedIndex].textContent;
    if (!folder) return;

    if (!window.confirm(
        'Are you sure you want to remove "' + character + '" from "' + anime +
        '"?\\n\\nIts downloaded files and archive will NOT be deleted.'
    )) return;

    removeButton.disabled = true;
    removeButton.textContent = "Removing...";
    removeStatus.textContent = "Updating your library...";

    try {
        const response = await fetch("/remove-character", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ anime, folder })
        });
        const result = await response.json();
        if (!response.ok || !result.success) throw new Error(result.error || "Removal failed.");

        removeStatus.textContent = result.character + " was removed from " +
            result.anime + ". Archive preserved. Refreshing...";
        setTimeout(() => window.location.reload(), 1200);
    } catch (error) {
        removeStatus.textContent = "ERROR: " + error.message;
        removeButton.disabled = false;
        removeButton.textContent = "Remove Character";
    }
});


// Move Character controls
const moveSourceSelect = document.getElementById("move-source-anime");
const moveCharacterSelect = document.getElementById("move-character");
const moveTargetSelect = document.getElementById("move-target-anime");
const moveButton = document.getElementById("move-button");
const moveStatus = document.getElementById("move-status");

manageData.forEach(item => {
    const option = document.createElement("option");
    option.value = item.anime;
    option.textContent = item.anime;
    moveSourceSelect.appendChild(option);
});

function updateMoveChoices() {
    const sourceAnime = moveSourceSelect.value;
    const sourceEntry = manageData.find(item => item.anime === sourceAnime);

    moveCharacterSelect.innerHTML = '<option value="">Select character...</option>';
    moveTargetSelect.innerHTML = '<option value="">To anime...</option>';

    if (sourceEntry) {
        sourceEntry.characters.forEach(character => {
            const option = document.createElement("option");
            option.value = character.folder;
            option.textContent = character.name;
            moveCharacterSelect.appendChild(option);
        });
    }

    manageData.filter(item => item.anime !== sourceAnime).forEach(item => {
        const option = document.createElement("option");
        option.value = item.anime;
        option.textContent = item.anime;
        moveTargetSelect.appendChild(option);
    });

    moveCharacterSelect.disabled = !sourceEntry || sourceEntry.characters.length === 0;
    moveTargetSelect.disabled = !sourceEntry || manageData.length < 2;
    moveButton.disabled = true;
}

function updateMoveButton() {
    moveButton.disabled = !(
        moveSourceSelect.value &&
        moveCharacterSelect.value &&
        moveTargetSelect.value &&
        moveSourceSelect.value !== moveTargetSelect.value
    );
}

moveSourceSelect.addEventListener("change", updateMoveChoices);
moveCharacterSelect.addEventListener("change", updateMoveButton);
moveTargetSelect.addEventListener("change", updateMoveButton);

moveButton.addEventListener("click", async () => {
    const sourceAnime = moveSourceSelect.value;
    const targetAnime = moveTargetSelect.value;
    const folder = moveCharacterSelect.value;
    const character = moveCharacterSelect.options[
        moveCharacterSelect.selectedIndex
    ].textContent;

    if (!sourceAnime || !targetAnime || !folder || sourceAnime === targetAnime) return;

    if (!window.confirm(
        'Move "' + character + '" from "' + sourceAnime +
        '" to "' + targetAnime + '"?\\n\\n' +
        'The downloaded archive and all files will remain untouched.'
    )) return;

    moveButton.disabled = true;
    moveButton.textContent = "Moving...";
    moveStatus.textContent = "Updating anime categories...";

    try {
        const response = await fetch("/move-character", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                source_anime: sourceAnime,
                target_anime: targetAnime,
                folder: folder
            })
        });

        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.error || "Move failed.");
        }

        moveStatus.textContent =
            result.character + " was moved from " +
            result.source_anime + " to " + result.target_anime +
            ". Archive preserved. Refreshing...";

        setTimeout(() => window.location.reload(), 1200);
    } catch (error) {
        moveStatus.textContent = "ERROR: " + error.message;
        moveButton.textContent = "Move Character";
        updateMoveButton();
    }
});

const archiveSelect = document.getElementById("archive-character");
const restoreAnimeSelect = document.getElementById("restore-anime");
const restoreButton = document.getElementById("restore-button");
const deleteForeverButton = document.getElementById("delete-forever-button");
const archiveStatus = document.getElementById("archive-status");

function updateArchiveButtons() {
    const selected = archiveData.find(item => item.folder === archiveSelect.value);
    restoreButton.disabled = !selected || selected.in_library || !restoreAnimeSelect.value;
    deleteForeverButton.disabled = !selected;
}
archiveSelect.addEventListener("change", updateArchiveButtons);
restoreAnimeSelect.addEventListener("change", updateArchiveButtons);

restoreButton.addEventListener("click", async () => {
    const folder = archiveSelect.value;
    const anime = restoreAnimeSelect.value;
    const selected = archiveData.find(item => item.folder === folder);
    if (!selected || !anime || selected.in_library) return;

    restoreButton.disabled = true;
    deleteForeverButton.disabled = true;
    archiveStatus.textContent = "Restoring archive to the library...";

    try {
        const response = await fetch("/restore-character", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ folder, anime })
        });
        const result = await response.json();
        if (!response.ok || !result.success) throw new Error(result.error || "Restore failed.");

        archiveStatus.textContent = result.character + " restored to " + result.anime +
            ". Refreshing...";
        setTimeout(() => window.location.reload(), 1200);
    } catch (error) {
        archiveStatus.textContent = "ERROR: " + error.message;
        updateArchiveButtons();
    }
});

deleteForeverButton.addEventListener("click", async () => {
    const folder = archiveSelect.value;
    const selected = archiveData.find(item => item.folder === folder);
    if (!selected) return;

    const confirmed = window.confirm(
        "PERMANENT DELETION WARNING\\n\\nYou are about to permanently delete: " +
        selected.name + "\\n\\nThis removes the entire archive folder, including all " +
        "LoRA files, images, descriptions, metadata and its offline page. " +
        "This cannot be undone.\\n\\nDo you want to continue?"
    );
    if (!confirmed) return;

    const typed = window.prompt(
        'Final confirmation: type DELETE to permanently erase "' + selected.name + '".'
    );
    if (typed !== "DELETE") {
        archiveStatus.textContent = "Deletion cancelled. The archive was not changed.";
        return;
    }

    restoreButton.disabled = true;
    deleteForeverButton.disabled = true;
    archiveStatus.textContent = "Permanently deleting the archive...";

    try {
        const response = await fetch("/delete-character", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ folder })
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.error || "Permanent deletion failed.");
        }

        archiveStatus.textContent = result.character +
            " was permanently deleted. Refreshing...";
        setTimeout(() => window.location.reload(), 1500);
    } catch (error) {
        archiveStatus.textContent = "ERROR: " + error.message;
        updateArchiveButtons();
    }
});
</script>
</body>
</html>
"""

    manage_page = (
        manage_page
        .replace("__MANAGE_ANIME_OPTIONS__", manage_anime_options)
        .replace("__ARCHIVE_OPTIONS__", archive_options)
        .replace("__RESTORE_ANIME_OPTIONS__", restore_anime_options)
        .replace("__MANAGE_DATA__", manage_data)
        .replace("__ARCHIVE_DATA__", archive_data)
    )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">

<title>My Anime LoRA Library</title>

<style>
* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    background: #17171d;
    color: #eeeeF4;
    font-family: Arial, sans-serif;
    font-size: 13px;
}}

header {{
    position: relative;
    background: #22222b;
    padding: 18px 4%;
    border-bottom: 1px solid #383842;
}}

header h1 {{
    font-size: 22px;
    margin: 0 0 5px;
}}

header p {{
    color: #999;
    margin: 0;
    font-size: 12px;
}}

.manage-link {{
    position: absolute;
    right: 4%;
    top: 50%;
    transform: translateY(-50%);
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 9px 13px;
    border: 1px solid #51465f;
    border-radius: 7px;
    background: #302a3a;
    color: #d8c2f4;
    text-decoration: none;
    font-size: 12px;
    font-weight: bold;
    transition: background .15s, border-color .15s;
}}

.manage-link:hover {{
    background: #40344f;
    border-color: #a77bea;
}}

.trash-icon {{
    font-size: 17px;
}}

main {{
    max-width: 1500px;
    margin: auto;
    padding: 18px 4%;
}}

.online-search-panel {{background:#22222b;border:1px solid #49405c;border-radius:7px;padding:15px;margin-bottom:18px}}
.online-search-panel h2 {{margin:0 0 7px;font-size:15px;color:#c9a7ff}}
.online-search-description {{color:#999;font-size:11px;line-height:1.5;margin:0 0 12px}}
.online-search-controls {{display:grid;grid-template-columns:minmax(180px,1fr) 135px 170px 130px auto;gap:9px}}
.online-search-controls input,.online-search-controls select {{min-width:0;padding:10px;background:#17171d;border:1px solid #494956;border-radius:5px;color:white;font-size:12px}}
.online-search-controls button,#load-more-models {{padding:10px 15px;background:#68449a;border:0;border-radius:5px;color:white;cursor:pointer;font-size:12px;font-weight:bold}}
.online-search-controls button:disabled,#load-more-models:disabled {{opacity:.5;cursor:wait}}
.online-search-advanced {{margin-top:10px;color:#bbb;font-size:11px}}
.online-search-advanced summary {{cursor:pointer;color:#c9a7ff;user-select:none}}
.online-search-advanced-fields {{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;align-items:center;padding:10px 0 2px}}
.online-search-advanced-fields input[type="text"] {{min-width:0;padding:8px;background:#17171d;border:1px solid #494956;border-radius:5px;color:white;font-size:11px}}
.online-search-advanced-fields label {{display:flex;align-items:center;gap:6px;white-space:nowrap}}
.online-search-content-preference {{margin-top:10px;padding:9px 10px;background:#20202a;border:1px solid #3a3a48;border-radius:5px;font-size:11px}}
.online-search-content-preference label {{display:flex;align-items:center;gap:7px;color:#ddd}}
@media(max-width:650px) {{.online-search-advanced-fields {{grid-template-columns:1fr}}}}
#civitai-search-status {{margin-top:10px;color:#aaa;font-size:11px;white-space:pre-wrap}}
#civitai-search-results {{display:grid;gap:6px;margin-top:12px}}
.civitai-result {{display:grid;grid-template-columns:58px minmax(0,1fr) auto;gap:12px;align-items:center;padding:8px;background:#1b1b23;border:1px solid #343440;border-radius:5px}}
.civitai-result img {{width:58px;height:68px;object-fit:cover;border-radius:4px;background:#292934}}
.civitai-result-name {{color:#c9a7ff;font-weight:bold;font-size:12px;text-decoration:none}}
.civitai-result-name:hover {{text-decoration:underline}}
.civitai-result-meta {{color:#999;font-size:10px;margin-top:5px}}
.civitai-result-extra {{color:#aaa;font-size:10px;margin-top:4px;line-height:1.5;overflow-wrap:anywhere}}
.civitai-result-tags {{display:flex;flex-wrap:wrap;gap:4px;margin-top:5px}}
.civitai-result-tag {{padding:2px 5px;background:#292934;border:1px solid #3a3a48;border-radius:3px;color:#bdb3cf;font-size:9px}}
.civitai-result-downloads {{color:#ddd;font-size:11px;white-space:nowrap;text-align:right}}
#load-more-models {{display:none;margin-top:10px}}
@media(max-width:850px) {{.online-search-controls {{grid-template-columns:1fr 1fr}}}}
@media(max-width:520px) {{.online-search-controls {{grid-template-columns:1fr}}.civitai-result {{grid-template-columns:46px minmax(0,1fr)}}.civitai-result img {{width:46px;height:58px}}.civitai-result-downloads {{grid-column:2;text-align:left}}}}
.library-stats {{
    color: #999;
    font-size: 11px;
    margin-bottom: 12px;
}}

.add-panel {{
    background: #22222b;
    border: 1px solid #49405c;
    border-radius: 7px;
    padding: 15px;
    margin-bottom: 18px;
}}

.add-panel h2 {{
    margin: 0 0 12px;
    font-size: 15px;
    color: #c9a7ff;
}}

.add-form {{
    display: grid;
    grid-template-columns: 1fr 1fr auto;
    gap: 9px;
}}

.add-form input {{
    min-width: 0;
    padding: 10px;
    background: #17171d;
    border: 1px solid #494956;
    border-radius: 5px;
    color: white;
    font-size: 12px;
}}

.add-form button {{
    padding: 10px 15px;
    background: #68449a;
    border: none;
    border-radius: 5px;
    color: white;
    cursor: pointer;
    font-weight: bold;
    font-size: 12px;
}}

.add-form button:hover {{
    background: #8059b5;
}}

.add-form button:disabled {{
    opacity: .55;
    cursor: wait;
}}

#add-status {{
    margin-top: 10px;
    color: #aaa;
    font-size: 11px;
    white-space: pre-wrap;
}}

@media (max-width: 750px) {{
    header {{
        padding-right: 145px;
    }}

    .manage-link {{
        right: 4%;
        padding: 8px 10px;
    }}

    .manage-link span:last-child {{
        display: none;
    }}

    .add-form {{
        grid-template-columns: 1fr;
    }}
}}

.manage-panel {{
    background: #22222b;
    border: 1px solid #594044;
    border-radius: 7px;
    padding: 15px;
    margin-bottom: 18px;
}}

.manage-panel h2 {{
    margin: 0 0 12px;
    font-size: 15px;
    color: #e6a0a0;
}}

.manage-form {{
    display: grid;
    grid-template-columns: 1fr 1fr auto;
    gap: 9px;
}}

.manage-form select {{
    min-width: 0;
    padding: 10px;
    background: #17171d;
    border: 1px solid #494956;
    border-radius: 5px;
    color: white;
    font-size: 12px;
}}

.manage-form button {{
    padding: 10px 15px;
    background: #843f4b;
    border: none;
    border-radius: 5px;
    color: white;
    cursor: pointer;
    font-weight: bold;
    font-size: 12px;
}}

.manage-form button:hover {{
    background: #a34f5d;
}}

.manage-form button:disabled {{
    opacity: .45;
    cursor: not-allowed;
}}

#remove-status {{
    margin-top: 10px;
    color: #aaa;
    font-size: 11px;
}}

@media (max-width: 750px) {{
    .manage-form {{
        grid-template-columns: 1fr;
    }}
}}

.search-box {{
    width: 100%;
    max-width: 420px;
    padding: 9px 12px;
    background: #252530;
    border: 1px solid #494956;
    border-radius: 5px;
    color: white;
    font-size: 12px;
    outline: none;
    margin-bottom: 16px;
}}

.search-box:focus {{
    border-color: #a77bea;
}}

.anime-section {{
    margin-bottom: 7px;
    background: #22222b;
    border: 1px solid #383842;
    border-radius: 5px;
    overflow: visible;
}}

.anime-section summary {{
    cursor: pointer;
    list-style: none;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    user-select: none;
}}

.anime-section summary::-webkit-details-marker {{
    display: none;
}}

.anime-section summary::before {{
    content: "▶";
    color: #a77bea;
    font-size: 9px;
    transition: transform .15s;
}}

.anime-section[open] summary::before {{
    transform: rotate(90deg);
}}

.anime-section summary:hover {{
    background: #2b2935;
}}

.anime-title {{
    font-size: 13px;
    font-weight: bold;
}}

.count {{
    color: #b99ae8;
    background: #342b45;
    border-radius: 10px;
    padding: 2px 7px;
    font-size: 10px;
    margin-left: auto;
}}

.column-headings,
.character-row {{
    display: grid;
    grid-template-columns: minmax(140px, 1.1fr)
                           minmax(180px, 1.5fr)
                           minmax(100px, .8fr);
    gap: 12px;
    align-items: center;
}}

.column-headings {{
    padding: 6px 12px;
    color: #888;
    font-size: 10px;
    text-transform: uppercase;
    border-top: 1px solid #383842;
    border-bottom: 1px solid #383842;
}}

.character-list {{
    overflow: visible;
}}

.character-row {{
    position: relative;
    padding: 8px 12px;
    min-height: 32px;
    color: #ddd;
    text-decoration: none;
    border-bottom: 1px solid #30303a;
}}

.character-row:last-child {{
    border-bottom: none;
}}

.character-row:hover {{
    background: #302b3b;
}}

.character-name {{
    color: #c9a7ff;
    font-weight: bold;
}}

.checkpoint,
.artist {{
    color: #aaa;
    font-size: 11px;
}}

.hover-preview {{
    display: none;
    position: absolute;
    left: 100%;
    top: -35px;
    width: 170px;
    max-height: 220px;
    object-fit: contain;
    background: #17171d;
    border: 1px solid #a77bea;
    border-radius: 5px;
    padding: 3px;
    z-index: 100;
    box-shadow: 0 5px 20px #000a;
    pointer-events: none;
}}

.character-row:hover .hover-preview {{
    display: block;
}}

#empty-message {{
    display: none;
    color: #aaa;
    padding: 20px 0;
}}

footer {{
    text-align: center;
    padding: 18px;
    color: #666;
    border-top: 1px solid #30303a;
    font-size: 10px;
}}

@media (max-width: 650px) {{
    .column-headings,
    .character-row {{
        grid-template-columns: minmax(90px, 1fr)
                               minmax(100px, 1.2fr);
    }}

    .column-headings span:last-child,
    .character-row .artist {{
        display: none;
    }}

    .hover-preview {{
        left: auto;
        right: 5px;
    }}
}}
</style>
</head>

<body>

<header>
    <h1>My Anime LoRA Library</h1>
    <p>Personal Offline Collection</p>
    <a class="manage-link" href="manage.html" title="Manage characters and archives">
        <span class="trash-icon">&#128465;</span>
        <span>Manage Library</span>
    </a>
</header>

<main>

    <section class="add-panel">
        <h2>+ Add a New Character</h2>

        <form class="add-form" id="add-character-form">
            <input
                type="url"
                id="civitai-url"
                placeholder="Paste Civitai model URL..."
                required
            >

            <input
                type="text"
                id="anime-title"
                list="anime-options"
                placeholder="Anime title (existing or new)..."
                required
            >

            <datalist id="anime-options">
                {anime_options}
            </datalist>

            <button type="submit" id="add-button">
                Add Character & Download
            </button>
        </form>

        <div id="add-status"></div>
    </section>

    <section class="online-search-panel">
        <h2>Search Civitai Models</h2>
        <p class="online-search-description">Civitai finds relevant matches first. Reorder those matches by the available statistics below; changing the ranking never runs a separate popularity search. Sorting applies to results loaded so far, and “Load more” expands the pool. Most Buzz uses Civitai's tipped-amount metric.</p>
        <form class="online-search-controls" id="civitai-search-form">
            <input type="search" id="civitai-search-query" placeholder="Search Civitai models..." required>
            <select id="civitai-model-type" aria-label="Model type">
                <option value="LORA" selected>LoRA</option><option value="All">All model types</option>
                <option value="Checkpoint">Checkpoint</option><option value="TextualInversion">Textual Inversion</option><option value="Controlnet">ControlNet</option>
            </select>
            <select id="civitai-sort-by" aria-label="Rank relevant results">
                <option value="downloads" selected>Most Downloaded</option>
                <option value="likes">Most Liked</option>
                <option value="buzz">Most Buzz (tipped amount)</option>
                <option value="comments">Most Discussed</option>
                <option value="favorites">Most Collected</option>
                <option value="imagesCount">Most Images</option>
                <option value="rating">Highest Rated</option>
                <option value="newest">Newest</option>
                <option value="oldest">Oldest</option>
            </select>
            <select id="civitai-sort-direction" aria-label="Metric sort direction">
                <option value="desc" selected>Highest first</option>
                <option value="asc">Lowest first</option>
            </select>
            <button type="submit" id="civitai-search-button">Search Civitai</button>
        </form>
        <div class="online-search-content-preference">
            <label><input type="checkbox" id="civitai-include-nsfw"> I confirm I am 18 or older and want to view mature content</label>
            <div id="mature-content-status" class="civitai-result-extra">Mature content is off by default. Enabling this setting switches Civitai requests to civitai.red.</div>
        </div>
        <details class="online-search-advanced">
            <summary>Advanced Civitai filters</summary>
            <div class="online-search-advanced-fields">
                <input type="text" id="civitai-base-models" placeholder="Base model(s), comma-separated (e.g. Illustrious, Pony, SDXL 1.0)" aria-label="Base model filter">
                <input type="text" id="civitai-tag-filter" placeholder="Civitai tag (optional)" aria-label="Tag filter">
                <input type="text" id="civitai-creator-filter" placeholder="Creator username (optional)" aria-label="Creator filter">
                <label><input type="checkbox" id="civitai-supports-generation"> Supports Civitai generation</label>
                <label><input type="checkbox" id="civitai-from-platform"> Trained on Civitai</label>
                <label><input type="checkbox" id="civitai-early-access"> Include early-access versions</label>
            </div>
        </details>
        <div id="civitai-search-status"></div><div id="civitai-search-results"></div>
        <button type="button" id="load-more-models">Load more relevant results</button>
    </section>

<div class="library-stats">
        {len(anime_sections)} anime · {total_characters} characters
    </div>

    <input
        class="search-box"
        id="search"
        type="search"
        placeholder="Search anime, characters, checkpoints or artists..."
        oninput="filterLibrary()"
    >

    {''.join(anime_sections)}

    <div id="empty-message">
        No matching anime or characters found.
    </div>
</main>

<footer>Personal Offline LoRA Library</footer>

<script>
document.getElementById("add-character-form").addEventListener("submit", async function(event) {{
    event.preventDefault();

    const url = document.getElementById("civitai-url").value.trim();
    const anime = document.getElementById("anime-title").value.trim();
    const button = document.getElementById("add-button");
    const status = document.getElementById("add-status");

    button.disabled = true;
    button.textContent = "Downloading...";
    status.textContent = "Connecting to Civitai. The download may take some time...";

    try {{
        const response = await fetch("/add-character", {{
            method: "POST",
            headers: {{
                "Content-Type": "application/json"
            }},
            body: JSON.stringify({{ url, anime }})
        }});

        const result = await response.json();

        if (!response.ok || !result.success) {{
            throw new Error(result.error || "The operation failed.");
        }}

        status.textContent =
            "SUCCESS! " + result.model + "\\n" +
            "Anime: " + result.anime + "\\n" +
            "Versions: " + result.versions +
            " | Files: " + result.files +
            " | Images: " + result.images +
            " | Errors: " + result.errors +
            "\\nRefreshing the library...";

        setTimeout(() => window.location.reload(), 1800);

    }} catch (error) {{
        status.textContent = "ERROR: " + error.message;
        button.disabled = false;
        button.textContent = "Add Character & Download";
    }}
}});

const civitaiSearchForm=document.getElementById("civitai-search-form");
const civitaiSearchButton=document.getElementById("civitai-search-button");
const civitaiSearchStatus=document.getElementById("civitai-search-status");
const civitaiResultsElement=document.getElementById("civitai-search-results");
const loadMoreModelsButton=document.getElementById("load-more-models");
const civitaiSortSelect=document.getElementById("civitai-sort-by");
const civitaiSortDirection=document.getElementById("civitai-sort-direction");
let civitaiSearchItems=[],civitaiNextCursor=null,civitaiCurrentQuery="",civitaiCurrentType="LORA",civitaiCurrentFilters={{}};
const matureContentToggle=document.getElementById("civitai-include-nsfw");
const matureContentStatus=document.getElementById("mature-content-status");

async function loadContentPreference() {{
    try {{
        const response=await fetch("/app-settings");
        const settings=await response.json();
        if(!response.ok||!settings.success) throw new Error("Could not load content preferences.");
        matureContentToggle.checked=settings.mature_content_enabled===true;
        matureContentStatus.textContent=matureContentToggle.checked
            ?"Mature content enabled. Civitai requests use civitai.red."
            :"Mature content is off. Civitai requests use civitai.com.";
    }} catch(error) {{matureContentStatus.textContent="Could not load mature-content preference: "+error.message}}
}}

matureContentToggle.addEventListener("change",async()=>{{
    const enabled=matureContentToggle.checked;
    matureContentToggle.disabled=true;
    matureContentStatus.textContent=enabled?"Saving 18+ confirmation and enabling mature content...":"Disabling mature content...";
    try {{
        const response=await fetch("/content-preference",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{enabled,age_confirmed:enabled}})}});
        const result=await response.json();
        if(!response.ok||!result.success) throw new Error(result.error||"Could not save content preference.");
        matureContentStatus.textContent=enabled
            ?"Mature content enabled. New searches use civitai.red."
            :"Mature content disabled. New searches use civitai.com.";
        civitaiSearchItems=[];civitaiNextCursor=null;civitaiResultsElement.replaceChildren();loadMoreModelsButton.style.display="none";
        civitaiSearchStatus.textContent="Content preference changed. Search again to refresh results.";
    }} catch(error) {{
        matureContentToggle.checked=!enabled;
        matureContentStatus.textContent="ERROR: "+error.message;
    }} finally {{matureContentToggle.disabled=false}}
}});
loadContentPreference();

const metricLabels={{
    downloads:"downloads",likes:"likes",buzz:"Buzz tipped",comments:"comments",
    favorites:"collections",imagesCount:"images",rating:"average rating"
}};

function renderCivitaiResults() {{
    const sortBy=civitaiSortSelect.value;
    const direction=civitaiSortDirection.value==="asc"?1:-1;
    const sorted=[...civitaiSearchItems];
    if(sortBy==="newest"||sortBy==="oldest") {{
        const dateDirection=sortBy==="newest"?-1:1;
        sorted.sort((a,b)=>(((Date.parse(a.createdAt||"")||0)-(Date.parse(b.createdAt||"")||0))*dateDirection)||((a._civitaiRank??0)-(b._civitaiRank??0)));
    }} else if(sortBy!=="relevance") {{
        sorted.sort((a,b)=>((Number(a[sortBy]??0)-Number(b[sortBy]??0))*direction)||((a._civitaiRank??0)-(b._civitaiRank??0)));
    }}
    civitaiResultsElement.replaceChildren();
    sorted.forEach(model=>{{
        const row=document.createElement("div");row.className="civitai-result";
        const preview=document.createElement("img");preview.alt="";preview.loading="lazy";
        if(model.preview) preview.src=model.preview;
        preview.onerror=()=>{{preview.style.visibility="hidden"}};
        const details=document.createElement("div"),link=document.createElement("a");
        link.className="civitai-result-name";link.href=model.url;link.target="_blank";link.rel="noopener noreferrer";link.textContent=model.name;
        details.appendChild(link);
        const meta=document.createElement("div");meta.className="civitai-result-meta";
        if(model.creatorUrl) {{
            const creatorLink=document.createElement("a");creatorLink.href=model.creatorUrl;creatorLink.target="_blank";creatorLink.rel="noopener noreferrer";creatorLink.textContent=model.creator;creatorLink.style.color="inherit";creatorLink.style.textDecoration="none";
            meta.append(document.createTextNode(model.type+" · by "),creatorLink);
        }} else {{
            meta.textContent=model.type+" · by "+model.creator;
        }}
        details.appendChild(meta);
        const baseModel=document.createElement("div");baseModel.className="civitai-result-extra";baseModel.textContent="Base model: "+(model.baseModel||"Unknown");details.appendChild(baseModel);
        const tags=Array.isArray(model.tags)?model.tags.filter(tag=>typeof tag==="string"&&tag.trim()).slice(0,5):[];
        if(tags.length) {{
            const tagRow=document.createElement("div");tagRow.className="civitai-result-tags";
            tags.forEach(tag=>{{const chip=document.createElement("span");chip.className="civitai-result-tag";chip.textContent=tag;tagRow.appendChild(chip)}});
            details.appendChild(tagRow);
        }}
        const metric=document.createElement("div");metric.className="civitai-result-downloads";
        if(sortBy==="newest"||sortBy==="oldest") {{
            metric.textContent=model.createdAt?new Date(model.createdAt).toLocaleDateString():"Date unavailable";
        }} else if(sortBy==="rating"&&model.rating==null) {{
            metric.textContent="No rating data";
        }} else {{
            const value=Number(model[sortBy]??0);
            metric.textContent=(sortBy==="rating"?value.toFixed(2):value.toLocaleString())+" "+metricLabels[sortBy];
        }}
        row.append(preview,details,metric);civitaiResultsElement.appendChild(row);
    }});
    loadMoreModelsButton.style.display=civitaiNextCursor?"inline-block":"none";
    const labels={{downloads:"downloads",likes:"likes",buzz:"Buzz tipped",comments:"discussion",favorites:"collections",imagesCount:"image count",rating:"average rating",newest:"newest first",oldest:"oldest first"}};
    const directionLabel=(sortBy==="newest"||sortBy==="oldest")?"":(direction===1?" · lowest first":" · highest first");
    civitaiSearchStatus.textContent="Collected "+civitaiSearchItems.length+" relevant results · sorted by "+labels[sortBy]+directionLabel+".";
    civitaiSortDirection.disabled=sortBy==="newest"||sortBy==="oldest";
}}

async function requestCivitaiModels(cursor=null) {{
    const response=await fetch("/search-models",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{query:civitaiCurrentQuery,cursor,model_type:civitaiCurrentType,filters:civitaiCurrentFilters}})}});
    const result=await response.json();
    if(!response.ok||!result.success) throw new Error(result.error||"Civitai search failed.");
    return result;
}}

civitaiSearchForm.addEventListener("submit",async event=>{{
    event.preventDefault();
    const query=document.getElementById("civitai-search-query").value.trim();if(!query)return;
    civitaiCurrentQuery=query;civitaiCurrentType=document.getElementById("civitai-model-type").value;
    const baseModelText=document.getElementById("civitai-base-models").value.trim();
    civitaiCurrentFilters={{
        base_models:baseModelText,
        tag:document.getElementById("civitai-tag-filter").value.trim(),
        username:document.getElementById("civitai-creator-filter").value.trim(),
        supports_generation:document.getElementById("civitai-supports-generation").checked,
        from_platform:document.getElementById("civitai-from-platform").checked,
        early_access:document.getElementById("civitai-early-access").checked
    }};
    civitaiSearchItems=[];civitaiNextCursor=null;civitaiResultsElement.replaceChildren();loadMoreModelsButton.style.display="none";
    civitaiSearchButton.disabled=true;loadMoreModelsButton.disabled=true;civitaiSearchStatus.textContent="Searching Civitai by relevance...";
    try {{
        const result=await requestCivitaiModels();civitaiSearchItems=(result.items||[]).map((item,index)=>({...item,_civitaiRank:index}));civitaiNextCursor=result.nextCursor||null;
        if(civitaiSearchItems.length)renderCivitaiResults();else civitaiSearchStatus.textContent="No matching models were found.";
    }} catch(error) {{civitaiSearchStatus.textContent="ERROR: "+error.message}}
    finally {{civitaiSearchButton.disabled=false;loadMoreModelsButton.disabled=false}}
}});

loadMoreModelsButton.addEventListener("click",async()=>{{
    if(!civitaiNextCursor)return;
    loadMoreModelsButton.disabled=true;civitaiSearchStatus.textContent="Loading the next page of relevance-ranked results...";
    try {{
        const result=await requestCivitaiModels(civitaiNextCursor);const rankOffset=civitaiSearchItems.length;civitaiSearchItems.push(...(result.items||[]).map((item,index)=>({...item,_civitaiRank:rankOffset+index})));civitaiNextCursor=result.nextCursor||null;
        renderCivitaiResults();
    }} catch(error) {{civitaiSearchStatus.textContent="ERROR: "+error.message}}
    finally {{loadMoreModelsButton.disabled=false}}
}});
civitaiSortSelect.addEventListener("change",()=>{{if(civitaiSearchItems.length)renderCivitaiResults()}});
civitaiSortDirection.addEventListener("change",()=>{{if(civitaiSearchItems.length)renderCivitaiResults()}});

function filterLibrary() {{
    const query = document.getElementById("search")
        .value.toLowerCase().trim();

    let visibleSections = 0;

    document.querySelectorAll(".anime-section").forEach(section => {{
        let visibleRows = 0;

        section.querySelectorAll(".character-row").forEach(row => {{
            const matches = row.dataset.search.includes(query);
            row.style.display = matches ? "grid" : "none";

            if (matches) visibleRows++;
        }});

        section.style.display = visibleRows ? "" : "none";
        section.open = query.length > 0 && visibleRows > 0;

        if (visibleRows) visibleSections++;
    }});

    document.getElementById("empty-message").style.display =
        visibleSections === 0 ? "block" : "none";
}}
</script>

</body>
</html>
"""

    output = ROOT / "index.html"
    output.write_text(page, encoding="utf-8")

    manage_output = ROOT / "manage.html"
    manage_output.write_text(manage_page, encoding="utf-8")

    print("\n======================================")
    print("       LIBRARY GENERATED")
    print("======================================")
    print("Anime:", len(anime_sections))
    print("Characters:", total_characters)
    print("Output:", output.resolve())
    print("======================================")


if __name__ == "__main__":
    generate()