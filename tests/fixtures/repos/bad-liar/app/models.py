"""Pydantic models."""

from pydantic import BaseModel


class Widget(BaseModel):
    name: str
    count: int
