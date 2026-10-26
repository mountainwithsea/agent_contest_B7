$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$node = (Get-Command node -ErrorAction Stop).Source
$npm = Join-Path (Split-Path $node) 'node_modules/npm/bin/npm-cli.js'
if (!(Test-Path -LiteralPath $npm)) { throw 'Build requires Node.js with npm.' }
if (!(Test-Path -LiteralPath 'node_modules')) { & $node $npm ci --no-audit --no-fund; if ($LASTEXITCODE) { throw 'npm ci failed' } }
if (!(Test-Path -LiteralPath 'node_modules/electron/dist/electron.exe')) { & $node node_modules/electron/install.js; if ($LASTEXITCODE) { throw 'Electron install failed' } }
& $node --test tests/*.test.cjs
if ($LASTEXITCODE) { throw 'Desktop tests failed' }
$python = Join-Path $PSScriptRoot '../.runtime/reference/Scripts/python.exe'
& $python -X utf8 build_payload.py
if ($LASTEXITCODE) { throw 'Payload staging failed' }
$env:CSC_IDENTITY_AUTO_DISCOVERY='false'
& $node node_modules/electron-builder/cli.js --win nsis zip --x64
if ($LASTEXITCODE) { throw 'Installer build failed' }
Copy-Item -LiteralPath '老师使用说明.txt' -Destination 'artifacts/老师使用说明.txt'
Get-ChildItem -LiteralPath artifacts -File | Where-Object { $_.Extension -in '.exe','.zip' } | ForEach-Object { '{0}  {1}' -f (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Name } | Set-Content -LiteralPath artifacts/SHA256SUMS.txt -Encoding utf8
