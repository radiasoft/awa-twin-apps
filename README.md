# awa-twin-apps

Simple demo apps for the AWA beamline: small apps for looking at and working with AWA data and the
AWA twin. Each app is a subpackage of `awa_twin_apps` with its own README and console script; they
share one install.

| App | Command | What it does |
|---|---|---|
| Twin viewer | `awa-twin-viewer` | The AWA twin at a recorded scan's settings, step by step, beside the measurement (in progress: see [awa-twin-viewer-plan.md](awa-twin-viewer-plan.md)) |

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

The twin itself comes from [lume-rftrack](https://github.com/lume-science/lume-rftrack)'s
`examples/awa-zone-twin`, which is not on PyPI.

## Data

The data lives outside this repository. Apps take the data directory as an argument, or read it
from `$AWA_DATA`:

```bash
export AWA_DATA=/path/to/awa-data
awa-twin-viewer
```

## Adding an app

1. Create `awa_twin_apps/<app>/` with an `__init__.py`, the app's modules and a `README.md`.
   Browser assets go in `awa_twin_apps/<app>/static/`; the `*/static/**` pattern in
   `pyproject.toml` packages them.
2. Add its console script under `[project.scripts]` in `pyproject.toml`, named `awa-<app>`.
3. Read the data directory from the command line, falling back to `$AWA_DATA`.
4. Add a row to the table above.

Code that a second app needs from an existing one moves into a shared module of `awa_twin_apps` at
that point, not before.
