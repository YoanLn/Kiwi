from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import documents, claims, chatbot, health, auth, voice

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="AI-powered insurance claims management platform"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5175", "http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix=settings.API_V1_PREFIX, tags=["health"])
app.include_router(auth.router, prefix=f"{settings.API_V1_PREFIX}/auth", tags=["auth"])
app.include_router(documents.router, prefix=f"{settings.API_V1_PREFIX}/documents", tags=["documents"])
app.include_router(claims.router, prefix=f"{settings.API_V1_PREFIX}/claims", tags=["claims"])
app.include_router(chatbot.router, prefix=f"{settings.API_V1_PREFIX}/chatbot", tags=["chatbot"])
app.include_router(voice.router, prefix=settings.API_V1_PREFIX, tags=["voice"])


@app.get("/")
async def root():
    return {
        "message": "LunatiX Insurance Platform API",
        "version": "1.0.0",
        "docs": "/docs"
    }
