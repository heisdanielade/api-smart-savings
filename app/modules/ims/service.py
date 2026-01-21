# app/modules/ims/service.py

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Any
from decimal import Decimal
from uuid import UUID
from calendar import monthrange

import httpx
from calendar import day_name


from app.modules.shared.enums import (
    TransactionFrequency,
    TransactionStatus,
    ValidationStatus,
    DestinationType,
    Currency,
)
from app.modules.ims.schemas import (
    IMSContextSchema,
    InterpretationData,
    DraftTransaction,
    ProjectionScheduleItem,
    ConfirmTransactionRequest,
)
from app.modules.ims.models import ScheduledTransaction
from app.modules.ims.repository import IMSRepository
from app.modules.group.repository import GroupRepository
from app.modules.user.models import User
from app.core.config import settings

logger = logging.getLogger("savings")

# External NLP service URL
NLP_SERVICE_URL = settings.NLP_SERVICE_URL

class ProjectionService:
    """Service for generating transaction projections and handling scheduled transactions."""
    
    @staticmethod
    def get_projection_schedule(
        start_date: datetime,
        end_date: Optional[datetime],
        frequency: TransactionFrequency,
        day_of_week: Optional[int] = None,
        max_occurrences: int = 24,
    ) -> List[datetime]:
        """
        Calculate all execution dates based on schedule parameters.
        
        Args:
            start_date: Earliest possible execution date
            end_date: Latest possible execution date (optional)
            frequency: How often to execute (ONCE, DAILY, WEEKLY, MONTHLY)
            day_of_week: For WEEKLY, which day (0=Monday, 6=Sunday)
            max_occurrences: Limit on number of dates to generate
            
        Returns:
            List of datetime objects for each execution
        """
        dates: List[datetime] = []
        current = ProjectionService._calculate_first_run(start_date, frequency, day_of_week)
        
        if frequency == TransactionFrequency.ONCE:
            return [current] if ProjectionService._is_within_range(current, end_date) else []
        
        while len(dates) < max_occurrences:
            if not ProjectionService._is_within_range(current, end_date):
                break
            dates.append(current)
            current = ProjectionService._get_next_date(current, frequency, day_of_week)
        
        return dates
    
    @staticmethod
    def _calculate_first_run(
        start_date: datetime,
        frequency: TransactionFrequency,
        day_of_week: Optional[int]
    ) -> datetime:
        """Calculate the first valid execution date."""
        if frequency == TransactionFrequency.WEEKLY and day_of_week is not None:
            days_ahead = day_of_week - start_date.weekday()
            if days_ahead < 0:
                days_ahead += 7
            return start_date + timedelta(days=days_ahead)
        return start_date
    
    @staticmethod
    def _get_next_date(
        current: datetime,
        frequency: TransactionFrequency,
        day_of_week: Optional[int]
    ) -> datetime:
        """Calculate the next execution date after current."""
        if frequency == TransactionFrequency.DAILY:
            return current + timedelta(days=1)
        
        if frequency == TransactionFrequency.WEEKLY:
            return current + timedelta(weeks=1)
        
        if frequency == TransactionFrequency.MONTHLY:
            # Handle month-end edge cases (e.g., 31st -> 30th/28th)
            year = current.year + (current.month // 12)
            month = (current.month % 12) + 1
            day = min(current.day, monthrange(year, month)[1])
            return current.replace(year=year, month=month, day=day)
        
        return current
    
    @staticmethod
    def _is_within_range(date: datetime, end_date: Optional[datetime]) -> bool:
        """Check if date is within the valid range."""
        if end_date is None:
            return True
        return date <= end_date
    
    @classmethod
    def create_draft(
        cls, 
        interpretation: InterpretationData,
        user_groups: Optional[dict] = None,
        user_goals: Optional[dict] = None,
    ) -> DraftTransaction:
        """
        Create a draft transaction from NLP interpretation.
        Calculates projection and validates required fields.
        
        Args:
            interpretation: Parsed data from NLP interpretation
            user_groups: Dictionary mapping group IDs to names
            user_goals: Dictionary mapping goal IDs to names
            
        Returns:
            DraftTransaction with projected dates and validation status
        """
        print(interpretation)
        now = datetime.now(timezone.utc)
        
        # Logic to correct destination_type and resolve names
        destination_type = interpretation.destination_type
        group_id = interpretation.group_id
        goal_id = interpretation.goal_id
        
        # Auto-correct destination type if group_id is present
        if group_id and destination_type != DestinationType.GROUP:
             destination_type = DestinationType.GROUP
             
        # Resolve names from context if available
        group_name = None
        if group_id and user_groups:
            # Try exact match or string match
            group_name = user_groups.get(str(group_id))
            
        goal_name = interpretation.goal_name
        if goal_id and not goal_name and user_goals:
            goal_name = user_goals.get(str(goal_id))
        
        # Helper: Normalize day to int for logic
        day_int = cls._convert_day_to_int(interpretation.day_of_week)
        
        # Helper: Convert back to string name for frontend (e.g. "Monday") or keep None
        day_str = day_name[day_int] if day_int is not None else None

        draft = DraftTransaction(
            amount=interpretation.amount,
            currency=interpretation.currency,
            frequency=interpretation.frequency,
            destination_type=destination_type,
            # IDs are excluded/removed from DraftTransaction, so we only pass names
            goal_name=goal_name,
            group_name=group_name,
            day_of_week=day_str,
            start_date=interpretation.start_date or now,
            end_date=interpretation.end_date,
        )
        
        # Validate required fields
        missing_fields = []
        validation_messages = []
        
        if draft.amount is None:
            missing_fields.append("amount")
            validation_messages.append("Please provide the amount for this transaction.")
        
        if missing_fields:
            draft.validation_status = ValidationStatus.CLARIFICATION_REQUIRED
            draft.missing_fields = missing_fields
            draft.validation_messages = validation_messages
        
        # Generate projection if we have enough data
        if draft.amount and draft.start_date:
            dates = cls.get_projection_schedule(
                start_date=draft.start_date,
                end_date=draft.end_date,
                frequency=draft.frequency,
                day_of_week=day_int,
            )
            draft.projected_dates = [
                ProjectionScheduleItem(date=d, amount=draft.amount) for d in dates
            ]
            if dates:
                draft.first_run_date = dates[0]
        
        return draft
    
    @staticmethod
    def _convert_day_to_int(day: Any) -> Optional[int]:
        """
        Convert day string/int to int (0-6).
        Monday=0, Sunday=6.
        """
        if day is None:
            return None
        if isinstance(day, int):
            if 0 <= day <= 6:
                return day
            return None # Invalid int?
        
        if isinstance(day, str):
            day_lower = day.lower()
            days = [d.lower() for d in day_name]
            try:
                return days.index(day_lower)
            except ValueError:
                return None
        return None

    @staticmethod
    def generate_cron_expression(frequency: TransactionFrequency, day_of_week: Optional[int] = None) -> str:
        """
        Generate a cron expression from frequency settings.
        
        Args:
            frequency: Transaction frequency
            day_of_week: Day of week for weekly frequency (0=Monday)
            
        Returns:
            Cron expression string
        """
        if frequency == TransactionFrequency.ONCE:
            return ""  # No recurring schedule
        
        if frequency == TransactionFrequency.DAILY:
            return "0 0 * * *"  # Every day at midnight
        
        if frequency == TransactionFrequency.WEEKLY:
            # Cron uses 0=Sunday, but we use 0=Monday, so adjust
            cron_dow = (day_of_week + 1) % 7 if day_of_week is not None else 1
            return f"0 0 * * {cron_dow}"
        
        if frequency == TransactionFrequency.MONTHLY:
            return "0 0 1 * *"  # First day of each month at midnight
        
        return ""


class IMSService:
    """
    Service for handling IMS (Intent Management Service) operations.
    Manages the flow: Prompt -> Interpretation -> Projection -> Confirmation -> Activation
    """
    
    def __init__(
        self,
        ims_repo: IMSRepository,
        group_repo: GroupRepository,
    ):
        self.ims_repo = ims_repo
        self.group_repo = group_repo
    
    async def interpret_prompt(
        self,
        prompt: str,
        current_user: User,
    ) -> DraftTransaction:
        """
        Interpret a natural language prompt and return a draft transaction.
        
        1. Fetches user's groups and goals for context
        2. Calls external NLP service at POST 0.0.0.0:8000
        3. Creates projection from interpretation
        4. Returns DraftTransaction for user confirmation
        
        Args:
            prompt: Natural language savings instruction
            current_user: Authenticated user
            
        Returns:
            DraftTransaction with projected dates and validation status
        """
        # Build context with user's groups and goals
        user_groups = await self._get_user_groups_context(current_user.id)
        user_goals = await self._get_user_goals_context(current_user.id)
        
        context = IMSContextSchema(
            prompt=prompt,
            user_groups=user_groups,
            user_goals=user_goals,
        )
        
        # Call external NLP service
        
        interpretation = await self._call_nlp_service(context)
        
        # Create draft with projection
        draft = ProjectionService.create_draft(
            interpretation, 
            user_groups=user_groups, 
            user_goals=user_goals
        )
        
        logger.info(f"Created draft transaction for user {current_user.id}: {draft.validation_status}")
        
        return draft
    
    async def _call_nlp_service(self, context: IMSContextSchema) -> InterpretationData:
        """
        Call the external NLP service to interpret the prompt.
        
        Args:
            context: Context with prompt, user groups, and goals
            
        Returns:
            InterpretationData from NLP service
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    NLP_SERVICE_URL,
                    json=context.model_dump(),
                )
                response.raise_for_status()
                data = response.json()
                
                flat_data = {
                    "intent": data.get("intent"),
                    "raw_prompt": data.get("raw_prompt"),
                    **data.get("data", {}),
                }
                
                return InterpretationData(**flat_data)
                
        except httpx.HTTPStatusError as e:
            response_body = e.response.text
            logger.error(
                f"NLP service returned error: status={e.response.status_code}, "
                f"url={e.request.url}, response_body={response_body}"
            )
            raise ValueError(
                f"NLP service error: status={e.response.status_code}, details={response_body}"
            )
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to NLP service at {NLP_SERVICE_URL}: {e}")
            raise ValueError(f"Failed to connect to interpretation service at {NLP_SERVICE_URL}: {e}")
        except Exception as e:
            logger.error(f"Error parsing NLP response: {e}")
            raise ValueError(f"Failed to parse interpretation response: {e}")
    
    async def _get_user_groups_context(self, user_id: UUID) -> List[dict]:
        """Get user's groups formatted for NLP context."""
        try:
            r = {}
            groups = await self.group_repo.get_user_groups(user_id)
            for g in groups:
                r[str(g.id)] = g.name
            return r
            
        except Exception as e:
            logger.warning(f"Failed to fetch user groups: {e}")
            return {}
    
    async def _get_user_goals_context(self, user_id: UUID) -> List[dict]:
        """Get user's savings goals formatted for NLP context."""
        try:
            r = {}
            goals = await self.group_repo.get_user_goals(user_id)
            for g in goals:
                r[str(g.id)] = g.name
            return r
            
        except Exception as e:
            logger.warning(f"Failed to fetch user goals: {e}")
            return {}
    
    async def confirm_transaction(
        self,
        request: ConfirmTransactionRequest,
        current_user: User,
    ) -> ScheduledTransaction:
        """
        Confirm and activate a draft transaction.
        
        1. Resolves group/goal names to IDs
        2. Validates ownership
        3. Creates ScheduledTransaction with projection_log
        4. Sets status to ACTIVE and next_run_at
        
        Args:
            request: Confirmed/corrected transaction data
            current_user: Authenticated user
            
        Returns:
            Created ScheduledTransaction
        """
        group_id = None
        goal_id = None

        # Resolve destination IDs from names
        if request.destination_type == DestinationType.GROUP:
            if not request.group_name:
                raise ValueError("Group name is required for group savings")
            
            # Find group by name
            groups = await self.group_repo.get_user_groups(current_user.id)
            # Case-insensitive match 
            found = next((g for g in groups if g.name.lower() == request.group_name.lower()), None)
            
            if not found:
                raise ValueError(f"Group '{request.group_name}' not found")
            
            group_id = found.id
            # Already validated membership by fetching user's groups
            
        elif request.destination_type == DestinationType.GOAL:
            if not request.goal_name:
                # If no goal name, check if one was provided in interpretation context or we should create new?
                # For now assume it's required.
                raise ValueError("Goal name is required for personal savings")
                
            # Find goal by name
            goals = await self.group_repo.get_user_goals(current_user.id)
            found = next((g for g in goals if g.name.lower() == request.goal_name.lower()), None)
            
            if found:
                goal_id = found.id
            else:
                 # It might be a new goal.
                 # For now, we only support existing ones or we need logic to create new goal?
                 # Based on "goal_name: Optional[str] = None  # For dynamic goal creation" comment in schema
                 # verify if we should create it.
                 # Assuming logic: IF not found, CREATE new goal (user specific)
                 # But we need to know that implementation details.
                 # For safety, let's assume we error for now unless told otherwise, OR create a dummy check.
                 # Actually, let's implement the basic check first. User prompt implies linking name to ID.
                 # If user says "New Car", and it doesn't exist, we probably should create it?
                 # Given explicit instruction "backend should link the name to an id", we must find it.
                 # If we can't find it, we can't link it.
                 raise ValueError(f"Goal '{request.goal_name}' not found. Please create it first.")

        # Convert day name to int for projection and storage
        day_int = ProjectionService._convert_day_to_int(request.day_of_week)
        
        # Validate that if frequency is WEEKLY, we must have a day_int
        if request.frequency == TransactionFrequency.WEEKLY and day_int is None:
             # Try to start it on the start_date's weekday if missing? 
             # Or error? Let's use start_date's weekday if none provided but required.
             # But request.day_of_week comes from frontend.
             # If string invalid, _convert_day_to_int returns None.
             if request.day_of_week:
                 raise ValueError(f"Invalid day of week: {request.day_of_week}")
             else:
                 # Default to start_date weekday
                 day_int = request.start_date.weekday()

        # Generate projection dates
        projection_dates = ProjectionService.get_projection_schedule(
            start_date=request.start_date,
            end_date=request.end_date,
            frequency=request.frequency,
            day_of_week=day_int,
        )
        
        if not projection_dates:
            raise ValueError("No valid execution dates could be calculated")
        
        # Create projection log as ISO strings
        projection_log = [d.isoformat() for d in projection_dates]
        
        # Generate cron expression
        cron_expression = ProjectionService.generate_cron_expression(
            request.frequency,
            day_int,
        )
        
        # Create scheduled transaction
        scheduled_tx = ScheduledTransaction(
            user_id=current_user.id,
            amount=request.amount,
            currency=request.currency,
            frequency=request.frequency,
            day_of_week=day_int,
            start_date=request.start_date,
            end_date=request.end_date,
            destination_type=request.destination_type,
            goal_id=goal_id,
            group_id=group_id,
            status=TransactionStatus.ACTIVE,
            cron_expression=cron_expression,
            next_run_at=projection_dates[0],
            projection_log=projection_log,
        )
        
        created_tx = await self.ims_repo.create_scheduled_transaction(scheduled_tx)
        
        logger.info(
            f"Created scheduled transaction {created_tx.id} for user {current_user.id}, "
            f"next run at {created_tx.next_run_at}"
        )
        
        return created_tx
    
    async def _validate_group_membership(self, user_id: UUID, group_id: UUID) -> None:
        """Validate that user is a member of the specified group."""
        is_member = await self.group_repo.is_user_member(group_id, user_id)
        if not is_member:
            raise ValueError("You are not a member of the specified group")
    
    async def get_user_scheduled_transactions(
        self,
        current_user: User,
        status_filter: Optional[TransactionStatus] = None,
    ) -> List[ScheduledTransaction]:
        """Get all scheduled transactions for the current user."""
        return await self.ims_repo.get_scheduled_transactions_by_user(
            current_user.id,
            status_filter=status_filter,
        )
    
    async def cancel_scheduled_transaction(
        self,
        tx_id: UUID,
        current_user: User,
    ) -> Optional[ScheduledTransaction]:
        """Cancel a scheduled transaction owned by the user."""
        tx = await self.ims_repo.get_scheduled_transaction_by_id(tx_id)
        if not tx:
            raise ValueError("Scheduled transaction not found")
        if tx.user_id != current_user.id:
            raise ValueError("You do not own this scheduled transaction")
        
        return await self.ims_repo.cancel_scheduled_transaction(tx_id)
