# Pre-deployment checklist

## Must pass before go-live

- [ ] Production secrets are present; either Click credentials are ready, or the explicit pre-Click profile is set (`CHECKOUT_ENABLED=false`, `PAYMENT_PROVIDER=disabled`, `CLICK_MODE=disabled`). No mock provider is enabled.
- [ ] `/api/ready` returns 200 with database migrations, notification, media and rate-limit checks up. In the pre-Click profile, `payment=disabled` and `checkout_enabled=false` are expected.
- [ ] The official operator account is the only admin/catalog owner; legacy seller accounts are inactive and seller routes return 404.
- [ ] Redis is reachable from every API worker and `/api/ready` reports `rate_limit_store=up`.
- [ ] PostgreSQL and persistent media backup/restore have been tested on disposable targets; local media uses a persistent volume and an off-server copy of the archive.
- [ ] In the pre-Click profile, product/cart/checkout UI clearly states that online purchase is unavailable and quote/order/payment callback endpoints cannot create state.
- [ ] After Click is enabled for certification, customer guest and authenticated checkout both redirect to the real hosted payment flow.
- [ ] After Click is enabled, the paid callback alone moves an order to `paid`, clears the source cart and enables fulfillment.
- [ ] After Click is enabled, failed, cancelled, expired, refunded and reconciliation-required paths are visible in the UI and Admin Console.
- [ ] After Click is enabled, refund is confirmed by the provider before the local payment becomes `refunded`.
- [ ] CMS draft/publish/unpublish, preview token, media upload, public page and FAQ flows work.
- [ ] Product/category/variant validation blocks invalid prices, duplicate SKUs and unsafe text.
- [ ] Frontend production build succeeds; missing images and API failures have usable fallback states.
- [ ] Browser smoke and security checks pass against the release candidate.
- [ ] Monitoring, alert contacts and the rollback owner are assigned.
