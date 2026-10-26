"""Load local settings without publishing credentials to logs or the browser."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIXES = ('B7_', 'LLM_', 'DEEPSEEK_', 'OPENALEX_', 'SEMANTIC_', 'ANYSTYLE_', 'GROBID_', 'REFERENCE_')


def load_values(path=None):
    path = Path(path or os.environ.get('B7_ENV_FILE', ROOT/'.env'))
    values = {}
    if path.is_file():
        for line in path.read_text('utf-8-sig').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line: continue
            key, value = line.removeprefix('export ').split('=', 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    for key, value in os.environ.items():
        if key.startswith(PREFIXES): values[key] = value
    values.setdefault('ANYSTYLE_FORMAT_MODE', 'remote')
    return values


def data_dir(app, root=ROOT, values=None):
    if app != 'reference': raise ValueError('Unknown application')
    values = load_values() if values is None else values
    key = 'REFERENCE_DATA_DIR'
    value = Path(values.get(key) or Path(root)/'data'/app)
    return (value if value.is_absolute() else Path(root)/value).resolve()


def formatter_home():
    return Path(os.environ.get('B7_ANYSTYLE_HOME', ROOT/'shared/runtime/anystyle')).resolve()


def node_executable():
    return Path(os.environ.get('B7_NODE_EXE', ROOT/'shared/runtime/node/node.exe')).resolve()


def child_environment(root=ROOT, app='reference'):
    if app != 'reference': raise ValueError('Unknown application')
    root = Path(root).resolve()
    values = load_values(root/'.env')
    result = dict(os.environ)
    result.update(values)
    result.update(B7_ROOT=str(root), B7_ENV_FILE=str(root/'.env'), PYTHONUTF8='1',
                  B7_ANYSTYLE_HOME=values.get('B7_ANYSTYLE_HOME') or str(root/'shared/runtime/anystyle'),
                  B7_NODE_EXE=values.get('B7_NODE_EXE') or str(root/'shared/runtime/node/node.exe'))
    result['REFERENCE_DATA_DIR'] = str(data_dir('reference', root, values))
    folder = 'reference-checker'
    result['PYTHONPATH'] = os.pathsep.join([str(root), str(root/folder)])
    return result
