"""T096/T097 — parser_version versionado e anexado ao resultado dos três níveis
de parsing (Constitution §13)."""

from amayama_scraper.parsing.group_detail import PARSER_VERSION as GROUP_DETAIL_VERSION
from amayama_scraper.parsing.market_index import PARSER_VERSION as MARKET_INDEX_VERSION
from amayama_scraper.parsing.spec_group_manifest import (
    PARSER_VERSION as SPEC_GROUP_MANIFEST_VERSION,
)


def test_parser_version_is_versioned_string():
    assert GROUP_DETAIL_VERSION == "amayama-parser-v1"


def test_each_level_has_its_own_versioned_parser_version():
    assert MARKET_INDEX_VERSION == "amayama-market-index-parser-v1"
    assert SPEC_GROUP_MANIFEST_VERSION == "amayama-spec-group-manifest-parser-v1"
    versions = {GROUP_DETAIL_VERSION, MARKET_INDEX_VERSION, SPEC_GROUP_MANIFEST_VERSION}
    assert len(versions) == 3
