<#
    build_raw_lotm.ps1 – Prepare Lord-of-the-Mysteries raws for ProseForge.
    Run from repo root:  powershell -ExecutionPolicy Bypass -File scripts/build_raw_lotm.ps1
#>

$ErrorActionPreference = "Stop"

$RAW   = Join-Path $PSScriptRoot "..\data\raw\lotm" | Resolve-Path
$JSON  = Join-Path $RAW "json"
$ZIP   = Join-Path $RAW "Lord Of The Mysteries (json).zip"

# 1 ─── Unzip if needed ────────────────────────────────────────────────────────
if (Test-Path $ZIP) {
    Expand-Archive -Path $ZIP -DestinationPath $JSON -Force
}

# 2 ─── Flatten Volume folders ────────────────────────────────────────────────
Get-ChildItem $JSON -Recurse -File -Filter *.json |
    Where-Object { $_.Directory.Name -like 'Volume *' } |
    Move-Item -Destination { Join-Path $JSON $_.Name } -Force

Get-ChildItem $JSON -Directory | Remove-Item -Recurse -Force

# 3 ─── Merge → lotm_full.json  (utf8NoBOM!) ──────────────────────────────────
$chapters = Get-ChildItem $JSON -File -Filter *.json |
            Sort-Object Name |
            ForEach-Object { Get-Content $_ -Raw | ConvertFrom-Json }

$chapters | ConvertTo-Json -Depth 5 |
           Set-Content (Join-Path $RAW "lotm_full.json") -Encoding utf8NoBOM

Write-Host "✔ Wrote $($chapters.Count) chapters to lotm_full.json"

# 4 ─── Clean up EPUB names (pure cosmetics) ──────────────────────────────────
Get-ChildItem (Join-Path $RAW "epub") -File -Filter "*.epub" | ForEach-Object {
    $new = $_.Name -replace 'Lord Of The Mysteries Chapter ', 'lotm_' `
                   -replace '[() ]', ''
    Rename-Item $_.FullName -NewName $new
}
Write-Host "✔ EPUB filenames slimmed"
