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
