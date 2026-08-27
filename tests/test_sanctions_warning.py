from datetime import datetime, timedelta, timezone

import pipeline.sanctions_warning_model as model


NOW = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)


def release(days, title="Treasury Targets Network", action="Sanctions List Update"):
    return {"date": (NOW - timedelta(days=days)).date().isoformat(), "title": title, "action_title": action}


def market(score=20):
    return {
        "id": "energy_market_dislocation", "label": "Energy", "available": True,
        "score": score, "indicators": [], "series_available": 2, "retained": False,
    }


def test_contract_and_weights(monkeypatch):
    monkeypatch.setattr(model, "_energy_market_component", lambda _now: market())
    warning = model.build_sanctions_warning(
        {"entries": [{"id": "1"}], "count": 1},
        {"releases": [release(1)]}, now=NOW,
    )
    assert warning["classification"] == "sanctions-expansion-pressure-not-designation-probability"
    assert warning["horizon"] == "0-30 days"
    assert model.WEIGHTS == {
        "ofac_action_velocity": 0.35, "sdn_delta_breadth": 0.20,
        "official_posture_shift": 0.25, "energy_market_dislocation": 0.20,
    }


def test_exact_sdn_delta():
    current = {"entries": [{"id": "2", "program": "IRAN", "type": "Entity"}, {"id": "3", "program": "RUSSIA", "type": "Individual"}], "count": 2}
    previous = {"entries": [{"id": "1"}, {"id": "2"}], "count": 2}
    result = model._sdn_delta_component(current, previous)
    assert result["added_count"] == 1
    assert result["removed_count"] == 1
    assert result["added"][0]["id"] == "3"


def test_first_snapshot_renormalizes(monkeypatch):
    monkeypatch.setattr(model, "_energy_market_component", lambda _now: market(60))
    warning = model.build_sanctions_warning(
        {"entries": [{"id": "1"}], "count": 1}, {"releases": [release(1)]}, now=NOW,
    )
    delta = next(row for row in warning["components"] if row["id"] == "sdn_delta_breadth")
    assert delta["available"] is False
    assert warning["data_health"]["available_components"] == 3


def test_action_velocity_detects_current_cluster():
    press = [release(day, action="SDN List Update") for day in (0, 1, 2, 3, 4, 5)]
    press += [release(day, action="SDN List Update") for day in (15, 30, 45, 60, 75, 90)]
    component = model._action_component(press, NOW)
    assert component["available"]
    assert component["score"] >= 35


def test_concurrence_requires_official_and_market(monkeypatch):
    monkeypatch.setattr(model, "_energy_market_component", lambda _now: market(80))
    releases = [release(day, title="Treasury Intensifies Maximum Pressure", action="SDN List Update") for day in range(6)]
    warning = model.build_sanctions_warning({"entries": [{"id": "1"}], "count": 1}, {"releases": releases}, now=NOW)
    assert warning["concurrence"]["active"] is True
    assert warning["concurrence"]["score_bonus"] == 5


def test_history_is_bounded_and_same_hour_replaced(monkeypatch):
    monkeypatch.setattr(model, "_energy_market_component", lambda _now: market())
    old = [{"timestamp": (NOW - timedelta(hours=200-index)).isoformat(), "score": index} for index in range(200)]
    old.append({"timestamp": (NOW - timedelta(minutes=20)).isoformat(), "score": 99})
    warning = model.build_sanctions_warning({}, {"releases": [release(1)]}, previous_warning={"history": old}, now=NOW)
    assert len(warning["history"]) <= 180
    assert warning["history"][-1]["timestamp"] == NOW.isoformat()
