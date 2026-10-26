"""Native upstream Ruby formatter plus local CLD3 WASM; no network."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import hashlib
from b7_shared.config import formatter_home, node_executable, ROOT as SUITE_ROOT

ROOT=Path(__file__).resolve().parents[1]

def runtime_paths():
    deps=formatter_home()
    return deps, deps/'rubyinstaller-3.3.12-2-x64/bin/ruby.exe', node_executable()

def fingerprint(mode='local'):
    if mode=='remote':return {}
    if mode!='local':raise ValueError('Unknown AnyStyle format mode')
    deps,ruby,node=runtime_paths()
    paths=list(deps.glob('*.gem'))+[deps/'package-lock.json',ruby,node]
    # Hash unpacked formatter gems, not every unused Ruby standard-library file.
    paths+=[p for gem in deps.iterdir() if gem.is_dir() and gem.name!='rubyinstaller-3.3.12-2-x64' for p in (gem/'lib').rglob('*.rb')]
    paths+=list((deps/'node_modules/cld3-asm').rglob('*.wasm'))
    return {str(p.relative_to(SUITE_ROOT)) if p.is_relative_to(SUITE_ROOT) else str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}

def convert(segments):
    begin=time.perf_counter()
    deps,ruby,node=runtime_paths()
    env=dict(os.environ,B7_ANYSTYLE_HOME=str(deps))
    def run(cmd,data):
        child_env=dict(env)
        child_env.pop('ELECTRON_RUN_AS_NODE',None)
        if str(cmd[0])==str(node) and env.get('B7_NODE_IS_ELECTRON')=='1':child_env['ELECTRON_RUN_AS_NODE']='1'
        p=subprocess.run(cmd,input=json.dumps(data,ensure_ascii=False),text=True,encoding='utf-8',capture_output=True,timeout=40,env=child_env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if p.returncode or p.stderr.strip():raise RuntimeError('Local formatter failed: '+p.stderr[:1200])
        return json.loads(p.stdout)
    result=run([str(ruby),'-EUTF-8',str(ROOT/'ref_app/format_anystyle.rb')],segments)
    languages=run([node,str(ROOT/'ref_app/format_locale.cjs')],result['locale_samples'])
    if len(result['csl'])!=len(segments) or len(languages)!=len(segments):raise ValueError('Local formatter row alignment')
    for row,language in zip(result['csl'],languages):
        if language is not None:row.setdefault('language',language['language'])
    result['language_predictions']=languages
    result['seconds']=time.perf_counter()-begin
    result['implementation']='AnyStyle 1.5.0 native normalizers/CSL + cld3-asm 4.0.0; no parsing model'
    return result
