---
name: add-or-update-disease-preset-and-validation
description: Workflow command scaffold for add-or-update-disease-preset-and-validation in ibm-z-hackathon.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /add-or-update-disease-preset-and-validation

Use this workflow when working on **add-or-update-disease-preset-and-validation** in `ibm-z-hackathon`.

## Goal

Adds a new disease to the model, including SEIR parameters, origin country, and validation/backtest scenario.

## Common Files

- `backend/app/data/diseases.json`
- `backend/app/data/countries.json`
- `backend/app/data/disease_corpus.json`
- `backend/app/disease_lookup.py`
- `backend/backtest/validate.py`
- `backend/backtest/validate_ensemble.py`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Edit or add entry in backend/app/data/diseases.json with new disease parameters.
- Update backend/app/data/countries.json if new origin countries are needed.
- Update backend/app/data/disease_corpus.json for LLM lookup and aliases.
- Modify backend/app/disease_lookup.py to handle new disease or origin logic.
- Add or update validation logic in backend/backtest/validate.py and backend/backtest/validate_ensemble.py.

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.