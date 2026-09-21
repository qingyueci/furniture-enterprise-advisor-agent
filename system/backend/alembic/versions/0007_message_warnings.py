"""Persist per-message warning codes so fallbacks survive history reloads.

只增加字段，不改历史消息正文、引用或结构化结果。该字段向后兼容：升级后
旧消息取默认空数组；代码回滚时正式数据库可保留该列，不执行破坏性降级。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007_message_warnings"
down_revision = "0006_product_user_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("warnings", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("messages", "warnings")
