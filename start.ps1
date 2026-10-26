param([switch]$NoBrowser,[switch]$FakeDns)
$ErrorActionPreference='Stop'
$executable=Join-Path $PSScriptRoot '.runtime/reference/Scripts/python.exe'
if(!(Test-Path -LiteralPath $executable)){throw 'Run setup.ps1 first'}
$arguments=@('-B','-X','utf8',(Join-Path $PSScriptRoot 'launch.py'))
if($NoBrowser){$arguments+='--no-browser'}
if($FakeDns){$arguments+='--fake-dns'}
& $executable @arguments
exit $LASTEXITCODE
