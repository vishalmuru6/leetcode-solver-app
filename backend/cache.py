"""
Redis Cache Manager - Complete PRD Compliant Implementation
Replaces SQLite with Redis for multi-user performance
"""

import os
import json
import asyncio
import logging
from typing import Any, Optional, Dict, List
from datetime import datetime, timedelta, timezone

try:
    import redis.asyncio as aioredis
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("[ERROR] Redis not available. Install with: pip install redis[hiredis]")

logger = logging.getLogger(__name__)

class CacheError(Exception):
    """Custom exception for cache-related errors"""
    pass

class CacheManager:
    """
    Redis-based cache manager for LeetCode solutions and user data
    PRD compliant for multi-user performance with <100ms response times
    """
    
    def __init__(self):
        if not REDIS_AVAILABLE:
            raise CacheError("Redis is required for PRD compliance. Install: pip install redis[hiredis]")
        
        self.redis_client: Optional[aioredis.Redis] = None
        self.is_initialized = False
        
        # Configuration from PRD
        self.default_ttl = int(os.getenv('CACHE_TTL', '86400'))  # 24 hours
        self.key_prefix = 'leetcode_solver:'
        self.redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        
        # Connection settings for performance
        self.connection_pool_size = int(os.getenv('REDIS_CONNECTION_POOL_SIZE', '20'))
        self.connection_timeout = int(os.getenv('REDIS_CONNECTION_TIMEOUT', '10'))
        
        logger.info("Redis CacheManager initialized for PRD compliance")
    
    async def initialize(self) -> None:
        """Initialize Redis connection with connection pooling"""
        try:
            # Create Redis connection with performance optimizations
            self.redis_client = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=self.connection_timeout,
                socket_keepalive=True,
                socket_keepalive_options={},
                retry_on_timeout=True,
                retry_on_error=[redis.ConnectionError, redis.TimeoutError],
                health_check_interval=30,
                max_connections=self.connection_pool_size
            )
            
            # Test connection
            await self.ping()
            self.is_initialized = True
            logger.info(f"Redis cache manager initialized successfully at {self.redis_url}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis cache manager: {e}")
            raise CacheError(f"Redis initialization failed: {str(e)}")
    
    async def close(self) -> None:
        """Close Redis connection and cleanup"""
        try:
            if self.redis_client:
                await self.redis_client.close()
            self.is_initialized = False
            logger.info("Redis cache manager closed successfully")
        except Exception as e:
            logger.error(f"Error closing Redis cache manager: {e}")
    
    def _ensure_initialized(self) -> None:
        """Ensure cache manager is initialized before operations"""
        if not self.is_initialized or not self.redis_client:
            raise CacheError("Redis cache manager not initialized")
    
    def _build_key(self, key: str, namespace: str = 'default') -> str:
        """Build prefixed cache key with namespace"""
        return f"{self.key_prefix}{namespace}:{key}"
    
    async def ping(self) -> bool:
        """Test Redis connection"""
        try:
            if not self.redis_client:
                return False
            result = await self.redis_client.ping()
            return result
        except Exception as e:
            logger.warning(f"Redis ping failed: {e}")
            return False
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        namespace: str = 'default'
    ) -> bool:
        """Set value in Redis cache with JSON serialization"""
        try:
            self._ensure_initialized()
            
            cache_key = self._build_key(key, namespace)
            ttl = ttl or self.default_ttl
            
            # Serialize value to JSON
            try:
                serialized_value = json.dumps(value, default=str, ensure_ascii=False)
            except (TypeError, ValueError) as e:
                logger.error(f"JSON serialization failed for key {key}: {e}")
                return False
            
            # Store in Redis with TTL
            await self.redis_client.setex(cache_key, ttl, serialized_value)
            
            logger.debug(f"Set cache key {cache_key} with TTL {ttl}s")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set cache key {key}: {e}")
            return False
    
    async def get(
        self,
        key: str,
        namespace: str = 'default',
        default: Any = None
    ) -> Any:
        """Get value from Redis cache with JSON deserialization"""
        try:
            self._ensure_initialized()
            
            cache_key = self._build_key(key, namespace)
            
            # Get from Redis
            value_json = await self.redis_client.get(cache_key)
            
            if value_json is None:
                return default
            
            try:
                value = json.loads(value_json)
                return value
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to deserialize cache value for key {key}: {e}")
                return default
            
        except Exception as e:
            logger.error(f"Failed to get cache key {key}: {e}")
            return default
    
    async def delete(self, key: str, namespace: str = 'default') -> bool:
        """Delete key from Redis cache"""
        try:
            self._ensure_initialized()
            
            cache_key = self._build_key(key, namespace)
            deleted = await self.redis_client.delete(cache_key)
            
            logger.debug(f"Deleted cache key {cache_key}")
            return deleted > 0
            
        except Exception as e:
            logger.error(f"Failed to delete cache key {key}: {e}")
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern (for daily refresh)"""
        try:
            self._ensure_initialized()
            
            # Use SCAN for memory-efficient pattern deletion
            keys_to_delete = []
            async for key in self.redis_client.scan_iter(match=pattern, count=100):
                keys_to_delete.append(key)
                
                # Delete in batches to avoid memory issues
                if len(keys_to_delete) >= 100:
                    if keys_to_delete:
                        deleted_batch = await self.redis_client.delete(*keys_to_delete)
                        logger.debug(f"Deleted batch of {deleted_batch} keys")
                    keys_to_delete = []
            
            # Delete remaining keys
            if keys_to_delete:
                deleted = await self.redis_client.delete(*keys_to_delete)
                logger.info(f"Deleted {deleted} keys matching pattern {pattern}")
                return deleted
            
            return 0
            
        except Exception as e:
            logger.error(f"Failed to delete pattern {pattern}: {e}")
            return 0
    
    async def exists(self, key: str, namespace: str = 'default') -> bool:
        """Check if key exists in Redis"""
        try:
            self._ensure_initialized()
            
            cache_key = self._build_key(key, namespace)
            exists = await self.redis_client.exists(cache_key)
            
            return bool(exists)
            
        except Exception as e:
            logger.error(f"Failed to check existence of cache key {key}: {e}")
            return False
    
    async def get_ttl(self, key: str, namespace: str = 'default') -> Optional[int]:
        """Get TTL of cache key"""
        try:
            self._ensure_initialized()
            
            cache_key = self._build_key(key, namespace)
            ttl = await self.redis_client.ttl(cache_key)
            
            return ttl if ttl > 0 else None
            
        except Exception as e:
            logger.error(f"Failed to get TTL for cache key {key}: {e}")
            return None
    
    async def expire(
        self,
        key: str,
        ttl: int,
        namespace: str = 'default'
    ) -> bool:
        """Set TTL for existing key"""
        try:
            self._ensure_initialized()
            
            cache_key = self._build_key(key, namespace)
            updated = await self.redis_client.expire(cache_key, ttl)
            
            return bool(updated)
            
        except Exception as e:
            logger.error(f"Failed to set TTL for cache key {key}: {e}")
            return False
    
    async def get_multiple(
        self,
        keys: List[str],
        namespace: str = 'default'
    ) -> Dict[str, Any]:
        """Get multiple values efficiently using pipeline"""
        try:
            self._ensure_initialized()
            
            if not keys:
                return {}
            
            # Build cache keys
            cache_keys = [self._build_key(key, namespace) for key in keys]
            
            # Use pipeline for efficiency
            pipe = self.redis_client.pipeline()
            for cache_key in cache_keys:
                pipe.get(cache_key)
            
            results = await pipe.execute()
            
            # Process results
            result_dict = {}
            for i, (original_key, value_json) in enumerate(zip(keys, results)):
                if value_json is not None:
                    try:
                        result_dict[original_key] = json.loads(value_json)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to deserialize value for key {original_key}")
                        result_dict[original_key] = None
                else:
                    result_dict[original_key] = None
            
            return result_dict
            
        except Exception as e:
            logger.error(f"Failed to get multiple keys: {e}")
            return {}
    
    # LeetCode-specific methods per PRD
    async def get_daily_solution(self, date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get cached daily LeetCode solution per PRD specification"""
        if not date:
            date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        key = f"daily_solution:{date}"
        return await self.get(key, namespace='leetcode')
    
    async def set_daily_solution(
        self,
        solution_data: Dict[str, Any],
        date: Optional[str] = None,
        ttl: Optional[int] = None
    ) -> bool:
        """Cache daily LeetCode solution per PRD specification"""
        if not date:
            date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        key = f"daily_solution:{date}"
        
        # Add metadata per PRD requirements
        enhanced_data = solution_data.copy()
        enhanced_data.update({
            'cached_at': datetime.now(timezone.utc).isoformat(),
            'cache_date': date,
            'cache_version': '1.0',
            'prd_compliant': True
        })
        
        return await self.set(key, enhanced_data, ttl=ttl, namespace='leetcode')
    
    async def clear_daily_cache(self) -> int:
        """Clear all daily solution cache (for 6 AM refresh per PRD)"""
        pattern = f"{self.key_prefix}leetcode:daily_solution:*"
        return await self.delete_pattern(pattern)
    
    async def get_user_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get cached user session data"""
        key = f"session:{user_id}"
        return await self.get(key, namespace='users')
    
    async def set_user_session(
        self,
        user_id: str,
        session_data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """Cache user session data"""
        key = f"session:{user_id}"
        
        # Add session metadata
        enhanced_session = session_data.copy()
        enhanced_session.update({
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'session_version': '1.0'
        })
        
        return await self.set(key, enhanced_session, ttl=ttl, namespace='users')
    
    async def delete_user_session(self, user_id: str) -> bool:
        """Delete user session from cache"""
        key = f"session:{user_id}"
        return await self.delete(key, namespace='users')
    
    async def flush_namespace(self, namespace: str = 'default') -> bool:
        """Delete all keys in a namespace"""
        try:
            pattern = f"{self.key_prefix}{namespace}:*"
            deleted_count = await self.delete_pattern(pattern)
            logger.info(f"Flushed {deleted_count} keys from namespace {namespace}")
            return True
        except Exception as e:
            logger.error(f"Failed to flush namespace {namespace}: {e}")
            return False
    
    async def get_info(self) -> Dict[str, Any]:
        """Get Redis server information"""
        try:
            self._ensure_initialized()
            
            info = await self.redis_client.info()
            
            return {
                'cache_type': 'redis',
                'redis_version': info.get('redis_version', 'unknown'),
                'used_memory_human': info.get('used_memory_human', 'unknown'),
                'connected_clients': info.get('connected_clients', 0),
                'keyspace_hits': info.get('keyspace_hits', 0),
                'keyspace_misses': info.get('keyspace_misses', 0),
                'uptime_in_seconds': info.get('uptime_in_seconds', 0),
                'total_commands_processed': info.get('total_commands_processed', 0),
                'instantaneous_ops_per_sec': info.get('instantaneous_ops_per_sec', 0),
                'prd_compliant': True
            }
            
        except Exception as e:
            logger.error(f"Failed to get Redis info: {e}")
            return {'cache_type': 'redis', 'error': str(e)}
    
    async def get_memory_usage(self) -> Dict[str, Any]:
        """Get Redis memory usage statistics"""
        try:
            self._ensure_initialized()
            
            info = await self.redis_client.info('memory')
            
            return {
                'used_memory': info.get('used_memory', 0),
                'used_memory_human': info.get('used_memory_human', 'unknown'),
                'used_memory_rss': info.get('used_memory_rss', 0),
                'used_memory_peak': info.get('used_memory_peak', 0),
                'used_memory_peak_human': info.get('used_memory_peak_human', 'unknown'),
                'mem_fragmentation_ratio': info.get('mem_fragmentation_ratio', 0.0)
            }
            
        except Exception as e:
            logger.error(f"Failed to get Redis memory usage: {e}")
            return {}
    
    # Context manager support
    async def __aenter__(self):
        if not self.is_initialized:
            await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()