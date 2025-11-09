# This is the project's layout

store-scraper/
    ├─ scripts/
    │   ├─ catalog/
    │   │   ├─ adapters/
    │   │   │   ├─ __init__.py
    │   │   │   ├─ base.py          # Adapter interface
    │   │   │   ├─ nintendo.py      # Working Adapter (Nintendo)
    │   │   │   ├─ psn.py           # Working Adapter (PlayStation)
    │   │   │   ├─ steam.py         # Working Adapter (Steam)
    │   │   │   └─ xbox.py          # Working Adapter (Xbox)
    │   │   │
    │   │   ├─ __init__.py
    │   │   ├─ db.py                # Database (SQL) handler
    │   │   ├─ dedupe.py            # optional cross-store clustering (title/year/publisher)
    │   │   ├─ http.py              # resilient HTTP (rate limit, retries, backoff)
    │   │   ├─ ingest.py            # staging/merge helpers (SQLite/Postgres optional)
    │   │   ├─ io_writer.py         # writes !.json and a..z/_.json in your exact format
    │   │   ├─ models.py            # Pydantic models that mirror the JSON schema
    │   │   ├─ normalize.py         # title/price/date/platform normalization
    │   │   └─ runner.py            # Orchestrates adapters, validation, writing
    │   │
    │   └─ crawl.py                 # CLI entrypoint
    │
    ├─ tests/                       # Pytest tests (fixtures later)
    ├─ CRAWL.bat                    # CLI entrypoint
    ├─ INSTALL.bat                  # Dependency installer
    ├─ pyproject.toml               # Project dependency file
    ├─ README.md                    # Project overview
    └─ SCHEMA.md                    # This file, project outline
