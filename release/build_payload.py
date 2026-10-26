"""Allowlist-only, reproducible runtime staging; never copy the workspace .env/data."""
import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
PAYLOAD=HERE/'staging/payload'
SKIP={'__pycache__','.pytest_cache','.git','tests','test','pip','setuptools','_distutils_hack'}

def include_payload(relative):
    parts=Path(relative).as_posix().split('/')
    name=parts[-1]
    if any(p in SKIP or p in ('_pytest','pytest') or p.startswith(('pytest-','_pytest-')) for p in parts):return False
    if relative.startswith('shared/runtime/node/'):return False
    if relative.startswith('shared/runtime/anystyle/'):
        tail=parts[3:]
        if not tail:return True
        if tail[0].endswith('.gem'):return False
        if tail[0]=='anystyle-1.5.0' and len(tail)>1 and tail[1] in ('res','.github'):return False
        if tail[0]=='rubyinstaller-3.3.12-2-x64':
            ruby=tail[1:]
            if not ruby:return True
            if ruby[0] not in ('bin','lib'):return False
            if ruby[0]=='bin' and len(ruby)>1 and ruby[1] not in ('ruby.exe','x64-ucrt-ruby330.dll','ruby_builtin_dlls'):return False
            if ruby[0]=='lib' and len(ruby)>1 and ruby[1]!='ruby':return False
            if ruby[:3]==['lib','ruby','3.3.0'] and len(ruby)>3:
                if ruby[3].removesuffix('.rb') in ('bundler','rdoc','irb','reline','ruby_vm','mkmf'):return False
            if ruby[:4]==['lib','ruby','gems','3.3.0'] and len(ruby)>4:
                if ruby[4]=='cache':return False
                if ruby[4]=='gems' and len(ruby)>5 and not ruby[5].startswith(('racc-','rexml-')):return False
                if ruby[4]=='extensions' and len(ruby)>7 and not ruby[7].startswith(('racc-','rexml-')):return False
                if ruby[4]=='specifications' and len(ruby)>5 and ruby[5]!='default' and not ruby[5].startswith(('racc-','rexml-')):return False
    return not name.endswith(('.pyc','.pyo'))

def remove_staged(path):
    path=Path(path)
    if not path.resolve().is_relative_to(PAYLOAD.resolve()):raise ValueError('Unsafe staging target')
    if path.is_dir():shutil.rmtree(path)
    else:path.unlink(missing_ok=True)

def copy_tree(source,target):
    def ignore(folder,names):
        ruby_help=Path(folder).name=='share' and Path(folder).parent.name=='rubyinstaller-3.3.12-2-x64'
        return [n for n in names if n in SKIP or n.endswith(('.pyc','.pyo')) or n.startswith(('pip-','setuptools-')) or ruby_help and n in ('ri','doc') or not include_payload((target/Path(folder).relative_to(source)/n).relative_to(PAYLOAD).as_posix())]
    def cached_copy(src,dst):
        s,d=Path(src),Path(dst)
        if d.is_file() and s.stat().st_size==d.stat().st_size and s.stat().st_mtime_ns==d.stat().st_mtime_ns:return dst
        return shutil.copy2(src,dst)
    shutil.copytree(source,target,dirs_exist_ok=True,ignore=ignore,copy_function=cached_copy)


def main():
    PAYLOAD.mkdir(parents=True,exist_ok=True)
    # Also prune leftovers from older staging runs, not just new copies.
    for old in sorted(PAYLOAD.rglob('*'),key=lambda p:len(p.parts)):
        if old.exists() and not include_payload(old.relative_to(PAYLOAD).as_posix()):remove_staged(old)
    for cache_dir in sorted(PAYLOAD.rglob('__pycache__'),reverse=True):
        if cache_dir.resolve().is_relative_to(PAYLOAD.resolve()):shutil.rmtree(cache_dir)
    for app,folders in {'reference-checker':['ref_app','reference_extractor','reference_identity']}.items():
        # Remove generated state from prior staging smoke runs, never source data.
        staged=PAYLOAD/app
        if staged.exists():
            for child in staged.iterdir():
                if child.name in folders:continue
                if not child.resolve().is_relative_to(PAYLOAD.resolve()):raise ValueError('Unsafe staging target')
                if child.is_dir():shutil.rmtree(child)
                else:child.unlink()
        for folder in folders:copy_tree(ROOT/app/folder,PAYLOAD/app/folder)
    copy_tree(ROOT/'b7_shared',PAYLOAD/'b7_shared')
    if (ROOT/'shared/runtime').exists():copy_tree(ROOT/'shared/runtime',PAYLOAD/'shared/runtime')
    for name in ('ri','doc'):
        unused=PAYLOAD/'shared/runtime/anystyle/rubyinstaller-3.3.12-2-x64/share'/name
        if unused.exists():
            if not unused.resolve().is_relative_to(PAYLOAD.resolve()):raise ValueError('Unsafe documentation target')
            shutil.rmtree(unused)
    copy_tree(ROOT/'shared/licenses',PAYLOAD/'licenses')
    cache=HERE/'cache';cache.mkdir(exist_ok=True)
    archive=cache/'python-3.13.12-embed-amd64.zip'
    if not archive.exists():
        urllib.request.urlretrieve('https://www.python.org/ftp/python/3.13.12/python-3.13.12-embed-amd64.zip',archive)
    for app,code in [('reference','reference-checker')]:
        target=PAYLOAD/'runtime'/app;target.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(archive) as z:z.extractall(target)
        copy_tree(ROOT/'.runtime'/app/'Lib/site-packages',target/'Lib/site-packages')
        (target/'python313._pth').write_text('python313.zip\n.\nLib/site-packages\n../../\n../../'+code+'\nimport site\n','utf-8')
        shutil.copyfile(HERE/'desktop/child_lifecycle.py',target/'Lib/site-packages/sitecustomize.py')
    files=[]
    for p in sorted(PAYLOAD.rglob('*')):
        if not p.is_file():continue
        relative=p.relative_to(PAYLOAD).as_posix()
        if relative=='distribution-manifest.json':continue
        if p.name=='.env' or '__pycache__' in p.parts or relative.startswith(('data/','logs/','.runtime/','reference-checker/data/')):raise ValueError('Private artifact: '+relative)
        files.append({'path':relative,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    manifest={'schema':1,'python':'3.13.12','source_root_excluded':True,'files':files,
              'python_archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
    (PAYLOAD/'distribution-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
    (HERE/'payload-summary.json').write_text(json.dumps({'files':len(files),'bytes':sum(p['bytes'] for p in files),
        'source_apps':['reference-checker'],'private_env_included':False,
        'python_archive_sha256':manifest['python_archive_sha256']},ensure_ascii=False,indent=2),'utf-8')
    print('Staged',len(files),'files;',sum(p['bytes'] for p in files)//1024//1024,'MiB; no personal configuration or tasks')


if __name__=='__main__':main()
