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

from routers.manual_orders import (
    _workflow_counts,
    _workflow_page,
    _workflow_stage,
    archive_admin_order,
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
            {"order_number": "DONE", "status": "delivered", "stage": _workflow_stage("delivered")},
        ]

    def test_legacy_and_intermediate_statuses_map_to_visible_steps(self):
        self.assertEqual(_workflow_stage("paid"), "supplier_shipping")
        self.assertEqual(_workflow_stage("processing"), "supplier_shipping")
        self.assertEqual(_workflow_stage("shipped"), "customer_shipping")
        self.assertEqual(_workflow_stage("payment_review"), "payment")

    def test_stage_counts_include_every_status_alias_independent_of_selected_filter(self):
        status_counts = {}
        for entry in self.entries:
            status_counts[entry["status"]] = status_counts.get(entry["status"], 0) + 1
        counts = _workflow_counts(status_counts, inquiry_count=4)
        filtered, total, page = _workflow_page(
            self.entries, "supplier_shipping", page=1, page_size=20
        )

        self.assertEqual(total, 3)
        self.assertEqual(page, 1)
        self.assertEqual(len(filtered), 3)
        self.assertEqual(counts["supplier_shipping"], 3)
        self.assertEqual(counts["customer_shipping"], 2)
        self.assertEqual(counts["payment"], 2)
        self.assertEqual(counts["inquiry"], 4)
        self.assertEqual(counts["paid"], 1)
        self.assertEqual(counts["payment_review"], 1)

    def test_pagination_clamps_after_orders_move_between_stages(self):
        filtered, total, page = _workflow_page(
            self.entries, "supplier_shipping", page=99, page_size=2
        )
        self.assertEqual(total, 3)
        self.assertEqual(page, 2)
        self.assertEqual([entry["order_number"] for entry in filtered], ["SUP-LEGACY"])


class OrderWorkflowEndpointTests(unittest.IsolatedAsyncioTestCase):
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
        self.assertEqual(response["counts"]["supplier_shipping"], 5)
        self.assertEqual(response["counts"]["payment"], 1)
        self.assertEqual(response["total"], 1)

        count_query = session.execute.await_args_list[1].args[0]
        order_query = session.execute.await_args_list[2].args[0]
        self.assertIn("ARCHIVED_AT IS NULL", str(count_query).upper())
        status_filter = order_query.compile().params["status_1"]
        self.assertEqual(set(status_filter), {"paid", "processing", "supplier_shipping"})

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
        self.assertEqual(response["counts"]["supplier_shipping"], 3)
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
            execute=AsyncMock(side_effect=[FakeResult(), *[FakeResult() for _ in range(7)]]),
            add=unittest.mock.Mock(),
            commit=AsyncMock(),
        )

        result = await permanently_delete_admin_order(
            "MC-DELETE-1", SimpleNamespace(id="admin-1"), session, None
        )

        self.assertEqual(result, {"order_number": "MC-DELETE-1", "deleted": True})
        self.assertEqual(session.execute.await_count, 8)
        delete_statements = [
            str(call.args[0]).upper()
            for call in session.execute.await_args_list
            if str(call.args[0]).lstrip().upper().startswith("DELETE")
        ]
        self.assertEqual(
            [statement.split(" FROM ", 1)[1].split(" ", 1)[0] for statement in delete_statements],
            ["ORDER_ITEMS", "ORDER_FULFILLMENT_STAGES", "SELLER_ORDER_FULFILLMENTS", "ORDERS"],
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
                    *[FakeResult() for _ in range(11)],
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
        self.assertEqual(session.execute.await_count, 14)
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
