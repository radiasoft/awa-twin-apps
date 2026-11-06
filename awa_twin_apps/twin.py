"""Run the AWA twin at a scan step's logged settings, and compare its YAG1 beam with the image.

The twin is `lume-rftrack`'s `examples/awa-zone-twin` (zone 1 only: the gun to YAG4). It is not an
installed package, so `twin_dir()` finds its `twin/` directory and `Twin` imports `zone_model`
from there. The scans log the solenoid currents (`SOLENOIDS`); a step is run by setting those on
the twin, which tracks zone 1, and taking the bunch at the screen (`SCREEN`).

The twin's beam is its macroparticles' (x, y) at the screen [mm]; `render()` histograms them as
a camera image at the camera's pixel size, and `particle_stats()` and `image_stats()` give the
same quantities of the twin and of the measured image to compare.

The measured image to compare is the scan file's `processed_image` (see `scans.StepData`): the
beam alone, centered in its window, at the camera's pixel size. Its centroid is therefore the
window's center, not the beam's position on the screen, so only sizes and shapes are compared;
render the twin centered on its own centroid (`render(..., center_mm=)`).

Assumed, not verified: the image's columns are x and its rows y, with the same signs as the
twin's x and y.

:copyright: Copyright (c) 2026 RadiaSoft LLC.  All Rights Reserved.
:license: http://www.apache.org/licenses/LICENSE-2.0.html
"""

from __future__ import annotations

import collections
import dataclasses
import pathlib
import sys
import threading

import numpy

# The cathode bunch's charge [pC], a knob that is not a variable of the twin: `Twin` builds the
# cathode bunch again at the charge asked for.
CHARGE_KNOB = "charge_pC"
# The logged PV of the beam charge, and its pC per logged unit: the AWA scans log the integrating
# current transformer in coulombs (it matches the `target_charge` of 5e-10 the camera records).
CHARGE_PC_PER_UNIT = 1e12
CHARGE_PV = "AWAVXI11ICT:Ch1"
# The knobs a viewer may set, in beam order: name -> (label, unit, note). They are the twin's
# variables and `CHARGE_KNOB`. Only the elements upstream of the screen (`SCREEN`, z = 2.9 m) can
# change its beam. A cavity's `P_actual` is relative (1 is the power of its field map) and its
# `phid` is from the autophased phase.
KNOBS = {
    CHARGE_KNOB: ("Charge", "pC", "of the cathode bunch; the logged ICT's"),
    "SolBF_current": ("SolBF current", "A", ""),
    "Gun_P_actual": ("Gun power", "W", "relative: 1 is the field map's power"),
    "Gun_phid": ("Gun phase", "deg", "from the autophased phase"),
    "SolM_current": ("SolM current", "A", ""),
    "L1_P_actual": ("L1 power", "W", "relative: 1 is the field map's power"),
    "L1_phid": ("L1 phase", "deg", "from the autophased phase"),
    "DT1_strength_x": ("DT1 kick x", "T*mm", ""),
    "DT1_strength_y": ("DT1 kick y", "T*mm", ""),
    "SolL1_current": ("SolL1 current", "A", ""),
    "DT2_strength_x": ("DT2 kick x", "T*mm", ""),
    "DT2_strength_y": ("DT2 kick y", "T*mm", ""),
    "SolL2_current": ("SolL2 current", "A", "downstream of YAG1: no effect there"),
}
# Simulated steps kept; the oldest are dropped past it.
MAX_CACHE = 500
# The twin's screen the camera looks at.
SCREEN = "YAG1"
# The logged solenoid readback [A] -> the twin's solenoid (its `<name>_current` variable). DS1 is
# the bucking-focusing solenoid, DS3 the matching solenoid and DS5 the second linac solenoid,
# by the twin's naming of the AWA power supplies.
SOLENOIDS = {
    "AWA:Drive:DS1:RB": "SolBF",
    "AWA:Drive:DS3:RB": "SolM",
    "AWA:Drive:DS5:RB": "SolL2",
}
# `image_stats()` measures the beam inside this many rms sizes of its centroid.
WINDOW = 4.0
# The fraction of the peak above which pixels give `image_stats()` its first guess of the beam.
_FIRST_GUESS = 0.05
# The times `image_stats()` refines the beam's window.
_ITERATIONS = 3
# The synoptic's kind of each RF-Track class the twin draws; others (drifts, ...) are not drawn.
_KINDS = {
    "Corrector": "corrector",
    "Quadrupole": "quadrupole",
    "RF_FieldMap_1d": "cavity",
    "Screen": "screen",
    "Static_Magnetic_FieldMap_1d": "solenoid",
}
# The twin's directory under a lume-rftrack source tree.
_TWIN_SUBDIR = pathlib.Path("examples") / "awa-zone-twin" / "twin"
# The drawn width [m] of a cavity, solenoid or screen (a field map's length includes its fringe
# field); every other kind is drawn at the element's length.
_WIDTHS = {"cavity": 0.3, "screen": 0.05, "solenoid": 0.15}


@dataclasses.dataclass(frozen=True)
class Beam:
    """The twin's beam at the screen: the macroparticles' positions [mm] and total charge [pC]."""

    x_mm: numpy.ndarray
    y_mm: numpy.ndarray
    charge_pc: float


class Twin:
    """AWA zone 1, built once and run step by step, one run at a time.

    Args:
        path (str): the twin's `twin/` directory (see `twin_dir()`)
        n_particles (int): macroparticles the twin tracks
        threads (int): RF-Track's threads, at most its maximum; default the twin's
    """

    def __init__(self, path=None, n_particles=2000, threads=None):
        self.n_particles = n_particles
        self._lock = threading.Lock()
        self._cache = collections.OrderedDict()
        sys.path.insert(0, str(twin_dir(path)))
        import RF_Track as rft
        import zone_model

        rft.cvar.number_of_threads = min(
            zone_model.DEFAULT_THREADS if threads is None else threads,
            rft.max_number_of_threads,
        )
        self._zone_model = zone_model
        self._model = zone_model.zone1_model(n_particles)
        # the cathode bunch's source, to build it again at another charge
        self._source = zone_model._load_generated_module("zone1_source")
        self._source.BUNCH.np = n_particles
        self._charge_pc = self._source.BUNCH.q_total_nc * 1000.0
        # the nominal value of each knob, which every run starts from
        self._defaults = {
            k: self._charge_pc
            if k == CHARGE_KNOB
            else float(self._model.supported_variables[k].default_value)
            for k in KNOBS
        }
        self._screen = zone_model.screen_names(self._model.simulator.beamline).index(
            SCREEN
        )

    def defaults(self) -> dict:
        """The nominal value of each of `KNOBS`, as built: {variable: value}."""
        return dict(self._defaults)

    def elements(self) -> list:
        """The drawn elements of the twin's beamline (see `elements()`)."""
        return elements(self._model.simulator.beamline)

    def run(self, values: dict) -> Beam:
        """The beam at the screen with the twin's variables at `values` ({variable: value}, of
        `KNOBS`, e.g. from `settings()`) and every other knob at its nominal value, so a run does
        not depend on the ones before it. Cached by values.

        Raises:
            KeyError: a variable that is not in `KNOBS`
        """
        full = {**self._defaults, **{k: float(v) for k, v in values.items()}}
        unknown = set(values) - set(KNOBS)
        if unknown:
            raise KeyError(f"not a knob: {sorted(unknown)}")
        k = tuple(sorted((n, round(v, 6)) for n, v in full.items()))
        with self._lock:
            if k in self._cache:
                self._cache.move_to_end(k)
                return self._cache[k]
            self._set_charge(full[CHARGE_KNOB])
            self._model.set({k: v for k, v in full.items() if k != CHARGE_KNOB})
            res = self._beam()
            self._cache[k] = res
            while len(self._cache) > MAX_CACHE:
                self._cache.popitem(last=False)
            return res

    def _beam(self) -> Beam:
        import RF_Track as rft

        b = self._model.simulator.beamline.get_bunch_at_screens()[self._screen]
        xy = b.get_phase_space("%X %Y" if isinstance(b, rft.Bunch6dT) else "%x %y")
        return Beam(
            x_mm=numpy.array(xy[:, 0]),
            y_mm=numpy.array(xy[:, 1]),
            charge_pc=abs(b.get_total_charge()) / rft.nC * 1000.0,
        )

    def _set_charge(self, charge_pc: float) -> None:
        """Make the twin's initial bunch the cathode bunch of `charge_pc`, the same particles with
        another charge (the same seed), unless it has it already. The twin tracks it next."""
        if abs(charge_pc - self._charge_pc) <= 1e-9 * max(charge_pc, 1.0):
            return
        import RF_Track as rft

        self._source.BUNCH.q_total_nc = charge_pc / 1000.0
        rft.rng_set_seed(self._source.BUNCH.random_seed)
        self._model.simulator.initial_bunch = self._source.build_bunch()
        self._charge_pc = charge_pc


def elements(beamline) -> list:
    """The elements of `beamline` (a Volume) to draw, in order of position: `{name, kind, z_m,
    width_m}`, the kind being `corrector`, `quadrupole`, `cavity`, `screen` or `solenoid`. An
    element is at its absolute z, its Volume placement; unnamed elements and drifts are left out."""
    res = []
    for i in range(beamline.size()):
        e = beamline[i]
        k = _KINDS.get(type(e).__name__)
        if k is None or not e.get_name():
            continue
        res.append(
            {
                "name": e.get_name(),
                "kind": k,
                "z_m": float(e.get_offsets().get_origin().flatten()[2]) / 1000.0,
                "width_m": _WIDTHS.get(k) or float(e.get_length()),
            }
        )
    return sorted(res, key=lambda x: x["z_m"])


def image_stats(image: numpy.ndarray, pixel_mm: float, window=WINDOW) -> dict:
    """The centroid and rms size [mm] of the beam in `image`, a (rows, columns) camera image, and
    its counts.

    The moments are taken inside `window` rms sizes of the centroid, less a baseline that is the
    median of the pixels outside it, so the noise floor and any offset stay out of the sizes
    without cutting the beam's tails. The window starts from the pixels above 5% of the peak and is
    refined three times. The centroid is from the image center (x to the columns, y to the rows);
    `counts` are the baseline-subtracted counts in the window.
    """
    im = numpy.asarray(image, dtype=numpy.float64)
    first = numpy.clip(im - numpy.median(im), 0.0, None)
    c = _moments(numpy.where(first >= _FIRST_GUESS * first.max(), first, 0.0), 0, 0)
    for _ in range(_ITERATIONS):
        x0, x1 = _bounds(c["x"], c["sx"], window, im.shape[1])
        y0, y1 = _bounds(c["y"], c["sy"], window, im.shape[0])
        outside = numpy.ones(im.shape, dtype=bool)
        outside[y0:y1, x0:x1] = False
        baseline = numpy.median(im[outside]) if outside.any() else 0.0
        w = im[y0:y1, x0:x1] - baseline
        c = _moments(w, x0, y0)
    return {
        "counts": c["total"],
        "centroid_x_mm": (c["x"] - (im.shape[1] - 1) / 2.0) * pixel_mm,
        "centroid_y_mm": (c["y"] - (im.shape[0] - 1) / 2.0) * pixel_mm,
        "rms_x_mm": c["sx"] * pixel_mm,
        "rms_y_mm": c["sy"] * pixel_mm,
    }


def particle_stats(beam: Beam) -> dict:
    """The centroid and rms size [mm] of `beam`, with its charge [pC] and macroparticle count,
    as `image_stats()` names them (`counts` is the macroparticle count)."""
    return {
        "counts": float(beam.x_mm.size),
        "centroid_x_mm": float(beam.x_mm.mean()),
        "centroid_y_mm": float(beam.y_mm.mean()),
        "rms_x_mm": float(beam.x_mm.std()),
        "rms_y_mm": float(beam.y_mm.std()),
        "charge_pc": beam.charge_pc,
    }


def render(
    beam: Beam, pixel_mm: float, shape: tuple, center_mm=(0.0, 0.0)
) -> numpy.ndarray:
    """`beam` as a camera image of `shape` (rows, columns) at `pixel_mm` per pixel, in particle
    counts per pixel, with (x, y) = `center_mm` at the image center (the beam axis by default; the
    beam's centroid, to compare with a measured image that is centered on its beam)."""
    r, c = shape
    cx, cy = center_mm
    return numpy.histogram2d(
        beam.y_mm,
        beam.x_mm,
        bins=[r, c],
        range=[
            [cy - r * pixel_mm / 2, cy + r * pixel_mm / 2],
            [cx - c * pixel_mm / 2, cx + c * pixel_mm / 2],
        ],
    )[0]


def settings(step_data) -> dict:
    """The twin's solenoid currents [A] for a step: the mean of each logged readback in
    `SOLENOIDS` (`step_data` is a `scans.StepData`), as {`<solenoid>_current`: A}, and the beam
    charge [pC] from the logged ICT (`CHARGE_PV`) as `CHARGE_KNOB`, if there is one."""
    res = {
        f"{SOLENOIDS[k]}_current": float(v.mean())
        for k, v in step_data.readbacks.items()
        if k in SOLENOIDS
    }
    if CHARGE_PV in step_data.readbacks:
        # rounded, so the conversion's rounding error is not shown (5e-10 C is 500 pC)
        res[CHARGE_KNOB] = round(
            float(step_data.readbacks[CHARGE_PV].mean()) * CHARGE_PC_PER_UNIT, 6
        )
    return res


def twin_dir(path=None) -> pathlib.Path:
    """The twin's `twin/` directory: `path`, else that of the lume-rftrack source tree
    `lume_rftrack` is installed from.

    Raises:
        ValueError: none is found, or it has no `zone_model.py`
    """
    p = path
    if not p:
        import lume_rftrack

        p = pathlib.Path(lume_rftrack.__file__).resolve().parent.parent / _TWIN_SUBDIR
    p = pathlib.Path(p)
    if not (p / "zone_model.py").is_file():
        raise ValueError(
            f"no zone_model.py in the twin directory {p}: give the twin's "
            "twin/ directory"
        )
    return p


def _bounds(center: float, sigma: float, window: float, n: int) -> tuple:
    """The pixel range `[start, stop)` of `window` sigmas about `center`, within `n` pixels and at
    least a pixel wide."""
    a = max(int(numpy.floor(center - window * sigma)), 0)
    b = min(int(numpy.ceil(center + window * sigma)) + 1, n)
    return (a, b) if b > a else (a, min(a + 1, n))


def _moments(w: numpy.ndarray, x0: int, y0: int) -> dict:
    """The centroid `x`, `y` and rms sizes `sx`, `sy` [pixels, in the full image] and `total` of
    the weights `w`, whose top left pixel is at (`x0`, `y0`)."""
    total = float(w.sum())
    res = {"total": total}
    for axis, p, o in (("x", w.sum(axis=0), x0), ("y", w.sum(axis=1), y0)):
        i = numpy.arange(p.size) + o
        c = float((p * i).sum() / total)
        res[axis] = c
        res["s" + axis] = float(numpy.sqrt(max((p * (i - c) ** 2).sum() / total, 0.0)))
    return res
