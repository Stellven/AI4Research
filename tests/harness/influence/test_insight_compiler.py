"""InsightCompiler must emit all 8 contracted asset types."""
from lib.influence.insight_compiler import ASSET_TYPES, build_assets
from lib.influence.models import InfluenceEvidencePacket


def test_all_eight_assets_emitted(sample_packet_dict):
    packet = InfluenceEvidencePacket.from_dict(sample_packet_dict)
    assets = build_assets(packet)
    assert set(assets) == set(ASSET_TYPES)
    assert len(assets) == 8


def test_each_asset_carries_identity(sample_packet_dict):
    packet = InfluenceEvidencePacket.from_dict(sample_packet_dict)
    for asset_type, asset in build_assets(packet).items():
        assert asset["asset_type"] == asset_type
        assert asset["packet_id"] == packet.packet_id
        assert asset["thesis_id"] == packet.thesis_id
        assert asset["schema_version"] == f"influence.output.{asset_type}.v1"


def test_deep_research_seed_pack_carries_coverage_gap(sample_packet_dict):
    packet = InfluenceEvidencePacket.from_dict(sample_packet_dict)
    seed = build_assets(packet)["deep_research_seed_pack"]
    assert seed["coverage_gap"] == ["hf_paper_connector_missing"]
