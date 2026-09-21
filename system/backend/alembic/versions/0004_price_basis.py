"""Nullable quotation basis; old records remain unknown, never inferred."""
from alembic import op
import sqlalchemy as sa
revision = "0004_price_basis"
down_revision = "0003_agent_message_fields"
branch_labels = None
depends_on = None

def upgrade():
    for name, size in (("quote_spec",80),("pricing_unit",20),("included_scope",500)):
        op.add_column("product_prices",sa.Column(name,sa.String(size),nullable=True))

def downgrade():
    for name in ("included_scope","pricing_unit","quote_spec"):
        op.drop_column("product_prices",name)
