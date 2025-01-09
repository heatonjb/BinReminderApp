"""Add referral system and SMS credits

Revision ID: 8a2d4f5e1234
Revises: 6e16eeb47967
Create Date: 2025-01-09 10:47:43.934679

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
import secrets

# revision identifiers, used by Alembic.
revision = '8a2d4f5e1234'
down_revision = '6e16eeb47967'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sms_credits', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('referral_code', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('referred_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_referred_by', 'user', ['referred_by_id'], ['id'])
        batch_op.create_unique_constraint('uq_referral_code', ['referral_code'])

    # Set default values for existing users
    user_table = table('user',
        column('id', sa.Integer),
        column('sms_credits', sa.Integer),
        column('referral_code', sa.String)
    )

    # Update existing users with default values
    op.execute(
        user_table.update().values({
            'sms_credits': 6,  # Default 6 credits for existing users
            'referral_code': sa.func.substr(sa.func.md5(sa.func.random()::text), 1, 8)  # Random 8-char code
        })
    )

    # Make columns non-nullable
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('sms_credits',
                           existing_type=sa.Integer(),
                           nullable=False)
        batch_op.alter_column('referral_code',
                           existing_type=sa.String(length=10),
                           nullable=False)


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint('fk_referred_by', type_='foreignkey')
        batch_op.drop_constraint('uq_referral_code', type_='unique')
        batch_op.drop_column('referred_by_id')
        batch_op.drop_column('referral_code')
        batch_op.drop_column('sms_credits')
