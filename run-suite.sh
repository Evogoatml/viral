#!/bin/bash
# Unified Suite Runner - Starts all components of the merged build
# Usage: ./run-suite.sh [--backend-only] [--frontend-only] [--influencer-only] [--scraper-only]

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# PID file to track running processes
PID_FILE="$SCRIPT_DIR/.suite-pids"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

# Parse arguments
BACKEND_ONLY=false
FRONTEND_ONLY=false
INFLUENCER_ONLY=false
SCRAPER_ONLY=false

for arg in "$@"; do
    case $arg in
        --backend-only)
            BACKEND_ONLY=true
            ;;
        --frontend-only)
            FRONTEND_ONLY=true
            ;;
        --influencer-only)
            INFLUENCER_ONLY=true
            ;;
        --scraper-only)
            SCRAPER_ONLY=true
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --backend-only      Start only the FastAPI backend"
            echo "  --frontend-only     Start only the React frontend"
            echo "  --influencer-only   Start only the influencer system"
            echo "  --scraper-only      Start only the scraping tool"
            echo "  --help, -h          Show this help message"
            echo ""
            echo "If no options are provided, all services will start."
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $arg${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# If no specific service is selected, start all
if [ "$BACKEND_ONLY" = false ] && [ "$FRONTEND_ONLY" = false ] && \
   [ "$INFLUENCER_ONLY" = false ] && [ "$SCRAPER_ONLY" = false ]; then
    START_ALL=true
else
    START_ALL=false
fi

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if a port is in use
port_in_use() {
    lsof -i :"$1" >/dev/null 2>&1 || netstat -an 2>/dev/null | grep -q ":$1 " || \
    ss -lnt 2>/dev/null | grep -q ":$1 "
}

# Function to wait for a service to be ready
wait_for_service() {
    local url=$1
    local max_attempts=30
    local attempt=0
    
    echo -e "${BLUE}Waiting for service at $url...${NC}"
    while [ $attempt -lt $max_attempts ]; do
        if curl -s "$url" >/dev/null 2>&1; then
            echo -e "${GREEN}✓ Service is ready${NC}"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    
    echo -e "${YELLOW}⚠ Service did not become ready in time${NC}"
    return 1
}

# Function to start a service in background and save PID
start_service() {
    local name=$1
    local command=$2
    local log_file="$LOG_DIR/${name}.log"
    
    echo -e "${BLUE}Starting $name...${NC}"
    eval "$command" > "$log_file" 2>&1 &
    local pid=$!
    echo "$name:$pid" >> "$PID_FILE"
    echo -e "${GREEN}✓ $name started (PID: $pid)${NC}"
    echo "  Logs: $log_file"
    return $pid
}

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}Shutting down services...${NC}"
    if [ -f "$PID_FILE" ]; then
        while IFS=: read -r name pid; do
            if kill -0 "$pid" 2>/dev/null; then
                echo -e "${BLUE}Stopping $name (PID: $pid)...${NC}"
                kill "$pid" 2>/dev/null || true
            fi
        done < "$PID_FILE"
        rm -f "$PID_FILE"
    fi
    echo -e "${GREEN}✓ All services stopped${NC}"
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Check prerequisites
echo -e "${BLUE}Checking prerequisites...${NC}"

# Check Python
if ! command_exists python3; then
    echo -e "${RED}✗ Python 3 is not installed${NC}"
    exit 1
fi
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo -e "${GREEN}✓ Python $PYTHON_VERSION found${NC}"

# Check Node.js
if ! command_exists node; then
    echo -e "${RED}✗ Node.js is not installed${NC}"
    exit 1
fi
NODE_VERSION=$(node --version)
echo -e "${GREEN}✓ Node.js $NODE_VERSION found${NC}"

# Check npm
if ! command_exists npm; then
    echo -e "${RED}✗ npm is not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ npm found${NC}"

# Check MongoDB (optional but recommended for backend)
if command_exists mongod; then
    if pgrep -x mongod >/dev/null; then
        echo -e "${GREEN}✓ MongoDB is running${NC}"
    else
        echo -e "${YELLOW}⚠ MongoDB is installed but not running${NC}"
        echo "  Backend will need MongoDB. Start it with: sudo systemctl start mongod"
    fi
else
    echo -e "${YELLOW}⚠ MongoDB not found (backend requires it)${NC}"
fi

# Check for .env file
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠ .env file not found${NC}"
    if [ -f ".env.example" ]; then
        echo -e "${BLUE}Creating .env from .env.example...${NC}"
        cp .env.example .env
        echo -e "${YELLOW}⚠ Please edit .env and add your API keys before continuing${NC}"
        read -p "Press Enter to continue or Ctrl+C to exit..."
    else
        echo -e "${RED}✗ .env.example not found. Please create .env manually${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}✓ .env file found${NC}"

# Initialize PID file
> "$PID_FILE"

# Setup Python virtual environment
if [ ! -d "venv" ]; then
    echo -e "${BLUE}Creating Python virtual environment...${NC}"
    python3 -m venv venv
fi

echo -e "${BLUE}Activating virtual environment...${NC}"
source venv/bin/activate

# Install Python dependencies
if [ -f "requirements.txt" ]; then
    echo -e "${BLUE}Installing Python dependencies...${NC}"
    pip install -q --upgrade pip
    pip install -q -r requirements.txt
    echo -e "${GREEN}✓ Python dependencies installed${NC}"
fi

# Install Node.js dependencies
if [ -f "package.json" ]; then
    if [ ! -d "node_modules" ]; then
        echo -e "${BLUE}Installing Node.js dependencies...${NC}"
        npm install --silent
        echo -e "${GREEN}✓ Node.js dependencies installed${NC}"
    else
        echo -e "${GREEN}✓ Node.js dependencies already installed${NC}"
    fi
fi

# Create necessary directories
mkdir -p data/avatars data/content data/strategies data/posts data/analytics logs

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Starting Merged Build Suite${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Start Management API (optional - for integration)
if [ "$START_ALL" = true ] && [ -f "management_api.py" ]; then
    if port_in_use 8080; then
        echo -e "${YELLOW}⚠ Port 8080 is already in use (management API may already be running)${NC}"
    else
        start_service "management-api" "python management_api.py"
        sleep 2
        echo -e "${GREEN}✓ Management API: http://localhost:8080${NC}"
        echo -e "${GREEN}✓ Management Dashboard: Open management_dashboard.html${NC}"
    fi
fi

# Start Backend (FastAPI)
if [ "$START_ALL" = true ] || [ "$BACKEND_ONLY" = true ]; then
    if port_in_use 8000; then
        echo -e "${YELLOW}⚠ Port 8000 is already in use (backend may already be running)${NC}"
    else
        cd backend
        if [ ! -f "requirements.txt" ]; then
            # Create backend requirements if missing
            echo "Creating backend/requirements.txt..."
            cat > requirements.txt << EOF
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
motor>=3.3.0
pymongo>=4.6.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
pydantic>=2.5.0
python-dotenv>=1.0.0
aiofiles>=23.2.0
openai>=1.0.0
chromadb>=0.4.0
sentence-transformers>=2.2.0
langchain>=0.1.0
langgraph>=0.0.1
EOF
        fi
        pip install -q -r requirements.txt
        cd ..
        
        start_service "backend" "cd backend && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
        sleep 3
        wait_for_service "http://localhost:8000" || true
    fi
fi

# Start Frontend (React/Vite)
if [ "$START_ALL" = true ] || [ "$FRONTEND_ONLY" = true ]; then
    if port_in_use 5173; then
        echo -e "${YELLOW}⚠ Port 5173 is already in use (frontend may already be running)${NC}"
    else
        # Check if vite.config exists, if not create basic one
        if [ ! -f "vite.config.ts" ] && [ ! -f "vite.config.js" ]; then
            echo "Creating basic vite.config.js..."
            cat > vite.config.js << 'EOF'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
EOF
        fi
        
        # Check if React dependencies are installed
        if [ ! -d "node_modules/react" ]; then
            echo -e "${BLUE}Installing frontend dependencies...${NC}"
            npm install --silent react react-dom @vitejs/plugin-react vite typescript @types/react @types/react-dom
        fi
        
        start_service "frontend" "npm run frontend:dev"
        sleep 3
    fi
fi

# Start Influencer System
if [ "$START_ALL" = true ] || [ "$INFLUENCER_ONLY" = true ]; then
    start_service "influencer" "python main.py"
    sleep 2
fi

# Start Scraper Tool (optional - only if explicitly requested)
if [ "$SCRAPER_ONLY" = true ]; then
    if port_in_use 3000; then
        echo -e "${YELLOW}⚠ Port 3000 is already in use${NC}"
    else
        start_service "scraper-web" "npm run web"
        sleep 2
    fi
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Suite Started Successfully!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BLUE}Services running:${NC}"
if [ "$START_ALL" = true ] || [ "$BACKEND_ONLY" = true ]; then
    echo -e "  ${GREEN}✓${NC} Backend API:     http://localhost:8000"
    echo -e "  ${GREEN}✓${NC} API Docs:         http://localhost:8000/docs"
fi
if [ "$START_ALL" = true ] || [ "$FRONTEND_ONLY" = true ]; then
    echo -e "  ${GREEN}✓${NC} Frontend:         http://localhost:5173"
fi
if [ "$START_ALL" = true ] || [ "$INFLUENCER_ONLY" = true ]; then
    echo -e "  ${GREEN}✓${NC} Influencer System: Running (check logs/influencer.log)"
fi
if [ "$SCRAPER_ONLY" = true ]; then
    echo -e "  ${GREEN}✓${NC} Scraper Web:      http://localhost:3000"
fi
echo ""
echo -e "${BLUE}Logs:${NC} $LOG_DIR"
echo -e "${BLUE}PID file:${NC} $PID_FILE"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Keep script running
wait
