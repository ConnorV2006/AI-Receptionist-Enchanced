"""Initial database schema for AI Receptionist.

Revision ID: 0001_initial
Revises: 
Create Date: 2025-10-01

This migration creates the core tables used by the AI Receptionist
application: clinics, administrators, API keys, SMS logs and call logs.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the initial set of tables."""
    # Clinics table
    op.create_table(
        'clinic',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('slug', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('twilio_account_sid_encrypted', sa.LargeBinary(), nullable=True),
        sa.Column('twilio_auth_token_encrypted', sa.LargeBinary(), nullable=True),
        sa.Column('twilio_from_number', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
    )

    # Administrators table
    op.create_table(
        'admin',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clinic_id', sa.Integer(), nullable=True),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('is_superadmin', sa.Boolean(), server_default=sa.text('false'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinic.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username')
    )

    # API Keys table
    op.create_table(
        'api_key',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clinic_id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=128), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=True),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinic.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key')
    )

    # SMS Logs table
    op.create_table(
        'sms_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clinic_id', sa.Integer(), nullable=False),
        sa.Column('from_number', sa.String(length=20), nullable=False),
        sa.Column('to_number', sa.String(length=20), nullable=False),
        sa.Column('direction', sa.String(length=10), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('cost', sa.Numeric(), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinic.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Call Logs table
    op.create_table(
        'call_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clinic_id', sa.Integer(), nullable=False),
        sa.Column('call_sid', sa.String(length=64), nullable=True),
        sa.Column('from_number', sa.String(length=20), nullable=False),
        sa.Column('to_number', sa.String(length=20), nullable=False),
        sa.Column('direction', sa.String(length=10), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('start_time', sa.DateTime(), nullable=True),
        sa.Column('end_time', sa.DateTime(), nullable=True),
        sa.Column('duration', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinic.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Drop all tables in reverse order."""
    op.drop_table('call_log')
    op.drop_table('sms_log')
    op.drop_table('api_key')
    op.drop_table('admin')
    op.drop_table('clinic')