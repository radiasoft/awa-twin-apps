"""AWA screen scans as saved by the AWA data acquisition, shared by the apps.

A scan is a set of files in one directory (or below it, at any depth), one setpoint of the scanned
solenoid per file, named `<camera>_<scan>_sol_<value>_<time>.h5`, e.g.
`Yag1_SolMScan_sol_270_1783720160.h5`: `<camera>_<scan>` names the dataset, `<value>` is the
setpoint [A] and `<time>` the Unix time the file was written. Each holds a stack of shots,
`images` (shots, rows, columns; uint16 camera counts), and one value per shot of every logged PV
(`AWA:Drive:DS3:RB`, ...), plus a `processed_image`. The `images` attributes carry the camera's
settings (`resolution`, `roi`, `target_charge`, `screen_name`, ...).

The camera background is a separate `<camera>_<scan>_sol_<value>_<time>_background.npy`, written
shortly before its setpoint's file, so it is matched by dataset and value, not by `<time>`.

:copyright: Copyright (c) 2026 RadiaSoft LLC.  All Rights Reserved.
:license: http://www.apache.org/licenses/LICENSE-2.0.html
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib
import re

import h5py
import numpy

# The attributes of `images` the loader returns as metadata (`StepData.metadata`), when present.
METADATA_ATTRIBUTES = (
    "alias",
    "background_file",
    "control_name",
    "resolution",
    "screen_name",
    "target_charge",
    "trig_time",
)
# A scan file's name: `<camera>_<scan>_sol_<value>_<time>[_background].(h5|npy)`
_NAME = re.compile(
    r"(?P<dataset>[A-Za-z0-9]+_[A-Za-z0-9]+)_sol_(?P<value>-?[0-9.]+?)_(?P<time>[0-9]+(?:\.[0-9]+)?)"
    r"(?P<background>_background)?\.(?P<suffix>h5|npy)"
)


@dataclasses.dataclass(frozen=True)
class Step:
    """One setpoint of a scan: its file, and the background matched to it (or None)."""

    dataset: str
    value: float
    time: float
    path: pathlib.Path
    background: pathlib.Path | None = None


@dataclasses.dataclass
class StepData:
    """What a step's file holds.

    Attributes:
        step (Step): the step read
        images (numpy.ndarray): the shots, (shots, rows, columns), float64 camera counts
        background (numpy.ndarray): the camera background, (rows, columns), or None
        mean (numpy.ndarray): the shots' mean less the background (the raw mean without one);
            negative counts are kept. It is the whole frame, with the screen's holder (a ring and
            a bright strip), so it is not the beam alone: use `processed` for that.
        processed (numpy.ndarray): the file's own `processed_image`, as stored: a 750x750 window of
            the background-subtracted frame at the camera's own pixel size (no rescaling;
            matched to `mean` by template matching, correlation 0.96-0.97), centered on the beam
            and with everything but the beam zeroed
        readbacks (dict): the logged PVs, name -> one value per shot
        roi (dict): the camera's region of interest, `xcenter`, `ycenter`, `xwidth`, `ywidth`
            [pixels] in the full frame, or None
        metadata (dict): the `METADATA_ATTRIBUTES` the file has
    """

    step: Step
    images: numpy.ndarray
    background: numpy.ndarray | None
    mean: numpy.ndarray
    processed: numpy.ndarray
    readbacks: dict
    roi: dict | None
    metadata: dict


def crop(image: numpy.ndarray, roi: dict) -> numpy.ndarray:
    """`image` (a full frame) cut to `roi`, centered on (`xcenter`, `ycenter`)."""
    x0 = roi["xcenter"] - roi["xwidth"] // 2
    y0 = roi["ycenter"] - roi["ywidth"] // 2
    return image[y0 : y0 + roi["ywidth"], x0 : x0 + roi["xwidth"]]


def datasets(data: pathlib.Path) -> dict[str, list[Step]]:
    """The datasets under `data`: `{<camera>_<scan>: steps}`, the steps in order of setpoint
    (then time). A step's background is the one of the same dataset and setpoint nearest to its
    file in time, else None.

    Raises:
        ValueError: `data` is not a directory
    """
    data = pathlib.Path(data)
    if not data.is_dir():
        raise ValueError(f"not a directory: {data}")
    files, backgrounds = [], {}
    for p in sorted(data.rglob("*")):
        m = _NAME.fullmatch(p.name)
        if not m:
            continue
        k = (m["dataset"], float(m["value"]))
        t = float(m["time"])
        if m["suffix"] == "npy":
            if m["background"]:
                backgrounds.setdefault(k, []).append((t, p))
        elif not m["background"]:
            files.append((k, t, p))
    res = {}
    for k, t, p in files:
        res.setdefault(k[0], []).append(
            Step(k[0], k[1], t, p, _background(backgrounds.get(k, []), t))
        )
    return {
        n: sorted(s, key=lambda x: (x.value, x.time)) for n, s in sorted(res.items())
    }


def read(step: Step) -> StepData:
    """Everything `step`'s file (and background) holds."""
    with h5py.File(step.path, "r") as f:
        images = f["images"][()].astype(numpy.float64)
        processed = f["processed_image"][()]
        n = images.shape[0]
        readbacks = {
            k: f[k][()].astype(numpy.float64)
            for k in f
            if k not in ("images", "processed_image")
            and f[k].ndim == 1
            and f[k].shape[0] == n
        }
        a = f["images"].attrs
        metadata = {k: _plain(a[k]) for k in METADATA_ATTRIBUTES if k in a}
        roi = ast.literal_eval(a["roi"]) if "roi" in a else None
    background = None if step.background is None else numpy.load(step.background)
    mean = images.mean(axis=0)
    if background is not None:
        mean = mean - background
    return StepData(
        step=step,
        images=images,
        background=background,
        mean=mean,
        processed=processed,
        readbacks=readbacks,
        roi=roi,
        metadata=metadata,
    )


def _background(candidates: list, time: float) -> pathlib.Path | None:
    """The path of the candidate `(time, path)` nearest `time`, or None without any."""
    if not candidates:
        return None
    return min(candidates, key=lambda c: abs(c[0] - time))[1]


def _plain(value):
    """An HDF5 attribute as a plain Python value: h5py returns numpy scalars and bytes."""
    if isinstance(value, bytes):
        return value.decode()
    return value.item() if isinstance(value, numpy.generic) else value
