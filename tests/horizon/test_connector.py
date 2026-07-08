"""Tests for DotConnector: evidence guard (both sides required, deterministic
rejection of fabricated evidence), tenant scoping, empty-input short circuit.
"""

from __future__ import annotations

from datetime import date

import pytest

from cios.brain.types import Signal
from cios.horizon.connector import DotConnector, MalformedConnectorOutput
from cios.horizon.types import Horizon, HorizonRead, IndustryTheme, ThemeConfidence

from .conftest import FakeModel


def _signal(url: str = "https://rival.com/pricing") -> Signal:
    return Signal(
        competitor_id=7,
        signal_type="pricing change",
        headline="Rival cuts entry price 20%",
        what_changed="entry tier dropped",
        recommended_action="Brief the field.",
        owner="PMM",
        team_to_involve="Sales Enablement",
        materiality_score=0.8,
        evidence_urls=[url],
    )


def _horizon_read(horizon: Horizon, url: str = "https://industry.com/trend") -> HorizonRead:
    return HorizonRead(
        tenant_id=1,
        horizon=horizon,
        as_of=date(2026, 7, 8),
        themes=[
            IndustryTheme(
                theme="price compression across the segment",
                confidence=ThemeConfidence.CONFIRMED,
                evidence_urls=[url],
            )
        ],
    )


async def test_connection_with_both_sides_evidenced_is_accepted() -> None:
    signal = _signal()
    read = _horizon_read(Horizon.D30)
    model = FakeModel(
        [
            {
                "connections": [
                    {
                        "horizon": "d30",
                        "connection": "this week's price cut fits the 30-day compression trend",
                        "signal_evidence_urls": ["https://rival.com/pricing"],
                        "horizon_evidence_urls": ["https://industry.com/trend"],
                    }
                ]
            }
        ]
    )
    connections = await DotConnector(model).connect(1, [signal], [read])
    assert len(connections) == 1
    assert connections[0].horizon is Horizon.D30
    assert connections[0].signal_evidence_urls == ["https://rival.com/pricing"]
    assert connections[0].horizon_evidence_urls == ["https://industry.com/trend"]


async def test_connection_citing_fabricated_signal_evidence_is_rejected() -> None:
    signal = _signal()
    read = _horizon_read(Horizon.D30)
    model = FakeModel(
        [
            {
                "connections": [
                    {
                        "horizon": "d30",
                        "connection": "fabricated",
                        "signal_evidence_urls": ["https://not-a-real-signal-url.com"],
                        "horizon_evidence_urls": ["https://industry.com/trend"],
                    }
                ]
            }
        ]
    )
    connections = await DotConnector(model).connect(1, [signal], [read])
    assert connections == []


async def test_connection_citing_fabricated_horizon_evidence_is_rejected() -> None:
    signal = _signal()
    read = _horizon_read(Horizon.D30)
    model = FakeModel(
        [
            {
                "connections": [
                    {
                        "horizon": "d30",
                        "connection": "fabricated",
                        "signal_evidence_urls": ["https://rival.com/pricing"],
                        "horizon_evidence_urls": ["https://not-in-any-horizon-read.com"],
                    }
                ]
            }
        ]
    )
    connections = await DotConnector(model).connect(1, [signal], [read])
    assert connections == []


async def test_connection_with_no_evidence_on_either_side_is_rejected() -> None:
    signal = _signal()
    read = _horizon_read(Horizon.D30)
    model = FakeModel(
        [
            {
                "connections": [
                    {
                        "horizon": "d30",
                        "connection": "vague",
                        "signal_evidence_urls": [],
                        "horizon_evidence_urls": [],
                    }
                ]
            }
        ]
    )
    connections = await DotConnector(model).connect(1, [signal], [read])
    assert connections == []


async def test_connection_naming_unsupplied_horizon_is_rejected() -> None:
    signal = _signal()
    read = _horizon_read(Horizon.D30)  # only D30 supplied
    model = FakeModel(
        [
            {
                "connections": [
                    {
                        "horizon": "d60",
                        "connection": "wrong horizon",
                        "signal_evidence_urls": ["https://rival.com/pricing"],
                        "horizon_evidence_urls": ["https://industry.com/trend"],
                    }
                ]
            }
        ]
    )
    connections = await DotConnector(model).connect(1, [signal], [read])
    assert connections == []


async def test_empty_signals_or_reads_short_circuits_without_model_call() -> None:
    model = FakeModel([])
    assert await DotConnector(model).connect(1, [], [_horizon_read(Horizon.D30)]) == []
    assert await DotConnector(model).connect(1, [_signal()], []) == []
    assert model.calls == []


async def test_malformed_output_twice_raises() -> None:
    signal = _signal()
    read = _horizon_read(Horizon.D30)
    model = FakeModel(["not json", "still not json"])
    with pytest.raises(MalformedConnectorOutput):
        await DotConnector(model).connect(1, [signal], [read])


async def test_result_carries_tenant_id() -> None:
    signal = _signal()
    read = _horizon_read(Horizon.D30)
    model = FakeModel(
        [
            {
                "connections": [
                    {
                        "horizon": "d30",
                        "connection": "connects",
                        "signal_evidence_urls": ["https://rival.com/pricing"],
                        "horizon_evidence_urls": ["https://industry.com/trend"],
                    }
                ]
            }
        ]
    )
    connections = await DotConnector(model).connect(42, [signal], [read])
    assert connections[0].tenant_id == 42
