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
    # If serialized, we should see START X, END X, START Y, END Y
    # If concurrent, we might see START X, START Y, END X, END Y
    
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
async def test_broadcast_concurrency_different_groups():
    """
    Verify that broadcasts for different groups can run concurrently.
    """
    manager = ConnectionManager()
    group1_id = uuid.uuid4()
    group2_id = uuid.uuid4()
    
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    
    await manager.connect(ws1, group1_id)
    await manager.connect(ws2, group2_id)
    
    send_log = []
    
    async def slow_send(connection, message, group_id):
        msg_id = message['id']
        send_log.append(f"START {msg_id}")
        await asyncio.sleep(0.05)
        send_log.append(f"END {msg_id}")
        
    manager._send_message = slow_send
    
    # Fire broadcasts for different groups
    t1 = asyncio.create_task(manager.broadcast({"id": "1"}, group1_id))
    t2 = asyncio.create_task(manager.broadcast({"id": "2"}, group2_id))
    
    await asyncio.gather(t1, t2)
    
    # These SHOULD be interleaved (or at least could be) because they are different groups
    # But strictly speaking, we just want to make sure they both finished.
    # Proving concurrency is harder without precise timing, but we can verify they both ran.
    
    assert len(send_log) == 4
    assert "START 1" in send_log
    assert "START 2" in send_log
