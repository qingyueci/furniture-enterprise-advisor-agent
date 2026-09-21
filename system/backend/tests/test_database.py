"""Opt-in, transaction-rolled-back integration tests against the project database."""
import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from app.core.database import get_engine
from app.models import Product, ProductPrice, User

pytestmark = pytest.mark.skipif(os.getenv('RUN_DATABASE_TESTS') != '1', reason='Set RUN_DATABASE_TESTS=1 after project database migration')


def test_database_constraints():
    with get_engine().connect() as connection:
        transaction = connection.begin()
        try:
            product_id = connection.scalar(insert(Product).values(
                product_name='事务测试', model=str(uuid4()), brand='TEST_ONLY', product_type='INTERNAL',
            ).returning(Product.id))
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(insert(ProductPrice).values(
                    product_id=product_id, price=Decimal('-0.01'), price_type='GUIDE',
                    source='TEST_ONLY', update_time=datetime.now(timezone.utc),
                ))
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(insert(User).values(username=str(uuid4()), password_hash='TEST_ONLY', role='INVALID', status='ACTIVE'))
            assert connection.scalar(select(Product.id).where(Product.id == product_id)) == product_id
        finally:
            transaction.rollback()
