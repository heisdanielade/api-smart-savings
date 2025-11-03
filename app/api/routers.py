# app/api/routers.py

from fastapi import APIRouter

from app.api.v1.routes import auth_routes
from app.api.v1.routes import user_routes

main_router = APIRouter()

main_router.include_router(auth_routes.router, prefix="/auth", tags=["Authentication"])
main_router.include_router(user_routes.router, prefix="/user", tags=["User Profile"])
