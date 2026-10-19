"""Offline response, evaluation-runner and release-integrity tests."""
import argparse
import contextlib
import copy
import io
import json
import shutil
from pathlib import Path
import tempfile
import unittest
import zipfile
import warnings
from unittest.mock import patch
from evaluation.core import ROOT, aggregate, indexed, load_specs, read, read_jsonl, read_bytes, read_text, strict_json, verify_spec
from evaluation.evaluate import parse_envelope, payload, run
from evaluation.validate import validate

requires_criteria = unittest.skipUnless((ROOT / 'benchmark/criteria.zip').is_file(), 'Install criteria.zip to run criterion-dependent tests')


def synthetic_response(spec, failed=(), review=()):
    """Test-only booleans; these are not model judgments of the bundled images."""
    return {'checks': {key: {
        'met': key not in failed,
        'observation': 'Synthetic test fixture; this is not an observation of the image.',
        'needs_review': key in review,
    } for key in spec['check_ids']}}


class CriterionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.specs = load_specs(); cls.spec = cls.specs['LEVI-1169']
        cls.raw = synthetic_response(cls.spec)

    @requires_criteria
    def test_strict_checks_and_types(self):
        for kind in ['missing', 'extra', 'string_boolean', 'null', 'extra_cell', 'extra_top']:
            with self.subTest(kind=kind):
                raw = copy.deepcopy(self.raw)
                if kind == 'missing': raw['checks'].pop('R00')
                elif kind == 'extra': raw['checks']['R999'] = raw['checks']['R00']
                elif kind == 'string_boolean': raw['checks']['R00']['met'] = 'false'
                elif kind == 'null': raw['checks']['R00']['needs_review'] = None
                elif kind == 'extra_cell': raw['checks']['R00']['confidence'] = 1
                else: raw['score'] = 100
                with self.assertRaises(ValueError): aggregate(raw, self.spec)

    @requires_criteria
    def test_review_is_not_failure_and_exclusions_apply(self):
        spec = next(s for s in self.specs.values() if s['excluded_check_ids'])
        raw = {'checks': {k: {'met': True, 'observation': 'Synthetic unit-test fixture', 'needs_review': False} for k in spec['check_ids']}}
        for k in spec['excluded_check_ids']: raw['checks'][k].update(met=False, needs_review=True)
        result = aggregate(raw, spec)
        self.assertEqual(result['verdict'], 'PASS'); self.assertFalse(result['needs_review'])
        key = next(k for k in spec['check_ids'] if k not in spec['excluded_check_ids'])
        raw['checks'][key]['needs_review'] = True
        result = aggregate(raw, spec)
        self.assertEqual(result['verdict'], 'PASS'); self.assertEqual(result['review_checks'], [key])
        raw['checks'][key]['met'] = False
        self.assertEqual(aggregate(raw, spec)['failed_checks'], [key])

    def test_duplicate_and_nonfinite_rejected(self):
        for text in ['{"checks":{},"checks":{}}', '{"x":NaN}', '{"x":Infinity}']:
            with self.assertRaises(ValueError): strict_json(text)
        with self.assertRaises(ValueError): indexed([{'qid': 'a'}, {'qid': 'a'}])

    def test_wrong_model_and_truncated_response(self):
        env = {'model': 'gpt-6-sol', 'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(self.raw)}}]}
        self.assertEqual(parse_envelope(env, 'gpt-6-sol'), self.raw)
        env['model'] = 'another-model'
        with self.assertRaises(ValueError): parse_envelope(env, 'gpt-6-sol')
        env['model'] = 'gpt-6-sol'; env['choices'][0]['finish_reason'] = 'length'
        with self.assertRaises(ValueError): parse_envelope(env, 'gpt-6-sol')

    @requires_criteria
    def test_request_uses_released_english_input(self):
        request = payload(self.spec, b'fixture bytes', 'gpt-6-sol')
        self.assertEqual(len(request['messages']), 1)
        parts = request['messages'][0]['content']; self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0]['text'], read_text(ROOT / self.spec['judge']))
        self.assertIn('Write each observation in concise English', parts[0]['text'])
        self.assertEqual(request['response_format']['json_schema']['schema'], read(ROOT / self.spec['schema']))
        self.assertNotIn('tools', request); self.assertEqual(request['reasoning_effort'], 'medium')

    @requires_criteria
    def test_archived_criterion_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'benchmark').mkdir()
            with zipfile.ZipFile(root / 'benchmark/criteria.zip', 'w') as archive:
                for key in ['judge', 'schema']:
                    data = read_bytes(ROOT / self.spec[key])
                    if key == 'judge': data += b'changed'
                    archive.writestr(Path(self.spec[key]).relative_to('benchmark').as_posix(), data)
            with self.assertRaisesRegex(ValueError, 'Criterion checksum mismatch'):
                verify_spec(self.spec, root)

    @requires_criteria
    def test_missing_archive_member_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'benchmark').mkdir()
            with zipfile.ZipFile(root / 'benchmark/criteria.zip', 'w') as archive:
                archive.writestr(Path(self.spec['judge']).relative_to('benchmark').as_posix(), read_bytes(ROOT / self.spec['judge']))
            with self.assertRaises(FileNotFoundError): verify_spec(self.spec, root)

    @requires_criteria
    def test_duplicate_archive_members_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'benchmark').mkdir()
            name = Path(self.spec['judge']).relative_to('benchmark').as_posix()
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                with zipfile.ZipFile(root / 'benchmark/criteria.zip', 'w') as archive:
                    archive.writestr(name, read_bytes(ROOT / self.spec['judge']))
                    archive.writestr(name, b'conflicting replacement')
            with self.assertRaisesRegex(ValueError, 'Duplicate criterion archive entries'):
                verify_spec(self.spec, root)

    @requires_criteria
    def test_criterion_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec = copy.deepcopy(self.spec)
            for key in ['judge', 'schema']:
                path = root / spec[key]; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(read_bytes(ROOT / spec[key]))
            (root / spec['judge']).write_text('changed instructions')
            with self.assertRaises(ValueError): verify_spec(spec, root)

class RunnerTests(unittest.TestCase):
    def args(self, output):
        return argparse.Namespace(manifest=ROOT / 'evaluation/examples/input.jsonl', generator='synthetic-test-generator', responses=None, request_only=True, run=False, model='gpt-6-sol', allow_different_model=False, endpoint=None, max_calls=2, output=output)

    @requires_criteria
    def test_cached_mode_has_no_network_and_preserves_synthetic_decisions(self):
        with tempfile.TemporaryDirectory() as tmp, patch('evaluation.evaluate.post_once', side_effect=AssertionError('Network called')):
            args = self.args(Path(tmp) / 'out')
            args.request_only = False
            args.responses = Path(tmp) / 'synthetic-responses'
            args.responses.mkdir()
            specs = load_specs()
            for qid, failed, review in [('LEVI-1169', (), ()), ('LEVI-1143', ('R01',), ('R02',))]:
                (args.responses / (qid + '.json')).write_text(json.dumps(synthetic_response(specs[qid], failed, review)))
            with contextlib.redirect_stdout(io.StringIO()): run(args)
            summary = read(args.output / 'summary.json')
            self.assertEqual(summary['logical_calls'], 0); self.assertEqual(summary['completed'], 2)
            expected = {
                'LEVI-1169': {'verdict': 'PASS', 'failed_checks': [], 'review_checks': [], 'needs_review': False},
                'LEVI-1143': {'verdict': 'FAIL', 'failed_checks': ['R01'], 'review_checks': ['R02'], 'needs_review': True},
            }
            for row in read_jsonl(args.output / 'records.jsonl'):
                for key, value in expected[row['qid']].items(): self.assertEqual(row[key], value)
            with self.assertRaises(ValueError): run(args)

    @requires_criteria
    def test_request_preparation_is_offline_and_has_no_verdict(self):
        with tempfile.TemporaryDirectory() as tmp, patch('evaluation.evaluate.post_once') as network:
            args = self.args(Path(tmp) / 'out')
            with contextlib.redirect_stdout(io.StringIO()): run(args)
            network.assert_not_called()
            records = read_jsonl(args.output / 'records.jsonl')
            self.assertEqual(len(records), 2)
            for row in records:
                self.assertEqual(row['status'], 'request_prepared')
                self.assertNotIn('verdict', row)
                request = read(args.output / row['qid'] / 'request.json')
                self.assertIn('Write each observation in concise English', request['messages'][0]['content'][0]['text'])
            self.assertEqual(read(args.output / 'summary.json')['logical_calls'], 0)

    def test_bad_manifest_has_no_output_or_call(self):
        with tempfile.TemporaryDirectory() as tmp, patch('evaluation.evaluate.post_once') as network:
            args = self.args(Path(tmp) / 'out'); args.manifest = Path(tmp) / 'bad.jsonl'
            args.manifest.write_text('{"qid":"UNKNOWN","image":"missing.png"}\n')
            with self.assertRaises(ValueError): run(args)
            self.assertFalse(args.output.exists()); network.assert_not_called()

    @requires_criteria
    def test_runtime_error_stops_and_is_not_visual_fail(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'LEVI_JUDGE_API_KEY': 'test-only-not-a-key'}):
            args = self.args(Path(tmp) / 'out'); args.request_only = False; args.run = True; args.endpoint = 'https://example.invalid/v1/chat/completions'
            with patch('evaluation.evaluate.post_once', side_effect=TimeoutError('synthetic timeout')) as network:
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit): run(args)
                self.assertEqual(network.call_count, 1)
            rows = read_jsonl(args.output / 'records.jsonl')
            self.assertEqual(rows[0]['status'], 'call_or_validation_error'); self.assertNotIn('verdict', rows[0])
            self.assertEqual(len(read(args.output / 'summary.json')['not_submitted']), 1)

    def test_budget_checked_before_network(self):
        with tempfile.TemporaryDirectory() as tmp, patch('evaluation.evaluate.post_once') as network:
            args = self.args(Path(tmp) / 'out'); args.request_only = False; args.run = True; args.max_calls = 1
            with self.assertRaises(ValueError): run(args)
            self.assertFalse(args.output.exists()); network.assert_not_called()

class ReleaseTests(unittest.TestCase):
    @requires_criteria
    def test_complete_release(self):
        self.assertEqual(validate(), {'tasks': 1375, 'bvis': 120, 'criteria_checked': True})

    @requires_criteria
    def test_extra_criterion_files_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / 'benchmark', root / 'benchmark')
            with zipfile.ZipFile(root / 'benchmark/criteria.zip', 'a') as archive:
                archive.writestr('criteria/LEVI-0001/effective_criteria.json', '{}')
            with self.assertRaisesRegex(ValueError, 'Expected exactly judge.txt and schema.json'):
                validate(root)

    def test_metadata_only_without_downloaded_criteria(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / 'benchmark', root / 'benchmark', ignore=shutil.ignore_patterns('criteria.zip', 'criteria'))
            shutil.copytree(ROOT / 'evaluation/examples', root / 'evaluation/examples')
            self.assertEqual(validate(root, metadata_only=True), {'tasks': 1375, 'bvis': 120, 'criteria_checked': False})

    def test_full_validation_requires_downloaded_criteria(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / 'benchmark', root / 'benchmark', ignore=shutil.ignore_patterns('criteria.zip', 'criteria'))
            with self.assertRaisesRegex(FileNotFoundError, 'Place criteria.zip in benchmark/'):
                validate(root)

    def test_examples_reference_existing_tasks_and_images(self):
        from evaluation.core import sha
        tasks = indexed(read_jsonl(ROOT / 'benchmark/tasks.jsonl'))
        inputs = read_jsonl(ROOT / 'evaluation/examples/input.jsonl')
        self.assertEqual(len(inputs), 2)
        for item in inputs:
            self.assertIn(item['qid'], tasks)
            self.assertEqual(sha(ROOT / 'evaluation/examples' / item['image']), item['image_sha256'])

if __name__ == '__main__': unittest.main()
