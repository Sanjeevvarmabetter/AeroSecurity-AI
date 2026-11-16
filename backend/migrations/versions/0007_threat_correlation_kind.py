"""allow threat_correlation analyses

Revision ID: 0007
Revises: 0006
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_ai_analyses_kind_valid"), "ai_analyses", type_="check")
    op.create_check_constraint(
        op.f("ck_ai_analyses_kind_valid"), "ai_analyses",
        "kind IN ('anomaly_explanation','aircraft_investigation','threat_correlation')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_ai_analyses_kind_valid"), "ai_analyses", type_="check")
    op.create_check_constraint(
        op.f("ck_ai_analyses_kind_valid"), "ai_analyses", "kind IN ('anomaly_explanation','aircraft_investigation')"
    )
