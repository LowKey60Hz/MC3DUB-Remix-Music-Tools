"""Clear only the four explicitly owned ISO-workspace directories."""
import argparse
from pathlib import Path
import shutil
import stat

WORKSPACE_FOLDERS = ('STREAMS', 'ASSETS', 'ISO_FILES', 'support_logs')


def is_link(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def cleanup_plan(root, source_iso):
    root = Path(root).resolve(strict=True)
    source_iso = Path(source_iso).resolve(strict=True)
    if root == Path(root.anchor) or not (root / 'supporting_tools/MC3_Profile_108S.py').is_file():
        raise ValueError('Select the music-tools project folder before resetting its workspace.')
    if not source_iso.is_file():
        raise ValueError('Selected source ISO is missing.')
    targets = []
    for name in WORKSPACE_FOLDERS:
        target = root / name
        # Check source containment even when the target does not yet exist.
        if source_iso == target or source_iso.is_relative_to(target):
            raise ValueError('The selected ISO is inside ' + name + '. Move it outside the workspace folders before restarting.')
        try:
            target.lstat()
        except FileNotFoundError:
            continue
        if is_link(target) or target.resolve().parent != root or not target.is_dir():
            raise ValueError('Workspace cleanup requires a regular project directory: ' + name)
        targets.append(target)
    return targets


def validate_tree(target, root):
    pending = [target]
    while pending:
        path = pending.pop()
        if is_link(path) or not path.resolve().is_relative_to(root):
            raise ValueError('Workspace contains a link/junction or an outside path; cleanup stopped: ' + str(path))
        if path.is_dir():
            pending.extend(path.iterdir())


def clear_workspace(root, source_iso):
    root = Path(root).resolve(strict=True)
    targets = cleanup_plan(root, source_iso)
    # Validate all trees before deleting any of them. Never traverse reparse
    # points, even when a particular runtime's rmtree would leave them alone.
    for target in targets:
        validate_tree(target, root)
    cleared = []
    for target in targets:
        # Recheck immediately before each recursive removal.
        if target not in cleanup_plan(root, source_iso):
            raise ValueError('Workspace changed during cleanup: ' + target.name)
        validate_tree(target, root)
        print('Clearing ' + target.name + '...', flush=True)
        try:
            shutil.rmtree(target)
        except OSError as error:
            raise OSError('Could not clear ' + target.name + '; close applications using its files and retry. Already cleared: ' + ', '.join(cleared) + '. ' + str(error)) from error
        cleared.append(target.name)
    (root / 'support_logs').mkdir(exist_ok=True)
    print('Workspace cleanup completed: ' + ', '.join(cleared), flush=True)
    return cleared


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--source-iso', type=Path, required=True)
    args = parser.parse_args()
    try:
        clear_workspace(args.root, args.source_iso)
    except (ValueError, OSError) as error:
        parser.exit(1, 'Cleanup stopped: ' + str(error) + '\n')
