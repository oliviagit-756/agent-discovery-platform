from pydantic import BaseModel, HttpUrl, Field

class AgentCreate(BaseModel):
    name: str
    description: str
    endpoint: HttpUrl


class UsageCreate(BaseModel):
    caller: str
    target: str
    units: int = Field(..., gt=0)
    request_id: str