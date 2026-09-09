# Auth Testing Playbook (PostgreSQL adaptation)

Auth: bcrypt hashes; JWT access (15min) + refresh (7d) in HttpOnly cookies (Secure, SameSite=lax, names access_token/refresh_token); csrf_token non-HttpOnly cookie, mutations require X-CSRF-Token header matching it; token_version invalidates sessions on password reset; reset tokens stored as sha256 hash, 1h TTL, single-use via atomic UPDATE ... RETURNING claim.

## API smoke
BASE=https://muslimah-shop.preview.emergentagent.com (or http://localhost:8001; Secure cookies need https for browser, curl handles both)
1. `curl -c cj -X POST $BASE/api/v1/auth/login -H 'Content-Type: application/json' -d '{"email":"customer.demo@muslimahcantik.id","password":"MC-Cust0mer-9d2m48Lw-2026"}'` → user JSON, sets cookies.
2. `curl -b cj $BASE/api/v1/auth/me` → same user; response must NOT contain password_hash.
3. CSRF: extract csrf cookie: `CSRF=$(grep csrf_token cj | awk '{print $NF}')`; `curl -b cj -H "X-CSRF-Token: $CSRF" -X PATCH $BASE/api/v1/auth/me -H 'Content-Type: application/json' -d '{"first_name":"Demo"}'` → 200; without header → 403 csrf_failed.
4. RBAC: /api/v1/auth/seller/ping with customer → 403; /admin/ping with customer or seller → 403; seller on seller ping → 200; admin on admin ping → 200.
5. Mass assignment: register with {"role":"admin"} → created user role is customer; PATCH /me with {"role":"admin"} → role unchanged.
6. Reset: POST forgot-password → generic 200 always; read link from backend log ("MOCK EMAIL password reset link"); POST reset-password with token → password_updated; old password login fails, new works, token reuse → 400 invalid_or_expired_token.
7. Lockout: 5 bad logins → 429 too_many_attempts (use throwaway emails to avoid locking shared accounts).
8. Addresses: POST /api/v1/account/addresses (CSRF) → first becomes is_default; second with is_default true demotes first; user A cannot PATCH/DELETE user B address (404 address_not_found).

## DB checks
psql: users.password_hash starts with $2b$; unique indexes users.email, product_variants.sku, products.slug, categories.slug; unique (product_id, locale), (category_id, locale); FK products.seller_id → users.id.
