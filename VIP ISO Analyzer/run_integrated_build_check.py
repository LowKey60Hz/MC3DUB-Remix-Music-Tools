"""Run the GUI build chain offscreen, reusing the ASSETS just verified separately."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent / 'UI Custom Gameplay Music Tools'
sys.path.insert(0, str(PROJECT / 'gui'))
import main as gui
from PySide6.QtCore import QTimer


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            value.update(data)
    return value.hexdigest()


def main():
    output = PROJECT / 'MC3_Modified_VIP.iso'
    report = ROOT / 'Integrated_Build_Verification.json'
    if output.exists() or report.exists():
        raise FileExistsError('Verification output exists; refusing overwrite')
    print('Checking fresh compiler output against the successful research archive...', flush=True)
    if digest(PROJECT / 'ISO_FILES/ASSETS.DAT') != digest(ROOT / 'VIP_v11A_ASSETS_v5_Test.dat'):
        raise ValueError('Fresh ASSETS differs from successful research archive')
    app = gui.QApplication.instance() or gui.QApplication([])
    app.setQuitOnLastWindowClosed(False)
    state = {'passed': False}
    log = (ROOT / 'Integrated_Build_Verification.log').open('x', encoding='utf-8')
    def finish(passed, message):
        state.update(passed=passed, message=str(message))
        print(('PASS: ' if passed else 'FAIL: ') + str(message), flush=True)
        app.quit()
    with patch.object(gui.Window, 'start_auto_validation'), patch.object(gui.Window, 'title_preview_original'):
        window = gui.Window()
    original_log = window.log
    def record(message):
        original_log(message)
        log.write(message + '\n')
        log.flush()
        if message.startswith(('BUILD [', 'SUCCESS:', 'BUILD FAILED:', 'ERROR:', 'BUILD BLOCKED:')) or 'PASS' in message:
            print(message, flush=True)
    window.log = record
    window.profile_verified = True
    with patch.object(gui.QMessageBox, 'question', return_value=gui.QMessageBox.Yes), \
         patch.object(gui.QMessageBox, 'information', side_effect=lambda *args: finish(True, args[-1])), \
         patch.object(gui.QMessageBox, 'warning', side_effect=lambda *args: finish(False, args[-1])), \
         patch.object(gui.QMessageBox, 'critical', side_effect=lambda *args: finish(False, args[-1])):
        with patch.object(gui.Window, 'start_build_step'):
            window.begin_build()
        if not window.build_busy:
            raise RuntimeError('GUI did not prepare build')
        # The new compiler ran and independently verified all records immediately
        # before this check. Everything else runs through actual GUI QProcesses.
        window.build_steps = [s for s in window.build_steps if s[0] != 'Compile ASSETS.DAT']
        state['executed_steps'] = [s[0] for s in window.build_steps]
        window.build_progress.setRange(0, len(window.build_steps))
        def timeout():
            if window.build_process:
                window.build_process.kill()
            finish(False, 'Integration check timed out; pending files retained')
        QTimer.singleShot(20 * 60 * 1000, timeout)
        QTimer.singleShot(0, window.start_build_step)
        app.exec()
    window.build_busy = False
    window.close()
    log.close()
    if state['passed']:
        state['output'] = str(output)
        state['output_bytes'] = output.stat().st_size
        state['sha256'] = digest(output)
        state['byte_identical_to_user_tested_expanded_iso'] = state['sha256'] == '3cef6559a5b2e8797b1eed4ed774f3c0ee4afec9b159f1c4defe4d835f0b34e3'
    report.write_text(json.dumps(state, indent=2) + '\n')
    print(json.dumps(state, indent=2), flush=True)
    if not state['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
