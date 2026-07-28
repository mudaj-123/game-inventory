# Repository guidance

## Scope

These instructions apply to the entire repository.

## Development rules

- Use Python 3.12 and add type annotations to Python code.
- Keep API routes, schemas, models, services, authentication, and persistence concerns in separate modules.
- Treat every barcode as a string; never coerce it to an integer or discard leading zeroes.
- Keep the inventory workflow independent of third-party online barcode-recognition services.
- Store source files and CSV files as UTF-8. The catalog importer must eventually accept UTF-8 with BOM too.
- Use Alembic migrations for schema changes; do not rely on `create_all()` for production upgrades.
- Do not commit secrets, local databases, generated exports, caches, virtual environments, or build artifacts.
- Add or update tests with each behavior change. Do not claim a check passed unless it was actually run.

## Commands

- Install development dependencies: `python3.12 -m pip install -e '.[dev]'`
- Run tests after dependencies are installed: `python3.12 -m pytest`
- Run static checks after dependencies are installed: `python3.12 -m ruff check .`
- Start locally: `python3.12 -m uvicorn app.main:app --reload`
