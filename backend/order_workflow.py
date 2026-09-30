"""Shared order-workflow stage rules used by order and Telegram Inbox APIs."""

from __future__ import annotations

from sqlalchemy import and_, case

WORKFLOW_STAGES = (
    "inquiry",
    "pending_payment",
    "payment_review",
    "paid",
    "supplier_shipping",
    "received_by_admin",
    "customer_shipping",
    "delivered",
)
WORKFLOW_FILTER_STAGES = (
    "inquiry",
    "payment",
    "supplier_shipping",
    "received_by_admin",
    "customer_shipping",
    "delivered",
    "archived",
)
WORKFLOW_FILTER_ALIASES = {
    "pending_payment": "payment",
    "payment_review": "payment",
    "paid": "supplier_shipping",
    "processing": "supplier_shipping",
    "shipped": "customer_shipping",
}
WORKFLOW_STATUS_STAGES = {
    "pending_payment": "payment",
    "payment_review": "payment",
    # Display the next operational checkpoint, not the last persisted event.
    "paid": "supplier_shipping",
    "processing": "supplier_shipping",
    "supplier_shipping": "received_by_admin",
    "received_by_admin": "customer_shipping",
    "customer_shipping": "customer_shipping",
    "shipped": "customer_shipping",
    "delivered": "delivered",
}
WORKFLOW_STAGE_STATUS_GROUPS = {
    "inquiry": set(),
    "payment": {"pending_payment", "payment_review"},
    "supplier_shipping": {"paid", "processing"},
    "received_by_admin": {"supplier_shipping"},
    "customer_shipping": {"received_by_admin", "customer_shipping", "shipped"},
    "delivered": {"delivered"},
}
ACTIONABLE_ORDER_STATUSES = {
    "pending_payment",
    "payment_review",
    "paid",
    "supplier_shipping",
    "received_by_admin",
    "customer_shipping",
    "processing",
    "shipped",
}
TERMINAL_ORDER_STATUSES = {"delivered", "cancelled"}


def workflow_stage_for_status(status: str, fallback: str | None = None) -> str:
    """Return the shared checkpoint and preserve caller-specific fallbacks."""
    if status in WORKFLOW_STATUS_STAGES:
        return WORKFLOW_STATUS_STAGES[status]
    return status if fallback is None else fallback


def workflow_stage_sql(status_column, fallback: str | None = None):
    """SQL equivalent of :func:`workflow_stage_for_status`."""
    return case(
        WORKFLOW_STATUS_STAGES,
        value=status_column,
        else_=status_column if fallback is None else fallback,
    )


def normalize_workflow_filter_stage(stage: str) -> str:
    """Normalize legacy URLs without reinterpreting canonical stage IDs."""
    return WORKFLOW_FILTER_ALIASES.get(stage, stage)


def telegram_conversation_stage_sql(
    conversation_status_column,
    total_orders_column,
    non_archived_orders_column,
    active_orders_column,
    non_delivered_orders_column,
    selected_order_status_column,
):
    """Resolve one Inbox stage from a conversation's related order summary."""
    all_orders_archived = and_(
        total_orders_column > 0,
        non_archived_orders_column == 0,
    )
    all_non_archived_orders_delivered = and_(
        non_archived_orders_column > 0,
        non_delivered_orders_column == 0,
    )
    return case(
        (conversation_status_column == "archived", "archived"),
        (all_orders_archived, "archived"),
        (
            active_orders_column > 0,
            workflow_stage_sql(selected_order_status_column, "inquiry"),
        ),
        (all_non_archived_orders_delivered, "delivered"),
        else_="inquiry",
    )


def telegram_conversation_stage(
    *,
    conversation_status: str,
    total_orders: int,
    non_archived_orders: int,
    active_orders: int,
    non_delivered_orders: int,
    selected_order_status: str | None,
) -> str:
    """Python equivalent used by tests and any non-query presentation code."""
    if conversation_status == "archived":
        return "archived"
    if total_orders > 0 and non_archived_orders == 0:
        return "archived"
    if active_orders > 0:
        return workflow_stage_for_status(selected_order_status or "", "inquiry")
    if non_archived_orders > 0 and non_delivered_orders == 0:
        return "delivered"
    return "inquiry"
