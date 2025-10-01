"""Initial database schema for AI Receptionist.

Revision ID: 0001
Revises: None
Create Date: 2025-09-30 21:00:00

This migration creates the core tables used by the application: clinic,
api_key, admin, sms_log and call_log. It mirrors the SQLAlchemy models
defined in app.py and includes indexes and constraints for uniqueness and
referential integrity.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the initial database tables."""
    # Clinic table
    op.create_table(
        'clinic',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('slug', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('twilio_account_sid_encrypted', sa.LargeBinary(), nullable=True),
        sa.Column('twilio_auth_token_encrypted', sa.LargeBinary(), nullable=True),
        sa.Column('twilio_from_number', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.UniqueConstraint('slug', name='uix_clinic_slug')
    )

    # API keys table
    op.create_table(
        'api_key',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('clinic_id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=128), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.true()),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinic.id'], name='fk_api_key_clinic_id_clinic'),
        sa.UniqueConstraint('key', name='uix_api_key_key')
    )

    # Admin table
    op.create_table(
        'admin',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('clinic_id', sa.Integer(), nullable=True),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('is_superadmin', sa.Boolean(), nullable=True, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinic.id'], name='fk_admin_clinic_id_clinic'),
        sa.UniqueConstraint('username', name='uix_admin_username')
    )

    # SMS log table
    op.create_table(
        'sms_log',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('clinic_id', sa.Integer(), nullable=False),
        sa.Column('from_number', sa.String(length=20), nullable=False),
        sa.Column('to_number', sa.String(length=20), nullable=False),
        sa.Column('direction', sa.String(length=10), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('cost', sa.Numeric(), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinic.id'], name='fk_sms_log_clinic_id_clinic')
    )

    # Call log table
    op.create_table(
        'call_log',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
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
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinic.id'], name='fk_call_log_clinic_id_clinic')
    )


def downgrade() -> None:
    """Drop all tables created in the upgrade."""
    op.drop_table('call_log')
    op.drop_table('sms_log')
    op.drop_table('admin')
    op.drop_table('api_key')
    op.drop_table('clinic')