"""Evaluate supplied PNGs against task criteria, or replay saved responses."""
import argparse
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import struct
import time
from urllib.parse import urlsplit

from .core import ROOT, aggregate, indexed, load_specs, read, read_jsonl, read_text, strict_json, verify_spec


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def image_bytes(path):
    data = path.read_bytes()
    if len(data) < 33 or data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
        raise ValueError('Expected a PNG: ' + str(path))
    if struct.unpack('>II', data[16:24]) != (1024, 1024):
        raise ValueError('Expected a 1024 x 1024 PNG; use the original output image')
    return data


def payload(spec, image, model, root=ROOT):
    return {'model': model, 'reasoning_effort': 'medium', 'max_completion_tokens': 8192,
            'stream': False, 'store': False,
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'levi_checks', 'strict': True, 'schema': read(root / spec['schema'])}},
            'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': read_text(root / spec['judge'])},
                          {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(image).decode()}}]}]}


def parse_envelope(envelope, model):
    returned = envelope.get('model')
    if not isinstance(returned, str) or not (returned == model or returned.startswith(model + '-')):
        raise ValueError('Wrong or absent returned model')
    choices = envelope.get('choices', [])
    if len(choices) != 1:
        raise ValueError('Expected one response choice')
    choice = choices[0]; message = choice.get('message', {})
    if choice.get('finish_reason') != 'stop' or message.get('refusal') or message.get('tool_calls'):
        raise ValueError('Incomplete, refused, or tool-using response')
    return strict_json(message['content'])


def post_once(endpoint, key, request):
    url = urlsplit(endpoint)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('Use an explicit HTTPS endpoint without credentials/query/fragment')
    conn = http.client.HTTPSConnection(url.hostname, url.port, timeout=300)
    try:
        conn.request('POST', url.path, body=json.dumps(request, ensure_ascii=False).encode(),
                     headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        response = conn.getresponse(); data = response.read()
        if response.status != 200:
            # Do not echo server error bodies, which may contain credentials.
            raise ValueError('HTTP ' + str(response.status))
        if key.encode() in data:
            raise ValueError('Credential echoed by endpoint; response not stored')
        return strict_json(data.decode('utf-8'))
    finally:
        conn.close()


def run(args):
    specs = load_specs()
    inputs = indexed(read_jsonl(args.manifest))
    if not inputs or not set(inputs) <= set(specs):
        raise ValueError('Empty manifest or unknown task IDs')
    if args.run and (args.max_calls < len(inputs) or args.max_calls < 1):
        raise ValueError('Set --max-calls to cover the supplied image count before live execution')
    if args.model != 'gpt-6-sol' and not args.allow_different_model:
        raise ValueError('A different judge requires --allow-different-model and is a new protocol')
    output = args.output.resolve()
    for name in ['benchmark', 'results', 'docs', 'evaluation', '.git']:
        if output == ROOT / name or ROOT / name in output.parents:
            raise ValueError('Write results outside dataset and source directories')
    if output.exists():
        raise ValueError('Output directory already exists; no implicit resume, overwrite, or retry')
    prepared = []
    for q, row in inputs.items():
        path = (args.manifest.parent / row['image']).resolve()
        data = image_bytes(path); digest = hashlib.sha256(data).hexdigest()
        if row.get('image_sha256') and digest != row['image_sha256']:
            raise ValueError('Image hash mismatch: ' + q)
        verify_spec(specs[q])
        cached = read(args.responses / (q + '.json')) if args.responses else None
        if cached is not None:
            aggregate(cached, specs[q])
        prepared.append((q, data, digest, cached))
    key = None
    if args.run:
        if not args.endpoint:
            raise ValueError('--endpoint is required for live execution')
        key = os.environ.get('LEVI_JUDGE_API_KEY')
        if not key:
            raise ValueError('Set LEVI_JUDGE_API_KEY in the environment')
    output.mkdir(parents=True)
    mode = 'cached_response' if args.responses else 'request_only' if args.request_only else 'live'
    write(output / 'run.json', {'mode': mode, 'generator': args.generator, 'requested_judge': args.model,
          'reasoning_effort': 'medium', 'endpoint': args.endpoint if args.run else None,
          'different_judge': args.model != 'gpt-6-sol',
          'selected_tasks': list(inputs), 'active_retries': 0, 'full_benchmark': len(inputs) == 1375,
          'cached_response_note': 'Supplied JSON is consumed as provided; it does not prove the judge saw this image.' if args.responses else None})
    records = []; calls = 0
    for q, data, digest, cached in prepared:
        spec = specs[q]; start = time.monotonic()
        record = {'qid': q, 'generator': args.generator, 'image_sha256': digest,
                  'judge_sha256': spec['judge_sha256'], 'schema_sha256': spec['schema_sha256'],
                  'status': 'request_prepared' if args.request_only else 'call_or_validation_error',
                  'mode': mode, 'logical_calls': 0}
        try:
            if args.request_only:
                write(output / q / 'request.json', payload(spec, data, args.model))
            else:
                if args.run:
                    calls += 1; record['logical_calls'] = 1
                    # Persist an attempt marker before transmission; never retry an uncertain outcome.
                    write(output / q / 'attempt.json', {'logical_attempt': 1, 'automatic_retries': 0, 'image_sha256': digest})
                    envelope = post_once(args.endpoint, key, payload(spec, data, args.model))
                    write(output / q / 'response.json', envelope)
                    cached = parse_envelope(envelope, args.model)
                    record['returned_model'] = envelope['model']
                decision = aggregate(cached, spec)
                write(output / q / 'raw.json', cached)
                record.update(status='completed', **decision)
        except Exception as exc:
            # Runtime/format failures are not model FAILs. Stop live batches on the first error.
            record['error_type'] = type(exc).__name__
            message = str(exc)
            record['error_message'] = (message.replace(key, '[REDACTED]') if key else message)[:300]
        record['elapsed_seconds'] = round(time.monotonic() - start, 3)
        write(output / q / 'result.json', record); records.append(record)
        if args.run and record['status'] != 'completed':
            break
    with (output / 'records.jsonl').open('x', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    write(output / 'summary.json', {'selected': len(inputs), 'processed': len(records), 'logical_calls': calls,
          'completed': sum(r['status'] == 'completed' for r in records),
          'not_submitted': [q for q in inputs if q not in {r['qid'] for r in records}]})
    print(f'{len(records)} inputs processed; {calls} model calls; results: {output}')
    if any(r['status'] == 'call_or_validation_error' for r in records):
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--generator', required=True)
    parser.add_argument('--output', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--responses', type=Path, help='Directory of saved <qid>.json judge responses; offline')
    mode.add_argument('--request-only', action='store_true', help='Build requests without network calls')
    mode.add_argument('--run', action='store_true', help='Explicitly perform potentially billable calls')
    parser.add_argument('--endpoint', help='Full HTTPS Chat Completions endpoint; no implicit provider fallback')
    parser.add_argument('--model', default='gpt-6-sol')
    parser.add_argument('--allow-different-model', action='store_true')
    parser.add_argument('--max-calls', type=int, default=1)
    try:
        run(parser.parse_args())
    except (FileNotFoundError, ValueError) as exc:
        parser.exit(2, f'Error: {exc}\n')
