param([string]$Destination = '.cache\mpv-runtime')
$ErrorActionPreference = 'Stop'
# Pinned upstream libmpv build. Revision and upstream published SHA256 are checked.
# Source: https://github.com/shinchiro/mpv-winbuild-cmake/releases/tag/20261008
$asset = 'mpv-dev-x86_64-20261008-git-36bf3d5290.7z'
$expected = '1e94b722d9d1b701406250c73ee37d73cd0045cdf47bdd7a54f2bea1b513465f'
$stage = Join-Path $env:RUNNER_TEMP 'relayview-mpv-download'
New-Item -ItemType Directory -Path $stage -Force | Out-Null
& gh release download 20261008 --repo shinchiro/mpv-winbuild-cmake --pattern $asset --dir $stage --clobber
if ($LASTEXITCODE -ne 0) { throw 'Could not fetch pinned libmpv release' }
$archive = Join-Path $stage $asset
$actual = (Get-FileHash -Algorithm SHA256 $archive).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw "libmpv checksum mismatch: $actual" }
$extract = Join-Path $stage 'extracted'
New-Item -ItemType Directory -Path $extract -Force | Out-Null
$sevenZip = Join-Path $env:ProgramFiles '7-Zip\7z.exe'
if (!(Test-Path $sevenZip)) { throw '7-Zip not available on this runner' }
& $sevenZip x -y "-o$extract" $archive | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'libmpv extraction failed' }
$dll = Get-ChildItem $extract -Filter 'libmpv-2.dll' -File -Recurse | Select-Object -First 1
if (!$dll) { throw 'The selected upstream package does not contain libmpv-2.dll' }
New-Item -ItemType Directory -Path $Destination -Force | Out-Null
# Copy all runtime DLLs that share libmpv's directory (not development import libs).
Get-ChildItem $dll.DirectoryName -Filter '*.dll' -File | ForEach-Object {
  Copy-Item $_.FullName (Join-Path $Destination $_.Name) -Force
}
if (!(Test-Path (Join-Path $Destination 'libmpv-2.dll'))) { throw 'DLL copy failed' }
Write-Host "Prepared libmpv runtime: $((Get-ChildItem $Destination -Filter '*.dll').Count) DLL(s)"
