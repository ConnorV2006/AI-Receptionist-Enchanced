"""initial tables

Revision ID: 0001_initial
Revises: 
Create Date: 2025-10-02
"""
from alembic import op
import sqlalchemy as sa

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'clinic',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('slug', sa.String(length=50), nullable=False, unique=True),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('twilio_number', sa.String(length=20)),
        sa.Column('twilio_sid', sa.String(length=100)),
        sa.Column('twilio_token', sa.String(length=100)),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'call_log',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('clinic_id', sa.Integer(), sa.ForeignKey('clinic.id'), nullable=False),
        sa.Column('caller_number', sa.String(length=20)),
        sa.Column('call_time', sa.DateTime(), nullable=True),
        sa.Column('transcript', sa.Text()),
        sa.Column('sentiment', sa.String(length=50)),
    )
    op.create_table(
        'message_log',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('clinic_id', sa.Integer(), sa.ForeignKey('clinic.id'), nullable=False),
        sa.Column('from_number', sa.String(length=20)),
        sa.Column('to_number', sa.String(length=20)),
        sa.Column('body', sa.Text()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

def downgrade():
    op.drop_table('message_log')
    op.drop_table('call_log')
    op.drop_table('clinic')
