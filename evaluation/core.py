"""Criterion loading, response validation and whole-task decisions."""
import hashlib
import json
from pathlib import Path
from functools import lru_cache
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = ['Symbolic', 'Geometric', 'Topological', 'Layout', 'Quantitative', 'Procedural']
MISSING_CRITERIA = (
    'Evaluation criteria are not installed. Place criteria.zip in benchmark/ without extracting it. '
    'See benchmark/README.md#downloads for release availability.'
)


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Non-finite JSON number: ' + value)
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


@lru_cache(maxsize=4)
def _criterion_archive(path, modified_ns, size):
    """Read the criterion archive once without extracting files."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate criterion archive entries')
        return {name: archive.read(name) for name in names}


def read_bytes(path):
    path = Path(path).resolve()
    if path.is_file():
        return path.read_bytes()
    for parent in path.parents:
        if parent.name != 'benchmark':
            continue
        member = path.relative_to(parent).as_posix()
        archive_path = parent / 'criteria.zip'
        if not member.startswith('criteria/'):
            continue
        if not archive_path.is_file():
            raise FileNotFoundError(MISSING_CRITERIA)
        stat = archive_path.stat()
        entries = _criterion_archive(str(archive_path), stat.st_mtime_ns, stat.st_size)
        if member not in entries:
            raise FileNotFoundError('Missing criterion archive member: ' + member)
        return entries[member]
    raise FileNotFoundError(path)


def read_text(path):
    return read_bytes(path).decode('utf-8')


def read(path):
    return strict_json(read_text(path))


def read_jsonl(path):
    return [strict_json(line) for line in read_text(path).splitlines() if line.strip()]


def sha(path):
    return hashlib.sha256(read_bytes(path)).hexdigest()


def indexed(rows, key='qid'):
    result = {}
    for row in rows:
        if row[key] in result:
            raise ValueError('Duplicate ' + key + ': ' + row[key])
        result[row[key]] = row
    return result


def load_specs(root=ROOT):
    return indexed(read(root / 'benchmark/evaluation_specs.json'))


def validate_response(value, spec, root=ROOT):
    """Validate each check against the task response schema."""
    schema = read(root / spec['schema'])
    if not isinstance(value, dict) or set(value) != {'checks'}:
        raise ValueError('Expected exactly one top-level checks object')
    checks = value['checks']
    expected = schema['properties']['checks']['properties']
    if not isinstance(checks, dict) or set(checks) != set(expected):
        raise ValueError('Missing or extra check IDs')
    for key, cell in checks.items():
        if not isinstance(cell, dict) or set(cell) != {'met', 'observation', 'needs_review'}:
            raise ValueError('Malformed check: ' + key)
        if type(cell['met']) is not bool or type(cell['needs_review']) is not bool:
            raise ValueError('Check booleans must be actual JSON booleans: ' + key)
        if not isinstance(cell['observation'], str):
            raise ValueError('Observation must be a string: ' + key)
    if not set(spec['excluded_check_ids']) <= set(expected):
        raise ValueError('Excluded check outside schema')
    if set(spec['check_ids']) != set(expected):
        raise ValueError('Spec/schema check IDs disagree')


def aggregate(value, spec, root=ROOT):
    validate_response(value, spec, root)
    excluded = set(spec['excluded_check_ids'])
    failed = [k for k, v in value['checks'].items() if not v['met'] and k not in excluded]
    review = [k for k, v in value['checks'].items() if v['needs_review'] and k not in excluded]
    return {'verdict': 'FAIL' if failed else 'PASS',
            'failed_checks': failed, 'review_checks': review, 'needs_review': bool(review)}


def verify_spec(spec, root=ROOT):
    for field in ('judge', 'schema'):
        if sha(root / spec[field]) != spec[field + '_sha256']:
            raise ValueError('Criterion checksum mismatch: ' + spec[field])
