# LEVI benchmark

The benchmark contains **1,375 text-to-image tasks** spanning **120 base visual identity spaces (BVIS)**. Each BVIS belongs to one domain; tasks may combine several BVIS and domains. Domain task counts therefore overlap.

| Domain | Tasks containing the domain | BVIS | Identity requirements |
|---|---:|---:|---|
| Symbolic | 421 | 17 | glyphs, strings, symbols and codes |
| Geometric | 630 | 24 | shape, orientation, proportion and symmetry |
| Topological | 545 | 18 | connectivity, loops, paths and links |
| Layout | 570 | 22 | order, grouping, containment and assignment |
| Quantitative | 328 | 19 | counts, readings and distributions |
| Procedural | 254 | 20 | sequences, transformations and intermediate states |

## Files

| File or directory | Contents |
|---|---|
| [tasks.jsonl](tasks.jsonl) | Generation prompts, task IDs, domain and BVIS memberships, and prompt hashes |
| [bvis.json](bvis.json) | BVIS names, identity definitions and domains |
| [evaluation_specs.json](evaluation_specs.json) | Per-task instruction/schema paths, check IDs, exclusions and hashes |
| `criteria.zip` | Evaluation instructions and schemas; download separately |
| [checksums.json](checksums.json) | Integrity hashes for the data, complete ZIP and evaluation examples |
| [assets/](assets/) | Vector reference assets; download separately |

Task memberships are defined in `tasks.jsonl`. Filter its `domains` or `bvis` fields to select a subset. No separate membership index is needed.

## Downloads

Evaluation criteria and vector reference assets will be hosted in a Hugging Face dataset repository. Download links are forthcoming.

| Package | Availability | Local destination | Setup |
|---|---|---|---|
| `criteria.zip` | Forthcoming | `benchmark/criteria.zip` | Keep the ZIP; do not extract |
| Vector assets | Forthcoming | `benchmark/assets/` | Extract the vector files here |

These assets are not tracked in the GitHub repository. The expected criterion-package hash is included in `checksums.json`. Vector references are optional for running the image judge and are not sent to it.

## Identifiers and fields

Tasks use **`LEVI-0001`–`LEVI-1375`**; BVIS entries use **`BVIS-001`–`BVIS-120`**. These stable IDs link prompts, memberships, evaluation specifications and example images.

A task contains `qid`, `domains`, `bvis`, `prompt_en` and `prompt_sha256`. A BVIS entry contains `bvis_id`, `name`, `predicate` and `domain`. `predicate` describes the defining identity condition. IDs do not encode difficulty or a train/test split.

Generate images with **`prompt_en`**. Use text-only input; reference SVGs and ground-truth constructions are not generator inputs.

## Evaluation criteria

The criterion package contains exactly two files per task, giving 2,750 files in total:

```text
criteria/
└── <task-id>/
    ├── judge.txt
    └── schema.json
```

- `judge.txt` contains the instructions sent to the judge: the generation prompt, required checks and applicable scope rules.
- `schema.json` defines the response. Each check returns `met` (boolean), `observation` (string) and `needs_review` (boolean).

The evaluation runner reads the archive directly; no extraction is required. Paths such as `benchmark/criteria/<qid>/judge.txt` in `evaluation_specs.json` identify archive members.

The package defines the task criteria used by the evaluation runner. Reported paper scores come from the study’s evaluation runs; running the evaluator does not reproduce those outcomes exactly.

`R00`, `R01`, etc. identify checks within a task. `C01` and `P01`, where present, identify conditions and predicate groups within that same task. They are not additional tasks or BVIS entries.

## Construction and score interpretation

The tasks were selected from a 1,600-task authoring inventory. Curation considered redundancy, semantic ambiguity, domain balance and observed ease after generation. The dataset is not an independent held-out random sample and has no train/test split.

The recorded judge is GPT-6-Sol with medium reasoning effort. Whole-task PASS requires every included check to be satisfied. Excluded checks do not affect the decision. Review flags are retained separately; runtime or response-format errors are not visual FAIL judgments. Independent human agreement has not been measured.

Reported pass rates use the full task denominator for the relevant subset; generation failures receive zero credit. Domain scores include all tasks containing the domain. BVIS-balanced scores average whole-task success among tasks containing each BVIS, then weight represented BVIS equally within a domain. They do not measure isolated component accuracy.

There are 143 / 421 / 811 tasks with 1 / 2 / 3+ BVIS, and 367 / 1,008 single-domain / cross-domain tasks. These group comparisons are descriptive, not controlled estimates of a composition penalty. Website examples are illustrative selections, not a sample for estimating failure frequencies.

## Validation and included assets

Check the bundled metadata before downloading:

```sh
python3 -m evaluation.validate --metadata-only
```

After installing `criteria.zip`, run `python3 -m evaluation.validate` to also check schemas, archive contents and the downloaded file hash. Neither command calls a model.

Two original 1024 × 1024 PNGs and an input manifest are included in [`evaluation/examples/`](../evaluation/examples/) for offline request preparation. Website WebPs are display copies and must not replace original PNGs in evaluation. The full generated-image corpus and per-model result archive are not bundled; `results/` remains a placeholder.

See the [evaluation guide](../evaluation/README.md) for runnable examples and new-image evaluation.
