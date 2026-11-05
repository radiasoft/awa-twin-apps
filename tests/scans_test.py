"""awa_twin_apps.scans: finding the datasets under a data directory and reading a step"""


def test_datasets():
    from pykern import pkunit

    from awa_twin_apps import scans

    d = _write_data(pkunit.empty_work_dir())
    res = scans.datasets(d)
    pkunit.pkeq(["Cam_AScan", "Cam_BScan"], list(res))
    a = res["Cam_AScan"]
    # in order of setpoint, not of time or name
    pkunit.pkeq([10.0, 20.0], [s.value for s in a])
    pkunit.pkeq(
        ["Cam_AScan_sol_10_200.h5", "Cam_AScan_sol_20_100.h5"], [s.path.name for s in a]
    )
    # the background of the same setpoint, found by value though its time differs
    pkunit.pkeq(
        ["Cam_AScan_sol_10_195.5_background.npy", "Cam_AScan_sol_20_90_background.npy"],
        [s.background.name for s in a],
    )
    b = res["Cam_BScan"]
    pkunit.pkeq([5.0], [s.value for s in b])
    pkunit.pkeq(None, b[0].background)


def test_datasets_not_a_directory():
    from pykern import pkunit

    from awa_twin_apps import scans

    with pkunit.pkexcept("not a directory"):
        scans.datasets(pkunit.empty_work_dir().join("missing"))


def test_read():
    import numpy
    from pykern import pkunit

    from awa_twin_apps import scans

    d = _write_data(pkunit.empty_work_dir())
    s = scans.datasets(d)["Cam_AScan"][0]
    r = scans.read(s)
    pkunit.pkeq((3, 6, 8), r.images.shape)
    pkunit.pkeq(numpy.float64, r.images.dtype)
    numpy.testing.assert_array_equal(r.mean, r.images.mean(axis=0) - 2.0)
    numpy.testing.assert_array_equal(r.background, numpy.full((6, 8), 2.0))
    pkunit.pkeq((2, 2), r.processed.shape)
    # the per-shot PVs only, not the stacks
    pkunit.pkeq(["PV:A", "PV:B"], sorted(r.readbacks))
    numpy.testing.assert_array_equal(r.readbacks["PV:A"], [1.0, 2.0, 3.0])
    pkunit.pkeq({"xcenter": 4, "ycenter": 3, "xwidth": 4, "ywidth": 2}, r.roi)
    pkunit.pkeq(
        {"resolution": 0.047, "screen_name": "Cam_BF", "target_charge": 5e-10},
        {k: r.metadata[k] for k in ("resolution", "screen_name", "target_charge")},
    )
    pkunit.pkeq((2, 4), scans.crop(r.mean, r.roi).shape)


def test_read_without_background():
    import numpy
    from pykern import pkunit

    from awa_twin_apps import scans

    d = _write_data(pkunit.empty_work_dir())
    r = scans.read(scans.datasets(d)["Cam_BScan"][0])
    pkunit.pkeq(None, r.background)
    numpy.testing.assert_array_equal(r.mean, r.images.mean(axis=0))


def test_sample_data():
    """The AWA sample data, if `$AWA_DATA` names it."""
    import os

    import pytest
    from pykern import pkunit

    from awa_twin_apps import scans

    if not os.environ.get("AWA_DATA"):
        pytest.skip("no $AWA_DATA")
    res = scans.datasets(os.environ["AWA_DATA"])
    pkunit.pkeq(["Yag1_Sol4Scan", "Yag1_SolMScan"], list(res))
    pkunit.pkeq([[70.0], [270.0, 278.0]], [[s.value for s in x] for x in res.values()])
    pkunit.pkok(
        all(s.background for x in res.values() for s in x), "a step has no background"
    )
    r = scans.read(res["Yag1_SolMScan"][0])
    pkunit.pkeq((4, 1200, 1920), r.images.shape)
    pkunit.pkeq((750, 750), r.processed.shape)
    pkunit.pkeq(1000, r.roi["xwidth"])
    pkunit.pkeq(0.047, r.metadata["resolution"])
    pkunit.pkeq(
        {"AWA:Drive:DS1:RB", "AWA:Drive:DS3:RB", "AWA:Drive:DS5:RB"},
        {k for k in r.readbacks if k.startswith("AWA:Drive")},
    )


def _write_data(root):
    """A data directory: `Cam_AScan` at 10 and 20 (in a subdirectory, with decoy files) and
    `Cam_BScan` at 5 without a background. Shots are 3 of 6x8."""
    import h5py
    import numpy

    d = root.join("data", "sub")
    d.ensure(dir=True)
    root.join("data", "README.txt").write("not a scan")
    root.join("data", ".DS_Store").write("")

    def _file(name, shots):
        with h5py.File(str(d.join(name)), "w") as f:
            f["images"] = (numpy.arange(3 * 6 * 8).reshape(3, 6, 8) + shots).astype(
                "uint16"
            )
            f["processed_image"] = numpy.zeros((2, 2), dtype="float32")
            f["PV:A"] = numpy.array([1.0, 2.0, 3.0])
            f["PV:B"] = numpy.array([4.0, 5.0, 6.0])
            f["not_per_shot"] = numpy.array([1.0, 2.0])
            f["images"].attrs["roi"] = (
                "{'xcenter': 4, 'ycenter': 3, 'xwidth': 4, 'ywidth': 2}"
            )
            f["images"].attrs["resolution"] = numpy.float64(0.047)
            f["images"].attrs["screen_name"] = "Cam_BF"
            f["images"].attrs["target_charge"] = numpy.float64(5e-10)

    _file("Cam_AScan_sol_20_100.h5", 0)
    _file("Cam_AScan_sol_10_200.h5", 0)
    _file("Cam_BScan_sol_5_300.h5", 0)
    for name in (
        "Cam_AScan_sol_10_195.5_background.npy",
        "Cam_AScan_sol_20_90_background.npy",
        # another setpoint's, which must not match
        "Cam_AScan_sol_30_199_background.npy",
    ):
        numpy.save(str(d.join(name)), numpy.full((6, 8), 2.0))
    return root.join("data")
