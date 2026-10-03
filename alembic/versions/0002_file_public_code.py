"""Public share code for each file.

Revision ID: 0002_file_public_code
Revises: 0001_initial
Create Date: 2026-10-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_file_public_code"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("files", sa.Column("public_code", sa.String(length=16), nullable=True))
    op.create_index("ix_files_public_code", "files", ["public_code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_files_public_code", table_name="files")
    op.drop_column("files", "public_code")
