from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.models import CreditLedger, User, UserProfile


async def test_user_profile_and_ledger_round_trip(app):
    async with app.state.sessionmaker() as session:
        user = User(email="a@example.com", hashed_password="x", full_name="A")
        session.add(user)
        await session.flush()
        session.add(UserProfile(user_id=user.id, credit_balance_minutes=Decimal("30")))
        session.add(CreditLedger(user_id=user.id, delta_minutes=Decimal("30"), reason="signup_bonus"))
        await session.commit()

        found = (await session.exec(select(User).where(User.email == "a@example.com"))).one()
        profile = await session.get(UserProfile, found.id)
        assert profile.credit_balance_minutes == Decimal("30.00")


async def test_user_email_is_unique(app):
    async with app.state.sessionmaker() as session:
        session.add(User(email="dup@example.com", hashed_password="x", full_name="A"))
        await session.commit()
        session.add(User(email="dup@example.com", hashed_password="y", full_name="B"))
        with pytest.raises(IntegrityError):
            await session.commit()
