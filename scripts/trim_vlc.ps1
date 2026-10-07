param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Destination
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $Source)) { throw "VLC installation not found at $Source" }
if (Test-Path $Destination) { Remove-Item $Destination -Recurse -Force }
Copy-Item -Path $Source -Destination $Destination -Recurse

# RelayView only uses VLC as an embedded network/RTSP playback engine. Remove
# components that are unrelated to that job while keeping codec, demux,
# packetizer, access, audio/video output and hardware acceleration plugins.
$remove = @(
    "locale",
    "lua",
    "skins",
    "sdk",
    "plugins\visualization",
    "plugins\services_discovery",
    "plugins\control",
    "plugins\notify",
    "plugins\keystore"
)

foreach ($relative in $remove) {
    $path = Join-Path $Destination $relative
    if (Test-Path $path) { Remove-Item $path -Recurse -Force }
}

# Packaging/docs that are not required at runtime.
Get-ChildItem $Destination -File -ErrorAction SilentlyContinue | Where-Object {
    $_.Extension -in @(".txt", ".html") -or $_.Name -in @("NEWS", "README", "THANKS", "AUTHORS")
} | Remove-Item -Force -ErrorAction SilentlyContinue

$bytes = (Get-ChildItem $Destination -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host ("Trimmed VLC runtime: {0:N1} MB" -f ($bytes / 1MB))
