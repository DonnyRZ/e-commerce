"""Pure contract checks for the hierarchical catalog helpers."""

from sqlalchemy.dialects import postgresql

from taxonomy import TAXONOMY_KINDS, descendant_ids_select


def test_taxonomy_kinds_are_explicit_and_product_safe():
    assert TAXONOMY_KINDS == {"department", "group", "category"}


def test_descendant_scope_uses_a_recursive_cte():
    statement = descendant_ids_select("department-id")
    sql = str(statement.compile(dialect=postgresql.dialect())).upper()

    assert "WITH RECURSIVE" in sql
    assert "CATEGORY_TREE" in sql
    assert "PARENT_ID" in sql
