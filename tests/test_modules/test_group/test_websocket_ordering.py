import pytest
import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock
from app.modules.group.websockets import ConnectionManager

@pytest.mark.asyncio
async def test_broadcast_ordering():
    """
    Verify that broadcasts for the same group are serialized.
    """
    manager = ConnectionManager()
    group_id = uuid.uuid4()
    
    # Mock WebSocket
    ws1 = AsyncMock()
    
    await manager.connect(ws1, group_id)
    
    # Mock _send_message to be slow and log start/end
    send_log = []
    
    async def slow_send(connection, message, group_id):
        msg_id = message['id']
        send_log.append(f"START {msg_id}")
        await asyncio.sleep(0.05)
        send_log.append(f"END {msg_id}")
        
    # Monkeypatch _send_message on the instance
    manager._send_message = slow_send
    
    # Fire two broadcasts concurrently
    t1 = asyncio.create_task(manager.broadcast({"id": "1"}, group_id))
    t2 = asyncio.create_task(manager.broadcast({"id": "2"}, group_id))
    
    await asyncio.gather(t1, t2)
    
    # Check for interleaving
    is_interleaved = False
    for i in range(len(send_log) - 1):
        if send_log[i].startswith("START") and send_log[i+1].startswith("START"):
            is_interleaved = True
            break
            
    assert not is_interleaved, f"Broadcasts were interleaved: {send_log}"
    
    # Verify both messages were sent
    assert len(send_log) == 4
    assert "START 1" in send_log
    assert "START 2" in send_log

@pytest.mark.asyncio
async def test_race_condition_prevention():
    """
    Verify that holding the group lock prevents other broadcasts.
    Simulates the route handler scenario:
    1. Request A acquires lock
    2. Request A does 'slow work' (DB + Email)
    3. Request B tries to acquire lock
    4. Request A finishes work and broadcasts
    5. Request A releases lock
    6. Request B acquires lock, does work, broadcasts
    """
    manager = ConnectionManager()
    group_id = uuid.uuid4()
    ws1 = AsyncMock()
    await manager.connect(ws1, group_id)
    
    event_log = []
    
    async def process_request(req_id, duration):
        # Simulate route handler logic
        lock = await manager.get_group_lock(group_id)
        async with lock:
            event_log.append(f"LOCK ACQUIRED {req_id}")
            # Simulate slow service work
            await asyncio.sleep(duration)
            event_log.append(f"WORK DONE {req_id}")
            # Simulate broadcast
            await manager.broadcast_with_lock_held({"id": req_id}, group_id)
            event_log.append(f"BROADCAST DONE {req_id}")
            
    # Start Request A (slow)
    t1 = asyncio.create_task(process_request("A", 0.2))
    
    # Start Request B (fast) shortly after
    await asyncio.sleep(0.05)
    t2 = asyncio.create_task(process_request("B", 0.01))
    
    await asyncio.gather(t1, t2)
    
    # Expected order:
    # LOCK ACQUIRED A
    # (B tries to acquire but waits)
    # WORK DONE A
    # BROADCAST DONE A
    # LOCK ACQUIRED B
    # WORK DONE B
    # BROADCAST DONE B
    
    print(event_log)
    
    # Verify A finished before B started
    a_end_idx = event_log.index("BROADCAST DONE A")
    b_start_idx = event_log.index("LOCK ACQUIRED B")
    
    assert b_start_idx > a_end_idx, "Request B started before Request A finished! Lock failed."
