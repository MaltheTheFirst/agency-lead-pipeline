import pytest

from agency_lead_pipeline.email_utils import (
    EmailClassification,
    best_candidate,
    candidates_from_text,
    classify_email,
    is_valid_email,
)


def test_extracts_plain_and_obfuscated_emails():
    candidates = candidates_from_text(
        "Email hello [at] northstar [dot] agency or sales@northstar.agency",
        "https://northstar.agency/contact",
        "text",
        "northstar.agency",
    )
    assert {item.email for item in candidates} == {
        "hello@northstar.agency", "sales@northstar.agency"
    }


def test_filters_placeholders_noreply_and_assets():
    assert not is_valid_email("person@example.com")
    assert not is_valid_email("no-reply@real-agency.com")
    assert not is_valid_email("logo@2x.png")
    assert is_valid_email("info@real-agency.com")


def test_prefers_business_inbox_on_agency_domain():
    candidates = candidates_from_text("person@other.com info@agency.com", "/", "text", "agency.com")
    assert best_candidate(candidates).email == "info@agency.com"


def test_all_role_candidates_rank_above_unknown_candidates():
    candidates = candidates_from_text(
        "founder@agency.com press@other.com", "/", "text", "agency.com"
    )
    assert best_candidate(candidates).email == "press@other.com"


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("info@agency.com", EmailClassification.ROLE),
        ("jane.doe@agency.com", EmailClassification.PERSONAL),
        ("founder@agency.com", EmailClassification.UNKNOWN),
    ],
)
def test_classifies_email_candidates(email, expected):
    assert classify_email(email) == expected


def test_personal_candidates_are_opt_in_while_unknown_candidates_remain():
    text = "jane.doe@agency.com founder@agency.com hello@agency.com"
    default_candidates = candidates_from_text(text, "/", "text", "agency.com")
    opted_in_candidates = candidates_from_text(
        text, "/", "text", "agency.com", allow_personal_emails=True
    )

    assert {item.email for item in default_candidates} == {
        "founder@agency.com", "hello@agency.com"
    }
    assert {item.email for item in opted_in_candidates} == {
        "jane.doe@agency.com", "founder@agency.com", "hello@agency.com"
    }
    assert best_candidate(opted_in_candidates).email == "hello@agency.com"
