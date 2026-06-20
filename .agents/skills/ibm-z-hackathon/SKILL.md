```markdown
# ibm-z-hackathon Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill teaches you the core development patterns and conventions used in the `ibm-z-hackathon` Python repository. You'll learn about the project's file organization, code style, commit conventions, and how to write and run tests. This guide is ideal for contributors aiming to maintain consistency and quality in the codebase.

## Coding Conventions

### File Naming
- Use **snake_case** for all file names.
  - Example: `data_processor.py`, `user_handler.py`

### Import Style
- Use **relative imports** within the package.
  - Example:
    ```python
    from .utils import calculate_score
    from .models import User
    ```

### Export Style
- Use **named exports** (explicitly define what is exported).
  - Example:
    ```python
    __all__ = ['process_data', 'UserModel']
    ```

### Commit Patterns
- Follow **Conventional Commits** with the `feat` prefix for new features.
  - Example:
    ```
    feat: add user authentication module
    ```
- Keep commit messages concise (average 64 characters).

## Workflows

### Feature Development
**Trigger:** When adding a new feature to the codebase  
**Command:** `/feature-dev`

1. Create a new branch for your feature.
2. Implement your feature following the coding conventions.
3. Write or update tests as needed.
4. Commit changes using the `feat:` prefix.
5. Push your branch and open a pull request.

### Testing
**Trigger:** When verifying code correctness  
**Command:** `/run-tests`

1. Identify test files (pattern: `*.test.*`).
2. Run all test files using your preferred Python test runner (e.g., `pytest` or `unittest`).
3. Review test results and fix any failing tests.

### Code Review
**Trigger:** Before merging code into the main branch  
**Command:** `/code-review`

1. Ensure code follows file naming, import, and export conventions.
2. Check that commits use the correct conventional format.
3. Verify that all tests pass.
4. Leave feedback or approve the pull request.

## Testing Patterns

- Test files follow the pattern `*.test.*` (e.g., `user_handler.test.py`).
- The specific test framework is not enforced; use standard Python testing tools like `pytest` or `unittest`.
- Place test files alongside the modules they test or in a dedicated `tests/` directory.

**Example test file:**
```python
# user_handler.test.py

import unittest
from .user_handler import UserHandler

class TestUserHandler(unittest.TestCase):
    def test_create_user(self):
        handler = UserHandler()
        user = handler.create_user('alice')
        self.assertEqual(user.name, 'alice')

if __name__ == '__main__':
    unittest.main()
```

## Commands
| Command        | Purpose                                   |
|----------------|-------------------------------------------|
| /feature-dev   | Start a new feature development workflow   |
| /run-tests     | Run all test files in the repository       |
| /code-review   | Perform a code review before merging       |
```