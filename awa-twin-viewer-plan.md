# AWA twin viewer: first milestone

## Goal

A local web app that runs the AWA twin at the settings logged for a recorded
YAG1 scan step and shows its YAG1 image beside the measured one, with the
compared numbers underneath. It is the AWA counterpart of `htu-twin-viewer`
(`~/src/radiasoft/htu-twin-apps`, `htu_twin_apps/twin_viewer`).

This milestone **does not fit anything**. It shows how well the unfitted twin
already matches the data and which parameters to fit first. More AWA data is
expected later, so the data loader must not assume today's three files.

## What exists

HTU, to copy from:
- `htu_twin_apps/twin_viewer/`: a ~850 line stdlib `http.server` app (`/api/datasets`,
  `/api/step`), a `Viewer` class that simulates a step on first request, caches it
  and simulates the rest of the dataset on a background thread, and a static page
  (`index.html`, `style.css`, `app.js`, plotly from a CDN) with a synoptic, plots,
  a dataset picker, a step slider, a numbers table and an editable settings table.
- Repo layout: one package with a subpackage per app, each with a README, a console
  script and `static/` assets; the `README.md` table of apps; `pyproject.toml`
  (chronver, `package-data` for `*/static/**`).

AWA, to build on:
- The twin: `lume-rftrack/examples/awa-zone-twin/twin/zone_model.py`
  (`zone1_model(n_particles)`), with solenoid currents in A (`SolBF_current`,
  `SolM_current`, `SolL1_current`, ...) and the YAG1 image from
  `simulator.beamline.get_bunch_at_screens()`.
- Data (`~/save/twain/example-data/Experimental Data/`): three YAG1 files, each one
  setpoint of a solenoid scan. Every `.h5` has `images` (4 shots, 1200x1920), a
  `processed_image` (750x750) and 4-point readbacks (`AWA:Drive:DS1/DS3/DS5:RB`,
  `AWAVXI11ICT:Ch1`, `LLRF:K1:Amp:SetPoint`, `LLRF:K1:PhRBV`). A `_background.npy`
  (1200x1920) sits beside each. Names are
  `Yag1_<Sol4Scan|SolMScan>_sol_<value>_<timestamp>[_background].(h5|npy)`.
- Beamline table: `Cathode_to_EndofZone2.xlsx` (element positions, control PVs).

## What to copy, and what not

| Copy (adapt) | Do not copy |
|---|---|
| `pyproject.toml`, README structure, "Adding an app" section | `lpa_source/` (the 17-step LPA fit chain) |
| `twin_viewer/server.py`: handler, `Viewer` cache/background/lock pattern, `_clean`, `_downsample`, edit-knob whitelist | spectrometer, magspec and A-line code, slit and PMQ knobs |
| `static/` page: layout, step slider, numbers and settings tables, reset-edits | the HTU synoptic's element list |
| the module docstring and copyright header style | `stacks.py` (it matches device frames to a scalar table by timestamp; AWA files hold shots and readbacks together) |
| | Cheetah and torch dependencies |

## Repo layout

```
awa-twin-apps/
  pyproject.toml            # awa-twin-apps; script awa-twin-viewer
  README.md                 # table of apps, install, data, adding an app
  awa-twin-viewer-plan.md   # this file
  awa_twin_apps/
    __init__.py
    scans.py                # reads the YAG scan files
    twin.py                 # runs zone 1 at logged settings; renders the YAG1 image
    twin_viewer/
      __init__.py
      README.md
      server.py
      static/{index.html,style.css,app.js}
  tests/
```

## Steps

1. **Repo skeleton.** Copy `pyproject.toml` (rename, dependencies `h5py`, `numpy`,
   `lume-rftrack`; the twin's own dependencies come with it), the README table and
   the empty `awa_twin_apps/twin_viewer/` package. Entry point `awa-twin-viewer`.
   *Done when* `pip install -e .` works and `awa-twin-viewer --help` runs.

2. **Scan loader (`scans.py`).** Read a data directory, from the argument or
   `$AWA_DATA`.
   - Find `<camera>_<scan>_sol_<value>_<timestamp>.h5` files and group them by
     `<camera>_<scan>`: a group is a dataset, a file is a step, sorted by value.
     Datasets come from the files found, not from a hard-coded table (HTU has a
     `TODO` for the same).
   - For a step: the 4 raw shots, the matching `_background.npy`, the background
     subtracted step-mean image, the 4-point readbacks (mean and spread) and the
     `processed_image`.
   - *Done when* tests load the three sample files and return 2 datasets
     (`Yag1_SolMScan`: 270, 278; `Yag1_Sol4Scan`: 70).

3. **Twin runner (`twin.py`).** Build `zone1_model(n_particles)` once and, for a step,
   `set()` the logged solenoid currents; return the tracked YAG1 bunch.
   - Render the twin's image: a 2D histogram of x, y at YAG1 over the measured
     image's field of view, at a pixel size that is an editable knob.
   - Compute the same numbers for both images: rms sizes (x, y), centroid, and
     total counts. Measured: the background-subtracted step-mean image.
   - One simulation at a time (lock), results cached per step and edit set.
   - *Done when* a step's twin image and numbers come back in one call at 2000
     particles, and a test with a few hundred particles checks the shapes.

4. **Server (`twin_viewer/server.py`).** Copy HTU's handler and `Viewer`.
   `/api/datasets` lists datasets and step counts; `/api/step?scan=&step=&edits=`
   returns the measured image, the twin image, the numbers and the settings.
   Background thread simulates the rest of the dataset. Edit knobs: the solenoid
   currents (the logged ones replaced), `um_per_px`, and `--particles`.
   *Done when* both datasets are served and a bad edit key is refused.

5. **Page.** Copy HTU's page and keep its structure.
   - **Synoptic:** the AWA beamline in beam order, from the twin's element list
     (names, kinds, positions), with the scanned solenoid outlined and each
     element's value at this step. Overlapping elements are separated as in the
     Phoebus display (`_placed()`).
   - **Twin against the data:** the two YAG1 images on the same axes (mm), and a
     profile plot of each.
   - **Numbers table:** measured and twin rms size, centroid and counts.
   - **Settings table:** logged value, value the twin ran with (editable), and
     units.
   - Dataset picker and step slider as in HTU.
   *Done when* a step shows both images and the tables, and editing a solenoid
   current reruns the twin.

6. **Docs and tests.** `twin_viewer/README.md` (run, what it shows, caveats, with a
   screenshot), the top-level README table, tests for the loader and the server
   API with a stub twin. Pre-commit and ruff as in `lume-rftrack`.

## Open items (need an answer before step 3)

1. **Reaching the twin code.** `zone_model.py` is an example in `lume-rftrack`, not
   an installed package. Options: a `$AWA_TWIN_DIR`/`--twin-dir` path added to
   `sys.path` (quickest), install the example as a package, or copy it into this
   repo. I'd start with the path.
2. **Solenoid names.** The files' `DS1/DS3/DS5` readbacks: DS1 is about 552 A,
   which matches the twin's `SolBF` (550 A). DS3 is 250-278 A against the twin's
   `SolM` at 440 A. DS5 is 70 A in the `Sol4Scan` and 1.4 A in the `SolMScan`.
   Which twin element is each, and what is a "Sol4"? The mapping decides which
   `*_current` the loader sets.
3. **Image scale.** What is `processed_image` (ROI, binning, background removal)?
   What is the YAG1 pixel size or field of view? Until known, `um_per_px` is a
   labelled placeholder.
4. **RF and charge.** `LLRF:K1:Amp:SetPoint` (4.2) and `PhRBV` (~12) are logged but
   have no mapped twin variable; the first milestone runs the nominal RF and
   shows these as logged only. The ICT (`AWAVXI11ICT:Ch1`) logs about 5.2e-10, which
   matches the camera's 5e-10 `target_charge`, so it is the beam charge in
   coulombs (about 0.52 nC; the unit is to be confirmed). The twin's charge is a
   knob (`charge_pC`) that defaults to each step's logged ICT: the twin rebuilds its
   cathode bunch (same seed, so the same particles) at that charge and re-tracks.
5. **Future data.** Will new scans use the same file names and layout? The loader
   is built around that pattern; other layouts would need a second reader.

## Findings while building the loader (step 2)

- The `images` attributes in each `.h5` carry the camera settings: `resolution` 0.047,
  `roi` (1000x1000 pixels centered at x=1091, y=574 of the 1200x1920 frame), `target_charge`
  5e-10 (0.5 nC, with `target_charge_pv` `AWAVXI11ICT:Ch1`), `screen_name` `Yag1_BF`,
  `background_file`, `trig_time`. `resolution` is very likely the pixel size in mm (47 um), which
  answers part of open item 3; confirm the unit with AWA.
- `processed_image` (750x750) is the image to compare. It is a window of the background-subtracted
  frame at the camera's own pixel size (matched at scale 1.0, correlation 0.96-0.97), centered on
  the beam, with everything but the beam zeroed. The whole-frame mean less the background also
  holds the screen holder (a ring and a bright strip), so moments of it are wrong (rms ~13 mm).
  The window's center is not the beam's position on the screen, so only sizes and shapes are
  compared, as in HTU's A-line view, where the twin's spot is centered on its own centroid.
  (An earlier version of this note said it was not a crop of the frame: that used the wrong scale.)
- Measured beam sizes from `processed_image`, by the windowed moments of `twin.image_stats`: rms
  x/y of 2.6/3.0 mm (`Sol4Scan` 70), 4.5/5.1 mm (`SolMScan` 270) and 4.0/4.4 mm (278).
- Open item 2: the scanned value equals a logged readback. `SolMScan` (270, 278) matches
  `AWA:Drive:DS3:RB`, the matching solenoid (`SolM` in the twin), which was 250 A during the
  `Sol4Scan` and 270-278 A in the `SolMScan`. `Sol4Scan` (70) matches `AWA:Drive:DS5:RB`, which
  the twin's naming makes `SolL2`; the 1.4 A in the other scans is DS5 left at about zero.
- The ICT logs 5.19e-10 (an earlier version of this note said 0.0: that was a rounding of the
  printout). It matches the camera's `target_charge` of 5e-10, so it is taken as coulombs.
- A step's background is written a few seconds before its file, so it is matched by dataset and
  setpoint, not by timestamp.

## Which parameters can matter at YAG1

The twin's zone 1 variables: each solenoid's `current` (SolBF, SolM, SolL1, SolL2, SolL4, A),
each cavity's `P_actual` (Gun, L1-L6; relative power, 1.0 = the map's, field scales as its
square root) and `phid` (relative to the autophased phase, 0 nominal), and each corrector's
`strength_x`/`strength_y` (DT1-DT7, T*mm). Only elements upstream of YAG1 (z = 2.9 m) can change
its beam: Gun, SolBF, SolM, L1, DT1, DT2 and SolL1. The rest (SolL2 at 4.1 m, SolL4, L2-L6,
DT3-DT7) only matter for YAG2-YAG4.

The `Sol4Scan` (the logged `AWA:Drive:DS5:RB` at 70 A, with SolM at 250 A) puts the measured beam
at 2.6/3.0 mm, much smaller than the `SolMScan`'s 4.5/5.1 mm. In the twin (2000 macroparticles,
SolBF 552.3 A, SolM 249.8 A) the YAG1 rms size against the `SolL1` current is:

| SolL1 [A] | 1 | 70 | 275 | 500 |
|---|---|---|---|---|
| rms x / y [mm] | 6.06 / 6.07 | 5.93 / 5.93 | 4.04 / 4.04 | 0.45 / 0.45 |

and `SolL2`, downstream of YAG1, has no effect (6.06 at 70 A, as at 1 A). So the DS5 -> `SolL2`
mapping in `twin.SOLENOIDS` cannot explain the data, while 70 A on `SolL1` changes the beam by
only 2%: the measured 2.6-3.0 mm needs about 350-400 A on `SolL1`, five times the logged value. So
the solenoid scanned in `Sol4Scan` is another element or on another calibration than the twin's
(reference 500 A). `awa-rftrack-lattices` numbers the solenoids `DS1` (bucking-focusing), `DS3`
(matching), `DS4` (`SolL1`), `DS5` (`SolL2`) and `DS6` (`SolL4`), with no `DS2`, which fits the
logged `DS1` (552 A) and `DS3` but not the effect of `DS5`; it holds no PV names, no LLRF, and no
calibration for the logged PVs. Needs AWA's solenoid naming and calibration.

(An earlier version of this section said 70 A on `SolL1` changed nothing and that nominal was
5.92 mm. That test reused the twin between runs, so the "nominal" run still had 70 A on `SolL1`;
`Twin.run` now sets every knob each time.)

## First twin against data (step 3, 2000 macroparticles, nominal RF, 1 nC)

rms size at YAG1 [mm], x / y, with the twin at each step's logged solenoid currents
(`SolBF` 552 A; `SolM` and `SolL2` as logged):

| Step | SolM [A] | SolL2 [A] | Measured | Twin |
|---|---|---|---|---|
| `Sol4Scan` 70 | 250 | 70 | 2.6 / 3.0 | 6.1 / 6.1 |
| `SolMScan` 270 | 270 | 1.4 | 4.5 / 5.1 | 5.7 / 5.7 |
| `SolMScan` 278 | 278 | 1.5 | 4.0 / 4.4 | 5.5 / 5.5 |

The twin is the right size but not matching: it is rotationally symmetric (the measured x and y
differ by 10-20%), and it moves less with the matching solenoid than the data does. Not mapped
yet: the LLRF amplitude and phase (the twin runs its nominal RF), and the charge (the ICT logs about
0.52 nC, against the twin's 1 nC).

## With the logged charge (the charge knob)

The twin at each step's logged ICT charge (483-519 pC) instead of 1 nC, rms size at YAG1 [mm],
x / y:

| Step | Measured | Twin, 1 nC | Twin, logged charge |
|---|---|---|---|
| `Sol4Scan` 70 (483 pC) | 2.6 / 3.0 | 6.1 / 6.1 | 5.1 / 5.1 |
| `SolMScan` 270 (519 pC) | 4.5 / 5.1 | 5.7 / 5.7 | 4.8 / 4.8 |
| `SolMScan` 278 (499 pC) | 4.0 / 4.4 | 5.5 / 5.5 | 4.6 / 4.6 |

The charge is the largest single effect so far: the `SolMScan` is within 7% (270 A) and 15%
(278 A). The twin still responds less to SolM than the data (3% from 270 to 278 A, against 10%),
and the `Sol4Scan` is still off (see the solenoid mapping above). The next step is to fit the
laser spot sizes (x and y separately) and the emission settings.

## Not in this milestone

- Fitting (source, solenoid calibration, laser spot size): after we see the
  residuals.
- Zone 2 and its screens, the other YAGs.
- A shot-by-shot browser (HTU's `shot_viewer`).
- Mapping the LLRF amplitude and phase to gun variables.
- Making the twin faster (the zone 1 track takes tens of seconds); see
  `awa-twin-multi-updated-plan.md` in `lume-rftrack`.
