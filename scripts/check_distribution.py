"""Check the distribution's entry points and resource layout."""
from pathlib import Path
import argparse
import tarfile
import zipfile


REQUIRED = (
    'biotracebench_analysis/replay/score_output.py',
    'biotracebench_analysis/replay/scoring.py',
    'biotracebench_analysis/publication/score_output.py',
    'biotracebench_scoring/review_counts.py',
    'biotracebench/review_configs/scoring/policy.json',
    'biotracebench/publication_configs/scoring/policy.json',
)
REMOVED = (
    'biotracebench_scoring/evaluation.py',
    'biotracebench_scoring/scoring.py',
)


def check(path):
    if path.suffix == '.whl':
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    else:
        with tarfile.open(path, 'r:gz') as archive:
            names = archive.getnames()
    for name in names:
        if 'legacy' in Path(name).parts or any(name.endswith(item) for item in REMOVED):
            raise ValueError(f'{path.name}: excluded module included: {name}')
    for item in REQUIRED:
        if not any(name == item or name.endswith('/' + item) for name in names):
            raise ValueError(f'{path.name}: missing supported scoring file: {item}')
    print(f'{path.name}: supported scoring interface verified')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, required=True)
    directory = parser.parse_args().dist
    for pattern in ('*.whl', '*.tar.gz'):
        paths = sorted(directory.glob(pattern))
        if len(paths) != 1:
            raise ValueError(f'Expected one {pattern} package in {directory}, found {len(paths)}')
        check(paths[0])


if __name__ == '__main__':
    main()
