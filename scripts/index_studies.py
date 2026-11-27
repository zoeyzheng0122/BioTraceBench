"""Build the repository dataset from a versioned reproduction archive."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = Path('src/biotracebench/review_configs/schemas')
DOMAINS = {
    'basic': ('Basic research', 'basic-three', 'basic-research', 'BASIC_RESEARCH.md'),
    'clinical': ('Clinical research', 'clinical-four-compact', 'clinical-trials', 'CLINICAL_TRIALS.md'),
}
STATUS = {
    'parseable_database': 'Parseable database',
    'partial_raw_text': 'Partial output',
    'terminal_zero': 'Assigned zero',
}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode()


def normalize_schema(text, archived, current):
    return text.replace(f'{archived}.schema.json', f'{current}.schema.json')


def prompt_bytes(path, archived, current):
    text = normalize_schema(path.read_text(), archived, current)
    return text.replace('](../../shared/', '](../shared/').encode()


def case_files(archive, study, positions, sources):
    case, domain, title, doi, schema = (study[key] for key in
                                         ('case', 'domain', 'title', 'doi', 'schema'))
    label, archived, current, guide = DOMAINS[domain]
    folder = Path('data')/case
    reference = Path('reference')/current/f'{case}.json'
    task_dir = archive/'benchmark/tasks'/domain/case
    task = read_json(task_dir/'task.json')
    if (task['case_id'], task['domain'], task['doi'], task['pipeline'], schema) != (
            case, domain, doi, archived, current+'.schema.json'):
        raise ValueError(f'Study index differs from the archive: {case}')

    task.update(pipeline=current, prompt='query.md', complete_prompt='generation-prompt.md',
                materials_manifest='inputs.json',
                schema=str(Path('../..')/SCHEMAS/schema),
                field_dictionary=str(Path('../..')/SCHEMAS/'field-dictionary.json'))
    inputs = read_json(archive/f'benchmark/metadata/manifests/{domain}/{case}.json')
    inputs['case']['pipeline'] = current
    inputs.update(task_prompt=task['prompt'], complete_prompt=task['complete_prompt'],
                  source_license='LICENSES.txt',
                  description='Source paths are relative to inputs/.')
    result = {
        folder/'task.json': json_bytes(task),
        folder/'query.md': prompt_bytes(task_dir/'prompt.md', archived, current),
        folder/'generation-prompt.md': prompt_bytes(task_dir/'complete-prompt.md', archived, current),
        folder/'inputs.json': json_bytes(inputs),
        folder/'LICENSES.txt': ('\n'.join(line.rstrip() for line in
            (archive/f'benchmark/metadata/licenses/{domain}/{case}.txt').read_text().splitlines())+'\n').encode(),
        reference: (archive/f'evaluation/projection/references/{case}.json').read_bytes(),
    }

    included = 0
    for source in inputs['files']:
        path = Path(source['path'])
        if path.is_absolute() or '..' in path.parts:
            raise ValueError(f'Invalid source path: {path}')
        key = f'materials/{domain}/{case}/{path}'
        entry = sources[key]
        if entry['sha256'] != source['sha256'] or entry['bytes'] != source['bytes']:
            raise ValueError(f'Source manifest differs from the archive: {key}')
        if entry['retrieval']['kind'] == 'included':
            content = (archive/'benchmark'/key).read_bytes()
            if len(content) != source['bytes'] or hashlib.sha256(content).hexdigest() != source['sha256']:
                raise ValueError(f'Invalid input: {key}')
            result[folder/'inputs'/path] = content
            included += 1

    lines = [
        f'# {case}',
        '',
        title,
        '',
        f'[{label}](../../docs/{guide}) · [Study DOI](https://doi.org/{doi}) · '
        f'[Target schema]({task["schema"]}) · [Dataset guide](../../docs/DATASET.md)',
        '',
        '## Task files',
        '',
        '| File | Purpose |',
        '| --- | --- |',
        '| [Query](query.md) | Study instructions and scope |',
        '| [Generation prompt](generation-prompt.md) | Full instructions and schema for the model |',
        '| [Task definition](task.json) | Structured case information |',
        f'| [Input manifest](inputs.json) | File paths and source information for {len(inputs["files"])} inputs |',
        '| [Source licenses](LICENSES.txt) | Terms for the study sources |',
        f'| [Reference database](../../{reference.as_posix()}) | Final reference for scoring |',
        '',
        f'The [frozen inputs archive](../../docs/TASK_MATERIALS.md) contains every source under '
        f'`benchmark/materials/{domain}/{case}/`.',
        '',
    ]
    if included:
        lines += [f'The [inputs directory](inputs/) contains {included} source files from the archive.', '']
    lines += [
        'See the [materials guide](../../docs/MATERIALS.md) for source access and redistribution.',
        '',
        '## Saved outputs',
        '',
        'Paths below are relative to the extracted [reproduction archive](../../docs/REPRODUCTION.md).',
        '',
        '| Model configuration | Status | Archived output |',
        '| --- | --- | --- |',
    ]
    for run in sorted(positions, key=lambda row: row['model']):
        database = Path('outputs')/run['model']/case/'database.json'
        path = f'`{database}`' if (archive/database).is_file() else '—'
        lines.append(f"| `{run['model']}` | {STATUS[run['status']]} | {path} |")
    lines.extend(['', '[All cases](../README.md) · [Evaluation guide](../../docs/EVALUATION.md)', ''])
    result[folder/'README.md'] = '\n'.join(lines).encode()
    return result


def dataset(archive):
    manifest = read_json(archive/'manifest.json')
    with (ROOT/'data/studies.csv').open(encoding='utf-8-sig', newline='') as stream:
        studies = list(csv.DictReader(stream))
    positions = defaultdict(list)
    for row in read_json(archive/'outputs/status.json')['positions']:
        positions[row['case']].append(row)
    counts = manifest['counts']
    cases = {row['case'] for row in studies}
    if len(studies) != counts['tasks'] or len(cases) != len(studies) or cases != positions.keys():
        raise ValueError('Study index does not cover the frozen cases')
    models = {row['model'] for runs in positions.values() for row in runs}
    if len(models) != counts['models'] or any(
            len(runs) != len(models) or {row['model'] for row in runs} != models
            for runs in positions.values()):
        raise ValueError('Incomplete or duplicate model positions')

    source_file = archive/'benchmark/metadata/source-access.json'
    sources = {row['path']:row for row in read_json(source_file)}
    result = {Path('data/source-catalog.json'): source_file.read_bytes()}
    for file in sorted((archive/'benchmark/tasks/shared').iterdir()):
        text = normalize_schema(file.read_text(), 'basic-three', 'basic-research')
        result[Path('data/shared')/file.name] = normalize_schema(
            text, 'clinical-four-compact', 'clinical-trials').encode()
    lines = [
        '# Study index',
        '',
        'Browse 100 studies. Each case directory contains its instructions, full prompt, '
        'input manifest, and link to its curated reference database.',
        '',
        '[Dataset guide](../docs/DATASET.md) · [Frozen inputs](../docs/TASK_MATERIALS.md) · '
        '[Study list CSV](studies.csv) · [Source catalogue](source-catalog.json)',
        '',
        '[Basic research](#basic-research) · [Clinical research](#clinical-research)',
    ]
    for domain, (label, _, _, _) in DOMAINS.items():
        lines.extend(['', f'## {label}', '', '| Case | Study |', '| --- | --- |'])
        section = sorted((row for row in studies if row['domain'] == domain),
                         key=lambda row: row['case'])
        if len(section) != 50:
            raise ValueError(f'Expected 50 {domain} cases')
        for study in section:
            case = study['case']
            title = study['title'].replace('|', r'\|')
            lines.append(f'| [{case}]({case}/README.md) | {title} |')
            if not (ROOT/SCHEMAS/study['schema']).is_file():
                raise ValueError(f"Missing repository schema: {study['schema']}")
            result.update(case_files(archive, study, positions[case], sources))
    result[Path('data/README.md')] = ('\n'.join(lines)+'\n').encode()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-root', type=Path, required=True)
    parser.add_argument('--check', action='store_true', help='Compare with repository files')
    args = parser.parse_args()
    result = dataset(args.artifact_root)
    for path, content in result.items():
        destination = ROOT/path
        if args.check:
            if not destination.is_file() or destination.read_bytes() != content:
                parser.error(f'Outdated or missing dataset file: {path}')
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
    print(f'{len(result)} dataset files verified.')


if __name__ == '__main__':
    main()
