# LEETCODE SOLVER APP

A production-ready automation tool that solves and submits LeetCode daily challenges with multi-user support, N8N workflow integration, and real-time progress tracking.

---

## 🚀 Features

### Core Functionality
- **Automated LeetCode Solving** – Logs into LeetCode, fetches the daily challenge, and submits AI-generated solutions via N8N workflows  
- **Multi-User Support** – Handles multiple concurrent users with isolated sessions and tracking  
- **Real-Time Progress** – WebSocket-powered live updates with progress bars and logs  
- **Anti-Detection** – Uses undetected ChromeDriver and stealth patches to bypass detection  

### Security & Performance
- **AES-256 Encryption** for credentials  
- **SQLite Caching** (hybrid memory + disk)  
- **JWT Authentication** with per-user session isolation  
- **Rate Limiting** to prevent abuse  

### User Experience
- **Static Frontend** with HTML, CSS, and JS  
- **Health Monitoring** via backend health checks and Redis stats  
- **Cross-Platform** – Works on Windows, macOS, and Linux  

---

## 📋 Prerequisites

### Backend
- **Python 3.11+**  
- **Redis** (running locally or remote instance)  
- **SQLite** (auto setup, no install needed)  
- **Chrome/Chromium** for Selenium automation  

### Frontend
- **Any modern browser**  

### External
- **N8N Workflow** for solution generation and validation  
- **LeetCode account** (user-provided)  

---

## 🏗️ Project Structure

LEETCODE-SOLVER-APP/
├── backend/
│ ├── auth.py # AES/JWT authentication
│ ├── cache.py # Redis + SQLite cache manager
│ ├── code_cache.py # Solution cache handler
│ ├── main.py # FastAPI entry point
│ ├── scheduler.py # Daily refresh scheduler
│ ├── user_manager.py # Multi-user session manager
│ ├── websocket.py # WebSocket updates
│ ├── utils/
│ │ ├── code_validator.py
│ │ ├── leetcode_submit.py
│ │ └── n8n_enhanced.py
│ ├── requirements.txt # Backend dependencies
│ └── .env.example # Environment template
│
├── configs/
│ └── settings.yaml # Application config
│
├── demo_video/ # Demo video files
│ ├── leetcode_solver_demo_video.mp4
│
├── frontend-html/ # Static frontend
│ ├── about.html
│ ├── index.html
│ ├── script.js
│ └── styles.css
│
├── n8n workflow/
│ └── leetcode_solver_app.json # Exported workflow
│
├── README.md
├── .gitignore
└── requirements.txt

yaml
Copy code

---

## 🚀 Quick Start

### 1. Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate      # macOS/Linux
venv\Scripts\activate         # Windows

pip install -r requirements.txt
cp .env.example .env
Edit .env with your own secrets/config.

2. Frontend Setup
bash
Copy code
cd frontend-html

# Option 1: Python HTTP server
python -m http.server 3000

# Option 2: Node.js http-server (if installed)
npx http-server -p 3000

# Option 3: VS Code Live Server extension
# Right-click index.html -> "Open with Live Server"
3. Access the App
Frontend: http://localhost:3000

Backend API: http://localhost:8000

Docs: http://localhost:8000/docs

Health Check: http://localhost:8000/health

🔧 Configuration
Environment Variables (.env)
env
Copy code
# Security
SECRET_KEY=your-secret
AES_KEY=your-32-byte-aes-key

# Redis
REDIS_URL=redis://localhost:6379/0

# N8N Integration
N8N_BASE_URL=https://your-n8n-instance
N8N_TRIGGER_PATH=/webhook/solve-daily
N8N_FETCH_PATH=/webhook/leetcode-code

# CORS
CORS_ORIGINS=http://localhost:3000
🎯 Usage
Start backend (python backend/main.py)

Serve frontend (python -m http.server 3000)

Open the frontend → log in → watch real-time solving updates

🔒 Security
Client-side AES encryption for credentials

No credential storage (deleted after use)

JWT-based sessions

Undetected ChromeDriver + stealth for anti-detection

🧪 Testing
bash
Copy code
cd backend
pytest
📂 Demo Video
A demo video of the app in action is included in this repo:

demo_video/leetcode_solver_demo_video.mp4

Open locally with any media player.

🙏 Acknowledgments
FastAPI

Redis

Selenium

N8N

Undetected ChromeDriver

⚠️ Disclaimer: This app is for educational and web automation testing purposes only. Use responsibly and comply with LeetCode’s Terms of Service.