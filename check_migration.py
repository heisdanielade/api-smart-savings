import asyncio
from sqlalchemy import text
from app.infra.database.session import AsyncSessionLocal

async def check_nullable():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT column_name, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = 'group_member' 
                AND column_name IN ('role', 'contributed_amount', 'joined_at')
                ORDER BY column_name
            """)
        )
        rows = result.fetchall()
        print("\\ngroup_member table columns:")
        print("-" * 40)
        for row in rows:
            nullable = "nullable" if row[1] == "YES" else "NOT NULL"
            print(f"{row[0]:<25} {nullable}")
        
        # Check other tables too
        result2 = await session.execute(
            text("""
                SELECT column_name, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = 'groups' 
                AND column_name = 'current_balance'
            """)
        )
        rows2 = result2.fetchall()
        print("\\ngroups table columns:")
        print("-" * 40)
        for row in rows2:
            nullable = "nullable" if row[1] == "YES" else "NOT NULL"
            print(f"{row[0]:<25} {nullable}")

asyncio.run(check_nullable())
