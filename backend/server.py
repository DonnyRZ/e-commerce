from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
import logging
from pydantic import BaseModel, ConfigDict
from typing import List
from datetime import datetime

from config import CORS_ORIGINS
from db.models import StatusCheck
from db.session import SessionLocal, engine
from routers.catalog import router as catalog_router

# Create the main app without a prefix
app = FastAPI(title="MUSLIMAH CANTIK API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


class StatusCheckIn(BaseModel):
    client_name: str


class StatusCheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    client_name: str
    timestamp: datetime


@api_router.get("/")
async def root():
    return {"message": "Hello World"}


@api_router.get("/v1/health")
async def health_check():
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_status = "up"
    except Exception:
        db_status = "down"
    return {
        "status": "ok" if db_status == "up" else "degraded",
        "app": "muslimah-cantik",
        "version": "v1",
        "db": db_status,
    }


@api_router.post("/status", response_model=StatusCheckOut)
async def create_status_check(input: StatusCheckIn):
    async with SessionLocal() as session:
        row = StatusCheck(client_name=input.client_name)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


@api_router.get("/status", response_model=List[StatusCheckOut])
async def get_status_checks():
    async with SessionLocal() as session:
        result = await session.execute(
            select(StatusCheck).order_by(StatusCheck.timestamp.desc()).limit(1000)
        )
        return list(result.scalars().all())


# Include the router in the main app
app.include_router(api_router)
app.include_router(catalog_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db():
    await engine.dispose()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
