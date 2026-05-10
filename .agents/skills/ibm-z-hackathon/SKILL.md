```markdown
# ibm-z-hackathon Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill introduces the core development patterns and conventions used in the `ibm-z-hackathon` TypeScript codebase. It covers file naming, import/export styles, commit message formatting, and testing patterns. While no explicit frameworks or automated workflows are detected, this guide will help you contribute code that aligns with established practices.

## Coding Conventions

### File Naming
- Use **kebab-case** for all file names.
  - Example:  
    ```
    user-profile.ts
    data-service.test.ts
    ```

### Import Style
- Use **alias imports** to reference modules.
  - Example:
    ```typescript
    import { UserService } from '@/services/user-service';
    ```

### Export Style
- Both default and named exports are used.
  - Example (named export):
    ```typescript
    export function fetchData() { ... }
    ```
  - Example (default export):
    ```typescript
    export default class User { ... }
    ```

### Commit Messages
- Use **conventional commits** with the `feat` prefix for new features.
- Keep commit messages concise (average ~59 characters).
  - Example:
    ```
    feat: add user authentication middleware
    ```

## Workflows

### Adding a New Feature
**Trigger:** When you want to introduce a new feature  
**Command:** `/add-feature`

1. Create a new TypeScript file using kebab-case.
2. Implement your feature using alias imports as needed.
3. Export your functions or classes (default or named as appropriate).
4. Write corresponding test files matching the `*.test.*` pattern.
5. Commit your changes using the `feat` prefix in the commit message.
   - Example: `feat: implement user login endpoint`

### Writing Tests
**Trigger:** When you need to test new or existing functionality  
**Command:** `/write-test`

1. Create a test file named with the `*.test.*` pattern (e.g., `user-service.test.ts`).
2. Write your tests using the project's preferred (but currently unknown) testing framework.
3. Ensure tests cover all relevant use cases.

## Testing Patterns

- Test files follow the `*.test.*` naming convention.
  - Example: `api-handler.test.ts`
- The specific testing framework is not detected; follow existing test examples in the codebase.
- Place test files alongside or near the files they test.

## Commands

| Command         | Purpose                                      |
|-----------------|----------------------------------------------|
| /add-feature    | Scaffold and commit a new feature            |
| /write-test     | Create and structure a new test file         |
```
