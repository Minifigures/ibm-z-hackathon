---
name: feature-development-with-tests-and-docs
description: Workflow command scaffold for feature-development-with-tests-and-docs in ibm-z-hackathon.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /feature-development-with-tests-and-docs

Use this workflow when working on **feature-development-with-tests-and-docs** in `ibm-z-hackathon`.

## Goal

Implements a new feature or major enhancement, updating core logic, adding new data or endpoints, updating or creating corresponding frontend components, and always including or updating tests and documentation.

## Common Files

- `backend/app/*.py`
- `backend/app/data/*.json`
- `backend/scripts/*.py`
- `frontend/components/*.tsx`
- `frontend/lib/*.ts`
- `frontend/tests/*.test.ts`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Implement backend logic and/or data ingestion scripts (e.g., add new Python modules, update data JSONs, scripts in backend/scripts/).
- Update or add new frontend components and supporting libraries (e.g., new .tsx components, update lib/api.ts).
- Add or update tests for new features (e.g., backend/tests/, frontend/tests/).
- Update documentation and/or deployment instructions (e.g., README.md, DEPLOY.md).

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.