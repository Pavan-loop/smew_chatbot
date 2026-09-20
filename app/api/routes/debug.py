"""
Debug endpoints — read from the in-memory analytics store.
Protected by a simple token so you don't expose traffic publicly.
Add DEBUG_TOKEN to your Railway environment variables.
"""

import secrets

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.core.store import store

router = APIRouter()


def _check(token: str | None):
    if not settings.debug_token:
        raise HTTPException(status_code=503, detail="Debug endpoints disabled: set DEBUG_TOKEN")
    if not secrets.compare_digest((token or "").encode(), settings.debug_token.encode()):
        raise HTTPException(status_code=401, detail="Invalid debug token")


@router.get("/debug/summary")
async def summary(token: str = Query(...)):
    _check(token)
    return store.summary()


@router.get("/debug/turns")
async def turns(token: str = Query(...)):
    _check(token)
    return store.turns_json()


@router.get("/debug/leads")
async def leads(token: str = Query(...)):
    _check(token)
    return store.leads_json()


@router.get("/debug/errors")
async def errors(token: str = Query(...)):
    _check(token)
    return store.errors_json()