"""Smart House Scale V1 tables.

This migration is deliberately raw SQL so it can be copied into the existing
Smart House Alembic tree without requiring the scale module to own the project
metadata or an independent database.
"""

from alembic import op

revision = "c4a9f1e2b7d0"
down_revision = "b62d4f9a7e31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS health")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS health.scale_devices (
            id UUID PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            mac_address VARCHAR(17) NOT NULL UNIQUE,
            model VARCHAR(120),
            protocol VARCHAR(80),
            unit VARCHAR(10) NOT NULL DEFAULT 'kg',
            active BOOLEAN NOT NULL DEFAULT TRUE,
            last_seen_at TIMESTAMPTZ,
            last_rssi INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS health.scale_users (
            id UUID PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            avatar VARCHAR(500),
            birth_date DATE,
            height_cm NUMERIC(6,2),
            biological_sex VARCHAR(16),
            initial_reference_weight_kg NUMERIC(7,3) NOT NULL,
            target_weight_kg NUMERIC(7,3),
            auto_assign_tolerance_kg NUMERIC(6,3) NOT NULL DEFAULT 3.0,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT scale_users_positive_height CHECK (height_cm IS NULL OR height_cm > 0),
            CONSTRAINT scale_users_positive_weight CHECK (initial_reference_weight_kg > 0),
            CONSTRAINT scale_users_positive_tolerance CHECK (auto_assign_tolerance_kg > 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS health.scale_measurement_sessions (
            id UUID PRIMARY KEY,
            session_uuid UUID NOT NULL UNIQUE,
            device_id UUID NOT NULL REFERENCES health.scale_devices(id),
            started_at TIMESTAMPTZ NOT NULL,
            last_seen_at TIMESTAMPTZ NOT NULL,
            finalized_at TIMESTAMPTZ,
            advertisement_count INTEGER NOT NULL DEFAULT 0,
            stable BOOLEAN NOT NULL DEFAULT FALSE,
            final_measurement_uuid UUID,
            raw_payload JSONB
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS health.scale_measurements (
            id UUID PRIMARY KEY,
            measurement_uuid UUID NOT NULL UNIQUE,
            device_id UUID NOT NULL REFERENCES health.scale_devices(id),
            user_id UUID REFERENCES health.scale_users(id),
            measured_at TIMESTAMPTZ NOT NULL,
            received_at TIMESTAMPTZ NOT NULL,
            weight_kg NUMERIC(7,3) NOT NULL,
            original_unit VARCHAR(10) NOT NULL,
            impedance INTEGER,
            rssi INTEGER,
            raw_payload JSONB,
            stable BOOLEAN NOT NULL,
            status VARCHAR(16) NOT NULL,
            pending_reason VARCHAR(32),
            assignment_method VARCHAR(16),
            assignment_delta_kg NUMERIC(7,3),
            confidence NUMERIC(6,4),
            assigned_at TIMESTAMPTZ,
            discarded_at TIMESTAMPTZ,
            assignment_candidates JSONB NOT NULL DEFAULT '[]'::jsonb,
            session_uuid UUID REFERENCES health.scale_measurement_sessions(session_uuid),
            protocol VARCHAR(80),
            model VARCHAR(120),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT scale_measurements_status CHECK (status IN ('assigned','pending','discarded')),
            CONSTRAINT scale_measurements_pending_reason CHECK (pending_reason IS NULL OR pending_reason IN ('no_candidate','multiple_candidates','unknown_or_visitor')),
            CONSTRAINT scale_measurements_assignment_method CHECK (assignment_method IS NULL OR assignment_method IN ('automatic','manual','corrected')),
            CONSTRAINT scale_measurements_stable CHECK (stable = TRUE),
            CONSTRAINT scale_measurements_positive_weight CHECK (weight_kg > 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS health.scale_measurement_events (
            id BIGSERIAL PRIMARY KEY,
            measurement_id UUID NOT NULL REFERENCES health.scale_measurements(id) ON DELETE CASCADE,
            action VARCHAR(32) NOT NULL,
            from_status VARCHAR(16),
            to_status VARCHAR(16) NOT NULL,
            from_user_id UUID,
            to_user_id UUID,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_scale_measurements_user_time ON health.scale_measurements(user_id, measured_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_scale_measurements_device_time ON health.scale_measurements(device_id, measured_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_scale_measurements_status_time ON health.scale_measurements(status, measured_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_scale_devices_mac ON health.scale_devices(mac_address)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS health.scale_measurement_events")
    op.execute("DROP TABLE IF EXISTS health.scale_measurements")
    op.execute("DROP TABLE IF EXISTS health.scale_measurement_sessions")
    op.execute("DROP TABLE IF EXISTS health.scale_users")
    op.execute("DROP TABLE IF EXISTS health.scale_devices")
