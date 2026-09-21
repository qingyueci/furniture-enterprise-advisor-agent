"""Add reversible deletion markers for product and user management."""
from alembic import op
import sqlalchemy as sa

revision = "0006_product_user_soft_delete"
down_revision = "0005_conversation_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_products_deleted_at", "products", ["deleted_at"])
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_column("users", "deleted_at")
    op.drop_index("ix_products_deleted_at", table_name="products")
    op.drop_column("products", "deleted_at")
