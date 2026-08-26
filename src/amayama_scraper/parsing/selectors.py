"""Seletores v1 — Níveis A/B/C, contracts/domain-contracts.md.

Evidência técnica já pesquisada e aprovada (Nível C: research.md §16 original;
Níveis A/B: research.md §21, evidência real de 2026-08-26). Qualquer
divergência estrutural em runtime deve produzir erro explícito de drift —
nunca parsing permissivo que oculte a divergência.
"""

from __future__ import annotations

# --- Nível A — Market Index (research.md §21) ---
MARKET_INDEX_CONTAINER = ".epcVariations"
MARKET_INDEX_ROW = ".epcVariations__row"
MARKET_INDEX_GRADE = "span.info-hint-new"

# --- Nível B — Spec Group Manifest (research.md §21) ---
SPEC_NAV_DETAILS = ".epcVariation__details"
SPEC_NAV_CATEGORY_NAV = ".epcVariation__schemaGroups"
SPEC_NAV_CATEGORY_LINK = "a.epcVariation__schemaGroup"
SPEC_NAV_GROUPS_CONTAINER = ".epcVariation__schemas"
SPEC_NAV_GROUP_CARD = ".epcVariation__schema[data-id]"
SPEC_NAV_GROUP_NAME_LINK = ".epcVariation__schema-name a[href]"

# --- Nível C — Group Detail ---
VARIATION_DETAILS = ".epcVariation__details"
SCHEMAS_CONTAINER = ".epcSchema__schemas"
SCHEMA = ".epcSchema__schema[data-id]"
IMAGE_DESCRIPTION = ".img__description"
IMAGE = ".imgMap img[src]"
ENTRIES_TABLE = ".entriesTable"
PNC_ROW = "tr[data-key]"
GROUP_HEADER = ".entriesPncTable__groupHeader"
OEM_NUMBER = ".entriesTable__number"
DESCRIPTION = ".entriesTable__description"
NESTED_DESCRIPTION = ".entriesPncDescriptionTable"
PERIOD = ".entriesTable__period"
QUANTITY = ".entriesTable__required"

ALL_SELECTORS: dict[str, str] = {
    "market_index_container": MARKET_INDEX_CONTAINER,
    "market_index_row": MARKET_INDEX_ROW,
    "market_index_grade": MARKET_INDEX_GRADE,
    "spec_nav_details": SPEC_NAV_DETAILS,
    "spec_nav_category_nav": SPEC_NAV_CATEGORY_NAV,
    "spec_nav_category_link": SPEC_NAV_CATEGORY_LINK,
    "spec_nav_groups_container": SPEC_NAV_GROUPS_CONTAINER,
    "spec_nav_group_card": SPEC_NAV_GROUP_CARD,
    "spec_nav_group_name_link": SPEC_NAV_GROUP_NAME_LINK,
    "variation_details": VARIATION_DETAILS,
    "schemas_container": SCHEMAS_CONTAINER,
    "schema": SCHEMA,
    "image_description": IMAGE_DESCRIPTION,
    "image": IMAGE,
    "entries_table": ENTRIES_TABLE,
    "pnc_row": PNC_ROW,
    "group_header": GROUP_HEADER,
    "oem_number": OEM_NUMBER,
    "description": DESCRIPTION,
    "nested_description": NESTED_DESCRIPTION,
    "period": PERIOD,
    "quantity": QUANTITY,
}
