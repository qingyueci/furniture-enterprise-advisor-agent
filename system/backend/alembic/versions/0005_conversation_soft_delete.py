"""Add reversible conversation deletion marker."""
from alembic import op
import sqlalchemy as sa

revision = "0005_conversation_soft_delete"
down_revision = "0004_price_basis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_conversations_deleted_at", "conversations", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_conversations_deleted_at", table_name="conversations")
    op.drop_column("conversations", "deleted_at")
