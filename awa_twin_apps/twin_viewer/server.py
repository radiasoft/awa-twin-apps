"""AWA twin viewer: step through a recorded AWA scan and see the twin's prediction beside the data.

Run `awa-twin-viewer [data directory] [--twin-dir DIR] [--port N]` and open
http://127.0.0.1:8070. The data directory is required. The twin is
`lume-rftrack`'s `examples/awa-zone-twin` as `awa_twin_apps.twin` runs it (zone 1 only, at its
nominal settings but for the solenoid currents).

Each dataset (`scans.datasets()`) is a scan of a YAG1 solenoid; its steps are the scan's setpoints.
For a step, the twin is run with the step's logged solenoid currents, and its beam at YAG1 is
returned beside the camera's image: both are centered on their own beam, at the camera's pixel
size, with their rms sizes. A step is simulated when first asked for and cached, and the rest of
its dataset is simulated in the background.

A step can be run with edits (`/api/step?...&edits={"SolM_current": 260, "Gun_phid": 5}`): values
that replace what the twin runs with. The keys are the twin's knobs (`twin.KNOBS`: the cathode
bunch's charge, the solenoid currents, the Gun's and L1's power and phase, and the kicks of DT1
and DT2) and the
camera's pixel size (`pixel_mm`), which scales the measured image only. An edited solenoid current
replaces the logged one at every step, so editing the scanned solenoid makes every step the same;
a knob not edited is at its nominal value, or the logged one (the solenoid currents and the
charge). Any other key is refused.

:copyright: Copyright (c) 2026 RadiaSoft LLC.  All Rights Reserved.
:license: http://www.apache.org/licenses/LICENSE-2.0.html
"""

from __future__ import annotations

import argparse
import http
import http.server
import json
import math
import mimetypes
import pathlib
import threading
import urllib.parse

import numpy

from awa_twin_apps import scans
from awa_twin_apps import twin as awa_twin

DEFAULT_PORT = 8070
# The twin's variables an edit may set.
EDIT_KNOBS = tuple(awa_twin.KNOBS)
# Simulated steps kept (edited and not); the oldest are dropped past it.
MAX_CACHE = 500
# The largest side, in pixels, of an image sent to the browser; larger images are block-averaged.
MAX_IMAGE_SIDE = 150
# Macroparticles the twin tracks per step.
PARTICLES = 2000
# The camera's pixel size [mm], which an edit may replace.
PIXEL_KNOB = "pixel_mm"
STATIC = pathlib.Path(__file__).resolve().parent / "static"
# The viewer; set by main.
VIEWER = None


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        try:
            if u.path == "/api/datasets":
                return self._json(VIEWER.datasets())
            if u.path == "/api/step":
                q = urllib.parse.parse_qs(u.query)
                return self._json(
                    VIEWER.step(
                        q["scan"][0],
                        int(q["step"][0]),
                        json.loads(q.get("edits", ["{}"])[0]),
                    )
                )
            return self._static(u.path)
        except (KeyError, IndexError, TypeError, ValueError) as e:
            return self._send(
                json.dumps({"error": str(e)}).encode(),
                "application/json",
                status=http.HTTPStatus.BAD_REQUEST,
            )

    def log_message(self, format, *args):  # quieter than the default: errors only
        pass

    def _json(self, value):
        self._send(
            json.dumps(_clean(value), allow_nan=False).encode(), "application/json"
        )

    def _send(self, body, content_type, status=http.HTTPStatus.OK):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _static(self, path):
        f = (STATIC / (path.lstrip("/") or "index.html")).resolve()
        if STATIC not in f.parents or not f.is_file():
            return self._send(
                b"not found", "text/plain", status=http.HTTPStatus.NOT_FOUND
            )
        self._send(f.read_bytes(), mimetypes.guess_type(f.name)[0] or "text/plain")


class Viewer:
    """The data, the twin, and the cache of simulated steps.

    Args:
        data (str): the data directory (`scans.datasets()`)
        twin: what runs the twin: `run(currents)` returns an `awa_twin.Beam`; an
            `awa_twin.Twin`
        background (bool): simulate the rest of a dataset on a thread after a step is asked for
    """

    def __init__(self, data, twin, background=True):
        self.data = pathlib.Path(data)
        self.twin = twin
        self._background_on = background
        self._steps = scans.datasets(self.data)
        self._cache = {}
        self._datasets = {}
        self._lock = threading.Lock()
        # one simulation at a time: requests and the background share the twin
        self._compute = threading.Lock()
        self._wanted = None
        self._worker = None

    def datasets(self) -> dict:
        """The datasets offered, their steps, and the scanned solenoid of each, with the twin's
        elements to draw and its macroparticle count."""
        return {
            "beamline": self.twin.elements(),
            "data": str(self.data),
            "particles": getattr(self.twin, "n_particles", None),
            "datasets": [
                {
                    "scan": n,
                    "title": self._dataset(n)["title"],
                    "steps": len(s),
                    "values": [x.value for x in s],
                    "scanned": self._dataset(n)["scanned"],
                }
                for n, s in self._steps.items()
            ],
        }

    def step(self, scan: str, index: int, edits: dict) -> dict:
        """The twin's beam and the measured image at `scan`'s step `index` with `edits` (see the
        module's docstring; computed if need be), and the rest of the dataset started in the
        background with the same edits.

        Raises:
            KeyError: unknown `scan`
            IndexError: `index` is not a step of `scan`
            TypeError: `edits` is not an object
            ValueError: `edits` has a key that is not editable, or a value that is not a number
        """
        d = self._dataset(scan)
        if not 0 <= index < len(d["steps"]):
            raise IndexError(f"{scan} has {len(d['steps'])} steps")
        e = _edits(edits)
        rv = self._step(scan, index, e)
        self._background(scan, e)
        return rv

    def _background(self, scan: str, edits: tuple) -> None:
        """Simulates `scan`'s steps with `edits`; a worker already running switches to them."""
        if not self._background_on:
            return

        def _done(w):
            with self._lock:
                if w is not None and self._wanted != w:
                    return False
                if self._worker is threading.current_thread():
                    self._worker = None
                return True

        def _run():
            try:
                while True:
                    with self._lock:
                        w = self._wanted
                    for i in range(len(self._dataset(w[0])["steps"])):
                        if self._wanted != w:
                            break
                        self._step(w[0], i, w[1])
                    if _done(w):
                        return
            finally:
                _done(None)

        with self._lock:
            self._wanted = (scan, edits)
            if self._worker is not None:
                return
            self._worker = threading.Thread(target=_run, daemon=True)
        self._worker.start()

    def _dataset(self, scan: str) -> dict:
        """`scan`'s steps with what each logged, and the solenoid it scans."""
        with self._lock:
            if scan in self._datasets:
                return self._datasets[scan]
        steps = [_measured(s) for s in self._steps[scan]]
        e = _scanned(steps)
        res = {
            "steps": steps,
            "scanned": e,
            "title": f"{scan}: scan of {e}",
        }
        with self._lock:
            return self._datasets.setdefault(scan, res)

    def _step(self, scan: str, index: int, edits: tuple) -> dict:
        key = (scan, index, edits)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        d = self._dataset(scan)
        with self._compute:
            with self._lock:
                if key in self._cache:
                    return self._cache[key]
            rv = _result(d, index, dict(edits), self.twin)
            rv.update(scan=scan, step=index, edits=dict(edits))
            with self._lock:
                if len(self._cache) >= MAX_CACHE:
                    del self._cache[next(iter(self._cache))]
                self._cache[key] = rv
        return rv


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("data", type=pathlib.Path, help="the directory of the scan files")
    p.add_argument("--particles", type=int, default=PARTICLES)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--threads", type=int, default=None, help="RF-Track threads")
    p.add_argument(
        "--twin-dir",
        type=pathlib.Path,
        help="the AWA twin's twin/ directory (default: that of the installed lume-rftrack's source tree)",
    )
    a = p.parse_args()
    try:
        awa_twin.twin_dir(a.twin_dir)
    except ValueError as e:
        p.error(str(e))
    print("building the twin (tens of seconds)...", flush=True)
    global VIEWER
    VIEWER = Viewer(a.data, awa_twin.Twin(a.twin_dir, a.particles, a.threads))
    print(f"AWA twin viewer: http://127.0.0.1:{a.port} (data {a.data})", flush=True)
    http.server.ThreadingHTTPServer(("0.0.0.0", a.port), Handler).serve_forever()


def _charge(measured: dict) -> float | None:
    """The beam charge [pC] a step logged (the mean of its shots), or None."""
    q = measured["logged"].get(awa_twin.CHARGE_PV)
    return None if q is None else round(q * awa_twin.CHARGE_PC_PER_UNIT, 6)


def _clean(value):
    """`value` with NaN and infinite numbers as None and numpy values as Python ones."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, numpy.ndarray):
        return _clean(value.tolist())
    if isinstance(value, (numpy.floating, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, numpy.integer):
        return int(value)
    return value


def _downsample(image: numpy.ndarray, k: int) -> numpy.ndarray:
    """`image` block-averaged by `k` in each direction."""
    r, c = (image.shape[0] // k) * k, (image.shape[1] // k) * k
    return image[:r, :c].reshape(r // k, k, c // k, k).mean(axis=(1, 3))


def _edits(edits: dict) -> tuple:
    """`edits` checked (known keys, finite numbers), as a sorted tuple to key the cache."""
    if not isinstance(edits, dict):
        raise TypeError("edits must be an object")
    for k, v in edits.items():
        if k not in EDIT_KNOBS and k != PIXEL_KNOB:
            raise ValueError(f"edits: {k!r} is not editable")
        if (
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
        ):
            raise ValueError(f"edits: {k!r} must be a finite number")
    if edits.get(PIXEL_KNOB, 1) <= 0:
        raise ValueError(f"edits: {PIXEL_KNOB!r} must be positive")
    for k, v in edits.items():
        if k.endswith("_P_actual") and v < 0:
            raise ValueError(f"edits: {k!r} must not be negative")
    if edits.get(awa_twin.CHARGE_KNOB, 1) <= 0:
        raise ValueError(f"edits: {awa_twin.CHARGE_KNOB!r} must be positive")
    return tuple(sorted((k, float(v)) for k, v in edits.items()))


def _extent(shape: tuple, pixel_mm: float, stats: dict | None) -> list:
    """`[x0, x1, y0, y1]` [mm] of an image of `shape` from the beam's centroid: the image's center,
    or the `stats` centroid's offset from it."""
    cx = 0.0 if stats is None else stats["centroid_x_mm"]
    cy = 0.0 if stats is None else stats["centroid_y_mm"]
    w, h = shape[1] * pixel_mm / 2.0, shape[0] * pixel_mm / 2.0
    return [-w - cx, w - cx, -h - cy, h - cy]


def _measured(step: scans.Step) -> dict:
    """What `step` logged and the camera saw, without the raw stack: the setpoint, the logged
    readbacks' means, the twin's solenoid currents they give, the processed image and the
    camera's pixel size."""
    r = scans.read(step)
    if "resolution" not in r.metadata:
        raise ValueError(f"{step.path.name} has no camera resolution")
    return {
        "value": step.value,
        "logged": {k: float(v.mean()) for k, v in r.readbacks.items()},
        "currents": awa_twin.settings(r),
        "image": r.processed.astype(numpy.float32),
        "pixel_mm": float(r.metadata["resolution"]),
        "shots": int(r.images.shape[0]),
    }


def _normalized(image: numpy.ndarray) -> numpy.ndarray:
    """`image` to a peak of 1, rounded for the browser."""
    p = image.max()
    return numpy.round(image / p if p > 0 else image, 3)


def _numbers(measured: dict, modeled: dict, charge_pc: float | None) -> list:
    """The compared quantities: `{name, unit, measured, twin}`. `charge_pc` is the logged charge
    [pC], None if the scan has none."""
    return [
        {
            "name": "rms x",
            "unit": "mm",
            "measured": measured["rms_x_mm"],
            "twin": modeled["rms_x_mm"],
        },
        {
            "name": "rms y",
            "unit": "mm",
            "measured": measured["rms_y_mm"],
            "twin": modeled["rms_y_mm"],
        },
        {
            "name": "rms x / y",
            "unit": "",
            "measured": measured["rms_x_mm"] / measured["rms_y_mm"],
            "twin": modeled["rms_x_mm"] / modeled["rms_y_mm"],
        },
        {
            "name": "charge",
            "unit": "pC",
            "measured": charge_pc,
            "twin": modeled["charge_pc"],
        },
    ]


def _profile(
    image: numpy.ndarray, axis: int, pixel_mm: float, center_mm: float
) -> dict:
    """The sum of `image` along `axis` (0 for the x profile, 1 for y) to a peak of 1, with its
    positions [mm] from `center_mm`."""
    p = image.sum(axis=axis)
    return {
        "mm": (numpy.arange(p.size) - (p.size - 1) / 2.0) * pixel_mm - center_mm,
        "value": p / p.max() if p.max() > 0 else p,
    }


def _result(d: dict, index: int, edits: dict, twin) -> dict:
    """The step's measured image and numbers, the twin's with the step's currents and `edits`, and
    the settings table."""
    m = d["steps"][index]
    pixel = edits.get(PIXEL_KNOB, m["pixel_mm"])
    beam = twin.run(
        {**m["currents"], **{k: v for k, v in edits.items() if k in EDIT_KNOBS}}
    )
    image = m["image"]
    measured = awa_twin.image_stats(image, pixel)
    modeled = awa_twin.particle_stats(beam)
    k = max(1, math.ceil(max(image.shape) / MAX_IMAGE_SIDE))
    shown = _downsample(image, k)
    # the twin's, centered on its centroid like the measured window is on its beam
    modeled_image = awa_twin.render(
        beam,
        pixel * k,
        shown.shape,
        (modeled["centroid_x_mm"], modeled["centroid_y_mm"]),
    )
    return {
        "value": m["value"],
        "scanned": d["scanned"],
        "shots": m["shots"],
        "display_pixel_mm": pixel * k,
        "measured": {
            **measured,
            "image": _normalized(shown),
            "peak": float(shown.max()),
            "extent_mm": _extent(shown.shape, pixel * k, measured),
        },
        "twin": {
            **modeled,
            "image": _normalized(modeled_image),
            "peak": float(modeled_image.max()),
            "extent_mm": _extent(modeled_image.shape, pixel * k, None),
        },
        "profiles": {
            "x": {
                "measured": _profile(shown, 0, pixel * k, measured["centroid_x_mm"]),
                "twin": _profile(modeled_image, 0, pixel * k, 0.0),
            },
            "y": {
                "measured": _profile(shown, 1, pixel * k, measured["centroid_y_mm"]),
                "twin": _profile(modeled_image, 1, pixel * k, 0.0),
            },
        },
        "numbers": _numbers(measured, modeled, _charge(m)),
        "settings": _settings(d, m, edits, pixel, twin.defaults()),
    }


def _scanned(steps: list) -> str:
    """The twin's solenoid that a dataset scans: the one whose logged readback follows the
    setpoints."""
    return min(
        awa_twin.SOLENOIDS.items(),
        key=lambda kv: sum(
            abs(s["logged"].get(kv[0], math.inf) - s["value"])
            / max(abs(s["value"]), 1.0)
            for s in steps
        ),
    )[1]


def _settings(d: dict, m: dict, edits: dict, pixel: float, defaults: dict) -> list:
    """The settings table: `{name, key, pv, unit, logged, twin, edited, editable, scanned, note}`
    for each of the twin's knobs (`twin.KNOBS`), the other logged PVs the twin does not use, and
    the camera's pixel size. `key` is the name of the edit, None if there is none; `twin` is what
    the twin ran with: the edit, else the logged value, else the nominal one."""
    pvs = {f"{e}_current": pv for pv, e in awa_twin.SOLENOIDS.items()}
    pvs[awa_twin.CHARGE_KNOB] = awa_twin.CHARGE_PV
    scanned = f"{d['scanned']}_current"
    rows = [
        {
            "name": label,
            "key": k,
            "pv": pvs.get(k, k),
            "unit": unit,
            "logged": m["currents"].get(k),
            "twin": edits.get(k, m["currents"].get(k, defaults[k])),
            "edited": k in edits,
            "editable": True,
            "scanned": k == scanned,
            "note": "scanned" if k == scanned else note,
        }
        for k, (label, unit, note) in awa_twin.KNOBS.items()
    ]
    rows += [
        {
            "name": k,
            "key": None,
            "pv": k,
            "unit": "",
            "logged": v,
            "twin": None,
            "edited": False,
            "editable": False,
            "scanned": False,
            "note": "",
        }
        for k, v in sorted(m["logged"].items())
        if k not in awa_twin.SOLENOIDS and k != awa_twin.CHARGE_PV
    ]
    rows.append(
        {
            "name": "pixel size",
            "key": PIXEL_KNOB,
            "pv": PIXEL_KNOB,
            "unit": "mm",
            "logged": m["pixel_mm"],
            "twin": pixel,
            "edited": PIXEL_KNOB in edits,
            "editable": True,
            "scanned": False,
            "note": "scales the measured image only",
        }
    )
    return rows
