# Pre-deployment checklist

## Must pass before go-live

- [ ] Production secrets are present and no payment provider is configured before its implementation is certified. No mock provider is enabled.
- [ ] `/api/ready` returns 200 with database migrations, notification, media and rate-limit checks up. While checkout is disabled, `payment=disabled` and `checkout_enabled=false` are expected.
- [ ] The official operator account is the only admin/catalog owner; legacy seller accounts are inactive and seller routes return 404.
- [ ] Redis is reachable from every API worker and `/api/ready` reports `rate_limit_store=up`.
- [ ] PostgreSQL and persistent media backup/restore have been tested on disposable targets; local media uses a persistent volume and an off-server copy of the archive.
- [ ] While checkout is disabled, product/cart/checkout UI clearly states that online purchase is unavailable and quote/order/payment endpoints cannot create state.
- [ ] A future payment workflow is implemented and certified before checkout is enabled.
- [ ] CMS draft/publish/unpublish, preview token, media upload, public page and FAQ flows work.
- [ ] Product/category/variant validation blocks invalid prices, duplicate SKUs and unsafe text.
- [ ] Frontend production build succeeds; missing images and API failures have usable fallback states.
- [ ] Browser smoke and security checks pass against the release candidate.
- [ ] Monitoring, alert contacts and the rollback owner are assigned.
