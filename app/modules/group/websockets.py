from typing import List, Dict
from fastapi import WebSocket
import uuid
import asyncio

import logging

class ConnectionManager:
    """Manages WebSocket connections for group chat."""
    
    def __init__(self):
        self.active_connections: Dict[uuid.UUID, List[WebSocket]] = {}
        self.group_locks: Dict[uuid.UUID, asyncio.Lock] = {}
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, group_id: uuid.UUID):
        """Accept and store a new WebSocket connection for a group."""
        async with self.lock:
            if group_id not in self.active_connections:
                self.active_connections[group_id] = []
                self.group_locks[group_id] = asyncio.Lock()
            self.active_connections[group_id].append(websocket)

    async def get_group_lock(self, group_id: uuid.UUID) -> asyncio.Lock:
        """Get or create a lock for a specific group."""
        async with self.lock:
            if group_id not in self.group_locks:
                self.group_locks[group_id] = asyncio.Lock()
            return self.group_locks[group_id]

    def disconnect(self, websocket: WebSocket, group_id: uuid.UUID):
        """Remove a WebSocket connection from a group."""
        if group_id in self.active_connections:
            if websocket in self.active_connections[group_id]:
                self.active_connections[group_id].remove(websocket)
            if not self.active_connections[group_id]:
                del self.active_connections[group_id]
                if group_id in self.group_locks:
                    del self.group_locks[group_id]

    async def broadcast(self, message: dict, group_id: uuid.UUID):
        """Broadcast a message to all connections in a group concurrently."""
        async with self.lock:
            if group_id not in self.group_locks:
                return
            group_lock = self.group_locks[group_id]
            connections = list(self.active_connections.get(group_id, []))

        if not connections:
            return

        async with group_lock:
            tasks = [self._send_message(connection, message, group_id) for connection in connections]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def broadcast_with_lock_held(self, message: dict, group_id: uuid.UUID):
        """
        Broadcast a message assuming the caller already holds the group lock.
        WARNING: Caller MUST hold the group lock before calling this.
        """
        async with self.lock:
            connections = list(self.active_connections.get(group_id, []))

        if not connections:
            return

        # We assume the lock is held by the caller, so we just send
        tasks = [self._send_message(connection, message, group_id) for connection in connections]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_message(self, connection: WebSocket, message: dict, group_id: uuid.UUID):
        try:
            await connection.send_json(message)
        except Exception as e:
            logging.warning(f"Failed to send message to connection in group {group_id}: {str(e)}")
            self.disconnect(connection, group_id)

manager = ConnectionManager()
