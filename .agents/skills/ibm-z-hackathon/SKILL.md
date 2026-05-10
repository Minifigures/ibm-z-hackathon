```markdown
# ibm-z-hackathon Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill introduces the development patterns and workflows used in the `ibm-z-hackathon` repository. The codebase is primarily Python, with a focus on backend logic, data processing, and integration with research documentation. The repository emphasizes clear coding conventions, conventional commits, and robust documentation and testing practices. This guide will help you contribute effectively by following established patterns for code, documentation, and workflow automation.

## Coding Conventions

### File Naming
- Use **snake_case** for all Python files and modules.
  - Example: `data_ingestion.py`, `model_utils.py`

### Import Style
- Use **alias imports** for external libraries and internal modules.
  - Example:
    ```python
    import numpy as np
    import pandas as pd
    from backend.app import data_utils as du
    ```

### Export Style
- Use **named exports** (explicitly listing what is exported from a module).
  - Example:
    ```python
    # In utils.py
    def process_data(...):
        ...

    def clean_data(...):
        ...

    __all__ = ['process_data', 'clean_data']
    ```

### Commit Messages
- Follow **conventional commit** style.
  - Prefixes: `feat`, `docs`
  - Example:
    ```
    feat: add new data ingestion pipeline for user uploads
    docs: update deployment instructions for new API endpoint
    ```

## Workflows

### Feature Development with Tests and Docs
**Trigger:** When adding a significant new capability (e.g., new modeling, visualization, or API endpoint)  
**Command:** `/new-feature`

1. **Implement backend logic and/or data ingestion scripts**
   - Add new Python modules or update existing ones in `backend/app/`.
   - Example:
     ```python
     # backend/app/new_feature.py
     def new_model(...):
         ...
     ```
   - Update or add data files in `backend/app/data/` or scripts in `backend/scripts/`.

2. **Update or add new frontend components and supporting libraries**
   - Add or modify `.tsx` components in `frontend/components/`.
   - Update API libraries in `frontend/lib/`.

3. **Add or update tests for new features**
   - Place backend tests in `backend/tests/`.
   - Place frontend tests in `frontend/tests/` (e.g., `*.test.ts`).

4. **Update documentation and/or deployment instructions**
   - Update `README.md` and `DEPLOY.md` to reflect new features or changes.

**Example Directory Changes:**
```
backend/app/new_feature.py
backend/app/data/new_data.json
backend/scripts/process_new_data.py
frontend/components/NewFeatureComponent.tsx
frontend/lib/api.ts
backend/tests/test_new_feature.py
DEPLOY.md
README.md
```

---

### Research Paper Integration and Documentation
**Trigger:** When documenting research basis for modeling or adding new literature  
**Command:** `/add-paper`

1. **Add new PDF files for each research paper**
   - Place PDFs in `docs/`.
   - Example: `docs/Smith2023_ModelingApproach.pdf`

2. **Update or create mapping files**
   - Edit `docs/RESEARCH_PAPERS.md` to list and describe each paper.
   - Update `docs/INTEGRATION_PLAYBOOK.md` to map papers to features or equations.

3. **Reference new papers in code or documentation as needed**
   - Add citations or references in code comments or markdown files.

**Example Documentation Update:**
```markdown
# docs/RESEARCH_PAPERS.md

## Smith2023_ModelingApproach.pdf
- Used for: Data normalization in backend/app/data_processing.py
```

---

## Testing Patterns

- **Framework:** Unknown (custom or standard Python testing)
- **File Pattern:** Test files follow the `*.test.*` naming convention.
  - Example: `backend/tests/data_ingestion.test.py`
- **Placement:** Tests are located in `backend/tests/` and `frontend/tests/`.
- **Best Practice:** Always include or update tests when adding new features or making changes.

**Example Test File:**
```python
# backend/tests/data_ingestion.test.py
import pytest
from backend.app import data_ingestion

def test_process_valid_data():
    ...
```

## Commands

| Command       | Purpose                                                      |
|---------------|--------------------------------------------------------------|
| /new-feature  | Start the feature development workflow with tests and docs    |
| /add-paper    | Add a new research paper and update documentation mappings    |
```