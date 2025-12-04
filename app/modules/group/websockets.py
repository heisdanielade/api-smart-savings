from typing import List, Dict
from fastapi import WebSocket
import uuid
import asyncio

import logging

class ConnectionManager:
    """Manages WebSocket connections for group chat."""
    
    def __init__(self):
        # Map group_id to list of active websockets
        self.active_connections: Dict[uuid.UUID, List[WebSocket]] = {}
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, group_id: uuid.UUID):
        """Accept and store a new WebSocket connection for a group."""
        # websocket.accept() is now handled in the route handler
        async with self.lock:
            if group_id not in self.active_connections:
                self.active_connections[group_id] = []
            self.active_connections[group_id].append(websocket)

    def disconnect(self, websocket: WebSocket, group_id: uuid.UUID):
        """Remove a WebSocket connection from a group."""
        # Note: This method is intentionally synchronous to be called from exception handlers
        # We'll make it async-safe by checking if we're in an async context
        if group_id in self.active_connections:
            if websocket in self.active_connections[group_id]:
                self.active_connections[group_id].remove(websocket)
            if not self.active_connections[group_id]:
                del self.active_connections[group_id]

    async def broadcast(self, message: dict, group_id: uuid.UUID):
        """Broadcast a message to all connections in a group."""
        async with self.lock:
            connections = list(self.active_connections.get(group_id, []))
        
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logging.warning(f"Failed to send message to connection in group {group_id}: {str(e)}")
                self.disconnect(connection, group_id)

manager = ConnectionManager()
