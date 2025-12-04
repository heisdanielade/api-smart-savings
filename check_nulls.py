import asyncio
from sqlalchemy import text
from app.infra.database.session import AsyncSessionLocal

async def check_nulls():
    async with AsyncSessionLocal() as session:
        # Check group_member table
        result = await session.execute(
            text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(role) as role_count,
                    COUNT(contributed_amount) as contrib_count,
                    COUNT(joined_at) as joined_count
                FROM group_member
            """)
        )
        row = result.fetchone()
        print("\ngroup_member table:")
        print(f"Total rows: {row[0]}")
        print(f"role NULLs: {row[0] - row[1]}")
        print(f"contributed_amount NULLs: {row[0] - row[2]}")
        print(f"joined_at NULLs: {row[0] - row[3]}")
        
        # Check groups table
        result2 = await session.execute(
            text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(current_balance) as balance_count
                FROM groups
            """)
        )
        row2 = result2.fetchone()
        print("\ngroups table:")
        print(f"Total rows: {row2[0]}")
        print(f"current_balance NULLs: {row2[0] - row2[1]}")
        
        # Check group_transaction_message
        result3 = await session.execute(
            text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(type) as type_count,
                    COUNT(timestamp) as timestamp_count
                FROM group_transaction_message
            """)
        )
        row3 = result3.fetchone()
        print("\ngroup_transaction_message table:")
        print(f"Total rows: {row3[0]}")
        print(f"type NULLs: {row3[0] - row3[1]}")
        print(f"timestamp NULLs: {row3[0] - row3[2]}")

asyncio.run(check_nulls())
