"""Offline tests: each adapter is fed realistic canned responses (shapes documented by the
community clients we follow) through a fake HTTP session. Run:  python -m pytest -q"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import pytest

from glucopop.sources import AuthError, SourceError, create
from glucopop.sources.libre import LibreLinkUp


class FakeResp:
    """`body` is the decoded JSON (Dexcom returns bare JSON strings); raw=True means non-JSON text."""

    def __init__(self, body, status=200, headers=None, raw=False):
        self._body, self.status_code, self.headers, self._raw = body, status, headers or {}, raw
        self.text = body if raw else json.dumps(body)

    def json(self):
        if self._raw:
            raise ValueError("not json")
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code}")


class FakeSession:
    """Routes by (method, path-substring). Records calls."""

    def __init__(self, routes):
        self.routes, self.calls, self.headers, self.cookies = routes, [], {}, {}

    def _dispatch(self, method, url, **kw):
        self.calls.append((method, url, kw))
        for (m, frag), resp in self.routes.items():
            if m == method and frag in url:
                return resp() if callable(resp) else resp
        raise AssertionError(f"unexpected {method} {url}")

    def post(self, url, **kw):
        return self._dispatch("POST", url, **kw)

    def get(self, url, **kw):
        return self._dispatch("GET", url, **kw)

    def request(self, method, url, **kw):
        return self._dispatch(method.upper(), url, **kw)


NOW_MS = int(time.time() * 1000) - 120_000  # 2 min ago


# ----------------------------------------------------------------------------- Dexcom
def test_dexcom_happy_path():
    src = create("dexcom", {"username": "u@x.com", "password": "p", "region": "ous"})
    src.session = FakeSession({
        ("POST", "AuthenticatePublisherAccount"): FakeResp("acc-123"),
        ("POST", "LoginPublisherAccountById"): FakeResp("sess-456"),
        ("POST", "ReadPublisherLatestGlucoseValues"): FakeResp([
            {"WT": f"Date({NOW_MS})", "ST": f"Date({NOW_MS})", "DT": f"Date({NOW_MS}+0300)", "Value": 142, "Trend": "FortyFiveUp"},
            {"WT": f"Date({NOW_MS - 300000})", "Value": 135, "Trend": "Flat"},
        ]),
    })
    r = src.latest()
    assert r.mgdl == 142 and r.trend == "FortyFiveUp" and r.arrow == "↗"
    assert 100 < r.age_seconds < 200
    assert r.extra["delta"] == 7
    assert src.session.calls[-1][2]["params"]["sessionId"] == "sess-456"


def test_dexcom_bad_password_maps_to_auth_error():
    src = create("dexcom", {"username": "u", "password": "bad", "region": "ous"})
    src.session = FakeSession({
        ("POST", "AuthenticatePublisherAccount"): FakeResp({"Code": "AccountPasswordInvalid", "Message": "x"}, 500),
    })
    with pytest.raises(AuthError):
        src.latest()


def test_dexcom_session_expiry_relogins():
    state = {"n": 0}

    def read():
        state["n"] += 1
        if state["n"] == 1:
            return FakeResp({"Code": "SessionIdNotFound", "Message": ""}, 500)
        return FakeResp([{"WT": f"Date({NOW_MS})", "Value": 99, "Trend": "Flat"}])

    src = create("dexcom", {"username": "u", "password": "p", "region": "ous"})
    src.session = FakeSession({
        ("POST", "AuthenticatePublisherAccount"): FakeResp("acc"),
        ("POST", "LoginPublisherAccountById"): FakeResp("sess"),
        ("POST", "ReadPublisherLatestGlucoseValues"): read,
    })
    assert src.latest().mgdl == 99
    assert state["n"] == 2


# ----------------------------------------------------------------------------- Libre
def _llu_ts(dt: datetime) -> str:
    return dt.strftime("%m/%d/%Y %I:%M:%S %p").lstrip("0").replace("/0", "/")


def test_libre_happy_path_with_region_redirect():
    factory = datetime.now(timezone.utc)
    conn = {"patientId": "pid-1", "firstName": "Ayşe", "lastName": "Y",
            "glucoseMeasurement": {"Value": 6.7, "ValueInMgPerDl": 121, "TrendArrow": 3,
                                   "Timestamp": _llu_ts(factory), "FactoryTimestamp": _llu_ts(factory),
                                   "isHigh": False, "isLow": False},
            "sensor": {"sn": "ABC123"}}
    logins = {"n": 0}

    def login():
        logins["n"] += 1
        if logins["n"] == 1:
            return FakeResp({"status": 0, "data": {"redirect": True, "region": "eu2"}})
        return FakeResp({"status": 0, "data": {"authTicket": {"token": "tok"}, "user": {"id": "user-uuid"}}})

    src = create("libre", {"username": "u@x.com", "password": "p"})
    src.session = FakeSession({
        ("POST", "/llu/auth/login"): login,
        ("GET", "/llu/connections"): FakeResp({"status": 0, "data": [conn]}),
    })
    r = src.latest()
    assert src.base == "https://api-eu2.libreview.io"
    assert r.mgdl == 121 and r.trend == "Flat" and r.person == "Ayşe Y"
    assert r.age_seconds < 120
    hdrs = src.session.calls[-1][2]["headers"]
    assert hdrs["authorization"] == "Bearer tok" and len(hdrs["account-id"]) == 64


def test_libre_terms_step_is_reported():
    src = create("libre", {"username": "u", "password": "p"})
    src.session = FakeSession({("POST", "/llu/auth/login"): FakeResp({"status": 4, "data": {"step": {"type": "tou"}}})})
    with pytest.raises(AuthError, match="llu_terms"):
        src.latest()


def test_libre_no_connections():
    src = create("libre", {"username": "u", "password": "p"})
    src.session = FakeSession({
        ("POST", "/llu/auth/login"): FakeResp({"status": 0, "data": {"authTicket": {"token": "t"}, "user": {"id": "i"}}}),
        ("GET", "/llu/connections"): FakeResp({"status": 0, "data": []}),
    })
    with pytest.raises(SourceError, match="libre_no_connection"):
        src.latest()


def test_libre_version_header_present():
    src = LibreLinkUp({"username": "u", "password": "p"})
    assert src.session.headers["product"] == "llu.android" and src.session.headers["version"]


# ----------------------------------------------------------------------------- Medtrum
def test_medtrum_patient_mode():
    ss = {"glucose": 7.2, "glucoseRate": 4, "updateTime": time.time() - 200, "status": 3, "batteryPercent": 80}
    src = create("medtrum", {"account_type": "patient", "username": "u", "password": "p",
                             "server": "https://easyview.medtrum.eu"})
    src.session = FakeSession({
        ("POST", "/v3/api/v2.0/login"): FakeResp({"error": 0, "uid": 12345, "realname": "Emre"}),
        ("GET", "/api/v2.1/monitor/12345/status"): FakeResp({"error": 0, "data": {"sensor_status": ss}}),
    })
    r = src.latest()
    assert r.mgdl == pytest.approx(129.6) and r.value_text("mg/dL") == "130"
    assert r.trend == "FortyFiveDown" and r.person == "Emre"


def test_medtrum_follow_mode_picks_named_user():
    ss = {"glucose": 4.0, "glucoseRate": 0, "updateTime": time.time() - 60, "status": 3}
    src = create("medtrum", {"account_type": "follow", "username": "f", "password": "p",
                             "server": "https://easyview.medtrum.eu", "follow_user": "kid2"})
    src.session = FakeSession({
        ("POST", "/mobile/ajax/login"): FakeResp({"res": "OK"}),
        ("GET", "/mobile/ajax/logindata"): FakeResp({"monitorlist": [
            {"username": "kid1", "sensor_status": {**ss, "glucose": 9.9}},
            {"username": "kid2", "sensor_status": ss}]}),
    })
    r = src.latest()
    assert r.mgdl == 72 and r.person == "kid2"


def test_medtrum_wrong_password():
    src = create("medtrum", {"account_type": "patient", "username": "u", "password": "p"})
    src.session = FakeSession({("POST", "/v3/api/v2.0/login"): FakeResp({"error": 1, "msg": "password error"})})
    with pytest.raises(AuthError):
        src.latest()


# ----------------------------------------------------------------------------- Nightscout
def test_nightscout_with_api_secret_and_delta():
    src = create("nightscout", {"url": "myns.example.com", "secret": "mysecret123"})
    assert src.url.startswith("https://") and "api-secret" in src.session.headers
    src.session = FakeSession({("GET", "/api/v1/entries/sgv.json"): FakeResp([
        {"sgv": 88, "direction": "SingleDown", "date": NOW_MS, "device": "xDrip-LibreReceiver"},
        {"sgv": 95, "direction": "Flat", "date": NOW_MS - 300000},
    ])})
    r = src.latest()
    assert r.mgdl == 88 and r.trend == "SingleDown" and r.extra["delta"] == -7
    assert r.extra["device"].startswith("xDrip")


def test_nightscout_token_goes_to_query():
    src = create("nightscout", {"url": "https://x.y", "secret": "widget-1a2b3c4d5e6f"})
    assert src._params()["token"] == "widget-1a2b3c4d5e6f" and "api-secret" not in src.session.headers


def test_nightscout_unauthorized():
    src = create("nightscout", {"url": "https://x.y"})
    src.session = FakeSession({("GET", "/api/v1/entries/sgv.json"): FakeResp("Unauthorized", 401, raw=True)})
    with pytest.raises(AuthError):
        src.latest()
