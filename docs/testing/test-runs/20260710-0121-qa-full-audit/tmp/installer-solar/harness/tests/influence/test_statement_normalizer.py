"""Normalizer: language, entities, quality-flag derivation."""
from lib.influence.models import Author, QualityFlags, Statement
from lib.influence.statement_normalizer import (
    ENTITIES_SOURCE_RULE,
    detect_language,
    extract_entities,
    normalize,
)


def _stmt(text, **kw):
    return Statement(statement_id="s1", source="x_backend", text=text,
                     author=Author("x", "@u", "U"), **kw)


def test_detect_language_en():
    assert detect_language("plain english sentence about models") == "en"


def test_detect_language_non_en():
    assert detect_language("这是一段关于大模型的中文观点表述很长很长很长") == "non-en"


def test_extract_entities_known_and_capitalized():
    ents = extract_entities("GPT-5 capability jump and scaling law predictions")
    assert "scaling law" in ents
    assert "GPT-5" in ents


def test_normalize_sets_entities_source():
    stmt = normalize(_stmt("GPT-5 capability jump and scaling law are key signals"))
    assert stmt.language == "en"
    assert stmt.entities_source == ENTITIES_SOURCE_RULE
    assert stmt.entities


def test_normalize_marketing_flag():
    stmt = normalize(_stmt("Sign up now for a discount, link in bio!"))
    assert stmt.quality_flags.is_marketing


def test_normalize_preserves_existing_entities():
    stmt = normalize(_stmt("anything", entities=["preset"]))
    assert stmt.entities == ["preset"]
    assert stmt.entities_source == ENTITIES_SOURCE_RULE
