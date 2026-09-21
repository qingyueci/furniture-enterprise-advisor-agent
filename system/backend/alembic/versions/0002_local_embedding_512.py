"""Use 512-dimensional local embeddings without converting existing vectors."""

from alembic import op

revision = "0002_local_embedding_512"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None

_EMPTY_GUARD = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM document_chunks LIMIT 1) THEN
        RAISE EXCEPTION 'document_chunks is not empty; back up and rebuild the index with the target embedding model';
    END IF;
END
$$;
"""


def upgrade() -> None:
    op.execute(_EMPTY_GUARD)
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(512)")


def downgrade() -> None:
    op.execute(_EMPTY_GUARD)
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(1536)")
