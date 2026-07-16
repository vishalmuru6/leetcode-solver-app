"""
WebSocket Manager for Real-Time Progress Updates
Handles WebSocket connections for per-user progress tracking and communication.
"""

import json
import asyncio
import logging
from typing import Dict, Any, Optional, Set
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect, HTTPException
from fastapi.routing import APIRouter

logger = logging.getLogger(__name__)

class WebSocketError(Exception):
    """Custom exception for WebSocket-related errors"""
    pass

class ConnectionManager:
    """
    Manages WebSocket connections for real-time communication with users.
    """
    
    def __init__(self):
        # Store active connections: {user_id: websocket}
        self.active_connections: Dict[str, WebSocket] = {}
        
        # Connection metadata: {user_id: connection_info}
        self.connection_info: Dict[str, Dict[str, Any]] = {}
        
        # Message queue for offline users: {user_id: [messages]}
        self.message_queue: Dict[str, list] = {}
        
        # Connection limits
        self.max_connections_per_user = 3
        self.connection_timeout = 300  # 5 minutes
        
        logger.info("WebSocket ConnectionManager initialized")
    
    async def connect(self, websocket: WebSocket, user_id: str) -> bool:
        """
        Accept a new WebSocket connection for a user.
        
        Args:
            websocket: WebSocket connection
            user_id: User identifier
        
        Returns:
            True if connection was accepted
        """
        try:
            await websocket.accept()
            
            # Store connection
            self.active_connections[user_id] = websocket
            self.connection_info[user_id] = {
                'connected_at': datetime.now(timezone.utc),
                'last_ping': datetime.now(timezone.utc),
                'message_count': 0
            }
            
            logger.info(f"WebSocket connected for user {user_id}")
            
            # Send any queued messages
            await self._send_queued_messages(user_id)
            
            # Send connection confirmation
            await self.send_personal_message(user_id, {
                'type': 'connection',
                'message': 'WebSocket connected successfully',
                'connected_at': datetime.now(timezone.utc).isoformat()
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect WebSocket for user {user_id}: {e}")
            return False
    
    async def disconnect(self, user_id: str) -> None:
        """
        Disconnect and cleanup WebSocket for a user.
        
        Args:
            user_id: User identifier
        """
        try:
            if user_id in self.active_connections:
                websocket = self.active_connections[user_id]
                
                try:
                    # Check if WebSocket is still alive before trying to close
                    if hasattr(websocket, 'client_state') and websocket.client_state.name != 'DISCONNECTED':
                        await websocket.close(code=1000, reason="Server disconnect")
                except Exception as e:
                    logger.warning(f"Error closing WebSocket for {user_id}: {e}")
                finally:
                    # Always remove from connections even if close fails
                    if user_id in self.active_connections:
                        del self.active_connections[user_id]
            
            if user_id in self.connection_info:
                del self.connection_info[user_id]
            
            # Clean up old messages in queue (keep last 10)
            if user_id in self.message_queue:
                self.message_queue[user_id] = self.message_queue[user_id][-10:]
            
            logger.info(f"WebSocket disconnected for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error during WebSocket disconnect for {user_id}: {e}")
    
    async def send_personal_message(self, user_id: str, message: Dict[str, Any]) -> bool:
        """
        Send a message to a specific user.
        
        Args:
            user_id: User identifier
            message: Message dictionary
        
        Returns:
            True if message was sent successfully
        """
        try:
            # Add timestamp to message
            message['timestamp'] = datetime.now(timezone.utc).isoformat()
            message_json = json.dumps(message)
            
            # Try to send to active connection
            if user_id in self.active_connections:
                websocket = self.active_connections[user_id]
                
                try:
                    await websocket.send_text(message_json)
                    
                    # Update connection info
                    if user_id in self.connection_info:
                        self.connection_info[user_id]['message_count'] += 1
                        self.connection_info[user_id]['last_ping'] = datetime.now(timezone.utc)
                    
                    logger.debug(f"Message sent to user {user_id}: {message.get('type', 'unknown')}")
                    return True
                    
                except Exception as e:
                    logger.warning(f"Failed to send message to user {user_id}: {e}")
                    
                    # Connection is broken, clean it up
                    await self.disconnect(user_id)
                    
                    # Queue the message for later delivery
                    await self._queue_message(user_id, message)
                    return False
            else:
                # User not connected, queue the message
                await self._queue_message(user_id, message)
                logger.debug(f"Message queued for offline user {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending message to user {user_id}: {e}")
            return False
    
    async def broadcast_message(self, message: Dict[str, Any], exclude_users: Optional[Set[str]] = None) -> int:
        """
        Broadcast a message to all connected users.
        
        Args:
            message: Message dictionary
            exclude_users: Set of user IDs to exclude from broadcast
        
        Returns:
            Number of users who received the message
        """
        if exclude_users is None:
            exclude_users = set()
        
        sent_count = 0
        
        for user_id in list(self.active_connections.keys()):
            if user_id not in exclude_users:
                if await self.send_personal_message(user_id, message.copy()):
                    sent_count += 1
        
        logger.info(f"Broadcast message sent to {sent_count} users")
        return sent_count
    
    async def _queue_message(self, user_id: str, message: Dict[str, Any]) -> None:
        """
        Queue a message for offline user delivery.
        
        Args:
            user_id: User identifier
            message: Message to queue
        """
        if user_id not in self.message_queue:
            self.message_queue[user_id] = []
        
        # Limit queue size to prevent memory issues
        if len(self.message_queue[user_id]) >= 50:
            self.message_queue[user_id].pop(0)  # Remove oldest message
        
        self.message_queue[user_id].append(message)
    
    async def _send_queued_messages(self, user_id: str) -> None:
        """
        Send all queued messages to a newly connected user.
        
        Args:
            user_id: User identifier
        """
        if user_id not in self.message_queue:
            return
        
        messages = self.message_queue[user_id].copy()
        self.message_queue[user_id].clear()
        
        for message in messages:
            await self.send_personal_message(user_id, message)
        
        if messages:
            logger.info(f"Sent {len(messages)} queued messages to user {user_id}")
    
    def get_connection_count(self) -> int:
        """
        Get the number of active WebSocket connections.
        
        Returns:
            Number of active connections
        """
        return len(self.active_connections)
    
    def get_user_connection_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get connection information for a specific user.
        
        Args:
            user_id: User identifier
        
        Returns:
            Connection info dictionary or None
        """
        return self.connection_info.get(user_id)
    
    def is_user_connected(self, user_id: str) -> bool:
        """
        Check if a user has an active WebSocket connection.
        
        Args:
            user_id: User identifier
        
        Returns:
            True if user is connected
        """
        return user_id in self.active_connections
    
    async def ping_all_connections(self) -> Dict[str, bool]:
        """
        Ping all active connections to check their health.
        
        Returns:
            Dictionary of user_id: ping_success
        """
        ping_results = {}
        
        for user_id in list(self.active_connections.keys()):
            try:
                websocket = self.active_connections[user_id]
                
                # Send ping message
                ping_message = {
                    'type': 'ping',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
                
                await websocket.send_text(json.dumps(ping_message))
                ping_results[user_id] = True
                
                # Update last ping time
                if user_id in self.connection_info:
                    self.connection_info[user_id]['last_ping'] = datetime.now(timezone.utc)
                
            except Exception as e:
                logger.warning(f"Ping failed for user {user_id}: {e}")
                ping_results[user_id] = False
                
                # Disconnect broken connection
                await self.disconnect(user_id)
        
        return ping_results
    
    async def cleanup_stale_connections(self) -> int:
        """
        Clean up stale WebSocket connections that haven't been active.
        
        Returns:
            Number of connections cleaned up
        """
        cleaned_count = 0
        current_time = datetime.now(timezone.utc)
        
        for user_id in list(self.connection_info.keys()):
            connection_info = self.connection_info[user_id]
            last_ping = connection_info.get('last_ping', connection_info['connected_at'])
            
            # Check if connection is stale
            time_since_ping = (current_time - last_ping).total_seconds()
            
            if time_since_ping > self.connection_timeout:
                logger.info(f"Cleaning up stale connection for user {user_id}")
                await self.disconnect(user_id)
                cleaned_count += 1
        
        return cleaned_count

# Global connection manager instance
connection_manager = ConnectionManager()

def setup_websocket_routes(app, user_manager) -> None:
    """
    Setup WebSocket routes for the FastAPI application.
    
    Args:
        app: FastAPI application instance
        user_manager: UserManager instance
    """
    
    @app.websocket("/ws/progress/{user_id}")
    async def websocket_endpoint(websocket: WebSocket, user_id: str):
        """
        WebSocket endpoint for real-time progress updates.
        
        Args:
            websocket: WebSocket connection
            user_id: User identifier for session isolation
        """
        # Validate user_id format
        if not user_id or not user_id.startswith('user_'):
            await websocket.close(code=4000, reason="Invalid user ID format")
            return
        
        # Connect WebSocket
        connected = await connection_manager.connect(websocket, user_id)
        
        if not connected:
            logger.error(f"Failed to establish WebSocket connection for user {user_id}")
            return
        
        try:
            # Store WebSocket in user manager
            user_manager.set_websocket_connection(user_id, websocket)
            
            logger.info(f"WebSocket session started for user {user_id}")
            
            # Keep connection alive and handle incoming messages
            while True:
                try:
                    # Wait for messages from client (ping/pong, etc.)
                    data = await websocket.receive_text()
                    
                    try:
                        message = json.loads(data)
                        await handle_client_message(user_id, message)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON received from user {user_id}: {data}")
                    
                except WebSocketDisconnect:
                    logger.info(f"WebSocket disconnected normally for user {user_id}")
                    break
                
                except Exception as e:
                    logger.error(f"WebSocket error for user {user_id}: {e}")
                    break
        
        finally:
            # Cleanup
            await connection_manager.disconnect(user_id)
            user_manager.remove_websocket_connection(user_id)
            logger.info(f"WebSocket cleanup completed for user {user_id}")

async def handle_client_message(user_id: str, message: Dict[str, Any]) -> None:
    """
    Handle incoming messages from WebSocket clients.
    
    Args:
        user_id: User identifier
        message: Message from client
    """
    try:
        message_type = message.get('type', 'unknown')
        
        if message_type == 'pong':
            # Handle pong response
            logger.debug(f"Received pong from user {user_id}")
            
        elif message_type == 'heartbeat':
            # Handle heartbeat
            await connection_manager.send_personal_message(user_id, {
                'type': 'heartbeat_ack',
                'message': 'Heartbeat acknowledged'
            })
            
        elif message_type == 'status_request':
            # Handle status request
            connection_info = connection_manager.get_user_connection_info(user_id)
            await connection_manager.send_personal_message(user_id, {
                'type': 'status_response',
                'connection_info': connection_info,
                'connected': True
            })
            
        else:
            logger.warning(f"Unknown message type '{message_type}' from user {user_id}")
    
    except Exception as e:
        logger.error(f"Error handling client message from user {user_id}: {e}")

async def send_progress_update(
    user_id: str,
    progress: int,
    message: str,
    details: Optional[str] = None
) -> bool:
    """
    Send a progress update to a specific user.
    
    Args:
        user_id: User identifier
        progress: Progress percentage (0-100)
        message: Progress message
        details: Optional additional details
    
    Returns:
        True if message was sent successfully
    """
    progress_message = {
        'type': 'progress',
        'progress': max(0, min(100, progress)),  # Clamp between 0-100
        'message': str(message),
        'step': message
    }
    
    if details:
        progress_message['details'] = str(details)
    
    return await connection_manager.send_personal_message(user_id, progress_message)

async def send_success_message(user_id: str, message: str, details: Optional[Dict[str, Any]] = None) -> bool:
    """
    Send a success message to a specific user.
    
    Args:
        user_id: User identifier
        message: Success message
        details: Optional additional details
    
    Returns:
        True if message was sent successfully
    """
    success_message = {
        'type': 'success',
        'message': str(message),
        'progress': 100
    }
    
    if details:
        success_message.update(details)
    
    return await connection_manager.send_personal_message(user_id, success_message)

async def send_error_message(user_id: str, message: str, details: Optional[Dict[str, Any]] = None) -> bool:
    """
    Send an error message to a specific user.
    
    Args:
        user_id: User identifier
        message: Error message
        details: Optional additional details
    
    Returns:
        True if message was sent successfully
    """
    error_message = {
        'type': 'error',
        'message': str(message)
    }
    
    if details:
        error_message.update(details)
    
    return await connection_manager.send_personal_message(user_id, error_message)

async def send_info_message(user_id: str, message: str, details: Optional[Dict[str, Any]] = None) -> bool:
    """
    Send an info message to a specific user.
    
    Args:
        user_id: User identifier
        message: Info message
        details: Optional additional details
    
    Returns:
        True if message was sent successfully
    """
    info_message = {
        'type': 'info',
        'message': str(message)
    }
    
    if details:
        info_message.update(details)
    
    return await connection_manager.send_personal_message(user_id, info_message)

# Background task for connection management
async def websocket_manager_background_task():
    """
    Background task to manage WebSocket connections health and cleanup.
    """
    while True:
        try:
            # Ping all connections every 30 seconds
            await connection_manager.ping_all_connections()
            
            # Clean up stale connections every 5 minutes
            if datetime.now().minute % 5 == 0:
                cleaned = await connection_manager.cleanup_stale_connections()
                if cleaned > 0:
                    logger.info(f"Cleaned up {cleaned} stale WebSocket connections")
            
            await asyncio.sleep(30)  # Wait 30 seconds
            
        except asyncio.CancelledError:
            logger.info("WebSocket manager background task cancelled")
            break
        except Exception as e:
            logger.error(f"WebSocket manager background task error: {e}")
            await asyncio.sleep(60)  # Wait longer on error

def get_websocket_stats() -> Dict[str, Any]:
    """
    Get WebSocket connection statistics.
    
    Returns:
        Dictionary with connection statistics
    """
    return {
        'active_connections': connection_manager.get_connection_count(),
        'queued_messages': sum(len(queue) for queue in connection_manager.message_queue.values()),
        'total_queued_users': len(connection_manager.message_queue),
        'connection_info': {
            user_id: {
                'connected_at': info['connected_at'].isoformat(),
                'last_ping': info['last_ping'].isoformat(),
                'message_count': info['message_count']
            }
            for user_id, info in connection_manager.connection_info.items()
        }
    }