
import json
import html
from pathlib import Path
from urllib.parse import quote


def read_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def generate_offline_site(model_folder):
    root = Path(model_folder)

    model = read_json(root / "Metadata.json")
    archive = read_json(root / "ArchiveIndex.json")

    model_name = model.get("name", "Unknown Model")
    creator = model.get("creator") or {}

    creator_name = creator.get("username", "Unknown Creator")
    creator_avatar = creator.get("image", "")

    # Build the creator's Civitai profile URL
    creator_url = (
        f"https://civitai.com/user/{quote(str(creator_name), safe='')}"
    )

    description_path = root / "Description" / "Description.html"

    if description_path.exists():
        description = description_path.read_text(encoding="utf-8")
    else:
        description = "<p>No description available.</p>"

    versions_html = []
    gallery_html = []

    for version in archive.get("versions", []):

        version_id = version["id"]
        version_name = version.get("name", "Version")

        version_folder = root / "Versions" / (
            f"{version_name} [{version_id}]"
        )

        # Load version metadata
        version_metadata_path = version_folder / "VersionMetadata.json"

        if version_metadata_path.exists():
            version_metadata = read_json(version_metadata_path)
        else:
            version_metadata = {}

        # Extract trigger words
        trained_words = version_metadata.get("trainedWords") or []

        trigger_words = []

        for word in trained_words:
            if isinstance(word, dict):
                word = word.get("word") or word.get("name")

            if word:
                trigger_words.append(str(word))

        trigger_html = "".join(
            f'<span class="trigger-word">{html.escape(word)}</span>'
            for word in trigger_words
        )

        # Version selector
        versions_html.append(
            f'<option value="{version_id}">'
            f'{html.escape(version_name)}</option>'
        )

        # Image directories
        images_folder = version_folder / "Images"
        metadata_folder = version_folder / "Image_Metadata"

        images = sorted(
            path for path in images_folder.iterdir()
            if path.is_file()
        ) if images_folder.exists() else []

        image_cards = []

        # Generate individual image cards
        for index, image_path in enumerate(images, 1):

            metadata_path = metadata_folder / f"image_{index:03d}.json"

            metadata = {}

            if metadata_path.exists():
                metadata = read_json(metadata_path)

            meta = metadata.get("meta") or {}

            prompt = html.escape(
                str(meta.get("prompt") or "Not available")
            )

            negative = html.escape(
                str(meta.get("negativePrompt") or "Not available")
            )

            details = {
                "Seed": meta.get("seed", "N/A"),
                "Checkpoint": meta.get("Model", "N/A"),
                "Steps": meta.get("steps", "N/A"),
                "Sampler": meta.get("sampler", "N/A"),
                "CFG Scale": meta.get("cfgScale", "N/A"),
                "Width": meta.get("width", "N/A"),
                "Height": meta.get("height", "N/A"),
            }

            detail_html = "".join(
                f"<div><b>{html.escape(str(key))}:</b> "
                f"{html.escape(str(value))}</div>"
                for key, value in details.items()
            )

            image_url = image_path.relative_to(root).as_posix()

            image_cards.append(f"""
            <article class="image-card">

                <img
                    src="{html.escape(image_url, quote=True)}"
                    onclick="openViewer(this.src)"
                    loading="lazy"
                >

                <div class="image-info">

                    <h3>Image {index}</h3>

                    <details>
                        <summary>Generation Information</summary>

                        <div class="details">
                            {detail_html}
                        </div>

                        <div class="prompt-block">

                            <div class="prompt-heading">
                                <h4>Positive Prompt</h4>
                                <button onclick="copyPrompt(this)">Copy</button>
                            </div>

                            <pre>{prompt}</pre>

                        </div>

                        <div class="prompt-block">

                            <div class="prompt-heading">
                                <h4>Negative Prompt</h4>
                                <button onclick="copyPrompt(this)">Copy</button>
                            </div>

                            <pre>{negative}</pre>

                        </div>

                    </details>

                </div>
            </article>
            """)

        # Each version gets its own gallery and trigger words
        gallery_html.append(f"""
        <section class="version-content" id="version-{version_id}">

            <h2>{html.escape(version_name)}</h2>

            <div class="gallery">
                {''.join(image_cards)}
            </div>

            <div class="trigger-section">

                <div class="trigger-heading">
                    <h3>Trigger Words</h3>

                    <button
                        class="copy-trigger-button"
                        onclick="copyTriggerWords(this)"
                        {"disabled" if not trigger_words else ""}
                    >
                        Copy All
                    </button>
                </div>

                <div class="trigger-list">
                    {trigger_html if trigger_html else '<span>No trigger words available.</span>'}
                </div>

            </div>

        </section>
        """)

    # Creator avatar
    avatar_html = ""

    if creator_avatar:
        avatar_html = (
            f'<img class="avatar" '
            f'src="{html.escape(creator_avatar, quote=True)}">'
        )

    # Keep the folder name as data for the local folder-opening endpoint.
    model_folder_name = json.dumps(root.name)

    # Generate complete HTML page
    page = f"""<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">

<title>{html.escape(model_name)}</title>

<style>

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    background: #17171d;
    color: #eeeeF4;
    font-family: Arial, sans-serif;
}}

header {{
    background: #22222b;
    padding: 22px 5%;
    border-bottom: 1px solid #383842;
}}

.header-actions {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
    margin-bottom: 18px;
}}

.back-button,
.open-folder-button {{
    display: inline-block;
    margin-bottom: 0;
    padding: 9px 15px;
    background: #49316b;
    color: white;
    text-decoration: none;
    border-radius: 7px;
    font-size: 13px;
    transition: background 0.2s;
}}

.back-button:hover,
.open-folder-button:hover {{
    background: #68449a;
}}

.open-folder-button {{
    padding: 9px 15px;
    background: #347e75;
    color: white;
    border: 0;
    border-radius: 7px;
    font-size: 13px;
    cursor: pointer;
    transition: background 0.2s;
}}

.open-folder-button:hover {{
    background: #41988d;
}}

h1 {{
    margin: 0 0 15px;
    font-size: 28px;
}}

.creator {{
    display: flex;
    align-items: center;
    gap: 12px;
    color: #aaa;
}}

.creator a {{
    color: #c9a7ff;
    text-decoration: none;
}}

.creator a:hover {{
    color: #e4caff;
    text-decoration: underline;
}}

.avatar {{
    width: 42px;
    height: 42px;
    border-radius: 50%;
    object-fit: cover;
}}

main {{
    max-width: 1400px;
    margin: auto;
    padding: 25px;
}}

.panel {{
    background: #22222b;
    padding: 22px;
    border-radius: 10px;
    margin-bottom: 25px;
}}

.description {{
    line-height: 1.7;
    overflow-wrap: anywhere;
}}

.description img {{
    max-width: 100%;
    height: auto;
}}

.description a {{
    color: #8c9eff;
}}

select {{
    background: #30303b;
    color: white;
    border: 1px solid #555;
    padding: 12px;
    border-radius: 7px;
    min-width: 220px;
}}

.gallery {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
    gap: 18px;
}}

.image-card {{
    background: #252530;
    border-radius: 10px;
    overflow: hidden;
}}

.image-card img {{
    width: 100%;
    display: block;
    cursor: zoom-in;
}}

.image-info {{
    padding: 14px;
}}

details {{
    margin-top: 12px;
}}

summary {{
    cursor: pointer;
    color: #a9b4ff;
}}

.details {{
    line-height: 1.8;
    margin-top: 12px;
}}

pre {{
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    background: #17171d;
    padding: 12px;
    border-radius: 7px;
    font-size: 12px;
}}

.trigger-section {{
    background: #292438;
    padding: 16px;
    border-radius: 9px;
    margin: 20px 0;
}}

.trigger-heading {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 12px;
}}

.trigger-section h3 {{
    margin: 0;
    color: #c9a7ff;
}}

.trigger-list {{
    display: flex;
    flex-wrap: wrap;
    gap: 9px;
}}

.trigger-word {{
    background: #49316b;
    color: #e4caff;
    padding: 7px 12px;
    border-radius: 7px;
    font-size: 13px;
}}

.copy-trigger-button,
.prompt-heading button {{
    background: #49316b;
    color: white;
    border: none;
    padding: 7px 13px;
    border-radius: 6px;
    cursor: pointer;
    white-space: nowrap;
}}

.copy-trigger-button:hover,
.prompt-heading button:hover {{
    background: #68449a;
}}

.copy-trigger-button:disabled {{
    opacity: 0.45;
    cursor: not-allowed;
}}

.prompt-block {{
    margin-top: 15px;
}}

.prompt-heading {{
    display: flex;
    align-items: center;
    justify-content: space-between;
}}

#viewer {{
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,.95);
    z-index: 100;
    justify-content: center;
    align-items: center;
    cursor: zoom-out;
}}

#viewer img {{
    max-width: 95%;
    max-height: 95%;
    object-fit: contain;
}}

.version-content {{
    display: none;
}}

.version-content.active {{
    display: block;
}}

footer {{
    text-align: center;
    padding: 30px;
    color: #888;
}}

</style>

</head>

<body>

<header>

    <div class="header-actions">
        <a class="back-button" href="../index.html">&#8592; Back to Library</a>
        <button class="open-folder-button" type="button"
                onclick="openModelFolder(this)">Open LoRA Folder</button>
    </div>

    <h1>{html.escape(model_name)}</h1>

    <div class="creator">
        {avatar_html}
        <span>
            Created by
            <a href="{html.escape(creator_url, quote=True)}"
               target="_blank"
               rel="noopener noreferrer">
                <b>{html.escape(creator_name)}</b>
            </a>
        </span>
    </div>

</header>

<main>

    <section class="panel">

        <h2>Model Versions</h2>

        <select id="versionSelector" onchange="changeVersion(this.value)">
            {''.join(versions_html)}
        </select>

    </section>

    {''.join(gallery_html)}

    <section class="panel">

        <h2>Model Description</h2>

        <div class="description">
            {description}
        </div>

    </section>

</main>

<div id="viewer" onclick="closeViewer()">
    <img id="viewerImage" src="">
</div>

<footer>
    Offline model archive · Generated by Civitai Downloader
</footer>

<script>

const MODEL_FOLDER = {model_folder_name};

async function openModelFolder(button) {{
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = "Opening...";

    try {{
        const response = await fetch("/open-folder", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{ folder: MODEL_FOLDER }})
        }});
        const result = await response.json();

        if (!response.ok || !result.success) {{
            throw new Error(result.error || "Could not open the model folder.");
        }}

        button.textContent = "Folder Opened";
    }} catch (error) {{
        alert(error.message || "Could not open the model folder.");
        button.textContent = originalText;
    }} finally {{
        button.disabled = false;
    }}
}}

async function copyText(text, button) {{

    try {{

        if (navigator.clipboard && window.isSecureContext) {{

            await navigator.clipboard.writeText(text);

        }} else {{

            const textarea = document.createElement("textarea");

            textarea.value = text;
            textarea.style.position = "fixed";
            textarea.style.opacity = "0";

            document.body.appendChild(textarea);
            textarea.select();

            const success = document.execCommand("copy");

            textarea.remove();

            if (!success) {{
                throw new Error("Copy failed");
            }}

        }}

        const originalText = button.textContent;

        button.textContent = "Copied!";

        setTimeout(() => {{
            button.textContent = originalText;
        }}, 1500);

    }} catch (error) {{

        button.textContent = "Copy failed";

    }}

}}

async function copyPrompt(button) {{

    const prompt = button
        .closest(".prompt-block")
        .querySelector("pre").innerText;

    await copyText(prompt, button);

}}

async function copyTriggerWords(button) {{

    const section = button.closest(".trigger-section");

    const words = Array.from(
        section.querySelectorAll(".trigger-word")
    ).map(word => word.textContent.trim());

    const text = words.join(", ");

    if (text) {{
        await copyText(text, button);
    }}

}}

function changeVersion(id) {{

    document.querySelectorAll(".version-content").forEach(section => {{
        section.classList.remove("active");
    }});

    const selected = document.getElementById("version-" + id);

    if (selected) {{
        selected.classList.add("active");
    }}

}}

function openViewer(src) {{

    document.getElementById("viewerImage").src = src;

    document.getElementById("viewer").style.display = "flex";

}}

function closeViewer() {{

    document.getElementById("viewer").style.display = "none";

}}

const selector = document.getElementById("versionSelector");

if (selector.options.length > 0) {{
    changeVersion(selector.value);
}}

</script>

</body>
</html>
"""

    output = root / "index.html"

    output.write_text(page, encoding="utf-8")

    return output


if __name__ == "__main__":

    import sys

    if len(sys.argv) > 1:
        folder = Path(sys.argv[1])
    else:
        folder = Path(input("Model folder: ").strip().strip('"'))

    result = generate_offline_site(folder)

    print("\nOffline website created:")
    print(result)
