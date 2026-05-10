```markdown
# ibm-z-hackathon Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill documents the core development patterns and conventions found in the `ibm-z-hackathon` repository. The codebase is written in TypeScript and does not use a specific framework. It emphasizes consistent file naming, import/export styles, and commit message conventions. This guide will help you contribute code that aligns with the project's established patterns.

## Coding Conventions

### File Naming
- **Style:** kebab-case
- **Example:**  
  - `user-profile.ts`
  - `data-service.ts`

### Import Style
- **Style:** Alias imports are preferred.
- **Example:**
  ```typescript
  import { UserService } from '@/services/user-service';
  ```

### Export Style
- **Style:** Mixed (both named and default exports are used)
- **Example:**
  ```typescript
  // Named export
  export function calculateTotal() { ... }

  // Default export
  export default class UserProfile { ... }
  ```

### Commit Messages
- **Type:** Conventional Commits
- **Prefix:** `feat`
- **Average Length:** ~64 characters
- **Example:**
  ```
  feat: add user authentication middleware for login route
  ```

## Workflows

### Code Contribution
**Trigger:** When adding new features or making changes to the codebase  
**Command:** `/contribute`

1. Create a new branch using a descriptive name (use kebab-case).
2. Write your code following the file naming, import, and export conventions.
3. Write or update tests in files matching the `*.test.*` pattern.
4. Commit your changes using the conventional commit format (e.g., `feat: ...`).
5. Open a pull request for review.

### Testing
**Trigger:** When you need to verify code correctness  
**Command:** `/test`

1. Identify or create test files using the `*.test.*` pattern.
2. Run the test suite using the project's preferred test runner (framework is unknown; check project scripts or documentation).
3. Ensure all tests pass before submitting your code.

## Testing Patterns

- **Test File Pattern:** Files should be named with the pattern `*.test.*` (e.g., `user-profile.test.ts`).
- **Framework:** Not explicitly detected; refer to project documentation or package.json for details.
- **Example Test File:**
  ```typescript
  // user-profile.test.ts
  import { getUserProfile } from '@/services/user-profile';

  test('should return user profile data', () => {
    const result = getUserProfile('user123');
    expect(result).toHaveProperty('name');
  });
  ```

## Commands
| Command      | Purpose                                        |
|--------------|------------------------------------------------|
| /contribute  | Start the code contribution workflow           |
| /test        | Run the test suite and verify code correctness |
```
