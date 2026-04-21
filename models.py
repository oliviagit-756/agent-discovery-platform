from sqlalchemy import Column, String, Integer
from database import Base

class Agent(Base):
    __tablename__ = "agents"

    name = Column(String, primary_key=True, index=True)
    description = Column(String)
    endpoint = Column(String)
    tags = Column(String)  # stored as comma-separated


class Usage(Base):
    __tablename__ = "usage"

    request_id = Column(String, primary_key=True)
    caller = Column(String)
    target = Column(String)
    units = Column(Integer)