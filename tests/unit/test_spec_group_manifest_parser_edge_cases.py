"""T077 — parse_spec_group_manifest() defensive/error paths."""

from amayama_scraper.parsing.spec_group_manifest import parse_spec_group_manifest

_NAV = """
<div class="epcVariation__schemaGroups">
  <a class="epcVariation__schemaGroup active" data-id="" href="https://x#">All</a>
  <a class="epcVariation__schemaGroup" data-id="4" href="https://x/front-axle-steering">
    Front axle
  </a>
</div>
"""


def _wrap(*, nav: str = _NAV, cards: str = "") -> str:
    return f"""
    <html><body>
      <div class="epcVariation__details">
        <div class="epcVariation__filters">{nav}</div>
        <div class="epcVariation__schemas">{cards}</div>
      </div>
    </body></html>
    """


def test_missing_root_marker_is_critical_error():
    html = "<html><body><div>nothing here</div></body></html>"
    result = parse_spec_group_manifest(html, spec_key="s", source_capture_id="cap")
    assert result.critical_error is not None
    assert result.manifest is None


def test_missing_category_nav_is_critical_error():
    html = """
    <html><body>
      <div class="epcVariation__details">
        <div class="epcVariation__schemas"></div>
      </div>
    </body></html>
    """
    result = parse_spec_group_manifest(html, spec_key="s", source_capture_id="cap")
    assert result.critical_error is not None
    assert result.manifest is None


def test_missing_groups_container_is_critical_error():
    html = f"""
    <html><body>
      <div class="epcVariation__details">
        <div class="epcVariation__filters">{_NAV}</div>
      </div>
    </body></html>
    """
    result = parse_spec_group_manifest(html, spec_key="s", source_capture_id="cap")
    assert result.critical_error is not None
    assert result.manifest is None


def test_category_link_without_href_is_ignored_not_a_crash():
    nav = """
    <div class="epcVariation__schemaGroups">
      <a class="epcVariation__schemaGroup" data-id="4">Front axle (no href)</a>
    </div>
    """
    html = _wrap(nav=nav, cards="")
    result = parse_spec_group_manifest(html, spec_key="s", source_capture_id="cap")
    assert result.critical_error is None
    assert result.manifest is not None
    assert result.manifest.categories == ()


def test_card_missing_data_id_is_a_parse_error_not_critical():
    # data-id="" (present but empty) is used here, not an absent attribute —
    # SPEC_NAV_GROUP_CARD (".epcVariation__schema[data-id]") only selects cards
    # where the attribute is present at all, matching real markup where a
    # malformed card still carries the attribute with an empty value.
    cards = """
    <div class="epcVariation__schema" data-id="">
      <div class="epcVariation__schema-name">
        <a href="https://x/front-axle-steering/407">407</a>
      </div>
    </div>
    """
    html = _wrap(cards=cards)
    result = parse_spec_group_manifest(html, spec_key="s", source_capture_id="cap")
    assert result.critical_error is None
    assert result.manifest is not None
    assert result.manifest.categories == ()
    assert len(result.parse_errors) == 1


def test_card_missing_name_link_href_is_a_parse_error_not_critical():
    cards = """
    <div class="epcVariation__schema" data-id="407">
      <div class="epcVariation__schema-name"></div>
    </div>
    """
    html = _wrap(cards=cards)
    result = parse_spec_group_manifest(html, spec_key="s", source_capture_id="cap")
    assert result.critical_error is None
    assert result.manifest is not None
    assert result.manifest.categories == ()
    assert len(result.parse_errors) == 1


def test_card_href_without_two_segments_is_critical_error():
    cards = """
    <div class="epcVariation__schema" data-id="407">
      <div class="epcVariation__schema-name"><a href="https://x/407">407</a></div>
    </div>
    """
    html = _wrap(cards=cards)
    result = parse_spec_group_manifest(html, spec_key="s", source_capture_id="cap")
    assert result.critical_error is not None
    assert result.manifest is None


def test_card_category_slug_not_declared_in_nav_is_critical_error():
    cards = """
    <div class="epcVariation__schema" data-id="1">
      <div class="epcVariation__schema-name">
        <a href="https://x/some-undeclared-category/1">1</a>
      </div>
    </div>
    """
    html = _wrap(cards=cards)
    result = parse_spec_group_manifest(html, spec_key="s", source_capture_id="cap")
    assert result.critical_error is not None
    assert result.manifest is None
