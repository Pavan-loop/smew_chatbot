import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Language = Literal["en", "kn", "kanglish"]
SERVICES = (
    "main gate",
    "safety door",
    "rolling shutter",
    "window grill",
    "staircase railing",
    "collapsible gate",
    "compound wall",
    "garage door",
    "MS fabrication",
    "steel structure",
    "repairs and welding",
    "custom order",
)


class State(BaseModel):
    service: str | None = None
    purpose: Literal["home", "commercial"] | None = None
    material: Literal["MS", "SS"] | None = None
    size: str | None = None
    design_preference: Literal["own", "recommend"] | None = None
    location: str | None = None
    area_status: Literal["served", "unserved", "uncertain"] = "uncertain"
    timeline: str | None = None
    preferred_time: str | None = None
    contact_consent: bool | None = None
    language: Language = "en"

    def summary(self) -> str:
        return "; ".join(
            f"{k}: {v}"
            for k, v in self.model_dump().items()
            if v is not None and k not in ("language", "contact_consent", "area_status")
        )


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service: str | None
    purpose: Literal["home", "commercial"] | None
    material: Literal["MS", "SS"] | None
    size: str | None
    design_preference: Literal["own", "recommend"] | None
    location: str | None
    area_status: Literal["served", "unserved", "uncertain"] | None
    timeline: str | None
    preferred_time: str | None
    contact_consent: bool | None
    language: Language
    is_ack: bool
    asks_price: bool
    shares_phone: bool

    @field_validator("service", "size", "location", "timeline", "preferred_time")
    @classmethod
    def short_text(cls, value: str | None):
        return value.strip()[:160] if value and value.strip() else None


class SessionMemory(BaseModel):
    state: State = Field(default_factory=State)
    turn: int = 0
    asked: dict[str, int] = Field(default_factory=dict)
    asked_turn: dict[str, int] = Field(default_factory=dict)
    awaiting: str | None = None
    form_shows: int = 0
    last_form_turn: int = -100
    lead_saved: bool = False


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=500)
    request_id: UUID
    language: Language = "en"

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str):
        if not value.strip():
            raise ValueError("Message cannot be blank")
        return value.strip()


class LeadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    phone: str = Field(min_length=10, max_length=20)
    name: str | None = Field(default=None, max_length=100)
    consent: Literal[True]

    @field_validator("consent", mode="before")
    @classmethod
    def explicit_consent(cls, value):
        if value is not True:
            raise ValueError("Explicit consent must be true")
        return value

    @field_validator("phone")
    @classmethod
    def mobile(cls, value: str):
        if not re.fullmatch(r"[+\d\s()-]+", value):
            raise ValueError("Enter a valid Indian mobile number")
        digits = re.sub(r"\D", "", value)
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        elif len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]
        if not re.fullmatch(r"[6-9]\d{9}", digits):
            raise ValueError("Enter a valid Indian mobile number")
        if digits == "9986464819":
            raise ValueError("Please enter your number, rather than the workshop's number")
        return digits

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None):
        return value.strip() if value and value.strip() else None


class LeadUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["new", "contacted", "closed"]
