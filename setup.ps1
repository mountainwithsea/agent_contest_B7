param([string]$Python='python')
$ErrorActionPreference='Stop'
& $Python -c "import sys; assert sys.version_info >= (3,13), 'Python 3.13+ required'"
if($LASTEXITCODE){throw 'Python 3.13+ required'}
$environment=Join-Path $PSScriptRoot '.runtime/reference'
$executable=Join-Path $environment 'Scripts/python.exe'
if(!(Test-Path -LiteralPath $executable)){
 & $Python -m venv $environment
 if($LASTEXITCODE){throw 'Virtual environment creation failed'}
}
& $executable -m pip install -r (Join-Path $PSScriptRoot 'reference-checker/requirements.lock.txt')
if($LASTEXITCODE){throw 'Dependency installation failed'}
if(!(Test-Path -LiteralPath (Join-Path $PSScriptRoot '.env'))){Copy-Item -LiteralPath (Join-Path $PSScriptRoot '.env.example') -Destination (Join-Path $PSScriptRoot '.env')}
Write-Host 'Ready. Fill your own API keys in .env, then run start.ps1.'
