from typing import Dict, Set
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # Mappe conversation_id vers un set de WebSockets connectés
        self.active_rooms: Dict[str, Set[WebSocket]] = {}

    async def connect(self, conversation_id: str, websocket: WebSocket):
        await websocket.accept()
        if conversation_id not in self.active_rooms:
            self.active_rooms[conversation_id] = set()
        self.active_rooms[conversation_id].add(websocket)

    def disconnect(self, conversation_id: str, websocket: WebSocket):
        if conversation_id in self.active_rooms:
            self.active_rooms[conversation_id].discard(websocket)
            if not self.active_rooms[conversation_id]:
                del self.active_rooms[conversation_id]

    async def broadcast(self, conversation_id: str, message: dict):
        if conversation_id in self.active_rooms:
            dead_connections = set()
            for connection in self.active_rooms[conversation_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    dead_connections.add(connection)
            for dead in dead_connections:
                self.active_rooms[conversation_id].discard(dead)


manager = ConnectionManager()

