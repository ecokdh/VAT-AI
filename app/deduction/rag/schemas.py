from pydantic import BaseModel, Field


class LawEmbedIn(BaseModel):
    source: str = Field(min_length=1)
    article: str | None = None
    content: str = Field(min_length=1)


class LawOut(BaseModel):
    id: int
    source: str
    article: str | None
    content: str
