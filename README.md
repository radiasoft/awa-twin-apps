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

The data lives outside this repository. Apps take the data directory as an argument.

## Run the twin viewer

```bash
awa-twin-viewer data-dir [--twin-dir DIR] [--port N] [--particles N] [--threads N]
```

Then open <http://127.0.0.1:8070>.

- `data-dir` is the directory of the scan files.
- `--twin-dir` is the twin's `twin/` directory. By default the viewer finds the lume-rftrack
  repository that `lume_rftrack` is imported from (the parent of the package directory) and uses
  its `examples/awa-zone-twin/twin`. That works for an editable install or a checkout, so the
  viewer runs whatever is in that working tree; with a regular install into `site-packages` there
  is no `examples/` directory, so pass `--twin-dir`.
- `--port` defaults to 8070, `--particles` (the macroparticles zone 1 tracks) to 2000, and
  `--threads` is the RF-Track thread count.
- The first step takes about 50 s while the twin builds and tracks; the rest of that dataset is
  then simulated in the background.

## Adding an app

1. Create `awa_twin_apps/<app>/` with an `__init__.py`, the app's modules and a `README.md`.
   Browser assets go in `awa_twin_apps/<app>/static/`; the `*/static/**` pattern in
   `pyproject.toml` packages them.
2. Add its console script under `[project.scripts]` in `pyproject.toml`, named `awa-<app>`.
3. Take the data directory as a command-line argument.
4. Add a row to the table above.

Code that a second app needs from an existing one moves into a shared module of `awa_twin_apps` at
that point, not before.
