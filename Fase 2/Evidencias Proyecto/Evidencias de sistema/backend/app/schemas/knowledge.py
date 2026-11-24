from typing import Literal

from pydantic import BaseModel, Field


class DocumentContentIn(BaseModel):
    content: str = Field(max_length=2_000_000)
    version: int


class DocumentPatchIn(BaseModel):
    chat_type: Literal["technical", "commercial", "both"] | None = None
    filename: str | None = Field(default=None, min_length=1, max_length=300)


class FaqIn(BaseModel):
    question: str = Field(min_length=5, max_length=300)
    answer: str = Field(min_length=5, max_length=4000)
    chat_type: Literal["technical", "commercial"]


class FaqPatchIn(BaseModel):
    question: str | None = Field(default=None, min_length=5, max_length=300)
    answer: str | None = Field(default=None, min_length=5, max_length=4000)
    chat_type: Literal["technical", "commercial"] | None = None


class SuggestionAcceptIn(BaseModel):
    answer_override: str | None = Field(default=None, max_length=4000)
    chat_type_override: Literal["technical", "commercial"] | None = None


class SuggestionsAcceptAllIn(BaseModel):
    window_days: int | None = None
