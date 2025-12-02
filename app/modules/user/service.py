# app/modules/user/service.py

from typing import Any, Optional
from datetime import datetime, timezone, timedelta

from fastapi import Request, BackgroundTasks
from redis.asyncio import Redis

from app.core.utils.cache import invalidate_cache
from app.core.utils.exceptions import CustomException
from app.modules.user.models import User
from app.modules.user.schemas import UserUpdate, ChangePasswordRequest, ChangeEmailRequest
from app.modules.shared.enums import NotificationType
from app.core.security.hashing import hash_password, verify_password
from app.modules.shared.helpers import generate_secure_code


class UserService:
    def __init__(self, user_repo, notification_manager):
        self.user_repo = user_repo
        self.notification_manager = notification_manager

    @staticmethod
    async def get_user_details(current_user: User) -> dict[str, Any]:
        """
        Prepare and return profile details of the authenticated user.
        """
        user_initial = ''.join([name[0] for name in current_user.full_name.upper().split()[:2]]) if current_user.full_name is not None else current_user.email[0].upper()

        data = {
            "email": current_user.email,
            "full_name": current_user.full_name,
            "stag": current_user.stag,
            "initial": user_initial,
            "role": current_user.role,
            "is_verified": current_user.is_verified,
            "preferred_currency": current_user.preferred_currency,
            "preferred_language": current_user.preferred_language,
            "created_at": current_user.created_at
        }

        return data

    async def update_user_details(self, redis: Redis, update_request: UserUpdate, current_user: User) -> dict[str, str]:
        update_data = update_request.model_dump(exclude_unset=True)
        if not update_data:
            return {"message": "No changes provided."}

        # Check stag uniqueness (if user provided one)
        if "stag" in update_data and update_data["stag"]:
            existing_user = await self.user_repo.get_by_stag(update_data["stag"])
            if existing_user and existing_user.id != current_user.id:
                raise CustomException.e400_bad_request("stag already taken")

        user = await self.user_repo.get_by_email(current_user.email)
        await self.user_repo.update(user, update_data)

        await invalidate_cache(redis, f"user_current:{user.email}")
        return {"message": "User details updated successfully."}

    async def update_user_password(self, change_password_request: ChangePasswordRequest, current_user: User, background_tasks: Optional[BackgroundTasks] = None) -> None:
        """
        Update the currently authenticated user's password, verifying the current password first.
        """
        current_pass = change_password_request.current_password
        
        # Verify old password
        if not verify_password(plain_password=current_pass, hashed_password=current_user.password_hash):
            CustomException.e403_forbidden("Invalid current password.")
        
        new_hashed_password = hash_password(change_password_request.new_password)
        # Update via repository
        updates = {"password_hash": new_hashed_password}
        await self.user_repo.update(
            current_user,
            updates,
        )

        # Send password change notification email
        await self.notification_manager.schedule(
            self.notification_manager.send,
            background_tasks=background_tasks,
            notification_type=NotificationType.PASSWORD_CHANGE_NOTIFICATION,
            recipients=[current_user.email],
        )

    @staticmethod
    async def get_login_history(current_user: User) -> dict:
        """
        Get login activity details for a user.
        """
        return {
            "last_login": current_user.last_login_at,
            "failed_attempts": current_user.failed_login_attempts,
            "last_failed_attempt": current_user.last_failed_login_at,
            "account_status": {
                "is_enabled": current_user.is_enabled,
                "is_verified": current_user.is_verified,
                "is_deleted": current_user.is_deleted
            }
        }

    async def change_user_email(
        self,
        redis: Redis,
        change_email_request: ChangeEmailRequest,
        current_user: User,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> None:
        """
        Change the email address for the currently authenticated user.
        """
        new_email = change_email_request.new_email.lower().strip()
        old_email = current_user.email.lower().strip()

        # Prevent redundant changes
        if new_email == old_email:
            raise CustomException.e400_bad_request(
                "The new email must be different from your current email."
            )

        # Prevent email duplication
        if await self.user_repo.get_by_email(new_email):
            raise CustomException.e409_conflict("An account with this email already exists.")

        # Verify user password
        if not verify_password(
            plain_password=change_email_request.password,
            hashed_password=current_user.password_hash,
        ):
            raise CustomException.e403_forbidden("Invalid password.")

        # Prepare verification code and expiry
        verification_code = generate_secure_code()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        updates = {
            "email": new_email,
            "is_verified": False,
            "verification_code": verification_code,
            "verification_code_expires_at": expires_at,
            "token_version": current_user.token_version + 1,  # invalidate existing tokens
        }
        await self.user_repo.update(current_user, updates)
        await invalidate_cache(redis, f"user_current:{old_email}")

        # Send verification email
        await self.notification_manager.schedule(
            self.notification_manager.send,
            background_tasks=background_tasks,
            notification_type=NotificationType.EMAIL_CHANGE_NOTIFICATION,
            recipients=[new_email]
        )

    async def get_financial_analytics(self, current_user: User) -> dict[str, Any]:
        """
        Generate comprehensive financial analytics for a user.
        
        Aggregates data from wallet transactions and group contributions to provide
        insights into the user's financial activity, spending patterns, and savings behavior.
        
        Args:
            current_user (User): The authenticated user.
            
        Returns:
            dict[str, Any]: Dictionary containing:
                - total_transactions: Count of all wallet transactions
                - total_amount_in: Sum of all deposits
                - total_amount_out: Sum of all withdrawals
                - net_flow: Difference between deposits and withdrawals
                - transaction_frequency_last_30_days: Recent transaction count
                - total_contributed_to_groups: Total group contributions
                - total_groups_active: Number of active group memberships
                - transaction_type_distribution: Breakdown by transaction type
                - group_contribution_share_per_group: Per-group contribution amounts
        """
        from app.modules.user.schemas import TransactionTypeDistribution
        
        # Get wallet transaction statistics
        wallet_stats = await self.user_repo.get_wallet_transaction_stats(current_user.id)
        
        # Get recent transaction frequency
        recent_transactions = await self.user_repo.get_transaction_count_last_n_days(
            current_user.id, days=30
        )
        
        # Get transaction type distribution
        type_distribution = await self.user_repo.get_transaction_type_distribution(current_user.id)
        
        # Get group contribution data
        total_group_contributions = await self.user_repo.get_total_group_contributions(current_user.id)
        group_breakdown = await self.user_repo.get_group_contribution_breakdown(current_user.id)
        active_groups_count = await self.user_repo.get_active_groups_count(current_user.id)
        
        # Compute derived metrics
        net_flow = wallet_stats["total_amount_in"] - wallet_stats["total_amount_out"]
        
        # Structure the response
        analytics_data = {
            "total_transactions": wallet_stats["total_transactions"],
            "total_amount_in": wallet_stats["total_amount_in"],
            "total_amount_out": wallet_stats["total_amount_out"],
            "net_flow": net_flow,
            "transaction_frequency_last_30_days": recent_transactions,
            "total_contributed_to_groups": total_group_contributions,
            "total_groups_active": active_groups_count,
            "transaction_type_distribution": type_distribution,
            "group_contribution_share_per_group": group_breakdown
        }
        
        return analytics_data

