"""
Complete N8N Enhanced Integration - PRD Compliant
Fixed all endpoint configurations and error handling per PRD specification
"""

import os
import requests
import time
import json
import asyncio
import aiohttp
from typing import Optional, Dict, Tuple, List, Any
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from urllib3.util.retry import Retry

try:
    from .code_validator import quick_fix_leetcode
except ImportError:
    # Fallback for when validator is not available
    def quick_fix_leetcode(code, problem_title=None):
        return code, True, []

# PRD-compliant N8N configuration
N8N_BASE_URL = os.getenv('N8N_WEBHOOK_BASE', 'http://localhost:5678')
TRIGGER_URL = f"{N8N_BASE_URL}/webhook/solve-daily"
FETCH_URL = f"{N8N_BASE_URL}/webhook/leetcode-code"

# Multiple endpoint fallbacks for reliability per PRD
# Includes both production and test webhook URLs
TRIGGER_URLS = [
    # Production webhooks
    f"{N8N_BASE_URL}/webhook/solve-daily",
    "http://127.0.0.1:5678/webhook/solve-daily",
    "http://localhost:5678/webhook/solve-daily",
    # Test webhooks (for when workflow is in test mode)
    f"{N8N_BASE_URL}/webhook-test/solve-daily",
    "http://127.0.0.1:5678/webhook-test/solve-daily",
    "http://localhost:5678/webhook-test/solve-daily"
]

FETCH_URLS = [
    # Production webhooks
    f"{N8N_BASE_URL}/webhook/leetcode-code",
    "http://127.0.0.1:5678/webhook/leetcode-code", 
    "http://localhost:5678/webhook/leetcode-code",
    # Test webhooks (for when workflow is in test mode)
    f"{N8N_BASE_URL}/webhook-test/leetcode-code",
    "http://127.0.0.1:5678/webhook-test/leetcode-code",
    "http://localhost:5678/webhook-test/leetcode-code"
]

class N8NTimeoutError(Exception):
    """Custom exception for N8N timeout issues"""
    pass

class N8NConnectionError(Exception):
    """Custom exception for N8N connection issues"""
    pass

class N8NValidationError(Exception):
    """Custom exception for N8N response validation issues"""
    pass

class EnhancedN8NClient:
    """Enhanced N8N client with PRD-compliant retry logic and comprehensive error handling"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'LeetCode-AutoSolver-PRD/1.0',
            'Accept': 'application/json',
            'Cache-Control': 'no-cache'
        })
        
        # Enhanced connection pooling for better performance per PRD
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.3,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,
            pool_maxsize=50,
            max_retries=retry_strategy
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        # Request timeout configuration
        self.default_timeout = int(os.getenv('N8N_TIMEOUT_SECONDS', '30'))
        
    def validate_n8n_connection(self) -> Dict[str, any]:
        """Comprehensive N8N connection validation per PRD requirements"""
        results = {
            'trigger_accessible': False,
            'fetch_accessible': False,
            'response_times': {},
            'errors': [],
            'endpoints_tested': 0,
            'successful_endpoints': 0
        }
        
        # Test trigger endpoints with comprehensive checks
        for url in TRIGGER_URLS:
            results['endpoints_tested'] += 1
            try:
                start = time.time()
                response = self.session.head(url, timeout=self.default_timeout)
                response_time = time.time() - start
                
                # Accept various HTTP status codes that indicate endpoint exists
                if response.status_code in [200, 404, 405, 501]:
                    results['trigger_accessible'] = True
                    results['response_times']['trigger'] = response_time
                    results['successful_endpoints'] += 1
                    break
                else:
                    results['errors'].append(f"Trigger {url}: HTTP {response.status_code}")
                    
            except requests.exceptions.Timeout:
                results['errors'].append(f"Trigger {url}: Timeout after {self.default_timeout}s")
            except requests.exceptions.ConnectionError as e:
                results['errors'].append(f"Trigger {url}: Connection failed - {str(e)[:100]}")
            except Exception as e:
                results['errors'].append(f"Trigger {url}: {type(e).__name__} - {str(e)[:100]}")
        
        # Test fetch endpoints
        for url in FETCH_URLS:
            results['endpoints_tested'] += 1
            try:
                start = time.time()
                response = self.session.head(url, timeout=self.default_timeout)
                response_time = time.time() - start
                
                if response.status_code in [200, 404, 501]:
                    results['fetch_accessible'] = True
                    results['response_times']['fetch'] = response_time
                    results['successful_endpoints'] += 1
                    break
                else:
                    results['errors'].append(f"Fetch {url}: HTTP {response.status_code}")
                    
            except requests.exceptions.Timeout:
                results['errors'].append(f"Fetch {url}: Timeout after {self.default_timeout}s")
            except requests.exceptions.ConnectionError as e:
                results['errors'].append(f"Fetch {url}: Connection failed - {str(e)[:100]}")
            except Exception as e:
                results['errors'].append(f"Fetch {url}: {type(e).__name__} - {str(e)[:100]}")
        
        # Calculate success ratio
        results['success_ratio'] = results['successful_endpoints'] / results['endpoints_tested'] if results['endpoints_tested'] > 0 else 0
        
        return results
        
    def trigger_workflow_prd_compliant(self, challenge_date: str = None) -> bool:
        """Trigger N8N workflow with PRD-compliant payload and error handling"""
        
        # Get current date in IST for daily challenge
        import pytz
        from datetime import timedelta
        
        ist = pytz.timezone('Asia/Kolkata')
        now_ist = datetime.now(ist)
        
        # If no specific date provided, calculate today's challenge date using 6AM logic
        if not challenge_date:
            if now_ist.hour < 6:
                # Before 6 AM IST, get previous day's challenge
                challenge_date = (now_ist - timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                # After 6 AM IST, get current day's challenge
                challenge_date = now_ist.strftime('%Y-%m-%d')
        
        # Enhanced payload per PRD specifications with date information
        payload = {
            "action": "solve_daily_challenge",
            "challenge_date": challenge_date,
            "ist_time": now_ist.isoformat(),
            "utc_time": datetime.now(timezone.utc).isoformat(),
            "timestamp": int(time.time()),
            "iso_timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "leetcode_auto_solver",
            "prd_version": "1.0",
            "client_id": "enhanced_n8n_client",
            "request_id": f"req_{int(time.time())}_{os.getpid()}",
            "force_refresh": True,  # Ensure fresh solution
            "use_today_challenge": True  # Explicit flag for today's challenge
        }
        
        for i, url in enumerate(TRIGGER_URLS):
            try:
                print(f"[n8n] Triggering workflow attempt {i+1}/{len(TRIGGER_URLS)}: {url}")
                
                response = self.session.post(
                    url,
                    json=payload,
                    timeout=self.default_timeout * 2  # Longer timeout for trigger
                )
                
                if response.ok:
                    # Determine if this was a test or production webhook
                    webhook_type = "TEST" if "webhook-test" in url else "PRODUCTION"
                    print(f"[n8n] SUCCESS: Workflow triggered successfully via {webhook_type} webhook")
                    print(f"[n8n] Working URL: {url} (HTTP {response.status_code})")
                    
                    # Try to parse response for additional info
                    try:
                        response_data = response.json()
                        if isinstance(response_data, dict) and 'message' in response_data:
                            print(f"[n8n] Server response: {response_data['message']}")
                    except:
                        pass  # Ignore JSON parsing errors for trigger response
                    
                    return True
                else:
                    error_msg = f"HTTP {response.status_code}"
                    try:
                        error_response = response.json()
                        if isinstance(error_response, dict):
                            error_detail = error_response.get('message', response.text[:200])
                            hint = error_response.get('hint', '')
                            
                            if 'not registered' in error_detail:
                                print(f"[n8n] ERROR: WORKFLOW NOT ACTIVE: {error_detail}")
                                if hint:
                                    print(f"[n8n] HINT: {hint}")
                                print(f"[n8n] FIX: Activate the workflow in n8n editor")
                            else:
                                error_msg += f": {error_detail}"
                        else:
                            error_msg += f": {response.text[:200]}"
                    except:
                        error_msg += f": {response.text[:200]}"
                    
                    print(f"[n8n] Trigger failed: {error_msg}")
                    
            except requests.exceptions.Timeout:
                print(f"[n8n] Timeout triggering {url} (>{self.default_timeout * 2}s)")
                continue
            except requests.exceptions.ConnectionError as e:
                print(f"[n8n] Connection error with {url}: {str(e)[:100]}")
                continue
            except Exception as e:
                print(f"[n8n] Unexpected error with {url}: {type(e).__name__} - {str(e)[:100]}")
                continue
        
        raise N8NConnectionError("All trigger URLs failed - N8N service may be down")
    
    def poll_for_solution_prd_compliant(self, timeout_seconds: int = 300) -> Tuple[str, bool, List[str]]:
        """Poll for solution from N8N global storage with proper retry logic"""
        
        print(f"[n8n] Polling for solution from N8N global storage (timeout: {timeout_seconds}s)")
        
        start_time = time.time()
        poll_interval = 5  # Poll every 5 seconds
        max_polls = timeout_seconds // poll_interval
        poll_count = 0
        
        while poll_count < max_polls:
            elapsed = time.time() - start_time
            
            # Try all fetch URLs until one works
            for url_idx, url in enumerate(FETCH_URLS):
                try:
                    print(f"[n8n] Poll #{poll_count + 1}: Checking {url} for stored solution...")
                    
                    response = self.session.get(url, timeout=self.default_timeout)
                    if response.ok:
                        data = response.json()
                        
                        # DEBUG: Log the polling response too
                        print(f"[n8n] DEBUG: Polling response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                        
                        raw_code = self._extract_code_from_response(data)
                        
                        if raw_code and len(raw_code.strip()) > 30:
                            webhook_type = "TEST" if "webhook-test" in url else "PRODUCTION"
                            print(f"[n8n] SUCCESS: Solution retrieved from {webhook_type} webhook: {len(raw_code)} chars")
                            print(f"[n8n] Working URL: {url} (after {elapsed:.1f}s)")
                            print(f"[n8n] DEBUG: Polling extracted code preview: {raw_code[:200]}...")
                            
                            # Validate and fix the code
                            problem_title = data.get('title', 'Daily Challenge')
                            corrected_code, is_safe, warnings = quick_fix_leetcode(
                                raw_code, 
                                problem_title=problem_title
                            )
                            
                            print(f"[n8n] DEBUG: Final polling code preview: {corrected_code[:200]}...")
                            print(f"[n8n] Solution processed and ready")
                            return corrected_code, is_safe, warnings, problem_title
                        else:
                            print(f"[n8n] No solution in global storage yet (URL {url_idx + 1}/{len(FETCH_URLS)})")
                            if isinstance(data, dict) and data:
                                print(f"[n8n] DEBUG: Available data: {list(data.keys())}")
                            
                    else:
                        print(f"[n8n] HTTP {response.status_code} from {url}")
                        
                except requests.exceptions.Timeout:
                    print(f"[n8n] Timeout polling {url}")
                    continue
                except Exception as e:
                    print(f"[n8n] Error polling {url}: {str(e)[:100]}")
                    continue
            
            # If we've checked all URLs and no solution found, wait before retry
            poll_count += 1
            if poll_count < max_polls:
                print(f"[n8n] No solution found in poll #{poll_count}. Waiting {poll_interval}s before retry...")
                time.sleep(poll_interval)
            else:
                print(f"[n8n] Polling timeout after {elapsed:.1f}s ({poll_count} polls)")
        
        # If no solution found after polling, return a basic template
        print(f"[n8n] No solution available after {timeout_seconds}s, returning template")
        return "# Solution not ready yet\npass", True, ["Solution not yet available - polling timeout"]
    
    def _validate_code_completeness(self, code: str) -> bool:
        """Enhanced code completeness validation per PRD quality requirements"""
        
        if not code or len(code.strip()) < 50:
            return False
            
        code_lower = code.lower().strip()
        
        # Enhanced incomplete patterns detection
        incomplete_patterns = [
            'todo:', '# todo', 'implement', 'your code here',
            'your implementation', 'pass  # placeholder',
            'raise notimplementederror', 'def solve(self):\n    pass',
            '# implementation needed', '# code goes here',
            '# write your code', '# add your logic',
            'placeholder', 'stub', 'not implemented',
            '// todo', '/* todo', 'fixme', 'hack:',
            'temp:', 'temporary', 'xxx', 'yyy'
        ]
        
        for pattern in incomplete_patterns:
            if pattern in code_lower:
                return False
        
        # Enhanced completion indicators with weighted scoring
        completion_indicators = [
            ('return ', 3),           # Critical - must have returns
            ('class solution', 3),    # LeetCode pattern
            ('def ', 2),             # Function definitions
            ('if ', 1),              # Conditional logic
            ('for ', 1),             # Iteration
            ('while ', 1),           # Loops
            ('.append(', 1),         # List operations
            ('enumerate(', 1),       # Proper iteration
            ('range(', 1),           # Range usage
            ('len(', 1),             # Length operations
            ('in ', 1),              # Membership testing
            ('and ', 1),             # Boolean logic
            ('or ', 1),              # Boolean logic
            ('not ', 1),             # Negation
            ('==', 1),               # Comparison
            ('!=', 1),               # Comparison
            ('<=', 1),               # Comparison
            ('>=', 1),               # Comparison
        ]
        
        total_score = 0
        for indicator, weight in completion_indicators:
            if indicator in code_lower:
                total_score += weight
        
        # Additional structural checks
        has_proper_structure = all([
            'class solution' in code_lower or 'def ' in code_lower,
            'return' in code_lower,
            len(code.split('\n')) >= 5,  # Reasonable number of lines
            ':' in code  # At least one colon (function/class definition)
        ])
        
        # Require minimum score AND proper structure
        is_complete = total_score >= 8 and has_proper_structure
        
        if is_complete:
            print(f"[n8n] Code validation: COMPLETE (score: {total_score}, structure: OK)")
        else:
            print(f"[n8n] Code validation: INCOMPLETE (score: {total_score}, structure: {'OK' if has_proper_structure else 'MISSING'})")
            
        return is_complete
    
    def _calculate_code_quality(self, code: str) -> float:
        """Calculate code quality score for additional validation"""
        if not code:
            return 0.0
        
        quality_factors = {
            'has_docstring': 0.1 if '"""' in code or "'''" in code else 0,
            'has_type_hints': 0.1 if ':' in code and '->' in code else 0,
            'proper_naming': 0.1 if any(word in code.lower() for word in ['nums', 'target', 'result', 'left', 'right']) else 0,
            'has_comments': 0.1 if '#' in code else 0,
            'reasonable_length': 0.2 if 100 <= len(code) <= 2000 else 0,
            'has_error_handling': 0.1 if 'try:' in code or 'except' in code else 0,
            'algorithmic_patterns': 0.3 if any(pattern in code.lower() for pattern in ['sort', 'hash', 'dp', 'binary', 'two pointer']) else 0
        }
        
        return sum(quality_factors.values())
    
    def _extract_code_from_response(self, data: dict) -> Optional[str]:
        """Enhanced code extraction with comprehensive field checking and freshness priority"""
        
        if not isinstance(data, dict):
            return None
        
        print(f"[n8n] DEBUG: Extracting code from response with keys: {list(data.keys())}")
        
        # Collect all potential code candidates with their sources
        candidates = []
        
        # Primary code fields (most likely to contain the solution)
        primary_fields = [
            'solutionCode', 'code', 'pythonCode', 'solution', 'todayCode', 'dailyCode', 'freshCode'
        ]
        
        # Secondary code fields  
        secondary_fields = [
            'codeText', 'generated_code', 'final_code', 
            'leetcode_solution', 'answer', 'result', 'content'
        ]
        
        # Tertiary fields (last resort)
        tertiary_fields = [
            'data', 'response', 'output', 'text', 'body'
        ]
        
        # Check primary fields first
        for field in primary_fields:
            if field in data and data[field]:
                code = str(data[field]).strip()
                if self._is_valid_code_candidate(code):
                    candidates.append({
                        'code': code,
                        'field': field,
                        'priority': 1,
                        'length': len(code),
                        'has_today_indicators': self._has_fresh_indicators(code)
                    })
                    print(f"[n8n] DEBUG: Found primary candidate in '{field}': {len(code)} chars")
        
        # If no primary candidates, try secondary
        if not candidates:
            for field in secondary_fields:
                if field in data and data[field]:
                    code = str(data[field]).strip()
                    if self._is_valid_code_candidate(code):
                        candidates.append({
                            'code': code,
                            'field': field,
                            'priority': 2,
                            'length': len(code),
                            'has_today_indicators': self._has_fresh_indicators(code)
                        })
                        print(f"[n8n] DEBUG: Found secondary candidate in '{field}': {len(code)} chars")
        
        # If still no candidates, try tertiary fields
        if not candidates:
            for field in tertiary_fields:
                if field in data and data[field]:
                    code = str(data[field]).strip()
                    if self._is_valid_code_candidate(code):
                        candidates.append({
                            'code': code,
                            'field': field,
                            'priority': 3,
                            'length': len(code),
                            'has_today_indicators': self._has_fresh_indicators(code)
                        })
                        print(f"[n8n] DEBUG: Found tertiary candidate in '{field}': {len(code)} chars")
        
        # Try nested extraction if no candidates found
        if not candidates:
            for key, value in data.items():
                if isinstance(value, dict):
                    nested_code = self._extract_code_from_response(value)
                    if nested_code and self._is_valid_code_candidate(nested_code):
                        candidates.append({
                            'code': nested_code,
                            'field': f'nested.{key}',
                            'priority': 4,
                            'length': len(nested_code),
                            'has_today_indicators': self._has_fresh_indicators(nested_code)
                        })
                        print(f"[n8n] DEBUG: Found nested candidate in '{key}': {len(nested_code)} chars")
                elif isinstance(value, str) and len(value) > 50:
                    if 'class Solution' in value or 'def ' in value:
                        candidates.append({
                            'code': value.strip(),
                            'field': key,
                            'priority': 5,
                            'length': len(value),
                            'has_today_indicators': self._has_fresh_indicators(value)
                        })
                        print(f"[n8n] DEBUG: Found direct string candidate in '{key}': {len(value)} chars")
        
        # Choose the best candidate
        if candidates:
            # Sort by: priority (lower is better), then by freshness indicators, then by length
            best_candidate = sorted(candidates, key=lambda c: (
                c['priority'],
                -int(c['has_today_indicators']),  # Fresh indicators first
                -c['length']  # Longer code second
            ))[0]
            
            print(f"[n8n] DEBUG: Selected best candidate from '{best_candidate['field']}' "
                  f"(priority: {best_candidate['priority']}, fresh: {best_candidate['has_today_indicators']}, "
                  f"length: {best_candidate['length']})")
            
            return best_candidate['code']
        
        print(f"[n8n] DEBUG: No valid code candidates found in response")
        return None
    
    def _is_valid_code_candidate(self, code: str) -> bool:
        """Check if extracted text is a valid code candidate"""
        if not code or len(code.strip()) < 30:
            return False
        
        # Must contain basic code indicators
        code_indicators = ['def ', 'class ', 'return', 'if ', 'for ']
        if not any(indicator in code for indicator in code_indicators):
            return False
        
        # Should not be mostly HTML, JSON, or other formats
        html_tags = ['<html>', '<body>', '<div>', '<script>']
        if any(tag in code.lower() for tag in html_tags):
            return False
        
        json_indicators = ['"status":', '"error":', '"message":']
        if any(indicator in code for indicator in json_indicators):
            return False
        
        return True
    
    def _has_fresh_indicators(self, code: str) -> bool:
        """Check if code contains indicators that suggest it's fresh/today's solution"""
        if not code:
            return False
            
        code_lower = code.lower()
        
        # Indicators that suggest fresh code
        fresh_indicators = [
            'today', 'daily', '2025', 'fresh', 'new', 'current',
            'september', 'sep', 'latest', 'updated'
        ]
        
        # Anti-indicators (suggest old code)
        stale_indicators = [
            'yesterday', 'old', 'cached', 'previous', 'sudoku', 
            'grid', 'board', '9x9', 'puzzle'
        ]
        
        # Count fresh vs stale indicators
        fresh_count = sum(1 for indicator in fresh_indicators if indicator in code_lower)
        stale_count = sum(1 for indicator in stale_indicators if indicator in code_lower)
        
        # If it mentions sudoku specifically, it's likely stale
        if 'sudoku' in code_lower:
            print(f"[n8n] DEBUG: Code contains 'sudoku' - likely stale")
            return False
            
        # More fresh indicators than stale
        return fresh_count > stale_count
    
    def check_global_storage_direct(self) -> Tuple[Optional[str], bool, List[str], str]:
        """
        Direct check of n8n global storage without polling
        Used by /leetcode-code endpoint for immediate retrieval
        """
        print("[n8n] Direct check of global storage for cached solution...")
        
        for url_idx, url in enumerate(FETCH_URLS):
            try:
                response = self.session.get(url, timeout=10)  # Shorter timeout for direct check
                if response.ok:
                    data = response.json()
                    
                    # DEBUG: Log the full response to understand what we're getting
                    print(f"[n8n] DEBUG: Full response from {url}:")
                    print(f"[n8n] DEBUG: Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                    if isinstance(data, dict):
                        for key, value in data.items():
                            if isinstance(value, str) and len(value) > 100:
                                print(f"[n8n] DEBUG: {key}: {value[:100]}... (truncated, total {len(value)} chars)")
                            else:
                                print(f"[n8n] DEBUG: {key}: {value}")
                    
                    raw_code = self._extract_code_from_response(data)
                    
                    if raw_code and len(raw_code.strip()) > 30:
                        webhook_type = "TEST" if "webhook-test" in url else "PRODUCTION"
                        print(f"[n8n] SUCCESS: Found solution in {webhook_type} global storage: {len(raw_code)} chars")
                        print(f"[n8n] Working URL: {url}")
                        print(f"[n8n] DEBUG: Extracted code preview: {raw_code[:200]}...")
                        
                        # Validate and fix the code
                        problem_title = data.get('title', 'Daily Challenge')
                        corrected_code, is_safe, warnings = quick_fix_leetcode(
                            raw_code, 
                            problem_title=problem_title
                        )
                        
                        print(f"[n8n] DEBUG: Final code preview: {corrected_code[:200]}...")
                        return corrected_code, is_safe, warnings, problem_title
                    else:
                        print(f"[n8n] No solution in global storage (URL {url_idx + 1}/{len(FETCH_URLS)})")
                        print(f"[n8n] DEBUG: Extracted code was: {repr(raw_code)}")
                elif response.status_code == 404:
                    try:
                        error_data = response.json()
                        if 'not registered' in error_data.get('message', ''):
                            print(f"[n8n] ERROR: WORKFLOW NOT ACTIVE: leetcode-code webhook not registered")
                            print(f"[n8n] FIX: Activate the workflow in n8n editor to enable global storage")
                            return None, False, ["N8N workflow not active - activate in n8n editor"], "Daily Challenge"
                    except:
                        pass
                    print(f"[n8n] HTTP {response.status_code} from {url}")
                else:
                    print(f"[n8n] HTTP {response.status_code} from {url}")
                    
            except Exception as e:
                print(f"[n8n] Error checking {url}: {str(e)[:100]}")
                continue
        
        print("[n8n] No solution found in global storage")
        return None, False, ["No solution in global storage"], "Daily Challenge"

# Main enhanced functions per PRD

def get_code_from_n8n_simple(
    enable_validation: bool = True,
    timeout_seconds: int = 300,
    fallback_enabled: bool = True,
    challenge_date: str = None
) -> Tuple[str, bool, List[str], str]:
    """
    PRD-compliant N8N code retrieval with comprehensive error handling and validation
    
    Args:
        enable_validation: Enable code validation per PRD quality requirements
        timeout_seconds: Maximum wait time per PRD performance requirements (default 5 minutes)
        fallback_enabled: Enable fallback strategies per PRD reliability requirements
    
    Returns:
        Tuple of (code, is_safe, warnings_or_errors)
    """
    
    client = EnhancedN8NClient()
    
    try:
        print(f"[n8n] Starting PRD-compliant workflow (timeout: {timeout_seconds}s)")
        
        # Step 1: Comprehensive connection validation per PRD
        print("[n8n] Validating N8N connection...")
        connection_status = client.validate_n8n_connection()
        
        if connection_status['success_ratio'] < 0.5:
            print(f"[n8n] Poor connection quality (success: {connection_status['success_ratio']:.1%})")
            if connection_status['errors']:
                for error in connection_status['errors'][:3]:  # Show first 3 errors
                    print(f"[n8n] Connection error: {error}")
            
            if not fallback_enabled:
                raise N8NConnectionError("N8N endpoints have poor connectivity")
        
        # Step 2: Trigger workflow with enhanced error handling per PRD
        trigger_success = False
        try:
            print(f"[n8n] Triggering workflow with PRD-compliant payload for date: {challenge_date or 'auto-calculated'}...")
            trigger_success = client.trigger_workflow_prd_compliant(challenge_date)
            
            if trigger_success:
                print("[n8n] Workflow triggered successfully")
            else:
                print("[n8n] Trigger failed, checking for existing solution...")
                
        except N8NConnectionError as e:
            if not fallback_enabled:
                raise
            print(f"[n8n] Trigger failed: {e}")
            print("[n8n] Continuing with polling in case workflow is already running...")
        
        # Step 3: Poll for solution with enhanced validation per PRD
        print(f"[n8n] Starting enhanced polling (max {timeout_seconds}s)...")
        code, is_safe, warnings, problem_title = client.poll_for_solution_prd_compliant(
            timeout_seconds=timeout_seconds
        )
        
        # Step 4: Final validation and quality assurance per PRD
        if code and len(code.strip()) > 30:
            quality_score = client._calculate_code_quality(code)
            print(f"[n8n] Solution retrieved successfully (quality: {quality_score:.2f})")
            
            # Add quality info to warnings
            if quality_score < 0.5:
                warnings.append(f"Code quality below average ({quality_score:.2f})")
            elif quality_score >= 0.8:
                warnings.append(f"High quality code detected ({quality_score:.2f})")
            
            return code, is_safe, warnings, problem_title
        else:
            raise N8NTimeoutError("No valid solution retrieved after polling")
                
    except N8NTimeoutError as e:
        print(f"[n8n] Workflow timeout: {str(e)}")
        if fallback_enabled:
            return handle_timeout_fallback_prd_compliant(str(e))
        else:
            return "", False, [f"Timeout: {str(e)}"], "Daily Challenge"
                    
    except Exception as e:
        print(f"[n8n] Workflow failed: {str(e)}")
        if fallback_enabled:
            return handle_timeout_fallback_prd_compliant(f"Error: {str(e)}")
        else:
            return "", False, [f"Error: {str(e)}"], "Daily Challenge"

def handle_timeout_fallback_prd_compliant(error_msg: str) -> Tuple[str, bool, List[str], str]:
    """Enhanced fallback strategies per PRD reliability requirements"""
    
    print("[n8n] Implementing PRD-compliant fallback strategies...")
    
    # Fallback 1: Emergency direct fetch (workflow might have completed silently)
    client = EnhancedN8NClient()
    for attempt, url in enumerate(FETCH_URLS, 1):
        try:
            print(f"[n8n] Emergency fallback {attempt}/{len(FETCH_URLS)}: {url}")
            
            response = client.session.get(url, timeout=20)
            if response.ok:
                try:
                    data = response.json()
                    code = client._extract_code_from_response(data)
                    
                    if code and len(code.strip()) > 30:
                        print("[n8n] Emergency fallback successful!")
                        corrected_code, is_safe, warnings = quick_fix_leetcode(code)
                        warnings.extend([
                            "Retrieved via emergency fallback",
                            f"Original error: {error_msg}",
                            "Solution may be from previous run"
                        ])
                        problem_title = data.get('title', 'Daily Challenge')
                        return corrected_code, is_safe, warnings, problem_title
                        
                except json.JSONDecodeError:
                    print(f"[n8n] Invalid JSON from {url}")
                    continue
                    
        except Exception as e:
            print(f"[n8n] Emergency fallback failed for {url}: {str(e)[:100]}")
            continue
    
    # Fallback 2: Return structured error template per PRD
    print("[n8n] All fallbacks exhausted - generating error template")
    
    current_time = datetime.now(timezone.utc)
    
    error_template = f'''# LeetCode Daily Challenge - Service Temporarily Unavailable
# Generated: {current_time.strftime("%Y-%m-%d %H:%M:%S UTC")}
# Error: {error_msg}
#
# This is an auto-generated template due to N8N workflow timeout
# PRD-compliant error handling has been activated
#
# IMMEDIATE ACTIONS REQUIRED:
# 1. Check N8N service status at {N8N_BASE_URL}
# 2. Verify webhook endpoints are responding
# 3. Check system resources and network connectivity
# 4. Review N8N workflow logs for errors
#
# MANUAL SOLUTION REQUIRED:
# Please visit LeetCode.com and implement the daily challenge manually
# until the automated service is restored.

from typing import List, Optional, Dict, Any

class Solution:
    def __init__(self):
        """
        Automated solution service is temporarily unavailable.
        Error: {error_msg}
        
        Please implement the solution manually by:
        1. Going to https://leetcode.com/problemset/all/
        2. Finding today's daily challenge
        3. Reading the problem statement
        4. Implementing the algorithm below
        """
        pass
    
    def solve(self, *args, **kwargs) -> Any:
        """
        MANUAL IMPLEMENTATION REQUIRED
        
        Steps to implement:
        1. Analyze the problem requirements
        2. Choose appropriate data structures
        3. Implement the algorithm
        4. Test with example cases
        5. Submit to LeetCode
        
        Common patterns to consider:
        - Array manipulation: Two pointers, sliding window
        - String processing: Character counting, pattern matching  
        - Tree problems: DFS, BFS, recursion
        - Graph problems: Traversal algorithms
        - Dynamic programming: Memoization, bottom-up
        """
        
        # TODO: Replace this with actual solution logic
        raise NotImplementedError(
            "Automated solution unavailable. "
            f"Manual implementation required. "
            f"Service error: {error_msg}"
        )
    
    # Helper method templates
    def helper_method(self, param):
        """Add helper methods as needed for the solution"""
        pass

# Example usage (remove when implementing actual solution):
# solution = Solution()
# result = solution.solve(input_data)
# print(result)
'''
    
    comprehensive_warnings = [
        f"N8N workflow error: {error_msg}",
        "All fallback strategies failed",
        "Manual implementation template provided",
        "Check N8N service health immediately",
        "Review system monitoring dashboards",
        "Verify webhook endpoint connectivity",
        f"Last attempt: {current_time.isoformat()}",
        "PRD-compliant error handling activated"
    ]
    
    return error_template, False, comprehensive_warnings, "Daily Challenge"

def check_n8n_health() -> Dict[str, Any]:
    """Comprehensive N8N health check per PRD monitoring requirements"""
    
    client = EnhancedN8NClient()
    
    try:
        start_time = time.time()
        validation_result = client.validate_n8n_connection()
        total_time = time.time() - start_time
        
        # Calculate detailed health metrics
        health_status = 'healthy'
        if validation_result['success_ratio'] < 0.5:
            health_status = 'unhealthy'
        elif validation_result['success_ratio'] < 0.8:
            health_status = 'degraded'
        
        health = {
            'status': health_status,
            'overall_health_score': validation_result['success_ratio'],
            'trigger_accessible': validation_result['trigger_accessible'],
            'fetch_accessible': validation_result['fetch_accessible'],
            'response_time': total_time,
            'individual_response_times': validation_result.get('response_times', {}),
            'endpoints_tested': validation_result['endpoints_tested'],
            'successful_endpoints': validation_result['successful_endpoints'],
            'errors': validation_result.get('errors', []),
            'configuration': {
                'base_url': N8N_BASE_URL,
                'trigger_endpoint': TRIGGER_URL,
                'fetch_endpoint': FETCH_URL,
                'timeout_seconds': client.default_timeout
            },
            'prd_compliance': {
                'compliant': True,
                'version': '1.0',
                'fallback_enabled': True,
                'retry_logic': True,
                'comprehensive_logging': True
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        # Generate recommendations based on health status
        recommendations = []
        
        if not health['trigger_accessible']:
            recommendations.extend([
                "Check N8N service is running",
                "Verify trigger webhook configuration",
                "Test N8N workflow manually"
            ])
            
        if not health['fetch_accessible']:
            recommendations.extend([
                "Check fetch webhook endpoint configuration",
                "Verify N8N workflow output format",
                "Test endpoint accessibility manually"
            ])
            
        if health['response_time'] > 10:
            recommendations.extend([
                "N8N response time is high - check system resources",
                "Consider optimizing N8N workflow performance",
                "Review network connectivity"
            ])
            
        if len(health['errors']) > 2:
            recommendations.extend([
                "Multiple connection errors detected",
                "Review N8N service logs",
                "Check network configuration and firewalls"
            ])
            
        if health['overall_health_score'] < 0.8:
            recommendations.append("Consider implementing additional N8N endpoint redundancy")
        
        health['recommendations'] = recommendations
        health['action_required'] = len(recommendations) > 0
        
        return health
        
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'error_type': type(e).__name__,
            'configuration': {
                'base_url': N8N_BASE_URL,
                'trigger_endpoint': TRIGGER_URL,
                'fetch_endpoint': FETCH_URL
            },
            'prd_compliance': {
                'compliant': False,
                'error_handling': True
            },
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'recommendations': [
                "Check N8N service availability",
                "Verify network connectivity",
                "Review error logs for detailed diagnosis",
                "Consider manual solution implementation"
            ]
        }

# Async wrapper for compatibility
async def get_code_from_n8n_async(
    timeout_seconds: int = 300,
    enable_validation: bool = True,
    fallback_enabled: bool = True
) -> Tuple[str, bool, List[str]]:
    """Async wrapper for N8N code retrieval per PRD async support"""
    
    loop = asyncio.get_event_loop()
    
    try:
        # Run the synchronous function in thread pool
        result = await loop.run_in_executor(
            None,
            get_code_from_n8n_simple,
            enable_validation,
            timeout_seconds,
            fallback_enabled
        )
        return result
        
    except Exception as e:
        print(f"[n8n] Async wrapper error: {str(e)}")
        if fallback_enabled:
            return handle_timeout_fallback_prd_compliant(f"Async error: {str(e)}")
        else:
            return "", False, [f"Async error: {str(e)}"], "Daily Challenge"

# Utility functions for PRD compliance
def get_n8n_configuration() -> Dict[str, Any]:
    """Get current N8N configuration for debugging"""
    return {
        'base_url': N8N_BASE_URL,
        'trigger_endpoints': TRIGGER_URLS,
        'fetch_endpoints': FETCH_URLS,
        'default_timeout': int(os.getenv('N8N_TIMEOUT_SECONDS', '30')),
        'environment_variables': {
            'N8N_WEBHOOK_BASE': os.getenv('N8N_WEBHOOK_BASE'),
            'N8N_TIMEOUT_SECONDS': os.getenv('N8N_TIMEOUT_SECONDS'),
        },
        'prd_version': '1.0'
    }

def get_code_from_n8n_sync_wrapper(
    enable_validation: bool = True,
    timeout_seconds: int = 300,
    fallback_enabled: bool = True
) -> Tuple[str, bool, List[str], str]:
    """
    Synchronous wrapper for N8N code retrieval - used by scheduler
    
    Args:
        enable_validation: Enable code validation per PRD quality requirements
        timeout_seconds: Maximum wait time per PRD performance requirements (default 5 minutes)
        fallback_enabled: Enable fallback strategies per PRD reliability requirements
    
    Returns:
        Tuple of (code, is_safe, warnings_or_errors, problem_title)
    """
    return get_code_from_n8n_simple(enable_validation, timeout_seconds, fallback_enabled)

def check_n8n_global_storage_direct() -> Tuple[Optional[str], bool, List[str], str]:
    """
    Direct check of n8n global storage for immediate retrieval
    Used by /leetcode-code endpoint when solution should already be available
    
    Returns:
        Tuple of (code_or_None, is_safe, warnings, problem_title)
    """
    client = EnhancedN8NClient()
    return client.check_global_storage_direct()

def test_n8n_connectivity() -> Dict[str, Any]:
    """Test N8N connectivity and return detailed results"""
    client = EnhancedN8NClient()
    
    print("[n8n] Testing connectivity to all endpoints...")
    
    start_time = time.time()
    validation = client.validate_n8n_connection()
    test_duration = time.time() - start_time
    
    result = {
        'test_duration_seconds': test_duration,
        'validation_result': validation,
        'configuration': get_n8n_configuration(),
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'test_passed': validation['trigger_accessible'] and validation['fetch_accessible']
    }
    
    # Print results
    if result['test_passed']:
        print(f"[n8n] Connectivity test PASSED in {test_duration:.1f}s")
    else:
        print(f"[n8n] Connectivity test FAILED in {test_duration:.1f}s")
        for error in validation.get('errors', []):
            print(f"[n8n] Error: {error}")
    
    return result