# app/modules/ims/schemas.py

from typing import List, Dict
from pydantic import BaseModel

class IMSInputSchema(BaseModel):
    """Input schema for IMS."""
    prompt: str

class IMSContextSchema(BaseModel):
    """Context schema for IMS service."""
    prompt: str
    user_groups: List[Dict[str, str]]
    user_goals: List[Dict[str, str]]
