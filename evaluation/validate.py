"""Validate the portable benchmark package without making model calls."""
import hashlib
import argparse
import re
import zipfile

from .core import ROOT, DOMAINS, MISSING_CRITERIA, indexed, load_specs, read, read_jsonl, sha, verify_spec


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(root=ROOT, metadata_only=False):
    tasks = indexed(read_jsonl(root / 'benchmark/tasks.jsonl'))
    catalog = indexed(read(root / 'benchmark/bvis.json'), 'bvis_id')
    require(list(tasks) == [f'LEVI-{i:04d}' for i in range(1, 1376)], 'Task IDs must be contiguous and unique')
    require(list(catalog) == [f'BVIS-{i:03d}' for i in range(1, 121)], 'BVIS IDs must be contiguous and unique')
    for b, entry in catalog.items():
        require(entry['domain'] in DOMAINS, 'Unknown BVIS domain: ' + b)
    for q, task in tasks.items():
        require(task['bvis'] and len(task['bvis']) == len(set(task['bvis'])) and set(task['bvis']) <= set(catalog), 'Invalid BVIS membership: ' + q)
        require(len(task['domains']) == len(set(task['domains'])), 'Duplicate domain: ' + q)
        require(set(task['domains']) == {catalog[b]['domain'] for b in task['bvis']}, 'Domain mismatch: ' + q)
        require(hashlib.sha256(task['prompt_en'].encode()).hexdigest() == task['prompt_sha256'], 'Prompt hash mismatch: ' + q)
    require({b for task in tasks.values() for b in task['bvis']} == set(catalog), 'Unrepresented BVIS')
    specs = load_specs(root)
    require(set(specs) == set(tasks), 'Criterion roster mismatch')
    for q, spec in specs.items():
        require(spec['judge'] == f'benchmark/criteria/{q}/judge.txt', 'Instruction path mismatch: ' + q)
        require(spec['schema'] == f'benchmark/criteria/{q}/schema.json', 'Schema path mismatch: ' + q)
        require(len(spec['check_ids']) == len(set(spec['check_ids'])), 'Duplicate check IDs: ' + q)
        require(set(spec['excluded_check_ids']) <= set(spec['check_ids']), 'Unknown excluded check: ' + q)
        if not metadata_only:
            verify_spec(spec, root)
            schema = read(root / spec['schema'])['properties']['checks']['properties']
            require(set(spec['check_ids']) == set(schema), 'Schema check mismatch: ' + q)
    for name in ('tasks.jsonl', 'bvis.json', 'evaluation_specs.json'):
        require(not re.search(r'[\u3400-\u9fff]', (root / 'benchmark' / name).read_text()), 'Non-English metadata: ' + name)
    if not metadata_only:
        if not (root / 'benchmark/criteria.zip').is_file():
            raise FileNotFoundError(MISSING_CRITERIA)
        with zipfile.ZipFile(root / 'benchmark/criteria.zip') as archive:
            names = archive.namelist()
            expected = {f'criteria/{qid}/{name}' for qid in tasks for name in ('judge.txt', 'schema.json')}
            require(len(names) == len(set(names)), 'Duplicate criterion archive entries')
            require(set(names) == expected, 'Expected exactly judge.txt and schema.json for every task')
            for name in names:
                require(not re.search(r'[\u3400-\u9fff]', archive.read(name).decode('utf-8')), 'Untranslated criterion text: ' + name)
    for path, expected in read(root / 'benchmark/checksums.json').items():
        if metadata_only and path == 'benchmark/criteria.zip':
            continue
        require(sha(root / path) == expected, 'Release checksum mismatch: ' + path)
    return {'tasks': len(tasks), 'bvis': len(catalog), 'criteria_checked': not metadata_only}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata-only', action='store_true', help='Check bundled metadata without the downloaded criterion package')
    args = parser.parse_args()
    try:
        counts = validate(metadata_only=args.metadata_only)
    except (FileNotFoundError, ValueError) as exc:
        parser.exit(2, f'Error: {exc}\n')
    scope = 'metadata and bundled file hashes; evaluation criteria were not checked' if args.metadata_only else 'metadata, evaluation criteria and file hashes'
    print(f"Verified {counts['tasks']:,} tasks / {counts['bvis']} BVIS: {scope}. No model calls.")
