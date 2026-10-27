from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.router import api_router
from backend.app.core.config import get_settings
from backend.app.schemas.system import ServiceInfoResponse

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI Research Hub 后端接口",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.get("/", response_model=ServiceInfoResponse, tags=["system"])
async def service_info(request: Request) -> ServiceInfoResponse:
    base_url = str(request.base_url).rstrip("/")
    return ServiceInfoResponse(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        docs_url=f"{base_url}{app.docs_url}",
        health_url=f"{base_url}{settings.api_v1_prefix}/health",
    )


app.include_router(api_router, prefix=settings.api_v1_prefix)
