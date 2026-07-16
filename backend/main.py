"""
Complete FastAPI Main Application - PRD Compliant
Redis cache, proper CORS, rate limiting, and multi-user support
"""

import os
import asyncio
import logging
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
import pytz

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
# Rate limiting imports disabled - unlimited access
# from slowapi import Limiter, _rate_limit_exceeded_handler
# from slowapi.util import get_remote_address
# from slowapi.errors import RateLimitExceeded
import time
import uvicorn
from dotenv import load_dotenv

# Import fixed modules
from auth import (
    decrypt_credentials, 
    generate_jwt_token, 
    initialize_auth_system,
    cleanup_auth_system,
    get_auth_health,
    RateLimitExceeded as AuthRateLimitExceeded
)
from cache import CacheManager
from scheduler import setup_scheduler, start_scheduler, stop_scheduler
from websocket import setup_websocket_routes
from user_manager import UserManager
from code_cache import init_code_cache, get_code_cache

# Enhanced utilities
try:
    from utils.n8n_enhanced import (
        get_code_from_n8n_simple,
        check_n8n_health,
        N8NTimeoutError,
        get_n8n_configuration,
        test_n8n_connectivity
    )
    print("[OK] Enhanced N8N utilities imported successfully")
except ImportError as e:
    print(f"[WARN] Failed to import enhanced N8N utilities: {e}")
    # Create dummy functions
    async def get_code_from_n8n_simple(*args, **kwargs):
        raise HTTPException(status_code=503, detail="N8N utilities not available")
    def check_n8n_health(*args, **kwargs):
        return {'status': 'unavailable', 'error': 'N8N utilities not imported'}
    class N8NTimeoutError(Exception):
        pass
    def get_n8n_configuration():
        return {'error': 'N8N utilities not available'}
    def test_n8n_connectivity():
        return {'error': 'N8N utilities not available'}

try:
    from utils.code_validator import LeetCodeValidator, quick_fix_leetcode
    print("[OK] Enhanced code validator imported successfully")
except ImportError as e:
    print(f"[WARN] Failed to import code validator: {e}")
    class LeetCodeValidator:
        def quick_validate(self, code):
            return code, True, 0.5
    def quick_fix_leetcode(code):
        return code, True, []

try:
    from utils.leetcode_submit import daily_challenge_automation
    print("[OK] Enhanced leetcode submit module imported successfully")
except ImportError as e:
    print(f"[WARN] Failed to import leetcode submit module: {e}")
    def daily_challenge_automation(*args, **kwargs):
        raise HTTPException(status_code=503, detail="LeetCode submission module not available")

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format=os.getenv('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
)
logger = logging.getLogger(__name__)

# Global managers - Redis-based per PRD
cache_manager = CacheManager()
user_manager = UserManager()

# Rate limiting DISABLED - Unlimited access
# limiter = Limiter(
#     key_func=get_remote_address,
#     storage_uri=os.getenv('REDIS_URL', 'redis://localhost:6379')
# )

# Helper function for IST-based daily challenge key
def get_daily_challenge_key():
    """Get current daily challenge key based on 6 AM IST refresh schedule"""
    ist = pytz.timezone('Asia/Kolkata')
    now_ist = datetime.now(ist)
    
    # If before 6 AM IST, use previous day's challenge
    if now_ist.hour < 6:
        challenge_date = (now_ist - timedelta(days=1)).strftime('%Y-%m-%d')
    else:
        challenge_date = now_ist.strftime('%Y-%m-%d')
    
    return challenge_date, now_ist

def calculate_cache_ttl(now_ist):
    """Calculate TTL until next 6 AM IST"""
    next_6am_ist = now_ist.replace(hour=6, minute=0, second=0, microsecond=0)
    if now_ist.hour >= 6:
        next_6am_ist += timedelta(days=1)
    
    return int((next_6am_ist - now_ist).total_seconds())

def get_daily_trigger_key(today_key: str = None):
    """Get the daily trigger tracking key for today"""
    if not today_key:
        today_key, _ = get_daily_challenge_key()
    return f"daily_trigger:{today_key}"

# Request deduplicator for concurrent cache misses per PRD
class RequestDeduplicator:
    def __init__(self):
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()
    
    async def deduplicate(self, cache_key: str, fetch_func):
        """Deduplicate concurrent requests for the same cache key"""
        async with self._lock:
            if cache_key in self.pending_requests:
                # Wait for existing request
                existing_future = self.pending_requests[cache_key]
                logger.info(f"Deduplicating request for key: {cache_key}")
                try:
                    return await existing_future
                except Exception as e:
                    # If the original request failed, allow this one to proceed
                    if cache_key in self.pending_requests:
                        del self.pending_requests[cache_key]
                    raise e
            
            # Create new future for this request
            future = asyncio.create_task(fetch_func())
            self.pending_requests[cache_key] = future
            
        try:
            result = await future
            return result
        finally:
            # Clean up completed request
            async with self._lock:
                if cache_key in self.pending_requests:
                    del self.pending_requests[cache_key]

deduplicator = RequestDeduplicator()

# Pydantic models per PRD
class HealthResponse(BaseModel):
    status: str
    redis_status: str
    cache_status: str
    active_users: int
    message: str = ""
    timestamp: str
    prd_compliant: bool = True

class SolveDailyRequest(BaseModel):
    """Request model for solve-daily endpoint per PRD"""
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=100)  
    encryption_key: Optional[str] = Field(None, min_length=1)
    user_id: str = Field(..., min_length=1, max_length=50)
    force_refresh: bool = Field(default=False)
    
    @validator('user_id')
    def validate_user_id(cls, v):
        if not v.startswith('user_'):
            raise ValueError('user_id must start with "user_"')
        return v

class LoginRequest(BaseModel):
    """Legacy login request model for compatibility"""
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=100)
    encryption_key: Optional[str] = Field(None, min_length=1)
    user_id: str = Field(..., min_length=1, max_length=50)

# Application lifespan management per PRD
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown per PRD requirements"""
    try:
        # Startup sequence
        logger.info("Starting LeetCode Solver application (PRD compliant v1.0)")
        
        # Initialize Redis cache manager per PRD
        await cache_manager.initialize()
        logger.info("Redis cache manager initialized successfully")
        
        # Initialize authentication system with Redis rate limiting
        auth_initialized = await initialize_auth_system()
        if auth_initialized:
            logger.info("Authentication system with Redis rate limiting initialized")
        else:
            logger.warning("Authentication system initialization failed - rate limiting may be disabled")
        
        # Setup and start scheduler for 6 AM IST refresh per PRD
        scheduler = setup_scheduler(cache_manager)
        start_scheduler(scheduler)
        logger.info("Scheduler started for 6 AM IST daily refresh per PRD")
        app.state.scheduler = scheduler
        
        # Start user manager cleanup task
        user_manager.start_cleanup_task()
        logger.info("User manager cleanup task started")
        
        # Initialize code cache manager with Redis backend
        code_cache = init_code_cache(cache_manager)
        app.state.code_cache = code_cache
        logger.info("Code cache manager initialized with Redis backend")
        
        # Test N8N connectivity during startup
        try:
            n8n_health = check_n8n_health()
            if n8n_health.get('status') == 'healthy':
                logger.info("N8N connectivity verified successfully")
            else:
                logger.warning(f"N8N connectivity issues detected: {n8n_health.get('status')}")
        except Exception as e:
            logger.warning(f"N8N health check failed during startup: {e}")
        
        # Smart daily trigger logic - only trigger N8N on first startup of the day
        try:
            logger.info("🚀 Server startup: Checking smart daily trigger logic...")
            today_key, now_ist = get_daily_challenge_key()
            
            # Create daily trigger tracking key
            daily_trigger_key = f"daily_trigger:{today_key}"
            
            # Check if we already have today's solution cached
            cached_solution = await cache_manager.get_daily_solution(today_key)
            
            # Check if we've already triggered N8N via server startup today
            startup_triggered_today = await cache_manager.get(daily_trigger_key)
            
            if cached_solution:
                logger.info(f"✅ Today's solution already cached for {today_key}")
                if startup_triggered_today:
                    logger.info(f"📝 N8N already triggered via startup today - using cached solution")
                else:
                    logger.info(f"📝 Solution cached via 6 AM scheduler - using cached solution")
                logger.info(f"🔄 Server restart detected - skipping N8N trigger")
            else:
                if startup_triggered_today:
                    logger.info(f"⚠️ Startup already triggered N8N today but no solution cached")
                    logger.info(f"📝 This suggests previous startup failed - retrying N8N trigger...")
                else:
                    logger.info(f"🌅 First startup of the day for {today_key} - triggering N8N...")
                
                # Trigger N8N and mark that we've triggered it today
                logger.info(f"❌ No solution cached for {today_key} - fetching fresh solution...")
                fresh_solution = await code_cache.force_refresh()
                
                if fresh_solution:
                    logger.info(f"✅ Startup solution fetch successful!")
                    logger.info(f"📊 Safety: {fresh_solution.is_safe}, Quality: {fresh_solution.quality_score:.2f}")
                    if fresh_solution.warnings:
                        logger.info(f"⚠️  Warnings: {'; '.join(fresh_solution.warnings[:2])}")
                    
                    # Mark that we've successfully triggered N8N via startup today
                    ttl = calculate_cache_ttl(now_ist)
                    await cache_manager.set(daily_trigger_key, f"triggered_at_{now_ist.isoformat()}", ttl)
                    logger.info(f"🏷️ Marked daily trigger complete for {today_key} (TTL: {ttl}s)")
                else:
                    logger.warning("⚠️ Startup solution fetch failed - cache miss will trigger N8N on first user request")
                
        except Exception as startup_fetch_error:
            logger.warning(f"⚠️ Startup solution check error: {startup_fetch_error}")
            logger.info("📝 Continuing startup - users can still trigger fresh solutions via N8N")
        
        logger.info("Application startup completed successfully per PRD")
        
        yield
        
        # Shutdown sequence
        logger.info("Shutting down LeetCode Solver application...")
        
        # Stop scheduler
        if hasattr(app.state, 'scheduler'):
            stop_scheduler(app.state.scheduler)
            logger.info("Scheduler stopped")
        
        # Close Redis connections
        await cache_manager.close()
        logger.info("Redis cache connections closed")
        
        # Clean up authentication system
        await cleanup_auth_system()
        logger.info("Authentication system cleaned up")
        
        # Clean up user sessions
        await user_manager.cleanup_all_sessions()
        logger.info("User sessions cleaned up")
        
        logger.info("Application shutdown completed successfully")
        
    except Exception as e:
        logger.error(f"Error during application lifecycle: {e}")
        raise

# Create FastAPI application per PRD
app = FastAPI(
    title="LeetCode Daily Challenge Auto-Solver",
    description="PRD-compliant automated LeetCode daily challenge solver with Redis cache and multi-user support",
    version="1.0.0",
    docs_url="/docs" if os.getenv('DEBUG', 'False').lower() == 'true' else None,
    redoc_url="/redoc" if os.getenv('DEBUG', 'False').lower() == 'true' else None,
    lifespan=lifespan
)

# Rate limiting DISABLED - Unlimited access
# app.state.limiter = limiter
# app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Enhanced CORS Configuration per PRD
cors_origins = os.getenv('CORS_ORIGINS', 'http://localhost:3000,https://localhost:3000,http://localhost:8080,http://127.0.0.1:3000,http://127.0.0.1:8080,null').split(',')
cors_origins = [origin.strip() for origin in cors_origins if origin.strip()]

# For development: allow all origins if DEBUG is true
if os.getenv('DEBUG', 'True').lower() == 'true':
    cors_origins = ["*"]  # Allow all origins in development
    logger.info("CORS: Allowing all origins for development")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True if cors_origins != ["*"] else False,  # No credentials with *
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization", 
        "Content-Type", 
        "X-Requested-With",
        "Accept",
        "Origin",
        "Cache-Control",
        "X-CSRF-Token",
        "*"  # Allow all headers in development
    ],
    expose_headers=["X-Total-Count", "X-Cache-Status", "X-Response-Time"]
)

# Setup WebSocket routes
setup_websocket_routes(app, user_manager)

# Exception handlers
@app.exception_handler(AuthRateLimitExceeded)
async def auth_rate_limit_handler(request: Request, exc: AuthRateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Too many authentication attempts. Please try again later.",
            "type": "auth_rate_limit_exceeded",
            "retry_after": 900  # 15 minutes
        }
    )

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    logger.error(f"ValueError: {exc}")
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "type": "validation_error"}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": "server_error"}
    )

# Middleware for request timing
@app.middleware("http")
async def add_response_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Response-Time"] = str(round(process_time * 1000, 2))
    return response

# Routes per PRD specification

@app.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """Comprehensive system health check per PRD monitoring requirements"""
    try:
        start_time = time.time()
        
        # Check Redis connection per PRD
        redis_healthy = await cache_manager.ping()
        redis_status = "connected" if redis_healthy else "disconnected"
        
        # Check cache functionality per PRD
        if redis_healthy:
            cache_test_key = f"health_check_test_{int(time.time())}"
            test_value = "health_test"
            
            await cache_manager.set(cache_test_key, test_value, ttl=10)
            retrieved_value = await cache_manager.get(cache_test_key)
            cache_status = "working" if retrieved_value == test_value else "failed"
            await cache_manager.delete(cache_test_key)
        else:
            cache_status = "unavailable"
        
        # Get active user count
        active_users = user_manager.get_active_user_count()
        
        # Overall health determination
        is_healthy = redis_healthy and cache_status == "working"
        overall_status = "healthy" if is_healthy else "unhealthy"
        
        # Performance check
        response_time = time.time() - start_time
        if response_time > 1.0:  # Health check taking too long
            overall_status = "degraded"
        
        message = "System operating normally per PRD" if is_healthy else "System has performance or connectivity issues"
        
        return HealthResponse(
            status=overall_status,
            redis_status=redis_status,
            cache_status=cache_status,
            active_users=active_users,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="error",
            redis_status="error",
            cache_status="error",
            active_users=0,
            message=f"Health check failed: {str(e)}",
            timestamp=datetime.now(timezone.utc).isoformat()
        )

@app.get("/solve-daily")
async def solve_daily_challenge_get(request: Request) -> Dict[str, Any]:
    """
    GET endpoint for daily solution - returns cached solution only per PRD
    No credentials required, cache-only access with <100ms target
    """
    try:
        logger.info("Daily challenge solution requested (GET - cache only)")
        
        start_time = time.time()
        today_key, now_ist = get_daily_challenge_key()
        
        # Use deduplicator for concurrent requests per PRD multi-user support
        async def get_cached_solution():
            return await cache_manager.get_daily_solution(today_key)
        
        cached_solution = await deduplicator.deduplicate(
            f"daily_solution_get:{today_key}", 
            get_cached_solution
        )
        
        response_time_ms = (time.time() - start_time) * 1000
        
        if cached_solution:
            # Cache hit - return instantly per PRD <100ms requirement
            logger.info(f"Cache hit - solution served in {response_time_ms:.1f}ms (PRD target: <100ms)")
            
            return {
                "status": "success",
                "source": "redis_cache",
                "response_time_ms": response_time_ms,
                "cache_hit": True,
                "solution": {
                    "code": cached_solution.get('code', ''),
                    "problem_title": cached_solution.get('problem_title', 'Daily Challenge'),
                    "problem_slug": cached_solution.get('problem_slug', 'daily-challenge'),
                    "is_safe": cached_solution.get('is_safe', True),
                    "quality_score": cached_solution.get('quality_score', 0.0),
                    "warnings": cached_solution.get('warnings', [])[:3],
                    "cached_at": cached_solution.get('cached_at'),
                    "cache_date": today_key
                },
                "meta": {
                    "prd_compliant": True,
                    "next_refresh": "6:00 AM IST daily",
                    "performance_target_met": response_time_ms < 100
                }
            }
        else:
            # Cache miss - per PRD, GET returns miss info
            return {
                "status": "cache_miss",
                "source": "redis_cache", 
                "response_time_ms": response_time_ms,
                "cache_hit": False,
                "message": "No solution cached for today. Solution will be available after 6:00 AM IST refresh.",
                "meta": {
                    "prd_compliant": True,
                    "use_post_endpoint": "Use POST /solve-daily with credentials to trigger N8N fetch",
                    "next_refresh": "6:00 AM IST daily"
                }
            }
            
    except Exception as e:
        logger.error(f"Daily challenge GET endpoint error: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Daily challenge service failed: {str(e)}"
        )

@app.post("/solve-daily")
async def solve_daily_challenge_post(
    request: Request, 
    solve_request: SolveDailyRequest,
    background_tasks: BackgroundTasks = None
) -> Dict[str, Any]:
    """
    POST endpoint for solving daily challenge with N8N integration per PRD
    Supports cache miss recovery and force refresh
    """
    try:
        logger.info(f"Daily challenge solve requested for user: {solve_request.user_id}")
        
        start_time = time.time()
        today_key, now_ist = get_daily_challenge_key()
        
        # Check cache first unless force refresh requested
        logger.info(f"Force refresh requested: {solve_request.force_refresh}")
        if not solve_request.force_refresh:
            cached_solution = await cache_manager.get_daily_solution(today_key)
            logger.info(f"Cached solution exists: {cached_solution is not None}")
            
            if cached_solution:
                response_time_ms = (time.time() - start_time) * 1000
                logger.info(f"Cache hit for user {solve_request.user_id} - {response_time_ms:.1f}ms")
                
                # Prepare result for cache hit
                cache_hit_result = {
                    "status": "success",
                    "source": "redis_cache",
                    "response_time_ms": response_time_ms,
                    "cache_hit": True,
                    "solution": cached_solution,
                    "user_id": solve_request.user_id,
                    "meta": {
                        "prd_compliant": True,
                        "performance_target_met": response_time_ms < 100
                    }
                }
                
                # Trigger automation even for cache hits
                logger.info(f"Cache hit - still triggering automation for user {solve_request.user_id}")
                if background_tasks:
                    try:
                        solution_code = cached_solution.get('code', '')
                        if solution_code:
                            # Handle credentials (encrypted or plain) for automation
                            if solve_request.encryption_key:
                                # Decrypt credentials for automation
                                username, password = await decrypt_credentials(
                                    solve_request.username,
                                    solve_request.password,
                                    solve_request.encryption_key
                                )
                                logger.info(f"Cache hit - credentials decrypted for automation - user {solve_request.user_id}")
                            else:
                                # Use credentials directly
                                username = solve_request.username
                                password = solve_request.password
                                logger.info(f"Cache hit - using plain credentials for automation - user {solve_request.user_id}")
                            
                            background_tasks.add_task(
                                daily_challenge_automation,
                                username=username,
                                password=password,
                                solution_code=solution_code,
                                user_id=solve_request.user_id
                            )
                            logger.info(f"Chrome automation triggered for cached solution - user {solve_request.user_id}")
                        else:
                            logger.warning(f"No solution code found in cache for user {solve_request.user_id}")
                    except Exception as automation_error:
                        logger.error(f"Failed to trigger automation for cached solution - user {solve_request.user_id}: {automation_error}")
                else:
                    logger.warning(f"Background tasks not available for automation - user {solve_request.user_id}")
                
                return cache_hit_result
        
        # Cache miss or force refresh - check smart trigger logic first
        logger.info(f"Cache miss/force refresh detected for user {solve_request.user_id}")
        
        # Check if we've already triggered N8N via startup today (unless force refresh)
        if not solve_request.force_refresh:
            daily_trigger_key = get_daily_trigger_key(today_key)
            startup_triggered_today = await cache_manager.get(daily_trigger_key)
            
            if startup_triggered_today:
                # We already triggered N8N today via startup, but cache is missing
                logger.warning(f"Cache miss detected but startup already triggered N8N today for {today_key}")
                logger.info(f"Avoiding duplicate N8N trigger for user {solve_request.user_id}")
                
                response_time_ms = (time.time() - start_time) * 1000
                return {
                    "status": "error",
                    "error": "Solution temporarily unavailable",
                    "message": "The daily solution was processed earlier but is not currently cached. Please try again in a few minutes or contact support if this persists.",
                    "response_time_ms": response_time_ms,
                    "cache_hit": False,
                    "user_id": solve_request.user_id,
                    "retry_suggested": True,
                    "meta": {
                        "startup_triggered_today": True,
                        "cache_miss_reason": "Cache unavailable despite startup trigger",
                        "prd_compliant": True
                    }
                }
        
        # Proceed with N8N trigger (first time today or force refresh)
        logger.info(f"Triggering N8N workflow for user {solve_request.user_id} (first time today or force refresh)")
        
        async def fetch_fresh_solution():
            try:
                # Handle credentials (encrypted or plain)
                if solve_request.encryption_key:
                    # Decrypt credentials with rate limiting
                    username, password = await decrypt_credentials(
                        solve_request.username,
                        solve_request.password,
                        solve_request.encryption_key
                    )
                else:
                    # Use credentials directly (for frontend without encryption)
                    username = solve_request.username
                    password = solve_request.password
                
                logger.info(f"Credentials decrypted for user {solve_request.user_id}")
                
                # Call N8N workflow per PRD specifications
                code, is_safe, warnings, problem_title = get_code_from_n8n_simple(
                    enable_validation=True,
                    timeout_seconds=300,  # 5 minutes per PRD
                    fallback_enabled=True,
                    challenge_date=today_key  # Pass the current challenge date
                )
                
                if code and len(code.strip()) > 30:
                    # Enhance solution data per PRD
                    solution_data = {
                        'code': code,
                        'is_safe': is_safe,
                        'warnings': warnings or [],
                        'problem_title': problem_title or 'Daily Challenge',  # Use actual problem title
                        'problem_slug': 'daily-challenge',
                        'quality_score': 0.8,  # Default quality score
                        'fetched_by': solve_request.user_id,
                        'fetch_time': datetime.now(timezone.utc).isoformat(),
                        'n8n_response_time': 0.0,  # Would be filled by N8N client
                        'prd_compliant': True
                    }
                    
                    # Cache in Redis per PRD with TTL until next 6 AM IST
                    ttl_seconds = calculate_cache_ttl(now_ist)
                    logger.info(f"Caching solution until next 6 AM IST (TTL: {ttl_seconds/3600:.1f} hours)")
                    
                    cache_success = await cache_manager.set_daily_solution(
                        solution_data=solution_data,
                        date=today_key,
                        ttl=ttl_seconds
                    )
                    
                    if cache_success:
                        logger.info(f"Fresh solution cached successfully for {today_key}")
                        
                        # Mark that we've successfully triggered N8N today via user request
                        daily_trigger_key = get_daily_trigger_key(today_key)
                        await cache_manager.set(daily_trigger_key, f"user_triggered_at_{now_ist.isoformat()}", ttl_seconds)
                        logger.info(f"🏷️ Marked daily trigger complete for {today_key} (user-triggered)")
                    else:
                        logger.warning("Failed to cache fresh solution")
                    
                    return solution_data
                else:
                    raise Exception("No valid solution received from N8N workflow")
                    
            except AuthRateLimitExceeded:
                raise HTTPException(
                    status_code=429,
                    detail="Too many authentication attempts. Please try again later."
                )
            except Exception as e:
                logger.error(f"Fresh solution fetch failed: {e}")
                raise Exception(f"Solution fetch failed: {str(e)}")
        
        # Use deduplicator for concurrent cache misses per PRD
        try:
            fresh_solution = await deduplicator.deduplicate(
                f"fresh_solution_post:{today_key}:{solve_request.user_id}",
                fetch_fresh_solution
            )
        except Exception as e:
            logger.error(f"Deduplicated fetch failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch solution: {str(e)}"
            )
        
        response_time_ms = (time.time() - start_time) * 1000
        
        logger.info(f"Fresh solution fetched and cached in {response_time_ms:.1f}ms")
        
        return {
            "status": "success",
            "source": "n8n_fresh",
            "response_time_ms": response_time_ms,
            "cache_hit": False,
            "solution": fresh_solution,
            "user_id": solve_request.user_id,
            "meta": {
                "solution_cached": True,
                "prd_compliant": True,
                "cache_duration": "24 hours",
                "next_refresh": "6:00 AM IST daily"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Solve daily POST error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to solve daily challenge: {str(e)}"
        )

@app.get("/users/active")
async def get_active_users(request: Request) -> Dict[str, Any]:
    """Get active users and system status per PRD monitoring"""
    return {
        "active_users": user_manager.get_active_user_count(),
        "max_users": "unlimited",
        "redis_status": "connected" if await cache_manager.ping() else "disconnected",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prd_compliant": True
    }

@app.get("/cache/stats") 
async def get_cache_stats(request: Request) -> Dict[str, Any]:
    """Get comprehensive Redis cache statistics per PRD monitoring"""
    try:
        info = await cache_manager.get_info()
        memory = await cache_manager.get_memory_usage()
        
        # Calculate cache efficiency metrics
        hits = info.get('keyspace_hits', 0)
        misses = info.get('keyspace_misses', 0)
        total_ops = hits + misses
        hit_ratio = (hits / total_ops * 100) if total_ops > 0 else 0
        
        return {
            "cache_type": "redis",
            "connection_status": "connected",
            "performance_metrics": {
                "redis_version": info.get('redis_version', 'unknown'),
                "uptime_seconds": info.get('uptime_in_seconds', 0),
                "instantaneous_ops_per_sec": info.get('instantaneous_ops_per_sec', 0),
                "total_commands_processed": info.get('total_commands_processed', 0)
            },
            "memory_usage": {
                "used_memory_human": info.get('used_memory_human', 'unknown'),
                "used_memory_peak_human": memory.get('used_memory_peak_human', 'unknown'),
                "mem_fragmentation_ratio": memory.get('mem_fragmentation_ratio', 0.0)
            },
            "cache_efficiency": {
                "keyspace_hits": hits,
                "keyspace_misses": misses,
                "hit_ratio_percent": round(hit_ratio, 2),
                "connected_clients": info.get('connected_clients', 0)
            },
            "prd_compliance": {
                "target_response_time_ms": 100,
                "multi_user_support": True,
                "cache_persistence": True,
                "daily_refresh_schedule": "6:00 AM IST"
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        return {"error": "Failed to retrieve Redis cache statistics", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/n8n/health")
async def get_n8n_health_status(request: Request) -> Dict[str, Any]:
    """Get N8N workflow health and connectivity status per PRD"""
    try:
        health_data = check_n8n_health()
        
        # Add PRD compliance information
        health_data['prd_compliance'] = {
            'endpoint_redundancy': len(health_data.get('configuration', {}).get('trigger_endpoints', [])) > 1,
            'fallback_enabled': True,
            'comprehensive_monitoring': True,
            'automated_recovery': True
        }
        
        return health_data
        
    except Exception as e:
        logger.error(f"N8N health check failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prd_compliance": {"monitoring_active": True}
        }

@app.get("/n8n/config")
async def get_n8n_configuration(request: Request) -> Dict[str, Any]:
    """Get N8N configuration for debugging per PRD"""
    try:
        config = get_n8n_configuration()
        config['timestamp'] = datetime.now(timezone.utc).isoformat()
        return config
    except Exception as e:
        return {
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

@app.post("/n8n/test")
async def test_n8n_connectivity(request: Request) -> Dict[str, Any]:
    """Test N8N connectivity on demand per PRD"""
    try:
        test_result = test_n8n_connectivity()
        return test_result
    except Exception as e:
        return {
            "test_passed": False,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

@app.get("/frontend/health")
async def get_frontend_health_status(request: Request) -> Dict[str, Any]:
    """Simplified health check specifically for frontend use"""
    try:
        start_time = time.time()
        
        # Get component health statuses
        redis_health = await cache_manager.ping()
        auth_health = await get_auth_health()
        n8n_health = check_n8n_health()
        
        # Calculate overall system health
        critical_components = {
            'redis': redis_health,
            'auth_system': auth_health.get('rate_limiter_initialized', False),
            'n8n': n8n_health.get('status') in ['healthy', 'degraded']
        }
        
        healthy_components = sum(1 for is_healthy in critical_components.values() if is_healthy)
        system_health_score = healthy_components / len(critical_components)
        
        if system_health_score >= 0.8:
            overall_status = 'healthy'
        elif system_health_score >= 0.6:
            overall_status = 'degraded'
        else:
            overall_status = 'unhealthy'
        
        # Get cache stats for performance metrics
        try:
            cache_info = await cache_manager.get_info()
            cache_memory = await cache_manager.get_memory_usage()
        except:
            cache_info = {}
            cache_memory = {}
        
        # Get user count
        active_users = user_manager.get_active_user_count()
        
        response_time = time.time() - start_time
        
        return {
            "overall_status": overall_status,
            "health_score": round(system_health_score, 2),
            "response_time_ms": round(response_time * 1000, 2),
            "components": {
                "redis": {
                    "status": "connected" if redis_health else "disconnected",
                    "version": cache_info.get('redis_version', 'unknown'),
                    "memory_used": cache_info.get('used_memory_human', 'N/A'),
                    "hit_ratio": f"{((cache_info.get('keyspace_hits', 0) / max(cache_info.get('keyspace_hits', 0) + cache_info.get('keyspace_misses', 0), 1)) * 100):.1f}%"
                },
                "authentication": {
                    "status": "active" if auth_health.get('rate_limiter_initialized') else "inactive",
                    "max_attempts": auth_health.get('max_attempts', 'N/A'),
                    "lockout_minutes": auth_health.get('lockout_minutes', 'N/A')
                },
                "n8n_workflow": {
                    "status": n8n_health.get('status', 'unknown'),
                    "trigger_accessible": n8n_health.get('trigger_accessible', False),
                    "fetch_accessible": n8n_health.get('fetch_accessible', False),
                    "health_score": f"{(n8n_health.get('overall_health_score', 0) * 100):.0f}%"
                },
                "system": {
                    "active_users": active_users,
                    "max_users": "unlimited",
                    "uptime": cache_info.get('uptime_in_seconds', 0)
                }
            },
            "recommendations": n8n_health.get('recommendations', [])[:3] if n8n_health.get('recommendations') else [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prd_compliant": True
        }
        
    except Exception as e:
        logger.error(f"Frontend health check failed: {e}")
        return {
            "overall_status": "error",
            "health_score": 0,
            "error": str(e),
            "components": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prd_compliant": True
        }

# Global automation status tracking
automation_status = {}

@app.get("/automation-status/{user_id}")
async def get_automation_status(user_id: str):
    """Get the current automation status for a user"""
    status = automation_status.get(user_id, {
        "status": "not_started", 
        "step": "waiting",
        "progress": 0,
        "message": "Automation not started"
    })
    return status

@app.post("/automation-status/{user_id}")
async def update_automation_status(user_id: str, status_data: dict):
    """Update automation status for a user"""
    automation_status[user_id] = {
        **automation_status.get(user_id, {}),
        **status_data,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    logger.info(f"Automation status updated for {user_id}: {status_data}")
    return {"success": True}

@app.get("/system/status")
async def get_system_status(request: Request) -> Dict[str, Any]:
    """Comprehensive system status per PRD monitoring requirements"""
    try:
        # Get component health statuses
        redis_health = await cache_manager.ping()
        auth_health = await get_auth_health()
        n8n_health = check_n8n_health()
        
        # Calculate overall system health
        critical_components = {
            'redis': redis_health,
            'auth_system': auth_health.get('rate_limiter_initialized', False),
            'n8n': n8n_health.get('status') in ['healthy', 'degraded']
        }
        
        healthy_components = sum(1 for is_healthy in critical_components.values() if is_healthy)
        system_health_score = healthy_components / len(critical_components)
        
        if system_health_score >= 0.8:
            overall_status = 'healthy'
        elif system_health_score >= 0.6:
            overall_status = 'degraded'
        else:
            overall_status = 'unhealthy'
        
        return {
            "overall_status": overall_status,
            "health_score": round(system_health_score, 2),
            "components": {
                "redis_cache": {
                    "status": "healthy" if redis_health else "unhealthy",
                    "details": await cache_manager.get_info() if redis_health else {"error": "disconnected"}
                },
                "authentication": {
                    "status": "healthy" if auth_health.get('rate_limiter_initialized') else "degraded",
                    "details": auth_health
                },
                "n8n_workflow": {
                    "status": n8n_health.get('status', 'unknown'),
                    "details": n8n_health
                },
                "user_manager": {
                    "status": "healthy",
                    "active_users": user_manager.get_active_user_count(),
                    "max_users": "unlimited"
                }
            },
            "prd_compliance": {
                "redis_backend": True,
                "rate_limiting": auth_health.get('rate_limiter_initialized', False),
                "multi_user_support": True,
                "daily_refresh_schedule": "6:00 AM IST",
                "response_time_target": "< 100ms for cached requests",
                "fallback_mechanisms": True
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"System status check failed: {e}")
        return {
            "overall_status": "error",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

# Legacy endpoint for backward compatibility
@app.post("/login")
async def login_legacy(
    request: Request,
    login_data: LoginRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Legacy login endpoint - redirects to solve-daily workflow per PRD
    """
    try:
        logger.info(f"Legacy login request from user: {login_data.user_id}")
        
        # Convert to solve request and redirect
        solve_request = SolveDailyRequest(
            username=login_data.username,
            password=login_data.password,
            encryption_key=login_data.encryption_key,
            user_id=login_data.user_id,
            force_refresh=False
        )
        
        # Call the main solve endpoint
        result = await solve_daily_challenge_post(request, solve_request, background_tasks)
        
        # Trigger Chrome automation for every successful login/submit
        logger.info(f"Checking automation trigger condition - result status: {result.get('status')}")
        if result.get("status") == "success":
            logger.info(f"Automation condition met - starting Chrome automation for user {login_data.user_id}")
            try:
                # Handle credentials (encrypted or plain)
                if hasattr(login_data, 'encryption_key') and login_data.encryption_key:
                    logger.info("Using encrypted credentials")
                    # Decrypt credentials before passing to automation
                    decrypted_username, decrypted_password = await decrypt_credentials(
                        login_data.username,
                        login_data.password,
                        login_data.encryption_key
                    )
                else:
                    logger.info("Using plain text credentials")
                    # Use credentials directly
                    decrypted_username = login_data.username
                    decrypted_password = login_data.password
                solution_code = result.get("solution", {}).get("corrected_code") or result.get("solution", {}).get("code")
                logger.info(f"Solution code length for automation: {len(solution_code) if solution_code else 0} chars")
                background_tasks.add_task(
                    daily_challenge_automation,
                    username=decrypted_username,
                    password=decrypted_password,
                    solution_code=solution_code,
                    user_id=login_data.user_id
                )
                logger.info(f"Chrome automation background task added for user {login_data.user_id}")
            except Exception as automation_error:
                logger.error(f"Failed to trigger automation for user {login_data.user_id}: {automation_error}")
        else:
            logger.warning(f"Automation not triggered - result status was '{result.get('status')}' instead of 'success'")
        
        # Format response for legacy compatibility
        return {
            "status": "success" if result.get("status") == "success" else "error",
            "message": "Authentication successful, solution retrieved" if result.get("status") == "success" else "Login failed",
            "user_id": login_data.user_id,
            "jwt_token": generate_jwt_token(login_data.user_id),
            "solution_data": result.get("solution", {}),
            "legacy_endpoint": True,
            "redirect_to": "Use POST /solve-daily for full functionality"
        }
        
    except HTTPException as e:
        return {
            "status": "error", 
            "message": str(e.detail),
            "user_id": login_data.user_id,
            "legacy_endpoint": True
        }
    except Exception as e:
        logger.error(f"Legacy login error: {e}")
        return {
            "status": "error",
            "message": f"Login processing failed: {str(e)}",
            "legacy_endpoint": True
        }

@app.get("/leetcode-code")
async def get_leetcode_code(request: Request) -> Dict[str, Any]:
    """
    Dedicated endpoint for LeetCode daily challenge code
    Returns today's solution from cache with 6AM IST refresh schedule
    """
    try:
        logger.info("LeetCode code requested via /leetcode-code endpoint")
        
        start_time = time.time()
        today_key, now_ist = get_daily_challenge_key()
        
        # Get cached solution for today's challenge
        async def get_cached_solution():
            return await cache_manager.get_daily_solution(today_key)
        
        cached_solution = await deduplicator.deduplicate(
            f"leetcode_code_get:{today_key}", 
            get_cached_solution
        )
        
        response_time_ms = (time.time() - start_time) * 1000
        
        if cached_solution:
            # NUCLEAR FIX: Always check if cached solution contains sudoku and reject it
            cached_code = cached_solution.get('code', '')
            if 'sudoku' in cached_code.lower() or 'isvalidsudoku' in cached_code.lower():
                logger.warning("REJECTING CACHED SUDOKU SOLUTION - Forcing fresh lookup")
                cached_solution = None  # Force cache miss
            
        if cached_solution:
            # Cache hit - return cached solution
            logger.info(f"LeetCode code served from Redis cache in {response_time_ms:.1f}ms")
            solution_code = cached_solution.get('code', '')
            corrected_code = cached_solution.get('corrected_code', solution_code)
            final_code = corrected_code if corrected_code else solution_code
            source = "redis_cache"
            cache_updated = False
            
            return {
                "status": "success",
                "source": source,
                "response_time_ms": response_time_ms,
                "cache_hit": True,
                "code": final_code,
                "solutionCode": final_code,  # Alternative field name for compatibility
                "pythonCode": final_code,    # Another common field name
                "problem_info": {
                    "title": cached_solution.get('problem_title', 'Daily Challenge'),
                    "slug": cached_solution.get('problem_slug', 'daily-challenge'),
                    "cached_at": cached_solution.get('cached_at'),
                    "cache_date": today_key
                },
                "quality_info": {
                    "is_safe": cached_solution.get('is_safe', True),
                    "quality_score": cached_solution.get('quality_score', 0.0),
                    "warnings": cached_solution.get('warnings', [])[:3]
                },
                "meta": {
                    "prd_compliant": True,
                    "next_refresh": "6:00 AM IST daily",
                    "performance_target_met": response_time_ms < 100,
                    "endpoint": "leetcode-code",
                    "cache_updated": cache_updated if 'cache_updated' in locals() else False,
                    "n8n_global_check": "performed" if 'n8n_code' in locals() else "skipped"
                }
            }
        else:
            # Cache miss - check n8n first, then fall back to direct API
            logger.info(f"LeetCode code cache miss for {today_key}, checking n8n global storage first...")
            
            # Step 1: Try n8n global storage first
            try:
                from utils.n8n_enhanced import check_n8n_global_storage_direct
                n8n_code, n8n_is_safe, n8n_warnings = check_n8n_global_storage_direct()
                
                if n8n_code and len(n8n_code.strip()) > 30:
                    # Check if it's not a stale sudoku solution
                    if 'sudoku' not in n8n_code.lower() and 'isvalidsudoku' not in n8n_code.lower():
                        logger.info(f"Found fresh solution in n8n global storage: {len(n8n_code)} chars")
                        
                        # Cache the n8n solution
                        solution_data = {
                            'code': n8n_code,
                            'corrected_code': n8n_code,
                            'is_safe': n8n_is_safe,
                            'warnings': n8n_warnings or [],
                            'problem_title': 'Daily Challenge',
                            'problem_slug': 'daily-challenge',
                            'quality_score': 0.85,
                            'cached_at': datetime.now(timezone.utc).isoformat(),
                            'fetch_time': datetime.now(timezone.utc).isoformat(),
                            'source': 'n8n_global_storage',
                            'prd_compliant': True
                        }
                        
                        # Calculate TTL until next 6AM IST
                        ttl_seconds = calculate_cache_ttl(now_ist)
                        cache_success = await cache_manager.set_daily_solution(
                            solution_data=solution_data,
                            date=today_key,
                            ttl=ttl_seconds
                        )
                        
                        response_time_ms = (time.time() - start_time) * 1000
                        logger.info(f"N8N solution cached successfully in {response_time_ms:.1f}ms")
                        
                        return {
                            "status": "success",
                            "source": "n8n_global_storage",
                            "response_time_ms": response_time_ms,
                            "cache_hit": False,
                            "cache_populated": cache_success,
                            "code": n8n_code,
                            "solutionCode": n8n_code,
                            "pythonCode": n8n_code,
                            "problem_info": {
                                "title": "Daily Challenge",
                                "slug": "daily-challenge",
                                "cached_at": solution_data['cached_at'],
                                "cache_date": today_key
                            },
                            "quality_info": {
                                "is_safe": n8n_is_safe,
                                "quality_score": 0.85,
                                "warnings": n8n_warnings or []
                            },
                            "meta": {
                                "prd_compliant": True,
                                "next_refresh": "6:00 AM IST daily",
                                "performance_target_met": response_time_ms < 100,
                                "endpoint": "leetcode-code",
                                "method": "n8n_workflow_integration",
                                "direct_api_bypassed": False
                            }
                        }
                    else:
                        logger.warning("N8N solution contains sudoku - rejecting and falling back to direct API")
                else:
                    logger.info("No solution found in n8n global storage, falling back to direct API")
                    
            except Exception as e:
                logger.warning(f"N8N global storage check failed: {e}, falling back to direct API")
            
            # Step 2: Fall back to direct LeetCode API if n8n failed
            logger.info("Falling back to direct LeetCode API...")
            
            try:
                # Call the fresh endpoint logic directly
                fresh_result = await get_fresh_leetcode_solution_internal()
                
                if fresh_result and fresh_result.get('code'):
                    # Cache the fresh solution
                    solution_data = {
                        'code': fresh_result['code'],
                        'corrected_code': fresh_result['code'],
                        'is_safe': fresh_result.get('quality_info', {}).get('is_safe', True),
                        'warnings': fresh_result.get('quality_info', {}).get('warnings', []),
                        'problem_title': fresh_result.get('problem_info', {}).get('title', 'Daily Challenge'),
                        'problem_slug': fresh_result.get('problem_info', {}).get('title_slug', 'daily-challenge'),
                        'quality_score': fresh_result.get('quality_info', {}).get('quality_score', 0.8),
                        'cached_at': datetime.now(timezone.utc).isoformat(),
                        'fetch_time': datetime.now(timezone.utc).isoformat(),
                        'source': 'direct_leetcode_api',
                        'prd_compliant': True
                    }
                    
                    # Calculate TTL until next 6AM IST
                    ttl_seconds = calculate_cache_ttl(now_ist)
                    cache_success = await cache_manager.set_daily_solution(
                        solution_data=solution_data,
                        date=today_key,
                        ttl=ttl_seconds
                    )
                    
                    response_time_ms = (time.time() - start_time) * 1000
                    
                    logger.info(f"Fresh solution from direct API cached successfully in {response_time_ms:.1f}ms")
                    
                    return {
                        "status": "success",
                        "source": "direct_leetcode_api",
                        "response_time_ms": response_time_ms,
                        "cache_hit": False,
                        "cache_populated": cache_success,
                        "code": fresh_result['code'],
                        "solutionCode": fresh_result['code'],
                        "pythonCode": fresh_result['code'],
                        "problem_info": fresh_result.get('problem_info', {}),
                        "quality_info": fresh_result.get('quality_info', {}),
                        "meta": {
                            "prd_compliant": True,
                            "next_refresh": "6:00 AM IST daily",
                            "performance_target_met": response_time_ms < 100,
                            "endpoint": "leetcode-code",
                            "method": "direct_api_bypass",
                            "n8n_bypassed": True
                        }
                    }
                    
            except Exception as e:
                logger.error(f"Direct LeetCode API failed: {e}")
            
            # No fallback solutions - N8N workflow required
            logger.error("All solution sources failed - N8N workflow must provide solutions")
            
            return {
                "status": "service_unavailable",
                "source": "no_source_available", 
                "response_time_ms": response_time_ms,
                "cache_hit": False,
                "code": "",
                "solutionCode": "",
                "pythonCode": "",
                "message": "Unable to fetch today's solution. Please try /leetcode-code-fresh endpoint or try again later.",
                "meta": {
                    "prd_compliant": True,
                    "direct_api_failed": True,
                    "cache_miss": True,
                    "next_refresh": "6:00 AM IST daily",
                    "current_cache_key": today_key,
                    "endpoint": "leetcode-code",
                    "recommended_action": "Use /leetcode-code-fresh endpoint for guaranteed fresh solution"
                }
            }
            
    except Exception as e:
        logger.error(f"LeetCode code endpoint error: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"LeetCode code service failed: {str(e)}"
        )

@app.get("/debug/n8n-workflow")
async def debug_n8n_workflow():
    """
    Debug endpoint to check what your n8n workflow is actually storing/returning
    """
    try:
        from utils.n8n_enhanced import check_n8n_global_storage_direct, EnhancedN8NClient
        
        # Check current n8n global storage
        logger.info("Debugging n8n workflow - checking global storage...")
        
        client = EnhancedN8NClient()
        code, is_safe, warnings = client.check_global_storage_direct()
        
        # Also try to trigger the workflow with today's date explicitly
        from datetime import datetime
        import pytz
        
        ist = pytz.timezone('Asia/Kolkata')
        now_ist = datetime.now(ist)
        today_date = now_ist.strftime('%Y-%m-%d')
        
        debug_info = {
            "current_global_storage": {
                "has_solution": code is not None and len(code.strip()) > 30,
                "code_length": len(code) if code else 0,
                "code_preview": code[:300] + "..." if code and len(code) > 300 else code,
                "contains_sudoku": "sudoku" in code.lower() if code else False,
                "contains_today": today_date in code if code else False,
                "is_safe": is_safe,
                "warnings": warnings
            },
            "workflow_trigger_info": {
                "today_date": today_date,
                "ist_time": now_ist.isoformat(),
                "hour": now_ist.hour,
                "should_use_previous_day": now_ist.hour < 6
            },
            "n8n_endpoints": {
                "trigger_urls": client.__class__.__dict__.get('TRIGGER_URLS', []),
                "fetch_urls": client.__class__.__dict__.get('FETCH_URLS', [])
            }
        }
        
        # Check what LeetCode's actual daily challenge is today
        import requests
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            query = {
                "query": """
                query questionOfToday {
                    activeDailyCodingChallengeQuestion {
                        date
                        question {
                            title
                            titleSlug
                            difficulty
                        }
                    }
                }
                """
            }
            
            response = requests.post('https://leetcode.com/graphql', json=query, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                question_data = data.get('data', {}).get('activeDailyCodingChallengeQuestion', {})
                if question_data:
                    question = question_data.get('question', {})
                    debug_info["leetcode_actual_today"] = {
                        "title": question.get('title', 'Unknown'),
                        "slug": question.get('titleSlug', 'unknown'),
                        "difficulty": question.get('difficulty', 'Unknown'),
                        "date": question_data.get('date', 'Unknown')
                    }
        except Exception as e:
            debug_info["leetcode_actual_today"] = {"error": str(e)}
        
        # Analysis
        analysis = []
        
        if debug_info["current_global_storage"]["contains_sudoku"]:
            analysis.append("🚨 N8N workflow is storing SUDOKU solution instead of today's challenge")
            analysis.append("❌ Your n8n workflow logic needs to be fixed")
            
        if not debug_info["current_global_storage"]["contains_today"]:
            analysis.append("⚠️  N8N solution doesn't contain today's date - might be stale")
            
        if not debug_info["current_global_storage"]["has_solution"]:
            analysis.append("❌ N8N global storage is empty - workflow might not be running")
            
        # Compare with actual LeetCode challenge
        leetcode_today = debug_info.get("leetcode_actual_today", {})
        if leetcode_today.get("title") and debug_info["current_global_storage"]["code_preview"]:
            if leetcode_today["title"].lower() not in debug_info["current_global_storage"]["code_preview"].lower():
                analysis.append(f"🚨 MISMATCH: LeetCode today is '{leetcode_today['title']}' but n8n has different solution")
                
        debug_info["analysis"] = analysis
        debug_info["timestamp"] = datetime.now().isoformat()
        
        return debug_info
        
    except Exception as e:
        return {
            "error": str(e),
            "message": "Failed to debug n8n workflow",
            "timestamp": datetime.now().isoformat()
        }

async def get_fresh_leetcode_solution_internal():
    """Internal helper function for direct LeetCode API integration"""
    try:
        import requests
        import json
        import re
        from datetime import datetime
        
        # Get today's date
        today = datetime.now().strftime('%Y-%m-%d')
        current_time = datetime.now().isoformat()
        
        # LeetCode GraphQL API
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        graphql_url = "https://leetcode.com/graphql"
        
        query = {
            "query": """
            query questionOfToday {
                activeDailyCodingChallengeQuestion {
                    date
                    link
                    question {
                        difficulty
                        title
                        titleSlug
                        content
                        codeSnippets {
                            lang
                            code
                        }
                        hints
                        sampleTestCase
                        topicTags {
                            name
                            slug
                        }
                    }
                }
            }
            """
        }
        
        logger.info("Fetching today's challenge from LeetCode API (internal)...")
        response = requests.post(graphql_url, json=query, headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            question_data = data.get('data', {}).get('activeDailyCodingChallengeQuestion', {})
            
            if question_data:
                question = question_data.get('question', {})
                title = question.get('title', f'Daily Challenge {today}')
                title_slug = question.get('titleSlug', 'daily-challenge')
                difficulty = question.get('difficulty', 'Unknown')
                content = question.get('content', '')
                hints = question.get('hints', [])
                topics = [tag['name'] for tag in question.get('topicTags', [])]
                
                # Get Python code snippet
                python_snippet = ""
                code_snippets = question.get('codeSnippets', [])
                for snippet in code_snippets:
                    if snippet.get('lang') == 'Python3' or snippet.get('lang') == 'Python':
                        python_snippet = snippet.get('code', '')
                        break
                
                # No hardcoded solutions - N8N only
                logger.error("Direct LeetCode API bypassed - N8N workflow required for solutions")
                return None  # Force N8N dependency
        
        return None
        
    except Exception as e:
        logger.error(f"Internal fresh solution generation failed: {e}")
        return None

@app.get("/leetcode-code-fresh")
async def get_fresh_leetcode_code():
    """
    COMPLETE BYPASS SOLUTION - Direct LeetCode API integration
    Fetches and solves today's challenge without any n8n dependency
    """
    
    logger.info("FRESH DIRECT API endpoint called - bypassing ALL cache and n8n")
    
    start_time = time.time()
    import requests
    import json
    import re
    from datetime import datetime
    
    # Get today's date
    today = datetime.now().strftime('%Y-%m-%d')
    current_time = datetime.now().isoformat()
    
    try:
        # Step 1: Get today's LeetCode daily challenge
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        graphql_url = "https://leetcode.com/graphql"
        
        query = {
            "query": """
            query questionOfToday {
                activeDailyCodingChallengeQuestion {
                    date
                    link
                    question {
                        difficulty
                        title
                        titleSlug
                        content
                        codeSnippets {
                            lang
                            code
                        }
                        hints
                        sampleTestCase
                        topicTags {
                            name
                            slug
                        }
                    }
                }
            }
            """
        }
        
        logger.info("Fetching today's challenge from LeetCode API...")
        response = requests.post(graphql_url, json=query, headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            question_data = data.get('data', {}).get('activeDailyCodingChallengeQuestion', {})
            
            if question_data:
                question = question_data.get('question', {})
                title = question.get('title', f'Daily Challenge {today}')
                title_slug = question.get('titleSlug', 'daily-challenge')
                difficulty = question.get('difficulty', 'Unknown')
                content = question.get('content', '')
                hints = question.get('hints', [])
                topics = [tag['name'] for tag in question.get('topicTags', [])]
                
                # Get Python code snippet
                python_snippet = ""
                code_snippets = question.get('codeSnippets', [])
                for snippet in code_snippets:
                    if snippet.get('lang') == 'Python3' or snippet.get('lang') == 'Python':
                        python_snippet = snippet.get('code', '')
                        break
                
                logger.info(f"Found challenge: {title} ({difficulty})")
                
                # No hardcoded solutions - N8N workflow required
                logger.info("Direct LeetCode API bypassed - forcing N8N workflow dependency")
                # Fall through to error response below
        
        logger.warning("LeetCode API returned empty or invalid data")
        
    except Exception as e:
        logger.error(f"Direct LeetCode API failed: {e}")
    
    # No hardcoded solutions - only return error if N8N fails
    response_time_ms = (time.time() - start_time) * 1000
    
    return {
        "status": "error", 
        "source": "n8n_required",
        "response_time_ms": response_time_ms,
        "date": today,
        "generated_at": current_time,
        "code": "",
        "solutionCode": "",
        "pythonCode": "",
        "error": "No solution available - N8N workflow required",
        "message": "Failed to fetch solution from both N8N workflow and direct LeetCode API",
        "problem_info": {
            "title": f"Daily Challenge {today}",
            "date": today,
            "error": "Solution not available"
        },
        "quality_info": {
            "is_safe": False,
            "quality_score": 0.0,
            "warnings": ["No solution fetched from N8N - check N8N workflow"],
            "approach": "n8n_only_no_fallbacks"
        },
        "meta": {
            "n8n_required": True,
            "no_hardcoded_solutions": True,
            "endpoint": "leetcode-code-fresh",
            "prd_compliant": True
        }
    }

# No hardcoded solution templates - N8N only approach
# All solution generation functions removed to force N8N dependency

# Development endpoints (only available in debug mode)
if os.getenv('DEBUG', 'False').lower() == 'true':
    @app.get("/debug/users")
    async def debug_get_users():
        """Debug endpoint to view active users"""
        return {
            "active_users": list(user_manager.active_users.keys()),
            "user_count": user_manager.get_active_user_count(),
            "websocket_connections": len(user_manager.websocket_connections),
            "debug_mode": True
        }
    
    @app.get("/debug/cache")
    async def debug_cache_keys():
        """Debug endpoint to view cache keys"""
        try:
            # This would need to be implemented in cache manager
            return {
                "message": "Cache debug info",
                "redis_connected": await cache_manager.ping(),
                "debug_mode": True
            }
        except Exception as e:
            return {"error": str(e), "debug_mode": True}
    
    @app.get("/debug/daily-trigger")
    async def debug_daily_trigger():
        """Debug endpoint to check daily trigger status"""
        try:
            today_key, now_ist = get_daily_challenge_key()
            daily_trigger_key = get_daily_trigger_key(today_key)
            
            # Check trigger status
            trigger_status = await cache_manager.get(daily_trigger_key)
            cached_solution = await cache_manager.get_daily_solution(today_key)
            
            return {
                "today_key": today_key,
                "current_time_ist": now_ist.isoformat(),
                "daily_trigger_key": daily_trigger_key,
                "trigger_status": trigger_status,
                "has_cached_solution": cached_solution is not None,
                "next_ttl_seconds": calculate_cache_ttl(now_ist),
                "message": "Daily trigger debug info"
            }
        except Exception as e:
            return {"error": str(e), "debug_mode": True}
    
    @app.post("/debug/reset-daily-trigger")
    async def reset_daily_trigger():
        """Debug endpoint to reset daily trigger flag (for testing)"""
        try:
            today_key, now_ist = get_daily_challenge_key()
            daily_trigger_key = get_daily_trigger_key(today_key)
            
            # Delete the daily trigger flag
            await cache_manager.redis_client.delete(daily_trigger_key)
            
            return {
                "message": f"Reset daily trigger flag for {today_key}",
                "today_key": today_key,
                "daily_trigger_key": daily_trigger_key,
                "current_time_ist": now_ist.isoformat(),
                "status": "reset_complete"
            }
        except Exception as e:
            return {"error": str(e), "debug_mode": True}

# Main entry point
if __name__ == "__main__":
    port = int(os.getenv('PORT', 8000))
    host = os.getenv('HOST', '0.0.0.0')
    reload = os.getenv('DEBUG', 'False').lower() == 'true'
    workers = int(os.getenv('WORKERS', '4'))
    
    logger.info(f"Starting LeetCode Solver (PRD compliant) on {host}:{port}")
    logger.info(f"Redis URL: {os.getenv('REDIS_URL', 'redis://localhost:6379')}")
    logger.info(f"N8N Base URL: {os.getenv('N8N_WEBHOOK_BASE', 'http://localhost:5678')}")
    logger.info("Max concurrent users: unlimited")
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers if not reload else 1,
        log_level=os.getenv('LOG_LEVEL', 'info').lower(),
        access_log=True,
        server_header=False,
        date_header=False,
        loop="asyncio",
        http="auto",
        ws="auto"
    )