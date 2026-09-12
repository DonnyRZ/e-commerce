"""Pure contract checks for the hierarchical catalog helpers."""

from sqlalchemy.dialects import postgresql

from seed_catalog import DEPARTMENTS, NEW_TAXONOMY_GROUPS, REMOVED_CATALOG_SLUGS
from taxonomy import TAXONOMY_KINDS, descendant_ids_select


def test_taxonomy_kinds_are_explicit_and_product_safe():
    assert TAXONOMY_KINDS == {"department", "group", "category"}


def test_approved_batik_and_parfum_taxonomy_is_storefront_visible():
    departments = {slug: is_active for slug, _order, _names, _image, is_active in DEPARTMENTS}
    assert departments["batik"] is True
    assert departments["parfum"] is True
    assert {slug for _department, slug, *_ in NEW_TAXONOMY_GROUPS} == {
        "batik-wanita-muslimah",
        "parfum-wanita-muslimah",
    }
    assert all(
        group_names and leaf_specs
        for _department, _slug, _order, group_names, leaf_specs in NEW_TAXONOMY_GROUPS
    )


def test_male_catalog_nodes_are_not_reintroduced():
    assert REMOVED_CATALOG_SLUGS == {
        "batik-pria",
        "batik-koko-kemko",
        "kemeja-batik-lengan-panjang",
        "kemeja-batik-lengan-pendek",
        "jas-blazer-batik-luara",
        "sarung-batik",
        "parfum-pria",
        "oud-woody",
        "kasturi-rempah",
        "fresh-citrus-aquatic",
        "attar-perfume-oil-premium",
    }


def test_descendant_scope_uses_a_recursive_cte():
    statement = descendant_ids_select("department-id")
    sql = str(statement.compile(dialect=postgresql.dialect())).upper()

    assert "WITH RECURSIVE" in sql
    assert "CATEGORY_TREE" in sql
    assert "PARENT_ID" in sql
