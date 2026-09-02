# Contributing to AutoNect

Thank you for your interest in contributing to AutoNect! We welcome contributions from the community – whether it's a bug report, a new feature, documentation improvements, or even just a question.

Please take a moment to review this guide to make the process smooth and effective.

---

## How to Contribute

### 1. Report Issues

If you find a bug or have a feature request, please open an issue on GitHub.

- **Bug reports** – include steps to reproduce, expected behaviour, and actual behaviour.
- **Feature requests** – describe the problem you're trying to solve and your proposed solution.

### 2. Submit Pull Requests

We use the **GitHub Flow**:

1. Fork the repository.
2. Create a new branch for your feature/fix:  
   `git checkout -b feature/your-feature-name`
3. Make your changes, following our coding standards (see below).
4. Commit with a clear, descriptive message.
5. Push to your fork: `git push origin feature/your-feature-name`
6. Open a Pull Request against the `Chat-UI` branch (not `main`).

---

## Development Setup

1. **Clone the repository**
2. **Run `./setup.sh`** – this sets up the virtual environment, installs dependencies, and configures everything.
3. **Run `./start.sh`** – this starts the server and handles login.

See the [README](README.md) for detailed instructions.

---

## Coding Standards

We aim for clean, maintainable, well‑documented code.

### Python

- **Formatting** – use [Black](https://black.readthedocs.io/) (line length 120).
- **Linting** – use [Ruff](https://beta.ruff.rs/) for linting and import sorting.
- **Type hints** – add type hints for function arguments and return values.
- **Docstrings** – use Google-style docstrings for all public functions and classes.

Run the linter before committing:

```bash
ruff check src/
ruff format src/
mypy src/
```

### JavaScript / CSS (Frontend)

- **Formatting** – use [Prettier](https://prettier.io/) (2 spaces, single quotes).
- **Linting** – use ESLint (we use the standard config).
- **CSS** – use CSS custom properties (variables) and follow the existing naming scheme.

---

## Branching Strategy

- **`main`** – production‑ready code. Only merged from `Chat-UI`.
- **`Chat-UI`** – active development branch for the web interface and backend.
- **`feature/*`** – for new features. These are merged into `Chat-UI`.
- **`hotfix/*`** – for urgent fixes. These are merged into both `Chat-UI` and `main`.

---

## Commit Messages

We follow **Conventional Commits**:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`

**Scope:** optional (e.g., `server`, `ui`, `security`, `deepseek`)

**Examples:**

```
feat(server): add configurable WebSocket output limit

- Read max_output_bytes from settings.json
- Truncate output if exceeded
```

```
fix(ui): correct command card expansion on first render
```

---

## Testing

- **Unit tests** – all tests are in the `tests/` directory.
- **Run tests** – `python -m pytest tests/` (if you install dev dependencies).
- **Security tests** – `python -m src.security.test_guard`

Please add tests for new features and ensure all tests pass before submitting a PR.

---

## Documentation

- Update the **README.md** if you change installation steps, configuration, or features.
- Update **`config/settings.json`** documentation in the README if you add new config keys.
- Add inline docstrings and comments for complex logic.

---

## Code of Conduct

We expect all contributors to be respectful, inclusive, and constructive. Please follow the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

---

## Questions?

Open a GitHub Discussion or issue, and we'll get back to you as soon as possible.

---

**Thank you for helping make AutoNect better!**