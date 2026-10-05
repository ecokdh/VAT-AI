"""Join business-profile and document-AI migrations without rewriting either history."""
from typing import Sequence

revision: str = "20261005a6"
down_revision: Sequence[str] = ("015d7b1f7bdb", "20261005a5")
branch_labels = depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
