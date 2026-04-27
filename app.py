#!/usr/bin/env python3
"""
Autonomous Influencer System
Creates a life-like avatar and runs a complete marketing/content system autonomously
"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

from core.orchestrator import AutonomousOrchestrator
from core.logger import setup_logger

# Load environment variables
load_dotenv()

logger = setup_logger(__name__)

async def main():
    """Main entry point for the autonomous influencer system"""
    logger.info("🚀 Starting Autonomous Influencer System...")
    
    # Initialize the orchestrator
    orchestrator = AutonomousOrchestrator()
    
    try:
        # Start the autonomous system
        await orchestrator.start()
        
        # Keep running
        await orchestrator.run_forever()
        
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down gracefully...")
        await orchestrator.shutdown()
    except Exception as e:
        logger.exception(f"❌ Fatal error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
