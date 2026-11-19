param(
    [Parameter(Mandatory=$true)]
    [string]$TargetRoot
)

$ErrorActionPreference = "Stop"
$SourceRoot = "C:\CivitaiDownloader"

foreach ($folder in @("config", "downloads", "logs")) {
    $source = Join-Path $SourceRoot $folder
    $target = Join-Path $TargetRoot $folder

    if (!(Test-Path -LiteralPath $source)) {
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
