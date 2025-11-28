# app/api/routers.py

from fastapi import APIRouter

from app.api.v1.routes import auth, user, gdpr, wallet, admin, group

main_router = APIRouter()

main_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
main_router.include_router(user.router, prefix="/user", tags=["Account Management"])
main_router.include_router(gdpr.router, prefix="/gdpr", tags=["GDPR & Privacy"])
main_router.include_router(wallet.router, prefix="/wallet", tags=["Wallet & Transaction"])
main_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
main_router.include_router(group.router, prefix="/groups", tags=["Groups"])
