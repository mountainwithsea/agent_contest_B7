$ErrorActionPreference='Stop'
Push-Location -LiteralPath $PSScriptRoot
$previousPath=$env:PYTHONPATH
try{
 $python=Join-Path $PSScriptRoot '.runtime/reference/Scripts/python.exe'
 $env:PYTHONPATH="$PSScriptRoot;$(Join-Path $PSScriptRoot 'reference-checker')"
 foreach($directory in @('tests','reference-checker/tests')){
  & $python -B -X utf8 -m unittest discover -s $directory
  if($LASTEXITCODE){throw ('Tests failed: '+$directory)}
 }
 if(Get-Command node -ErrorAction SilentlyContinue){
  & node --test release/tests/*.test.cjs
  if($LASTEXITCODE){throw 'Desktop tests failed'}
 }
}finally{$env:PYTHONPATH=$previousPath;Pop-Location}
