"""Add created_at field to User model

Revision ID: 7f9a2d5e1235
Revises: 08f2627e84c4
Create Date: 2025-01-12 12:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7f9a2d5e1235'
down_revision = '08f2627e84c4'
branch_labels = None
depends_on = None


def upgrade():
    # Add created_at column with default value of current timestamp
    op.add_column('user',
        sa.Column('created_at', sa.DateTime(), nullable=False, 
                  server_default=sa.text('CURRENT_TIMESTAMP'))
    )


def downgrade():
    op.drop_column('user', 'created_at')