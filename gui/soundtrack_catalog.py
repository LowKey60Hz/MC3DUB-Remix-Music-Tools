"""Read-only song catalog for the GUI; no game files are changed."""
import argparse
import json
import sys
import contextlib
import io
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    root = parser.parse_args().root.resolve()
    sys.path.insert(0, str(root / 'supporting_tools'))
    from manage_gameplay_soundtrack import collect, soundtrack_entries
    with contextlib.redirect_stdout(sys.stderr):
        parsed, genres, _, _ = collect(root)
        groups = soundtrack_entries(root, parsed, genres)
    rows = []
    for genre, songs in groups:
        for ref, title in songs:
            rows.append({'ref': ref, 'title': title, 'genre': genre})
    print('MC3_CATALOG_JSON:' + json.dumps(rows, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Catalog error: {exc}', file=sys.stderr)
        sys.exit(1)
