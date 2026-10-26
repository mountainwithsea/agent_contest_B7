import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .config import Config
from .pipeline import extract


def main():
    parser = argparse.ArgumentParser(description='Extract references without document-specific manual coordinates.')
    parser.add_argument('input', type=Path)
    parser.add_argument('--env', type=Path, default=Path('.env'))
    parser.add_argument('--output', type=Path, help='New output directory; existing directories are never overwritten.')
    parser.add_argument('--mode', choices=('auto', 'model'), default='auto', help='Rules first with model fallback, or original model-only extraction.')
    args = parser.parse_args()
    output = args.output or Path('output/reference-extraction') / (
        args.input.stem + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:6])
    try:
        config = Config.load(args.env)
        config.extraction_mode = args.mode
        result = extract(args.input, output, config)
    except Exception as exc:
        # No config repr, credentials or HTTP response bodies are printed.
        print('Cannot start extraction: ' + type(exc).__name__, file=sys.stderr)
        return 2
    print(f"{result['status']}: {len(result['references'])} references; {result['total_tokens']} tokens")
    print('Output: ' + str(output.resolve() / 'index.html'))
    if result.get('error'):
        print(result['error'], file=sys.stderr)
    return 1 if result['status'] == '执行未完成' else 0


if __name__ == '__main__':
    raise SystemExit(main())
