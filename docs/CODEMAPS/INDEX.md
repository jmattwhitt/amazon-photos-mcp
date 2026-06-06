# Codebase Overview — CODEMAPS Index

**Last Updated:** 2026-06-06
**Root:** `.`
**Total Files Scanned:** 70

## Areas

| Area | Size | Key Directories |
|------|------|-----------------|
| [Frontend](./frontend.md) | 0 files | — |
| [Backend/API](./backend.md) | 0 files | — |
| [Database](./database.md) | 0 files | — |
| [Integrations](./integrations.md) | 0 files | — |
| [Workers](./workers.md) | 0 files | — |

## Repository Structure

```
amazon-photos-mcp/
├── .claude
│   └── settings.local.json
├── .github
│   ├── workflows
│   │   └── ci.yml
│   └── dependabot.yml
├── .mypy_cache
│   ├── 3.10
│   │   ├── cache.0.db
│   │   ├── cache.1.db
│   │   ├── cache.10.db
│   │   ├── cache.11.db
│   │   ├── cache.12.db
│   │   ├── cache.13.db
│   │   ├── cache.14.db
│   │   ├── cache.15.db
│   │   ├── cache.2.db
│   │   ├── cache.3.db
│   │   ├── cache.4.db
│   │   ├── cache.5.db
│   │   ├── cache.6.db
│   │   ├── cache.7.db
│   │   ├── cache.8.db
│   │   └── cache.9.db
│   ├── .gitignore
│   └── CACHEDIR.TAG
├── .omc
│   ├── plans
│   │   └── 2026-06-05-review-recommendations.md
│   ├── state
│   │   ├── checkpoints
│   │   ├── sessions
│   │   ├── agent-replay-1c3c6eb4-5c82-4630-baca-37d38850f65c.jsonl
│   │   ├── agent-replay-97bc36fa-4e2f-4363-ab83-c73942795565.jsonl
│   │   ├── hud-stdin-cache.json
│   │   ├── last-tool-error.json
│   │   ├── mission-state.json
│   │   └── subagent-tracking.json
│   └── project-memory.json
├── .pytest_cache
│   ├── v
│   │   └── cache
│   ├── .gitignore
│   ├── CACHEDIR.TAG
│   └── README.md
├── .ruff_cache
│   ├── 0.15.5
│   │   ├── 13003855125424319772
│   │   ├── 284484741013109352
│   │   ├── 3610101793495698859
│   │   ├── 4928881372578331262
│   │   ├── 5260705796707179509
│   │   └── 8191408636848791369
│   ├── .gitignore
│   └── CACHEDIR.TAG
├── .venv
│   ├── Lib
│   │   └── site-packages
│   ├── Scripts
│   │   ├── activate
│   │   ├── activate.bat
│   │   ├── activate.csh
│   │   ├── activate.fish
│   │   ├── activate.nu
│   │   ├── activate.ps1
│   │   ├── activate_this.py
│   │   ├── amazon-photos-mcp.exe
│   │   ├── coverage-3.12.exe
│   │   ├── coverage.exe
│   │   ├── coverage3.exe
│   │   ├── cyclopts.exe
│   │   ├── deactivate.bat
│   │   ├── dmypy.exe
│   │   ├── docutils.exe
│   │   ├── dotenv.exe
│   │   ├── email_validator.exe
│   │   ├── f2py.exe
│   │   ├── fastmcp.exe
│   │   ├── get-amazon-cookies-easy.exe
│   │   ├── get-amazon-cookies.exe
│   │   ├── httpx.exe
│   │   ├── jsonschema.exe
│   │   ├── keyring.exe
│   │   ├── markdown-it.exe
│   │   ├── mcp.exe
│   │   ├── mypy.exe
│   │   ├── mypyc.exe
│   │   ├── numpy-config.exe
│   │   ├── py.test.exe
│   │   ├── pydoc.bat
│   │   ├── pygmentize.exe
│   │   ├── pytest.exe
│   │   ├── python.exe
│   │   ├── pythonw.exe
│   │   ├── pywin32_postinstall.exe
│   │   ├── pywin32_postinstall.py
│   │   ├── pywin32_testall.exe
│   │   ├── pywin32_testall.py
│   │   ├── rst2html.exe
│   │   ├── rst2html4.exe
│   │   ├── rst2html5.exe
│   │   ├── rst2latex.exe
│   │   ├── rst2man.exe
│   │   ├── rst2odt.exe
│   │   ├── rst2pseudoxml.exe
│   │   ├── rst2s5.exe
│   │   ├── rst2xetex.exe
│   │   ├── rst2xml.exe
│   │   ├── stubgen.exe
│   │   ├── stubtest.exe
│   │   ├── tqdm.exe
│   │   ├── uvicorn.exe
│   │   ├── watchfiles.exe
│   │   └── websockets.exe
│   ├── .gitignore
│   ├── .lock
│   ├── CACHEDIR.TAG
│   └── pyvenv.cfg
├── .worktrees
├── amazon_photos_mcp
│   ├── __pycache__
│   │   ├── __init__.cpython-311.pyc
│   │   └── __init__.cpython-312.pyc
│   ├── crypto.py
│   ├── phash.py
│   ├── rate_limiter.py
│   └── __init__.py
├── docs
│   ├── CODEMAPS
│   └── superpowers
│       └── plans
├── scripts
│   ├── __pycache__
│   │   ├── get_cookies.cpython-311.pyc
│   │   └── __init__.cpython-311.pyc
│   ├── get_cookies.ps1
│   ├── get_cookies.py
│   ├── get_cookies_easy.py
│   └── __init__.py
├── tests
│   ├── smoke
│   │   ├── conftest.py
│   │   ├── test_inspector.py
│   │   └── __init__.py
│   ├── __pycache__
│   │   ├── conftest.cpython-311-pytest-9.0.3.pyc
│   │   ├── conftest.cpython-312-pytest-9.0.3.pyc
│   │   ├── test_tools.cpython-311-pytest-9.0.3.pyc
│   │   ├── test_tools.cpython-312-pytest-9.0.3.pyc
│   │   ├── test_utils.cpython-311-pytest-9.0.3.pyc
│   │   └── test_utils.cpython-312-pytest-9.0.3.pyc
│   ├── conftest.py
│   ├── test_integration.py
│   ├── test_tools.py
│   └── test_utils.py
├── .coverage
├── .gitignore
├── LICENSE
├── log.log
├── pyproject.toml
├── README.md
└── uv.lock
```

## How to Regenerate

```bash
npx tsx scripts/codemaps/generate.ts        # Regenerate codemaps
npx madge --image graph.svg src/            # Dependency graph (requires graphviz)
npx jsdoc2md src/**/*.ts                    # Extract JSDoc
```

## Related Documentation

- [Frontend](./frontend.md) — UI components, pages, hooks
- [Backend/API](./backend.md) — API routes, controllers, middleware
- [Database](./database.md) — Models, schemas, migrations
- [Integrations](./integrations.md) — External services & adapters
- [Workers](./workers.md) — Background jobs, queues, cron tasks
