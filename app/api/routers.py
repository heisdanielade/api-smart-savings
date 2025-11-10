# app/api/routers.py

from fastapi import APIRouter

from app.api.v1.routes import auth, user, gdpr, wallet

main_router = APIRouter()

main_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
main_router.include_router(user.router, prefix="/user", tags=["User Account"])
main_router.include_router(gdpr.router, prefix="/gdpr", tags=["GDPR & Privacy"])
main_router.include_router(wallet.router, prefix="/wallet", tags=["Wallet"])
