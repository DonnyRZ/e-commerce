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


def descendant_ids_select(category_id: str):
    """Return a recursive selectable containing ``category_id`` and children."""

    tree = select(Category.id).where(Category.id == category_id).cte(
        name="category_tree", recursive=True
    )
    tree = tree.union_all(
        select(Category.id).join(tree, Category.parent_id == tree.c.id)
    )
    return select(tree.c.id)


async def get_category_by_slug(
    session: AsyncSession, slug: str, *, active_only: bool = False
) -> Optional[Category]:
    stmt = select(Category).where(Category.slug == slug)
    if active_only:
        stmt = stmt.where(Category.is_active.is_(True))
    return await session.scalar(stmt)


async def get_root_category(
    session: AsyncSession, category: Category
) -> Optional[Category]:
    """Walk parents to the department root, guarding against malformed cycles."""

    current = category
    seen = set()
    while current.parent_id:
        if current.id in seen:
            return None
        seen.add(current.id)
        current = await session.get(Category, current.parent_id)
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
