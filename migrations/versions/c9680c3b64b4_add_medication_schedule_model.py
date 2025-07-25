"""add medication schedule model

Revision ID: c9680c3b64b4
Revises: 
Create Date: 2025-07-19 15:08:55.774132

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9680c3b64b4'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('medication_schedule',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('nama_obat', sa.String(length=128), nullable=False),
    sa.Column('interval_jam', sa.Integer(), nullable=False),
    sa.Column('waktu_mulai', sa.DateTime(), nullable=False),
    sa.Column('catatan', sa.String(length=256), nullable=True),
    sa.Column('aktif', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('medication_schedule')
    # ### end Alembic commands ###
