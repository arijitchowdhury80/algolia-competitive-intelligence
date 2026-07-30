"""File export helpers for canonical Argus intelligence packets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cios.dashboard.packet_consumers import (
    build_dashboard_state_from_packet,
    build_latest_json_from_packet,
    build_public_status_from_packet,
)
from cios.dashboard.publisher import to_json_dict

from .argus_packet import ArgusIntelligencePacket


@dataclass(frozen=True)
class ArgusPacketBundle:
    run_id: str
    packet_id: str
    packet_path: Path
    latest_path: Path
    dashboard_state_path: Path
    public_status_path: Path
    delivery_plan_path: Path


def write_argus_packet_bundle(packet: ArgusIntelligencePacket, out_dir: str | Path) -> ArgusPacketBundle:
    """Write the packet and first consumer views using one run identity."""

    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)

    packet_path = root / "argus-intelligence-packet.json"
    latest_path = root / "argus-latest-packet.json"
    dashboard_state_path = root / "argus-packet-dashboard-state.json"
    public_status_path = root / "argus-packet-public-status.json"
    delivery_plan_path = root / "argus-packet-delivery-plan.json"

    _write_json(packet_path, _with_identity(packet, {"packet": packet.model_dump(mode="json")}))
    _write_json(latest_path, _with_identity(packet, build_latest_json_from_packet(packet)))
    _write_json(
        dashboard_state_path,
        _with_identity(packet, to_json_dict(build_dashboard_state_from_packet(packet))),
    )
    _write_json(public_status_path, _with_identity(packet, build_public_status_from_packet(packet)))
    _write_json(delivery_plan_path, _delivery_plan(packet))

    return ArgusPacketBundle(
        run_id=packet.run.run_id,
        packet_id=packet.packet_id,
        packet_path=packet_path,
        latest_path=latest_path,
        dashboard_state_path=dashboard_state_path,
        public_status_path=public_status_path,
        delivery_plan_path=delivery_plan_path,
    )


def _with_identity(packet: ArgusIntelligencePacket, payload: dict[str, Any]) -> dict[str, Any]:
    return {"packet_id": packet.packet_id, "run_id": packet.run.run_id, **payload}


def _delivery_plan(packet: ArgusIntelligencePacket) -> dict[str, Any]:
    return _with_identity(packet, packet.consumer_state.model_dump(mode="json"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


__all__ = ["ArgusPacketBundle", "write_argus_packet_bundle"]
