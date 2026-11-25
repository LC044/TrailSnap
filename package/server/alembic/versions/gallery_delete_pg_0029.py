"""Index referencing rows visited during bulk gallery deletion."""
from alembic import op

revision = 'gallery_delete_pg_0029'
down_revision = 'llm_usage_pg_0028'
branch_labels = None
depends_on = None

REFERENCES = (
    ('albums', 'cover'),
    ('photo_tags', 'cover_id'),
    ('memories', 'cover_photo_id'),
    ('life_chapters', 'cover_photo_id'),
    ('daily_frames', 'photo_id'),
    ('face_identities', 'default_face_id'),
    ('face_clusters', 'anchor_face_id'),
)


def upgrade() -> None:
    for table, column in REFERENCES:
        op.create_index(f'ix_{table}_{column}', table, [column])


def downgrade() -> None:
    for table, column in reversed(REFERENCES):
        op.drop_index(f'ix_{table}_{column}', table_name=table)
