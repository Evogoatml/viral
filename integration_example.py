#!/usr/bin/env python3
"""
Complete Integration Example
Shows how to use all three integration methods together
"""

import asyncio
from suite_orchestrator import SuiteOrchestrator
from plugin_system import PluginManager
from message_queue_integration import MessageQueueIntegration, QueueConfig, QueueType, OrchestratorQueueBridge

async def main():
    """Example of complete integration"""
    
    # 1. Initialize orchestrator
    print("1. Initializing orchestrator...")
    orchestrator = SuiteOrchestrator()
    
    # 2. Load plugins
    print("2. Loading plugins...")
    plugin_manager = PluginManager()
    plugin_manager.load_plugins()
    orchestrator.plugin_manager = plugin_manager
    
    # 3. Setup message queue (optional)
    print("3. Setting up message queue...")
    try:
        queue_config = QueueConfig(
            queue_type=QueueType.REDIS,
            host="localhost",
            port=6379
        )
        queue = MessageQueueIntegration(queue_config)
        await queue.connect()
        
        bridge = OrchestratorQueueBridge(orchestrator, queue)
        await bridge.setup()
        orchestrator.queue_bridge = bridge
        print("   ✓ Message queue connected")
    except Exception as e:
        print(f"   ⚠️ Message queue not available: {e}")
        queue = None
    
    # 4. Setup environment
    print("4. Setting up environment...")
    orchestrator.setup_environment()
    
    # 5. Start services
    print("5. Starting services...")
    orchestrator.start_all(['backend', 'frontend'])
    
    # 6. Keep running
    print("\n✓ Integration complete! Services running...")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        orchestrator.stop_all()
        if queue:
            await queue.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
