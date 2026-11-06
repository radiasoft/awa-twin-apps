# AWA twin viewer: first milestone

## Goal

A local web app that runs the AWA twin at the settings logged for a recorded
YAG1 scan step and shows its YAG1 image beside the measured one, with the
compared numbers underneath. It is the AWA counterpart of `htu-twin-viewer`
(the `htu-twin-apps` repo, `htu_twin_apps/twin_viewer`).

This milestone **does not fit anything**. It shows how well the unfitted twin
already matches the data and which parameters to fit first. More AWA data is
expected later, so the data loader must not assume today's three files.

## Status

The viewer is built and prototyped; docs are deferred (still prototyping).

- `awa_twin_apps/scans.py`: finds `<camera>_<scan>_sol_<value>_<timestamp>.h5`
  files under the data directory argument, groups them into datasets and
  steps, matches each step's `_background.npy` by dataset and setpoint, and
  returns the shots, readbacks and `processed_image`.
- `awa_twin_apps/twin.py`: `Twin` builds `zone1_model(n_particles)` once and
  runs a step with every knob set each time (nothing leaks between runs).
  Knobs: `charge_pC` (defaults to the step's logged ICT), solenoid currents
  (SolBF, SolM, SolL1, SolL2), Gun and L1 power and phase, DT1/DT2 kicks.
  `image_stats` measures both images the same way (iterative +/-4 sigma
  window moments, baseline from the outside median).
- `awa_twin_apps/twin_viewer/server.py`: stdlib `http.server`, a cached
  `Viewer` with a background worker and a compute lock, validated edit keys.
  Run `awa-twin-viewer data-dir [--twin-dir DIR] [--port N] [--particles N]`
  (port 8070).
- `static/`: synoptic, measured and twin images on the same axes, profiles,
  numbers table, editable settings table, dataset picker and step slider.
- `tests/{scans,twin,server}_test.py`: 20 tests, with `$AWA_DATA` for the
  real-data ones.

Copied from HTU: `pyproject.toml`, the handler and cache/worker/lock pattern,
and the page structure. Not copied: the LPA fit chain, spectrometer and PMQ
knobs, `stacks.py` and the Cheetah and torch dependencies.

## Deferred

- **Docs.** `twin_viewer/README.md` (run, what it shows, caveats, screenshot),
  the top-level README table of apps, pre-commit and ruff config. Too early
  while prototyping.

## Open items

1. **Solenoid naming and calibration.** The position check against
   `Cathode_to_EndofZone2.xlsx` confirms `AWA:Drive:DS1/DS3/DS5:RB` are the
   twin's `SolBF`, `SolM` and `SolL2`, and `DS4` (`SolL1`) and `DS6`
   (`SolL4`) are not logged. `SolL2` (4.6 m) is downstream of YAG1 (3.0 m),
   so the `Sol4Scan`'s DS5 = 70 A cannot change the YAG1 beam in the twin.
   The `Sol4Scan` differs from the `SolMScan` also in `SolM` (250 vs
   270-278 A); the smaller measured beam (2.6/3.0 vs 4.5/5.1 mm) may be that
   `SolM` difference, which the twin underestimates (below). Not tested.
2. **RF.** `LLRF:K1:Amp:SetPoint` (4.2) and `PhRBV` (about 12) are logged
   with no mapped twin variable, so the viewer runs the nominal RF. Needs AWA's
   LLRF names, power and phase conventions, and a per-cavity offset from the
   logged phase to the crest-relative `phid`.
3. **Future data.** Will new scans use the same file names and layout? The
   loader is built around that pattern; other layouts need a second reader.
4. **Units to confirm with AWA.** The `images` attribute `resolution` (0.047) is
   taken as mm per pixel; the ICT (`AWAVXI11ICT:Ch1`, about 5.2e-10) as coulombs.

## Findings

- The `images` attributes carry the camera settings: `resolution` 0.047, `roi`
  (1000x1000 pixels centered at x=1091, y=574 of the 1200x1920 frame),
  `target_charge` 5e-10 (`target_charge_pv` `AWAVXI11ICT:Ch1`), `screen_name`
  `Yag1_BF`, `background_file`, `trig_time`.
- `processed_image` (750x750) is the image to compare: a window of the
  background-subtracted frame at the camera's pixel size (correlation 0.96-0.97
  at scale 1.0), centered on the beam, everything else zeroed. The
  whole-frame mean less the background also holds the screen holder, so its
  moments are wrong (rms about 13 mm). The window's center is not the beam's
  position on the screen, so only sizes and shapes are compared (as in HTU's
  A-line view).
- A step's background is written a few seconds before its file, so it is
  matched by dataset and setpoint, not by timestamp.
- The scanned value equals a logged readback: `SolMScan` (270, 278) is
  `AWA:Drive:DS3:RB`; `Sol4Scan` (70) is `AWA:Drive:DS5:RB`.
- Only elements upstream of YAG1 (z = 2.9 m) can change its beam: Gun, SolBF,
  SolM, L1, DT1, DT2, SolL1. SolL2 and the rest only matter for YAG2-YAG4. The
  twin's YAG1 rms against `SolL1` current (SolBF 552.3 A, SolM 249.8 A):

  | SolL1 [A] | 1 | 70 | 275 | 500 |
  |---|---|---|---|---|
  | rms x / y [mm] | 6.06 / 6.07 | 5.93 / 5.93 | 4.04 / 4.04 | 0.45 / 0.45 |

## Twin against data (2000 macroparticles, nominal RF)

rms size at YAG1 [mm], x / y, at each step's logged solenoid currents (SolBF
552 A; SolM and SolL2 as logged):

| Step | Measured | Twin, 1 nC | Twin, logged charge |
|---|---|---|---|
| `Sol4Scan` 70 (483 pC) | 2.6 / 3.0 | 6.1 / 6.1 | 5.1 / 5.1 |
| `SolMScan` 270 (519 pC) | 4.5 / 5.1 | 5.7 / 5.7 | 4.8 / 4.8 |
| `SolMScan` 278 (499 pC) | 4.0 / 4.4 | 5.5 / 5.5 | 4.6 / 4.6 |

- The charge is the largest single effect so far: the `SolMScan` is within 7%
  (270 A) and 15% (278 A).
- The twin responds less to SolM than the data (3% from 270 to 278 A, against
  10%).
- The twin is rotationally symmetric; the data has x and y differing by
  10-20%.
- The `Sol4Scan` is still off (open item 1).
- The first step takes about 50 s at 2000 particles (RF-Track holds the GIL
  while tracking and cannot be cancelled).

## Next

- Fit the laser spot sizes (`sig_x` and `sig_y` separately) and the emission
  settings on the two `SolMScan` steps, using the `Sol4Scan` as a check. A
  `fit.py` with a command-line runner would write the best parameters to a
  JSON file (as HTU's `twin-fit-values.json`) that the viewer loads. Search at
  500 particles, confirm at 2000.
- Changes to the twin itself (YAG1 and zone 2 positions in its lattice, solenoid
  placement, a writable charge) change these results; rerun the table after them.

## Not in this milestone

- Fitting (source, solenoid calibration, laser spot size): after we see the
  residuals.
- Zone 2 and its screens, the other YAGs.
- A shot-by-shot browser (HTU's `shot_viewer`).
- Mapping the LLRF amplitude and phase to gun variables.
