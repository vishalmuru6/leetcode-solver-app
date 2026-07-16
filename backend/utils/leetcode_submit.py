import time
import os
import json
import hashlib
import logging
from datetime import datetime, timedelta
import pytz
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException

# Required dependencies
try:
    import pyperclip
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False

try:
    import pyautogui
    import pytesseract
    PYAUTOGUI_AVAILABLE = True
    # Configure PyAutoGUI settings
    pyautogui.PAUSE = 0.5
    pyautogui.FAILSAFE = True
    print("[INFO] PyAutoGUI and pytesseract available for GUI automation")
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    print("[WARNING] PyAutoGUI/pytesseract not available - install with: pip install pyautogui pytesseract")

# Disable Redis - using SQLite cache instead
REDIS_AVAILABLE = False
print("[INFO] Redis disabled - using SQLite cache system")

try:
    from cryptography.fernet import Fernet
    ENCRYPTION_AVAILABLE = True
except ImportError:
    ENCRYPTION_AVAILABLE = False
    print("[WARNING] Cryptography not available - install with: pip install cryptography")

# Global driver tracking
_current_driver = None

# Cache configuration
CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', 'cache')
DAILY_CACHE_FILE = os.path.join(CACHE_DIR, 'daily_challenge_cache.json')
CREDENTIALS_FILE = os.path.join(CACHE_DIR, 'credentials.enc')
IST_TIMEZONE = pytz.timezone('Asia/Kolkata')

# Redis disabled - using SQLite cache system instead

def ensure_cache_directory():
    """Ensure cache directory exists"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

def get_encryption_key():
    """Get or create encryption key for credentials"""
    key_file = os.path.join(CACHE_DIR, 'key.key')
    
    if os.path.exists(key_file):
        with open(key_file, 'rb') as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        ensure_cache_directory()
        with open(key_file, 'wb') as f:
            f.write(key)
        return key

def encrypt_credentials(username, password):
    """Encrypt and store credentials"""
    if not ENCRYPTION_AVAILABLE:
        print("[WARNING] Encryption not available - credentials not stored")
        return False
    
    try:
        ensure_cache_directory()
        key = get_encryption_key()
        fernet = Fernet(key)
        
        credentials = json.dumps({
            'username': username,
            'password': password,
            'timestamp': datetime.now().isoformat()
        })
        
        encrypted_credentials = fernet.encrypt(credentials.encode())
        
        with open(CREDENTIALS_FILE, 'wb') as f:
            f.write(encrypted_credentials)
        
        print("[SUCCESS] Credentials encrypted and stored")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to encrypt credentials: {e}")
        return False

def decrypt_credentials():
    """Decrypt and retrieve credentials"""
    if not ENCRYPTION_AVAILABLE or not os.path.exists(CREDENTIALS_FILE):
        return None, None
    
    try:
        key = get_encryption_key()
        fernet = Fernet(key)
        
        with open(CREDENTIALS_FILE, 'rb') as f:
            encrypted_credentials = f.read()
        
        decrypted_data = fernet.decrypt(encrypted_credentials).decode()
        credentials = json.loads(decrypted_data)
        
        return credentials['username'], credentials['password']
        
    except Exception as e:
        print(f"[ERROR] Failed to decrypt credentials: {e}")
        return None, None

def get_ist_today():
    """Get current date in IST"""
    return datetime.now(IST_TIMEZONE).date()

def get_last_refresh_time():
    """Get last cache refresh time in IST"""
    try:
        if os.path.exists(DAILY_CACHE_FILE):
            with open(DAILY_CACHE_FILE, 'r') as f:
                data = json.load(f)
                refresh_time_str = data.get('last_refresh')
                if refresh_time_str:
                    return datetime.fromisoformat(refresh_time_str).replace(tzinfo=IST_TIMEZONE)
    except Exception:
        pass
    return None

def should_refresh_cache():
    """Cache refresh disabled - using new SQLite cache system"""
    print("[CACHE] Cache refresh disabled - using new SQLite cache system")
    return False

def get_redis_client():
    """Redis disabled - using SQLite cache system"""
    return None

def cache_daily_solution(problem_url, problem_statement, solution_code):
    """Cache daily solution in both Redis and file system"""
    ensure_cache_directory()
    
    cache_data = {
        'problem_url': problem_url,
        'problem_statement': problem_statement,
        'solution_code': solution_code,
        'last_refresh': datetime.now(IST_TIMEZONE).isoformat(),
        'date': get_ist_today().isoformat()
    }
    
    # File system cache (fallback)
    try:
        with open(DAILY_CACHE_FILE, 'w') as f:
            json.dump(cache_data, f, indent=2)
        print("[CACHE] Daily solution cached to file system")
    except Exception as e:
        print(f"[WARNING] Failed to cache to file: {e}")
    
    # Redis cache (primary)
    redis_client = get_redis_client()
    if redis_client:
        try:
            redis_key = f"leetcode_daily:{get_ist_today()}"
            redis_client.hset(redis_key, mapping=cache_data)
            redis_client.expire(redis_key, 86400)  # Expire after 24 hours
            print("[CACHE] Daily solution cached to Redis")
        except Exception as e:
            print(f"[WARNING] Failed to cache to Redis: {e}")

def get_cached_daily_solution():
    """Get cached daily solution from Redis or file system"""
    today = get_ist_today()
    
    # Try Redis first
    redis_client = get_redis_client()
    if redis_client:
        try:
            redis_key = f"leetcode_daily:{today}"
            cached_data = redis_client.hgetall(redis_key)
            if cached_data and cached_data.get('solution_code'):
                print("[CACHE] Retrieved daily solution from Redis")
                return cached_data
        except Exception as e:
            print(f"[WARNING] Redis retrieval failed: {e}")
    
    # Fallback to file system
    try:
        if os.path.exists(DAILY_CACHE_FILE):
            with open(DAILY_CACHE_FILE, 'r') as f:
                cached_data = json.load(f)
                cache_date = cached_data.get('date')
                if cache_date == today.isoformat():
                    print("[CACHE] Retrieved daily solution from file system")
                    return cached_data
    except Exception as e:
        print(f"[WARNING] File cache retrieval failed: {e}")
    
    return None

def cleanup_driver():
    """Force cleanup of existing driver"""
    global _current_driver
    if _current_driver:
        try:
            _current_driver.quit()
        except Exception as e:
            print(f"[WARNING] Driver cleanup error: {e}")
        finally:
            _current_driver = None
            time.sleep(1)
    
    # Kill any remaining chromedriver processes (Windows)
    try:
        import subprocess
        subprocess.run(['taskkill', '/f', '/im', 'chromedriver.exe'], 
                     capture_output=True, check=False)
    except Exception:
        pass

def init_driver():
    """Initialize undetected Chrome with stealth configuration"""
    global _current_driver
    cleanup_driver()
    
    print("[INFO] Starting stealth Chrome for daily challenge...")
    
    try:
        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins")
        options.add_argument("--window-size=1920,1080")
        
        # Try to auto-detect Chrome version, fall back to manual version if needed
        try:
            driver = uc.Chrome(options=options, version_main=139)  # Match installed Chrome version
        except Exception as version_error:
            print(f"[WARNING] Chrome version 139 failed: {version_error}")
            print("[INFO] Trying auto-detection...")
            driver = uc.Chrome(options=options)
        _current_driver = driver
        
        # Enhanced stealth script
        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined,
                    });
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5],
                    });
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en'],
                    });
                """
            })
        except Exception as e:
            print(f"[WARNING] Stealth script failed: {e}")
        
        # Configure timeouts without test navigation
        driver.set_page_load_timeout(30)
        driver.implicitly_wait(5)  # Reduced implicit wait
        print("[SUCCESS] Stealth Chrome ready")
        return driver
        
    except Exception as e:
        print(f"[WARNING] Primary Chrome init failed: {e}")
        try:
            # Fallback with minimal options
            options = uc.ChromeOptions()
            options.add_argument("--no-sandbox")
            try:
                driver = uc.Chrome(options=options, version_main=139)  # Match installed Chrome version
            except Exception:
                print("[INFO] Fallback: trying auto-detection...")
                driver = uc.Chrome(options=options)
            _current_driver = driver
            driver.set_page_load_timeout(30)
            driver.implicitly_wait(5)
            print("[SUCCESS] Fallback Chrome ready")
            return driver
        except Exception as fallback_error:
            raise Exception(f"Chrome initialization failed: {str(e)} | Fallback failed: {str(fallback_error)}")

def wait_for_element_clickable(driver, selectors, timeout=10):
    """Wait for any of the given selectors to be clickable"""
    wait = WebDriverWait(driver, timeout)
    for selector in selectors:
        try:
            if selector.startswith("//"):
                element = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
            else:
                element = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
            return element, selector
        except:
            continue
    return None, None

def wait_for_dynamic_content(driver, timeout=15, silent=False):
    """Wait for dynamic content to load"""
    if not silent:
        print("[WAIT] Loading dynamic content...")
    
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except Exception as e:
        print(f"[WARNING] Document ready state check failed: {e}")
    
    # Wait for React/Vue frameworks
    for attempt in range(min(timeout, 20)):  # Cap at 20 to prevent excessive waiting
        try:
            loading_complete = driver.execute_script("""
                try {
                    var loadingElements = document.querySelectorAll(
                        '.loading, .spinner, .skeleton, [class*="loading"], [class*="spinner"]'
                    );
                    var hasLoading = false;
                    for (var i = 0; i < loadingElements.length; i++) {
                        if (loadingElements[i].offsetParent !== null) {
                            hasLoading = true;
                            break;
                        }
                    }
                    return !hasLoading;
                } catch (e) {
                    return true; // Assume loaded if script fails
                }
            """)
            
            if loading_complete:
                time.sleep(2)
                print("[SUCCESS] Dynamic content loaded")
                return True
                
            time.sleep(1)
            
        except Exception as e:
            print(f"[WARNING] Dynamic content check failed: {e}")
            time.sleep(1)
    
    print("[WARNING] Dynamic content loading timeout")
    return False

def secure_login(driver, username=None, password=None):
    """Secure login with credential management"""
    print("[LOGIN] Starting secure login process...")
    
    # Try to get credentials from storage first
    stored_username, stored_password = None, None
    if not username or not password:
        try:
            stored_username, stored_password = decrypt_credentials()
            if stored_username and stored_password:
                username, password = stored_username, stored_password
                print("[LOGIN] Using stored encrypted credentials")
        except Exception as e:
            print(f"[WARNING] Could not decrypt stored credentials: {e}")
    
    if not username or not password:
        raise Exception("No credentials provided and none stored")
    
    # Navigate to login with better reliability
    driver.get("https://leetcode.com/accounts/login/")
    print("[LOGIN] Loading login page...")
    
    # Wait for page to properly load
    time.sleep(2)
    
    # Find and fill username field
    username_selectors = ["input[name='login']", "input[type='email']", "input#id_login"]
    username_field, _ = wait_for_element_clickable(driver, username_selectors, 10)
    
    if not username_field:
        raise Exception("Could not find username field")
    
    # Clear and enter username carefully
    username_field.clear()
    time.sleep(0.2)
    username_field.send_keys(username)
    print("[SUCCESS] Username entered")
    
    # Find and fill password field
    password_selectors = ["input[name='password']", "input[type='password']", "input#id_password"]
    password_field, _ = wait_for_element_clickable(driver, password_selectors, 8)
    
    if not password_field:
        raise Exception("Could not find password field")
    
    # Clear and enter password carefully
    password_field.clear()
    password_field.send_keys(password)
    print("[SUCCESS] Password entered")
    
    # Wait 1 second after entering credentials before clicking
    print("[LOGIN] Waiting 1 second after entering credentials...")
    time.sleep(1)
    print("[LOGIN] Clicking sign-in button...")
    login_success = False
    
    # Method 1: Immediate JavaScript click (fastest) - with better filtering
    try:
        js_clicked = driver.execute_script("""
            // First, try the most specific selectors
            var specificButtons = document.querySelectorAll('button[type="submit"]');
            for (var btn of specificButtons) {
                var text = btn.textContent.trim().toLowerCase();
                var classList = btn.className.toLowerCase();
                
                // Skip interview/other buttons explicitly
                if (text.includes('interview') || text.includes('premium') || text.includes('explore')) {
                    continue;
                }
                
                // Look for sign in specific text
                if ((text === 'sign in' || text === 'login' || text === 'submit') && btn.offsetParent !== null && !btn.disabled) {
                    console.log('Clicking login button:', text);
                    btn.click();
                    return true;
                }
            }
            
            // If no submit button found, look for other login buttons
            var allButtons = document.querySelectorAll('button, input[type="submit"]');
            for (var btn of allButtons) {
                var text = btn.textContent.trim().toLowerCase();
                var id = (btn.id || '').toLowerCase();
                
                // Skip interview/navigation buttons
                if (text.includes('interview') || text.includes('premium') || text.includes('explore') || 
                    text.includes('problems') || text.includes('discuss') || text.includes('contest')) {
                    continue;
                }
                
                // Look for sign in indicators
                if ((text === 'sign in' || text === 'login' || id.includes('signin') || id.includes('login')) 
                    && btn.offsetParent !== null && !btn.disabled) {
                    console.log('Clicking login button:', text || id);
                    btn.click();
                    return true;
                }
            }
            
            return false;
        """)
        
        if js_clicked:
            print("[SUCCESS] Login clicked immediately via JavaScript")
            login_success = True
    except Exception as e:
        print(f"[WARNING] JavaScript click failed: {e}")
    
    # Method 2: Direct element click if JS failed - with specific selectors
    if not login_success:
        try:
            # Try very specific login selectors first
            specific_selectors = [
                "button#signin_btn",
                "//button[text()='Sign In']",
                "//button[text()='sign in']", 
                "//button[contains(@class, 'login')]",
                "//input[@type='submit']"
            ]
            
            login_btn, _ = wait_for_element_clickable(driver, specific_selectors, 1)
            
            if login_btn:
                # Double check it's not an interview button
                button_text = login_btn.text.strip().lower()
                if 'interview' not in button_text and 'premium' not in button_text:
                    login_btn.click()
                    print(f"[SUCCESS] Login clicked via element: {button_text}")
                    login_success = True
                else:
                    print(f"[WARNING] Skipped wrong button: {button_text}")
        except Exception as e:
            print(f"[WARNING] Element click failed: {e}")
    
    # Method 3: Enter key as final fallback
    if not login_success:
        try:
            from selenium.webdriver.common.keys import Keys
            password_field.send_keys(Keys.RETURN)
            print("[SUCCESS] Login submitted via Enter key")
            login_success = True
        except Exception as e:
            print(f"[WARNING] Enter key failed: {e}")
    
    if not login_success:
        print("[ERROR] All login methods failed")
        raise Exception("Could not click login button")
    
    # Wait for login to process
    time.sleep(3)
    
    # Check if login succeeded, reload as fallback if still on login page
    current_url = driver.current_url.lower()
    print(f"[DEBUG] Current URL after login: {current_url}")
    
    if "login" in current_url:
        print("[FALLBACK] Still on login page - reloading...")
        driver.refresh()
        time.sleep(3)
        current_url = driver.current_url.lower()
        print(f"[DEBUG] URL after refresh: {current_url}")
        
        if "login" in current_url:
            page_content = driver.page_source.lower()
            if not any(indicator in page_content for indicator in ["problemset", "problems", "dashboard"]):
                print("[ERROR] Login verification failed - no dashboard indicators found")
                raise Exception("Login failed - check credentials")
    
    print(f"[SUCCESS] Login successful - current URL: {current_url}")
    
    # Store credentials if not already stored
    try:
        if stored_username is None or username != stored_username or password != stored_password:
            encrypt_credentials(username, password)
    except Exception as e:
        print(f"[WARNING] Could not store credentials: {e}")

def find_daily_challenge_url(driver):
    """Find and extract today's daily challenge URL - original logic with better loading"""
    print("[DAILY] Finding today's daily challenge...")
    
    try:
        # Use direct fallback approach as primary (faster)
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Try constructing today's daily challenge URL directly
        print(f"[PRIMARY] Using direct daily challenge URL for {today}...")
        
        # Go directly to problems page to find today's challenge - WITH BETTER LOADING
        print(f"[PRIMARY] Checking problems page for today's challenge...")
        try:
            driver.get("https://leetcode.com/problems/")
            
            # Better page loading - wait for page to be ready
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(3)  # Wait for dynamic content
            print("[SUCCESS] Problems page loaded")
            
        except Exception as e:
            print(f"[WARNING] Problems page failed to load: {e}")
            # Try alternative approach
            driver.get("https://leetcode.com/problemset/all/")
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(3)
            print("[FALLBACK] Using problemset page instead")
        
        # Look for today's daily challenge on problems page - ORIGINAL LOGIC
        daily_problem_url = driver.execute_script(f"""
            // Look for daily challenge indicators
            var dailySelectors = [
                'a[href*="envType=daily-question"][href*="{today}"]',
                'a[href*="daily"][href*="/problems/"]',
                '.daily-question a[href*="/problems/"]',
                '[class*="daily"] a[href*="/problems/"]'
            ];
            
            for (var i = 0; i < dailySelectors.length; i++) {{
                var elements = document.querySelectorAll(dailySelectors[i]);
                for (var j = 0; j < elements.length; j++) {{
                    var link = elements[j];
                    if (link.href && link.href.includes('/problems/')) {{
                        return link.href;
                    }}
                }}
            }}
            
            // If not found, get first non-premium problem
            var problemLinks = document.querySelectorAll('a[href*="/problems/"]:not([href*="premium"])');
            if (problemLinks.length > 0) {{
                return problemLinks[0].href;
            }}
            
            return null;
        """)
        
        if daily_problem_url:
            print(f"[SUCCESS] Found daily challenge: {daily_problem_url}")
            return daily_problem_url
        
        # JavaScript fallback approach - ORIGINAL LOGIC WITH BETTER LOADING
        try:
            driver.get("https://leetcode.com/")
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(3)  # Wait for dynamic content
            print("[SUCCESS] Main page loaded")
        except Exception as e:
            print(f"[ERROR] Main page failed to load: {e}")
            # Last resort fallback
            return "https://leetcode.com/problems/valid-sudoku/"
        
        daily_url = driver.execute_script("""
            console.log('[JS] Searching for daily challenge...');
            
            // Method 1: Direct daily challenge selectors
            var dailySelectors = [
                'a[href*="/problems/"][class*="daily"]',
                'a[href*="/problems/"][data-cy*="daily"]',
                '.daily-challenge a[href*="/problems/"]',
                'div[class*="daily"] a[href*="/problems/"]',
                '[class*="today"] a[href*="/problems/"]'
            ];
            
            for (var i = 0; i < dailySelectors.length; i++) {
                try {
                    var elements = document.querySelectorAll(dailySelectors[i]);
                    for (var j = 0; j < elements.length; j++) {
                        var link = elements[j];
                        if (link.href && link.href.includes('/problems/')) {
                            console.log('[JS] Found daily via selector:', dailySelectors[i]);
                            return link.href;
                        }
                    }
                } catch (e) {
                    console.warn('[JS] Daily selector failed:', dailySelectors[i]);
                }
            }
            
            // Method 2: Context-based search
            var problemLinks = Array.from(document.querySelectorAll('a[href*="/problems/"]'));
            
            for (var k = 0; k < problemLinks.length; k++) {
                var link = problemLinks[k];
                var parentElement = link.parentElement;
                
                // Check parent elements for daily context
                var checkParent = parentElement;
                var maxDepth = 4;
                
                while (checkParent && maxDepth > 0) {
                    var parentText = (checkParent.textContent || '').toLowerCase();
                    var parentClass = (checkParent.className || '').toLowerCase();
                    var parentId = (checkParent.id || '').toLowerCase();
                    
                    if (parentText.includes('daily') || parentText.includes('today') ||
                        parentClass.includes('daily') || parentId.includes('daily')) {
                        console.log('[JS] Found daily challenge via context:', link.href);
                        return link.href;
                    }
                    
                    checkParent = checkParent.parentElement;
                    maxDepth--;
                }
            }
            
            console.log('[JS] No daily challenge found on main page');
            return null;
        """)
        
        if daily_url:
            print(f"[SUCCESS] Found daily challenge: {daily_url}")
            return daily_url
        
        # Fallback: Try direct daily challenge page - ORIGINAL LOGIC
        print("[INFO] Trying fallback daily challenge URL...")
        fallback_url = "https://leetcode.com/problems/"
        driver.get(fallback_url)
        WebDriverWait(driver, 15).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(3)
        
        # Get first available problem as fallback
        first_problem = driver.execute_script("""
            var problemLinks = document.querySelectorAll('a[href*="/problems/"]:not([href*="premium"])');
            for (var i = 0; i < problemLinks.length; i++) {
                var link = problemLinks[i];
                if (link.href && !link.href.includes('premium')) {
                    return link.href;
                }
            }
            return 'https://leetcode.com/problems/two-sum/';
        """)
        
        print(f"[FALLBACK] Using problem: {first_problem}")
        return first_problem
        
    except Exception as e:
        print(f"[ERROR] Daily challenge detection failed: {e}")
        return "https://leetcode.com/problems/two-sum/"

def extract_problem_statement(driver):
    """Extract problem statement from current page"""
    print("[EXTRACT] Getting problem statement...")
    
    try:
        # Wait for problem content to load
        wait_for_dynamic_content(driver, silent=True)
        
        problem_data = driver.execute_script("""
            var statement = '';
            var title = '';
            
            // Get problem title
            var titleElements = document.querySelectorAll('h1, [class*="title"], .question-title');
            for (var i = 0; i < titleElements.length; i++) {
                var text = titleElements[i].textContent.trim();
                if (text && text.length > 0) {
                    title = text;
                    break;
                }
            }
            
            // Get problem statement
            var contentSelectors = [
                '.content__u3I1',
                '.question-content',
                '[class*="content"]',
                '.description',
                'div[class*="question"]'
            ];
            
            for (var j = 0; j < contentSelectors.length; j++) {
                var elements = document.querySelectorAll(contentSelectors[j]);
                for (var k = 0; k < elements.length; k++) {
                    var text = elements[k].textContent.trim();
                    if (text && text.length > 100) {
                        statement = text;
                        break;
                    }
                }
                if (statement) break;
            }
            
            return {
                title: title,
                statement: statement,
                url: window.location.href
            };
        """)
        
        if problem_data and problem_data.get('title'):
            print(f"[SUCCESS] Extracted: {problem_data['title']}")
            return problem_data
        else:
            print("[WARNING] Could not extract problem statement")
            return {
                'title': 'Daily Challenge',
                'statement': 'Problem statement extraction failed',
                'url': driver.current_url
            }
            
    except Exception as e:
        print(f"[ERROR] Problem extraction failed: {e}")
        return {
            'title': 'Daily Challenge',
            'statement': 'Problem statement extraction failed',
            'url': driver.current_url
        }

def click_language_button(language_name):
    """Click on language button directly using PyAutoGUI locateOnScreen"""
    print(f"[PYAUTOGUI] Clicking {language_name} button...")
    
    try:
        if not PYAUTOGUI_AVAILABLE:
            print("[ERROR] PyAutoGUI not available")
            return False
        
        # Define search terms for different languages
        search_terms = {
            'cpp': ['C++', 'c++', 'CPP'],
            'python3': ['Python3', 'Python 3', 'python3'],
            'python': ['Python', 'python'],
            'java': ['Java', 'java'],
            'javascript': ['JavaScript', 'JS']
        }
        
        terms = search_terms.get(language_name.lower(), [language_name])
        
        # Try to locate and click each variation
        for term in terms:
            try:
                print(f"[DEBUG] Looking for '{term}' on screen...")
                # Try to find the text on screen
                location = pyautogui.locateOnScreen(term, confidence=0.8)
                if location:
                    center = pyautogui.center(location)
                    print(f"[SUCCESS] Found '{term}' at {center}, clicking...")
                    pyautogui.click(center)
                    return True
            except pyautogui.ImageNotFoundException:
                continue
            except Exception as e:
                print(f"[DEBUG] Search for '{term}' failed: {e}")
                continue
        
        print(f"[WARNING] {language_name} not found on screen")
        return False
        
    except Exception as e:
        print(f"[ERROR] PyAutoGUI click failed: {e}")
        return False

def set_language_to_python(driver):
    """Improved language selection with proper dropdown handling"""
    print("[LANG] Setting language to Python3...")
    
    try:
        # First, find and click the dropdown
        dropdown_clicked = driver.execute_script("""
            // Look for language dropdown buttons with better detection
            var candidates = [];
            var allElements = document.querySelectorAll('button, [role="combobox"], [class*="select"], [data-testid*="lang"]');
            
            for (var i = 0; i < allElements.length; i++) {
                var elem = allElements[i];
                if (elem.offsetParent !== null && !elem.disabled) {
                    var text = elem.textContent.trim().toLowerCase();
                    var className = elem.className.toLowerCase();
                    var dataAttrs = Array.from(elem.attributes).map(attr => attr.name + '=' + attr.value).join(' ').toLowerCase();
                    
                    // Score elements by likelihood of being language dropdown
                    var score = 0;
                    if (text.includes('c++') || text.includes('python') || text.includes('java')) score += 5;
                    if (text.includes('language') || className.includes('lang') || dataAttrs.includes('lang')) score += 3;
                    if (className.includes('select') || elem.tagName === 'SELECT') score += 2;
                    if (elem.getAttribute('role') === 'combobox') score += 4;
                    
                    if (score > 0) {
                        candidates.push({element: elem, score: score, text: text});
                    }
                }
            }
            
            // Sort by score and try best candidate
            candidates.sort((a, b) => b.score - a.score);
            
            if (candidates.length > 0) {
                var bestCandidate = candidates[0];
                console.log('Clicking language dropdown:', bestCandidate.text, 'Score:', bestCandidate.score);
                bestCandidate.element.click();
                return true;
            }
            
            return false;
        """)
        
        if not dropdown_clicked:
            print("[ERROR] No language dropdown found")
            return False
            
        print("[INFO] Dropdown clicked, waiting for options to appear...")
        
        # Wait for dropdown to fully open before looking for options
        time.sleep(0.8)  # Reduced from 2 seconds to 0.8 seconds
        
        # Now look for Python3 option with faster checking
        for attempt in range(5):  # Reduced attempts from 8 to 5
            time.sleep(0.4)  # Reduced from 1 second to 0.4 seconds
            
            found = driver.execute_script("""
                // Look more specifically for dropdown menus and options
                var dropdownSelectors = [
                    '[role="listbox"] [role="option"]',
                    '.ant-select-dropdown .ant-select-item',
                    '[class*="dropdown"] [class*="option"]',
                    '[class*="menu"] [class*="item"]',
                    'li, div[role="option"], [data-value]'
                ];
                
                for (var selector of dropdownSelectors) {
                    try {
                        var options = document.querySelectorAll(selector);
                        for (var option of options) {
                            if (option.offsetParent !== null) {
                                var text = (option.textContent || option.innerText || '').trim();
                                if (text === 'Python3' || text === 'Python 3' || text === 'python3') {
                                    console.log('Found Python3 option:', text, 'Selector:', selector);
                                    option.click();
                                    return true;
                                }
                            }
                        }
                    } catch (e) {
                        console.log('Selector failed:', selector, e);
                    }
                }
                
                // Fallback: look for any element with Python3 text
                var allElements = document.querySelectorAll('*');
                for (var elem of allElements) {
                    if (elem.offsetParent !== null && elem.children.length === 0) { // Leaf elements only
                        var text = (elem.textContent || '').trim();
                        if (text === 'Python3' || text === 'Python 3') {
                            console.log('Found Python3 via fallback:', text);
                            elem.click();
                            return true;
                        }
                    }
                }
                
                return false;
            """)
            
            if found:
                print(f"[SUCCESS] Python3 selected after {attempt + 1} attempts")
                time.sleep(0.3)  # Reduced from 1 second to 0.3 seconds
                return True
            
            print(f"[WAIT] Attempt {attempt + 1}/5 - Python3 not found yet...")
        
        print("[WARNING] Python3 not found after all attempts")
        return False
        
    except Exception as e:
        print(f"[ERROR] Language selection failed: {e}")
        return False

def set_language_javascript_fallback(driver):
    """JavaScript fallback for language selection"""
    try:
        success = driver.execute_script("""
            var buttons = document.querySelectorAll('button');
            for (var i = 0; i < buttons.length; i++) {
                var btn = buttons[i];
                if (btn.offsetParent !== null && !btn.disabled) {
                    var text = btn.textContent.trim().toLowerCase();
                    if (text.includes('python') || text.includes('language')) {
                        btn.click();
                        setTimeout(function() {
                            var allOptions = document.querySelectorAll('*');
                            for (var j = 0; j < allOptions.length; j++) {
                                var option = allOptions[j];
                                if (option.offsetParent !== null) {
                                    var optText = (option.textContent || option.innerText || '').trim();
                                    if (optText === 'Python3' || optText === 'Python 3' || optText === 'python3') {
                                        option.click();
                                        window.pythonSelected = true;
                                        window.selectedText = optText;
                                        return;
                                    }
                                    else if (optText === 'Python' || optText === 'python') {
                                        option.click();
                                        window.pythonSelected = true;
                                        window.selectedText = optText;
                                        return;
                                    }
                                }
                            }
                        }, 2000);
                        return true;
                    }
                }
            }
            return false;
        """)
        
        if success:
            time.sleep(3)
            result = driver.execute_script("return {selected: window.pythonSelected || false, selectedText: window.selectedText || null};")
            if result['selected']:
                print(f"[SUCCESS] {result['selectedText']} selected via JavaScript fallback")
                return True
        
        return False
    except:
        return False

def check_current_language(driver):
    """Check what language is currently selected with modern LeetCode detection"""
    try:
        current_lang = driver.execute_script("""
            // Modern LeetCode language detection
            function detectCurrentLanguage() {
                // Strategy 1: Look for active/selected language buttons
                const selectors = [
                    '[data-testid*="lang"] [aria-selected="true"]',
                    '[data-testid*="language"] [aria-selected="true"]',
                    'button[role="combobox"]',
                    'button[aria-expanded="true"]',
                    '.ant-select-selection-item',
                    '[class*="selected"][class*="lang"]',
                    '[class*="active"][class*="lang"]'
                ];
                
                for (const selector of selectors) {
                    const elements = document.querySelectorAll(selector);
                    for (const elem of elements) {
                        if (elem.offsetParent) {
                            const text = (elem.textContent || elem.innerText || '').trim();
                            if (/python|java|javascript|c\+\+|cpp|go|rust|swift/i.test(text)) {
                                console.log('Found language via selector:', selector, text);
                                return text;
                            }
                        }
                    }
                }
                
                // Strategy 2: Look for dropdown button text
                const dropdownSelectors = [
                    'button[role="combobox"]',
                    'button[class*="select"]',
                    '[data-testid*="lang"]',
                    '[aria-label*="Language"]'
                ];
                
                for (const selector of dropdownSelectors) {
                    const elements = document.querySelectorAll(selector);
                    for (const elem of elements) {
                        if (elem.offsetParent) {
                            const text = (elem.textContent || elem.innerText || '').trim();
                            if (/python|java|javascript|c\+\+|cpp|go|rust|swift/i.test(text) && text.length < 30) {
                                console.log('Found language via dropdown:', selector, text);
                                return text;
                            }
                        }
                    }
                }
                
                // Strategy 3: Scan for any element with Python text
                const allElements = document.querySelectorAll('*');
                for (const elem of allElements) {
                    if (elem.offsetParent && elem.children.length === 0) { // Leaf elements only
                        const text = (elem.textContent || '').trim();
                        if (/^(python3?|java|javascript|c\+\+|cpp|go|rust|swift)$/i.test(text)) {
                            console.log('Found language via text scan:', text);
                            return text;
                        }
                    }
                }
                
                return null;
            }
            
            return detectCurrentLanguage();
        """)
        return current_lang
    except Exception as e:
        print(f"[DEBUG] Language detection error: {e}")
        return None

def try_leetcode_specific_language(driver):
    """Try LeetCode-specific language selection patterns"""
    try:
        # Modern LeetCode uses specific patterns
        result = driver.execute_script("""
            // Look for modern LeetCode language selector patterns
            var selectors = [
                'button[data-key*="python"]',
                'div[data-value*="python"]', 
                'button[title*="Python"]',
                'div[class*="lang"] button',
                'button:contains("Python")',
                '.language-select button',
                '[data-dropdown-trigger] button'
            ];
            
            console.log('Trying LeetCode-specific selectors...');
            
            for (var i = 0; i < selectors.length; i++) {
                try {
                    var elements = document.querySelectorAll(selectors[i]);
                    console.log('Selector', selectors[i], 'found', elements.length, 'elements');
                    
                    for (var j = 0; j < elements.length; j++) {
                        var elem = elements[j];
                        if (elem.offsetParent !== null) {
                            var text = elem.textContent || elem.innerText || '';
                            console.log('Element text:', text);
                            
                            if (/python|java|c\\+\\+|javascript/i.test(text)) {
                                // Found a language element - click it
                                elem.click();
                                console.log('Clicked language element:', text);
                                
                                // Wait for dropdown
                                setTimeout(function() {
                                    // Look for Python3 option
                                    var options = document.querySelectorAll('*');
                                    for (var k = 0; k < options.length; k++) {
                                        var option = options[k];
                                        if (option.offsetParent !== null) {
                                            var optText = option.textContent || '';
                                            if (optText.trim() === 'Python3' || optText.trim() === 'Python 3') {
                                                option.click();
                                                console.log('Selected Python3');
                                                window.pythonSelected = true;
                                                return;
                                            }
                                        }
                                    }
                                }, 1000);
                                
                                return true;
                            }
                        }
                    }
                } catch (e) {
                    console.warn('Selector failed:', selectors[i], e);
                }
            }
            
            return false;
        """)
        
        if result:
            time.sleep(2)
            python_selected = driver.execute_script("return window.pythonSelected || false;")
            if python_selected:
                print("[SUCCESS] Python3 selected via LeetCode-specific selectors")
                return True
        
        return False
        
    except Exception as e:
        print(f"[WARNING] LeetCode-specific approach failed: {e}")
        return False

def try_dom_language_selection(driver):
    """Try comprehensive DOM scanning for language selector"""
    try:
        # Get all possible language-related elements
        result = driver.execute_script("""
            var foundElements = [];
            
            // Comprehensive selectors for language dropdowns
            var selectors = [
                'select[class*="lang"]',
                'div[class*="lang"]',
                'button[class*="lang"]',
                '[data-cy*="lang"]',
                '[data-testid*="lang"]',
                '[aria-label*="lang"]',
                'select option',
                '.ant-select',
                '.dropdown',
                '[role="combobox"]',
                '[aria-haspopup="listbox"]'
            ];
            
            // Search for elements
            for (var i = 0; i < selectors.length; i++) {
                try {
                    var elements = document.querySelectorAll(selectors[i]);
                    for (var j = 0; j < elements.length; j++) {
                        var elem = elements[j];
                        if (elem.offsetParent !== null) {
                            var text = elem.textContent || elem.innerText || '';
                            var value = elem.value || '';
                            
                            // Check if this looks like a language selector
                            if (/python|java|javascript|c\\+\\+/i.test(text + value)) {
                                foundElements.push({
                                    selector: selectors[i],
                                    text: text.trim(),
                                    value: value,
                                    tagName: elem.tagName,
                                    id: elem.id,
                                    className: elem.className,
                                    index: j
                                });
                            }
                        }
                    }
                } catch (e) {
                    console.warn('Selector failed:', selectors[i], e);
                }
            }
            
            return foundElements;
        """)
        
        if result:
            print(f"[LANG] Found {len(result)} potential language elements")
            for item in result:
                print(f"  - {item['tagName']} ({item['selector']}): {item['text'][:50]}")
        
        # Try to interact with found elements
        for item in result:
            try:
                if 'python' in item['text'].lower():
                    # Try to click this element
                    element = driver.find_elements(By.CSS_SELECTOR, item['selector'])[item['index']]
                    if element.is_displayed() and element.is_enabled():
                        element.click()
                        time.sleep(1)
                        
                        # Look for Python3 in dropdown
                        python3_found = driver.execute_script("""
                            var options = document.querySelectorAll('*');
                            for (var i = 0; i < options.length; i++) {
                                var elem = options[i];
                                if (elem.offsetParent !== null) {
                                    var text = elem.textContent || '';
                                    if (text.trim() === 'Python3' || text.trim() === 'Python 3') {
                                        elem.click();
                                        return true;
                                    }
                                }
                            }
                            return false;
                        """)
                        
                        if python3_found:
                            print("[SUCCESS] Python3 selected via DOM scanning")
                            return True
                            
            except Exception as e:
                continue
                
        return False
        
    except Exception as e:
        print(f"[WARNING] DOM scanning failed: {e}")
        return False

def try_keyboard_language_selection(driver):
    """Try keyboard shortcuts to change language"""
    try:
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.common.action_chains import ActionChains
        
        # Focus on the page first
        driver.find_element(By.TAG_NAME, 'body').click()
        
        # Common keyboard shortcuts for language selection
        shortcuts = [
            [Keys.ALT, 'l'],  # Alt+L
            [Keys.CONTROL, 'l'],  # Ctrl+L
            [Keys.F2],  # F2
            [Keys.TAB, Keys.TAB, Keys.TAB, Keys.ENTER]  # Tab navigation
        ]
        
        for shortcut in shortcuts:
            try:
                actions = ActionChains(driver)
                if len(shortcut) == 1:
                    actions.send_keys(shortcut[0])
                else:
                    actions.key_down(shortcut[0]).send_keys(shortcut[1]).key_up(shortcut[0])
                actions.perform()
                time.sleep(1)
                
                # Check if a dropdown appeared
                dropdown_appeared = driver.execute_script("""
                    var dropdowns = document.querySelectorAll('[role="listbox"], .dropdown-menu, .ant-select-dropdown');
                    for (var i = 0; i < dropdowns.length; i++) {
                        if (dropdowns[i].offsetParent !== null) {
                            return true;
                        }
                    }
                    return false;
                """)
                
                if dropdown_appeared:
                    # Try to find Python3
                    python_found = driver.execute_script("""
                        var elements = document.querySelectorAll('*');
                        for (var i = 0; i < elements.length; i++) {
                            var elem = elements[i];
                            if (elem.offsetParent !== null) {
                                var text = elem.textContent || '';
                                if (text.trim() === 'Python3' || text.trim() === 'Python 3') {
                                    elem.click();
                                    return true;
                                }
                            }
                        }
                        return false;
                    """)
                    
                    if python_found:
                        print("[SUCCESS] Python3 selected via keyboard shortcuts")
                        return True
                        
            except Exception:
                continue
                
        return False
        
    except Exception as e:
        print(f"[WARNING] Keyboard approach failed: {e}")
        return False

def try_enhanced_pyautogui_language(driver):
    """Enhanced PyAutoGUI with better screen region detection"""
    try:
        if not PYAUTOGUI_AVAILABLE:
            return False
            
        # Take screenshot and find code editor area
        screenshot = pyautogui.screenshot()
        width, height = screenshot.size
        
        # Focus on the top-right area where language selector usually is
        top_right_region = (width//2, 0, width//2, height//3)
        
        # Look for language-related text in specific region
        import pytesseract
        region_screenshot = screenshot.crop(top_right_region)
        
        # OCR on the region
        text_data = pytesseract.image_to_data(region_screenshot, output_type=pytesseract.Output.DICT)
        
        language_keywords = ['python', 'java', 'javascript', 'c++', 'language', 'lang']
        
        for i, text in enumerate(text_data['text']):
            text_lower = text.lower()
            if any(keyword in text_lower for keyword in language_keywords) and int(text_data['conf'][i]) > 60:
                # Calculate absolute coordinates
                x = top_right_region[0] + text_data['left'][i] + text_data['width'][i]//2
                y = top_right_region[1] + text_data['top'][i] + text_data['height'][i]//2
                
                # Click the language element
                pyautogui.click(x, y)
                time.sleep(2)
                
                # Look for Python3 option
                new_screenshot = pyautogui.screenshot()
                new_data = pytesseract.image_to_data(new_screenshot, output_type=pytesseract.Output.DICT)
                
                for j, option_text in enumerate(new_data['text']):
                    if 'python3' in option_text.lower() or 'python 3' in option_text.lower():
                        if int(new_data['conf'][j]) > 60:
                            opt_x = new_data['left'][j] + new_data['width'][j]//2
                            opt_y = new_data['top'][j] + new_data['height'][j]//2
                            pyautogui.click(opt_x, opt_y)
                            print("[SUCCESS] Python3 selected via enhanced PyAutoGUI")
                            return True
                            
                break
                
        return False
        
    except Exception as e:
        print(f"[WARNING] Enhanced PyAutoGUI failed: {e}")
        return False

def try_javascript_language_selection(driver):
    """Advanced JavaScript injection for language selection"""
    try:
        result = driver.execute_script("""
            // Advanced language detection and selection
            function findAndSelectPython() {
                // Step 1: Find all clickable elements
                var allElements = document.querySelectorAll('*');
                var languageElements = [];
                
                for (var i = 0; i < allElements.length; i++) {
                    var elem = allElements[i];
                    if (elem.offsetParent === null) continue;
                    
                    var text = elem.textContent || elem.innerText || '';
                    var computedStyle = window.getComputedStyle(elem);
                    
                    // Look for language indicators
                    if (/python|java|javascript|c\\+\\+/i.test(text) && 
                        computedStyle.cursor === 'pointer' || 
                        elem.tagName === 'BUTTON' || 
                        elem.tagName === 'SELECT' ||
                        elem.getAttribute('role') === 'button') {
                        
                        languageElements.push({
                            element: elem,
                            text: text.trim(),
                            priority: text.toLowerCase().includes('python') ? 1 : 2
                        });
                    }
                }
                
                // Sort by priority and try clicking
                languageElements.sort((a, b) => a.priority - b.priority);
                
                for (var j = 0; j < languageElements.length; j++) {
                    try {
                        var elem = languageElements[j].element;
                        
                        // Simulate click events
                        var clickEvent = new MouseEvent('click', {
                            view: window,
                            bubbles: true,
                            cancelable: true
                        });
                        elem.dispatchEvent(clickEvent);
                        
                        // Wait a bit for dropdown
                        setTimeout(function() {
                            // Look for Python3 option
                            var allOptions = document.querySelectorAll('*');
                            for (var k = 0; k < allOptions.length; k++) {
                                var option = allOptions[k];
                                if (option.offsetParent !== null) {
                                    var optText = option.textContent || '';
                                    if (optText.trim() === 'Python3' || optText.trim() === 'Python 3') {
                                        var optClickEvent = new MouseEvent('click', {
                                            view: window,
                                            bubbles: true,
                                            cancelable: true
                                        });
                                        option.dispatchEvent(optClickEvent);
                                        window.pythonSelected = true;
                                        return;
                                    }
                                }
                            }
                        }, 1000);
                        
                        return true;
                        
                    } catch (e) {
                        continue;
                    }
                }
                
                return false;
            }
            
            return findAndSelectPython();
        """)
        
        if result:
            time.sleep(2)
            python_selected = driver.execute_script("return window.pythonSelected || false;")
            if python_selected:
                print("[SUCCESS] Python3 selected via JavaScript injection")
                return True
                
        return False
        
    except Exception as e:
        print(f"[WARNING] JavaScript injection failed: {e}")
        return False

def try_action_chains_language(driver):
    """Use ActionChains to simulate user interaction"""
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.common.by import By
        
        # Find elements that might be language selectors
        potential_selectors = [
            "button",
            "select", 
            "[role='button']",
            "[role='combobox']",
            ".dropdown-toggle",
            ".select-trigger"
        ]
        
        for selector in potential_selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for element in elements:
                try:
                    if element.is_displayed() and element.is_enabled():
                        text = element.text.strip()
                        if any(lang in text.lower() for lang in ['python', 'java', 'javascript']):
                            
                            # Use ActionChains for more human-like interaction
                            actions = ActionChains(driver)
                            actions.move_to_element(element)
                            actions.pause(0.5)
                            actions.click(element)
                            actions.perform()
                            
                            time.sleep(1)
                            
                            # Look for Python3 option
                            python_options = driver.find_elements(By.XPATH, 
                                "//*[contains(text(), 'Python3') or contains(text(), 'Python 3') or text()='Python']")
                            
                            for option in python_options:
                                if option.is_displayed() and option.is_enabled():
                                    if 'python3' in option.text.lower() or option.text.strip() == 'Python 3':
                                        actions = ActionChains(driver)
                                        actions.move_to_element(option)
                                        actions.pause(0.3)
                                        actions.click(option)
                                        actions.perform()
                                        print("[SUCCESS] Python3 selected via ActionChains")
                                        return True
                            
                except Exception:
                    continue
                    
        return False
        
    except Exception as e:
        print(f"[WARNING] ActionChains approach failed: {e}")
        return False

def pyautogui_set_language_python_simple(driver):
    """Simple PyAutoGUI - search for C++ button and select 4th option (Python3)"""
    try:
        if not PYAUTOGUI_AVAILABLE:
            return False
            
        print("[LANG] Searching for C++ dropdown button...")
        
        # Ensure browser window is maximized and focused
        try:
            driver.maximize_window()
            driver.switch_to.window(driver.current_window_handle)
            
            # Bring window to front using JavaScript
            driver.execute_script("window.focus();")
            time.sleep(2)
            
            # Additional focus attempt
            pyautogui.click(driver.get_window_position()['x'] + 100, driver.get_window_position()['y'] + 100)
            time.sleep(1)
            
            print("[LANG] Browser window maximized and focused")
        except Exception as e:
            print(f"[WARNING] Failed to focus browser window: {e}")
        
        # Get screen dimensions
        screen_width, screen_height = pyautogui.size()
        print(f"[LANG] Screen size: {screen_width}x{screen_height}")
        
        # Use exact coordinates provided by user: C++ button at (60, 23) relative to browser content
        try:
            # Get browser window position to calculate absolute coordinates
            browser_pos = driver.get_window_position()
            browser_size = driver.get_window_size()
            
            # Calculate absolute screen coordinates
            # The coordinates (60, 23) are relative to the browser content area
            # Need to add browser window position + chrome toolbar height
            toolbar_height = 80  # Approximate height of Chrome toolbar/address bar
            
            absolute_x = browser_pos['x'] + 60
            absolute_y = browser_pos['y'] + toolbar_height + 23
            
            print(f"[LANG] Browser position: ({browser_pos['x']}, {browser_pos['y']})")
            print(f"[LANG] Browser size: {browser_size['width']}x{browser_size['height']}")
            print(f"[LANG] Calculated absolute coordinates: ({absolute_x}, {absolute_y})")
            
            # Click the C++ dropdown button
            print(f"[LANG] Clicking C++ button at absolute position ({absolute_x}, {absolute_y})")
            pyautogui.click(absolute_x, absolute_y)
            time.sleep(2)  # Wait for dropdown to appear
            
            # Select Python3 (4th option down from the C++ button)
            python3_positions = [
                (absolute_x, absolute_y + 120),  # 30px * 4 = 120px down
                (absolute_x, absolute_y + 140),  # 35px * 4 = 140px down  
                (absolute_x, absolute_y + 160),  # 40px * 4 = 160px down
                (absolute_x, absolute_y + 180),  # 45px * 4 = 180px down
                (absolute_x, absolute_y + 200),  # 50px * 4 = 200px down
            ]
            
            print(f"[LANG] Selecting Python3 (4th option) from dropdown...")
            for j, (py_x, py_y) in enumerate(python3_positions):
                print(f"[LANG] Clicking Python3 attempt {j+1} at ({py_x}, {py_y})")
                pyautogui.click(py_x, py_y)
                time.sleep(0.8)
            
            # Also try keyboard navigation as backup
            try:
                print("[LANG] Trying keyboard navigation backup...")
                pyautogui.click(absolute_x, absolute_y)  # Click dropdown again
                time.sleep(1)
                # Press down arrow 3 times to reach 4th option (Python3)
                pyautogui.press('down')
                pyautogui.press('down') 
                pyautogui.press('down')
                pyautogui.press('enter')
                time.sleep(0.5)
                print("[LANG] Keyboard navigation completed")
            except Exception as e:
                print(f"[WARNING] Keyboard navigation failed: {e}")
            
            print("[SUCCESS] Language selection completed using calculated absolute coordinates")
            return True
                    
        except Exception as e:
            print(f"[ERROR] Screenshot search failed: {e}")
            return False
        
    except Exception as e:
        print(f"[WARNING] Simple PyAutoGUI failed: {e}")
        return False

def try_pyautogui_without_tesseract(driver):
    """PyAutoGUI language selection without OCR - using visual patterns"""
    try:
        if not PYAUTOGUI_AVAILABLE:
            return False
            
        print("[LANG] Using PyAutoGUI without Tesseract...")
        
        # Take screenshot
        screenshot = pyautogui.screenshot()
        width, height = screenshot.size
        
        # Define common language button colors (LeetCode typically uses)
        # Gray buttons, blue/green highlights, white text on dark backgrounds
        target_colors = [
            (107, 114, 126),  # Gray button
            (59, 130, 246),   # Blue highlight  
            (34, 197, 94),    # Green button
            (71, 85, 105),    # Dark gray
            (148, 163, 184),  # Light gray
        ]
        
        # Search in the top area where language selectors are usually located
        search_regions = [
            (width//2, 0, width//2, height//4),      # Top-right quarter
            (width//3, 0, width//3, height//4),      # Top-middle third  
            (0, height//8, width, height//4),        # Top strip across full width
        ]
        
        clicks_tried = []
        
        for region in search_regions:
            print(f"[LANG] Scanning region: {region}")
            
            x_start, y_start, region_width, region_height = region
            x_end = x_start + region_width
            y_end = y_start + region_height
            
            # Sample every 20 pixels to find clickable elements
            for y in range(y_start, min(y_end, height), 20):
                for x in range(x_start, min(x_end, width), 20):
                    try:
                        pixel = screenshot.getpixel((x, y))
                        
                        # Check if pixel matches target colors (with tolerance)
                        for target_color in target_colors:
                            if all(abs(pixel[i] - target_color[i]) < 30 for i in range(3)):
                                
                                # Check if we haven't tried this area before
                                area_key = (x//50, y//50)  # Group nearby clicks
                                if area_key not in clicks_tried:
                                    clicks_tried.append(area_key)
                                    
                                    print(f"[LANG] Trying click at ({x}, {y}) - color match: {pixel}")
                                    
                                    # Click and wait
                                    pyautogui.click(x, y)
                                    time.sleep(2)
                                    
                                    # Check if dropdown appeared by looking for more UI elements
                                    new_screenshot = pyautogui.screenshot()
                                    
                                    # Look for dropdown colors (typically white/light backgrounds)
                                    dropdown_colors = [(255, 255, 255), (248, 250, 252), (241, 245, 249)]
                                    
                                    # Search area below the click for dropdown
                                    search_below_y_start = max(0, y - 50)
                                    search_below_y_end = min(height, y + 200)
                                    
                                    dropdown_found = False
                                    for check_y in range(search_below_y_start, search_below_y_end, 10):
                                        for check_x in range(max(0, x-100), min(width, x+100), 10):
                                            try:
                                                check_pixel = new_screenshot.getpixel((check_x, check_y))
                                                for dropdown_color in dropdown_colors:
                                                    if all(abs(check_pixel[i] - dropdown_color[i]) < 20 for i in range(3)):
                                                        dropdown_found = True
                                                        break
                                                if dropdown_found:
                                                    break
                                            except:
                                                continue
                                        if dropdown_found:
                                            break
                                    
                                    if dropdown_found:
                                        print(f"[LANG] Dropdown detected, searching for Python option...")
                                        
                                        # Look for Python option by clicking likely areas
                                        python_areas = [
                                            (x-50, y+30), (x, y+30), (x+50, y+30),     # Below original click
                                            (x-50, y+50), (x, y+50), (x+50, y+50),     # Further below
                                            (x-50, y+70), (x, y+70), (x+50, y+70),     # Even further below
                                        ]
                                        
                                        for py_x, py_y in python_areas:
                                            if 0 <= py_x < width and 0 <= py_y < height:
                                                try:
                                                    pyautogui.click(py_x, py_y)
                                                    time.sleep(1)
                                                    print(f"[LANG] Clicked potential Python option at ({py_x}, {py_y})")
                                                except:
                                                    continue
                                        
                                        # Assume success if we got this far
                                        print("[SUCCESS] Python language selection attempted via PyAutoGUI")
                                        return True
                                        
                                break
                        
                    except Exception:
                        continue
                        
        print("[LANG] PyAutoGUI visual search completed - no clear language selectors found")
        return False
        
    except Exception as e:
        print(f"[WARNING] PyAutoGUI without Tesseract failed: {e}")
        return False

def pyautogui_set_language_python():
    """Use PyAutoGUI to set language to Python"""
    try:
        # Try to find language dropdown
        screenshot = pyautogui.screenshot()
        
        # Look for common language texts
        language_texts = ["Python", "Java", "C++", "JavaScript"]
        
        for lang_text in language_texts:
            try:
                # Use pytesseract to find text location
                text_data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)
                
                for i, text in enumerate(text_data['text']):
                    if lang_text.lower() in text.lower() and int(text_data['conf'][i]) > 50:
                        x = text_data['left'][i] + text_data['width'][i]//2
                        y = text_data['top'][i] + text_data['height'][i]//2
                        
                        pyautogui.click(x, y)
                        time.sleep(2)
                        
                        # Look for Python3 option
                        new_screenshot = pyautogui.screenshot()
                        new_data = pytesseract.image_to_data(new_screenshot, output_type=pytesseract.Output.DICT)
                        
                        for j, option_text in enumerate(new_data['text']):
                            if 'python3' in option_text.lower() and int(new_data['conf'][j]) > 50:
                                opt_x = new_data['left'][j] + new_data['width'][j]//2
                                opt_y = new_data['top'][j] + new_data['height'][j]//2
                                pyautogui.click(opt_x, opt_y)
                                print("[SUCCESS] Python3 selected via PyAutoGUI")
                                return True
                        
                        break
                        
            except Exception:
                continue
                
        return False
        
    except Exception as e:
        print(f"[ERROR] PyAutoGUI language selection failed: {e}")
        return False

def input_solution_code(driver, code):
    """Input solution code into Monaco editor with multiple strategies"""
    print("[CODE] Inputting solution code...")
    
    if not code or len(code.strip()) < 10:
        raise Exception("Invalid solution code provided")
    
    # Clean the code - remove any potential problematic characters
    code = code.replace('\r\n', '\n').replace('\r', '\n')
    # Escape special characters for JavaScript
    code_escaped = code.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    
    try:
        # Verify Monaco editor exists
        monaco_editors = driver.find_elements(By.CSS_SELECTOR, ".monaco-editor")
        if not monaco_editors:
            raise Exception("Monaco editor not found")
        
        print("[SUCCESS] Monaco editor confirmed")
        time.sleep(2)
        
        # Method 1: Monaco API
        success = driver.execute_script("""
            try {
                if (window.monaco && window.monaco.editor) {
                    var editors = window.monaco.editor.getEditors();
                    if (editors && editors.length > 0) {
                        var editor = editors[0];
                        var model = editor.getModel();
                        if (model) {
                            model.setValue('');
                            setTimeout(() => {
                                try {
                                    model.setValue(arguments[0]);
                                    window.monacoSuccess = true;
                                } catch (e) {
                                    console.error('Monaco setValue failed:', e);
                                    window.monacoSuccess = false;
                                }
                            }, 500);
                            return true;
                        }
                    }
                }
            } catch (e) {
                console.error('Monaco API failed:', e);
            }
            return false;
        """, code)
        
        if success:
            time.sleep(1.5)  # Reduced from 4 seconds to 1.5 seconds
            try:
                monaco_success = driver.execute_script("return window.monacoSuccess || false;")
                if monaco_success:
                    print("[SUCCESS] Code set via Monaco API")
                    # Verify code was actually set
                    time.sleep(0.5)  # Reduced from 1 second to 0.5 seconds
                    current_code = driver.execute_script("""
                        try {
                            if (window.monaco && window.monaco.editor) {
                                var editors = window.monaco.editor.getEditors();
                                if (editors && editors.length > 0) {
                                    return editors[0].getValue();
                                }
                            }
                            return '';
                        } catch (e) {
                            return '';
                        }
                    """)
                    if current_code and len(current_code.strip()) > len(code.strip()) * 0.5:
                        return True
                    else:
                        print("[WARNING] Monaco API set but code verification failed")
            except Exception as e:
                print(f"[WARNING] Monaco verification failed: {e}")
        
        # Method 2: Textarea approach
        textareas = driver.find_elements(By.TAG_NAME, "textarea")
        for i, textarea in enumerate(textareas):
            try:
                if textarea.is_displayed() and textarea.is_enabled():
                    ActionChains(driver).move_to_element(textarea).click().perform()
                    time.sleep(0.5)
                    
                    textarea.send_keys(Keys.CONTROL + 'a')
                    time.sleep(0.2)
                    textarea.send_keys(Keys.DELETE)
                    time.sleep(0.5)
                    textarea.send_keys(code)
                    
                    # Verify
                    current_value = textarea.get_attribute('value') or ''
                    if len(current_value) > len(code) * 0.7:
                        print(f"[SUCCESS] Code set via textarea {i}")
                        return True
            except:
                continue
        
        # Method 3: PyAutoGUI fallback
        if PYAUTOGUI_AVAILABLE and CLIPBOARD_AVAILABLE:
            print("[CODE] Using PyAutoGUI fallback...")
            try:
                monaco_editor = driver.find_element(By.CSS_SELECTOR, ".monaco-editor")
                driver.execute_script("arguments[0].scrollIntoView();", monaco_editor)
                time.sleep(1)
                
                location = monaco_editor.location_once_scrolled_into_view
                size = monaco_editor.size
                
                center_x = location['x'] + size['width'] // 2
                center_y = location['y'] + size['height'] // 2
                
                # Multiple click attempts
                for click_attempt in range(3):
                    pyautogui.click(center_x, center_y)
                    time.sleep(0.5)
                
                pyautogui.hotkey('ctrl', 'a')
                time.sleep(1)
                pyautogui.press('delete')
                time.sleep(1)
                
                # Split code into smaller chunks to avoid clipboard issues
                max_chunk_size = 1000
                if len(code) > max_chunk_size:
                    for i in range(0, len(code), max_chunk_size):
                        chunk = code[i:i+max_chunk_size]
                        pyperclip.copy(chunk)
                        time.sleep(0.2)
                        pyautogui.hotkey('ctrl', 'v')
                        time.sleep(0.5)
                else:
                    pyperclip.copy(code)
                    time.sleep(0.5)
                    pyautogui.hotkey('ctrl', 'v')
                
                print("[SUCCESS] Code pasted via PyAutoGUI")
                return True
            except Exception as e:
                print(f"[ERROR] PyAutoGUI method failed: {e}")
        
        raise Exception("All code input methods failed")
        
    except Exception as e:
        print(f"[ERROR] Code input failed: {e}")
        return False

def submit_solution(driver):
    """Submit solution with improved validation and less aggressive clicking"""
    print("[SUBMIT] Submitting solution...")
    
    try:
        # Ensure page is ready
        wait_for_dynamic_content(driver, silent=True)
        time.sleep(0.3)  # Reduced from 1 second to 0.3 seconds
        
        # First, verify we're not already in a submission state
        already_submitting = driver.execute_script("""
            // Check for submission in progress indicators
            var submissionIndicators = [
                '[class*="loading"]', '[class*="submitting"]', '[class*="pending"]',
                '.spinner', '[data-testid*="loading"]'
            ];
            
            for (var selector of submissionIndicators) {
                var elements = document.querySelectorAll(selector);
                for (var elem of elements) {
                    if (elem.offsetParent !== null) {
                        return true;
                    }
                }
            }
            return false;
        """)
        
        if already_submitting:
            print("[INFO] Submission already in progress, skipping submit click")
            return True
        
        # Strategy 1: Look for submit buttons with scoring system
        submit_result = driver.execute_script("""
            var candidates = [];
            var buttons = document.querySelectorAll('button, input[type="submit"]');
            
            for (var btn of buttons) {
                if (btn.offsetParent !== null && !btn.disabled) {
                    var text = btn.textContent.trim().toLowerCase();
                    var className = btn.className.toLowerCase();
                    var score = 0;
                    
                    // Score based on text content
                    if (text === 'submit') score += 10;
                    if (text.includes('submit')) score += 5;
                    if (text.includes('run')) score += 2;
                    
                    // Score based on styling (green buttons are usually submit)
                    if (className.includes('green') || className.includes('primary')) score += 3;
                    
                    // Score based on attributes
                    if (btn.getAttribute('data-e2e-locator') && btn.getAttribute('data-e2e-locator').includes('submit')) score += 8;
                    if (btn.getAttribute('data-cy') && btn.getAttribute('data-cy').includes('submit')) score += 8;
                    
                    if (score > 0) {
                        candidates.push({element: btn, score: score, text: text});
                    }
                }
            }
            
            // Sort by score and click best candidate
            if (candidates.length > 0) {
                candidates.sort((a, b) => b.score - a.score);
                var best = candidates[0];
                console.log('Clicking submit button:', best.text, 'Score:', best.score);
                best.element.click();
                return {success: true, text: best.text, score: best.score};
            }
            
            return {success: false};
        """)
        
        if submit_result.get('success'):
            print(f"[SUCCESS] Submit clicked: '{submit_result.get('text')}' (score: {submit_result.get('score')})")
            print("[INFO] Waiting 5 seconds after submit click...")
            time.sleep(5)  # Wait 5 seconds after clicking submit
            return True
        
        print("[WARNING] No submit button found with standard methods")
        return False
        
    except Exception as e:
        print(f"[ERROR] Submit failed: {e}")
        return False

def pyautogui_submit_solution():
    """Use PyAutoGUI to find and click submit button"""
    try:
        screenshot = pyautogui.screenshot()
        
        # Look for "Submit" text
        text_data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)
        
        for i, text in enumerate(text_data['text']):
            if 'submit' in text.lower() and int(text_data['conf'][i]) > 50:
                x = text_data['left'][i] + text_data['width'][i]//2
                y = text_data['top'][i] + text_data['height'][i]//2
                
                pyautogui.click(x, y)
                print("[SUCCESS] Submit clicked via PyAutoGUI")
                return True
        
        # Fallback: Look for green button
        width, height = screenshot.size
        green_colors = [(34, 197, 94), (16, 185, 129)]
        
        for y in range(height//2, height, 20):
            for x in range(width//2, width, 20):
                pixel = screenshot.getpixel((x, y))
                for green in green_colors:
                    if all(abs(pixel[i] - green[i]) < 40 for i in range(3)):
                        pyautogui.click(x, y)
                        print("[SUCCESS] Green submit button clicked via PyAutoGUI")
                        return True
        
        return False
        
    except Exception as e:
        print(f"[ERROR] PyAutoGUI submit failed: {e}")
        return False

def wait_for_submission_result(driver, timeout=60):
    """Wait for submission result with enhanced accuracy"""
    print(f"[WAIT] Waiting for submission result (timeout: {timeout}s)...")
    
    start_time = time.time()
    last_detected = None
    
    while time.time() - start_time < timeout:
        try:
            # Enhanced result detection with better selectors
            result_found = driver.execute_script("""
                // Look for result containers more precisely
                var resultSelectors = [
                    '[data-e2e-locator*="submission-result"]',
                    '[class*="result"]',
                    '[class*="status"]',
                    '.submission-result',
                    '.result-state'
                ];
                
                var results = [];
                
                // Check specific result selectors first
                for (var i = 0; i < resultSelectors.length; i++) {
                    var elements = document.querySelectorAll(resultSelectors[i]);
                    for (var j = 0; j < elements.length; j++) {
                        var elem = elements[j];
                        if (elem.offsetParent !== null) {
                            var text = elem.textContent.trim();
                            if (text.length > 0 && text.length < 100) {
                                results.push({
                                    text: text,
                                    selector: resultSelectors[i],
                                    confidence: 'high'
                                });
                            }
                        }
                    }
                }
                
                // Fallback: Look for specific result text patterns
                var resultTexts = ['Accepted', 'Wrong Answer', 'Time Limit Exceeded', 'Runtime Error', 'Compilation Error'];
                for (var k = 0; k < resultTexts.length; k++) {
                    var xpath = "//*[text()='" + resultTexts[k] + "']";
                    var xpathResult = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                    if (xpathResult.singleNodeValue && xpathResult.singleNodeValue.offsetParent !== null) {
                        results.push({
                            text: resultTexts[k],
                            selector: 'xpath_exact',
                            confidence: 'highest'
                        });
                    }
                }
                
                // Return the highest confidence result
                if (results.length > 0) {
                    results.sort((a, b) => {
                        if (a.confidence === 'highest') return -1;
                        if (b.confidence === 'highest') return 1;
                        if (a.confidence === 'high') return -1;
                        if (b.confidence === 'high') return 1;
                        return 0;
                    });
                    return results[0];
                }
                
                return null;
            """)
            
            if result_found:
                result_text = result_found.get('text', '').strip()
                confidence = result_found.get('confidence', 'unknown')
                selector = result_found.get('selector', 'unknown')
                
                # Track what we're detecting
                if result_text != last_detected:
                    print(f"[RESULT] {result_text} (confidence: {confidence}, selector: {selector})")
                    last_detected = result_text
                
                # Precise categorization - only return definitive results
                result_lower = result_text.lower()
                if result_text == 'Accepted':  # Exact match for highest accuracy
                    print(f"[FINAL] Solution ACCEPTED!")
                    return {"status": "accepted", "message": "Solution accepted!", "confidence": confidence}
                elif result_text == 'Wrong Answer':
                    print(f"[FINAL] Wrong Answer detected")
                    return {"status": "wrong_answer", "message": "Wrong Answer", "confidence": confidence}
                elif 'time limit' in result_lower or result_text == 'Time Limit Exceeded':
                    print(f"[FINAL] Time Limit Exceeded detected")
                    return {"status": "timeout", "message": "Time Limit Exceeded", "confidence": confidence}
                elif 'runtime error' in result_lower or result_text == 'Runtime Error':
                    print(f"[FINAL] Runtime Error detected")
                    return {"status": "runtime_error", "message": "Runtime Error", "confidence": confidence}
                elif 'compilation error' in result_lower or result_text == 'Compilation Error':
                    print(f"[FINAL] Compilation Error detected")
                    return {"status": "compilation_error", "message": "Compilation Error", "confidence": confidence}
                elif 'submitted' in result_lower or 'processing' in result_lower:
                    # Don't return early for submission/processing messages - keep waiting
                    print(f"[INFO] Submission in progress: {result_text}")
                elif 'accepted' in result_lower:  # Fuzzy match as backup
                    print(f"[WARNING] Fuzzy 'accepted' match - verify manually: '{result_text}'")
                    return {"status": "accepted_fuzzy", "message": f"Possibly accepted: {result_text}", "confidence": "low"}
                else:
                    print(f"[DEBUG] Intermediate result: '{result_text}' (continuing to wait...)")
            
            # Progress indicator
            elapsed = int(time.time() - start_time)
            if elapsed % 10 == 0 and elapsed > 0:
                print(f"[WAIT] Still waiting... ({elapsed}/{timeout}s)")
            
            time.sleep(2)
            
        except Exception as e:
            print(f"[WARNING] Result check error: {e}")
            time.sleep(2)
    
    return {"status": "timeout", "message": f"No result within {timeout} seconds"}

def get_solution_simple(problem_url, problem_statement):
    """Get solution from n8n with simple single call"""
    print("[N8N] Getting solution with simple approach...")
    
    try:
        from utils.n8n_enhanced import get_code_from_n8n_simple
        
        print("[N8N] Calling simple n8n client...")
        
        code, is_safe, warnings, problem_title = get_code_from_n8n_simple(
            enable_validation=True,
            timeout_seconds=180,  # 3 minutes
            fallback_enabled=True
        )
        
        if code and len(code.strip()) > 30:
            print(f"[SUCCESS] Solution received: {len(code)} chars")
            for warning in warnings:
                print(f"[WARNING] {warning}")
            return code
        else:
            print("[ERROR] No valid code received from n8n")
            return None
            
    except Exception as e:
        print(f"[ERROR] N8N client failed: {e}")
        return None

def daily_challenge_automation(username=None, password=None, solution_code=None, user_id=None):
    """Main automation function for daily challenge with improved n8n integration"""
    logger = logging.getLogger(__name__)
    logger.info("[START] LeetCode Daily Challenge Automation")
    logger.info("=" * 50)
    logger.info(f"[DEBUG] Automation called with username: {username[:3]}***{username[-3:] if username else 'None'}")
    logger.info(f"[DEBUG] Solution code length: {len(solution_code) if solution_code else 0} chars")
    
    async def update_status(status, step, progress, message):
        """Update automation status"""
        if user_id:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    await session.post(f'http://localhost:8000/automation-status/{user_id}', 
                                     json={'status': status, 'step': step, 'progress': progress, 'message': message})
            except Exception as e:
                logger.error(f"Failed to update status: {e}")
    
    import asyncio
    
    def sync_update_status(status, step, progress, message):
        """Synchronous wrapper for status updates"""
        try:
            asyncio.run(update_status(status, step, progress, message))
        except Exception as e:
            logger.error(f"Failed to update status: {e}")
    
    # Initial status
    sync_update_status("starting", "initializing", 10, "Starting Chrome automation...")
    
    driver = None
    
    try:
        # Use the solution already provided from the new cache system
        print("[CACHE] Using solution from new SQLite cache system")
        cached_solution = {
            'solution_code': solution_code,
            'problem_statement': 'Daily Challenge - Solution from cache',
            'problem_url': 'https://leetcode.com/problemset/all/'
        }
        
        # Initialize driver
        sync_update_status("initializing", "launching_browser", 15, "🚀 Launching stealth Chrome browser...")
        driver = init_driver()
        sync_update_status("initializing", "browser_ready", 20, "✅ Chrome browser launched successfully")
        
        # Secure login
        sync_update_status("logging_in", "loading_login_page", 25, "🔐 Loading LeetCode login page...")
        secure_login(driver, username, password)
        sync_update_status("logging_in", "login_complete", 35, "✅ Successfully logged into LeetCode")
        
        # Find daily challenge
        sync_update_status("navigating", "finding_problem", 40, "🔍 Searching for today's daily challenge...")
        daily_url = find_daily_challenge_url(driver)
        sync_update_status("navigating", "navigating_to_problem", 45, "📍 Navigating to daily challenge...")
        driver.get(daily_url)
        sync_update_status("navigating", "problem_loaded", 50, "✅ Daily challenge page loaded")
        
        # Better page loading for problem page
        WebDriverWait(driver, 15).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(3)  # Wait for dynamic content
        print(f"[SUCCESS] Problem page loaded: {driver.current_url}")
        
        # Extract problem statement
        problem_data = extract_problem_statement(driver)
        problem_statement = problem_data.get('statement', '')
        
        # Use the solution code from the cache system (passed as parameter)
        if not solution_code:
            print("[ERROR] No solution code provided from cache system")
            return {
                "status": "error",
                "success": False,
                "message": "No solution available from cache system",
                "error": "solution_code parameter is None or empty"
            }
        
        print(f"[CACHE] Solution code length: {len(solution_code)} characters")
        
        # Wait for editor to load
        sync_update_status("preparing", "extracting_problem", 55, "📝 Extracting problem statement...")
        
        # Extract problem statement (add status here since it's a key step)
        problem_data = extract_problem_statement(driver)
        sync_update_status("preparing", "problem_extracted", 60, f"✅ Problem extracted: {problem_data.get('title', 'Daily Challenge')}")
        
        sync_update_status("preparing", "loading_editor", 65, "⚡ Loading Monaco code editor...")
        wait_for_dynamic_content(driver, silent=True)
        sync_update_status("preparing", "editor_ready", 70, "✅ Code editor loaded and ready")
        time.sleep(1.5)  # Reduced from 3 seconds to 1.5 seconds
        
        # Verify Monaco editor
        if not driver.find_elements(By.CSS_SELECTOR, ".monaco-editor"):
            return {
                "status": "editor_error", 
                "message": "Code editor not found - page may not have loaded correctly"
            }
        
        # Set language to Python3 (with retry)
        sync_update_status("preparing", "selecting_language", 72, "🐍 Setting language to Python3...")
        language_success = False
        for lang_attempt in range(2):
            print(f"[LANG] Language selection attempt {lang_attempt + 1}/2")
            if set_language_to_python(driver):
                language_success = True
                print("[SUCCESS] Python3 language selection confirmed")
                sync_update_status("preparing", "language_selected", 75, "✅ Python3 language selected")
                break
            print(f"[WARNING] Language selection attempt {lang_attempt + 1} failed, retrying...")
            time.sleep(1)  # Reduced from 3 seconds to 1 second
        
        if not language_success:
            print("[ERROR] Python3 selection failed - stopping automation")
            return {
                "status": "language_error",
                "message": "Could not select Python3 - automation stopped",
                "problem_url": daily_url
            }
        
        # Ensure language selection is complete before proceeding
        time.sleep(1)  # Reduced from 3 seconds to 1 second
        
        # Verify language is actually set to Python3
        current_lang = check_current_language(driver)
        if current_lang and 'python' in current_lang.lower():
            print(f"[SUCCESS] Language confirmed as: {current_lang}")
        else:
            print(f"[WARNING] Language may not be Python3: {current_lang}")
        
        # Input solution code (with retry and validation)
        sync_update_status("coding", "inputting_code", 78, "📝 Inputting solution code into editor...")
        code_input_success = False
        for code_attempt in range(2):
            print(f"[CODE] Code input attempt {code_attempt + 1}/2")
            if input_solution_code(driver, solution_code):
                # Verify code was actually input
                time.sleep(0.8)  # Reduced from 2 seconds to 0.8 seconds
                editor_content = driver.execute_script("""
                    try {
                        if (window.monaco && window.monaco.editor) {
                            var editors = window.monaco.editor.getEditors();
                            if (editors && editors.length > 0) {
                                return editors[0].getValue();
                            }
                        }
                        // Fallback to textarea
                        var textarea = document.querySelector('textarea');
                        if (textarea) {
                            return textarea.value;
                        }
                        return '';
                    } catch (e) {
                        return '';
                    }
                """)
                
                if editor_content and len(editor_content.strip()) > len(solution_code.strip()) * 0.5:
                    code_input_success = True
                    print("[SUCCESS] Code input verified in editor")
                    sync_update_status("coding", "code_input_verified", 82, "✅ Solution code successfully entered")
                    break
                else:
                    print(f"[WARNING] Code verification failed - editor content length: {len(editor_content)}")
            
            print(f"[WARNING] Code input attempt {code_attempt + 1} failed, retrying...")
            time.sleep(1)  # Reduced from 3 seconds to 1 second
        
        if not code_input_success:
            return {
                "status": "code_input_error",
                "message": "Failed to input solution code into editor",
                "problem_url": daily_url
            }
        
        # Wait before submission to ensure everything is ready
        print("[INFO] Waiting 1 second before submission to ensure readiness...")
        time.sleep(1)  # Reduced from 3 seconds to 1 second
        
        # Submit solution (only try once to prevent spam clicking)
        sync_update_status("submitting", "preparing_submit", 85, "🚀 Preparing to submit solution...")
        print("[SUBMIT] Attempting to submit solution...")
        sync_update_status("submitting", "clicking_submit", 88, "🖱️ Clicking submit button...")
        submit_success = submit_solution(driver)
        
        if not submit_success:
            print("[WARNING] First submit attempt failed, trying once more...")
            sync_update_status("submitting", "retrying_submit", 89, "🔄 Retrying submit...")
            time.sleep(0.5)  # Reduced from 2 seconds to 0.5 seconds
            submit_success = submit_solution(driver)
        
        if not submit_success:
            return {
                "status": "submit_error",
                "message": "Failed to submit solution after 2 attempts",
                "problem_url": daily_url
            }
        
        # Wait for result and ensure we get it before proceeding
        sync_update_status("processing", "submission_sent", 92, "📨 Solution submitted! Waiting for result...")
        print("[RESULT] Waiting for submission result...")
        sync_update_status("processing", "waiting_for_result", 95, "⏳ LeetCode is processing your solution...")
        result = wait_for_submission_result(driver, timeout=60)
        
        # Display result clearly
        result_status = result.get('status', 'unknown')
        result_message = result.get('message', 'No message')
        print(f"[RESULT] Final Result: {result_status} - {result_message}")
        
        # Cache successful solution
        if result.get('status') == 'accepted':
            cache_daily_solution(daily_url, problem_statement, solution_code)
            print("[SUCCESS] Solution accepted and cached!")
        elif result.get('status') == 'wrong_answer':
            print("[INFO] Wrong answer - solution not cached")
        elif result.get('status') == 'timeout':
            print("[INFO] Time limit exceeded - solution not cached")
        else:
            print(f"[INFO] Result: {result_status} - solution not cached")
        
        # Wait a moment to ensure result is fully processed
        print("[INFO] Submission complete, waiting 10 seconds for final result validation...")
        time.sleep(10)
        
        # Double-check the result before finishing
        final_check = wait_for_submission_result(driver, timeout=15)
        if final_check.get('status') != result.get('status'):
            print(f"[WARNING] Result changed! Initial: {result.get('status')} -> Final: {final_check.get('status')}")
            result = final_check  # Use the final result
        
        # Final status update
        result_status = result.get('status', 'unknown')
        if result_status == 'accepted':
            final_status = "completed"
            final_message = "🎉 Solution ACCEPTED! Daily challenge solved successfully!"
        elif result_status == 'wrong_answer':
            final_status = "failed"
            final_message = "❌ Wrong Answer - Solution needs improvement"
        elif result_status == 'runtime_error':
            final_status = "failed"
            final_message = "⚠️ Runtime Error - Code has execution issues"
        elif result_status == 'time_limit_exceeded':
            final_status = "failed"
            final_message = "⏰ Time Limit Exceeded - Solution too slow"
        else:
            final_status = "failed"
            final_message = f"❌ Submission failed: {result_status.replace('_', ' ')}"
            
        sync_update_status(final_status, "finished", 100, final_message)
        
        return {
            "status": "completed",
            "submission_result": result,
            "problem_url": daily_url,
            "problem_title": problem_data.get('title', 'Daily Challenge'),
            "solution_cached": result.get('status') == 'accepted',
            "timestamp": datetime.now(IST_TIMEZONE).isoformat()
        }
        
    except Exception as e:
        error_msg = str(e)
        logger = logging.getLogger(__name__)
        logger.error(f"[ERROR] Automation failed: {error_msg}")
        logger.error(f"[ERROR] Exception type: {type(e).__name__}")
        
        return {
            "status": "error",
            "message": error_msg,
            "timestamp": datetime.now(IST_TIMEZONE).isoformat(),
            "problem_url": daily_url if 'daily_url' in locals() else None
        }
        
    finally:
        if driver:
            try:
                print("[INFO] Closing browser...")
                cleanup_driver()
                print("[INFO] Browser closed")
            except:
                pass

def get_automation_status():
    """Get current automation status and cache info"""
    cached_solution = get_cached_daily_solution()
    last_refresh = get_last_refresh_time()
    
    return {
        "cache_status": {
            "has_cached_solution": bool(cached_solution),
            "last_refresh": last_refresh.isoformat() if last_refresh else None,
            "refresh_needed": should_refresh_cache(),
            "today_ist": get_ist_today().isoformat()
        },
        "system_status": {
            "redis_available": REDIS_AVAILABLE,
            "encryption_available": ENCRYPTION_AVAILABLE,
            "pyautogui_available": PYAUTOGUI_AVAILABLE,
            "clipboard_available": CLIPBOARD_AVAILABLE
        }
    }

def force_cache_refresh():
    """Force refresh of daily challenge cache"""
    print("[CACHE] Forcing cache refresh...")
    
    # Clear existing cache
    if os.path.exists(DAILY_CACHE_FILE):
        os.remove(DAILY_CACHE_FILE)
    
    redis_client = get_redis_client()
    if redis_client:
        try:
            pattern = f"leetcode_daily:*"
            keys = redis_client.keys(pattern)
            if keys:
                redis_client.delete(*keys)
                print("[CACHE] Redis cache cleared")
        except Exception as e:
            print(f"[WARNING] Redis clear failed: {e}")
    
    print("[CACHE] Cache refresh forced - next run will fetch new daily challenge")

if __name__ == "__main__":
    print("LeetCode Daily Challenge Core Automation")
    print("=" * 50)
    
    # Check system status
    status = get_automation_status()
    print("\nSystem Status:")
    for component, available in status["system_status"].items():
        print(f"- {component}: {'Available' if available else 'Not Available'}")
    
    print(f"\nCache Status:")
    cache_info = status["cache_status"]
    print(f"- Today (IST): {cache_info['today_ist']}")
    print(f"- Has cached solution: {cache_info['has_cached_solution']}")
    print(f"- Last refresh: {cache_info['last_refresh'] or 'Never'}")
    print(f"- Refresh needed: {cache_info['refresh_needed']}")
    
    # Get credentials if not stored
    username, password = decrypt_credentials()
    if not username or not password:
        print("\nCredentials required:")
        username = input("LeetCode username: ")
        password = input("LeetCode password: ")
    else:
        print("\nUsing stored encrypted credentials")
    
    # Option to provide solution code
    print("\nSolution code (optional - leave empty for external generation):")
    print("Enter code or press Enter to skip:")
    
    solution_lines = []
    try:
        while True:
            line = input()
            if not line.strip():
                break
            solution_lines.append(line)
    except:
        pass
    
    solution_code = '\n'.join(solution_lines) if solution_lines else None
    
    # Run automation
    print("\nStarting daily challenge automation...")
    result = daily_challenge_automation(username, password, solution_code)
    
    print(f"\nAutomation Result:")
    print(f"Status: {result.get('status')}")
    print(f"Message: {result.get('message', 'No message')}")
    
    if result.get('submission_result'):
        sub_result = result['submission_result']
        print(f"Submission: {sub_result.get('status')} - {sub_result.get('message')}")
    
    input("\nPress Enter to exit...")