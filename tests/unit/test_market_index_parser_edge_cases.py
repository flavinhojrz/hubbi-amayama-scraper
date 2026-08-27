"""T074 — parse_market_spec_index() defensive/error paths (row-level, not container-level)."""

from amayama_scraper.parsing.market_index import parse_market_spec_index

_BREADCRUMB = """
<ul class="epcBreadcrumbs">
  <li><div class="breadcrumbs__last-item" dir="auto">AMA BR</div></li>
</ul>
"""


def _wrap(rows_html: str) -> str:
    return f"""
    <html><body>
      {_BREADCRUMB}
      <div class="epcVariations">
        <table><tbody>
          <tr class="epcVariations__header"><th>Model</th><th>Prod period</th><th>Grade</th></tr>
          {rows_html}
        </tbody></table>
      </div>
    </body></html>
    """


def test_missing_market_breadcrumb_is_critical_error():
    html = """
    <html><body>
      <div class="epcVariations">
        <table><tbody>
          <tr class="epcVariations__row">
            <td><a href="https://x/agda43-62158">AGDA43</a></td>
            <td>2024.04 - ...</td>
            <td><span class="info-hint-new">Trendline</span></td>
          </tr>
        </tbody></table>
      </div>
    </body></html>
    """
    result = parse_market_spec_index(html, source_capture_id="cap")
    assert result.critical_error is not None
    assert result.entries == ()


def test_row_with_wrong_td_count_is_a_parse_error_not_critical():
    html = _wrap('<tr class="epcVariations__row"><td>only one td</td></tr>')
    result = parse_market_spec_index(html, source_capture_id="cap")
    assert result.critical_error is None
    assert result.entries == ()
    assert len(result.parse_errors) == 1
    assert "expected 3" in result.parse_errors[0].message


def test_row_missing_link_is_a_parse_error():
    html = _wrap(
        '<tr class="epcVariations__row"><td>no link here</td><td>2024.04 - ...</td><td></td></tr>'
    )
    result = parse_market_spec_index(html, source_capture_id="cap")
    assert result.critical_error is None
    assert result.entries == ()
    assert len(result.parse_errors) == 1
    assert "model link" in result.parse_errors[0].message


def test_row_with_non_numeric_catalog_id_suffix_is_a_parse_error():
    html = _wrap(
        '<tr class="epcVariations__row">'
        '<td><a href="https://www.amayama.com/en/x/agda43-notanumber">AGDA43</a></td>'
        "<td>2024.04 - ...</td><td></td></tr>"
    )
    result = parse_market_spec_index(html, source_capture_id="cap")
    assert result.critical_error is None
    assert result.entries == ()
    assert len(result.parse_errors) == 1
    assert "amayama_catalog_id" in result.parse_errors[0].message


def test_one_bad_row_does_not_drop_the_others():
    html = _wrap(
        '<tr class="epcVariations__row"><td>bad row</td></tr>'
        '<tr class="epcVariations__row">'
        '<td><a href="https://www.amayama.com/en/x/agda43-62158">AGDA43</a></td>'
        "<td>2024.04 - ...</td>"
        '<td><span class="info-hint-new">Trendline</span></td></tr>'
    )
    result = parse_market_spec_index(html, source_capture_id="cap")
    assert result.critical_error is None
    assert len(result.entries) == 1
    assert len(result.parse_errors) == 1
    assert result.entries[0].model_code == "AGDA43"


def test_unparseable_production_period_is_not_an_error():
    html = _wrap(
        '<tr class="epcVariations__row">'
        '<td><a href="https://www.amayama.com/en/x/agda43-62158">AGDA43</a></td>'
        "<td>some unexpected free text</td>"
        '<td><span class="info-hint-new">Trendline</span></td></tr>'
    )
    result = parse_market_spec_index(html, source_capture_id="cap")
    assert result.critical_error is None
    assert result.parse_errors == ()
    entry = result.entries[0]
    assert entry.production_start is None
    assert entry.production_end is None
    assert entry.production_period_raw == "some unexpected free text"
