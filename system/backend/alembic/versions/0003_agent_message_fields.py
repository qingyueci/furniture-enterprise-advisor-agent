"""Persist Agent task type and verified structured response data."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_agent_message_fields"
down_revision = "0002_local_embedding_512"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("structured_data", postgresql.JSONB(), nullable=True))
    op.add_column("messages", sa.Column("task_type", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "task_type")
    op.drop_column("messages", "structured_data")
