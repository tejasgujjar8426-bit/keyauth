from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Initialize FastAPI app
app = FastAPI()

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# The database initialization happens automatically when this is imported
from database import db

# Import routers
from routes.auth import router as auth_router
from routes.apps import router as apps_router
from routes.users import router as users_router
from routes.api import router as api_router
from routes.admin import router as admin_router
from routes.health import router as health_router

# Include routers
app.include_router(auth_router)
app.include_router(apps_router)
app.include_router(users_router)
app.include_router(api_router)
app.include_router(admin_router)
app.include_router(health_router)
