"""Idempotent seed for auth accounts (admin / demo customer / demo seller).

Run: python3 seed_accounts.py
Passwords come from SEED_* env vars — never hardcoded.
"""

import asyncio
import os

from sqlalchemy import select

from auth import hash_password
from db.models import SellerProfile, User
from db.session import SessionLocal

ACCOUNTS = [
    ("SEED_ADMIN_EMAIL", "SEED_ADMIN_PASSWORD", "admin", "Platform", "Owner"),
    ("SEED_SELLER_EMAIL", "SEED_SELLER_PASSWORD", "seller", "UNIQLO Products", "Partner"),
    ("SEED_CUSTOMER_EMAIL", "SEED_CUSTOMER_PASSWORD", "customer", "Demo", "Customer"),
    ("SEED_SELLER2_EMAIL", "SEED_SELLER2_PASSWORD", "seller", "Tropical Glow", "Beauty"),
]


async def seed():
    async with SessionLocal() as session:
        for email_env, password_env, role, first, last in ACCOUNTS:
            email = os.environ.get(email_env, "").strip().lower()
            password = os.environ.get(password_env, "")
            if not email or not password:
                print(f"SKIP {role}: {email_env}/{password_env} not set")
                continue
            user = await session.scalar(select(User).where(User.email == email))
            if user:
                user.role = role if user.role in ("customer", role) else user.role
                user.password_hash = hash_password(password)
                user.is_active = True
                user.token_version += 1
                action = "updated"
            else:
                user = User(
                    email=email,
                    first_name=first,
                    last_name=last,
                    full_name=f"{first} {last}".strip(),
                    role=role,
                    preferred_locale="id",
                    password_hash=hash_password(password),
                )
                session.add(user)
                action = "created"
            if role == "seller":
                await session.flush()
                profile = await session.scalar(
                    select(SellerProfile).where(SellerProfile.user_id == user.id)
                )
                if not profile:
                    store = f"{first} {last}".strip()
                    session.add(
                        SellerProfile(
                            user_id=user.id,
                            store_name=store,
                            slug=email.split("@")[0].replace(".", "-"),
                        )
                    )
                    print(f"  + seller_profile: {store}")
            print(f"{action}: {email} ({role})")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
