"""Shared compiled-archive record gate. Profile engines retain their own layout checks."""
import argparse
import json
import os
from pathlib import Path
from vip_capacity import inspect_archive, assess, CAPACITY_PROFILES


def save_report(path, report):
    if path is None:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    os.replace(temporary, path)


def check_records(replacements, profile=None, report_path=None):
    result = {}
    for kind in ('ASSETS', 'STREAMS'):
        try:
            inspection = inspect_archive(Path(replacements) / (kind + '.DAT'), kind)
        except (ValueError, OSError) as error:
            save_report(report_path, dict(status='INVALID_OR_UNSUPPORTED_ARCHIVE_INDEX', layout_profile=profile,
                        failed_archive=kind, error=str(error), passes_size_policy=False))
            raise
        result[kind] = inspection
        print(f'{kind}: {inspection["live_record_count"]:,} records; '
              f'last live byte end {inspection["max_live_end_exclusive"]:,}; record policy '
              f'{"PASS" if inspection["passes_record_policy"] else "BLOCKED"}', flush=True)
    if profile in CAPACITY_PROFILES:
        capacity = assess(result['ASSETS']['archive_bytes'], result['STREAMS']['archive_bytes'],
                          assets_index=result['ASSETS'], streams_index=result['STREAMS'], layout_profile=profile)
        capacity['source_verification'] = 'Performed by the preceding source-validation step and profile engine, not this gate'
        save_report(report_path, capacity)
        label = capacity['layout_label']
        print(f'{label}: ASSETS {capacity["assets_allocated_bytes"]:,} + STREAMS {capacity["streams_allocated_bytes"]:,} '
              f'/ shared budget {capacity["shared_layout_capacity_bytes"]:,} bytes', flush=True)
        if capacity['over_capacity_bytes']:
            amount = capacity['over_capacity_bytes']
            raise ValueError(f'{label} capacity exceeded by {amount:,} bytes ({amount / 1048576:.2f} MiB). '
                             'Reduce or remove music, or use shorter tracks before building. The verified ISO region cannot be enlarged by disabling this check.')
        if not capacity['passes_size_policy']:
            risky = [kind + ': ' + '; '.join(value['risks']) for kind, value in result.items() if not value['passes_record_policy']]
            raise ValueError(label + ' record policy blocked: ' + ' | '.join(risky))
        print(f'{label} shared capacity PASS: {capacity["remaining_bytes"]:,} bytes ({capacity["remaining_bytes"] / 1048576:.2f} MiB) remain', flush=True)
    elif profile is not None:
        raise ValueError('Unsupported capacity profile')
    else:
        if any(not value['passes_record_policy'] for value in result.values()):
            raise ValueError('Compiled archive record policy blocked')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replacement-dir', type=Path, required=True)
    parser.add_argument('--profile', choices=tuple(CAPACITY_PROFILES))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        check_records(args.replacement_dir, args.profile, args.report)
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')
