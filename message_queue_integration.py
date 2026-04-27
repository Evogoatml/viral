#!/usr/bin/env python3
"""
Message Queue Integration for Suite Orchestrator
Provides integration with RabbitMQ, Redis, and other message queues
"""

import json
import asyncio
import os
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum

class QueueType(Enum):
    REDIS = "redis"
    RABBITMQ = "rabbitmq"
    KAFKA = "kafka"
    NATS = "nats"

@dataclass
class QueueConfig:
    """Message queue configuration"""
    queue_type: QueueType
    host: str = "localhost"
    port: int = 6379
    username: Optional[str] = None
    password: Optional[str] = None
    exchange: Optional[str] = None
    routing_key: Optional[str] = None

class MessageQueueIntegration:
    """Message queue integration handler"""
    
    def __init__(self, config: QueueConfig):
        self.config = config
        self.connected = False
        self.client = None
        self.subscribers: Dict[str, Callable] = {}
    
    async def connect(self):
        """Connect to message queue"""
        if self.config.queue_type == QueueType.REDIS:
            await self._connect_redis()
        elif self.config.queue_type == QueueType.RABBITMQ:
            await self._connect_rabbitmq()
        else:
            raise ValueError(f"Unsupported queue type: {self.config.queue_type}")
    
    async def _connect_redis(self):
        """Connect to Redis"""
        try:
            import redis.asyncio as redis
            self.client = redis.Redis(
                host=self.config.host,
                port=self.config.port,
                password=self.config.password,
                decode_responses=True
            )
            await self.client.ping()
            self.connected = True
            print("✓ Connected to Redis")
        except ImportError:
            print("⚠️ redis package not installed. Install with: pip install redis")
            raise
        except Exception as e:
            print(f"✗ Failed to connect to Redis: {e}")
            raise
    
    async def _connect_rabbitmq(self):
        """Connect to RabbitMQ"""
        try:
            import aio_pika
            connection = await aio_pika.connect_robust(
                f"amqp://{self.config.username or 'guest'}:{self.config.password or 'guest'}@{self.config.host}:{self.config.port}/"
            )
            self.client = await connection.channel()
            self.connected = True
            print("✓ Connected to RabbitMQ")
        except ImportError:
            print("⚠️ aio-pika package not installed. Install with: pip install aio-pika")
            raise
        except Exception as e:
            print(f"✗ Failed to connect to RabbitMQ: {e}")
            raise
    
    async def publish(self, topic: str, message: Dict[str, Any]):
        """Publish message to queue"""
        if not self.connected:
            await self.connect()
        
        message_json = json.dumps(message)
        
        if self.config.queue_type == QueueType.REDIS:
            await self._publish_redis(topic, message_json)
        elif self.config.queue_type == QueueType.RABBITMQ:
            await self._publish_rabbitmq(topic, message_json)
    
    async def _publish_redis(self, topic: str, message: str):
        """Publish to Redis pub/sub"""
        await self.client.publish(topic, message)
    
    async def _publish_rabbitmq(self, topic: str, message: str):
        """Publish to RabbitMQ exchange"""
        exchange = await self.client.declare_exchange(
            self.config.exchange or "suite_events",
            aio_pika.ExchangeType.TOPIC
        )
        await exchange.publish(
            aio_pika.Message(message.encode()),
            routing_key=self.config.routing_key or topic
        )
    
    async def subscribe(self, topic: str, callback: Callable):
        """Subscribe to topic"""
        self.subscribers[topic] = callback
        
        if self.config.queue_type == QueueType.REDIS:
            await self._subscribe_redis(topic, callback)
        elif self.config.queue_type == QueueType.RABBITMQ:
            await self._subscribe_rabbitmq(topic, callback)
    
    async def _subscribe_redis(self, topic: str, callback: Callable):
        """Subscribe to Redis pub/sub"""
        pubsub = self.client.pubsub()
        await pubsub.subscribe(topic)
        
        async def listener():
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        await callback(data)
                    except Exception as e:
                        print(f"Error processing message: {e}")
        
        asyncio.create_task(listener())
    
    async def _subscribe_rabbitmq(self, topic: str, callback: Callable):
        """Subscribe to RabbitMQ queue"""
        queue = await self.client.declare_queue(f"suite_{topic}")
        exchange = await self.client.declare_exchange(
            self.config.exchange or "suite_events",
            aio_pika.ExchangeType.TOPIC
        )
        await queue.bind(exchange, routing_key=self.config.routing_key or topic)
        
        async def process_message(message: aio_pika.IncomingMessage):
            async with message.process():
                try:
                    data = json.loads(message.body.decode())
                    await callback(data)
                except Exception as e:
                    print(f"Error processing message: {e}")
        
        await queue.consume(process_message)
    
    async def publish_event(self, event_type: str, data: Dict[str, Any]):
        """Publish suite event"""
        message = {
            "event": event_type,
            "timestamp": asyncio.get_event_loop().time(),
            "data": data
        }
        await self.publish(f"suite.{event_type}", message)
    
    async def disconnect(self):
        """Disconnect from queue"""
        if self.client:
            if self.config.queue_type == QueueType.REDIS:
                await self.client.close()
            elif self.config.queue_type == QueueType.RABBITMQ:
                await self.client.close()
        self.connected = False

# Integration with orchestrator
class OrchestratorQueueBridge:
    """Bridge between orchestrator and message queue"""
    
    def __init__(self, orchestrator, queue: MessageQueueIntegration):
        self.orchestrator = orchestrator
        self.queue = queue
    
    async def setup(self):
        """Setup queue subscriptions"""
        await self.queue.connect()
        
        # Subscribe to orchestrator events
        await self.queue.subscribe("suite.control.start", self.handle_start_command)
        await self.queue.subscribe("suite.control.stop", self.handle_stop_command)
        await self.queue.subscribe("suite.control.restart", self.handle_restart_command)
    
    async def handle_start_command(self, message: Dict[str, Any]):
        """Handle start command from queue"""
        services = message.get("data", {}).get("services")
        if services:
            self.orchestrator.start_all(services)
        else:
            self.orchestrator.start_all()
        
        # Publish event
        await self.queue.publish_event("started", {"services": services or "all"})
    
    async def handle_stop_command(self, message: Dict[str, Any]):
        """Handle stop command from queue"""
        services = message.get("data", {}).get("services")
        if services:
            for service in services:
                self.orchestrator.stop_service(service)
        else:
            self.orchestrator.stop_all()
        
        await self.queue.publish_event("stopped", {"services": services or "all"})
    
    async def handle_restart_command(self, message: Dict[str, Any]):
        """Handle restart command from queue"""
        service = message.get("data", {}).get("service")
        if service:
            self.orchestrator.stop_service(service)
            import time
            time.sleep(2)
            self.orchestrator.start_service(service)
            await self.queue.publish_event("restarted", {"service": service})
    
    def hook_service_start(self, service_name: str, pid: int):
        """Hook called when service starts"""
        asyncio.create_task(
            self.queue.publish_event("service_started", {
                "service": service_name,
                "pid": pid
            })
        )
    
    def hook_service_stop(self, service_name: str, pid: int):
        """Hook called when service stops"""
        asyncio.create_task(
            self.queue.publish_event("service_stopped", {
                "service": service_name,
                "pid": pid
            })
        )
