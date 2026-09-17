from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth import csrf_protect, require_roles
from db.models import User, UserAddress
from db.session import get_session

router = APIRouter(prefix="/api/v1/account", tags=["account"])
require_customer = require_roles("customer")


class AddressIn(BaseModel):
    label: str = Field(default="Home", max_length=80)
    recipient_name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=3, max_length=40)
    address_line_1: str = Field(min_length=3, max_length=255)
    address_line_2: Optional[str] = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=120)
    state_province: str = Field(min_length=1, max_length=120)
    postal_code: str = Field(min_length=2, max_length=20)
    country_code: str = Field(default="ID", min_length=2, max_length=2)
    is_default: bool = False


def _address_out(a: UserAddress) -> dict:
    return {
        "id": a.id,
        "label": a.label,
        "recipient_name": a.recipient_name,
        "phone": a.phone,
        "address_line_1": a.address_line_1,
        "address_line_2": a.address_line_2,
        "city": a.city,
        "state_province": a.state_province,
        "postal_code": a.postal_code,
        "country_code": a.country_code,
        "is_default": a.is_default,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
    }


async def _owned_address(
    address_id: str, user: User, session: AsyncSession
) -> UserAddress:
    address = await session.scalar(
        select(UserAddress).where(
            UserAddress.id == address_id, UserAddress.user_id == user.id
        )
    )
    if not address:
        raise HTTPException(status_code=404, detail="address_not_found")
    return address


async def _ensure_one_default(
    session: AsyncSession, user: User
) -> None:
    """Normalize the per-customer default-address invariant.

    A PATCH may explicitly unset the current default. Always choosing a
    deterministic replacement prevents checkout from receiving an address
    list with no default (or multiple defaults after legacy data/imports).
    """

    rows = (
        await session.execute(
            select(UserAddress)
            .where(UserAddress.user_id == user.id)
            .order_by(UserAddress.created_at, UserAddress.id)
            .with_for_update()
        )
    ).scalars().all()
    if not rows:
        return
    chosen = next((row for row in rows if row.is_default), rows[0])
    await session.execute(
        update(UserAddress)
        .where(UserAddress.user_id == user.id)
        .values(is_default=False)
    )
    chosen.is_default = True


async def _lock_customer(session: AsyncSession, user: User) -> None:
    # Address defaulting is a read-modify-write operation. Locking the owner
    # serializes create/update/delete requests without relying on a fragile
    # application-level uniqueness assumption for the boolean flag.
    await session.scalar(select(User.id).where(User.id == user.id).with_for_update())


@router.get("/addresses")
async def list_addresses(
    user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.execute(
            select(UserAddress)
            .where(UserAddress.user_id == user.id)
            .order_by(UserAddress.is_default.desc(), UserAddress.created_at)
        )
    ).scalars().all()
    return [_address_out(a) for a in rows]


@router.post("/addresses", status_code=201)
async def create_address(
    payload: AddressIn,
    user: User = Depends(require_customer),
    _: None = Depends(csrf_protect),
    session: AsyncSession = Depends(get_session),
):
    await _lock_customer(session, user)
    has_any = await session.scalar(
        select(UserAddress.id).where(UserAddress.user_id == user.id).limit(1)
    )
    address = UserAddress(user_id=user.id, **payload.model_dump())
    if not has_any:
        address.is_default = True
    session.add(address)
    await session.flush()
    await _ensure_one_default(session, user)
    await session.commit()
    return _address_out(address)


@router.patch("/addresses/{address_id}")
async def update_address(
    address_id: str,
    payload: AddressIn,
    user: User = Depends(require_customer),
    _: None = Depends(csrf_protect),
    session: AsyncSession = Depends(get_session),
):
    await _lock_customer(session, user)
    address = await _owned_address(address_id, user, session)
    for key, value in payload.model_dump().items():
        setattr(address, key, value)
    await session.flush()
    await _ensure_one_default(session, user)
    await session.commit()
    return _address_out(address)


@router.delete("/addresses/{address_id}", status_code=204)
async def delete_address(
    address_id: str,
    user: User = Depends(require_customer),
    _: None = Depends(csrf_protect),
    session: AsyncSession = Depends(get_session),
):
    await _lock_customer(session, user)
    address = await _owned_address(address_id, user, session)
    await session.delete(address)
    await session.flush()
    await _ensure_one_default(session, user)
    await session.commit()
    return None
