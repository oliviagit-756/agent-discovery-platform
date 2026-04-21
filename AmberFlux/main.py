from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import SessionLocal, engine, Base
import models, schemas
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Agent Discovery + Usage Platform")

# -----------------------------
# DB Dependency
# -----------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -----------------------------
# LLM Tag Generator (Gemini)
# -----------------------------
def generate_tags(description: str) -> str:
    """
    Uses Google Gemini to extract 2-3 short tags from an agent description.
    Falls back to 'general' if the LLM call fails for any reason so
    agent creation never hard-fails on an external dependency.
    """
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=(
                f"Extract 2-3 short, lowercase, comma-separated tags for this agent. "
                f"Return ONLY the tags, no explanation.\n\nDescription: {description}"
            ),
        )
        return response.text.strip()
    except Exception as e:
        print("Gemini Error:", e)
        return "general"

# -----------------------------
# REQ 1: Agent Registry
# -----------------------------
@app.post("/agents")
def add_agent(agent: schemas.AgentCreate, db: Session = Depends(get_db)):
    """Register a new agent. Tags are auto-generated from the description via LLM."""
    existing = db.query(models.Agent).filter(models.Agent.name == agent.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Agent already exists")

    tags = generate_tags(agent.description)

    new_agent = models.Agent(
        name=agent.name,
        description=agent.description,
        endpoint=str(agent.endpoint),
        tags=tags,
    )

    db.add(new_agent)
    db.commit()

    return {"message": "Agent added", "name": agent.name, "tags": tags}


@app.get("/agents")
def list_agents(db: Session = Depends(get_db)):
    """List all registered agents."""
    return db.query(models.Agent).all()


@app.get("/search")
def search_agents(q: str, db: Session = Depends(get_db)):
    """
    Case-insensitive search across name, description, and tags.
    """
    q_lower = q.lower()
    agents = db.query(models.Agent).all()
    return [
        a
        for a in agents
        if q_lower in a.name.lower()
        or q_lower in a.description.lower()
        or q_lower in (a.tags or "").lower()
    ]

# -----------------------------
# REQ 2: Usage Logging
# -----------------------------
@app.post("/usage")
def log_usage(data: schemas.UsageCreate, db: Session = Depends(get_db)):
    """
    Log a call between two agents. Idempotent via request_id:
    - Same request_id with same payload -> silently ignored
    - Same request_id with different payload -> 409 Conflict
    """
    # Validate that both agents exist
    target = db.query(models.Agent).filter(models.Agent.name == data.target).first()
    caller = db.query(models.Agent).filter(models.Agent.name == data.caller).first()

    if not target:
        raise HTTPException(status_code=404, detail="Target agent not found")
    if not caller:
        raise HTTPException(status_code=404, detail="Caller agent not found")

    # Edge case: caller and target cannot be the same agent
    if data.caller == data.target:
        raise HTTPException(
            status_code=400, detail="Caller and target must be different agents"
        )

    # Idempotency: if request_id already exists, don't double-count.
    # We also verify the payload matches the original to catch client bugs
    # where the same request_id is reused for a different request.
    existing = (
        db.query(models.Usage)
        .filter(models.Usage.request_id == data.request_id)
        .first()
    )
    if existing:
        if (
            existing.caller != data.caller
            or existing.target != data.target
            or existing.units != data.units
        ):
            raise HTTPException(
                status_code=409,
                detail="request_id already used with a different payload",
            )
        return {"message": "Duplicate request ignored (idempotent)"}

    usage = models.Usage(
        request_id=data.request_id,
        caller=data.caller,
        target=data.target,
        units=data.units,
    )
    db.add(usage)
    db.commit()

    return {"message": "Usage logged"}


@app.get("/usage-summary")
def usage_summary(db: Session = Depends(get_db)):
    """
    Returns total units consumed per target agent.
    Aggregation is done in SQL (GROUP BY) for efficiency.
    """
    results = (
        db.query(models.Usage.target, func.sum(models.Usage.units))
        .group_by(models.Usage.target)
        .all()
    )
    return {target: int(total) for target, total in results}