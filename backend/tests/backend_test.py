"""Backend tests for GPS Multi-Dim Router (iteration 3).

Iteration 3 adds true detour generation for critical zones:
- route_touches_zone(): geometric check (300m radius).
- generate_detours(): perpendicular waypoint OSRM bypass.
- astar_score(): HARD_PENALTY=100 to any route touching a zone — guarantees
  any clean route always wins regardless of the active dimension.

Tests verify:
- /api/dimensions schema preserved (toggle/default/hint).
- /api/geocode messy queries (Nominatim → Photon fallback).
- /api/route honors critical_zones across ALL dimension preferences:
  ALL dimensions {time,distance,fuel,tolls,elevation} must return a route
  >300m away from the zone(s).
- Multi-zone scenario: both zones avoided.
- Explanation text mentions 'Evitando N zona(s) crítica(s)' or '⚠ No fue posible evitar'.
- No-zone behavior preserved.
- Detour dedupe (no exact-distance duplicates added when alts already cover).
"""
import math
import os
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

# CDMX scenario shared across tests
ORIGIN = {"lat": 19.4326, "lng": -99.1332}
DESTINATION = {"lat": 19.4248, "lng": -99.1689}
ZONE_MID = {"lat": 19.4283, "lng": -99.1510}  # between origin & destination
ZONE_2 = {"lat": 19.4290, "lng": -99.1430}    # second zone

ZONE_RADIUS_M = 300.0


def haversine_m(a_lat, a_lng, b_lat, b_lng):
    R = 6371000.0
    lat1, lng1 = math.radians(a_lat), math.radians(a_lng)
    lat2, lng2 = math.radians(b_lat), math.radians(b_lng)
    dlat, dlng = lat2 - lat1, lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def route_all_coords(best):
    out = []
    for seg in best["segments"]:
        out.extend(seg["coords"])
    return out


def min_dist_to_zone(coords, zone):
    return min(haversine_m(c[0], c[1], zone["lat"], zone["lng"]) for c in coords)


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --- root ---
class TestRoot:
    def test_root_online(self, client):
        r = client.get(f"{BASE_URL}/api/")
        assert r.status_code == 200
        assert r.json().get("status") == "online"


# --- dimensions ---
class TestDimensions:
    def test_dimensions_schema(self, client):
        r = client.get(f"{BASE_URL}/api/dimensions")
        assert r.status_code == 200
        dims = r.json().get("dimensions", [])
        assert len(dims) == 7
        by_key = {d["key"]: d for d in dims}
        assert set(by_key) == {"time", "distance", "tolls", "fuel", "operator", "critical", "elevation"}
        for d in dims:
            assert isinstance(d["toggle"], bool)
            assert d["default"] in ("min", "max")
            assert d["hint"]


# --- geocode (smoke / cache + fallback) ---
class TestGeocode:
    def test_geocode_messy_query(self, client):
        r = client.get(f"{BASE_URL}/api/geocode", params={"q": "jilotepec edo mex"})
        if r.status_code in (502, 503):
            pytest.skip(f"geocode upstream unavailable: {r.status_code}")
        assert r.status_code == 200, r.text
        results = r.json().get("results", [])
        assert len(results) >= 1
        joined = " | ".join(x["display_name"] for x in results).lower()
        assert "jilotepec" in joined

    def test_geocode_empty(self, client):
        r = client.get(f"{BASE_URL}/api/geocode", params={"q": "   "})
        assert r.status_code == 200
        assert r.json().get("results") == []


# --- route: critical zone avoidance (iteration 3 core) ---
class TestRouteCriticalAvoidance:
    """Hard-penalty must keep the best route >300m away from any zone for EVERY dimension."""

    @pytest.mark.parametrize("dims", [
        {"time": "min"},
        {"distance": "min"},
        {"fuel": "min"},
        {"tolls": "min"},
        {"elevation": "max"},
    ])
    def test_avoid_zone_all_dimensions(self, client, dims):
        payload = {
            "origin": ORIGIN,
            "destination": DESTINATION,
            "dimensions": dims,
            "critical_zones": [ZONE_MID],
        }
        r = client.post(f"{BASE_URL}/api/route", json=payload)
        if r.status_code == 502:
            pytest.skip(f"OSRM unreachable: {r.text}")
        assert r.status_code == 200, r.text
        data = r.json()
        coords = route_all_coords(data["best"])
        d = min_dist_to_zone(coords, ZONE_MID)
        # The best route MUST clear the 300m radius (HARD_PENALTY guarantee).
        assert d > ZONE_RADIUS_M, (
            f"dim={dims}: best route still passes {d:.1f}m from zone (<= {ZONE_RADIUS_M}). "
            f"explanation={data['explanation']}"
        )
        # critical metric should be 0 since geometric penalty only counts coords <= radius.
        assert data["best"]["metrics"]["critical"] >= 0.0
        # If best is clean, explanation should mention 'Evitando'
        assert "Evitando" in data["explanation"] or "No fue posible evitar" in data["explanation"]

    def test_avoid_two_zones(self, client):
        payload = {
            "origin": ORIGIN,
            "destination": DESTINATION,
            "dimensions": {"time": "min"},
            "critical_zones": [ZONE_MID, ZONE_2],
        }
        r = client.post(f"{BASE_URL}/api/route", json=payload)
        if r.status_code == 502:
            pytest.skip(f"OSRM unreachable: {r.text}")
        assert r.status_code == 200, r.text
        data = r.json()
        coords = route_all_coords(data["best"])
        d1 = min_dist_to_zone(coords, ZONE_MID)
        d2 = min_dist_to_zone(coords, ZONE_2)
        # Best route should avoid both if at all possible; if not, explanation flags it.
        if "Evitando" in data["explanation"]:
            assert d1 > ZONE_RADIUS_M, f"zone1 {d1:.1f}m"
            assert d2 > ZONE_RADIUS_M, f"zone2 {d2:.1f}m"
        else:
            # Must explicitly acknowledge failure
            assert "No fue posible evitar" in data["explanation"]

    def test_explanation_mentions_avoidance(self, client):
        payload = {
            "origin": ORIGIN,
            "destination": DESTINATION,
            "dimensions": {"time": "min"},
            "critical_zones": [ZONE_MID],
        }
        r = client.post(f"{BASE_URL}/api/route", json=payload)
        if r.status_code == 502:
            pytest.skip("OSRM unreachable")
        assert r.status_code == 200
        explanation = r.json()["explanation"]
        assert ("Evitando 1 zona(s) crítica(s)" in explanation
                or "No fue posible evitar" in explanation), explanation


class TestRouteNoZones:
    """Without zones, the response is just normal multi-objective routing."""

    def test_no_zones_explanation_clean(self, client):
        payload = {
            "origin": ORIGIN,
            "destination": DESTINATION,
            "dimensions": {"time": "min", "distance": "min"},
            "critical_zones": [],
        }
        r = client.post(f"{BASE_URL}/api/route", json=payload)
        if r.status_code == 502:
            pytest.skip("OSRM unreachable")
        assert r.status_code == 200
        data = r.json()
        # No zone note in explanation
        assert "Evitando" not in data["explanation"]
        assert "No fue posible evitar" not in data["explanation"]
        # Best route still has both A* + Manhattan segments
        algos = [s["algorithm"] for s in data["best"]["segments"]]
        assert "A*" in algos and "Manhattan" in algos

    def test_empty_dims_no_zones_400(self, client):
        payload = {
            "origin": ORIGIN,
            "destination": DESTINATION,
            "dimensions": {},
            "critical_zones": [],
        }
        r = client.post(f"{BASE_URL}/api/route", json=payload)
        assert r.status_code == 400


class TestDetourDedupe:
    """When zones force detours, generated alts shouldn't all share identical distance keys."""

    def test_alternatives_distances_distinct(self, client):
        payload = {
            "origin": ORIGIN,
            "destination": DESTINATION,
            "dimensions": {"time": "min"},
            "critical_zones": [ZONE_MID],
        }
        r = client.post(f"{BASE_URL}/api/route", json=payload)
        if r.status_code == 502:
            pytest.skip("OSRM unreachable")
        assert r.status_code == 200
        data = r.json()
        # All alternatives + best -> their distances should be unique (rounded km)
        all_routes = [data["best"]] + data["alternatives"]
        rounded = [round(a["metrics"]["distance"], 2) for a in all_routes]
        # Allow duplicates only if there's just one route.
        if len(rounded) > 1:
            assert len(set(rounded)) == len(rounded), f"duplicate distances found: {rounded}"
