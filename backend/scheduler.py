"""
APScheduler Configuration for Daily Cache Refresh
Manages automatic daily refresh of LeetCode solutions at 6AM IST.
"""

import os
import asyncio
import logging
import time  # For time.time()
from datetime import datetime, timezone, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
import pytz

from utils.n8n_enhanced import get_code_from_n8n_simple, get_code_from_n8n_sync_wrapper

logger = logging.getLogger(__name__)

# Configuration
CACHE_REFRESH_HOUR = int(os.getenv('CACHE_REFRESH_HOUR', '6'))  # 6 AM
CACHE_REFRESH_MINUTE = int(os.getenv('CACHE_REFRESH_MINUTE', '0'))  # 0 minutes
IST_TIMEZONE = pytz.timezone('Asia/Kolkata')

class SchedulerError(Exception):
    """Custom exception for scheduler-related errors"""
    pass

def setup_scheduler(cache_manager) -> AsyncIOScheduler:
    """
    Setup and configure the APScheduler for daily cache refresh.
    
    Args:
        cache_manager: CacheManager instance
    
    Returns:
        Configured AsyncIOScheduler
    """
    try:
        # Configure job stores
        jobstores = {
            'default': MemoryJobStore()
        }
        
        # Configure executors
        executors = {
            'default': AsyncIOExecutor()
        }
        
        # Job defaults
        job_defaults = {
            'coalesce': False,  # Run all missed jobs
            'max_instances': 1,  # Only one instance at a time
            'misfire_grace_time': 3600  # 1 hour grace period for missed jobs
        }
        
        # Create scheduler
        scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=IST_TIMEZONE
        )
        
        # Add the daily cache refresh job
        scheduler.add_job(
            func=daily_cache_refresh,
            trigger=CronTrigger(
                hour=CACHE_REFRESH_HOUR,
                minute=CACHE_REFRESH_MINUTE,
                timezone=IST_TIMEZONE
            ),
            args=[cache_manager],
            id='daily_cache_refresh',
            name='Daily LeetCode Solution Cache Refresh',
            replace_existing=True
        )
        
        # Add cleanup job (runs every hour)
        scheduler.add_job(
            func=cleanup_expired_cache,
            trigger=CronTrigger(minute=0),  # Every hour at minute 0
            args=[cache_manager],
            id='cache_cleanup',
            name='Cache Cleanup',
            replace_existing=True
        )
        
        # Add health check job (runs every 30 minutes)
        scheduler.add_job(
            func=health_check_job,
            trigger=CronTrigger(minute='*/30'),  # Every 30 minutes
            args=[cache_manager],
            id='health_check',
            name='System Health Check',
            replace_existing=True
        )
        
        logger.info(
            f"Scheduler configured successfully. "
            f"Daily refresh at {CACHE_REFRESH_HOUR:02d}:{CACHE_REFRESH_MINUTE:02d} IST"
        )
        
        return scheduler
        
    except Exception as e:
        logger.error(f"Failed to setup scheduler: {e}")
        raise SchedulerError(f"Scheduler setup failed: {str(e)}")

def start_scheduler(scheduler: AsyncIOScheduler) -> None:
    """
    Start the scheduler.
    
    Args:
        scheduler: AsyncIOScheduler instance
    """
    try:
        scheduler.start()
        logger.info("Scheduler started successfully")
        
        # Log next job executions
        jobs = scheduler.get_jobs()
        for job in jobs:
            next_run = job.next_run_time
            if next_run:
                logger.info(f"Job '{job.name}' next run: {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        raise SchedulerError(f"Scheduler start failed: {str(e)}")

def stop_scheduler(scheduler: AsyncIOScheduler) -> None:
    """
    Stop the scheduler gracefully.
    
    Args:
        scheduler: AsyncIOScheduler instance
    """
    try:
        if scheduler.running:
            scheduler.shutdown(wait=True)
            logger.info("Scheduler stopped successfully")
        else:
            logger.info("Scheduler was not running")
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")

async def daily_cache_refresh(cache_manager) -> None:
    """
    Daily 6 AM job to refresh the LeetCode solution cache for new 24-hour cycle.
    
    Args:
        cache_manager: CacheManager instance  
    """
    try:
        logger.info("🕰️ Daily 6 AM cache refresh - ALWAYS refresh solution for new 24-hour cycle")
        
        # Get current date
        current_date = datetime.now(IST_TIMEZONE).strftime('%Y-%m-%d')
        
        # Get the code cache manager from app state
        from code_cache import get_code_cache
        try:
            code_cache = get_code_cache()
            
            # Force refresh by clearing cache and fetching fresh solution
            logger.info("🔄 Force refreshing cache for new 24-hour cycle...")
            fresh_solution = await code_cache.force_refresh()
            
            if fresh_solution:
                cache_age = (time.time() - fresh_solution.cached_at) / 60  # minutes
                logger.info(f"✅ Daily refresh successful! Fresh solution cached (created {cache_age:.1f}min ago)")
                logger.info(f"🔒 Solution will be used for next 24 hours until tomorrow 6 AM")
                logger.info(f"📊 Safety: {fresh_solution.is_safe}, Quality: {fresh_solution.quality_score:.2f}")
                if fresh_solution.warnings:
                    logger.info(f"⚠️  Warnings: {'; '.join(fresh_solution.warnings[:2])}")
            else:
                logger.error("❌ Daily refresh failed - no solution received from N8N")
                
        except Exception as cache_error:
            logger.error(f"❌ Failed to access code cache manager: {cache_error}")
            # Fallback to direct cache approach if needed
            logger.info("🔄 Falling back to direct cache refresh...")
            
            # Clear old cache  
            await cache_manager.delete('daily_challenge_solution')
            logger.info("✅ Old cache cleared - next user request will trigger fresh N8N call")
        
        logger.info("🎯 Daily cache refresh job completed")
        
    except Exception as e:
        logger.error(f"Daily cache refresh failed: {e}", exc_info=True)
        
        # Try to handle critical failures gracefully
        try:
            await handle_refresh_failure(cache_manager, current_date)
        except Exception as fallback_error:
            logger.error(f"Fallback handling also failed: {fallback_error}")

async def handle_refresh_failure(cache_manager, date: str) -> None:
    """
    Handle failures in daily cache refresh by implementing fallback strategies.
    
    Args:
        cache_manager: CacheManager instance
        date: Date for which refresh failed
    """
    try:
        logger.info("Implementing fallback strategies for cache refresh failure")
        
        # No fallback solutions - N8N only approach
        logger.error(f"Daily refresh failed for {date} - no fallback solutions will be cached")
        logger.error("N8N workflow must be fixed to provide solutions")
        # Do not cache any fallback or placeholder solutions
        
    except Exception as e:
        logger.error(f"Fallback handling failed: {e}")

async def cleanup_expired_cache(cache_manager) -> None:
    """
    Cleanup job to remove expired cache entries and optimize memory usage.
    
    Args:
        cache_manager: CacheManager instance
    """
    try:
        logger.debug("Starting cache cleanup job")
        
        # Get memory usage before cleanup
        memory_before = await cache_manager.get_memory_usage()
        
        # Clean up old daily solutions (keep last 7 days)
        cutoff_date = datetime.now(IST_TIMEZONE) - timedelta(days=7)
        
        for i in range(8, 15):  # Clean up solutions 8-14 days old
            old_date = (cutoff_date - timedelta(days=i)).strftime('%Y-%m-%d')
            await cache_manager.delete(f"daily_solution:{old_date}", namespace='leetcode')
        
        # Clean up expired user sessions
        # This would require implementing a scan for expired sessions
        # For now, we'll rely on Redis TTL to handle expiration
        
        # Get memory usage after cleanup
        memory_after = await cache_manager.get_memory_usage()
        
        # Log cleanup results
        memory_freed = memory_before.get('used_memory', 0) - memory_after.get('used_memory', 0)
        if memory_freed > 0:
            logger.debug(f"Cache cleanup completed, freed {memory_freed} bytes")
        else:
            logger.debug("Cache cleanup completed")
        
    except Exception as e:
        logger.error(f"Cache cleanup failed: {e}")

async def health_check_job(cache_manager) -> None:
    """
    Health check job to monitor system status.
    
    Args:
        cache_manager: CacheManager instance
    """
    try:
        logger.debug("Running scheduled health check")
        
        # Check Redis connection
        redis_healthy = await cache_manager.ping()
        
        # Check cache functionality
        test_key = f"health_check_{int(datetime.now().timestamp())}"
        cache_healthy = False
        
        if redis_healthy:
            await cache_manager.set(test_key, "test", ttl=10)
            cached_value = await cache_manager.get(test_key)
            cache_healthy = cached_value == "test"
            await cache_manager.delete(test_key)
        
        # Check today's solution availability
        today = datetime.now(IST_TIMEZONE).strftime('%Y-%m-%d')
        daily_solution = await cache_manager.get_daily_solution(today)
        solution_available = daily_solution is not None
        
        # Log health status
        health_status = {
            'redis': 'healthy' if redis_healthy else 'unhealthy',
            'cache': 'healthy' if cache_healthy else 'unhealthy',
            'daily_solution': 'available' if solution_available else 'missing'
        }
        
        overall_healthy = redis_healthy and cache_healthy
        
        if overall_healthy:
            logger.debug(f"Health check passed: {health_status}")
        else:
            logger.warning(f"Health check issues detected: {health_status}")
        
        # Store health status in cache for monitoring
        await cache_manager.set(
            'last_health_check',
            {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'status': health_status,
                'overall_healthy': overall_healthy
            },
            ttl=7200,  # 2 hours
            namespace='system'
        )
        
    except Exception as e:
        logger.error(f"Health check job failed: {e}")

def get_scheduler_status(scheduler: AsyncIOScheduler) -> dict:
    """
    Get detailed scheduler status information.
    
    Args:
        scheduler: AsyncIOScheduler instance
    
    Returns:
        Dictionary with scheduler status details
    """
    try:
        if not scheduler:
            return {'status': 'not_configured'}
        
        jobs = scheduler.get_jobs()
        job_info = []
        
        for job in jobs:
            job_data = {
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger),
                'pending': job.pending
            }
            job_info.append(job_data)
        
        return {
            'status': 'running' if scheduler.running else 'stopped',
            'jobs': job_info,
            'job_count': len(jobs)
        }
        
    except Exception as e:
        logger.error(f"Failed to get scheduler status: {e}")
        return {'status': 'error', 'error': str(e)}

async def manually_trigger_refresh(cache_manager, date: Optional[str] = None) -> dict:
    """
    Manually trigger cache refresh for testing or recovery purposes.
    
    Args:
        cache_manager: CacheManager instance
        date: Specific date to refresh (None for today)
    
    Returns:
        Dictionary with operation results
    """
    try:
        if not date:
            date = datetime.now(IST_TIMEZONE).strftime('%Y-%m-%d')
        
        logger.info(f"Manually triggering cache refresh for {date}")
        
        # Run the refresh job
        await daily_cache_refresh(cache_manager)
        
        # Check if solution was cached
        solution = await cache_manager.get_daily_solution(date)
        
        return {
            'success': solution is not None,
            'date': date,
            'solution_cached': solution is not None,
            'message': f"Manual refresh completed for {date}"
        }
        
    except Exception as e:
        logger.error(f"Manual cache refresh failed: {e}")
        return {
            'success': False,
            'date': date,
            'error': str(e),
            'message': f"Manual refresh failed for {date}"
        }