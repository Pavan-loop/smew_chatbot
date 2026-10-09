import asyncio
import csv
import fcntl
import io
import json
import logging
import os
import re
import secrets
import tempfile
import time
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

from app.brain import (
    REVIEWED_MODES,
    business_info_reply,
    business_question,
    conversational_reply,
    merge,
    normalize_turn,
    outside_service_area,
    plan_turn,
    polish_answer,
    reviewed_reply,
    social_prefix,
    text,
    validated_reply,
)
from app.config import Settings
from app.database import Database, RateExceeded
from app.models import ChatRequest, LeadRequest, LeadUpdate
from app.notifications import NotificationWorker
from app.providers import OpenAIProvider, ProviderError
from app.security import SessionSigner, bearer, redact_phones

log = logging.getLogger("smew")


class RequestGuard:
    """Bound request bytes before JSON parsing, including chunked requests."""

    def __init__(self, app, origins: list[str]):
        self.app, self.origins = app, origins

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        origin = headers.get(b"origin", b"").decode(errors="replace")
        if origin and origin not in self.origins:
            return await JSONResponse({"detail": "Origin not allowed"}, status_code=403)(scope, receive, send)
        if scope["method"] in ("POST", "PATCH", "PUT"):
            chunks, size = [], 0
            while True:
                event = await receive()
                if event["type"] == "http.disconnect":
                    return
                chunk = event.get("body", b"")
                size += len(chunk)
                if size > 16384:
                    return await JSONResponse({"detail": "Request is too large"}, status_code=413)(
                        scope, receive, send
                    )
                chunks.append(chunk)
                if not event.get("more_body", False):
                    break
            body = b"".join(chunks)
            delivered = False

            async def buffered_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            inner_receive = buffered_receive
        else:
            inner_receive = receive
        correlation = str(uuid.uuid4())

        async def secure_send(event):
            if event["type"] == "http.response.start":
                extra = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-request-id", correlation.encode()),
                    (b"referrer-policy", b"no-referrer"),
                ]
                if scope["path"].startswith("/api/"):
                    extra.append((b"cache-control", b"no-store"))
                event["headers"] = list(event.get("headers", [])) + extra
            await send(event)

        await self.app(scope, inner_receive, secure_send)


def sse(event: dict) -> str:
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"


def create_app(settings: Settings | None = None, provider=None) -> FastAPI:
    settings = settings or Settings()
    database = Database(settings.database_path)
    signer = SessionSigner(
        settings.session_secret.get_secret_value(),
        settings.session_days,
        settings.client_ip_header,
        settings.trust_forwarded_for,
    )
    locks: dict[str, asyncio.Lock] = {}
    semaphore = asyncio.Semaphore(settings.max_concurrent_chats)
    business = json.loads(settings.business_file.read_text())
    # The workshop's own numbers are not customer data and stay readable in chat.
    workshop_numbers = tuple(
        str(business.get(key, ""))[-10:] for key in ("phone", "whatsapp") if business.get(key)
    )

    @asynccontextmanager
    async def lifespan(application):
        os.umask(0o077)
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        lockfile = settings.database_path.with_suffix(".app.lock").open("a")
        try:
            fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lockfile.close()
            raise RuntimeError("Run exactly one backend worker/replica per database") from None
        try:
            await asyncio.to_thread(database.initialize)
            settings.database_path.chmod(0o600)
            connections = httpx.Limits(max_connections=settings.max_concurrent_chats + 4)
            async with httpx.AsyncClient(trust_env=False, limits=connections) as client:
                application.state.provider = provider or OpenAIProvider(settings, client)
                worker = NotificationWorker(settings, database, client)
                application.state.worker = worker
                task = asyncio.create_task(worker.run()) if settings.worker_enabled else None
                try:
                    yield
                finally:
                    if task:
                        task.cancel()
                        with suppress(asyncio.CancelledError):
                            await task
        finally:
            fcntl.flock(lockfile.fileno(), fcntl.LOCK_UN)
            lockfile.close()

    application = FastAPI(
        title="SMEW Assistant",
        version="2.0.0",
        lifespan=lifespan,
        docs_url=None if settings.environment == "production" else "/docs",
        redoc_url=None,
        openapi_url=None if settings.environment == "production" else "/openapi.json",
    )
    application.state.database = database
    application.state.settings = settings
    application.state.signer = signer
    application.add_middleware(RequestGuard, origins=settings.allowed_origins)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=["Retry-After", "X-Request-ID"],
    )

    @application.exception_handler(RateExceeded)
    async def rate_error(request, exc):
        return JSONResponse(
            {"detail": "Too many requests. Please try again later or contact the workshop."},
            status_code=429,
            headers={"Retry-After": "60"},
        )

    async def limit(request: Request, kind: str, per_minute: int):
        ip = signer.ip_key(request)
        await asyncio.to_thread(database.consume_limits, [(f"{kind}:ip:{ip}", 60, per_minute)])

    async def session_id(request: Request) -> str:
        sid = signer.verify(bearer(request))
        memory = await asyncio.to_thread(database.load_session, sid)
        if memory is None:
            raise HTTPException(401, "Session expired. Start a new conversation.")
        return sid

    async def admin(request: Request):
        expected = settings.admin_token.get_secret_value()
        if not expected:
            raise HTTPException(503, "Administration is not configured")
        try:
            token = bearer(request)
        except HTTPException:
            token = ""
        if not token or not secrets.compare_digest(token.encode(), expected.encode()):
            # Only failures consume this bucket, so anonymous traffic cannot lock out a valid token.
            await limit(request, "admin-fail", 10)
            raise HTTPException(401, "Invalid admin credentials")
        await limit(request, "admin", 120)

    @application.get("/healthz")
    async def health():
        return {"status": "ok"}

    @application.get("/readyz")
    async def ready():
        try:
            await asyncio.to_thread(database.ready)
            if settings.worker_enabled and time.time() - application.state.worker.last_tick > 60:
                return JSONResponse({"status": "not_ready"}, status_code=503)
            return {"status": "ready"}
        except Exception:
            return JSONResponse({"status": "not_ready"}, status_code=503)

    @application.post("/api/session")
    async def new_session(request: Request):
        await limit(request, "session", 10)
        await asyncio.to_thread(database.consume_limits, [("sessions:global", 86400, 200)])
        sid = secrets.token_urlsafe(24)
        await asyncio.to_thread(database.create_session, sid)
        return {"session_token": signer.issue(sid), "visitor_id": sid, "protocol": 2}

    @application.get("/api/session")
    async def read_session(request: Request, sid: str = Depends(session_id)):
        await limit(request, "session-read", 30)
        memory = await asyncio.to_thread(database.load_session, sid)
        history = await asyncio.to_thread(database.history, sid, 40)
        if memory.lead_saved:
            for m in history:
                m["action"] = None
        return {"messages": history, "lead_captured": memory.lead_saved, "language": memory.state.language}

    async def build_events(sid: str, body: ChatRequest, phone_shared: bool = False):
        # body.message is already phone-redacted; phone_shared records that a number was typed.
        memory = await asyncio.to_thread(database.load_session, sid)
        original = memory.model_copy(deep=True)
        history = await asyncio.to_thread(database.history, sid)
        last = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), "")
        try:
            async with asyncio.timeout(50):
                memory.turn += 1
                language = "kn" if re.search(r"[\u0c80-\u0cff]", body.message) else body.language
                reply = conversational_reply(memory, body.message, language, last)
                if reply is None:
                    reply = business_info_reply(body.message, language, business)
                show_form = False
                if reply is not None:
                    memory.state.language = language
                else:
                    previous_awaiting = memory.awaiting
                    patch, usage = await application.state.provider.extract(
                        history, body.message, memory, business
                    )
                    await asyncio.to_thread(database.record_usage, settings.extractor_model, usage)
                    if phone_shared:
                        # The model only sees a masked number; the server knows one was shared.
                        patch = patch.model_copy(update={"shares_phone": True})
                    patch = normalize_turn(memory, patch, body.message, business)
                    merge(memory, patch, body.language)
                    plan = plan_turn(memory, patch, business)
                    show_form = plan.show_form
                    needs_answer = business_question(body.message)
                    use_reviewed = (
                        patch.asks_price
                        or patch.design_preference == "recommend"
                        or plan.mode in ("out_of_area", "declined", "ack")
                        or (plan.mode in REVIEWED_MODES and not needs_answer)
                    )
                    if use_reviewed:
                        reply = reviewed_reply(
                            memory, patch, plan, body.message, previous_awaiting, last, business, needs_answer
                        )
                    else:
                        reply, usage = await application.state.provider.reply(
                            history, body.message, memory, "", business
                        )
                        await asyncio.to_thread(database.record_usage, settings.chat_model, usage)
                        reply, valid = validated_reply(reply, memory, plan, business)
                        if not valid:
                            await asyncio.to_thread(database.error, "reply_guardrail")
                        else:
                            # The model answers facts; the server owns the next enquiry question.
                            answer = polish_answer(
                                " ".join(
                                    sentence
                                    for sentence in re.split(r"(?<=[.!?])\s+", reply)
                                    if not sentence.rstrip().endswith("?")
                                )
                            )
                            followup = (
                                reviewed_reply(
                                    memory, patch, plan, body.message, previous_awaiting, last, business, True
                                )
                                if plan.mode in REVIEWED_MODES
                                else ""
                            )
                            reply = " ".join(part for part in (answer, followup) if part) or text(
                                memory.state.language, "help"
                            )
                    reply = social_prefix(body.message, memory.state.language) + reply
                if reply.strip() == last.strip():
                    # Never send the exact same message twice in a row.
                    reply = text(memory.state.language, "recap") + reply
                events = [{"type": "text", "text": reply, "language": memory.state.language}]
                if show_form:
                    events.append(
                        {
                            "type": "action",
                            "action": "show_lead_form",
                            "service": memory.state.service,
                            "notes": memory.state.summary(),
                            "language": memory.state.language,
                        }
                    )
        except (ProviderError, TimeoutError) as exc:
            code = str(exc) if isinstance(exc, ProviderError) else "chat_overall_timeout"
            await asyncio.to_thread(database.error, code)
            log.warning("chat_provider_failed code=%s", code)
            memory = original
            memory.turn += 1
            memory.state.language = body.language
            reply = text(body.language, "failure")
            events = [{"type": "error", "text": reply}]
        events.append({"type": "done"})
        await asyncio.to_thread(
            database.save_turn, sid, str(body.request_id), body.message, reply, memory, events
        )
        return events

    @application.post("/api/chat")
    async def chat(body: ChatRequest, request: Request, sid: str = Depends(session_id)):
        await limit(request, "chat", 20)
        # Customer phone numbers typed into chat are masked before storage and before any LLM call.
        redacted, phone_shared = redact_phones(body.message, workshop_numbers)
        body = body.model_copy(update={"message": redacted})
        lock = locks.setdefault(sid, asyncio.Lock())
        if lock.locked():
            raise HTTPException(409, "A request is already running in this conversation")
        await lock.acquire()
        acquired_slot = False
        try:
            cached = await asyncio.to_thread(database.cached_chat, sid, str(body.request_id))
            if cached:
                if cached[0] != body.message:
                    raise HTTPException(409, "Request ID was already used for another message")
            else:
                try:
                    await asyncio.wait_for(semaphore.acquire(), timeout=0.1)
                    acquired_slot = True
                except TimeoutError:
                    raise HTTPException(503, "The assistant is busy. Please try again shortly.") from None
                await asyncio.to_thread(
                    database.consume_limits,
                    [
                        ("chats:global", 86400, settings.max_daily_chat_requests),
                        (f"chats:session:{sid}", 86400, 50),
                    ],
                )
        except BaseException:
            lock.release()
            locks.pop(sid, None)
            if acquired_slot:
                semaphore.release()
            raise

        async def events():
            task = None
            try:
                yield sse({"type": "visitor", "visitor_id": sid, "protocol": 2})
                if cached:
                    result = cached[1]
                else:
                    task = asyncio.create_task(build_events(sid, body, phone_shared))
                    while not task.done():
                        done, _ = await asyncio.wait({task}, timeout=8)
                        if not done:
                            yield sse({"type": "ping"})
                    result = task.result()
                # Buffer the model output for validation, then deliver an SSE reply.
                # Persistence completes before any reply or form confirmation is sent.
                for event in result:
                    yield sse(event)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.to_thread(database.error, "chat_internal_error")
                log.exception("chat_internal_error")
                yield sse({"type": "error", "text": text(body.language, "failure")})
                yield sse({"type": "done"})
            finally:
                if task and not task.done():
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
                if acquired_slot:
                    semaphore.release()
                lock.release()
                locks.pop(sid, None)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
        )

    @application.post("/api/lead")
    async def lead(body: LeadRequest, request: Request, sid: str = Depends(session_id)):
        await limit(request, "lead", 5)
        lock = locks.setdefault(sid, asyncio.Lock())
        if lock.locked():
            raise HTTPException(409, "Please wait for the current chat reply")
        async with lock:
            try:
                memory = await asyncio.to_thread(database.load_session, sid)
                if not memory.form_shows:
                    # The callback form is only offered by plan_turn after consent; direct posts are refused.
                    raise HTTPException(409, "Please continue the chat until the callback form is offered")
                if outside_service_area(memory, business):
                    raise HTTPException(422, "That location is outside our service area")
                await asyncio.to_thread(
                    database.consume_limits,
                    [
                        (f"leads:session:{sid}", 86400, 3),
                        (f"leads:ip:{signer.ip_key(request)}", 86400, 5),
                        ("leads:global", 86400, settings.max_daily_leads),
                    ],
                )
                consent_text = "I agree that SMEW may save my number and contact me about this enquiry."
                saved, duplicate = await asyncio.to_thread(
                    database.save_lead, sid, str(body.request_id), body.phone, body.name, consent_text
                )
                return {
                    "ok": True,
                    "lead_id": saved["id"],
                    "duplicate": duplicate,
                    "notification_status": "queued",
                    "message": text(memory.state.language, "saved"),
                }
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from None
            finally:
                locks.pop(sid, None)

    @application.get("/api/admin/summary", dependencies=[Depends(admin)])
    async def summary():
        data = await asyncio.to_thread(database.summary)
        data["worker_healthy"] = (
            settings.worker_enabled and time.time() - application.state.worker.last_tick < 60
        )
        data["daily_chat_limit"] = settings.max_daily_chat_requests
        return data

    @application.get("/api/admin/leads", dependencies=[Depends(admin)])
    async def leads(limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)):
        return await asyncio.to_thread(database.leads, limit, offset)

    @application.patch("/api/admin/leads/{lid}", dependencies=[Depends(admin)])
    async def update_lead(lid: uuid.UUID, body: LeadUpdate):
        if not await asyncio.to_thread(database.update_lead, str(lid), body.status):
            raise HTTPException(404, "Lead not found")
        return {"ok": True}

    @application.delete("/api/admin/leads/{lid}", dependencies=[Depends(admin)])
    async def delete_lead(lid: uuid.UUID):
        if not await asyncio.to_thread(database.delete_lead, str(lid)):
            raise HTTPException(404, "Lead not found")
        return {"ok": True}

    @application.post("/api/admin/leads/{lid}/retry", dependencies=[Depends(admin)])
    async def retry(lid: uuid.UUID):
        try:
            exists = await asyncio.to_thread(database.retry_notification, str(lid))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        if not exists:
            raise HTTPException(404, "Lead not found")
        return {"ok": True}

    @application.get("/api/admin/export", dependencies=[Depends(admin)])
    async def export():
        rows = (await asyncio.to_thread(database.leads, 10000, 0))["items"]
        output = io.StringIO()
        columns = [
            "id",
            "created",
            "name",
            "phone",
            "service",
            "notes",
            "status",
            "notification_status",
            "consent_at",
        ]
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            # Prevent spreadsheet formula injection from untrusted names/notes.
            writer.writerow(
                {
                    k: "'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@", "\t", "\r")) else v
                    for k, v in row.items()
                }
            )
        return Response(
            output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="smew-leads.csv"'},
        )

    @application.get("/api/admin/backup", dependencies=[Depends(admin)])
    async def backup():
        descriptor, filename = tempfile.mkstemp(suffix=".sqlite3")
        os.close(descriptor)
        try:
            await asyncio.to_thread(database.backup, Path(filename))
        except BaseException:
            Path(filename).unlink(missing_ok=True)
            raise
        return FileResponse(
            filename,
            media_type="application/octet-stream",
            filename="smew-backup.sqlite3",
            background=BackgroundTask(Path(filename).unlink, missing_ok=True),
        )

    return application


app = create_app()
