"""Business onboarding and versioned transaction questions."""
from alembic import op
import sqlalchemy as sa
revision='b72e19aa0010'
down_revision='b72c4e91f630'
branch_labels=None
depends_on=None

def upgrade():
    existing={c['name'] for c in sa.inspect(op.get_bind()).get_columns('tax_profiles_v2')}
    columns=[sa.Column('tax_type',sa.String(),nullable=True),sa.Column('business_description',sa.String(),nullable=True),sa.Column('operating_industry',sa.String(),nullable=True),sa.Column('has_employees',sa.Boolean(),nullable=True),sa.Column('onboarding_completed',sa.Boolean(),nullable=False,server_default=sa.false())]
    for c in columns:
        if c.name not in existing:op.add_column('tax_profiles_v2',c)
    op.add_column('transactions',sa.Column('question_answers_json',sa.String(),nullable=False,server_default='{}'))
    op.add_column('transactions',sa.Column('question_rule_version',sa.String(),nullable=True))

def downgrade():
    op.drop_column('transactions','question_rule_version');op.drop_column('transactions','question_answers_json')
    for n in ('onboarding_completed','has_employees','operating_industry','business_description'):op.drop_column('tax_profiles_v2',n)
