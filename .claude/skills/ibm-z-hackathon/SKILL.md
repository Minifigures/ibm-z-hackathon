```markdown
# ibm-z-hackathon Development Patterns

> Auto-generated skill from repository analysis

## Overview

This skill covers the development patterns and workflows of the `ibm-z-hackathon` repository. The project is primarily Python-based (with a TypeScript/React frontend), focused on disease modeling, simulation, and interactive visualization. It features robust backend logic for disease parameter management, LLM-powered disease lookup, and a modern frontend for data exploration. The repository follows clear coding conventions, structured workflows, and includes both backend and frontend testing.

---

## Coding Conventions

**File Naming**
- Use `snake_case` for Python files:  
  Example: `disease_lookup.py`, `test_endpoints.py`
- Use `camelCase` or `PascalCase` for TypeScript/React components:  
  Example: `disease-search.tsx`, `page.tsx`

**Import Style**
- Use aliases for imports in Python:
  ```python
  import numpy as np
  import pandas as pd
  ```
- In TypeScript:
  ```typescript
  import React from 'react';
  import { fetchDisease } from '../lib/api';
  ```

**Export Style**
- Use named exports:
  ```python
  # Python
  def lookup_disease(...):
      ...
  ```
  ```typescript
  // TypeScript
  export function DiseaseSearch() { ... }
  ```

**Commit Messages**
- Use [Conventional Commits](https://www.conventionalcommits.org/):
  - Prefixes: `feat`, `docs`, `fix`, `merge`
  - Example:  
    `feat: add SEIR parameters for new disease preset`

---

## Workflows

### Add or Update Disease Preset and Validation
**Trigger:** When adding a new disease to the simulation or validating predictions  
**Command:** `/add-disease-preset`

1. Edit or add entry in `backend/app/data/diseases.json` with new disease parameters (e.g., SEIR values).
2. Update `backend/app/data/countries.json` if new origin countries are needed.
3. Update `backend/app/data/disease_corpus.json` for LLM lookup and aliases.
4. Modify `backend/app/disease_lookup.py` to handle new disease or origin logic.
5. Add or update validation logic in `backend/backtest/validate.py` and `backend/backtest/validate_ensemble.py`.
6. Update `backend/app/main.py` to expose the new disease in API endpoints.
7. Add or update tests in `backend/tests/test_endpoints.py` and/or `backend/tests/test_disease_lookup.py`.

**Example:**  
_Adding "DiseaseX" with SEIR parameters:_
```json
// backend/app/data/diseases.json
{
  "DiseaseX": {
    "beta": 0.3,
    "gamma": 0.1,
    "sigma": 0.2,
    "origin": "CountryY"
  }
}
```

---

### Add or Enhance LLM Disease Lookup Feature
**Trigger:** When improving or expanding LLM-powered disease parameter lookup or origin inference  
**Command:** `/update-llm-disease-lookup`

1. Edit `backend/app/disease_lookup.py` to adjust LLM prompt, validation, or lookup logic.
2. Update `backend/app/data/disease_corpus.json` with new diseases or aliases.
3. Edit `backend/app/data/countries.json` if new origin countries are supported.
4. Update `frontend/components/disease-search.tsx` and `frontend/lib/api.ts` to reflect new API contract or UI logic.
5. Update or add tests in `backend/tests/test_disease_lookup.py` and `frontend/tests/disease-search.test.tsx`.

**Example:**  
_Adding an alias in the corpus:_
```json
// backend/app/data/disease_corpus.json
{
  "DiseaseX": ["DX", "X-disease", "Disease X"]
}
```

---

### Frontend Feature or UI Panel Addition
**Trigger:** When adding or significantly enhancing a frontend visualization or interactive panel  
**Command:** `/add-frontend-panel`

1. Create or update `frontend/components/*.tsx` for the new panel or visualization.
2. Update `frontend/app/page.tsx` to integrate the new component or adjust layout.
3. Modify `frontend/lib/api.ts` to support new API data or types.
4. Add or update tests in `frontend/tests/*.test.tsx` to cover the new feature.

**Example:**  
_Adding a new panel:_
```typescript
// frontend/components/DiseaseStatsPanel.tsx
export function DiseaseStatsPanel(props) {
  // Panel implementation
}
```
```typescript
// frontend/app/page.tsx
import { DiseaseStatsPanel } from '../components/DiseaseStatsPanel';
// ...add <DiseaseStatsPanel /> to the layout
```

---

### Merge Feature Branch with Conflict Resolution
**Trigger:** When integrating a completed feature branch, especially after parallel development  
**Command:** `/merge-feature-branch`

1. Merge the remote-tracking branch into the target branch.
2. Resolve conflicts in overlapping files (e.g., `backend/app/main.py`, `backend/app/data/diseases.json`, `frontend/lib/api.ts`).
3. Integrate or reconcile test changes (`backend/tests/test_endpoints.py`, `frontend/tests/*.test.tsx`).
4. Verify all tests pass after the merge.

**Example:**  
_Resolving a conflict in `diseases.json`:_
```json
<<<<<<< HEAD
  "DiseaseA": { ... }
=======
  "DiseaseA": { ...updated... }
>>>>>>> feature-branch
```
_Manually reconcile, then remove conflict markers._

---

## Testing Patterns

- **Backend (Python):**
  - Tests are located in `backend/tests/`
  - Use `snake_case` for test files: `test_endpoints.py`, `test_disease_lookup.py`
  - Example:
    ```python
    def test_disease_lookup_valid():
        ...
    ```

- **Frontend (TypeScript/React):**
  - Uses `vitest` as the testing framework
  - Test files follow the pattern: `*.test.tsx`
  - Example:
    ```typescript
    import { render } from '@testing-library/react';
    import { DiseaseSearch } from '../components/disease-search';

    test('renders DiseaseSearch', () => {
      render(<DiseaseSearch />);
      // assertions
    });
    ```

---

## Commands

| Command                  | Purpose                                                      |
|--------------------------|--------------------------------------------------------------|
| /add-disease-preset      | Add or update a disease preset and validation scenario       |
| /update-llm-disease-lookup | Enhance LLM disease lookup or origin inference logic        |
| /add-frontend-panel      | Add or update a frontend visualization or interactive panel  |
| /merge-feature-branch    | Merge a feature branch and resolve conflicts                 |
```
