---
name: research-paper-integration-and-documentation
description: Workflow command scaffold for research-paper-integration-and-documentation in ibm-z-hackathon.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /research-paper-integration-and-documentation

Use this workflow when working on **research-paper-integration-and-documentation** in `ibm-z-hackathon`.

## Goal

Adds new research papers to the documentation, mapping them to features or equations in the codebase, and updating integration playbooks.

## Common Files

- `docs/*.pdf`
- `docs/RESEARCH_PAPERS.md`
- `docs/INTEGRATION_PLAYBOOK.md`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Add new PDF files for each research paper to docs/.
- Update or create mapping files (e.g., RESEARCH_PAPERS.md, INTEGRATION_PLAYBOOK.md) to link papers to features.
- Reference new papers in code or documentation as needed.

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.