"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

import sqlalchemy as sa  # noqa: F401 - used once the body is written

from alembic import op  # noqa: F401 - used once the body is written
${imports if imports else ""}
revision = ${repr(up_revision).replace("'", '"')}
down_revision = ${repr(down_revision).replace("'", '"')}
branch_labels = ${repr(branch_labels).replace("'", '"')}
depends_on = ${repr(depends_on).replace("'", '"')}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
