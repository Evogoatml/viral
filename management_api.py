#!/usr/bin/env python3
"""
Management API Server - REST API for controlling the suite orchestrator
Enables integration with larger management systems, monitoring tools, and dashboards
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncio
import subprocess
import json
from pathlib import Path
import sys
import threading

# Import the orchestrator
try:
    from suite_orchestrator import SuiteOrchestrator, ServiceStatus
except ImportError:
    print("Warning: suite_orchestrator not found. Some features may not work.")
    SuiteOrchestrator = None
    ServiceStatus = None

app = FastAPI(
    title="Suite Management API",
    description="REST API for managing the merged build suite",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global orchestrator instance
orchestrator: Optional[SuiteOrchestrator] = None

# Pydantic models
class ServiceInfo(BaseModel):
    name: str
    status: str
    pid: Optional[int] = None
    started_at: Optional[str] = None
    log_file: Optional[str] = None
    port: Optional[int] = None
    health_url: Optional[str] = None

class StartRequest(BaseModel):
    services: Optional[List[str]] = None
    backend_only: bool = False
    frontend_only: bool = False
    influencer_only: bool = False
    skip_checks: bool = False
    skip_setup: bool = False

class StopRequest(BaseModel):
    services: Optional[List[str]] = None

class HealthResponse(BaseModel):
    status: str
    services: Dict[str, ServiceInfo]
    timestamp: str
    uptime: Optional[float] = None

class MetricsResponse(BaseModel):
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    disk_usage: Optional[float] = None
    active_services: int
    total_services: int
    timestamp: str

class WebhookConfig(BaseModel):
    url: str
    events: List[str]  # start, stop, error, health_check
    secret: Optional[str] = None

# Webhook management
webhooks: List[WebhookConfig] = []

def get_orchestrator() -> SuiteOrchestrator:
    """Get or create orchestrator instance"""
    global orchestrator
    if orchestrator is None:
        orchestrator = SuiteOrchestrator()
        orchestrator._setup_services()
    return orchestrator

async def send_webhook(event: str, data: Dict[str, Any]):
    """Send webhook notifications"""
    import aiohttp
    for webhook in webhooks:
        if event in webhook.events:
            try:
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "event": event,
                        "timestamp": datetime.now().isoformat(),
                        "data": data
                    }
                    headers = {"Content-Type": "application/json"}
                    if webhook.secret:
                        headers["X-Webhook-Secret"] = webhook.secret
                    
                    async with session.post(
                        webhook.url,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        if response.status == 200:
                            print(f"Webhook sent to {webhook.url} for event {event}")
            except Exception as e:
                print(f"Webhook error: {e}")

@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    get_orchestrator()

@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "name": "Suite Management API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/api/health",
            "services": "/api/services",
            "start": "/api/services/start",
            "stop": "/api/services/stop",
            "status": "/api/services/status",
            "metrics": "/api/metrics",
            "logs": "/api/logs/{service}",
            "webhooks": "/api/webhooks"
        }
    }

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    orch = get_orchestrator()
    
    services_info = {}
    for name, service in orch.services.items():
        status = orch.status.get(name, ServiceStatus(name=name))
        services_info[name] = ServiceInfo(
            name=name,
            status=status.status,
            pid=status.pid,
            started_at=status.started_at,
            log_file=status.log_file,
            port=service.port,
            health_url=service.health_url
        )
    
    # Calculate uptime if any service is running
    uptime = None
    for status in orch.status.values():
        if status.status == "running" and status.started_at:
            try:
                start_time = datetime.fromisoformat(status.started_at)
                uptime = (datetime.now() - start_time).total_seconds()
                break
            except:
                pass
    
    overall_status = "healthy" if any(s.status == "running" for s in orch.status.values()) else "unhealthy"
    
    return HealthResponse(
        status=overall_status,
        services=services_info,
        timestamp=datetime.now().isoformat(),
        uptime=uptime
    )

@app.get("/api/services", response_model=Dict[str, ServiceInfo])
async def list_services():
    """List all services and their status"""
    orch = get_orchestrator()
    
    services_info = {}
    for name, service in orch.services.items():
        status = orch.status.get(name, ServiceStatus(name=name))
        services_info[name] = ServiceInfo(
            name=name,
            status=status.status,
            pid=status.pid,
            started_at=status.started_at,
            log_file=status.log_file,
            port=service.port,
            health_url=service.health_url
        )
    
    return services_info

@app.post("/api/services/start")
async def start_services(request: StartRequest, background_tasks: BackgroundTasks):
    """Start services"""
    orch = get_orchestrator()
    
    services = None
    if request.services:
        services = request.services
    elif request.backend_only:
        services = ['backend']
    elif request.frontend_only:
        services = ['frontend']
    elif request.influencer_only:
        services = ['influencer']
    
    # Run in background thread (orchestrator is synchronous)
    def start_task():
        try:
            orch.start_all(services)
        except Exception as e:
            print(f"Error starting services: {e}")
    
    thread = threading.Thread(target=start_task, daemon=True)
    thread.start()
    
    # Send webhook
    background_tasks.add_task(
        send_webhook,
        "start",
        {"services": services or "all"}
    )
    
    return {
        "message": "Services starting",
        "services": services or "all",
        "status": "starting"
    }

@app.post("/api/services/stop")
async def stop_services(request: StopRequest, background_tasks: BackgroundTasks):
    """Stop services"""
    orch = get_orchestrator()
    
    # Run in background thread
    def stop_task():
        try:
            if request.services:
                for service_name in request.services:
                    orch.stop_service(service_name)
            else:
                orch.stop_all()
        except Exception as e:
            print(f"Error stopping services: {e}")
    
    thread = threading.Thread(target=stop_task, daemon=True)
    thread.start()
    
    # Send webhook
    background_tasks.add_task(
        send_webhook,
        "stop",
        {"services": request.services or "all"}
    )
    
    return {
        "message": "Services stopping",
        "services": request.services or "all",
        "status": "stopping"
    }

@app.get("/api/services/status")
async def get_status():
    """Get detailed status of all services"""
    orch = get_orchestrator()
    
    status_report = {}
    for name, service in orch.services.items():
        status = orch.status.get(name, ServiceStatus(name=name))
        status_report[name] = {
            "name": name,
            "status": status.status,
            "pid": status.pid,
            "started_at": status.started_at,
            "log_file": status.log_file,
            "port": service.port,
            "health_url": service.health_url,
            "required": service.required
        }
    
    return status_report

@app.get("/api/metrics", response_model=MetricsResponse)
async def get_metrics():
    """Get system metrics"""
    try:
        import psutil
    except ImportError:
        return MetricsResponse(
            cpu_usage=None,
            memory_usage=None,
            disk_usage=None,
            active_services=0,
            total_services=0,
            timestamp=datetime.now().isoformat()
        )
    
    orch = get_orchestrator()
    
    # Get system metrics
    cpu_usage = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    # Count active services
    active = sum(1 for s in orch.status.values() if s.status == "running")
    total = len(orch.services)
    
    # Get custom metrics from plugins
    custom_metrics = {}
    if orch.plugin_manager:
        plugin_metrics = orch.plugin_manager.call_hook('metrics_collect', {})
        if plugin_metrics:
            custom_metrics.update(plugin_metrics)
    
    return MetricsResponse(
        cpu_usage=cpu_usage,
        memory_usage=memory.percent,
        disk_usage=disk.percent,
        active_services=active,
        total_services=total,
        timestamp=datetime.now().isoformat()
    )

@app.get("/api/logs/{service}")
async def get_logs(service: str, lines: int = 100):
    """Get logs for a service"""
    orch = get_orchestrator()
    
    if service not in orch.status:
        raise HTTPException(status_code=404, detail=f"Service '{service}' not found")
    
    status = orch.status[service]
    
    # Try to find log file
    log_file = None
    if status.log_file:
        log_file = Path(status.log_file)
    else:
        # Default log location
        log_file = orch.log_dir / f"{service}.log"
    
    if not log_file.exists():
        return {"service": service, "logs": [], "message": "No logs available"}
    
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        
        return {
            "service": service,
            "log_file": str(log_file),
            "total_lines": len(all_lines),
            "lines_returned": len(recent_lines),
            "logs": [line.rstrip() for line in recent_lines]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading logs: {str(e)}")

@app.get("/api/logs/{service}/stream")
async def stream_logs(service: str):
    """Stream logs for a service (SSE)"""
    from fastapi.responses import StreamingResponse
    
    orch = get_orchestrator()
    
    if service not in orch.status:
        raise HTTPException(status_code=404, detail=f"Service '{service}' not found")
    
    status = orch.status[service]
    if not status.log_file:
        raise HTTPException(status_code=404, detail="No log file configured")
    
    log_file = Path(status.log_file)
    
    def generate():
        if log_file.exists():
            with open(log_file, 'r') as f:
                # Seek to end
                f.seek(0, 2)
                while True:
                    line = f.readline()
                    if line:
                        yield f"data: {json.dumps({'line': line.rstrip()})}\n\n"
                    else:
                        import time
                        time.sleep(0.1)
    
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.post("/api/webhooks")
async def register_webhook(webhook: WebhookConfig):
    """Register a webhook"""
    webhooks.append(webhook)
    return {
        "message": "Webhook registered",
        "webhook": webhook.dict()
    }

@app.get("/api/webhooks")
async def list_webhooks():
    """List registered webhooks"""
    return {
        "webhooks": [w.dict() for w in webhooks]
    }

@app.delete("/api/webhooks/{index}")
async def delete_webhook(index: int):
    """Delete a webhook"""
    if 0 <= index < len(webhooks):
        webhook = webhooks.pop(index)
        return {"message": "Webhook deleted", "webhook": webhook.dict()}
    raise HTTPException(status_code=404, detail="Webhook not found")

@app.post("/api/services/{service}/restart")
async def restart_service(service: str, background_tasks: BackgroundTasks):
    """Restart a specific service"""
    orch = get_orchestrator()
    
    if service not in orch.services:
        raise HTTPException(status_code=404, detail=f"Service '{service}' not found")
    
    def restart_task():
        orch.stop_service(service)
        import time
        time.sleep(2)
        orch.start_service(service)
    
    background_tasks.add_task(restart_task)
    
    return {
        "message": f"Service '{service}' restarting",
        "service": service,
        "status": "restarting"
    }

@app.get("/api/integration/export")
async def export_config():
    """Export configuration for external systems"""
    orch = get_orchestrator()
    
    config = {
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "services": {},
        "environment": {
            "python_version": sys.version,
            "base_dir": str(orch.base_dir)
        }
    }
    
    for name, service in orch.services.items():
        status = orch.status.get(name, ServiceStatus(name=name))
        config["services"][name] = {
            "name": name,
            "command": service.command,
            "cwd": service.cwd,
            "port": service.port,
            "health_url": service.health_url,
            "status": status.status,
            "pid": status.pid
        }
    
    return config

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
