import pytest

from dualuse.extract import Extraction, classify_with_rules, fields_to_tier, handoff_summary, keyword_tier
from dualuse.triage import Tier


def extraction(**overrides) -> Extraction:
    fields = dict(
        situation="Caller's house is filling with smoke",
        need="Someone to get them out",
        location="4210 Lake Ave, Altadena",
        life_threat_now=False,
        needs_person_soon=False,
        enough_information=True,
        evidence=[],
        missing=[],
        language="English",
    )
    fields.update(overrides)
    return Extraction(**fields)


def test_life_threat_is_immediate_even_with_little_information():
    assert fields_to_tier(extraction(life_threat_now=True, enough_information=False)) is Tier.IMMEDIATE


def test_urgent_but_not_life_threatening_is_priority():
    assert fields_to_tier(extraction(needs_person_soon=True)) is Tier.PRIORITY


def test_not_enough_information_is_unknown():
    assert fields_to_tier(extraction(enough_information=False)) is Tier.UNKNOWN


def test_enough_information_and_no_risk_is_normal():
    assert fields_to_tier(extraction()) is Tier.NORMAL


@pytest.mark.parametrize(
    "text, tier",
    [
        ("my house is on fire and my kid is inside", Tier.IMMEDIATE),
        ("He is not breathing and I can't get him out", Tier.IMMEDIATE),
        ("we evacuated and have nowhere to sleep tonight", Tier.PRIORITY),
        ("my mother's oxygen tank runs out in two hours and the power is off", Tier.PRIORITY),
        ("is the 210 freeway open towards Pasadena", Tier.NORMAL),
        ("I want to ask about FEMA assistance for my damaged roof", Tier.NORMAL),
        ("help", Tier.UNKNOWN),
        ("", Tier.UNKNOWN),
    ],
)
def test_keyword_tier_baseline(text, tier):
    assert keyword_tier(text) is tier


def test_rules_classification_agrees_with_keyword_tier_and_quotes_the_match():
    result = classify_with_rules("my house is on fire and my kid is inside")
    assert result.tier is Tier.IMMEDIATE
    assert result.source == "rules"
    assert fields_to_tier(result.extraction) is Tier.IMMEDIATE
    assert any("fire" in quote for quote in result.extraction.evidence)


def test_rules_classification_marks_a_short_utterance_as_missing_information():
    result = classify_with_rules("help")
    assert result.tier is Tier.UNKNOWN
    assert result.extraction.enough_information is False
    assert result.extraction.missing


def test_handoff_summary_lists_the_fields_an_operator_needs():
    summary = handoff_summary(
        extraction(life_threat_now=True, evidence=["my kid is inside"], missing=["how many people"]),
        Tier.IMMEDIATE,
        waited_s=125,
    )
    assert "IMMEDIATE" in summary
    assert "2 min" in summary
    assert "Caller's house is filling with smoke" in summary
    assert "Someone to get them out" in summary
    assert "4210 Lake Ave, Altadena" in summary
    assert "my kid is inside" in summary
    assert "how many people" in summary


def test_handoff_summary_says_when_the_location_is_not_confirmed():
    assert "not confirmed" in handoff_summary(extraction(location=None), Tier.NORMAL, waited_s=30)
