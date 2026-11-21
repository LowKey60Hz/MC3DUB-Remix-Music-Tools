"""Non-interactive loading-screen adapter for the tested ASSETS slot workflow.
Usage: python loading_apply.py PROJECT_ROOT CONFIG_JSON
CONFIG_JSON contains assignments: [{slot: 1..18, source: filename}].
"""
import json
from pathlib import Path
import shutil
import sys
import tempfile

LIMIT = 455680  # 445 KiB, matching the shared loading-screen converter policy.


class LoadingPreparationError(RuntimeError):
    """A source failed before any game slots were changed."""

    def __init__(self, filename, reason):
        self.filename = filename
        self.reason = reason
        super().__init__(f'{filename}: {reason}')


def main(root, config_file):
    root = Path(root).resolve()
    music = root / 'Loading Music'
    target = root / 'ASSETS' / 'audio' / 'loadscreen'
    config = json.loads(Path(config_file).read_text(encoding='utf-8'))
    entries = config['assignments']
    if not isinstance(entries, list) or not entries or len(entries) > 18:
        raise ValueError('Expected between 1 and 18 slot assignments.')
    if not target.is_dir() or any(not (target / f'{n}.raw').is_file() for n in range(1,19)):
        raise ValueError('All 18 extracted ASSETS/audio/loadscreen slots are required.')
    selected = {}
    for item in entries:
        slot = item['slot']
        name = item['source']
        if type(slot) is not int or not 1 <= slot <= 18 or slot in selected:
            raise ValueError('Invalid or repeated slot assignment.')
        if not isinstance(name, str) or Path(name).name != name or not name or name in ('.','..'):
            raise ValueError('Invalid source filename.')
        source = music / name
        if not source.is_file() or source.suffix.lower() not in ('.mp3','.wav'):
            raise ValueError(f'Source file not found or unsupported: {name}')
        selected[slot] = source
    converter = root / 'supporting_tools' / 'convert_loading_raw.py'
    if not converter.is_file():
        raise ValueError('Missing supporting_tools/convert_loading_raw.py.')
    # Import the same converter used by the updated command-line workflow.
    sys.path.insert(0, str(converter.parent))
    from convert_loading_raw import convert
    with tempfile.TemporaryDirectory(prefix='MC3_Loading_', dir=root) as tmp:
        temp = Path(tmp)
        converted = {}
        unique = list(dict.fromkeys(selected.values()))
        for idx, source in enumerate(unique, 1):
            output = temp / f'converted_{idx}.raw'
            print(f'[{idx}/{len(unique)}] Converting {source.name}', flush=True)
            try:
                convert(source, output)
            except (OSError, RuntimeError, ValueError) as exc:
                reason = str(exc)
                if isinstance(exc, ValueError) and (
                    reason.startswith('Output exceeds the loading-screen RAW limit')
                    or reason == 'Input audio is empty.'
                ):
                    reason = 'File exceeds loading-screen audio limit of 9.493 seconds (445 KiB) or is empty. Shorten the audio or remove.'
                raise LoadingPreparationError(source.name, reason) from exc
            if not output.is_file():
                raise LoadingPreparationError(source.name, 'The audio converter produced no output.')
            size = output.stat().st_size
            if size == 0 or size > LIMIT:
                raise LoadingPreparationError(source.name, 'File exceeds loading-screen audio limit of 9.493 seconds (445 KiB) or is empty. Shorten the audio or remove.')
            print(f'[OK] {source.name}: {size:,} bytes', flush=True)
            converted[source] = output
        backups = {}
        try:
            for slot, source in sorted(selected.items()):
                dest = target / f'{slot}.raw'
                backup = temp / f'backup_{slot}.raw'
                shutil.copyfile(dest, backup)
                backups[slot] = backup
                shutil.copyfile(converted[source], dest)
                print(f'[UPDATED] Slot {slot} <- {source.name}', flush=True)
        except OSError:
            print('[ERROR] Write failed; restoring original slots.', flush=True)
            for slot, backup in backups.items():
                shutil.copyfile(backup, target / f'{slot}.raw')
            raise
    print('[DONE] Loading-screen slots updated. Build ISO when ready.', flush=True)

if __name__ == '__main__':
    try:
        if len(sys.argv) != 3: raise ValueError('Expected project root and assignment configuration.')
        main(sys.argv[1], sys.argv[2])
    except LoadingPreparationError as exc:
        print('[LOADING_FAILURE] ' + json.dumps({'filename': exc.filename, 'reason': exc.reason, 'no_slots_changed': True}), flush=True)
        print('[ERROR] '+str(exc), flush=True)
        sys.exit(1)
    except Exception as exc:
        print('[ERROR] '+str(exc), flush=True)
        sys.exit(1)
