"""
Debug endpoints — read from the in-memory analytics store.
Protected by a simple token so you don't expose traffic publicly.
Add DEBUG_TOKEN to your Railway environment variables.
"""

import os
from fastapi import APIRouter, HTTPException, Query
from app.core.store import store

router = APIRouter()

DEBUG_TOKEN = os.getenv("DEBUG_TOKEN", "smew-debug-2026")


def _check(token: str | None):
    if token != DEBUG_TOKEN:
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