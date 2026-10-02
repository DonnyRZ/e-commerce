"""Regression tests for stage aliases, counts, and safe workflow pagination."""
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused:unused@127.0.0.1:1/audit")
os.environ.setdefault("JWT_SECRET", "isolated-test-secret-never-used-for-real-auth")

from routers import manual_orders as orders  # noqa: E402
from routers.manual_orders import (
    _workflow_counts,
    _workflow_filter_stage,
    _workflow_page,
    _workflow_stage,
    ManualOrderCreateIn,
    archive_admin_order,
    create_manual_order,
    list_order_workflow,
    permanently_delete_admin_order,
    permanently_delete_admin_telegram_inquiry,
    restore_admin_order,
)


class FakeResult:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def all(self):
        return self.rows

    def scalars(self):
        return self


class OrderWorkflowMappingTests(unittest.TestCase):
    def setUp(self):
        self.entries = [
            {"order_number": "PAY-1", "status": "pending_payment", "stage": _workflow_stage("pending_payment")},
            {"order_number": "PAY-2", "status": "payment_review", "stage": _workflow_stage("payment_review")},
            {"order_number": "SUP-READY", "status": "paid", "stage": _workflow_stage("paid")},
            {"order_number": "SUP-MANUAL", "status": "supplier_shipping", "stage": _workflow_stage("supplier_shipping")},
            {"order_number": "SUP-LEGACY", "status": "processing", "stage": _workflow_stage("processing")},
            {"order_number": "CUS-MANUAL", "status": "customer_shipping", "stage": _workflow_stage("customer_shipping")},
            {"order_number": "CUS-LEGACY", "status": "shipped", "stage": _workflow_stage("shipped")},
            {"order_number": "RECEIVED", "status": "received_by_admin", "stage": _workflow_stage("received_by_admin")},
            {"order_number": "DONE", "status": "delivered", "stage": _workflow_stage("delivered")},
        ]

    def test_persisted_statuses_map_to_the_next_visible_checkpoint(self):
        self.assertEqual(_workflow_stage("paid"), "supplier_shipping")
        self.assertEqual(_workflow_stage("processing"), "supplier_shipping")
        self.assertEqual(_workflow_stage("supplier_shipping"), "received_by_admin")
        self.assertEqual(_workflow_stage("received_by_admin"), "customer_shipping")
        self.assertEqual(_workflow_stage("customer_shipping"), "customer_shipping")
        self.assertEqual(_workflow_stage("shipped"), "customer_shipping")
        self.assertEqual(_workflow_stage("delivered"), "delivered")
        self.assertEqual(_workflow_stage("payment_review"), "payment")
        self.assertEqual(_workflow_filter_stage("supplier_shipping"), "supplier_shipping")
        self.assertEqual(_workflow_filter_stage("received_by_admin"), "received_by_admin")
        self.assertEqual(_workflow_filter_stage("paid"), "supplier_shipping")

    def test_stage_counts_partition_all_statuses_and_filter_by_next_checkpoint(self):
        status_counts = {}
        for entry in self.entries:
            status_counts[entry["status"]] = status_counts.get(entry["status"], 0) + 1
        counts = _workflow_counts(status_counts, inquiry_count=4)
        filtered, total, page = _workflow_page(
            self.entries, "supplier_shipping", page=1, page_size=20
        )

        self.assertEqual(total, 2)
        self.assertEqual(page, 1)
        self.assertEqual(len(filtered), 2)
        self.assertEqual(counts["supplier_shipping"], 2)
        self.assertEqual(counts["received_by_admin"], 1)
        self.assertEqual(counts["customer_shipping"], 3)
        self.assertEqual(counts["payment"], 2)
        self.assertEqual(counts["inquiry"], 4)
        self.assertEqual(counts["delivered"], 1)
        self.assertEqual(
            sum(counts[stage] for stage in ("payment", "supplier_shipping", "received_by_admin", "customer_shipping", "delivered")),
            len(self.entries),
        )
        self.assertEqual(counts["paid"], 1)
        self.assertEqual(counts["payment_review"], 1)

    def test_pagination_clamps_after_orders_move_between_stages(self):
        filtered, total, page = _workflow_page(
            self.entries, "supplier_shipping", page=99, page_size=1
        )
        self.assertEqual(total, 2)
        self.assertEqual(page, 2)
        self.assertEqual([entry["order_number"] for entry in filtered], ["SUP-LEGACY"])


class OrderWorkflowEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_received_by_admin_filter_contains_supplier_shipped_order(self):
        shipped_order = SimpleNamespace(
            id="order-supplier-shipped",
            order_number="MC-SUPPLIER-SHIPPED-1",
            order_source="telegram_manual",
            status="supplier_shipping",
            payment_state="paid",
            archived_at=None,
            created_at=datetime(2026, 9, 29, tzinfo=timezone.utc),
            user_id=None,
            shipping_address={},
            guest_email="customer@example.com",
            subtotal=100,
            grand_total=120,
            currency="UZS",
        )
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=0),
            execute=AsyncMock(
                side_effect=[
                    FakeResult(),
                    FakeResult([("paid", 1), ("supplier_shipping", 1)]),
                    FakeResult([shipped_order]),
                    FakeResult([("order-supplier-shipped", 1)]),
                    FakeResult(),
                ]
            ),
            get=AsyncMock(return_value=None),
        )

        response = await list_order_workflow(
            scope="all",
            stage="received_by_admin",
            q=None,
            page=1,
            page_size=20,
            user=SimpleNamespace(id="admin"),
            session=session,
        )

        self.assertEqual([item["order_number"] for item in response["items"]], ["MC-SUPPLIER-SHIPPED-1"])
        self.assertEqual(response["items"][0]["status"], "supplier_shipping")
        self.assertEqual(response["items"][0]["stage"], "received_by_admin")
        self.assertEqual(response["items"][0]["next_action"], "receive_admin")
        self.assertEqual(response["counts"]["received_by_admin"], 1)
        self.assertEqual(response["counts"]["supplier_shipping"], 1)

        order_query = session.execute.await_args_list[2].args[0]
        self.assertEqual(
            set(order_query.compile().params["status_1"]),
            {"supplier_shipping"},
        )

    async def test_supplier_filter_includes_paid_rows_and_keeps_global_counts(self):
        order = SimpleNamespace(
            id="order-paid",
            order_number="MC-PAID-1",
            order_source="checkout",
            status="paid",
            payment_state="paid",
            archived_at=None,
            created_at=datetime(2026, 9, 29, tzinfo=timezone.utc),
            user_id=None,
            shipping_address={},
            guest_email="customer@example.com",
            subtotal=100,
            grand_total=120,
            currency="UZS",
        )
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=0),
            execute=AsyncMock(
                side_effect=[
                    FakeResult(),
                    FakeResult([("paid", 3), ("supplier_shipping", 2), ("payment_review", 1)]),
                    FakeResult([order]),
                    FakeResult([("order-paid", 1)]),
                    FakeResult(),
                ]
            ),
            get=AsyncMock(return_value=None),
        )

        response = await list_order_workflow(
            scope="all",
            stage="supplier_shipping",
            q=None,
            page=1,
            page_size=20,
            user=SimpleNamespace(id="admin"),
            session=session,
        )

        self.assertEqual([item["order_number"] for item in response["items"]], ["MC-PAID-1"])
        self.assertEqual(response["items"][0]["stage"], "supplier_shipping")
        self.assertEqual(response["counts"]["supplier_shipping"], 3)
        self.assertEqual(response["counts"]["payment"], 1)
        self.assertEqual(response["total"], 1)

        count_query = session.execute.await_args_list[1].args[0]
        order_query = session.execute.await_args_list[2].args[0]
        self.assertIn("ARCHIVED_AT IS NULL", str(count_query).upper())
        status_filter = order_query.compile().params["status_1"]
        self.assertEqual(set(status_filter), {"paid", "processing"})

    async def test_customer_shipping_filter_includes_received_and_in_transit_orders(self):
        order = SimpleNamespace(
            id="order-received",
            order_number="MC-RECEIVED-1",
            order_source="telegram_manual",
            status="received_by_admin",
            payment_state="paid",
            archived_at=None,
            created_at=datetime(2026, 9, 29, tzinfo=timezone.utc),
            user_id=None,
            shipping_address={},
            guest_email="customer@example.com",
            subtotal=100,
            grand_total=120,
            currency="UZS",
        )
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=0),
            execute=AsyncMock(
                side_effect=[
                    FakeResult(),
                    FakeResult([("received_by_admin", 1), ("customer_shipping", 1), ("delivered", 1)]),
                    FakeResult([order]),
                    FakeResult([("order-received", 1)]),
                    FakeResult(),
                ]
            ),
            get=AsyncMock(return_value=None),
        )

        response = await list_order_workflow(
            scope="all",
            stage="customer_shipping",
            q=None,
            page=1,
            page_size=20,
            user=SimpleNamespace(id="admin"),
            session=session,
        )

        self.assertEqual(response["items"][0]["stage"], "customer_shipping")
        self.assertEqual(response["items"][0]["next_action"], "ship_customer")
        self.assertEqual(response["counts"]["customer_shipping"], 2)
        self.assertEqual(response["counts"]["delivered"], 1)
        order_query = session.execute.await_args_list[2].args[0]
        self.assertEqual(
            set(order_query.compile().params["status_1"]),
            {"received_by_admin", "customer_shipping", "shipped"},
        )

    async def test_archived_filter_returns_archived_orders_but_not_active_counts(self):
        archived_order = SimpleNamespace(
            id="order-archived",
            order_number="MC-ARCHIVED-1",
            order_source="checkout",
            status="supplier_shipping",
            payment_state="paid",
            archived_at=datetime(2026, 9, 29, tzinfo=timezone.utc),
            created_at=datetime(2026, 9, 28, tzinfo=timezone.utc),
            user_id=None,
            shipping_address={},
            guest_email="customer@example.com",
            subtotal=100,
            grand_total=120,
            currency="UZS",
        )
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=1),
            execute=AsyncMock(
                side_effect=[
                    FakeResult(),
                    FakeResult([("supplier_shipping", 3)]),
                    FakeResult([archived_order]),
                    FakeResult([("order-archived", 1)]),
                    FakeResult(),
                ]
            ),
            get=AsyncMock(return_value=None),
        )

        response = await list_order_workflow(
            scope="all",
            stage="archived",
            q=None,
            page=1,
            page_size=20,
            user=SimpleNamespace(id="admin"),
            session=session,
        )

        self.assertEqual([item["order_number"] for item in response["items"]], ["MC-ARCHIVED-1"])
        self.assertEqual(response["items"][0]["archived_at"], archived_order.archived_at)
        self.assertEqual(response["counts"]["archived"], 1)
        self.assertEqual(response["counts"]["supplier_shipping"], 0)
        self.assertEqual(response["counts"]["received_by_admin"], 3)
        self.assertEqual(response["items"][0]["stage"], "received_by_admin")
        archived_query = session.execute.await_args_list[2].args[0]
        self.assertIn("ARCHIVED_AT IS NOT NULL", str(archived_query).upper())


class OrderLifecycleEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_archive_and_restore_preserve_order_and_are_audited(self):
        order = SimpleNamespace(
            id="order-1",
            order_number="MC-ARCHIVE-1",
            status="supplier_shipping",
            payment_state="paid",
            archived_at=None,
        )
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=order),
            add=unittest.mock.Mock(),
            commit=AsyncMock(),
        )
        admin = SimpleNamespace(id="admin-1")

        archived = await archive_admin_order("MC-ARCHIVE-1", admin, session, None)
        self.assertTrue(archived["archived"])
        self.assertIsNotNone(order.archived_at)
        session.commit.assert_awaited_once()

        restored = await restore_admin_order("MC-ARCHIVE-1", admin, session, None)
        self.assertFalse(restored["archived"])
        self.assertIsNone(order.archived_at)
        self.assertEqual(session.commit.await_count, 2)
        self.assertEqual(session.add.call_count, 2)

    async def test_permanent_delete_removes_order_and_all_owned_rows(self):
        order = SimpleNamespace(
            id="order-1",
            order_number="MC-DELETE-1",
            status="delivered",
            payment_state="paid",
            archived_at=None,
            grand_total=120,
            currency="UZS",
        )
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=order),
            execute=AsyncMock(side_effect=[FakeResult(), *[FakeResult() for _ in range(9)]]),
            add=unittest.mock.Mock(),
            commit=AsyncMock(),
        )

        result = await permanently_delete_admin_order(
            "MC-DELETE-1", SimpleNamespace(id="admin-1"), session, None
        )

        self.assertEqual(result, {"order_number": "MC-DELETE-1", "deleted": True})
        self.assertEqual(session.execute.await_count, 10)
        delete_statements = [
            str(call.args[0]).upper()
            for call in session.execute.await_args_list
            if str(call.args[0]).lstrip().upper().startswith("DELETE")
        ]
        self.assertEqual(
            [statement.split(" FROM ", 1)[1].split(" ", 1)[0] for statement in delete_statements],
            ["ORDER_ITEMS", "ORDER_FULFILLMENT_STAGES", "TELEGRAM_ORDER_NOTIFICATION_OUTBOX", "SELLER_ORDER_FULFILLMENTS", "ORDERS"],
        )
        self.assertTrue(any("FROM INVENTORY_RESERVATIONS" in str(call.args[0]).upper() for call in session.execute.await_args_list))
        session.commit.assert_awaited_once()

    async def test_permanent_delete_waits_for_active_telegram_send(self):
        order = SimpleNamespace(id="order-1", order_number="MC-SENDING-1", archived_at=None)
        payment = SimpleNamespace(id="payment-1")
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=order),
            execute=AsyncMock(
                side_effect=[
                    FakeResult([payment]),
                    FakeResult([SimpleNamespace(status="sending")]),
                ]
            ),
            add=unittest.mock.Mock(),
            commit=AsyncMock(),
        )

        with self.assertRaises(HTTPException) as caught:
            await permanently_delete_admin_order(
                "MC-SENDING-1", SimpleNamespace(id="admin-1"), session, None
            )

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.detail["error"], "payment_notification_in_progress")
        session.commit.assert_not_awaited()

    async def test_permanent_delete_waits_for_active_order_notification(self):
        order = SimpleNamespace(id="order-1", order_number="MC-ORDER-SENDING-1", archived_at=None)
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=order),
            execute=AsyncMock(
                side_effect=[
                    FakeResult(),
                    FakeResult([SimpleNamespace(status="sending")]),
                ]
            ),
            add=unittest.mock.Mock(),
            commit=AsyncMock(),
        )

        with self.assertRaises(HTTPException) as caught:
            await permanently_delete_admin_order(
                "MC-ORDER-SENDING-1", SimpleNamespace(id="admin-1"), session, None
            )

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.detail["error"], "order_notification_in_progress")
        session.commit.assert_not_awaited()

    async def test_permanent_delete_removes_payment_evidence_and_keeps_audit(self):
        order = SimpleNamespace(
            id="order-1",
            order_number="MC-EVIDENCE-DELETE-1",
            status="payment_review",
            payment_state="unpaid",
            archived_at=None,
            grand_total=120,
            currency="UZS",
        )
        payment = SimpleNamespace(id="payment-1")
        evidence = SimpleNamespace(storage_key="evidence-1.png")
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=order),
            execute=AsyncMock(
                side_effect=[
                    FakeResult([payment]),
                    FakeResult([SimpleNamespace(status="sent")]),
                    FakeResult([evidence]),
                    *[FakeResult() for _ in range(13)],
                ]
            ),
            add=unittest.mock.Mock(),
            commit=AsyncMock(),
        )

        with patch("routers.manual_orders.delete_evidence_file") as delete_file:
            result = await permanently_delete_admin_order(
                "MC-EVIDENCE-DELETE-1", SimpleNamespace(id="admin-1"), session, None
            )

        self.assertTrue(result["deleted"])
        self.assertEqual(session.execute.await_count, 16)
        delete_tables = [
            str(call.args[0]).upper().split(" FROM ", 1)[1].split(" ", 1)[0]
            for call in session.execute.await_args_list
            if str(call.args[0]).lstrip().upper().startswith("DELETE")
        ]
        self.assertEqual(
            delete_tables,
            [
                "MANUAL_PAYMENT_EVIDENCE",
                "PAYMENT_EVENTS",
                "TELEGRAM_PAYMENT_NOTIFICATION_OUTBOX",
                "PAYMENTS",
                "ORDER_ITEMS",
                "ORDER_FULFILLMENT_STAGES",
                "TELEGRAM_ORDER_NOTIFICATION_OUTBOX",
                "SELLER_ORDER_FULFILLMENTS",
                "ORDERS",
            ],
        )
        delete_file.assert_called_once_with("evidence-1.png")
        session.add.assert_called_once()
        session.commit.assert_awaited_once()


class TelegramInquiryDeletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_permanent_delete_removes_only_the_inquiry_and_audits(self):
        inquiry = SimpleNamespace(
            id="inquiry-1",
            reference="SC-DELETE-1",
            order_id=None,
            status="sent",
            snapshot={"items": [{"sku": "SKU-1"}], "subtotal": 500, "currency": "UZS"},
        )
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=inquiry),
            delete=AsyncMock(),
            commit=AsyncMock(),
        )

        with patch("routers.manual_orders.audit", new_callable=AsyncMock) as audit_log:
            result = await permanently_delete_admin_telegram_inquiry(
                "SC-DELETE-1", SimpleNamespace(id="admin-1"), session, None
            )

        self.assertEqual(
            result,
            {"reference": "SC-DELETE-1", "deleted": True, "scope": "cms"},
        )
        session.delete.assert_awaited_once_with(inquiry)
        session.commit.assert_awaited_once()
        audit_log.assert_awaited_once()
        statement = str(session.scalar.await_args.args[0]).upper()
        self.assertIn("FOR UPDATE", statement)

    async def test_permanent_delete_refuses_an_inquiry_already_linked_to_an_order(self):
        inquiry = SimpleNamespace(reference="SC-CONVERTED-1", order_id="order-1")
        session = SimpleNamespace(scalar=AsyncMock(return_value=inquiry), delete=AsyncMock(), commit=AsyncMock())

        with self.assertRaises(HTTPException) as caught:
            await permanently_delete_admin_telegram_inquiry(
                "SC-CONVERTED-1", SimpleNamespace(id="admin-1"), session, None
            )

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.detail["error"], "inquiry_already_converted")
        session.delete.assert_not_awaited()
        session.commit.assert_not_awaited()


class TelegramInboxPendingConversionTests(unittest.IsolatedAsyncioTestCase):
    async def test_pending_inbox_request_converts_through_shared_manual_order_flow(self):
        inquiry = SimpleNamespace(
            id="inquiry-1",
            reference="SC-INBOX-1",
            order_id=None,
            status="sent",
            source="telegram_inbox",
            expires_at=None,
            telegram_chat_id=123,
            telegram_connection_id="connection-1",
            conversation_id="conversation-1",
            user_id=None,
            snapshot={
                "currency": "UZS",
                "subtotal": 100,
                "items": [{
                    "sku": "SKU-1",
                    "name": "Product One",
                    "quantity": 1,
                    "unit_price": 100,
                    "line_total": 100,
                    "_candidate_id": "candidate-1",
                }],
                "_candidate_ids": ["candidate-1"],
            },
        )
        variant = SimpleNamespace(
            id="variant-1",
            sku="SKU-1",
            product_id="product-1",
            is_active=True,
            sale_price_override=None,
            price_override=None,
            option_values={},
        )
        product = SimpleNamespace(
            id="product-1",
            status="active",
            base_price=100,
            slug="product-one",
            seller_id="seller-1",
        )
        candidate = SimpleNamespace(
            id="candidate-1",
            conversation_id="conversation-1",
            status="pending_order",
            order_id=None,
        )
        added = []

        def add(row):
            if isinstance(row, orders.Order) and row.id is None:
                row.id = "order-1"
            added.append(row)

        session = SimpleNamespace(
            scalar=AsyncMock(return_value=inquiry),
            execute=AsyncMock(side_effect=[FakeResult([variant]), FakeResult([candidate])]),
            get=AsyncMock(return_value=product),
            add=add,
            flush=AsyncMock(),
            commit=AsyncMock(),
            rollback=AsyncMock(),
        )
        payload = ManualOrderCreateIn(
            guest_email="customer@example.com",
            shipping_address={
                "recipient_name": "Customer One",
                "phone": "+998901234567",
                "address_line_1": "Tashkent",
                "city": "Tashkent",
                "country_code": "UZ",
            },
        )
        expected = {"order_number": "MC-ORDER-1", "status": "pending_payment"}

        with (
            patch("routers.manual_orders._queue_payment_prompt") as queue_prompt,
            patch("routers.manual_orders.audit", new_callable=AsyncMock),
            patch("routers.manual_orders._admin_order_payload", new_callable=AsyncMock, return_value=expected),
        ):
            result = await create_manual_order(
                "SC-INBOX-1",
                payload,
                user=SimpleNamespace(id="admin-1"),
                session=session,
                idempotency_key=None,
            )

        order = next(row for row in added if isinstance(row, orders.Order))
        self.assertEqual(result, expected)
        self.assertEqual(order.order_source, "telegram_inbox")
        self.assertEqual(order.telegram_conversation_id, "conversation-1")
        self.assertEqual(candidate.status, "ordered")
        self.assertEqual(candidate.order_id, "order-1")
        self.assertEqual(inquiry.order_id, "order-1")
        self.assertEqual(inquiry.status, "order_created")
        self.assertIsNone(inquiry.snapshot)
        queue_prompt.assert_called_once()
        session.commit.assert_awaited_once()

    async def test_permanent_delete_waits_while_telegram_is_sending(self):
        import time

        inquiry = SimpleNamespace(
            reference="SC-SENDING-1",
            order_id=None,
            status="sending",
            snapshot={"_delivery": {"started": time.time()}},
        )
        session = SimpleNamespace(scalar=AsyncMock(return_value=inquiry), delete=AsyncMock(), commit=AsyncMock())

        with self.assertRaises(HTTPException) as caught:
            await permanently_delete_admin_telegram_inquiry(
                "SC-SENDING-1", SimpleNamespace(id="admin-1"), session, None
            )

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.detail["error"], "inquiry_delivery_in_progress")
        session.delete.assert_not_awaited()
        session.commit.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
