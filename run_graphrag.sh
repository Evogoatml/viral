#!/bin/bash
echo "🚀 Starting GraphRAG Enterprise AI..."

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install dependencies
pip install -q -r requirements_graphrag.txt

# Run based on argument
if [ "$1" == "api" ]; then
    echo "Starting FastAPI server..."
    uvicorn backend.api.app:app --reload --host 0.0.0.0 --port 8000
elif [ "$1" == "test" ]; then
    echo "Running test queries..."
    python main_graphrag.py
else
    echo "Usage: ./run_graphrag.sh [api|test]"
    echo "  api  - Start FastAPI server"
    echo "  test - Run test queries"
fi
