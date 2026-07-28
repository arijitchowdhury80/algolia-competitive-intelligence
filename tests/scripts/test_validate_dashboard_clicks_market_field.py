from scripts import validate_dashboard_clicks as validator


def test_market_field_selector_contract_names_required_sections() -> None:
    assert "#market-field" in validator.MARKET_FIELD_REQUIRED_SELECTORS
    assert "#selected-movement" in validator.MARKET_FIELD_REQUIRED_SELECTORS
    assert "#action-layer" in validator.MARKET_FIELD_REQUIRED_SELECTORS
    assert "#proof-drawer" in validator.MARKET_FIELD_REQUIRED_SELECTORS
    assert "#evidence-lab" in validator.MARKET_FIELD_REQUIRED_SELECTORS
    assert "#admin" in validator.MARKET_FIELD_REQUIRED_SELECTORS
