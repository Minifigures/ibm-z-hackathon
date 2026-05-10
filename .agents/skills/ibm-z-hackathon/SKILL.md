```markdown
# ibm-z-hackathon Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill teaches you the core development patterns and conventions used in the `ibm-z-hackathon` TypeScript codebase. You'll learn how to structure files, write imports and exports, follow commit message conventions, and understand the testing approach. This guide also provides suggested commands for common workflows.

## Coding Conventions

### File Naming
- Use **camelCase** for file names.
  - Example: `userProfile.ts`, `dataFetcher.ts`

### Import Style
- Use **alias imports** to reference modules.
  - Example:
    ```typescript
    import { fetchData as getData } from './dataFetcher';
    ```

### Export Style
- Both **named** and **default exports** are used.
  - Named export:
    ```typescript
    export function processUser() { ... }
    ```
  - Default export:
    ```typescript
    export default UserProfile;
    ```

### Commit Messages
- Follow the **Conventional Commits** specification.
- Use the `feat` prefix for new features.
  - Example:  
    ```
    feat: add user authentication to login flow
    ```
- Commit messages are descriptive (average length: 86 characters).

## Workflows

### Feature Development
**Trigger:** When implementing a new feature  
**Command:** `/feature-dev`

1. Create a new branch for your feature.
2. Write code following the coding conventions.
3. Use camelCase for new file names.
4. Use alias imports where appropriate.
5. Export modules using named or default exports as needed.
6. Write or update tests in files matching `*.test.*`.
7. Commit changes using the `feat` prefix and a descriptive message.
8. Open a pull request for review.

### Testing Code
**Trigger:** When validating code changes  
**Command:** `/run-tests`

1. Identify or create test files matching the pattern `*.test.*`.
2. Run the test suite using the project's test runner (framework is unspecified; check project docs or scripts).
3. Ensure all tests pass before merging changes.

## Testing Patterns

- Test files are named with the pattern `*.test.*` (e.g., `userProfile.test.ts`).
- The specific testing framework is not detected; refer to project documentation or scripts for details.
- Place tests alongside the code they test or in a dedicated `tests` directory.

## Commands
| Command        | Purpose                                      |
|----------------|----------------------------------------------|
| /feature-dev   | Start a new feature development workflow      |
| /run-tests     | Run the test suite for the codebase          |
```
