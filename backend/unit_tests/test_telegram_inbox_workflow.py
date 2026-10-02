"""Regression tests for workflow-aware, deduplicated Telegram Inbox filters."""

import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://unused:unused@127.0.0.1:1/audit"
)
os.environ.setdefault("JWT_SECRET", "isolated-test-secret-never-used-for-real-auth")

from order_workflow import (  # noqa: E402
    telegram_conversation_stage,
    workflow_stage_for_status,
)  # noqa: E402
from routers.manual_orders import _workflow_stage  # noqa: E402
from routers import telegram_inbox as telegram_inbox_router  # noqa: E402
from routers.telegram_inbox import (  # noqa: E402
    _conversation_stage_cte,
    _conversation_order_context,
    _cursor_decode,
    _cursor_encode,
    InboxPendingOrderCreateIn,
    add_conversation_candidates_to_pending_orders,
    list_conversations,
)  # noqa: E402


class FakeResult:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def all(self):
        return self.rows

    def scalars(self):
        return self


class TelegramInboxWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirmed_inbox_candidates_are_queued_as_pending_order(self):
        conversation = SimpleNamespace(
            id="conversation-1",
            connection_id="connection-1",
            chat_id=123,
            locale="uz",
            customer_name="Customer One",
            customer_username="customerone",
            status="ready_for_order",
            last_message_at=None,
        )
        candidate = SimpleNamespace(
            id="candidate-1",
            status="confirmed",
            order_id=None,
            product_id="product-1",
            variant_id="variant-1",
            sku="SKU-1",
            quantity=2,
            product_name="Product One",
            option_values={"Size": "M"},
            image_url=None,
        )
        product = SimpleNamespace(
            id="product-1",
            status="active",
            is_demo=False,
            category_id="category-1",
            currency="UZS",
            seller_id="seller-1",
            base_price=10000,
        )
        variant = SimpleNamespace(
            id="variant-1",
            product_id="product-1",
            is_active=True,
            sale_price_override=None,
            price_override=None,
            sku="SKU-1",
            option_values={"Size": "M"},
        )
        category = SimpleNamespace(id="category-1")
        events = []
        added = []

        def add(row):
            added.append(row)

        async def get(model, _row_id):
            return {
                telegram_inbox_router.Product: product,
                telegram_inbox_router.ProductVariant: variant,
                telegram_inbox_router.Category: category,
            }.get(model)

        async def commit():
            events.append("commit")

        session = SimpleNamespace(
            scalar=AsyncMock(return_value=None),
            execute=AsyncMock(return_value=FakeResult([candidate])),
            get=AsyncMock(side_effect=get),
            add=add,
            flush=AsyncMock(),
            commit=AsyncMock(side_effect=commit),
            rollback=AsyncMock(),
        )

        payload = InboxPendingOrderCreateIn(
            candidate_ids=[candidate.id],
        )
        with (
            patch.object(
                telegram_inbox_router,
                "_load_conversation",
                new=AsyncMock(return_value=conversation),
            ),
            patch.object(telegram_inbox_router, "audit", new=AsyncMock()),
        ):
            result = await add_conversation_candidates_to_pending_orders(
                "conversation-1",
                payload,
                user=SimpleNamespace(id="admin-1"),
                session=session,
                idempotency_key="inbox-pending-test-001",
            )

        inquiry = next(row for row in added if isinstance(row, telegram_inbox_router.TelegramCartInquiry))
        self.assertEqual(result["reference"], inquiry.reference)
        self.assertEqual(result["status"], "pending_order")
        self.assertEqual(events, ["commit"])
        self.assertIsNone(inquiry.order_id)
        self.assertEqual(inquiry.source, "telegram_inbox")
        self.assertEqual(inquiry.conversation_id, conversation.id)
        self.assertEqual(inquiry.snapshot["items"][0]["sku"], candidate.sku)
        self.assertEqual(candidate.status, "pending_order")
        self.assertIsNone(candidate.order_id)
        self.assertEqual(conversation.status, "waiting_customer")

    async def test_pending_order_retry_returns_existing_inquiry_before_candidate_check(self):
        conversation = SimpleNamespace(id="conversation-1")
        existing = SimpleNamespace(
            reference="SC-EXISTING1",
            status="sent",
        )
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=existing),
            execute=AsyncMock(),
        )
        payload = InboxPendingOrderCreateIn(candidate_ids=["candidate-already-queued"])
        with patch.object(
            telegram_inbox_router,
            "_load_conversation",
            new=AsyncMock(return_value=conversation),
        ):
            result = await add_conversation_candidates_to_pending_orders(
                "conversation-1",
                payload,
                user=SimpleNamespace(id="admin-1"),
                session=session,
                idempotency_key="inbox-pending-test-001",
            )

        self.assertEqual(
            result,
            {
                "reference": "SC-EXISTING1",
                "status": "pending_order",
            },
        )
        session.execute.assert_not_awaited()

    def test_order_and_inbox_share_status_stage_mapping(self):
        statuses = {
            "pending_payment": "payment",
            "payment_review": "payment",
            "paid": "supplier_shipping",
            "processing": "supplier_shipping",
            "supplier_shipping": "received_by_admin",
            "received_by_admin": "customer_shipping",
            "customer_shipping": "customer_shipping",
            "shipped": "customer_shipping",
            "delivered": "delivered",
        }
        for status, expected_stage in statuses.items():
            with self.subTest(status=status):
                self.assertEqual(_workflow_stage(status), expected_stage)
                self.assertEqual(
                    workflow_stage_for_status(status, "inquiry"),
                    expected_stage,
                )

    def test_conversation_stage_rules_keep_chat_visible_once(self):
        self.assertEqual(
            telegram_conversation_stage(
                conversation_status="needs_admin",
                total_orders=0,
                non_archived_orders=0,
                active_orders=0,
                non_delivered_orders=0,
                selected_order_status=None,
            ),
            "inquiry",
        )
        self.assertEqual(
            telegram_conversation_stage(
                conversation_status="needs_admin",
                total_orders=2,
                non_archived_orders=2,
                active_orders=1,
                non_delivered_orders=2,
                selected_order_status="supplier_shipping",
            ),
            "received_by_admin",
        )
        self.assertEqual(
            telegram_conversation_stage(
                conversation_status="needs_admin",
                total_orders=2,
                non_archived_orders=1,
                active_orders=1,
                non_delivered_orders=1,
                selected_order_status="paid",
            ),
            "supplier_shipping",
        )
        self.assertEqual(
            telegram_conversation_stage(
                conversation_status="needs_admin",
                total_orders=2,
                non_archived_orders=0,
                active_orders=0,
                non_delivered_orders=0,
                selected_order_status=None,
            ),
            "archived",
        )
        self.assertEqual(
            telegram_conversation_stage(
                conversation_status="archived",
                total_orders=1,
                non_archived_orders=1,
                active_orders=1,
                non_delivered_orders=1,
                selected_order_status="paid",
            ),
            "archived",
        )
        self.assertEqual(
            telegram_conversation_stage(
                conversation_status="needs_admin",
                total_orders=1,
                non_archived_orders=1,
                active_orders=0,
                non_delivered_orders=0,
                selected_order_status="delivered",
            ),
            "delivered",
        )
        self.assertEqual(
            telegram_conversation_stage(
                conversation_status="needs_admin",
                total_orders=1,
                non_archived_orders=1,
                active_orders=1,
                non_delivered_orders=1,
                selected_order_status="unexpected_status",
            ),
            "inquiry",
        )

    def test_stage_query_compiles_to_batched_windowed_sql(self):
        query = select(_conversation_stage_cte())
        sql = str(query.compile(dialect=postgresql.dialect())).upper()
        self.assertIn("ROW_NUMBER() OVER", sql)
        self.assertIn("TELEGRAM_INBOX_ORDER_STATS", sql)
        self.assertIn("TELEGRAM_INBOX_CONVERSATION_STAGES", sql)
        self.assertIn("ARCHIVED_AT IS NULL", sql)

    def test_cursor_round_trip_and_rejects_invalid_payload(self):
        conversation = SimpleNamespace(
            id="conversation-1",
            last_message_at=datetime(2026, 9, 29, 10, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(
            _cursor_decode(_cursor_encode(conversation)),
            (conversation.last_message_at, conversation.id),
        )
        with self.assertRaises(HTTPException) as caught:
            _cursor_decode("not-a-valid-cursor")
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(caught.exception.detail["error"], "invalid_inbox_cursor")

    async def test_detail_selects_latest_active_and_archives_correctly(self):
        now = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)

        def make_order(number, status, minutes_ago, archived_at=None):
            return SimpleNamespace(
                id=number,
                order_number=number,
                status=status,
                archived_at=archived_at,
                created_at=now.replace(minute=minutes_ago),
            )

        conversation = SimpleNamespace(id="conversation-1", status="needs_admin")
        archived_at = now
        order_rows = [
            make_order("MC-NEW", "supplier_shipping", 1),
            make_order("MC-OLD", "paid", 2),
            make_order("MC-ARCHIVED", "delivered", 3, archived_at),
        ]
        session = SimpleNamespace(
            execute=AsyncMock(return_value=FakeResult(order_rows))
        )
        stage, count, latest, orders = await _conversation_order_context(
            session, conversation
        )
        self.assertEqual((stage, count), ("received_by_admin", 3))
        self.assertEqual(latest["order_number"], "MC-NEW")
        self.assertEqual(len(orders), 3)

        session.execute = AsyncMock(
            return_value=FakeResult(
                [
                    make_order("MC-DONE-NEW", "delivered", 1),
                    make_order("MC-DONE-OLD", "delivered", 2),
                ]
            )
        )
        stage, _, latest, _ = await _conversation_order_context(session, conversation)
        self.assertEqual(stage, "delivered")
        self.assertEqual(latest["order_number"], "MC-DONE-NEW")

        session.execute = AsyncMock(
            return_value=FakeResult(
                [
                    make_order("MC-ARCHIVED-NEW", "paid", 1, archived_at),
                    make_order("MC-ARCHIVED-OLD", "delivered", 2, archived_at),
                ]
            )
        )
        stage, _, _, _ = await _conversation_order_context(session, conversation)
        self.assertEqual(stage, "archived")

    async def test_list_legacy_status_alias_and_unique_stage_counts(self):
        conversation = SimpleNamespace(
            id="conversation-1",
            chat_id=123,
            customer_user_id=None,
            customer_username="customer",
            customer_name="Customer",
            telegram_language_code="id",
            locale="id",
            status="needs_admin",
            last_message_at=datetime(2026, 9, 29, 10, 30, tzinfo=timezone.utc),
            last_customer_message_at=None,
        )
        session = SimpleNamespace(
            execute=AsyncMock(
                side_effect=[
                    FakeResult([("supplier_shipping", 1), ("archived", 2)]),
                    FakeResult(
                        [
                            (
                                conversation,
                                "supplier_shipping",
                                2,
                                "MC-LATEST-1",
                                "paid",
                                None,
                                datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc),
                                "supplier_shipping",
                            )
                        ]
                    ),
                    FakeResult(),
                ]
            ),
            scalar=AsyncMock(),
        )

        response = await list_conversations(
            stage="supplier_shipping",
            chat_status=None,
            status="needs_admin",
            q=None,
            cursor=None,
            limit=50,
            user=SimpleNamespace(id="admin"),
            session=session,
        )

        self.assertEqual(len(response["items"]), 1)
        self.assertEqual(response["items"][0]["workflow_stage"], "supplier_shipping")
        self.assertEqual(response["items"][0]["order_count"], 2)
        self.assertEqual(
            response["items"][0]["latest_order"]["order_number"], "MC-LATEST-1"
        )
        self.assertEqual(response["counts"]["supplier_shipping"], 1)
        self.assertEqual(response["counts"]["archived"], 2)
        self.assertEqual(response["total"], 1)
        self.assertEqual(session.execute.await_count, 3)
        count_sql = str(
            session.execute.await_args_list[0]
            .args[0]
            .compile(dialect=postgresql.dialect())
        ).upper()
        self.assertIn("TELEGRAM_CONVERSATIONS.STATUS", count_sql)
        self.assertIn(
            "needs_admin",
            str(
                session.execute.await_args_list[0]
                .args[0]
                .compile(dialect=postgresql.dialect())
                .params
            ),
        )

    async def test_invalid_cursor_fails_before_database_queries(self):
        session = SimpleNamespace(execute=AsyncMock(), scalar=AsyncMock())
        with self.assertRaises(HTTPException) as caught:
            await list_conversations(
                stage=None,
                chat_status=None,
                status=None,
                q=None,
                cursor="invalid",
                limit=50,
                user=SimpleNamespace(id="admin"),
                session=session,
            )
        self.assertEqual(caught.exception.detail["error"], "invalid_inbox_cursor")
        session.execute.assert_not_awaited()

    async def test_cursor_pages_are_stable_and_do_not_repeat_conversations(
        self,
    ):
        first = SimpleNamespace(
            id="conversation-a",
            chat_id=101,
            customer_user_id=None,
            customer_username="first",
            customer_name="First",
            telegram_language_code="id",
            locale="id",
            status="needs_admin",
            last_message_at=datetime(2026, 9, 29, 11, 0, tzinfo=timezone.utc),
            last_customer_message_at=None,
        )
        second = SimpleNamespace(
            id="conversation-b",
            chat_id=102,
            customer_user_id=None,
            customer_username="second",
            customer_name="Second",
            telegram_language_code="id",
            locale="id",
            status="waiting_customer",
            last_message_at=datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc),
            last_customer_message_at=None,
        )

        def list_row(conversation):
            return (conversation, "inquiry", 0, None, None, None, None, None)

        first_session = SimpleNamespace(
            execute=AsyncMock(
                side_effect=[
                    FakeResult([("inquiry", 2)]),
                    FakeResult([list_row(first), list_row(second)]),
                    FakeResult(),
                ]
            ),
            scalar=AsyncMock(),
        )
        first_page = await list_conversations(
            stage=None,
            chat_status=None,
            status=None,
            q=None,
            cursor=None,
            limit=1,
            user=SimpleNamespace(id="admin"),
            session=first_session,
        )
        self.assertEqual(
            [item["id"] for item in first_page["items"]], ["conversation-a"]
        )
        self.assertEqual(first_page["total"], 2)
        self.assertIsNotNone(first_page["next_cursor"])

        second_session = SimpleNamespace(
            execute=AsyncMock(
                side_effect=[
                    FakeResult([("inquiry", 2)]),
                    FakeResult([list_row(second)]),
                    FakeResult(),
                ]
            ),
            scalar=AsyncMock(),
        )
        second_page = await list_conversations(
            stage=None,
            chat_status=None,
            status=None,
            q=None,
            cursor=first_page["next_cursor"],
            limit=1,
            user=SimpleNamespace(id="admin"),
            session=second_session,
        )
        self.assertEqual(
            [item["id"] for item in second_page["items"]], ["conversation-b"]
        )
        self.assertIsNone(second_page["next_cursor"])
        paged_sql = str(
            second_session.execute.await_args_list[1]
            .args[0]
            .compile(dialect=postgresql.dialect())
        ).upper()
        self.assertIn("LAST_MESSAGE_AT <", paged_sql)
        self.assertIn("TELEGRAM_CONVERSATIONS.ID <", paged_sql)


if __name__ == "__main__":
    unittest.main()
