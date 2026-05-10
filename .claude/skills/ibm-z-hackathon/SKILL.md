```markdown
# ibm-z-hackathon Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill introduces the core development patterns and conventions used in the `ibm-z-hackathon` Python codebase. It covers file organization, code style, commit message standards, and testing practices to help contributors write consistent, maintainable code.

## Coding Conventions

### File Naming
- Use **snake_case** for all file names.
  - Example: `data_processor.py`, `user_utils.py`

### Import Style
- Use **relative imports** within the package.
  - Example:
    ```python
    from .utils import parse_data
    from ..models import User
    ```

### Export Style
- Use **named exports** (explicitly list exported functions/classes).
  - Example:
    ```python
    __all__ = ['process_data', 'User']
    ```

### Commit Messages
- Follow **conventional commit** format.
- Use the `fix` prefix for bug fixes.
- Keep commit messages concise (average ~62 characters).
  - Example:
    ```
    fix: resolve issue with data parsing in user module
    ```

## Workflows

### Code Contribution
**Trigger:** When adding new features or fixing bugs  
**Command:** `/contribute`

1. Create a new branch for your changes.
2. Write code following the coding conventions above.
3. Add or update relevant tests (see Testing Patterns).
4. Commit changes using the conventional commit format.
5. Open a pull request for review.

### Testing
**Trigger:** Before pushing code or opening a pull request  
**Command:** `/test`

1. Identify test files matching the `*.test.*` pattern.
2. Run all test files manually (no framework detected).
   - Example:
     ```bash
     python my_module.test.py
     ```
3. Ensure all tests pass before submitting your changes.

## Testing Patterns

- Test files use the `*.test.*` naming pattern.
  - Example: `data_processor.test.py`
- No specific testing framework detected; tests may use Python's built-in `unittest` or custom test code.
- Place test files alongside the modules they test or in a dedicated `tests/` directory.

#### Example Test File
```python
# data_processor.test.py

from .data_processor import process_data

def test_process_data():
    input_data = "sample input"
    expected_output = "processed"
    assert process_data(input_data) == expected_output

if __name__ == "__main__":
    test_process_data()
    print("All tests passed.")
```

## Commands

| Command      | Purpose                                  |
|--------------|------------------------------------------|
| /contribute  | Start the code contribution workflow      |
| /test        | Run all tests before submitting changes   |
```
