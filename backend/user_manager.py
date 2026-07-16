"""
User Session Manager
Handles multiple concurrent user sessions with isolation and WebSocket communication.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from fastapi import WebSocket

logger = logging.getLogger(__name__)

class UserSessionError(Exception):
    """Custom exception for user session management errors"""
    pass

class UserManager:
    """
    Manages multiple user sessions with proper isolation and communication.
    """
    
    def __init__(self):
        # Active user sessions: {user_id: user_data}
        self.active_users: Dict[str, Dict[str, Any]] = {}
        
        # WebSocket connections: {user_id: websocket}
        self.websocket_connections: Dict[str, WebSocket] = {}
        
        # Session locks for thread safety
        self.session_locks: Dict[str, asyncio.Lock] = {}
        
        # User activity tracking
        self.user_activity: Dict[str, Dict[str, Any]] = {}
        
        # Configuration - UNLIMITED
        self.max_concurrent_users = float('inf')  # Unlimited concurrent users
        self.session_timeout = float('inf')  # No session timeout
        self.cleanup_interval = 86400  # 24 hours cleanup (disabled essentially)
        
        # Cleanup task will be started during app startup
        self._cleanup_task = None
        
        logger.info("UserManager initialized")
    
    def register_user(self, user_id: str, user_data: Dict[str, Any]) -> bool:
        """
        Register a new user session.
        
        Args:
            user_id: Unique user identifier
            user_data: User session data
        
        Returns:
            True if user was registered successfully
        """
        try:
            if len(self.active_users) >= self.max_concurrent_users:
                logger.warning(f"Cannot register user {user_id}: Maximum concurrent users reached")
                return False
            
            if user_id in self.active_users:
                logger.warning(f"User {user_id} already registered, updating session")
            
            # Create session lock
            if user_id not in self.session_locks:
                self.session_locks[user_id] = asyncio.Lock()
            
            # Store user data
            self.active_users[user_id] = {
                **user_data,
                'session_id': user_id,
                'registered_at': datetime.now(timezone.utc),
                'last_activity': datetime.now(timezone.utc),
                'status': 'active',
                'automation_status': 'initializing'
            }
            
            # Initialize activity tracking
            self.user_activity[user_id] = {
                'login_time': datetime.now(timezone.utc),
                'message_count': 0,
                'last_message_time': None,
                'automation_started': False,
                'automation_completed': False
            }
            
            logger.info(f"User {user_id} registered successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register user {user_id}: {e}")
            return False
    
    def unregister_user(self, user_id: str) -> bool:
        """
        Unregister a user session and cleanup resources.
        
        Args:
            user_id: User identifier
        
        Returns:
            True if user was unregistered successfully
        """
        try:
            # Remove user data
            if user_id in self.active_users:
                user_data = self.active_users[user_id]
                session_duration = (datetime.now(timezone.utc) - user_data['registered_at']).total_seconds()
                
                del self.active_users[user_id]
                logger.info(f"User {user_id} unregistered after {session_duration:.1f}s")
            
            # Remove WebSocket connection
            if user_id in self.websocket_connections:
                del self.websocket_connections[user_id]
            
            # Clean up activity tracking
            if user_id in self.user_activity:
                del self.user_activity[user_id]
            
            # Keep session lock for a bit in case of reconnection
            # It will be cleaned up by periodic cleanup
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to unregister user {user_id}: {e}")
            return False
    
    def is_user_active(self, user_id: str) -> bool:
        """
        Check if a user session is active.
        
        Args:
            user_id: User identifier
        
        Returns:
            True if user is active
        """
        return user_id in self.active_users
    
    def get_user_data(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user session data.
        
        Args:
            user_id: User identifier
        
        Returns:
            User data dictionary or None
        """
        return self.active_users.get(user_id)
    
    def update_user_data(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update user session data.
        
        Args:
            user_id: User identifier
            updates: Data updates to apply
        
        Returns:
            True if update was successful
        """
        try:
            if user_id not in self.active_users:
                return False
            
            self.active_users[user_id].update(updates)
            self.active_users[user_id]['last_activity'] = datetime.now(timezone.utc)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update user data for {user_id}: {e}")
            return False
    
    def get_active_user_count(self) -> int:
        """
        Get the number of active users.
        
        Returns:
            Number of active users
        """
        return len(self.active_users)
    
    def get_user_session_lock(self, user_id: str) -> asyncio.Lock:
        """
        Get or create a session lock for a user.
        
        Args:
            user_id: User identifier
        
        Returns:
            AsyncIO lock for the user session
        """
        if user_id not in self.session_locks:
            self.session_locks[user_id] = asyncio.Lock()
        
        return self.session_locks[user_id]
    
    def set_websocket_connection(self, user_id: str, websocket: WebSocket) -> None:
        """
        Store WebSocket connection for a user.
        
        Args:
            user_id: User identifier
            websocket: WebSocket connection
        """
        self.websocket_connections[user_id] = websocket
        
        # Update activity
        if user_id in self.user_activity:
            self.user_activity[user_id]['websocket_connected'] = True
        
        logger.debug(f"WebSocket connection stored for user {user_id}")
    
    def remove_websocket_connection(self, user_id: str) -> None:
        """
        Remove WebSocket connection for a user.
        
        Args:
            user_id: User identifier
        """
        if user_id in self.websocket_connections:
            del self.websocket_connections[user_id]
        
        # Update activity
        if user_id in self.user_activity:
            self.user_activity[user_id]['websocket_connected'] = False
        
        logger.debug(f"WebSocket connection removed for user {user_id}")
    
    def get_websocket_connection(self, user_id: str) -> Optional[WebSocket]:
        """
        Get WebSocket connection for a user.
        
        Args:
            user_id: User identifier
        
        Returns:
            WebSocket connection or None
        """
        return self.websocket_connections.get(user_id)
    
    async def send_message_to_user(self, user_id: str, message: Dict[str, Any]) -> bool:
        """
        Send a message to a specific user via WebSocket.
        
        Args:
            user_id: User identifier
            message: Message to send
        
        Returns:
            True if message was sent successfully
        """
        try:
            websocket = self.get_websocket_connection(user_id)
            
            if not websocket:
                logger.warning(f"No WebSocket connection for user {user_id}")
                return False
            
            # Add timestamp to message
            message['timestamp'] = datetime.now(timezone.utc).isoformat()
            
            # Send message via WebSocket
            import json
            await websocket.send_text(json.dumps(message))
            
            # Update activity tracking
            if user_id in self.user_activity:
                self.user_activity[user_id]['message_count'] += 1
                self.user_activity[user_id]['last_message_time'] = datetime.now(timezone.utc)
            
            logger.debug(f"Message sent to user {user_id}: {message.get('type', 'unknown')}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send message to user {user_id}: {e}")
            
            # Remove broken connection
            self.remove_websocket_connection(user_id)
            return False
    
    async def broadcast_message_to_all(
        self,
        message: Dict[str, Any],
        exclude_users: Optional[List[str]] = None
    ) -> int:
        """
        Broadcast a message to all active users.
        
        Args:
            message: Message to broadcast
            exclude_users: List of user IDs to exclude
        
        Returns:
            Number of users who received the message
        """
        if exclude_users is None:
            exclude_users = []
        
        sent_count = 0
        
        for user_id in list(self.active_users.keys()):
            if user_id not in exclude_users:
                if await self.send_message_to_user(user_id, message.copy()):
                    sent_count += 1
        
        logger.info(f"Broadcast message sent to {sent_count} users")
        return sent_count
    
    def update_user_automation_status(self, user_id: str, status: str, details: Optional[str] = None) -> None:
        """
        Update the automation status for a user.
        
        Args:
            user_id: User identifier
            status: Automation status
            details: Optional status details
        """
        if user_id in self.active_users:
            self.active_users[user_id]['automation_status'] = status
            self.active_users[user_id]['last_activity'] = datetime.now(timezone.utc)
            
            if details:
                self.active_users[user_id]['automation_details'] = details
        
        # Update activity tracking
        if user_id in self.user_activity:
            if status == 'running':
                self.user_activity[user_id]['automation_started'] = True
            elif status in ['completed', 'failed']:
                self.user_activity[user_id]['automation_completed'] = True
        
        logger.debug(f"User {user_id} automation status updated: {status}")
    
    def get_user_statistics(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get statistics for a specific user.
        
        Args:
            user_id: User identifier
        
        Returns:
            User statistics or None
        """
        if user_id not in self.active_users:
            return None
        
        user_data = self.active_users[user_id]
        activity_data = self.user_activity.get(user_id, {})
        
        current_time = datetime.now(timezone.utc)
        session_duration = (current_time - user_data['registered_at']).total_seconds()
        
        return {
            'user_id': user_id,
            'session_duration': session_duration,
            'automation_status': user_data.get('automation_status', 'unknown'),
            'last_activity': user_data['last_activity'].isoformat(),
            'websocket_connected': user_id in self.websocket_connections,
            'message_count': activity_data.get('message_count', 0),
            'automation_started': activity_data.get('automation_started', False),
            'automation_completed': activity_data.get('automation_completed', False)
        }
    
    def get_all_user_statistics(self) -> Dict[str, Any]:
        """
        Get statistics for all active users.
        
        Returns:
            Dictionary with overall statistics
        """
        current_time = datetime.now(timezone.utc)
        
        user_stats = []
        total_messages = 0
        automations_running = 0
        automations_completed = 0
        
        for user_id in self.active_users:
            user_stat = self.get_user_statistics(user_id)
            if user_stat:
                user_stats.append(user_stat)
                total_messages += user_stat['message_count']
                
                if user_stat['automation_status'] == 'running':
                    automations_running += 1
                elif user_stat['automation_completed']:
                    automations_completed += 1
        
        return {
            'active_users': len(self.active_users),
            'websocket_connections': len(self.websocket_connections),
            'total_messages_sent': total_messages,
            'automations_running': automations_running,
            'automations_completed': automations_completed,
            'users': user_stats,
            'generated_at': current_time.isoformat()
        }
    
    async def cleanup_inactive_users(self) -> int:
        """
        Clean up inactive user sessions that have timed out.
        
        Returns:
            Number of users cleaned up
        """
        current_time = datetime.now(timezone.utc)
        cleanup_count = 0
        
        # Find inactive users
        inactive_users = []
        for user_id, user_data in self.active_users.items():
            last_activity = user_data.get('last_activity', user_data['registered_at'])
            inactive_duration = (current_time - last_activity).total_seconds()
            
            if inactive_duration > self.session_timeout:
                inactive_users.append(user_id)
        
        # Clean up inactive users
        for user_id in inactive_users:
            logger.info(f"Cleaning up inactive user session: {user_id}")
            self.unregister_user(user_id)
            cleanup_count += 1
        
        # Clean up old session locks
        lock_cleanup_count = 0
        for user_id in list(self.session_locks.keys()):
            if user_id not in self.active_users:
                del self.session_locks[user_id]
                lock_cleanup_count += 1
        
        if cleanup_count > 0 or lock_cleanup_count > 0:
            logger.info(f"Cleaned up {cleanup_count} inactive users and {lock_cleanup_count} old locks")
        
        return cleanup_count
    
    def start_cleanup_task(self) -> None:
        """
        Start the background cleanup task (called during app startup).
        """
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            logger.info("User manager cleanup task started")

    async def stop_cleanup_task(self) -> None:
        """
        Stop the background cleanup task (called during app shutdown).
        """
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("User manager cleanup task stopped")

    async def cleanup_all_sessions(self) -> int:
        """
        Clean up all user sessions (for shutdown).
        
        Returns:
            Number of sessions cleaned up
        """
        user_count = len(self.active_users)
        
        # Stop cleanup task first
        await self.stop_cleanup_task()
        
        # Close all WebSocket connections
        for user_id, websocket in list(self.websocket_connections.items()):
            try:
                # Check if WebSocket is still alive before closing
                if hasattr(websocket, 'client_state') and websocket.client_state.name != 'DISCONNECTED':
                    await websocket.close(code=1000, reason="Server shutdown")
            except Exception as e:
                logger.warning(f"Error closing WebSocket for {user_id}: {e}")
        
        # Clear all data structures
        self.active_users.clear()
        self.websocket_connections.clear()
        self.user_activity.clear()
        self.session_locks.clear()
        
        logger.info(f"Cleaned up all {user_count} user sessions")
        return user_count
    
    async def handle_user_automation_error(self, user_id: str, error: str) -> None:
        """
        Handle automation errors for a user.
        
        Args:
            user_id: User identifier
            error: Error description
        """
        try:
            # Update user status
            self.update_user_automation_status(user_id, 'failed', error)
            
            # Send error message to user
            await self.send_message_to_user(user_id, {
                'type': 'error',
                'message': f'Automation failed: {error}',
                'automation_status': 'failed'
            })
            
            logger.error(f"Automation error for user {user_id}: {error}")
            
        except Exception as e:
            logger.error(f"Error handling automation error for user {user_id}: {e}")
    
    async def _periodic_cleanup(self) -> None:
        """
        Background task for periodic cleanup of inactive sessions.
        """
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self.cleanup_inactive_users()
                
            except asyncio.CancelledError:
                logger.info("Periodic cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")
                await asyncio.sleep(60)  # Wait longer on error
    
    def get_user_session_summary(self, user_id: str) -> Optional[Dict[str, str]]:
        """
        Get a summary of user session for logging/debugging.
        
        Args:
            user_id: User identifier
        
        Returns:
            Session summary or None
        """
        if user_id not in self.active_users:
            return None
        
        user_data = self.active_users[user_id]
        activity = self.user_activity.get(user_id, {})
        
        return {
            'user_id': user_id,
            'status': user_data.get('automation_status', 'unknown'),
            'session_age': str(datetime.now(timezone.utc) - user_data['registered_at']),
            'websocket': 'connected' if user_id in self.websocket_connections else 'disconnected',
            'messages_sent': str(activity.get('message_count', 0)),
            'username': user_data.get('username', 'unknown')
        }