"""awa_twin_apps.twin_viewer.server: the viewer's steps and edits, and its HTTP API, with a stub
twin and synthetic scans"""


def test_datasets():
    from pykern import pkunit

    d = _viewer(pkunit.empty_work_dir())[0].datasets()["datasets"]
    pkunit.pkeq(["Cam_Sol4Scan", "Cam_SolMScan"], [x["scan"] for x in d])
    pkunit.pkeq([1, 2], [x["steps"] for x in d])
    pkunit.pkeq([[70.0], [100.0, 200.0]], [x["values"] for x in d])
    r = _viewer(pkunit.empty_work_dir())[0].datasets()
    # what the page draws the beamline from, and the twin's size
    pkunit.pkeq(["SolBF", "YAG1"], [x["name"] for x in r["beamline"]])
    pkunit.pkeq(2000, r["particles"])
    # the scanned solenoid is the one whose readback follows the setpoints
    pkunit.pkeq(["SolL2", "SolM"], [x["scanned"] for x in d])


def test_step():
    from pykern import pkunit

    from awa_twin_apps import twin

    v, t = _viewer(pkunit.empty_work_dir())
    r = v.step("Cam_SolMScan", 1, {})
    # the twin ran with the logged currents and charge (the ICT's, in pC)
    c = dict(t.calls[0])
    pkunit.pkok(abs(c.pop("charge_pC") - 500.0) < 1e-6, "{}", t.calls)
    pkunit.pkeq(
        {"SolBF_current": 552.0, "SolM_current": 200.0, "SolL2_current": 1.5}, c
    )
    pkunit.pkeq(1, len(t.calls))
    pkunit.pkeq(200.0, r["value"])
    pkunit.pkeq("SolM", r["scanned"])
    # the measured image is a 60 x 80 gaussian of sigma 6 (x) and 9 (y) pixels at 0.1 mm
    pkunit.pkok(abs(r["measured"]["rms_x_mm"] / 0.6 - 1) < 0.03, "{}", r["measured"])
    pkunit.pkok(abs(r["measured"]["rms_y_mm"] / 0.9 - 1) < 0.03, "{}", r["measured"])
    pkunit.pkeq((80, 60), (len(r["measured"]["image"]), len(r["measured"]["image"][0])))
    pkunit.pkeq((80, 60), (len(r["twin"]["image"]), len(r["twin"]["image"][0])))
    pkunit.pkeq(1.0, max(max(x) for x in r["measured"]["image"]))
    # the twin's rms size is the stub's, from the matching solenoid
    pkunit.pkok(abs(r["twin"]["rms_x_mm"] / 3.0 - 1) < 0.05, "{}", r["twin"])
    pkunit.pkeq(
        ["rms x", "rms y", "rms x / y", "charge"], [x["name"] for x in r["numbers"]]
    )
    # the charge is the ICT's, in pC, against the twin's
    c = {x["name"]: x for x in r["numbers"]}["charge"]
    pkunit.pkok(abs(c["measured"] - 500.0) < 1e-6, "{}", c)
    pkunit.pkeq(500.0, c["twin"])
    # every knob of the twin, then what was logged and not used, then the pixel size
    s = {x["name"]: x for x in r["settings"]}
    # the charge knob is the logged ICT's, which is not a row of its own
    pkunit.pkeq(
        (500.0, 500.0, "pC"),
        (s["Charge"]["logged"], s["Charge"]["twin"], s["Charge"]["unit"]),
    )
    pkunit.pkeq("AWAVXI11ICT:Ch1", s["Charge"]["pv"])
    pkunit.pkeq(False, "AWAVXI11ICT:Ch1" in s)
    pkunit.pkeq(list(twin.KNOBS), [x["key"] for x in r["settings"] if x["key"]][:-1])
    pkunit.pkeq(200.0, s["SolM current"]["logged"])
    pkunit.pkeq(200.0, s["SolM current"]["twin"])
    pkunit.pkeq(True, s["SolM current"]["scanned"])
    pkunit.pkeq("scanned", s["SolM current"]["note"])
    pkunit.pkeq(False, s["SolBF current"]["scanned"])
    # a knob with no logged value is at its nominal one
    pkunit.pkeq(None, s["Gun phase"]["logged"])
    pkunit.pkeq(0.0, s["Gun phase"]["twin"])
    pkunit.pkeq(1.0, s["Gun power"]["twin"])
    pkunit.pkeq(440.0, s["SolM current"]["twin"] + 240.0)
    # what the twin does not use is shown as logged
    pkunit.pkeq(None, s["LLRF:K1:Amp:SetPoint"]["twin"])
    pkunit.pkeq(None, s["LLRF:K1:Amp:SetPoint"]["key"])
    pkunit.pkeq("SolM_current", s["SolM current"]["key"])
    # a solenoid's readback is its row's logged value, not a row of its own
    pkunit.pkeq(False, "AWA:Drive:DS3:RB" in s)
    pkunit.pkeq(False, "SolM_current" in s)
    pkunit.pkeq(False, s["LLRF:K1:Amp:SetPoint"]["editable"])
    pkunit.pkeq(0.1, s["pixel size"]["twin"])


def test_step_cached():
    from pykern import pkunit

    v, t = _viewer(pkunit.empty_work_dir())
    a = v.step("Cam_SolMScan", 0, {})
    pkunit.pkeq(True, v.step("Cam_SolMScan", 0, {}) is a)
    pkunit.pkeq(1, len(t.calls))
    # another step, or other edits, are other results
    v.step("Cam_SolMScan", 1, {})
    v.step("Cam_SolMScan", 0, {"SolBF_current": 500})
    pkunit.pkeq(3, len(t.calls))


def test_edits():
    from pykern import pkunit

    v, t = _viewer(pkunit.empty_work_dir())
    base = v.step("Cam_SolMScan", 0, {})
    r = v.step("Cam_SolMScan", 0, {"SolM_current": 123, "pixel_mm": 0.2})
    # an edit replaces the logged current, and is what the twin ran with
    pkunit.pkeq(123.0, t.calls[-1]["SolM_current"])
    pkunit.pkeq(552.0, t.calls[-1]["SolBF_current"])
    s = {x["name"]: x for x in r["settings"]}
    pkunit.pkeq(
        (True, 100.0, 123.0),
        (
            s["SolM current"]["edited"],
            s["SolM current"]["logged"],
            s["SolM current"]["twin"],
        ),
    )
    pkunit.pkeq(False, s["SolBF current"]["edited"])
    pkunit.pkeq({"SolM_current": 123.0, "pixel_mm": 0.2}, r["edits"])
    # the pixel size scales the measured image only
    pkunit.pkok(
        abs(r["measured"]["rms_x_mm"] / base["measured"]["rms_x_mm"] - 2) < 1e-6,
        "{}",
        r["measured"],
    )
    pkunit.pkeq(0.2, s["pixel size"]["twin"])
    pkunit.pkeq(0.1, s["pixel size"]["logged"])


def test_knobs():
    """The Gun's and L1's power and phase, the kicks of DT1 and DT2 and SolL1 are edited like the
    solenoids, and are at their nominal values until they are."""
    from pykern import pkunit

    v, t = _viewer(pkunit.empty_work_dir())
    base = v.step("Cam_SolMScan", 0, {})
    s = {x["key"]: x for x in base["settings"] if x["key"]}
    pkunit.pkeq(
        (False, 1.0, None),
        (
            s["L1_P_actual"]["edited"],
            s["L1_P_actual"]["twin"],
            s["L1_P_actual"]["logged"],
        ),
    )
    pkunit.pkeq(1.0, s["SolL1_current"]["twin"])
    edits = {
        "Gun_P_actual": 1.1,
        "Gun_phid": 5,
        "L1_phid": -3,
        "DT1_strength_x": 0.2,
        "DT2_strength_y": -0.1,
        "SolL1_current": 20,
    }
    r = v.step("Cam_SolMScan", 0, edits)
    # what the twin is given: the logged currents and charge and the edits (it supplies the
    # nominal rest)
    c = dict(t.calls[-1])
    pkunit.pkok(abs(c.pop("charge_pC") - 500.0) < 1e-6, "{}", t.calls[-1])
    pkunit.pkeq(
        {**edits, "SolBF_current": 552.0, "SolM_current": 100.0, "SolL2_current": 1.5},
        c,
    )
    s = {x["key"]: x for x in r["settings"] if x["key"]}
    for k, x in edits.items():
        pkunit.pkeq((True, float(x)), (s[k]["edited"], s[k]["twin"]))
    pkunit.pkeq(False, s["L1_P_actual"]["edited"])
    pkunit.pkeq(5.0, s["Gun_phid"]["twin"])
    pkunit.pkeq("deg", s["Gun_phid"]["unit"])
    pkunit.pkeq("T*mm", s["DT1_strength_x"]["unit"])


def test_charge_knob():
    """The charge is the logged ICT's until it is edited, and the twin runs with it."""
    from pykern import pkunit

    v, t = _viewer(pkunit.empty_work_dir())
    r = v.step("Cam_SolMScan", 0, {"charge_pC": 300})
    pkunit.pkeq(300.0, t.calls[-1]["charge_pC"])
    s = {x["key"]: x for x in r["settings"] if x["key"]}
    pkunit.pkeq(
        (True, 500.0, 300.0),
        (s["charge_pC"]["edited"], s["charge_pC"]["logged"], s["charge_pC"]["twin"]),
    )
    c = {x["name"]: x for x in r["numbers"]}["charge"]
    # the twin's beam is the edited charge, against the logged one
    pkunit.pkeq((500.0, 300.0), (c["measured"], c["twin"]))


def test_edits_refused():
    from pykern import pkunit

    v = _viewer(pkunit.empty_work_dir())[0]
    for edits, err in (
        ({"EMQ1": 1.0}, "not editable"),
        # the twin's variables, not the elements
        ({"SolM": 1.0}, "not editable"),
        ({"Gun_P_actual": -1.0}, "must not be negative"),
        ({"charge_pC": 0}, "must be positive"),
        ({"source.energy_mev": 1.0}, "not editable"),
        ({"SolM_current": float("nan")}, "finite number"),
        ({"SolM_current": True}, "finite number"),
        ({"SolM_current": "1"}, "finite number"),
        ({"pixel_mm": 0}, "positive"),
        ([1], "must be an object"),
    ):
        with pkunit.pkexcept(err):
            v.step("Cam_SolMScan", 0, edits)
    with pkunit.pkexcept("has 2 steps"):
        v.step("Cam_SolMScan", 2, {})
    with pkunit.pkexcept("nope"):
        v.step("nope", 0, {})


def test_http():
    import http.server
    import json
    import threading
    import urllib.error
    import urllib.parse
    import urllib.request

    from pykern import pkunit

    from awa_twin_apps.twin_viewer import server

    server.VIEWER = _viewer(pkunit.empty_work_dir())[0]
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        u = f"http://127.0.0.1:{s.server_address[1]}"

        def _get(path):
            try:
                with urllib.request.urlopen(u + path) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                b = e.read()
                return e.code, json.loads(b) if b.startswith(b"{") else b.decode()

        c, d = _get("/api/datasets")
        pkunit.pkeq(200, c)
        pkunit.pkeq(2, len(d["datasets"]))
        c, r = _get("/api/step?scan=Cam_SolMScan&step=1")
        pkunit.pkeq(200, c)
        pkunit.pkeq(200.0, r["value"])
        e = urllib.parse.quote(json.dumps({"EMQ1": 1}))
        c, r = _get(f"/api/step?scan=Cam_SolMScan&step=1&edits={e}")
        pkunit.pkeq(400, c)
        pkunit.pkre("not editable", r["error"])
        e = urllib.parse.quote(json.dumps({"Gun_phid": 5, "L1_P_actual": 1.2}))
        c, r = _get(f"/api/step?scan=Cam_SolMScan&step=1&edits={e}")
        pkunit.pkeq(200, c)
        pkunit.pkeq({"Gun_phid": 5.0, "L1_P_actual": 1.2}, r["edits"])
        c, r = _get("/api/step?scan=Cam_SolMScan&step=9")
        pkunit.pkeq(400, c)
        # the page, and no way out of the static directory
        with urllib.request.urlopen(u + "/") as r:
            pkunit.pkeq(200, r.status)
            pkunit.pkre("text/html", r.headers["Content-Type"])
            pkunit.pkre("AWA twin viewer", r.read().decode())
        with urllib.request.urlopen(u + "/app.js") as r:
            pkunit.pkre("javascript", r.headers["Content-Type"])
        pkunit.pkeq(404, _get("/../server.py")[0])
        pkunit.pkeq(404, _get("/nope.html")[0])
    finally:
        s.shutdown()
        server.VIEWER = None


class _Twin:
    """A stub twin: a round beam whose rms size [mm] is 1 + SolM / 100, and a record of its runs."""

    n_particles = 2000

    def __init__(self):
        self.calls = []

    def elements(self):
        return [
            {"name": "SolBF", "kind": "solenoid", "z_m": -0.5, "width_m": 0.15},
            {"name": "YAG1", "kind": "screen", "z_m": 2.9, "width_m": 0.05},
        ]

    def defaults(self):
        """Nominal values: the currents as the twin builds them, the cavities' power 1, no
        phase offset and no kicks."""
        from awa_twin_apps import twin

        nominal = {"SolBF": 550.0, "SolM": 440.0, "SolL1": 1.0, "SolL2": 1.0}
        return {
            k: 1000.0
            if k == twin.CHARGE_KNOB
            else nominal[k.split("_")[0]]
            if k.endswith("_current")
            else float(k.endswith("P_actual"))
            for k in twin.KNOBS
        }

    def run(self, values):
        import numpy

        from awa_twin_apps import twin

        self.calls.append(dict(values))
        s = 1.0 + values["SolM_current"] / 100.0
        rng = numpy.random.default_rng(3)
        return twin.Beam(
            x_mm=rng.normal(0, s, 20000),
            y_mm=rng.normal(0, s, 20000),
            charge_pc=values.get("charge_pC", 1000.0),
        )


def _viewer(root):
    """A `Viewer` of synthetic scans (`_write_data`) with a stub twin, and the twin."""
    from awa_twin_apps.twin_viewer import server

    t = _Twin()
    return server.Viewer(_write_data(root), t, background=False), t


def _write_data(root):
    """`Cam_SolMScan` at 100 and 200 A (scanning DS3), and `Cam_Sol4Scan` at 70 A (scanning DS5).
    Each step's processed image is a 60 x 80 gaussian of sigma 6 (x) and 9 (y) pixels, at 0.1
    mm."""
    import h5py
    import numpy

    d = root.join("data")
    d.ensure(dir=True)
    y, x = numpy.mgrid[0:80, 0:60]
    processed = 1000 * numpy.exp(
        -((x - 29.5) ** 2 / 2 / 6**2 + (y - 39.5) ** 2 / 2 / 9**2)
    )

    def _file(name, ds3, ds5):
        with h5py.File(str(d.join(name)), "w") as f:
            f["images"] = numpy.zeros((2, 8, 8), dtype="uint16")
            f["processed_image"] = processed.astype("float32")
            for k, v in (
                ("AWA:Drive:DS1:RB", 552.0),
                ("AWA:Drive:DS3:RB", ds3),
                ("AWA:Drive:DS5:RB", ds5),
                ("AWAVXI11ICT:Ch1", 5e-10),
                ("LLRF:K1:Amp:SetPoint", 4.2),
            ):
                f[k] = numpy.full(2, v)
            f["images"].attrs["roi"] = (
                "{'xcenter': 4, 'ycenter': 4, 'xwidth': 8, 'ywidth': 8}"
            )
            f["images"].attrs["resolution"] = numpy.float64(0.1)

    _file("Cam_SolMScan_sol_100_10.h5", 100.0, 1.5)
    _file("Cam_SolMScan_sol_200_20.h5", 200.0, 1.5)
    _file("Cam_Sol4Scan_sol_70_30.h5", 250.0, 70.0)
    return d
