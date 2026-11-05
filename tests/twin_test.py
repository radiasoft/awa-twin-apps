"""awa_twin_apps.twin: comparing a beam with a camera image, and running the AWA twin"""


def test_image_stats():
    import numpy
    from pykern import pkunit

    from awa_twin_apps import twin

    rng = numpy.random.default_rng(1)
    r, c = 200, 300
    y, x = numpy.mgrid[0:r, 0:c]
    # centroid (+10, -5) pixels from the center, sigma 12 (x) and 20 (y) pixels
    cx, cy = (c - 1) / 2 + 10, (r - 1) / 2 - 5
    image = 1000 * numpy.exp(-((x - cx) ** 2 / 2 / 12**2 + (y - cy) ** 2 / 2 / 20**2))
    # an offset and a noise floor, with negatives as after a background subtraction
    image = image + 30 + rng.normal(0, 8, image.shape)
    s = twin.image_stats(image, 0.05)
    pkunit.pkok(abs(s["centroid_x_mm"] - 0.5) < 0.01, "centroid x {}", s)
    pkunit.pkok(abs(s["centroid_y_mm"] + 0.25) < 0.01, "centroid y {}", s)
    pkunit.pkok(abs(s["rms_x_mm"] / (12 * 0.05) - 1) < 0.03, "rms x {}", s)
    pkunit.pkok(abs(s["rms_y_mm"] / (20 * 0.05) - 1) < 0.03, "rms y {}", s)
    # the counts of a gaussian: 1000 * 2 pi sigma_x sigma_y, less what is outside the window
    pkunit.pkok(
        abs(s["counts"] / (1000 * 2 * numpy.pi * 12 * 20) - 1) < 0.02, "counts {}", s
    )


def test_particle_stats_and_render():
    import numpy
    from pykern import pkunit

    from awa_twin_apps import twin

    b = twin.Beam(
        x_mm=numpy.array([-1.0, 1.0, 1.0, 3.0]),
        y_mm=numpy.array([0.0, 0.0, 0.5, -0.5]),
        charge_pc=12.0,
    )
    s = twin.particle_stats(b)
    pkunit.pkeq(4.0, s["counts"])
    pkunit.pkeq(1.0, s["centroid_x_mm"])
    pkunit.pkeq(12.0, s["charge_pc"])
    # 10x20 pixels of 0.5 mm: x in [-5, 5), y in [-2.5, 2.5)
    im = twin.render(b, 0.5, (10, 20))
    pkunit.pkeq((10, 20), im.shape)
    pkunit.pkeq(4.0, im.sum())
    # x = 3.0 is column 16, y = -0.5 is row 4
    pkunit.pkeq(1.0, im[4, 16])


def test_render_matches_particles():
    """A dense beam rendered as an image has the sizes of its particles."""
    import numpy
    from pykern import pkunit

    from awa_twin_apps import twin

    rng = numpy.random.default_rng(2)
    n = 400_000
    b = twin.Beam(
        x_mm=rng.normal(0.3, 1.2, n), y_mm=rng.normal(-0.2, 0.8, n), charge_pc=1.0
    )
    s = twin.particle_stats(b)
    r = twin.image_stats(twin.render(b, 0.05, (400, 400)), 0.05)
    for k in ("centroid_x_mm", "centroid_y_mm"):
        pkunit.pkok(abs(r[k] - s[k]) < 0.02, "{} {} {}", k, r, s)
    for k in ("rms_x_mm", "rms_y_mm"):
        pkunit.pkok(abs(r[k] / s[k] - 1) < 0.02, "{} {} {}", k, r, s)


def test_sample_beam_sizes():
    """The processed images of the AWA sample data, if `$AWA_DATA` names it: a beam of a few mm
    at the window's center."""
    import os

    import pytest
    from pykern import pkunit

    from awa_twin_apps import scans, twin

    if not os.environ.get("AWA_DATA"):
        pytest.skip("no $AWA_DATA")
    for steps in scans.datasets(os.environ["AWA_DATA"]).values():
        for s in steps:
            r = scans.read(s)
            m = twin.image_stats(r.processed, r.metadata["resolution"])
            for k in ("rms_x_mm", "rms_y_mm"):
                pkunit.pkok(2.0 < m[k] < 6.0, "{} {} {}", s.path.name, k, m)
            for k in ("centroid_x_mm", "centroid_y_mm"):
                pkunit.pkok(abs(m[k]) < 0.5, "{} {} {}", s.path.name, k, m)


def test_settings():
    import types

    import numpy
    from pykern import pkunit

    from awa_twin_apps import twin

    d = types.SimpleNamespace(
        readbacks={
            "AWA:Drive:DS1:RB": numpy.array([552.0, 553.0]),
            "AWA:Drive:DS3:RB": numpy.array([270.0, 270.0]),
            "AWAVXI11ICT:Ch1": numpy.array([5.0e-10, 5.2e-10]),
        }
    )
    s = twin.settings(d)
    # the charge is the ICT's mean, in pC
    pkunit.pkok(abs(s.pop("charge_pC") - 510.0) < 1e-6, "{}", s)
    pkunit.pkeq({"SolBF_current": 552.5, "SolM_current": 270.0}, s)
    del d.readbacks["AWAVXI11ICT:Ch1"]
    pkunit.pkeq({"SolBF_current": 552.5, "SolM_current": 270.0}, twin.settings(d))


def test_twin_dir():
    from pykern import pkunit

    from awa_twin_apps import twin

    with pkunit.pkexcept("no zone_model.py"):
        twin.twin_dir(pkunit.empty_work_dir())


def test_twin_run():
    """The AWA twin at 300 macroparticles, if `lume_rftrack` is a source tree with it."""
    import pytest
    from pykern import pkunit

    from awa_twin_apps import twin

    try:
        t = twin.Twin(n_particles=300, threads=4)
    except ValueError:
        pytest.skip("no AWA twin directory")
    # the drawn elements: in order of position, with the gun's solenoids and the camera's screen
    e = t.elements()
    pkunit.pkeq(sorted(x["z_m"] for x in e), [x["z_m"] for x in e])
    k = {x["name"]: x["kind"] for x in e}
    pkunit.pkeq(
        ["solenoid", "cavity", "screen"], [k["SolBF"], k["Gun"], k[twin.SCREEN]]
    )
    pkunit.pkok(all(x["width_m"] > 0 for x in e), "{}", e)
    d = t.defaults()
    pkunit.pkeq(list(twin.KNOBS), list(d))
    pkunit.pkeq(
        (550.0, 440.0, 1.0, 0.0, 1000.0),
        (
            d["SolBF_current"],
            d["SolM_current"],
            d["Gun_P_actual"],
            d["Gun_phid"],
            d["charge_pC"],
        ),
    )
    base = {"SolBF_current": 550.0, "SolM_current": 440.0, "SolL2_current": 1.0}
    a = t.run(base)
    pkunit.pkeq(a.x_mm.shape, a.y_mm.shape)
    pkunit.pkok(a.x_mm.size > 100, "too few particles at the screen: {}", a.x_mm.size)
    pkunit.pkok(a.charge_pc > 0, "no charge")
    # the same values come from the cache, and the knobs not given are nominal
    pkunit.pkeq(True, t.run(dict(base)) is a)
    pkunit.pkeq(True, t.run({"SolM_current": 440.0}) is a)
    with pkunit.pkexcept("not a knob"):
        t.run({"SolM": 440.0})
    # a different matching solenoid focuses the beam differently
    b = t.run({**base, "SolM_current": 270.0})
    pkunit.pkok(
        abs(b.x_mm.std() - a.x_mm.std()) > 0.01 * a.x_mm.std(),
        "rms x did not change: {} {}",
        a.x_mm.std(),
        b.x_mm.std(),
    )
    # so does the gun's phase
    c = t.run({**base, "Gun_phid": 20.0})
    pkunit.pkok(
        abs(c.x_mm.std() - a.x_mm.std()) > 0.01 * a.x_mm.std()
        or abs(c.x_mm.size - a.x_mm.size) > 5,
        "the gun's phase changed nothing: {} {}",
        a.x_mm.std(),
        c.x_mm.std(),
    )
    # a corrector's kick moves the beam
    k = t.run({**base, "DT1_strength_x": 0.05})
    pkunit.pkok(abs(k.x_mm.mean() - a.x_mm.mean()) > 0.1, "DT1 did not move the beam")
    # the charge: the same particles with another charge, and back
    q = t.run({**base, "charge_pC": 520.0})
    pkunit.pkok(abs(q.charge_pc - 520.0) < 1.0, "charge {}", q.charge_pc)
    pkunit.pkok(abs(a.charge_pc - 1000.0) < 1.0, "charge {}", a.charge_pc)
    pkunit.pkok(
        abs(q.x_mm.std() - a.x_mm.std()) > 0.02 * a.x_mm.std(),
        "the charge changed nothing: {} {}",
        q.x_mm.std(),
        a.x_mm.std(),
    )
    # a run does not keep an earlier run's edits: without the cache it is the same as the first
    t._cache.clear()
    again = t.run(base)
    pkunit.pkok(
        abs(again.x_mm.std() / a.x_mm.std() - 1) < 1e-3,
        "an earlier edit stayed: {} {}",
        again.x_mm.std(),
        a.x_mm.std(),
    )
