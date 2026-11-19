# Anime LoRA Library

A Windows desktop application for discovering, downloading, organizing, and browsing AI image-generation models from Civitai, with a focus on LoRA models.

## Features

- Download models and their associated files from Civitai.
- Organize downloaded models into a local library.
- Browse model descriptions, versions, images, and generation metadata offline.
- Search and manage characters in the local library.
- Archive, restore, move, and permanently delete library entries.
- Desktop interface built with Python and PyWebView.

## Project Structure

```text
anime-lora-library/
├── installer/
│   ├── AnimeLoRALibrary.iss
│   └── MigrateData.ps1
├── src/
│   ├── api.py
│   ├── desktop_app.py
│   ├── downloader.py
│   ├── generate_library.py
│   ├── inspect_model.py
│   ├── library_server.py
│   ├── offline_site.py
│   ├── organizer.py
│   └── test_download.py
├── requirements.txt
└── README.md
```

## Requirements

- Windows 10 or later
- Python 3.11
- A Civitai API key for authenticated downloads
- Internet connection for discovering and downloading models

## Installation

Clone the repository:

```powershell
git clone https://github.com/farshadbht/anime-lora-library.git
cd anime-lora-library
```

Create a virtual environment:

```powershell
python -m venv .venv
```

Install dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Install Playwright browser components if needed:

```powershell
.\.venv\Scripts\python.exe -m playwright install
```

## Configuration

On first launch, the application initializes its local configuration and data directories.

Add your Civitai API key through the application's configuration file:

```text
config/settings.json
```

**Never commit your API key or personal configuration files to GitHub.**

## Running the Application

Launch the desktop application:

```powershell
.\.venv\Scripts\python.exe .\src\desktop_app.py
```

## Building the Windows Application

The project uses PyInstaller to package the desktop application.

```powershell
.\.venv\Scripts\python.exe -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name AnimeLoRALibrary `
    --collect-all webview `
    .\src\desktop_app.py
```

The packaged application will be generated inside:

```text
dist/AnimeLoRALibrary/
```

## Data and Privacy

The following directories are intended for local use and should not be committed:

- `config/` — API keys and application settings
- `downloads/` — downloaded models and library data
- `logs/` — application logs
- `.venv/` — Python virtual environment
- `dist/` and `build/` — generated build files

## License

No license has been specified yet.
