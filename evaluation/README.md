# Evaluation

Run commands from the repository root with **Python 3.10+**. No third-party packages are required. Download `criteria.zip` to `benchmark/` before preparing requests or evaluating images. The runner reads the archive directly. [Download links](../benchmark/README.md#downloads) are forthcoming.

## Validate the dataset

Check bundled task metadata:

```sh
python3 -m evaluation.validate --metadata-only
```

After installing `criteria.zip`, run `python3 -m evaluation.validate` for full validation, including the exact two-file criterion layout and the package hash.

## Offline request example

Requires `benchmark/criteria.zip`.

```sh
python3 -m evaluation.evaluate \
  --manifest evaluation/examples/input.jsonl --generator gpt-image-2 \
  --request-only --output runs/example
```

This prepares evaluation requests without an API key or model call. Use a new output directory for each run.

### Bundled examples

| Task | Original image |
|---|---|
| LEVI-1169 | Egg-carton occupancy and an external egg |
| LEVI-1143 | Egg-carton and blister-pack correspondence |

`examples/input.jsonl` links task IDs, image paths and hashes. `examples/images/` contains two original 1024 × 1024 GPT Image 2 PNGs. No saved model responses are bundled.

The images demonstrate request preparation and are not presented as gold-standard correct images. Tests use synthetic responses to check the evaluation logic.

## Evaluate your images

Create a JSONL manifest with one unique task per line. Image paths are relative to the manifest file:

```json
{"qid":"LEVI-1169","image":"images/LEVI-1169.png"}
```

An optional `image_sha256` field checks image integrity. Inputs must be original 1024 × 1024 PNG outputs; the runner does not resize them.

Use `--request-only` as in the offline example to inspect requests without sending them.

Each request contains the task's instructions, one image and the structured response schema. Reference SVGs, stored outcomes and human reviews are not provided to the judge.

For a live run, set `LEVI_JUDGE_API_KEY` and `LEVI_JUDGE_ENDPOINT` in your environment. The endpoint must be a full HTTPS Chat Completions URL supporting the requested model and JSON schema:

```sh
python3 -m evaluation.evaluate \
  --manifest my-images.jsonl --generator my-generator \
  --run --endpoint "$LEVI_JUDGE_ENDPOINT" \
  --max-calls 1375 --output runs/my-generator
```

**Live runs can incur API charges.** `--max-calls` is an upper bound and must cover the supplied manifest. Validation, request preparation, saved-response replay and tests make no paid calls.

The default judge is `gpt-6-sol`, with medium reasoning effort and an 8192-token completion limit. A different judge requires `--model` and `--allow-different-model`; its results are marked accordingly. The runner does not retry or switch providers automatically. The live API path has been tested offline with simulated responses, not verified against a live service in this release.

## Replay your saved responses

For responses from your own evaluation, place one `<qid>.json` file per task in a response directory and use `--responses /path/to/responses` instead of `--request-only` or `--run`. This validates and aggregates those responses without calling a model. Image-hash checking alone cannot establish that the responses were produced from those images.

## Decisions and outputs

Every check must contain exactly `met`, `observation` and `needs_review`. Missing checks, extra fields, duplicate JSON keys and invalid types are rejected. Whole-task `verdict` is PASS only if all included checks have `met=true`. `failed_checks` lists violations; `review_checks` and `needs_review` retain diagnostic uncertainty separately.

`excluded_check_ids` in the task specification are applied consistently. For example, R03 for LEVI-0830 remains in the response schema but is excluded from the decision and review flags.

Outputs include:

- `run.json`: selected tasks, generator label, judge configuration and execution mode.
- `<qid>/request.json` in request-preparation mode, or saved responses and `<qid>/result.json` after evaluation.
- `records.jsonl`: per-task records, including `verdict` for completed assessments.
- `summary.json`: processed/completed counts, model-call count and unsubmitted tasks.

The runner checks all inputs before starting and stops after the first runtime or response-validation failure. Such failures receive `call_or_validation_error`, not a visual FAIL. Existing output directories are rejected to avoid overwriting prior runs. A subset run is not a full-benchmark leaderboard entry; model observations are not independently established ground truth.

## Code layout and tests

- `evaluate.py`: request preparation, live evaluation and saved-response replay.
- `core.py`: criterion loading, response validation and whole-task decisions.
- `validate.py`: dataset and package-integrity checks.
- `examples/`: original images and an input manifest for request preparation.
- `tests/`: offline regression tests.

```sh
python3 -m unittest discover -s evaluation/tests -v
```

Metadata and missing-download checks run without the criterion package. Criterion-dependent tests run when `benchmark/criteria.zip` is installed; otherwise they are explicitly skipped.

Full per-model result archives are not included; `results/` is a placeholder. The project website and paper report the recorded outcomes.
