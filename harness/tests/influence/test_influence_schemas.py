"""Schema round-trip: fixtures + pipeline outputs validate against schemas/influence."""
import json
import pathlib

import jsonschema
import pytest

from lib.influence import run_pipeline
from lib.influence.insight_compiler import build_assets
from lib.influence.models import Author, InfluenceEvidencePacket, Statement

HARNESS_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_DIR = HARNESS_ROOT / "schemas" / "influence"
FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _schema(name):
    return json.loads((SCHEMA_DIR / name).read_text())


def test_statement_fixture_validates():
    jsonschema.validate(json.loads((FIXTURES / "sample_statement.json").read_text()),
                        _schema("statement.schema.json"))


def test_thesis_fixture_validates():
    jsonschema.validate(json.loads((FIXTURES / "sample_thesis.json").read_text()),
                        _schema("thesis.schema.json"))


def test_evidence_packet_fixture_validates():
    jsonschema.validate(json.loads((FIXTURES / "sample_evidence_packet.json").read_text()),
                        _schema("influence_evidence_packet.schema.json"))


def test_pipeline_packet_validates_against_schema():
    stmts = [Statement(statement_id="s1", source="x_backend",
                       text="GPT-5 will exceed the conservative scaling-law forecasts of 2024.",
                       author=Author("x", "@a", "A"), entities=["GPT-5"])]
    result = run_pipeline(stmts)
    schema = _schema("influence_evidence_packet.schema.json")
    assert result["packets"]
    for packet in result["packets"]:
        jsonschema.validate(packet, schema)


def test_all_output_assets_validate():
    packet = InfluenceEvidencePacket.from_dict(
        json.loads((FIXTURES / "sample_evidence_packet.json").read_text()))
    for asset_type, asset in build_assets(packet).items():
        schema = _schema(f"output_assets/{asset_type}.schema.json")
        jsonschema.validate(asset, schema)
