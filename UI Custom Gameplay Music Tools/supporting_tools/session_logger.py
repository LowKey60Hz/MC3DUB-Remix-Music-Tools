#!/usr/bin/env python3
"""Launch the interactive batch tool and tee its output to support_logs."""
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime


def main():
    if len(sys.argv) != 2:
        return 2
    batch = Path(sys.argv[1]).resolve()
    root = batch.parent
    folder = root / 'support_logs'
    folder.mkdir(exist_ok=True)
    stamp = datetime.now().strftime('%Y-%m-%d_%H%M%S_%f')
    log = folder / ('session_' + stamp + '.log')
    env = os.environ.copy()
    env['MC3_LOG_ACTIVE'] = '1'
    with log.open('wb') as out:
        header = ('MC3 Gameplay Music Tools session: ' + datetime.now().isoformat(timespec='seconds') + '\r\n'
                  + 'Project: ' + str(root) + '\r\n' + 'Batch: ' + batch.name + '\r\n'
                  + '===================================================\r\n').encode('utf-8', errors='replace')
        out.write(header)
        out.flush()
        print('[SESSION LOG] ' + str(log), flush=True)
        # Inherit console input: SET /P, PAUSE and Python input() stay interactive.
        proc = subprocess.Popen(['cmd.exe', '/d', '/c', 'call', str(batch)], cwd=str(root), env=env,
                                stdin=None, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
        try:
            while True:
                chunk = os.read(proc.stdout.fileno(), 4096)
                if not chunk:
                    break
                out.write(chunk)
                out.flush()
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
        except KeyboardInterrupt:
            proc.terminate()
        return proc.wait()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except OSError as exc:
        print('[LOGGING ERROR] ' + str(exc), file=sys.stderr)
        sys.exit(1)
