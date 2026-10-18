"""Private shared benchmark membership and immutable cases."""
from alembic import op
import sqlalchemy as sa
revision='d95e31aa0012'
down_revision='c84d20aa0011'
branch_labels=None
depends_on=None
def upgrade():
    op.create_table('team_benchmark_members',sa.Column('user_id',sa.Uuid(),sa.ForeignKey('users.id'),primary_key=True),sa.Column('role',sa.String(),nullable=False),sa.Column('enabled',sa.Boolean(),nullable=False))
    op.create_table('team_benchmark_cases',sa.Column('case_id',sa.String(),primary_key=True),*[sa.Column(n,sa.String(),nullable=False) for n in ('image_key','image_sha256','category','tags_json','gold_json','prediction_json','metadata_json')],sa.Column('created_at',sa.DateTime(),nullable=False))
def downgrade():
    op.drop_table('team_benchmark_cases');op.drop_table('team_benchmark_members')
