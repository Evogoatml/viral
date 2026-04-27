#!/usr/bin/env python3
"""
Unified Suite Orchestrator - Python-based service manager
Manages all services in the merged build suite with better error handling
and cross-platform support.
"""

import os
import sys
import subprocess
import signal
import time
import json
import platform
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import argparse

# Colors for terminal output
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    MAGENTA = '\033[0;35m'
    CYAN = '\033[0;36m'
    NC = '\033[0m'  # No Color
    
    @staticmethod
    def disable():
        """Disable colors on Windows"""
        Colors.RED = ''
        Colors.GREEN = ''
        Colors.YELLOW = ''
        Colors.BLUE = ''
        Colors.MAGENTA = ''
        Colors.CYAN = ''
        Colors.NC = ''

# Disable colors on Windows
if platform.system() == 'Windows':
    Colors.disable()

@dataclass
class Service:
    """Service configuration"""
    name: str
    command: List[str]
    cwd: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    port: Optional[int] = None
    health_url: Optional[str] = None
    wait_time: int = 3
    required: bool = True

@dataclass
class ServiceStatus:
    """Service status tracking"""
    name: str
    pid: Optional[int] = None
    status: str = "stopped"  # stopped, starting, running, failed
    started_at: Optional[str] = None
    log_file: Optional[str] = None

class SuiteOrchestrator:
    """Main orchestrator class"""
    
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).parent
        self.base_dir = self.base_dir.resolve()
        self.services: Dict[str, Service] = {}
        self.status: Dict[str, ServiceStatus] = {}
        self.log_dir = self.base_dir / "logs"
        self.pid_file = self.base_dir / ".suite-pids.json"
        self.running = False
        self.plugin_manager = None
        self.queue_bridge = None
        
        # Create log directory
        self.log_dir.mkdir(exist_ok=True)
        
        # Load existing PIDs if any
        self._load_pids()
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _load_pids(self):
        """Load existing process IDs from file"""
        if self.pid_file.exists():
            try:
                with open(self.pid_file, 'r') as f:
                    data = json.load(f)
                    for name, info in data.items():
                        self.status[name] = ServiceStatus(
                            name=name,
                            pid=info.get('pid'),
                            status=info.get('status', 'stopped'),
                            started_at=info.get('started_at')
                        )
            except Exception as e:
                print(f"{Colors.YELLOW}⚠ Warning: Could not load PID file: {e}{Colors.NC}")
    
    def _save_pids(self):
        """Save process IDs to file"""
        data = {}
        for name, status in self.status.items():
            if status.pid:
                data[name] = {
                    'pid': status.pid,
                    'status': status.status,
                    'started_at': status.started_at
                }
        
        try:
            with open(self.pid_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"{Colors.YELLOW}⚠ Warning: Could not save PID file: {e}{Colors.NC}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"\n{Colors.YELLOW}Received shutdown signal...{Colors.NC}")
        self.stop_all()
        sys.exit(0)
    
    def check_prerequisites(self) -> bool:
        """Check if all prerequisites are met"""
        print(f"{Colors.BLUE}Checking prerequisites...{Colors.NC}")
        
        checks = {
            'Python 3.10+': self._check_python(),
            'Node.js': self._check_node(),
            'npm': self._check_npm(),
            'MongoDB': self._check_mongodb(),
            '.env file': self._check_env_file(),
        }
        
        all_ok = True
        for check_name, result in checks.items():
            if result:
                print(f"  {Colors.GREEN}✓{Colors.NC} {check_name}")
            else:
                print(f"  {Colors.YELLOW}⚠{Colors.NC} {check_name} (optional)")
                if check_name in ['Python 3.10+', 'Node.js', 'npm']:
                    all_ok = False
        
        return all_ok
    
    def _check_python(self) -> bool:
        """Check Python version"""
        try:
            result = subprocess.run(
                [sys.executable, '--version'],
                capture_output=True,
                text=True
            )
            version_str = result.stdout.strip()
            # Extract version number
            version = version_str.split()[-1]
            major, minor = map(int, version.split('.')[:2])
            return major == 3 and minor >= 10
        except:
            return False
    
    def _check_node(self) -> bool:
        """Check Node.js installation"""
        try:
            subprocess.run(['node', '--version'], capture_output=True, check=True)
            return True
        except:
            return False
    
    def _check_npm(self) -> bool:
        """Check npm installation"""
        try:
            subprocess.run(['npm', '--version'], capture_output=True, check=True)
            return True
        except:
            return False
    
    def _check_mongodb(self) -> bool:
        """Check MongoDB availability"""
        try:
            # Try to connect or check if process is running
            if platform.system() == 'Windows':
                result = subprocess.run(
                    ['tasklist', '/FI', 'IMAGENAME eq mongod.exe'],
                    capture_output=True
                )
                return 'mongod.exe' in result.stdout.decode()
            else:
                result = subprocess.run(['pgrep', '-x', 'mongod'], capture_output=True)
                return result.returncode == 0
        except:
            return False
    
    def _check_env_file(self) -> bool:
        """Check if .env file exists"""
        return (self.base_dir / '.env').exists()
    
    def setup_environment(self):
        """Setup Python virtual environment and install dependencies"""
        print(f"{Colors.BLUE}Setting up environment...{Colors.NC}")
        
        venv_dir = self.base_dir / "venv"
        
        # Create venv if it doesn't exist
        if not venv_dir.exists():
            print(f"  {Colors.BLUE}Creating virtual environment...{Colors.NC}")
            subprocess.run([sys.executable, '-m', 'venv', str(venv_dir)], check=True)
        
        # Determine Python executable in venv
        if platform.system() == 'Windows':
            python_exe = venv_dir / "Scripts" / "python.exe"
            pip_exe = venv_dir / "Scripts" / "pip.exe"
        else:
            python_exe = venv_dir / "bin" / "python"
            pip_exe = venv_dir / "bin" / "pip"
        
        # Install Python dependencies
        requirements_file = self.base_dir / "requirements.txt"
        if requirements_file.exists():
            print(f"  {Colors.BLUE}Installing Python dependencies...{Colors.NC}")
            subprocess.run([str(pip_exe), 'install', '-q', '--upgrade', 'pip'], check=True)
            subprocess.run([str(pip_exe), 'install', '-q', '-r', str(requirements_file)], check=True)
            print(f"  {Colors.GREEN}✓ Python dependencies installed{Colors.NC}")
        
        # Install Node.js dependencies
        package_json = self.base_dir / "package.json"
        node_modules = self.base_dir / "node_modules"
        
        if package_json.exists() and not node_modules.exists():
            print(f"  {Colors.BLUE}Installing Node.js dependencies...{Colors.NC}")
            subprocess.run(['npm', 'install', '--silent'], cwd=self.base_dir, check=True)
            print(f"  {Colors.GREEN}✓ Node.js dependencies installed{Colors.NC}")
        
        # Create necessary directories
        dirs = ['data/avatars', 'data/content', 'data/strategies', 'data/posts', 'data/analytics']
        for dir_path in dirs:
            (self.base_dir / dir_path).mkdir(parents=True, exist_ok=True)
    
    def register_service(self, service: Service):
        """Register a service to be managed"""
        self.services[service.name] = service
        if service.name not in self.status:
            self.status[service.name] = ServiceStatus(name=service.name)
    
    def _get_python_executable(self):
        """Get Python executable path (venv or system)"""
        venv_dir = self.base_dir / "venv"
        if venv_dir.exists():
            if platform.system() == 'Windows':
                return venv_dir / "Scripts" / "python.exe"
            else:
                return venv_dir / "bin" / "python"
        return sys.executable
    
    def _setup_services(self):
        """Setup default services"""
        python_exe = str(self._get_python_executable())
        
        # Backend service
        self.register_service(Service(
            name="backend",
            command=[python_exe, '-m', 'uvicorn', 'main:app', '--host', '0.0.0.0', '--port', '8000', '--reload'],
            cwd=str(self.base_dir / "backend"),
            port=8000,
            health_url="http://localhost:8000/",
            required=True
        ))
        
        # Frontend service
        self.register_service(Service(
            name="frontend",
            command=['npm', 'run', 'frontend:dev'],
            cwd=str(self.base_dir),
            port=5173,
            health_url="http://localhost:5173/",
            required=False
        ))
        
        # Influencer system
        self.register_service(Service(
            name="influencer",
            command=[python_exe, 'main.py'],
            cwd=str(self.base_dir),
            required=False
        ))
    
    def start_service(self, service_name: str) -> bool:
        """Start a specific service"""
        if service_name not in self.services:
            print(f"{Colors.RED}✗ Service '{service_name}' not found{Colors.NC}")
            return False
        
        service = self.services[service_name]
        status = self.status[service_name]
        
        # Check if already running
        if status.pid and self._is_process_running(status.pid):
            print(f"{Colors.YELLOW}⚠ {service_name} is already running (PID: {status.pid}){Colors.NC}")
            return True
        
        print(f"{Colors.BLUE}Starting {service_name}...{Colors.NC}")
        
        # Prepare log file
        log_file = self.log_dir / f"{service_name}.log"
        status.log_file = str(log_file)
        
        try:
            # Prepare environment
            env = os.environ.copy()
            if service.env:
                env.update(service.env)
            
            # Start process
            with open(log_file, 'w') as log:
                process = subprocess.Popen(
                    service.command,
                    cwd=service.cwd or str(self.base_dir),
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True
                )
            
            status.pid = process.pid
            status.status = "starting"
            status.started_at = datetime.now().isoformat()
            self._save_pids()
            
            # Wait a bit
            time.sleep(service.wait_time)
            
            # Check if process is still running
            if self._is_process_running(process.pid):
                status.status = "running"
                print(f"  {Colors.GREEN}✓ {service_name} started (PID: {process.pid}){Colors.NC}")
                print(f"    Logs: {log_file}")
                
                # Call plugin hooks
                if self.plugin_manager:
                    self.plugin_manager.call_hook('service_start', service_name, process.pid)
                
                # Health check if URL provided
                if service.health_url:
                    self._check_health(service_name, service.health_url)
                
                return True
            else:
                status.status = "failed"
                print(f"  {Colors.RED}✗ {service_name} failed to start{Colors.NC}")
                return False
                
        except Exception as e:
            status.status = "failed"
            print(f"  {Colors.RED}✗ Error starting {service_name}: {e}{Colors.NC}")
            
            # Call plugin hooks for error
            if self.plugin_manager:
                self.plugin_manager.call_hook('service_error', service_name, e)
            
            return False
    
    def _is_process_running(self, pid: int) -> bool:
        """Check if a process is still running"""
        try:
            if platform.system() == 'Windows':
                subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], 
                             capture_output=True, check=True)
                return True
            else:
                os.kill(pid, 0)
                return True
        except:
            return False
    
    def _check_health(self, service_name: str, url: str):
        """Check service health"""
        try:
            import urllib.request
            urllib.request.urlopen(url, timeout=2)
            print(f"    {Colors.GREEN}✓ Health check passed{Colors.NC}")
        except:
            print(f"    {Colors.YELLOW}⚠ Health check pending...{Colors.NC}")
    
    def stop_service(self, service_name: str) -> bool:
        """Stop a specific service"""
        if service_name not in self.status:
            return False
        
        status = self.status[service_name]
        
        if not status.pid:
            return True
        
        if not self._is_process_running(status.pid):
            status.pid = None
            status.status = "stopped"
            return True
        
        print(f"{Colors.BLUE}Stopping {service_name} (PID: {status.pid})...{Colors.NC}")
        
        try:
            # Try graceful shutdown
            if platform.system() == 'Windows':
                subprocess.run(['taskkill', '/PID', str(status.pid), '/T'], 
                             capture_output=True)
            else:
                os.kill(status.pid, signal.SIGTERM)
            
            # Wait for process to stop
            for _ in range(10):
                if not self._is_process_running(status.pid):
                    break
                time.sleep(0.5)
            
            # Force kill if still running
            if self._is_process_running(status.pid):
                if platform.system() == 'Windows':
                    subprocess.run(['taskkill', '/F', '/PID', str(status.pid)], 
                                 capture_output=True)
                else:
                    os.kill(status.pid, signal.SIGKILL)
            
            status.pid = None
            status.status = "stopped"
            self._save_pids()
            
            # Call plugin hooks
            if self.plugin_manager:
                self.plugin_manager.call_hook('service_stop', service_name, old_pid)
            
            print(f"  {Colors.GREEN}✓ {service_name} stopped{Colors.NC}")
            return True
            
        except Exception as e:
            print(f"  {Colors.RED}✗ Error stopping {service_name}: {e}{Colors.NC}")
            return False
    
    def start_all(self, services: Optional[List[str]] = None):
        """Start all or specified services"""
        self._setup_services()
        
        if services is None:
            services = list(self.services.keys())
        
        print(f"{Colors.GREEN}{'='*60}{Colors.NC}")
        print(f"{Colors.GREEN}  Starting Merged Build Suite{Colors.NC}")
        print(f"{Colors.GREEN}{'='*60}{Colors.NC}\n")
        
        started = []
        failed = []
        
        for service_name in services:
            if service_name in self.services:
                if self.start_service(service_name):
                    started.append(service_name)
                else:
                    failed.append(service_name)
                    service = self.services[service_name]
                    if service.required:
                        print(f"{Colors.RED}✗ Required service '{service_name}' failed to start{Colors.NC}")
                        self.stop_all()
                        return False
        
        print(f"\n{Colors.GREEN}{'='*60}{Colors.NC}")
        print(f"{Colors.GREEN}  Suite Status{Colors.NC}")
        print(f"{Colors.GREEN}{'='*60}{Colors.NC}\n")
        
        for service_name in started:
            service = self.services[service_name]
            status = self.status[service_name]
            print(f"{Colors.GREEN}✓{Colors.NC} {service_name:15} - {status.status:10} (PID: {status.pid})")
            if service.port:
                print(f"    URL: http://localhost:{service.port}")
        
        if failed:
            print(f"\n{Colors.RED}Failed services:{Colors.NC}")
            for service_name in failed:
                print(f"  {Colors.RED}✗{Colors.NC} {service_name}")
        
        self.running = True
        return len(failed) == 0
    
    def stop_all(self):
        """Stop all services"""
        print(f"\n{Colors.YELLOW}Shutting down services...{Colors.NC}")
        
        for service_name in list(self.status.keys()):
            self.stop_service(service_name)
        
        # Call plugin shutdown hooks
        if self.plugin_manager:
            self.plugin_manager.call_hook('shutdown')
        
        # Clean up PID file
        if self.pid_file.exists():
            self.pid_file.unlink()
        
        print(f"{Colors.GREEN}✓ All services stopped{Colors.NC}")
        self.running = False
    
    def status_report(self):
        """Print status report of all services"""
        self._setup_services()
        
        print(f"\n{Colors.BLUE}Service Status Report{Colors.NC}")
        print(f"{'='*60}\n")
        
        for service_name, service in self.services.items():
            status = self.status.get(service_name, ServiceStatus(name=service_name))
            status_icon = "✓" if status.status == "running" else "○"
            status_color = Colors.GREEN if status.status == "running" else Colors.YELLOW
            
            print(f"{status_color}{status_icon}{Colors.NC} {service_name:15} - {status.status:10}", end="")
            if status.pid:
                print(f" (PID: {status.pid})")
            else:
                print()
            
            if service.port:
                print(f"    Port: {service.port}")
            if status.log_file:
                print(f"    Logs: {status.log_file}")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Unified Suite Orchestrator')
    parser.add_argument('action', choices=['start', 'stop', 'status', 'restart'],
                       help='Action to perform')
    parser.add_argument('--service', '-s', action='append',
                       help='Specific service(s) to start/stop')
    parser.add_argument('--backend-only', action='store_true',
                       help='Start only backend')
    parser.add_argument('--frontend-only', action='store_true',
                       help='Start only frontend')
    parser.add_argument('--influencer-only', action='store_true',
                       help='Start only influencer system')
    parser.add_argument('--skip-checks', action='store_true',
                       help='Skip prerequisite checks')
    parser.add_argument('--skip-setup', action='store_true',
                       help='Skip environment setup')
    
    args = parser.parse_args()
    
    orchestrator = SuiteOrchestrator()
    
    if args.action == 'start':
        if not args.skip_checks:
            if not orchestrator.check_prerequisites():
                print(f"{Colors.RED}✗ Prerequisites check failed{Colors.NC}")
                sys.exit(1)
        
        if not args.skip_setup:
            orchestrator.setup_environment()
        
        services = None
        if args.service:
            services = args.service
        elif args.backend_only:
            services = ['backend']
        elif args.frontend_only:
            services = ['frontend']
        elif args.influencer_only:
            services = ['influencer']
        
        success = orchestrator.start_all(services)
        
        if success:
            print(f"\n{Colors.GREEN}✓ Suite started successfully!{Colors.NC}")
            print(f"{Colors.YELLOW}Press Ctrl+C to stop all services{Colors.NC}\n")
            
            # Keep running until interrupted
            try:
                while orchestrator.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                orchestrator.stop_all()
        else:
            sys.exit(1)
    
    elif args.action == 'stop':
        orchestrator.stop_all()
    
    elif args.action == 'status':
        orchestrator.status_report()
    
    elif args.action == 'restart':
        orchestrator.stop_all()
        time.sleep(2)
        orchestrator.start_all(args.service)

if __name__ == '__main__':
    main()
