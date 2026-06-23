from agency_lead_pipeline.email_utils import best_candidate, candidates_from_text, is_valid_email


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
