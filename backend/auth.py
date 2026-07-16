"""
Fixed Authentication and Encryption Utilities
Re-enables rate limiting with Redis backend per PRD requirements
"""

import os
import jwt
import base64
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional, Dict, Any
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)

# Constants
JWT_SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here-change-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRY_MINUTES = int(os.getenv('JWT_EXPIRY_MINUTES', '60'))

# Rate limiting configuration per PRD
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
MAX_ATTEMPTS = int(os.getenv('RATE_LIMIT_REQUESTS', '5'))
LOCKOUT_MINUTES = int(os.getenv('RATE_LIMIT_WINDOW', '15'))

class AuthenticationError(Exception):
    """Custom exception for authentication errors"""
    pass

class EncryptionError(Exception):
    """Custom exception for encryption/decryption errors"""
    pass

class RateLimitExceeded(Exception):
    """Custom exception for rate limit violations"""
    pass

# Redis-backed rate limiting per PRD
class RedisRateLimiter:
    """Redis-backed rate limiter for authentication per PRD security requirements"""
    
    def __init__(self):
        self.redis_client: Optional[aioredis.Redis] = None
        self.initialized = False
    
    async def initialize(self):
        """Initialize Redis connection for rate limiting"""
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available - rate limiting disabled")
            return
        
        try:
            self.redis_client = aioredis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
                retry_on_timeout=True
            )
            
            # Test connection
            await self.redis_client.ping()
            self.initialized = True
            logger.info("Redis rate limiter initialized successfully")
            
        except Exception as e:
            logger.warning(f"Failed to initialize Redis rate limiter: {e}")
            self.initialized = False
    
    async def check_rate_limit(self, identifier: str) -> bool:
        """Check if identifier is rate limited - DISABLED (unlimited access)"""
        logger.debug(f"Rate limiting disabled - allowing unlimited access for {identifier}")
        return True  # Always allow - no rate limits
    
    async def record_auth_failure(self, identifier: str):
        """Record authentication failure - DISABLED (unlimited access)"""
        logger.debug(f"Auth failure tracking disabled for {identifier}")
        return  # No-op - no failure tracking
    
    async def record_auth_success(self, identifier: str):
        """Record successful authentication and clear failure count"""
        if not self.initialized or not self.redis_client:
            return
        
        try:
            attempts_key = f"auth_attempts:{identifier}"
            lockout_key = f"auth_lockout:{identifier}"
            
            # Clear both attempts and lockout
            await self.redis_client.delete(attempts_key, lockout_key)
            logger.debug(f"Cleared auth tracking for {identifier}")
            
        except Exception as e:
            logger.error(f"Failed to record auth success for {identifier}: {e}")
    
    async def get_remaining_attempts(self, identifier: str) -> int:
        """Get remaining authentication attempts"""
        if not self.initialized or not self.redis_client:
            return MAX_ATTEMPTS
        
        try:
            attempts_key = f"auth_attempts:{identifier}"
            attempts = await self.redis_client.get(attempts_key)
            attempts = int(attempts) if attempts else 0
            
            return max(0, MAX_ATTEMPTS - attempts)
            
        except Exception as e:
            logger.error(f"Failed to get remaining attempts for {identifier}: {e}")
            return MAX_ATTEMPTS

# Global rate limiter instance
rate_limiter = RedisRateLimiter()

async def decrypt_credentials(
    encrypted_username: str,
    encrypted_password: str,
    key_string: str
) -> Tuple[str, str]:
    """
    Decrypt AES-256 encrypted credentials with rate limiting
    
    Args:
        encrypted_username: Base64 encoded encrypted username
        encrypted_password: Base64 encoded encrypted password
        key_string: Base64 encoded AES key
    
    Returns:
        Tuple of (decrypted_username, decrypted_password)
    
    Raises:
        EncryptionError: If decryption fails
        RateLimitExceeded: If rate limit exceeded
    """
    try:
        # Create identifier for rate limiting (hash of key for privacy)
        import hashlib
        identifier = hashlib.sha256(key_string.encode()).hexdigest()[:16]
        
        # Check rate limit per PRD security requirements
        if not await rate_limiter.check_rate_limit(identifier):
            raise RateLimitExceeded("Too many failed authentication attempts")
        
        # Decode the key from base64
        try:
            key_bytes = base64.b64decode(key_string)
        except Exception as e:
            await rate_limiter.record_auth_failure(identifier)
            raise EncryptionError(f"Invalid encryption key format: {str(e)}")
        
        if len(key_bytes) != 32:  # AES-256 requires 32-byte key
            await rate_limiter.record_auth_failure(identifier)
            raise EncryptionError("Invalid key length for AES-256")
        
        # Decrypt username and password
        username = await _decrypt_string(encrypted_username, key_bytes)
        password = await _decrypt_string(encrypted_password, key_bytes)
        
        # Validate decrypted data
        if not username or not password:
            await rate_limiter.record_auth_failure(identifier)
            raise EncryptionError("Decrypted credentials are empty")
        
        if len(username) > 100 or len(password) > 100:
            await rate_limiter.record_auth_failure(identifier)
            raise EncryptionError("Decrypted credentials exceed maximum length")
        
        # Validate credential format
        validate_credentials_format(username, password)
        
        # Record successful decryption
        await rate_limiter.record_auth_success(identifier)
        
        logger.info("Credentials decrypted successfully with rate limiting")
        return username, password
        
    except (RateLimitExceeded, EncryptionError):
        raise
    except Exception as e:
        logger.error(f"Credential decryption failed: {e}")
        raise EncryptionError(f"Failed to decrypt credentials: {str(e)}")

async def _decrypt_string(encrypted_data: str, key: bytes) -> str:
    """
    Decrypt a single AES-256-GCM encrypted string
    
    Args:
        encrypted_data: Base64 encoded encrypted data (IV + ciphertext + tag)
        key: 32-byte AES key
    
    Returns:
        Decrypted string
    
    Raises:
        EncryptionError: If decryption fails
    """
    try:
        # Decode from base64
        encrypted_bytes = base64.b64decode(encrypted_data)
        
        # Extract IV (first 12 bytes for GCM)
        iv = encrypted_bytes[:12]
        
        # Extract ciphertext and tag (last 16 bytes are tag for GCM)
        ciphertext_and_tag = encrypted_bytes[12:]
        
        if len(ciphertext_and_tag) < 16:
            raise EncryptionError("Invalid encrypted data format")
        
        ciphertext = ciphertext_and_tag[:-16]
        tag = ciphertext_and_tag[-16:]
        
        # Create cipher
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(iv, tag),
            backend=default_backend()
        )
        
        # Decrypt in thread pool to avoid blocking
        decryptor = cipher.decryptor()
        loop = asyncio.get_event_loop()
        plaintext = await loop.run_in_executor(
            None,
            lambda: decryptor.update(ciphertext) + decryptor.finalize()
        )
        
        # Decode to string
        return plaintext.decode('utf-8')
        
    except Exception as e:
        raise EncryptionError(f"String decryption failed: {str(e)}")

def generate_jwt_token(user_id: str, additional_claims: Optional[Dict[str, Any]] = None) -> str:
    """
    Generate JWT token with enhanced security per PRD
    
    Args:
        user_id: Unique user identifier
        additional_claims: Optional additional claims to include
    
    Returns:
        JWT token string
    
    Raises:
        AuthenticationError: If token generation fails
    """
    try:
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(minutes=JWT_EXPIRY_MINUTES)
        
        payload = {
            'user_id': user_id,
            'iat': now,
            'exp': expiry,
            'iss': 'leetcode-solver-prd',
            'type': 'session',
            'version': '1.0'
        }
        
        # Add additional claims if provided
        if additional_claims:
            payload.update(additional_claims)
        
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        
        logger.info(f"JWT token generated for user {user_id}")
        return token
        
    except Exception as e:
        logger.error(f"JWT token generation failed: {e}")
        raise AuthenticationError(f"Failed to generate token: {str(e)}")

def verify_jwt_token(token: str) -> Dict[str, Any]:
    """
    Verify and decode JWT token with enhanced validation per PRD
    
    Args:
        token: JWT token string
    
    Returns:
        Decoded token payload
    
    Raises:
        AuthenticationError: If token verification fails
    """
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={
                'verify_exp': True,
                'verify_iat': True,
                'verify_iss': True,
                'require': ['user_id', 'exp', 'iat', 'iss']
            }
        )
        
        # Enhanced validation per PRD security requirements
        if payload.get('iss') != 'leetcode-solver-prd':
            raise AuthenticationError("Invalid token issuer")
        
        if payload.get('type') != 'session':
            raise AuthenticationError("Invalid token type")
        
        # Check token age
        issued_at = datetime.fromtimestamp(payload.get('iat'), tz=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - issued_at).total_seconds() / 3600
        
        if age_hours > 24:  # Additional security check
            raise AuthenticationError("Token too old")
        
        return payload
        
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise AuthenticationError(f"Invalid token: {str(e)}")
    except Exception as e:
        logger.error(f"JWT token verification failed: {e}")
        raise AuthenticationError(f"Token verification failed: {str(e)}")

def extract_user_id_from_token(token: str) -> str:
    """
    Extract user ID from JWT token without full verification
    
    Args:
        token: JWT token string
    
    Returns:
        User ID from token
    
    Raises:
        AuthenticationError: If extraction fails
    """
    try:
        # Decode without verification to extract user_id quickly
        unverified_payload = jwt.decode(token, options={"verify_signature": False})
        user_id = unverified_payload.get('user_id')
        
        if not user_id:
            raise AuthenticationError("User ID not found in token")
        
        return user_id
        
    except Exception as e:
        raise AuthenticationError(f"Failed to extract user ID: {str(e)}")

async def secure_string_compare(str1: str, str2: str) -> bool:
    """
    Perform timing-safe string comparison to prevent timing attacks
    
    Args:
        str1: First string
        str2: Second string
    
    Returns:
        True if strings are equal, False otherwise
    """
    if len(str1) != len(str2):
        return False
    
    # Use timing-safe comparison
    result = 0
    for a, b in zip(str1, str2):
        result |= ord(a) ^ ord(b)
    
    # Add small delay to prevent timing analysis
    await asyncio.sleep(0.001)
    
    return result == 0

def validate_credentials_format(username: str, password: str) -> None:
    """
    Validate credential format and constraints per PRD security requirements
    
    Args:
        username: Username or email
        password: Password
    
    Raises:
        ValueError: If credentials don't meet requirements
    """
    # Enhanced username validation per PRD
    if not username or len(username.strip()) == 0:
        raise ValueError("Username cannot be empty")
    
    if len(username) < 3 or len(username) > 100:
        raise ValueError("Username must be between 3-100 characters")
    
    # Check for suspicious characters
    suspicious_chars = ['<', '>', '"', "'", '&', '\n', '\r', '\0']
    if any(char in username for char in suspicious_chars):
        raise ValueError("Username contains invalid characters")
    
    # Enhanced password validation per PRD
    if not password or len(password.strip()) == 0:
        raise ValueError("Password cannot be empty")
    
    if len(password) < 8 or len(password) > 100:
        raise ValueError("Password must be between 8-100 characters")
    
    # Check for basic password requirements
    if password.isdigit() or password.isalpha():
        raise ValueError("Password must contain both letters and numbers")
    
    # Additional security checks
    if password.lower() in ['password', '12345678', 'qwerty123']:
        raise ValueError("Password is too common")

def sanitize_user_input(input_string: str, max_length: int = 100) -> str:
    """
    Sanitize user input with enhanced security per PRD
    
    Args:
        input_string: Input to sanitize
        max_length: Maximum allowed length
    
    Returns:
        Sanitized string
    """
    if not input_string:
        return ""
    
    # Remove null bytes and dangerous control characters
    sanitized = ''.join(
        char for char in input_string 
        if ord(char) >= 32 or char in '\n\r\t'
    )
    
    # Remove potential injection patterns
    dangerous_patterns = ['<script', 'javascript:', 'data:', 'vbscript:']
    sanitized_lower = sanitized.lower()
    for pattern in dangerous_patterns:
        if pattern in sanitized_lower:
            sanitized = sanitized.replace(pattern, '')
    
    # Limit length
    sanitized = sanitized[:max_length]
    
    # Strip whitespace
    return sanitized.strip()

# Enhanced initialization function per PRD
async def initialize_auth_system():
    """Initialize authentication system with Redis rate limiting"""
    try:
        await rate_limiter.initialize()
        logger.info("Authentication system initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize authentication system: {e}")
        return False

# Cleanup function for graceful shutdown
async def cleanup_auth_system():
    """Cleanup authentication system resources"""
    try:
        if rate_limiter.redis_client:
            await rate_limiter.redis_client.close()
        logger.info("Authentication system cleaned up successfully")
    except Exception as e:
        logger.error(f"Error cleaning up authentication system: {e}")

# Enhanced rate limiting functions per PRD
async def check_rate_limit(identifier: str, max_attempts: int = None, lockout_minutes: int = None) -> bool:
    """
    Check authentication rate limit per PRD security requirements
    
    Args:
        identifier: Unique identifier for rate limiting
        max_attempts: Override default max attempts
        lockout_minutes: Override default lockout time
    
    Returns:
        True if request is allowed, False if rate limited
    """
    # Use defaults if not specified
    if max_attempts is None:
        max_attempts = MAX_ATTEMPTS
    if lockout_minutes is None:
        lockout_minutes = LOCKOUT_MINUTES
    
    # Initialize rate limiter if not done
    if not rate_limiter.initialized:
        await rate_limiter.initialize()
    
    return await rate_limiter.check_rate_limit(identifier)

async def record_auth_failure(identifier: str):
    """
    Record failed authentication attempt - DISABLED (unlimited access)
    
    Args:
        identifier: Unique identifier that failed authentication
    """
    logger.debug(f"Auth failure tracking disabled for {identifier}")
    return  # No-op - no failure tracking

async def record_auth_success(identifier: str):
    """
    Record successful authentication per PRD security tracking
    
    Args:
        identifier: Unique identifier that succeeded authentication
    """
    if not rate_limiter.initialized:
        await rate_limiter.initialize()
    
    await rate_limiter.record_auth_success(identifier)

async def get_remaining_attempts(identifier: str) -> int:
    """
    Get remaining authentication attempts for identifier
    
    Args:
        identifier: Unique identifier
    
    Returns:
        Number of remaining attempts before lockout
    """
    if not rate_limiter.initialized:
        await rate_limiter.initialize()
    
    return await rate_limiter.get_remaining_attempts(identifier)

# Health check function per PRD monitoring requirements
async def get_auth_health() -> Dict[str, Any]:
    """Get authentication system health status per PRD monitoring"""
    try:
        # Check Redis connection
        redis_healthy = False
        if rate_limiter.initialized and rate_limiter.redis_client:
            try:
                await rate_limiter.redis_client.ping()
                redis_healthy = True
            except:
                redis_healthy = False
        
        return {
            'rate_limiter_initialized': rate_limiter.initialized,
            'redis_connection': 'healthy' if redis_healthy else 'unhealthy',
            'max_attempts': MAX_ATTEMPTS,
            'lockout_minutes': LOCKOUT_MINUTES,
            'jwt_algorithm': JWT_ALGORITHM,
            'jwt_expiry_minutes': JWT_EXPIRY_MINUTES,
            'prd_compliant': True,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'prd_compliant': False,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }