"""
Code Cache Manager for LeetCode Solutions
Handles caching of N8N-fetched code for instant submission
"""

import asyncio
import logging
import time
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from cache import CacheManager

logger = logging.getLogger(__name__)

@dataclass
class CachedSolution:
    """Represents a cached LeetCode solution"""
    code: str
    problem_slug: str
    problem_title: str
    is_safe: bool
    quality_score: float
    warnings: list
    cached_at: float
    retrieval_method: str
    response_time: float
    is_daily_challenge: bool = True

class CodeCacheManager:
    """
    Manages caching of LeetCode solutions fetched from N8N
    """
    
    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager
        self.cache_prefix = "leetcode_solution"
        self.daily_cache_key = "daily_challenge_solution"
        self.cache_ttl = 90000  # 25 hours to ensure it lasts until next 6 AM refresh
        self.background_fetch_task = None
        self.last_fetch_time = 0  # Start at 0 to allow immediate calls
        self.fetch_interval = 21600  # Fetch every 6 hours (much less aggressive)
        
        # Add global lock to prevent concurrent N8N calls
        self._fetch_lock = asyncio.Lock()
        self._is_fetching = False
        
        logger.info("Code Cache Manager initialized (rate limiting disabled, concurrency protection enabled)")
    
    async def get_daily_solution(self) -> Optional[CachedSolution]:
        """
        Get the cached daily challenge solution
        """
        try:
            cached_data = await self.cache.get(self.daily_cache_key)
            
            if cached_data:
                # Parse cached data
                if isinstance(cached_data, str):
                    solution_dict = json.loads(cached_data)
                else:
                    solution_dict = cached_data
                
                solution = CachedSolution(**solution_dict)
                
                # Check if cache is still fresh (within 24 hours)
                cache_age = time.time() - solution.cached_at
                if cache_age < self.cache_ttl:
                    logger.info(f"Retrieved cached daily solution (age: {cache_age/3600:.1f}h)")
                    return solution
                else:
                    logger.info(f"Cached solution expired (age: {cache_age/3600:.1f}h)")
                    await self.cache.delete(self.daily_cache_key)
            
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving cached solution: {e}")
            return None
    
    async def cache_daily_solution(self, solution: CachedSolution) -> bool:
        """
        Cache a daily challenge solution
        """
        try:
            # Convert to dict for JSON serialization
            solution_dict = asdict(solution)
            solution_json = json.dumps(solution_dict, default=str)
            
            # Store in cache with TTL
            await self.cache.set(
                self.daily_cache_key,
                solution_json,
                ttl=self.cache_ttl
            )
            
            logger.info(f"Cached daily solution: {len(solution.code)} chars, quality: {solution.quality_score}")
            return True
            
        except Exception as e:
            logger.error(f"Error caching solution: {e}")
            return False
    
    async def fetch_and_cache_solution(self, challenge_date: str = None) -> Optional[CachedSolution]:
        """
        Fetch solution from N8N and cache it (with concurrency protection)
        """
        async with self._fetch_lock:
            # Double-check pattern - check cache again while holding lock
            existing_solution = await self.get_daily_solution()
            if existing_solution:
                logger.info("✅ Solution was cached by another process while waiting for lock")
                return existing_solution
            
            if self._is_fetching:
                logger.warning("⚠️  Another fetch is in progress, waiting...")
                return None
                
            self._is_fetching = True
            
            try:
                from utils.n8n_enhanced import get_code_from_n8n_simple
                from utils.code_validator import LeetCodeValidator
                
                logger.info(f"🔒 Fetching fresh solution from N8N (locked to prevent concurrent calls)...")
                start_time = time.time()
                
                # Update last fetch time BEFORE making the call
                self.last_fetch_time = time.time()
                
                # Single attempt with full wait - wait the entire time for complete code generation
                code, is_safe, warnings, problem_title = get_code_from_n8n_simple(
                    enable_validation=True,
                    timeout_seconds=360,  # 6 minutes wait for complete code generation (AI needs time)
                    fallback_enabled=True,
                    challenge_date=challenge_date  # Pass the specific challenge date
                )
                
                if not code:
                    logger.error("No code received from N8N")
                    return None
                
                response_time = time.time() - start_time
                
                # Get quality score
                try:
                    validator = LeetCodeValidator()
                    _, _, quality_score = validator.quick_validate(code)
                except Exception:
                    quality_score = 0.7  # Default score
                
                # Create solution object
                solution = CachedSolution(
                    code=code,
                    problem_slug="daily-challenge",  # Default for daily
                    problem_title=problem_title or "Daily Challenge",  # Use actual problem title
                    is_safe=is_safe,
                    quality_score=quality_score,
                    warnings=warnings or [],
                    cached_at=time.time(),
                    retrieval_method="n8n_enhanced_locked",
                    response_time=response_time,
                    is_daily_challenge=True
                )
                
                # Cache the solution
                await self.cache_daily_solution(solution)
                
                logger.info(f"✅ Successfully fetched and cached solution ({response_time:.1f}s)")
                return solution
                
            except Exception as e:
                logger.error(f"Error fetching and caching solution: {e}")
                return None
            finally:
                self._is_fetching = False
    
    async def ensure_fresh_solution(self) -> Optional[CachedSolution]:
        """
        Ensure we have a cached solution - fetch from n8n if NO cache exists
        Uses locking to prevent concurrent N8N workflow calls
        """
        # ALWAYS check cache first (fast path)
        solution = await self.get_daily_solution()
        
        if solution:
            # Cache exists - use it for the full 24 hour cycle
            cache_age_hours = (time.time() - solution.cached_at) / 3600
            logger.info(f"✅ Using cached solution (age: {cache_age_hours:.1f}h) - Valid until next 6 AM refresh")
            return solution
        
        # NO cache exists - check if another process is already fetching
        if self._is_fetching:
            logger.info("⏳ Another process is fetching solution, waiting for it to complete...")
            # Wait briefly and check cache again
            await asyncio.sleep(2)
            solution = await self.get_daily_solution()
            if solution:
                logger.info("✅ Solution was cached by another process while we waited")
                return solution
            else:
                logger.warning("⚠️  Other process fetch didn't complete, will attempt our own fetch")
        
        # Calculate the challenge date for today (using 6AM IST logic)
        import pytz
        from datetime import timedelta
        ist = pytz.timezone('Asia/Kolkata')
        now_ist = datetime.now(ist)
        
        if now_ist.hour < 6:
            challenge_date = (now_ist - timedelta(days=1)).strftime('%Y-%m-%d')
        else:
            challenge_date = now_ist.strftime('%Y-%m-%d')
        
        # NO cache exists and no other process fetching - make the call
        logger.info(f"❌ No cached solution found - Making protected n8n call to fetch solution for {challenge_date}...")
        fresh_solution = await self.fetch_and_cache_solution(challenge_date)
        
        if fresh_solution:
            logger.info("✅ Fresh solution cached! Will be used for next 24 hours until 6 AM refresh")
        
        return fresh_solution
    
    async def start_background_caching(self):
        """
        Start background task to periodically fetch and cache solutions
        """
        if self.background_fetch_task is None or self.background_fetch_task.done():
            # Cancel any existing task first
            if self.background_fetch_task and not self.background_fetch_task.done():
                self.background_fetch_task.cancel()
                
            self.background_fetch_task = asyncio.create_task(self._background_fetch_loop())
            logger.info("Started background solution caching (fetch every 6h, check every 30min)")
    
    async def stop_background_caching(self):
        """
        Stop background caching task
        """
        if self.background_fetch_task:
            self.background_fetch_task.cancel()
            try:
                await self.background_fetch_task
            except asyncio.CancelledError:
                pass
            self.background_fetch_task = None
            logger.info("Stopped background solution caching")
    
    async def _background_fetch_loop(self):
        """
        Background loop - COMPLETELY DISABLED
        Only 6 AM daily scheduler should call n8n
        """
        logger.info("🚫 Background fetch loop DISABLED - only 6 AM daily refresh allowed")
        
        # Infinite sleep - this task does nothing now
        while True:
            try:
                await asyncio.sleep(86400)  # Sleep forever
                logger.debug("Background fetch: Still disabled (this is expected)")
                
            except asyncio.CancelledError:
                logger.info("Background fetch task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in disabled background loop: {e}")
                await asyncio.sleep(86400)
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics
        """
        try:
            solution = await self.get_daily_solution()
            
            if solution:
                cache_age = time.time() - solution.cached_at
                return {
                    "has_cached_solution": True,
                    "cache_age_hours": cache_age / 3600,
                    "code_length": len(solution.code),
                    "quality_score": solution.quality_score,
                    "is_safe": solution.is_safe,
                    "warnings_count": len(solution.warnings),
                    "retrieval_method": solution.retrieval_method,
                    "response_time": solution.response_time,
                    "cached_at": datetime.fromtimestamp(solution.cached_at, tz=timezone.utc).isoformat()
                }
            else:
                return {
                    "has_cached_solution": False,
                    "rate_limiting_disabled": True,
                    "fetch_interval_hours": self.fetch_interval / 3600
                }
                
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"error": str(e)}
    
    async def force_refresh(self) -> Optional[CachedSolution]:
        """
        Force refresh the cached solution by fetching from N8N (with concurrency protection)
        """
        async with self._fetch_lock:
            logger.info("🔄 Force refreshing solution cache (protected from concurrent calls)...")
            
            # Calculate the challenge date for today (using 6AM IST logic)
            import pytz
            from datetime import timedelta
            ist = pytz.timezone('Asia/Kolkata')
            now_ist = datetime.now(ist)
            
            if now_ist.hour < 6:
                challenge_date = (now_ist - timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                challenge_date = now_ist.strftime('%Y-%m-%d')
            
            # Delete current cache
            await self.cache.delete(self.daily_cache_key)
            
            # Set fetching flag
            self._is_fetching = True
            
            try:
                # Fetch fresh solution (without additional locking since we already have it)
                from utils.n8n_enhanced import get_code_from_n8n_simple
                from utils.code_validator import LeetCodeValidator
                
                logger.info(f"🔒 Force fetching fresh solution from N8N for challenge date: {challenge_date}...")
                start_time = time.time()
                
                # Update last fetch time BEFORE making the call
                self.last_fetch_time = time.time()
                
                # Single attempt with full wait
                code, is_safe, warnings, problem_title = get_code_from_n8n_simple(
                    enable_validation=True,
                    timeout_seconds=360,  # 6 minutes for AI code generation
                    fallback_enabled=True,
                    challenge_date=challenge_date  # Pass the current challenge date
                )
                
                if not code:
                    logger.error("No code received from N8N during force refresh")
                    return None
                
                response_time = time.time() - start_time
                
                # Get quality score
                try:
                    validator = LeetCodeValidator()
                    _, _, quality_score = validator.quick_validate(code)
                except Exception:
                    quality_score = 0.7
                
                # Create solution object
                solution = CachedSolution(
                    code=code,
                    problem_slug="daily-challenge",
                    problem_title=problem_title or "Daily Challenge",  # Use actual problem title
                    is_safe=is_safe,
                    quality_score=quality_score,
                    warnings=warnings or [],
                    cached_at=time.time(),
                    retrieval_method="force_refresh_locked",
                    response_time=response_time,
                    is_daily_challenge=True
                )
                
                # Cache the solution
                await self.cache_daily_solution(solution)
                
                logger.info(f"✅ Force refresh completed successfully ({response_time:.1f}s)")
                return solution
                
            except Exception as e:
                logger.error(f"Force refresh failed: {e}")
                return None
            finally:
                self._is_fetching = False

# Global instance will be initialized in main.py
code_cache_manager: Optional[CodeCacheManager] = None

def get_code_cache() -> CodeCacheManager:
    """Get the global code cache manager instance"""
    global code_cache_manager
    if code_cache_manager is None:
        raise RuntimeError("Code cache manager not initialized")
    return code_cache_manager

def init_code_cache(cache_manager: CacheManager) -> CodeCacheManager:
    """Initialize the global code cache manager"""
    global code_cache_manager
    code_cache_manager = CodeCacheManager(cache_manager)
    return code_cache_manager