from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.conversation import get_session
from app.core.leads import save_lead

router = APIRouter()


class LeadRequest(BaseModel):
    phone: str = Field(min_length=10, max_length=15)
    name: str | None = Field(default=None, max_length=100)
    service: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=1000)
    visitor_id: str | None = None


@router.post("/lead")
async def submit_lead(body: LeadRequest):
    sent = await save_lead(
        phone=body.phone,
        name=body.name,
        service=body.service,
        notes=body.notes,
        visitor_id=body.visitor_id,
    )
    if body.visitor_id:
        get_session(body.visitor_id).phone_saved = True
    return {"ok": True, "notified": sent}
