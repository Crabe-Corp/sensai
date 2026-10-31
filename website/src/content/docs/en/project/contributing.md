---
title: "Contributor Guide"
description: "Code conventions, team contributors, testing standards and PR lifecycle."
editUrl: "https://github.com/Crabe-Corp/sensai/edit/dev/docs/en/contributing.md"
sidebar:
  order: 1
---
Welcome to the **SensAI** team! This document details engineering standards, code styles, and the contribution lifecycle.

---

## Project Team

| Contributor | GitHub Profile | Role & Responsibilities |
| :--- | :--- | :--- |
| **Lucas** | [@LucasLhomme](https://github.com/LucasLhomme) | Front & Backend, UX |
| **Jawed** | [@jawedlahrouri](https://github.com/jawedlahrouri) | Core & tools |
| **Grégoire** | [@graigware](https://github.com/graigware) | Security, memory management & data |
| **Joseph** | [@jobirck](https://github.com/jobirck) | Knowledge & evaluation |

---

## Code Standards & Architecture

### 1. Python (Backend & Core Engine)

- **Strict Typing:** Always use Python type hints (`typing.Optional`, `list[str]`, `dict[str, Any]`, etc.).
- **Async Hygiene:** Synchronous, blocking operations (disk I/O, synchronous SQL queries, HTTP calls) executed within FastAPI routes must be dispatched via `await asyncio.to_thread(...)` to avoid stalling the main event loop.
- **Error Handling:** Avoid bare exceptions; log errors using Python's `logging` module.
- **Linters & Formatters:** Adhere to PEP 8 / Flake8 / Ruff standards.

### 2. Frontend (React 19 & shadcn/ui)

- **Art Direction:** Strictly follow Dark Obsidian design principles inspired by Linear.app and Dub.co.
- **Visual Boundaries:** No multi-color gradients, no garish neon colors, no excessive glassmorphism, no emojis in buttons or headers.
- **Accessibility:** Leverage accessible primitives from `@base-ui/react` and shadcn/ui.
- **Linter:** Run `npm run lint` with **Oxlint** before each commit.

### 3. Modern C++ (Native Extensions & SDK)

When contributing C++ modules:
- **Strict RAII:** No raw `new` or `delete`. Always use `std::unique_ptr` or `std::shared_ptr`.
- **Rule of 0:** Prefer standard containers for automated resource lifecycle management.
- **Encapsulation & Const-Correctness:** Private fields, `const` member functions, explicit use of `override` and `final`.
- **No C Macros:** Favor `constexpr` and typed constants.

---

## Testing & Quality Assurance

Ensure all test suites pass prior to opening a Pull Request:

```bash
# Python backend tests
pytest -v

# Frontend linting and typecheck
cd frontend
npm run lint
npm run build
```

---

## Pull Request Lifecycle (PR Checklist)

1. **Branching:** Create an explicit branch off `dev` (e.g. `feature/name` or `fix/name`).
2. **Atomic Commits:** Use conventional commits (`feat: ...`, `fix: ...`, `docs: ...`).
3. **Documentation:** Document any user-facing change or new tool under the `docs/` folder.
4. **Clean CI:** Verify all GitHub Actions jobs pass.
