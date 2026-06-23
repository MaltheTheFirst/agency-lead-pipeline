from agency_lead_pipeline.geography import is_european_location


def test_european_city_country_locations():
    assert is_european_location("Kraków, Poland")
    assert is_european_location("London, England")
    assert is_european_location("Cluj-Napoca, Romania")


def test_non_european_and_missing_locations():
    assert not is_european_location("New York, NY")
    assert not is_european_location("Ahmedabad, India")
    assert not is_european_location("")

