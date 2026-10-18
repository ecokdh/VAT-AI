import uuid
from datetime import datetime,timezone
from sqlmodel import SQLModel,Field
class TeamMember(SQLModel,table=True):
    __tablename__='team_benchmark_members'
    user_id:uuid.UUID=Field(primary_key=True,foreign_key='users.id')
    role:str=Field(default='viewer',nullable=False)
    enabled:bool=Field(default=True,nullable=False)
class BenchmarkCase(SQLModel,table=True):
    __tablename__='team_benchmark_cases'
    case_id:str=Field(primary_key=True)
    image_key:str
    image_sha256:str
    category:str
    tags_json:str
    gold_json:str
    prediction_json:str
    metadata_json:str
    created_at:datetime=Field(default_factory=lambda:datetime.now(timezone.utc))
