from agency_lead_pipeline.clutch import parse_clutch_html


def test_parse_clutch_listing_and_next_page():
    html = """
    <div class="provider-list-item">
      <h3>North Star Studio</h3>
      <span class="location">Copenhagen, Denmark</span>
      <a href="/profile/north-star">Profile</a>
      <a data-link="https://northstar.example/?utm_source=clutch">Visit website</a>
    </div>
    <a rel="next" href="?page=2">Next</a>
    """
    records, next_url = parse_clutch_html(html, "https://clutch.co/web-developers")
    assert records[0].agency == "North Star Studio"
    assert records[0].country == "Copenhagen, Denmark"
    assert records[0].clutch_profile == "https://clutch.co/profile/north-star"
    assert records[0].website.startswith("https://northstar.example")
    assert next_url == "https://clutch.co/web-developers?page=2"

