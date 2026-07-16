// Form validation and submission
const loginForm = document.getElementById('loginForm');
const submitBtn = document.getElementById('submitBtn');
const loader = document.getElementById('loader');

// Form validation rules
const validationRules = {
    username: {
        required: true,
        minLength: 3,
        maxLength: 100,
        message: 'Username must be between 3-100 characters'
    },
    password: {
        required: true,
        minLength: 1,
        maxLength: 100,
        message: 'Password is required'
    }
};

// Initialize parallax effect
function initParallax() {
    const orbs = document.querySelectorAll('.floating-orb');
    const shapes = document.querySelectorAll('.geometric-shape');
    
    window.addEventListener('scroll', () => {
        const scrolled = window.pageYOffset;
        const rate = scrolled * -0.5;
        
        orbs.forEach((orb, index) => {
            const speed = (index + 1) * 0.3;
            orb.style.transform = `translateY(${rate * speed}px)`;
        });
        
        shapes.forEach((shape, index) => {
            const speed = (index + 1) * 0.2;
            shape.style.transform = `translateY(${rate * speed}px) rotate(${45 + scrolled * 0.1}deg)`;
        });
    });
}

// Form validation
function validateField(fieldName, value) {
    const rules = validationRules[fieldName];
    const errorElement = document.getElementById(`${fieldName}-error`);
    
    if (!rules) return true;
    
    if (rules.required && (!value || value.trim() === '')) {
        showError(errorElement, 'This field is required');
        return false;
    }
    
    if (rules.minLength && value.length < rules.minLength) {
        showError(errorElement, rules.message);
        return false;
    }
    
    if (rules.maxLength && value.length > rules.maxLength) {
        showError(errorElement, rules.message);
        return false;
    }
    
    // Additional password validation
    if (fieldName === 'password') {
        if (!/(?=.*[a-zA-Z])(?=.*\d)/.test(value)) {
            showError(errorElement, 'Password must contain both letters and numbers');
            return false;
        }
        
        const commonPasswords = ['password', '12345678', 'qwerty123'];
        if (commonPasswords.includes(value.toLowerCase())) {
            showError(errorElement, 'Password is too common');
            return false;
        }
    }
    
    clearError(errorElement);
    return true;
}

function showError(element, message) {
    element.textContent = message;
    element.style.display = 'block';
}

function clearError(element) {
    element.textContent = '';
    element.style.display = 'none';
}

// Real-time validation
document.addEventListener('DOMContentLoaded', () => {
    Object.keys(validationRules).forEach(fieldName => {
        const field = document.getElementById(fieldName);
        if (field) {
            field.addEventListener('blur', () => {
                validateField(fieldName, field.value);
            });
            
            field.addEventListener('input', () => {
                if (field.value.length > 0) {
                    validateField(fieldName, field.value);
                }
            });
        }
    });
});

// Progress tracking system
class ProgressTracker {
    constructor() {
        this.currentStep = 0;
        this.totalSteps = 6;
        this.progressBar = null;
        this.progressText = null;
        this.progressContainer = null;
        this.steps = [
            { text: 'Validating credentials...', duration: 500 },
            { text: 'Connecting to backend...', duration: 1000 },
            { text: 'Fetching daily challenge...', duration: 2000 },
            { text: 'Processing solution...', duration: 1500 },
            { text: 'Launching Chrome automation...', duration: 2000 },
            { text: 'Submitting to LeetCode...', duration: 5000 }
        ];
    }
    
    showProgress() {
        // Create progress overlay
        this.progressContainer = document.createElement('div');
        this.progressContainer.className = 'progress-overlay';
        this.progressContainer.innerHTML = `
            <div class="progress-modal">
                <div class="progress-header">
                    <span class="material-icons">auto_fix_high</span>
                    <h3>Solving Daily Challenge</h3>
                </div>
                <div class="progress-content">
                    <div class="progress-bar-container">
                        <div class="progress-bar" id="progressBar">
                            <div class="progress-fill"></div>
                        </div>
                        <div class="progress-percentage">0%</div>
                    </div>
                    <div class="progress-text" id="progressText">Initializing...</div>
                    <div class="progress-steps">
                        ${this.steps.map((step, index) => `
                            <div class="progress-step" data-step="${index}">
                                <span class="step-indicator">${index + 1}</span>
                                <span class="step-text">${step.text}</span>
                                <span class="step-status material-icons">schedule</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(this.progressContainer);
        this.progressBar = document.querySelector('.progress-fill');
        this.progressText = document.getElementById('progressText');
        
        // Trigger entrance animation
        setTimeout(() => this.progressContainer.classList.add('active'), 100);
    }
    
    async updateProgress(stepIndex, customText = null) {
        if (stepIndex >= this.steps.length) return;
        
        this.currentStep = stepIndex;
        const progress = ((stepIndex + 1) / this.totalSteps) * 100;
        const step = this.steps[stepIndex];
        
        // Update progress bar
        this.progressBar.style.width = `${progress}%`;
        document.querySelector('.progress-percentage').textContent = `${Math.round(progress)}%`;
        
        // Update step text
        this.progressText.textContent = customText || step.text;
        
        // Update step indicators
        const stepElements = document.querySelectorAll('.progress-step');
        stepElements.forEach((el, index) => {
            const statusIcon = el.querySelector('.step-status');
            if (index < stepIndex) {
                el.classList.add('completed');
                statusIcon.textContent = 'check_circle';
                statusIcon.style.color = '#4caf50';
            } else if (index === stepIndex) {
                el.classList.add('active');
                el.classList.remove('completed');
                statusIcon.textContent = 'radio_button_checked';
                statusIcon.style.color = '#00d2d3';
                statusIcon.classList.remove('spin');
            } else {
                el.classList.remove('active', 'completed');
                statusIcon.textContent = 'schedule';
                statusIcon.style.color = '#666';
                statusIcon.classList.remove('spin');
            }
        });
        
        // Wait for step duration only for initial steps, not automation steps
        if (!customText && stepIndex < 4) {
            await new Promise(resolve => setTimeout(resolve, Math.min(step.duration, 1000)));
        }
    }
    
    async complete(success = true, message = 'Completed successfully!') {
        if (success) {
            // Complete all steps
            await this.updateProgress(this.totalSteps - 1);
            
            // Mark all as completed
            const stepElements = document.querySelectorAll('.progress-step');
            stepElements.forEach((el) => {
                el.classList.add('completed');
                el.classList.remove('active');
                const statusIcon = el.querySelector('.step-status');
                statusIcon.textContent = 'check_circle';
                statusIcon.style.color = '#4caf50';
                statusIcon.classList.remove('spin');
            });
            
            this.progressBar.style.width = '100%';
            document.querySelector('.progress-percentage').textContent = '100%';
            this.progressText.textContent = message;
            
            // Success animation
            setTimeout(() => {
                this.progressContainer.classList.add('success');
            }, 500);
            
        } else {
            this.progressContainer.classList.add('error');
            this.progressText.textContent = message;
        }
        
        // Auto close after 3 seconds on success, 5 seconds on error
        setTimeout(() => this.close(), success ? 3000 : 5000);
    }
    
    async pollAutomationStatus(userId) {
        let attempts = 0;
        const maxAttempts = 60; // 5 minutes max
        
        return new Promise((resolve) => {
            const poll = async () => {
                try {
                    const response = await fetch(`http://localhost:8000/automation-status/${userId}`);
                    const status = await response.json();
                    
                    // Update progress based on automation status
                    if (status.status !== 'not_started') {
                        // Update progress bar to reflect actual automation progress
                        const actualProgress = Math.max(67, status.progress); // Start from step 4 (67%)
                        this.progressBar.style.width = `${actualProgress}%`;
                        document.querySelector('.progress-percentage').textContent = `${actualProgress}%`;
                        this.progressText.textContent = status.message || 'Chrome automation in progress...';
                        
                        // Mark automation mode visually
                        const progressModal = document.querySelector('.progress-modal');
                        if (progressModal && !progressModal.classList.contains('automation-mode')) {
                            progressModal.classList.add('automation-mode');
                            // Add a visual indicator for automation
                            const header = progressModal.querySelector('.progress-header h3');
                            if (header && !header.innerHTML.includes('🤖')) {
                                header.innerHTML = '🤖 Chrome Automation Active - ' + header.innerHTML;
                            }
                        }
                        
                        // Update steps based on automation phase - don't await to prevent blocking
                        if (status.step === 'launching_browser' || status.step === 'browser_ready' || 
                            status.step === 'loading_login_page' || status.step === 'login_complete' ||
                            status.step === 'finding_problem' || status.step === 'problem_loaded' || 
                            status.step === 'extracting_problem' || status.step === 'problem_extracted' ||
                            status.step === 'loading_editor' || status.step === 'editor_ready' || 
                            status.step === 'selecting_language' || status.step === 'language_selected' || 
                            status.step === 'inputting_code' || status.step === 'code_input_verified') {
                            // Chrome automation phase - update step 4 message only
                            this.progressText.textContent = status.message;
                        } else if (status.step === 'preparing_submit' || status.step === 'clicking_submit' || 
                                 status.step === 'retrying_submit' || status.step === 'submission_sent' || 
                                 status.step === 'waiting_for_result') {
                            // Submission phase - move to step 5
                            if (this.currentStep < 5) {
                                this.updateProgress(5, status.message);
                            } else {
                                this.progressText.textContent = status.message;
                            }
                        }
                    }
                    
                    // Check if completed or failed
                    if (status.status === 'completed' || status.status === 'failed') {
                        const success = status.status === 'completed';
                        await this.complete(success, status.message || 'Automation completed');
                        resolve(success);
                        return;
                    }
                    
                    attempts++;
                    if (attempts >= maxAttempts) {
                        await this.complete(false, 'Automation timed out');
                        resolve(false);
                        return;
                    }
                    
                    // Continue polling
                    setTimeout(poll, 5000); // Poll every 5 seconds
                    
                } catch (error) {
                    console.error('Error polling automation status:', error);
                    attempts++;
                    if (attempts >= maxAttempts) {
                        await this.complete(false, 'Failed to track automation progress');
                        resolve(false);
                        return;
                    }
                    setTimeout(poll, 5000);
                }
            };
            
            // Start polling after initial delay
            setTimeout(poll, 2000);
        });
    }

    close() {
        if (this.progressContainer) {
            this.progressContainer.classList.add('closing');
            setTimeout(() => {
                this.progressContainer.remove();
            }, 300);
        }
    }
}

// Form submission with enhanced progress tracking
loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formData = new FormData(loginForm);
    const data = Object.fromEntries(formData.entries());
    
    // Validate all fields
    let isValid = true;
    Object.keys(validationRules).forEach(fieldName => {
        if (!validateField(fieldName, data[fieldName])) {
            isValid = false;
        }
    });
    
    if (!isValid) {
        showToast('Please fix the validation errors', 'error');
        return;
    }
    
    // Initialize progress tracker
    const progressTracker = new ProgressTracker();
    progressTracker.showProgress();
    
    try {
        // Step 1: Validate credentials
        await progressTracker.updateProgress(0);
        
        // Step 2: Connect to backend
        await progressTracker.updateProgress(1);
        
        // Generate unique user ID
        const userId = `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        
        // Step 3: Fetch daily challenge (this is the main API call)
        await progressTracker.updateProgress(2, 'Connecting to LeetCode solver...');
        
        const response = await fetch('http://localhost:8000/solve-daily', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                username: data.username,
                password: data.password,
                user_id: userId,
                force_refresh: false
            })
        });
        
        const result = await response.json();
        
        // Step 4: Process solution
        await progressTracker.updateProgress(3, 'Processing LeetCode solution...');
        
        if (result.status === 'success') {
            // Complete step 4 and move to automation
            await progressTracker.updateProgress(3, 'Solution processed successfully!');
            
            // Move to step 5 (Chrome automation)
            await progressTracker.updateProgress(4, 'Starting Chrome automation...');
            
            console.log('Solution fetched from backend, starting automation polling...');
            
            // Start polling for automation status instead of fake completion
            const automationSuccess = await progressTracker.pollAutomationStatus(userId);
            
            // Show success message and solution info only after real submission result
            if (automationSuccess) {
                setTimeout(() => {
                    showSuccessModal(result);
                }, 1000);
            } else {
                // Show failure if automation failed
                showToast('Automation failed to complete successfully', 'error');
            }
            
            // Removed debug logging to prevent any raw data display
            
        } else {
            await progressTracker.complete(false, result.message || 'Submission failed');
            showToast(result.message || 'Login failed', 'error');
        }
        
    } catch (error) {
        console.error('Login error:', error);
        
        let errorMessage = 'An unexpected error occurred';
        if (error.message.includes('Failed to fetch')) {
            errorMessage = 'Unable to connect to server. Please check if the backend is running.';
        } else if (error.message.includes('NetworkError')) {
            errorMessage = 'Network error. Please check your internet connection.';
        } else {
            errorMessage = 'Login failed. Please check your credentials and try again.';
        }
        
        await progressTracker.complete(false, errorMessage);
        showToast(errorMessage, 'error');
    }
});

// Loading state management
function setLoading(loading) {
    if (loading) {
        submitBtn.disabled = true;
        loader.style.display = 'block';
        document.querySelector('.btn-text').style.opacity = '0.7';
    } else {
        submitBtn.disabled = false;
        loader.style.display = 'none';
        document.querySelector('.btn-text').style.opacity = '1';
    }
}

// Password visibility toggle
function togglePassword(fieldId) {
    const field = document.getElementById(fieldId);
    const button = field.nextElementSibling;
    const icon = button.querySelector('.material-icons');
    
    if (field.type === 'password') {
        field.type = 'text';
        icon.textContent = 'visibility_off';
    } else {
        field.type = 'password';
        icon.textContent = 'visibility';
    }
}

// Health Check Modal
let healthModal;
let healthData = null;

function openHealthCheck() {
    healthModal = document.getElementById('healthModal');
    healthModal.classList.add('active');
    fetchHealthData();
}

function closeHealthCheck() {
    if (healthModal) {
        healthModal.classList.remove('active');
    }
}

function refreshHealthData() {
    fetchHealthData();
}

async function fetchHealthData() {
    const healthContent = document.getElementById('healthContent');
    
    // Show loading
    healthContent.innerHTML = `
        <div class="loading-container">
            <div class="loader"></div>
            <p>Checking System Health...</p>
        </div>
    `;
    
    try {
        const response = await fetch('http://localhost:8000/frontend/health');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        healthData = await response.json();
        renderHealthData();
        showToast('System health data updated successfully', 'success');
        
    } catch (error) {
        console.error('Failed to fetch health data:', error);
        healthContent.innerHTML = `
            <div style="text-align: center; padding: 2rem; color: #ff6b6b;">
                <span class="material-icons" style="font-size: 3rem; margin-bottom: 1rem;">error</span>
                <h3>Failed to fetch health data</h3>
                <p>Please check if the backend server is running on port 8000.</p>
                <p style="font-size: 0.9rem; color: #b0bec5; margin-top: 1rem;">Error: ${error.message}</p>
            </div>
        `;
        showToast('Failed to fetch system health data', 'error');
    }
}

function renderHealthData() {
    if (!healthData) return;
    
    const healthContent = document.getElementById('healthContent');
    
    const overallStatus = healthData.overall_status || 'unknown';
    const healthScore = Math.round((healthData.health_score || 0) * 100);
    const components = healthData.components || {};
    
    healthContent.innerHTML = `
        <!-- Overall Status -->
        <div style="background: rgba(255, 255, 255, 0.05); padding: 1.5rem; border-radius: 12px; margin-bottom: 2rem;">
            <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem;">
                ${getStatusIcon(overallStatus)}
                <h3>Overall System Status: ${overallStatus.toUpperCase()}</h3>
            </div>
            <div style="background: rgba(255, 255, 255, 0.1); border-radius: 8px; overflow: hidden; margin-bottom: 0.5rem;">
                <div style="background: linear-gradient(135deg, #00d2d3, #009fa1); height: 8px; width: ${healthScore}%; transition: width 0.5s ease;"></div>
            </div>
            <small style="color: #b0bec5;">Health Score: ${healthScore}% | Response Time: ${healthData.response_time_ms?.toFixed(1)}ms</small>
        </div>
        
        <!-- Component Status Grid -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1.5rem;">
            ${renderComponentCard('Redis Cache', 'storage', components.redis?.status, [
                { label: 'Status', value: components.redis?.status || 'Unknown' },
                { label: 'Hit Ratio', value: components.redis?.hit_ratio || 'N/A' },
                { label: 'Memory Usage', value: components.redis?.memory_used || 'N/A' },
                { label: 'Version', value: components.redis?.version || 'N/A' }
            ])}
            
            ${renderComponentCard('Authentication', 'security', components.authentication?.status, [
                { label: 'Rate Limiter', value: components.authentication?.status === 'active' ? 'Active' : 'Inactive' },
                { label: 'Max Attempts', value: components.authentication?.max_attempts || 'N/A' },
                { label: 'Lockout Time', value: `${components.authentication?.lockout_minutes || 0} min` }
            ])}
            
            ${renderComponentCard('N8N Workflow', 'cloud_queue', components.n8n_workflow?.status, [
                { label: 'Trigger Accessible', value: components.n8n_workflow?.trigger_accessible ? 'Yes' : 'No' },
                { label: 'Fetch Accessible', value: components.n8n_workflow?.fetch_accessible ? 'Yes' : 'No' },
                { label: 'Health Score', value: components.n8n_workflow?.health_score || '0%' }
            ])}
            
            ${renderComponentCard('System Info', 'people', 'healthy', [
                { label: 'Active Users', value: components.system?.active_users || 0 },
                { label: 'Max Users', value: components.system?.max_users || 100 },
                { label: 'Uptime', value: formatUptime(components.system?.uptime) }
            ])}
        </div>
        
        ${healthData.recommendations?.length > 0 ? `
            <div style="margin-top: 2rem; padding: 1rem; background: rgba(33, 150, 243, 0.1); border-radius: 8px; border-left: 4px solid #2196f3;">
                <h4 style="margin-bottom: 0.5rem;">System Recommendations:</h4>
                <ul style="margin: 0; padding-left: 1rem;">
                    ${healthData.recommendations.map(rec => `<li>${rec}</li>`).join('')}
                </ul>
            </div>
        ` : ''}
        
        <div style="margin-top: 2rem; text-align: center; font-size: 0.9rem; color: #b0bec5;">
            Last updated: ${new Date(healthData.timestamp).toLocaleString()}
        </div>
    `;
}

function renderComponentCard(title, icon, status, items) {
    return `
        <div style="background: rgba(255, 255, 255, 0.03); padding: 1.5rem; border-radius: 12px;">
            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem;">
                <span class="material-icons" style="color: #00d2d3;">${icon}</span>
                <h4>${title}</h4>
            </div>
            <div style="margin-bottom: 1rem;">
                ${getStatusChip(status)}
            </div>
            <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                ${items.map(item => `
                    <div style="display: flex; justify-content: space-between; font-size: 0.9rem;">
                        <span style="color: #b0bec5;">${item.label}</span>
                        <span>${item.value}</span>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

function getStatusIcon(status) {
    const iconMap = {
        'healthy': '<span class="material-icons" style="color: #4caf50;">check_circle</span>',
        'degraded': '<span class="material-icons" style="color: #ff9800;">warning</span>',
        'unhealthy': '<span class="material-icons" style="color: #f44336;">error</span>',
        'connected': '<span class="material-icons" style="color: #4caf50;">check_circle</span>',
        'disconnected': '<span class="material-icons" style="color: #f44336;">error</span>',
        'success': '<span class="material-icons" style="color: #4caf50;">check_circle</span>'
    };
    return iconMap[status] || '<span class="material-icons" style="color: #9e9e9e;">help</span>';
}

function getStatusChip(status) {
    const colorMap = {
        'healthy': '#4caf50',
        'connected': '#4caf50',
        'success': '#4caf50',
        'degraded': '#ff9800',
        'warning': '#ff9800',
        'unhealthy': '#f44336',
        'error': '#f44336',
        'disconnected': '#f44336'
    };
    
    const color = colorMap[status] || '#9e9e9e';
    return `<span style="background: ${color}; color: white; padding: 0.25rem 0.75rem; border-radius: 12px; font-size: 0.8rem; font-weight: 500;">${status}</span>`;
}

function formatUptime(uptimeSeconds) {
    if (!uptimeSeconds || uptimeSeconds === 0) return 'N/A';
    
    const days = Math.floor(uptimeSeconds / 86400);
    const hours = Math.floor((uptimeSeconds % 86400) / 3600);
    const minutes = Math.floor((uptimeSeconds % 3600) / 60);
    
    if (days > 0) {
        return `${days}d ${hours}h ${minutes}m`;
    } else if (hours > 0) {
        return `${hours}h ${minutes}m`;
    } else if (minutes > 0) {
        return `${minutes}m`;
    } else {
        return `${Math.floor(uptimeSeconds)}s`;
    }
}

// Helper function to escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Success modal for displaying solution results
function showSuccessModal(result) {
    // Ensure result is clean and safe
    if (typeof result !== 'object' || !result) {
        console.error('Invalid result passed to showSuccessModal:', result);
        showToast('Error displaying solution', 'error');
        return;
    }
    
    const modal = document.createElement('div');
    modal.className = 'success-modal-overlay';
    
    // Extract and sanitize data
    const solution = result.solution || {};
    const responseTime = Math.round(result.response_time_ms || 0);
    const source = result.source === 'redis_cache' ? 'Cache' : 'Fresh Fetch';
    
    // Safely extract solution properties
    const codeLength = solution.code ? solution.code.length : 0;
    const problemTitle = solution.problem_title || 'Daily Challenge';
    const qualityScore = Math.round((solution.quality_score || 0) * 100);
    const warningCount = solution.warnings ? solution.warnings.length : 0;
    const isSafe = solution.is_safe ? 'Safe' : 'Needs Review';
    const codePreview = solution.code ? escapeHtml(solution.code.substring(0, 200)) : '';
    const showEllipsis = solution.code && solution.code.length > 200;
    
    modal.innerHTML = `
        <div class="success-modal">
            <div class="success-header">
                <div class="success-icon">
                    <span class="material-icons">celebration</span>
                </div>
                <h2>🎉 Daily Challenge Solved!</h2>
                <p>Your LeetCode solution has been successfully retrieved</p>
            </div>
            
            <div class="success-content">
                <div class="success-stats">
                    <div class="stat-item">
                        <span class="material-icons">speed</span>
                        <div>
                            <span class="stat-value">${responseTime}ms</span>
                            <span class="stat-label">Response Time</span>
                        </div>
                    </div>
                    <div class="stat-item">
                        <span class="material-icons">source</span>
                        <div>
                            <span class="stat-value">${source}</span>
                            <span class="stat-label">Source</span>
                        </div>
                    </div>
                    <div class="stat-item">
                        <span class="material-icons">security</span>
                        <div>
                            <span class="stat-value">${isSafe}</span>
                            <span class="stat-label">Code Safety</span>
                        </div>
                    </div>
                    <div class="stat-item">
                        <span class="material-icons">grade</span>
                        <div>
                            <span class="stat-value">${qualityScore}%</span>
                            <span class="stat-label">Quality Score</span>
                        </div>
                    </div>
                </div>
                
                <div class="solution-info">
                    <h3>
                        <span class="material-icons">code</span>
                        Solution Details
                    </h3>
                    <div class="solution-meta">
                        <p><strong>Problem:</strong> ${problemTitle}</p>
                        <p><strong>Code Length:</strong> ${codeLength} characters</p>
                        ${warningCount > 0 ? 
                            `<p><strong>Warnings:</strong> ${warningCount} item(s)</p>` : 
                            '<p><strong>Status:</strong> No warnings detected</p>'
                        }
                    </div>
                    
                    ${codePreview ? `
                        <div class="code-preview">
                            <div class="code-header">
                                <span>Solution Code Preview</span>
                                <button onclick="copySolutionCode()" class="copy-btn">
                                    <span class="material-icons">content_copy</span>
                                    Copy Code
                                </button>
                            </div>
                            <pre><code>${codePreview}${showEllipsis ? '...' : ''}</code></pre>
                        </div>
                    ` : ''}
                </div>
            </div>
            
            <div class="success-actions">
                <button class="btn-secondary" onclick="closeSuccessModal()">
                    <span class="material-icons">close</span>
                    Close
                </button>
                <button class="btn-primary" onclick="downloadSolution()">
                    <span class="material-icons">download</span>
                    Download Solution
                </button>
                <button class="btn-primary" onclick="openLeetCodeProblem()">
                    <span class="material-icons">open_in_new</span>
                    Open LeetCode
                </button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    setTimeout(() => modal.classList.add('active'), 100);
    
    // Store for later reference
    window.currentSuccessModal = modal;
    window.currentSolution = solution;
}

function closeSuccessModal() {
    const modal = window.currentSuccessModal;
    if (modal) {
        modal.classList.add('closing');
        setTimeout(() => modal.remove(), 300);
        window.currentSuccessModal = null;
    }
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('Code copied to clipboard!', 'success');
    }).catch(() => {
        showToast('Failed to copy code', 'error');
    });
}

function downloadSolution() {
    try {
        const solution = window.currentSolution;
        if (!solution) {
            showToast('No solution available to download', 'error');
            return;
        }
        
        const content = `// LeetCode Daily Challenge Solution
// Generated: ${new Date().toISOString()}
// Problem: ${solution.problem_title || 'Daily Challenge'}
// Quality Score: ${Math.round((solution.quality_score || 0) * 100)}%
// Safe: ${solution.is_safe ? 'Yes' : 'No'}

${solution.code || '// No code available'}
`;
        
        const blob = new Blob([content], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `leetcode-daily-${new Date().toISOString().split('T')[0]}.js`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        showToast('Solution downloaded successfully!', 'success');
    } catch (error) {
        showToast('Failed to download solution', 'error');
    }
}

function copySolutionCode() {
    const solution = window.currentSolution;
    if (!solution || !solution.code) {
        showToast('No code available to copy', 'error');
        return;
    }
    
    copyToClipboard(solution.code);
}

function openLeetCodeProblem() {
    // Try to get the problem slug from current solution
    const solution = window.currentSolution;
    let leetcodeUrl = 'https://leetcode.com/problems/';
    
    if (solution && solution.problem_slug && solution.problem_slug !== 'daily-challenge') {
        // Use the specific problem slug if available
        leetcodeUrl += solution.problem_slug;
    } else {
        // Fallback to daily challenge page
        leetcodeUrl = 'https://leetcode.com/explore/featured/card/top-interview-questions-easy/';
    }
    
    window.open(leetcodeUrl, '_blank');
    showToast('Opening LeetCode in new tab', 'info');
}

// Close modals on escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        if (window.currentSuccessModal) {
            closeSuccessModal();
        }
    }
});

// Toast notifications
function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    
    const iconMap = {
        success: 'check_circle',
        error: 'error',
        warning: 'warning',
        info: 'info'
    };
    
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="material-icons">${iconMap[type] || 'info'}</span>
        <span>${message}</span>
    `;
    
    container.appendChild(toast);
    
    // Auto remove after duration
    setTimeout(() => {
        toast.remove();
    }, duration);
    
    // Click to dismiss
    toast.addEventListener('click', () => {
        toast.remove();
    });
}

// Modal event handlers
document.addEventListener('click', (e) => {
    if (e.target === healthModal) {
        closeHealthCheck();
    }
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && healthModal?.classList.contains('active')) {
        closeHealthCheck();
    }
});

// Scroll animations with Intersection Observer
function initScrollAnimations() {
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -10% 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const element = entry.target;
                const delay = element.dataset.delay || 0;
                
                setTimeout(() => {
                    element.classList.add('animate-in');
                }, delay);
                
                // Unobserve after animation to prevent re-triggering
                observer.unobserve(element);
            }
        });
    }, observerOptions);

    // Add animation classes and observe elements
    const animatedElements = [
        '.main-title',
        '.subtitle',
        '.feature-card',
        '.login-card',
        '.badges .badge',
        '.floating-orb',
        '.geometric-shape'
    ];

    animatedElements.forEach(selector => {
        const elements = document.querySelectorAll(selector);
        elements.forEach((element, index) => {
            // Add base animation class
            element.classList.add('scroll-animate');
            
            // Add staggered delay for multiple elements
            if (elements.length > 1) {
                element.dataset.delay = index * 150; // 150ms stagger
            }
            
            // Observe element
            observer.observe(element);
        });
    });
}

// Enhanced parallax with smooth scroll
function initEnhancedParallax() {
    const orbs = document.querySelectorAll('.floating-orb');
    const shapes = document.querySelectorAll('.geometric-shape');
    const features = document.querySelectorAll('.feature-card');
    const loginCard = document.querySelector('.login-card');
    
    let ticking = false;
    
    function updateParallax() {
        const scrolled = window.pageYOffset;
        const windowHeight = window.innerHeight;
        const rate = scrolled * -0.3;
        
        // Animate orbs with different speeds
        orbs.forEach((orb, index) => {
            const speed = (index + 1) * 0.2;
            const yOffset = rate * speed;
            const rotation = scrolled * 0.05;
            orb.style.transform = `translateY(${yOffset}px) scale(${1 + scrolled * 0.0001})`;
        });
        
        // Animate shapes with rotation
        shapes.forEach((shape, index) => {
            const speed = (index + 1) * 0.15;
            const yOffset = rate * speed;
            const rotation = 45 + scrolled * 0.1;
            shape.style.transform = `translateY(${yOffset}px) rotate(${rotation}deg)`;
        });
        
        // Subtle card animations
        if (features.length > 0) {
            features.forEach((card, index) => {
                const cardTop = card.getBoundingClientRect().top;
                const cardInView = cardTop < windowHeight && cardTop > -card.offsetHeight;
                
                if (cardInView) {
                    const parallaxStrength = (windowHeight - cardTop) / windowHeight;
                    const translateY = parallaxStrength * 10;
                    card.style.transform = `translateY(${translateY}px)`;
                }
            });
        }
        
        // Login card subtle movement
        if (loginCard) {
            const cardTop = loginCard.getBoundingClientRect().top;
            if (cardTop < windowHeight && cardTop > -loginCard.offsetHeight) {
                const parallaxStrength = (windowHeight - cardTop) / windowHeight;
                const translateY = parallaxStrength * 5;
                loginCard.style.transform = `translateY(${translateY}px)`;
            }
        }
        
        ticking = false;
    }
    
    function requestTick() {
        if (!ticking) {
            requestAnimationFrame(updateParallax);
            ticking = true;
        }
    }
    
    window.addEventListener('scroll', requestTick);
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initEnhancedParallax();
    initScrollAnimations();
    
    // Add some floating particles
    createFloatingParticles();
});

function createFloatingParticles() {
    const background = document.querySelector('.parallax-background');
    
    for (let i = 0; i < 6; i++) {
        const particle = document.createElement('div');
        particle.style.cssText = `
            position: absolute;
            width: 4px;
            height: 4px;
            border-radius: 50%;
            background: ${i % 2 === 0 ? 'rgba(0, 210, 211, 0.6)' : 'rgba(255, 167, 38, 0.6)'};
            top: ${Math.random() * 100}%;
            left: ${Math.random() * 100}%;
            animation: particleFloat ${3 + Math.random() * 2}s ease-in-out infinite;
            animation-delay: ${Math.random() * 2}s;
        `;
        background.appendChild(particle);
    }
}

// Add particle animation CSS
const style = document.createElement('style');
style.textContent = `
    @keyframes particleFloat {
        0%, 100% { transform: translateY(0) translateX(0); opacity: 0.3; }
        50% { transform: translateY(-30px) translateX(${Math.random() * 20 - 10}px); opacity: 0.8; }
    }
`;
document.head.appendChild(style);