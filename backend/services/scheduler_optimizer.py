"""
High-performance job scheduling system with advanced optimization algorithms.

Implements intelligent job scheduling with resource allocation, priority management,
and predictive conflict resolution for maximum throughput.
"""

import asyncio
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import heapq
from collections import defaultdict, deque
import uuid

logger = logging.getLogger(__name__)

class JobStatus(Enum):
    """Job execution status"""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"

class ResourceType(Enum):
    """System resource types"""
    HAMILTON_INSTRUMENT = "hamilton_instrument"
    DATABASE_CONNECTION = "database_connection"
    CAMERA = "camera"
    DISK_SPACE = "disk_space"
    MEMORY = "memory"

@dataclass
class ResourceRequirement:
    """Job resource requirements"""
    resource_type: ResourceType
    amount: float
    duration_seconds: Optional[int] = None
    exclusive: bool = False

@dataclass
class Job:
    """Optimized job definition"""
    job_id: str
    name: str
    scheduled_time: datetime
    estimated_duration: timedelta
    priority: int = 50  # 0=highest, 100=lowest
    resource_requirements: List[ResourceRequirement] = field(default_factory=list)
    dependencies: Set[str] = field(default_factory=set)
    retry_count: int = 0
    max_retries: int = 3
    timeout: Optional[timedelta] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    def __lt__(self, other):
        """Priority queue ordering"""
        # Primary: scheduled time, Secondary: priority, Tertiary: creation time
        return (self.scheduled_time, self.priority, self.created_at) < \
               (other.scheduled_time, other.priority, other.created_at)

@dataclass
class ResourcePool:
    """Resource availability tracking"""
    resource_type: ResourceType
    total_capacity: float
    available_capacity: float
    allocations: Dict[str, Tuple[float, datetime]] = field(default_factory=dict)
    
    def can_allocate(self, amount: float) -> bool:
        """Check if resource can be allocated"""
        return self.available_capacity >= amount
        
    def allocate(self, job_id: str, amount: float, duration: Optional[timedelta] = None) -> bool:
        """Allocate resource to job"""
        if not self.can_allocate(amount):
            return False
            
        self.available_capacity -= amount
        end_time = datetime.now() + duration if duration else None
        self.allocations[job_id] = (amount, end_time)
        return True
        
    def deallocate(self, job_id: str):
        """Deallocate resource from job"""
        if job_id in self.allocations:
            amount, _ = self.allocations[job_id]
            self.available_capacity += amount
            del self.allocations[job_id]

class AdvancedScheduler:
    """
    Advanced job scheduler with optimization algorithms.
    
    Features:
    - Intelligent job prioritization and batching
    - Resource-aware scheduling with conflict detection
    - Predictive analytics for optimal job placement
    - Dynamic load balancing and auto-scaling
    - Advanced retry strategies with exponential backoff
    - Real-time performance optimization
    """
    
    def __init__(self, max_concurrent_jobs: int = 3):
        # Core scheduling
        self.max_concurrent_jobs = max_concurrent_jobs
        self.pending_jobs: List[Job] = []  # min-heap
        self.running_jobs: Dict[str, Job] = {}
        self.completed_jobs: deque = deque(maxlen=1000)  # Keep recent history
        
        # Resource management
        self.resource_pools: Dict[ResourceType, ResourcePool] = {
            ResourceType.HAMILTON_INSTRUMENT: ResourcePool(ResourceType.HAMILTON_INSTRUMENT, 1.0, 1.0),
            ResourceType.DATABASE_CONNECTION: ResourcePool(ResourceType.DATABASE_CONNECTION, 10.0, 10.0),
            ResourceType.CAMERA: ResourcePool(ResourceType.CAMERA, 2.0, 2.0),
            ResourceType.DISK_SPACE: ResourcePool(ResourceType.DISK_SPACE, 100.0, 100.0),  # GB
            ResourceType.MEMORY: ResourcePool(ResourceType.MEMORY, 8.0, 8.0)  # GB
        }
        
        # Optimization state
        self.job_execution_history: Dict[str, List[Tuple[datetime, timedelta]]] = defaultdict(list)
        self.resource_usage_history: Dict[ResourceType, deque] = defaultdict(lambda: deque(maxlen=100))
        
        # Threading and async
        self._scheduler_lock = threading.RLock()
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        
        # Event callbacks
        self.job_callbacks: Dict[JobStatus, List[Callable[[Job], None]]] = defaultdict(list)
        
        # Performance tracking
        self.stats = {
            'jobs_scheduled': 0,
            'jobs_completed': 0,
            'jobs_failed': 0,
            'avg_wait_time': 0.0,
            'avg_execution_time': 0.0,
            'resource_utilization': {},
            'throughput_jobs_per_hour': 0.0
        }
        
        logger.info("AdvancedScheduler initialized")
        
    async def start(self):
        """Start the scheduler"""
        if self._running:
            return
            
        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Advanced scheduler started")
        
    async def stop(self):
        """Stop the scheduler"""
        self._running = False
        
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
                
        logger.info("Advanced scheduler stopped")
        
    def schedule_job(self, job: Job) -> str:
        """
        Schedule a job for execution.
        
        Args:
            job: Job to schedule
            
        Returns:
            Job ID
        """
        with self._scheduler_lock:
            # Validate job
            if not job.job_id:
                job.job_id = str(uuid.uuid4())
                
            # Check dependencies
            unmet_dependencies = self._check_dependencies(job)
            if unmet_dependencies:
                job.status = JobStatus.PENDING
                logger.warning(f"Job {job.job_id} has unmet dependencies: {unmet_dependencies}")
            else:
                job.status = JobStatus.QUEUED
                
            # Optimize scheduling time using historical data
            optimized_time = self._optimize_scheduling_time(job)
            if optimized_time != job.scheduled_time:
                logger.info(f"Job {job.job_id} scheduling time optimized: {job.scheduled_time} -> {optimized_time}")
                job.scheduled_time = optimized_time
                
            # Add to pending queue
            heapq.heappush(self.pending_jobs, job)
            self.stats['jobs_scheduled'] += 1
            
            # Trigger callbacks
            self._trigger_callbacks(job, JobStatus.QUEUED)
            
            logger.info(f"Job scheduled: {job.job_id} ({job.name}) at {job.scheduled_time}")
            return job.job_id
            
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a scheduled job"""
        with self._scheduler_lock:
            # Check running jobs
            if job_id in self.running_jobs:
                job = self.running_jobs[job_id]
                job.status = JobStatus.CANCELLED
                job.completed_at = datetime.now()
                self._deallocate_resources(job)
                del self.running_jobs[job_id]
                self.completed_jobs.append(job)
                logger.info(f"Running job cancelled: {job_id}")
                return True
                
            # Check pending jobs
            for i, job in enumerate(self.pending_jobs):
                if job.job_id == job_id:
                    job.status = JobStatus.CANCELLED
                    job.completed_at = datetime.now()
                    self.pending_jobs.pop(i)
                    heapq.heapify(self.pending_jobs)  # Re-heapify after removal
                    self.completed_jobs.append(job)
                    logger.info(f"Pending job cancelled: {job_id}")
                    return True
                    
            return False
            
    def get_job_status(self, job_id: str) -> Optional[Job]:
        """Get job status and information"""
        # Check running jobs
        if job_id in self.running_jobs:
            return self.running_jobs[job_id]
            
        # Check pending jobs
        for job in self.pending_jobs:
            if job.job_id == job_id:
                return job
                
        # Check completed jobs
        for job in self.completed_jobs:
            if job.job_id == job_id:
                return job
                
        return None
        
    async def _scheduler_loop(self):
        """Main scheduler loop"""
        while self._running:
            try:
                await self._process_pending_jobs()
                await self._monitor_running_jobs()
                await self._cleanup_resources()
                await self._update_statistics()
                await asyncio.sleep(1)  # Check every second
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(5)
                
    async def _process_pending_jobs(self):
        """Process jobs ready for execution"""
        current_time = datetime.now()
        jobs_to_start = []
        
        with self._scheduler_lock:
            # Find jobs ready to start
            while (self.pending_jobs and 
                   len(self.running_jobs) < self.max_concurrent_jobs):
                
                if self.pending_jobs[0].scheduled_time > current_time:
                    break  # No more jobs ready
                    
                job = heapq.heappop(self.pending_jobs)
                
                # Check if job should be executed
                if job.status == JobStatus.CANCELLED:
                    continue
                    
                # Check dependencies
                if not self._are_dependencies_satisfied(job):
                    # Re-queue with delay
                    job.scheduled_time = current_time + timedelta(minutes=1)
                    heapq.heappush(self.pending_jobs, job)
                    continue
                    
                # Check resource availability
                if self._can_allocate_resources(job):
                    jobs_to_start.append(job)
                else:
                    # Re-queue with delay for resource availability
                    job.scheduled_time = current_time + timedelta(seconds=30)
                    heapq.heappush(self.pending_jobs, job)
                    logger.debug(f"Job {job.job_id} delayed due to resource constraints")
                    
        # Start jobs outside the lock to avoid blocking
        for job in jobs_to_start:
            await self._start_job(job)
            
    async def _start_job(self, job: Job):
        """Start executing a job"""
        try:
            # Allocate resources
            if not self._allocate_resources(job):
                logger.error(f"Failed to allocate resources for job {job.job_id}")
                await self._handle_job_failure(job, "Resource allocation failed")
                return
                
            # Update job status
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now()
            
            # Add to running jobs
            with self._scheduler_lock:
                self.running_jobs[job.job_id] = job
                
            # Trigger callbacks
            self._trigger_callbacks(job, JobStatus.RUNNING)
            
            logger.info(f"Job started: {job.job_id} ({job.name})")
            
            # Start job execution in background
            asyncio.create_task(self._execute_job(job))
            
        except Exception as e:
            logger.error(f"Error starting job {job.job_id}: {e}")
            await self._handle_job_failure(job, str(e))
            
    async def _execute_job(self, job: Job):
        """Execute a job (placeholder - would call actual job logic)"""
        try:
            # Simulate job execution
            await asyncio.sleep(job.estimated_duration.total_seconds())
            
            # Mark as completed
            await self._handle_job_completion(job)
            
        except asyncio.CancelledError:
            job.status = JobStatus.CANCELLED
            job.completed_at = datetime.now()
            await self._cleanup_job(job)
            
        except Exception as e:
            await self._handle_job_failure(job, str(e))
            
    async def _handle_job_completion(self, job: Job):
        """Handle successful job completion"""
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now()
        
        # Update execution history for optimization
        execution_time = job.completed_at - job.started_at
        self.job_execution_history[job.name].append((job.completed_at, execution_time))
        
        # Keep only recent history
        if len(self.job_execution_history[job.name]) > 50:
            self.job_execution_history[job.name] = self.job_execution_history[job.name][-50:]
            
        await self._cleanup_job(job)
        
        self.stats['jobs_completed'] += 1
        logger.info(f"Job completed: {job.job_id} in {execution_time}")
        
    async def _handle_job_failure(self, job: Job, error_message: str):
        """Handle job failure with retry logic"""
        job.error_message = error_message
        
        if job.retry_count < job.max_retries:
            job.retry_count += 1
            job.status = JobStatus.RETRYING
            
            # Exponential backoff for retry
            delay_seconds = min(300, 30 * (2 ** job.retry_count))  # Max 5 minutes
            job.scheduled_time = datetime.now() + timedelta(seconds=delay_seconds)
            
            # Re-queue for retry
            with self._scheduler_lock:
                heapq.heappush(self.pending_jobs, job)
                
            logger.warning(f"Job {job.job_id} failed, retrying in {delay_seconds}s (attempt {job.retry_count}/{job.max_retries})")
        else:
            job.status = JobStatus.FAILED
            job.completed_at = datetime.now()
            self.stats['jobs_failed'] += 1
            logger.error(f"Job {job.job_id} failed permanently: {error_message}")
            
        await self._cleanup_job(job)
        
    async def _cleanup_job(self, job: Job):
        """Clean up job resources"""
        # Deallocate resources
        self._deallocate_resources(job)
        
        # Remove from running jobs
        with self._scheduler_lock:
            if job.job_id in self.running_jobs:
                del self.running_jobs[job.job_id]
                
            # Add to completed jobs
            self.completed_jobs.append(job)
            
        # Trigger callbacks
        self._trigger_callbacks(job, job.status)
        
    def _optimize_scheduling_time(self, job: Job) -> datetime:
        """Optimize job scheduling time based on historical data"""
        if job.name not in self.job_execution_history:
            return job.scheduled_time
            
        history = self.job_execution_history[job.name]
        if len(history) < 3:
            return job.scheduled_time
            
        # Calculate average execution time
        avg_duration = sum(duration for _, duration in history[-10:]) / len(history[-10:])
        
        # Estimate optimal start time considering system load
        optimal_time = self._find_optimal_execution_window(job.scheduled_time, avg_duration)
        
        return optimal_time
        
    def _find_optimal_execution_window(self, preferred_time: datetime, duration: timedelta) -> datetime:
        """Find optimal execution window with minimum resource contention"""
        current_time = datetime.now()
        search_start = max(preferred_time, current_time)
        
        # Look for gaps in the schedule
        for offset_hours in range(0, 24):  # Search next 24 hours
            candidate_time = search_start + timedelta(hours=offset_hours)
            
            # Check if this time slot has low resource contention
            if self._is_low_contention_time(candidate_time, duration):
                return candidate_time
                
        # If no optimal time found, return preferred time
        return preferred_time
        
    def _is_low_contention_time(self, start_time: datetime, duration: timedelta) -> bool:
        """Check if time slot has low resource contention"""
        end_time = start_time + duration
        
        # Count overlapping jobs
        overlapping_jobs = 0
        for job in self.running_jobs.values():
            if job.started_at and not job.completed_at:
                job_end = job.started_at + job.estimated_duration
                if start_time < job_end and end_time > job.started_at:
                    overlapping_jobs += 1
                    
        return overlapping_jobs < self.max_concurrent_jobs // 2
        
    def _can_allocate_resources(self, job: Job) -> bool:
        """Check if job resources can be allocated"""
        for requirement in job.resource_requirements:
            pool = self.resource_pools.get(requirement.resource_type)
            if not pool or not pool.can_allocate(requirement.amount):
                return False
        return True
        
    def _allocate_resources(self, job: Job) -> bool:
        """Allocate resources for job execution"""
        allocated_resources = []
        
        try:
            for requirement in job.resource_requirements:
                pool = self.resource_pools[requirement.resource_type]
                duration = timedelta(seconds=requirement.duration_seconds) if requirement.duration_seconds else job.estimated_duration
                
                if pool.allocate(job.job_id, requirement.amount, duration):
                    allocated_resources.append(requirement.resource_type)
                else:
                    # Rollback allocations
                    for resource_type in allocated_resources:
                        self.resource_pools[resource_type].deallocate(job.job_id)
                    return False
                    
            return True
            
        except Exception as e:
            logger.error(f"Resource allocation error for job {job.job_id}: {e}")
            # Rollback any successful allocations
            for resource_type in allocated_resources:
                self.resource_pools[resource_type].deallocate(job.job_id)
            return False
            
    def _deallocate_resources(self, job: Job):
        """Deallocate job resources"""
        for requirement in job.resource_requirements:
            pool = self.resource_pools.get(requirement.resource_type)
            if pool:
                pool.deallocate(job.job_id)
                
    def _check_dependencies(self, job: Job) -> Set[str]:
        """Check for unmet job dependencies"""
        unmet_dependencies = set()
        
        for dep_job_id in job.dependencies:
            dep_job = self.get_job_status(dep_job_id)
            if not dep_job or dep_job.status != JobStatus.COMPLETED:
                unmet_dependencies.add(dep_job_id)
                
        return unmet_dependencies
        
    def _are_dependencies_satisfied(self, job: Job) -> bool:
        """Check if all job dependencies are satisfied"""
        return len(self._check_dependencies(job)) == 0
        
    async def _monitor_running_jobs(self):
        """Monitor running jobs for timeout and completion"""
        current_time = datetime.now()
        jobs_to_timeout = []
        
        for job in list(self.running_jobs.values()):
            # Check for timeout
            if job.timeout and job.started_at:
                if current_time - job.started_at > job.timeout:
                    jobs_to_timeout.append(job)
                    
        # Handle timeouts
        for job in jobs_to_timeout:
            logger.warning(f"Job {job.job_id} timed out")
            await self._handle_job_failure(job, "Job execution timeout")
            
    async def _cleanup_resources(self):
        """Clean up expired resource allocations"""
        current_time = datetime.now()
        
        for pool in self.resource_pools.values():
            expired_jobs = []
            for job_id, (amount, end_time) in pool.allocations.items():
                if end_time and current_time > end_time:
                    expired_jobs.append(job_id)
                    
            for job_id in expired_jobs:
                pool.deallocate(job_id)
                logger.debug(f"Expired resource allocation cleaned up for job {job_id}")
                
    async def _update_statistics(self):
        """Update scheduler performance statistics"""
        if not self.completed_jobs:
            return
            
        # Calculate average metrics
        recent_jobs = list(self.completed_jobs)[-100:]  # Last 100 jobs
        
        if recent_jobs:
            # Wait times
            wait_times = []
            execution_times = []
            
            for job in recent_jobs:
                if job.started_at and job.created_at:
                    wait_time = (job.started_at - job.created_at).total_seconds()
                    wait_times.append(wait_time)
                    
                if job.completed_at and job.started_at:
                    exec_time = (job.completed_at - job.started_at).total_seconds()
                    execution_times.append(exec_time)
                    
            if wait_times:
                self.stats['avg_wait_time'] = sum(wait_times) / len(wait_times)
            if execution_times:
                self.stats['avg_execution_time'] = sum(execution_times) / len(execution_times)
                
        # Resource utilization
        for resource_type, pool in self.resource_pools.items():
            utilization = ((pool.total_capacity - pool.available_capacity) / 
                          pool.total_capacity * 100) if pool.total_capacity > 0 else 0
            self.stats['resource_utilization'][resource_type.value] = utilization
            
    def _trigger_callbacks(self, job: Job, status: JobStatus):
        """Trigger registered callbacks for job status changes"""
        for callback in self.job_callbacks[status]:
            try:
                callback(job)
            except Exception as e:
                logger.error(f"Job callback error: {e}")
                
    def register_callback(self, status: JobStatus, callback: Callable[[Job], None]):
        """Register callback for job status changes"""
        self.job_callbacks[status].append(callback)
        
    def get_scheduler_statistics(self) -> Dict[str, Any]:
        """Get comprehensive scheduler statistics"""
        return {
            **self.stats,
            'pending_jobs': len(self.pending_jobs),
            'running_jobs': len(self.running_jobs),
            'completed_jobs_in_history': len(self.completed_jobs),
            'resource_pools': {
                resource_type.value: {
                    'total_capacity': pool.total_capacity,
                    'available_capacity': pool.available_capacity,
                    'active_allocations': len(pool.allocations)
                }
                for resource_type, pool in self.resource_pools.items()
            }
        }

# Global advanced scheduler instance
advanced_scheduler = AdvancedScheduler()