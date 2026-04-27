#!/bin/bash
# Start Management API and Dashboard
# Usage: ./start_management.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}Starting Management System...${NC}"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
fi

source venv/bin/activate

# Install management dependencies
if [ -f "requirements_management.txt" ]; then
    echo -e "${BLUE}Installing management dependencies...${NC}"
    pip install -q -r requirements_management.txt
fi

# Start Management API
echo -e "${BLUE}Starting Management API on port 8080...${NC}"
python management_api.py &
API_PID=$!

echo -e "${GREEN}✓ Management API started (PID: $API_PID)${NC}"
echo -e "${GREEN}✓ API URL: http://localhost:8080${NC}"
echo -e "${GREEN}✓ API Docs: http://localhost:8080/docs${NC}"
echo ""
echo -e "${BLUE}Opening dashboard...${NC}"

# Try to open dashboard in browser
if command -v xdg-open > /dev/null; then
    xdg-open management_dashboard.html
elif command -v open > /dev/null; then
    open management_dashboard.html
else
    echo -e "${YELLOW}Please open management_dashboard.html in your browser${NC}"
fi

echo ""
echo -e "${YELLOW}Press Ctrl+C to stop the Management API${NC}"

# Wait for interrupt
trap "kill $API_PID 2>/dev/null; exit" INT TERM
wait $API_PID
