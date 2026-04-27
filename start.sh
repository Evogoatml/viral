#!/bin/bash
# Quick start script for Autonomous Influencer System

echo "🚀 Starting Autonomous Influencer System..."
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found. Creating from template..."
    cp .env.example .env
    echo "📝 Please edit .env and add your API keys"
    echo "   At minimum, add OPENAI_API_KEY for full functionality"
    read -p "Press Enter to continue after editing .env, or Ctrl+C to exit..."
fi

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p data/avatars data/content data/strategies data/posts data/analytics logs

# Start the system
echo ""
echo "✅ Starting system..."
echo ""
python main.py
