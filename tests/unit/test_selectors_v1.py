"""T079/T080 — seletores v1 constants match documented contract (Níveis A/B/C)."""

from amayama_scraper.parsing import selectors


def test_all_documented_selectors_present():
    expected = {
        "market_index_container": ".epcVariations",
        "market_index_row": ".epcVariations__row",
        "market_index_grade": "span.info-hint-new",
        "spec_nav_details": ".epcVariation__details",
        "spec_nav_category_nav": ".epcVariation__schemaGroups",
        "spec_nav_category_link": "a.epcVariation__schemaGroup",
        "spec_nav_groups_container": ".epcVariation__schemas",
        "spec_nav_group_card": ".epcVariation__schema[data-id]",
        "spec_nav_group_name_link": ".epcVariation__schema-name a[href]",
        "variation_details": ".epcVariation__details",
        "schemas_container": ".epcSchema__schemas",
        "schema": ".epcSchema__schema[data-id]",
        "image_description": ".img__description",
        "image": ".imgMap img[src]",
        "entries_table": ".entriesTable",
        "pnc_row": "tr[data-key]",
        "group_header": ".entriesPncTable__groupHeader",
        "oem_number": ".entriesTable__number",
        "description": ".entriesTable__description",
        "nested_description": ".entriesPncDescriptionTable",
        "period": ".entriesTable__period",
        "quantity": ".entriesTable__required",
    }
    assert expected == selectors.ALL_SELECTORS
