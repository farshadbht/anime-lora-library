param(
    [Parameter(Mandatory = $true)]
    [string]$TargetRoot,

    [string]$SourceRoot = ""
)

$ErrorActionPreference = "Stop"

# No previous installation selected: skip migration.
if ([string]::IsNullOrWhiteSpace($SourceRoot)) {
    Write-Host "No previous installation selected. Skipping migration."
    exit 0
}

$SourceRoot = [System.IO.Path]::GetFullPath($SourceRoot).TrimEnd('\')
$TargetRoot = [System.IO.Path]::GetFullPath($TargetRoot).TrimEnd('\')

# Prevent copying a folder into itself.
if ($SourceRoot -eq $TargetRoot) {
    Write-Host "Source and destination are identical. Skipping migration."
    exit 0
}

if (!(Test-Path -LiteralPath $SourceRoot -PathType Container)) {
    Write-Host "Previous installation folder not found. Skipping migration."
    exit 0
}

Write-Host "Migrating data from: $SourceRoot"
Write-Host "Migrating data to:   $TargetRoot"

foreach ($folder in @("config", "downloads", "logs")) {
    $source = Join-Path $SourceRoot $folder
    $target = Join-Path $TargetRoot $folder

    if (!(Test-Path -LiteralPath $source -PathType Container)) {
        continue
    }

    New-Item -ItemType Directory -Force -Path $target | Out-Null

    $copied = 0
    $skipped = 0

    Get-ChildItem -LiteralPath $source -Force -Recurse | ForEach-Object {
        $relative = $_.FullName.Substring($source.Length).TrimStart('\')
        $destination = Join-Path $target $relative

        if ($_.PSIsContainer) {
            New-Item -ItemType Directory -Force -Path $destination | Out-Null
        }
        elseif (Test-Path -LiteralPath $destination) {
            $skipped++
        }
        else {
            $parent = Split-Path $destination -Parent
            New-Item -ItemType Directory -Force -Path $parent | Out-Null

            Copy-Item -LiteralPath $_.FullName -Destination $destination
            $copied++
        }
    }

    Write-Host "$folder : copied $copied files; skipped $skipped existing files."
}

Write-Host "Migration completed."
