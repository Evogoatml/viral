#!/bin/bash
# Stop Suite - Gracefully stops all services started by run-suite.sh

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/.suite-pids"

if [ ! -f "$PID_FILE" ]; then
    echo -e "${YELLOW}No PID file found. Services may not be running.${NC}"
    exit 0
fi

echo -e "${BLUE}Stopping all services...${NC}"

# Read PID file and stop each service
while IFS=: read -r name pid; do
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo -e "${BLUE}Stopping $name (PID: $pid)...${NC}"
        kill "$pid" 2>/dev/null || true
        
        # Wait for process to stop
        for i in {1..10}; do
            if ! kill -0 "$pid" 2>/dev/null; then
                echo -e "${GREEN}✓ $name stopped${NC}"
                break
            fi
            sleep 0.5
        done
        
        # Force kill if still running
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "${YELLOW}Force killing $name...${NC}"
            kill -9 "$pid" 2>/dev/null || true
            echo -e "${GREEN}✓ $name force stopped${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ $name (PID: $pid) is not running${NC}"
    fi
done < "$PID_FILE"

# Clean up PID file
rm -f "$PID_FILE"

echo -e "${GREEN}✓ All services stopped${NC}"
