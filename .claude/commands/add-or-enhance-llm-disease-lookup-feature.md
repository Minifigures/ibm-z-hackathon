---
name: add-or-enhance-llm-disease-lookup-feature
description: Workflow command scaffold for add-or-enhance-llm-disease-lookup-feature in ibm-z-hackathon.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /add-or-enhance-llm-disease-lookup-feature

Use this workflow when working on **add-or-enhance-llm-disease-lookup-feature** in `ibm-z-hackathon`.

## Goal

Extends or improves the LLM-powered disease lookup, including origin country inference and validation.

## Common Files

- `backend/app/disease_lookup.py`
- `backend/app/data/disease_corpus.json`
- `backend/app/data/countries.json`
- `frontend/components/disease-search.tsx`
- `frontend/lib/api.ts`
- `backend/tests/test_disease_lookup.py`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Edit backend/app/disease_lookup.py to adjust LLM prompt, validation, or logic.
- Update backend/app/data/disease_corpus.json with new diseases or aliases.
- Edit backend/app/data/countries.json if new origin countries are supported.
- Update frontend/components/disease-search.tsx and frontend/lib/api.ts to reflect new API contract or UI logic.
- Update or add tests in backend/tests/test_disease_lookup.py and frontend/tests/disease-search.test.tsx.

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.