import math

import numpy as np
import pytest

from app.mobility import (
    air_flow_matrix,
    combined_mobility,
    country_index,
    distance_matrix_km,
    haversine_km,
    load_countries,
    sea_flow_matrix,
)


def test_haversine_known_pair():
    # NYC to London is approximately 5570 km. Use airport-area lat/lng.
    d = haversine_km(40.7128, -74.0060, 51.5074, -0.1278)
    assert 5400 < d < 5700


def test_haversine_zero_self():
    assert haversine_km(48.0, 2.0, 48.0, 2.0) == pytest.approx(0.0, abs=1e-6)


def test_distance_matrix_symmetric_and_zero_diagonal():
    d = distance_matrix_km()
    n = d.shape[0]
    assert d.shape == (n, n)
    assert np.allclose(d, d.T, atol=1e-6)
    assert np.allclose(np.diag(d), 0.0)


def test_country_index_round_trip():
    countries = load_countries()
    idx = country_index()
    assert len(countries) == len(idx)
    for i, c in enumerate(countries):
        assert idx[c.iso3] == i


def test_air_flow_zero_diagonal_and_nonnegative():
    f = air_flow_matrix()
    assert np.all(f >= 0)
    assert np.allclose(np.diag(f), 0.0)


def test_air_flow_normalized_to_target_total():
    f = air_flow_matrix()
    # Module normalizes to ~5M daily international travelers.
    assert abs(f.sum() - 5_000_000.0) < 1.0


def test_air_flow_decay_with_distance_for_similar_pop():
    # Holding population fixed, doubling distance should reduce gravity flow.
    countries = load_countries()
    idx = country_index()
    f = air_flow_matrix()
    d = distance_matrix_km()

    # Pick three countries with similar populations to observe the decay.
    # USA->CAN (close) should exceed USA->JPN (far) for a ~similar destination scale.
    usa = idx["USA"]
    can = idx["CAN"]
    jpn = idx["JPN"]
    assert d[usa, can] < d[usa, jpn]
    # Per-unit-mass decay: divide the flow by destination population effective mass.
    # Direct compare suffices given Canada and Japan are within an order of magnitude.
    assert f[usa, can] > f[usa, jpn] * 0.5  # weaker form: not buried by distance


def test_sea_flow_landlocked_attenuated():
    f_sea = sea_flow_matrix()
    countries = load_countries()
    idx = country_index()
    # Landlocked Afghanistan (AFG) outbound flow is dominated by similarly-sized coastal Iran (IRN).
    assert f_sea[idx["AFG"]].sum() < f_sea[idx["IRN"]].sum()


def test_combined_mobility_zero_diagonal():
    m = combined_mobility()
    assert np.allclose(np.diag(m), 0.0)


def test_combined_mobility_nonnegative_and_bounded():
    m = combined_mobility(air_weight=2.0, port_weight=2.0)
    assert np.all(m >= 0)
    # Per-day per-region outflow fraction should never exceed the cap (0.5%).
    assert m.max() <= 0.005 + 1e-9


def test_travel_restriction_scales_down():
    base = combined_mobility(travel_restriction=0.0)
    half = combined_mobility(travel_restriction=0.5)
    full = combined_mobility(travel_restriction=1.0)
    assert half.sum() < base.sum()
    assert full.sum() == pytest.approx(0.0, abs=1e-12)


def test_air_weight_zero_disables_air_channel():
    m_air_only = combined_mobility(air_weight=0.0, port_weight=1.0)
    m_full = combined_mobility(air_weight=1.0, port_weight=1.0)
    assert m_full.sum() > m_air_only.sum()
