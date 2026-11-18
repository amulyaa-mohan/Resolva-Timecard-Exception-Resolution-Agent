# Reports

Actual, reproducible evaluation reports produced by `python -m evals.run`. Each report records the
git commit, provider, model, prompt version, validator and settings it was produced with.

- `ollama-qwen2.5-7b-instruct-propose_v1.*` and `...-propose_v2.*`: real-model runs on a local GPU,
  used for the prompt v1 vs v2 comparison.
- The mock report is produced by CI on every run (artifact `eval-report-mock`) and is not committed.

Only numbers that appear in these files belong in slides or the README. Reports produced with the
stand-in validator say so in their Limitations section.
