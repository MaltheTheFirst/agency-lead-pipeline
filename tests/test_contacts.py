from agency_lead_pipeline.contacts import parse_contact_html


def test_contact_parser_retains_candidates_and_same_domain_links():
    html = """
    <a href="mailto:hello@northstar.agency?subject=Hi">Email</a>
    <p>Sales: sales [at] northstar [dot] agency</p>
    <a href="/contact-us">Contact</a>
    <a href="https://other.example.net/contact">External contact</a>
    <script type="application/ld+json">{"email": "team@northstar.agency"}</script>
    """
    candidates, links = parse_contact_html(
        html, "https://northstar.agency", "northstar.agency"
    )
    assert {candidate.email for candidate in candidates} == {
        "hello@northstar.agency", "sales@northstar.agency", "team@northstar.agency"
    }
    assert links == ["https://northstar.agency/contact-us"]


def test_contact_parser_applies_personal_email_setting_to_every_source():
    html = """
    <a href="mailto:jane.doe@northstar.agency">Email Jane</a>
    <p>John: john.smith@northstar.agency</p>
    <script type="application/ld+json">{"email": "mary.jones@northstar.agency"}</script>
    <p>General: founder@northstar.agency</p>
    """

    default_candidates, _ = parse_contact_html(
        html, "https://northstar.agency", "northstar.agency"
    )
    opted_in_candidates, _ = parse_contact_html(
        html, "https://northstar.agency", "northstar.agency",
        allow_personal_emails=True,
    )

    assert {candidate.email for candidate in default_candidates} == {
        "founder@northstar.agency"
    }
    assert {candidate.email for candidate in opted_in_candidates} == {
        "jane.doe@northstar.agency", "john.smith@northstar.agency",
        "mary.jones@northstar.agency", "founder@northstar.agency",
    }
