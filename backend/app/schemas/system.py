from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ServiceInfoResponse(BaseModel):
    name: str
    version: str
    environment: str
    docs_url: str
    health_url: str


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str
    timestamp: datetime


class ReadinessResponse(BaseModel):
    status: Literal["ready"]
    database: Literal["ok"]
    timestamp: datetime

