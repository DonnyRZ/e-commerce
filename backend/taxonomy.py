"""Shared taxonomy helpers for the single-store catalog.

The original catalog used a flat department -> category relationship.  The
same self-referencing table can safely represent deeper navigation trees as
long as product assignments remain limited to leaf ``category`` nodes.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Category

TAXONOMY_KINDS = {"department", "group", "category"}
PRODUCT_CATEGORY_KIND = "category"


def descendant_ids_select(category_id: str, *, active_only: bool = False):
    """Return a recursive selectable containing ``category_id`` and children.

    Public catalog queries pass ``active_only=True`` so an active child cannot
    leak through an inactive parent that was created by an older release or
    edited directly in the database. Admin integrity checks intentionally use
    the default and can therefore inspect the complete stored tree.
    """

    anchor = select(
        Category.id.label("id"),
        Category.kind.label("kind"),
        Category.department.label("department"),
    ).where(Category.id == category_id)
    if active_only:
        anchor = anchor.where(Category.is_active.is_(True))
    tree = anchor.cte(name="category_tree", recursive=True)
    # DISTINCT recursive members make this query terminate even if legacy or
    # manually-edited data contains a parent cycle. Admin validation prevents
    # new cycles, but public catalog reads must still be safe for old data.
    recursive = (
        select(
            Category.id,
            Category.kind,
            Category.department,
        )
        .join(tree, Category.parent_id == tree.c.id)
        .where(
            Category.kind.in_(("group", "category")),
            Category.department == tree.c.department,
            (
                ((Category.kind == "group") & (tree.c.kind == "department"))
                | (
                    (Category.kind == "category")
                    & tree.c.kind.in_(("department", "group"))
                )
            ),
        )
    )
    if active_only:
        recursive = recursive.where(Category.is_active.is_(True))
    tree = tree.union(recursive)
    return select(tree.c.id)


def active_taxonomy_ids_select():
    """Return all nodes reachable from an active department root.

    This is used as the public product scope. It makes the database's active
    flag hierarchical even for legacy rows that predate the admin parent
    validation rules.
    """

    tree = select(
        Category.id.label("id"),
        Category.kind.label("kind"),
        Category.department.label("department"),
    ).where(
        Category.kind == "department",
        Category.department == Category.slug,
        Category.parent_id.is_(None),
        Category.is_active.is_(True),
    ).cte(name="active_taxonomy_tree", recursive=True)
    tree = tree.union(
        select(
            Category.id,
            Category.kind,
            Category.department,
        )
        .join(tree, Category.parent_id == tree.c.id)
        .where(
            Category.is_active.is_(True),
            Category.kind.in_(("group", "category")),
            Category.department == tree.c.department,
            (
                ((Category.kind == "group") & (tree.c.kind == "department"))
                | (
                    (Category.kind == "category")
                    & tree.c.kind.in_(("department", "group"))
                )
            ),
        )
    )
    return select(tree.c.id)


async def active_taxonomy_chain(
    session: AsyncSession, category: Category, *, lock: bool = False
) -> bool:
    """Return whether a node and every ancestor form an active tree.

    The explicit walk complements the recursive SQL scopes for single-node
    detail endpoints and safely rejects malformed parent cycles.
    """

    current = category
    seen = set()
    while current:
        if (
            current.id in seen
            or not current.is_active
            or current.kind not in TAXONOMY_KINDS
        ):
            return False
        seen.add(current.id)
        if not current.parent_id:
            return current.kind == "department" and current.department == current.slug
        parent_query = select(Category).where(Category.id == current.parent_id)
        if lock:
            parent_query = parent_query.with_for_update()
        parent = await session.scalar(parent_query)
        if not parent or not parent.is_active:
            return False
        if current.department != parent.department:
            return False
        if current.kind == "group" and parent.kind != "department":
            return False
        if current.kind == "category" and parent.kind not in (
            "department",
            "group",
        ):
            return False
        if current.kind == "department":
            return False
        current = parent
    return False


async def get_category_by_slug(
    session: AsyncSession, slug: str, *, active_only: bool = False
) -> Optional[Category]:
    stmt = select(Category).where(Category.slug == slug)
    if active_only:
        stmt = stmt.where(Category.is_active.is_(True))
    return await session.scalar(stmt)


async def get_root_category(
    session: AsyncSession, category: Category, *, lock: bool = False
) -> Optional[Category]:
    """Walk parents to the department root, guarding against malformed cycles."""

    current = category
    seen = set()
    while current.parent_id:
        if current.id in seen:
            return None
        seen.add(current.id)
        parent_query = select(Category).where(Category.id == current.parent_id)
        if lock:
            parent_query = parent_query.with_for_update()
        current = await session.scalar(parent_query)
        if not current:
            return None
    return current


async def get_category_ancestors(
    session: AsyncSession, category: Category, *, active_only: bool = False
) -> list[Category]:
    """Return ancestors in root-to-parent order."""

    ancestors: list[Category] = []
    current = category
    seen = {category.id}
    while current.parent_id:
        parent = await session.get(Category, current.parent_id)
        if not parent or parent.id in seen:
            break
        seen.add(parent.id)
        if not active_only or parent.is_active:
            ancestors.append(parent)
        current = parent
    ancestors.reverse()
    return ancestors


async def category_descendant_ids(
    session: AsyncSession, category_id: str, *, leaves_only: bool = True
) -> list[str]:
    descendant_ids = descendant_ids_select(category_id)
    stmt = select(Category.id).where(Category.id.in_(descendant_ids))
    if leaves_only:
        stmt = stmt.where(Category.kind == PRODUCT_CATEGORY_KIND)
    return list((await session.execute(stmt)).scalars().all())


def same_root(first: Category, second: Category) -> bool:
    """Fast check for already-loaded roots; callers should compare root ids."""

    return first.id == second.id
