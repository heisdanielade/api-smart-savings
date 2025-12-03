from typing import List, Dict
from fastapi import WebSocket
import uuid

class ConnectionManager:
    def __init__(self):
        # Map group_id to list of active websockets
        self.active_connections: Dict[uuid.UUID, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, group_id: uuid.UUID):
        await websocket.accept()
        if group_id not in self.active_connections:
            self.active_connections[group_id] = []
        self.active_connections[group_id].append(websocket)

    def disconnect(self, websocket: WebSocket, group_id: uuid.UUID):
        if group_id in self.active_connections:
            if websocket in self.active_connections[group_id]:
                self.active_connections[group_id].remove(websocket)
            if not self.active_connections[group_id]:
                del self.active_connections[group_id]

    async def broadcast(self, message: dict, group_id: uuid.UUID):
        if group_id in self.active_connections:
            for connection in self.active_connections[group_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    # Handle potential connection issues (e.g., client disconnected)
                    # Ideally, we should remove the dead connection here or let disconnect handle it
                    pass

manager = ConnectionManager()
