---
title: "Background processing"
order: 10
section: "core"
---

# Background Processing

> **Status: v1.** Resolves the **(open)** item from [architecture.md](architecture.md): "Background processing. Ingestion and content generation are long-running tasks. Queue system (Celery, Dramatiq, etc.) vs LangGraph's built-in persistence."

---

## 1. Requirements

SkillNet has several operations that cannot complete within a normal HTTP request cycle:

| Operation | Duration | Characteristics |
|-----------|----------|-----------------|
| Course generation (LLM pipeline) | 2-10 min | Multi-step, needs progress tracking, human review interrupt |
| Document ingestion (parse + chunk + embed) | 30s-3 min | CPU/GPU-bound embedding, idempotent retry per chunk |
| Spaced repetition recalculation | 10-60s | Periodic batch, no user waiting |
| Bulk user import (CSV) | 5-30s | Row-level error tracking |
| Course feedback report generation | 15-45s | LLM call, single-step |
| Embedding model migration | 5-30 min | Background, interruptible |

**Functional requirements:**

1. **Progress tracking.** The admin sees which step is running for generation jobs (extracting, structuring, generating, reviewing). Employees see ingestion status for uploaded documents.
2. **Step-level retry.** If step 3/5 fails, retry from step 3, not step 1. Generation steps and embedding batches are individually retryable.
3. **Concurrency limits.** LLM calls are expensive and rate-limited. The system must cap simultaneous generation jobs and ingestion tasks.
4. **Cancellation.** An admin can cancel a running generation job. The system stops the pipeline at the next checkpoint.
5. **Durability across restarts.** If the server restarts mid-generation, the job resumes from the last checkpoint, not from scratch.
6. **No user-facing latency.** All long-running operations return immediately with a job ID. The client tracks progress via polling or SSE.

**Non-requirements for MVP:**

- Multi-node distribution (single-server deployment)
- Priority queues (FIFO is sufficient at MVP scale)
- Rate limiting per user (single-tenant, admin-only triggers)
- Job scheduling from the UI (only periodic system tasks)

---

## 2. Option Evaluation

Five approaches evaluated for a self-hosted, single-tenant MVP.

### 2.1 LangGraph Persistence (built-in checkpointing)

LangGraph provides `SqliteSaver` and `PostgresSaver` for persisting graph state between nodes. The generation pipeline is already a LangGraph graph with defined nodes (extracting, structuring, generating, reviewing).

| Aspect | Assessment |
|--------|------------|
| **Fits generation pipeline** | Excellent. The pipeline is already a graph. Checkpointing is built in. |
| **Interrupt/resume** | Native. `interrupt()` pauses the graph, human input resumes it. |
| **Crash recovery** | Automatic. Load checkpoint, resume from last completed node. |
| **Fits ingestion/batch jobs** | Poor. These are not graph-shaped workflows. Forcing them into LangGraph adds complexity. |
| **Concurrency control** | None built in. Must be managed externally. |
| **Dependencies** | Already present (LangGraph is a core dependency for agent orchestration). |

**Verdict:** Perfect for the generation pipeline. Wrong tool for everything else.

### 2.2 Celery + Redis

The industry standard for Python background tasks.

| Aspect | Assessment |
|--------|------------|
| **Maturity** | Battle-tested, massive ecosystem. |
| **Retry/concurrency** | Excellent. Per-task retry policies, worker concurrency, rate limits. |
| **Monitoring** | Flower dashboard, rich event system. |
| **Dependencies** | Adds Redis (new infrastructure), Celery (heavy library), separate worker process. |
| **Deployment** | Docker Compose grows: app + worker + Redis + beat (scheduler). |
| **For single-tenant MVP** | Over-engineered. The operational overhead of Redis + Celery workers exceeds the benefit when running 1-5 jobs per day. |

**Verdict:** Right tool at scale. Too much infrastructure for an MVP doing a handful of jobs daily.

### 2.3 arq (async Redis queue)

Lightweight async alternative to Celery, built on Redis.

| Aspect | Assessment |
|--------|------------|
| **Simplicity** | Much simpler than Celery. Async-native, minimal boilerplate. |
| **Dependencies** | Still requires Redis. |
| **Features** | Basic retry, cron jobs, result storage. No workflow graphs. |
| **Community** | Smaller than Celery, less battle-tested. |

**Verdict:** Better than Celery for this use case, but still requires Redis — a dependency the system doesn't otherwise need.

### 2.4 FastAPI BackgroundTasks + DB Polling

Use FastAPI's built-in `BackgroundTasks` for fire-and-forget, with a database table tracking job state.

| Aspect | Assessment |
|--------|------------|
| **Dependencies** | Zero. Uses existing PostgreSQL and FastAPI. |
| **Simplicity** | Very simple for the happy path. |
| **Durability** | None. `BackgroundTasks` runs in-process. Server restart loses the task. No checkpoint, no retry. |
| **Concurrency** | Manual (asyncio semaphores). |
| **Progress tracking** | Via DB polling — works but no push. |

**Verdict:** Too fragile for multi-minute generation jobs. Acceptable only for sub-30s tasks that can be retried from scratch.

### 2.5 Dramatiq

Redis or RabbitMQ-backed task queue. Simpler API than Celery, better defaults.

| Aspect | Assessment |
|--------|------------|
| **Simplicity** | Cleaner than Celery, good middleware system. |
| **Dependencies** | Requires Redis or RabbitMQ (same issue as Celery/arq). |
| **Async support** | Limited. Dramatiq is sync-first. SkillNet is async-first (FastAPI + asyncpg + AsyncOpenAI). |

**Verdict:** Sync-first design clashes with SkillNet's async stack. Still requires a message broker.

### 2.6 Summary Matrix

| Criterion | LangGraph | Celery+Redis | arq | BackgroundTasks+DB | Dramatiq |
|-----------|-----------|-------------|-----|-------------------|----------|
| Generation pipeline fit | +++| + | + | -- | + |
| Generic job fit | -- | +++ | ++ | + | ++ |
| Zero new dependencies | +++ | -- | -- | +++ | -- |
| Crash recovery | +++ | ++ | + | -- | ++ |
| Async-native | ++ | + | +++ | +++ | -- |
| MVP complexity | ++ | -- | + | +++ | - |

---

## 3. Recommendation: Hybrid Approach

Use the right tool for each job type, with zero new infrastructure dependencies.

### 3.1 LangGraph Persistence for the Generation Pipeline

The generation pipeline (course + manual creation) is already modeled as a LangGraph state graph. Using LangGraph's built-in `PostgresSaver` for checkpointing gives us:

- **Interrupt/resume** for human review (the `reviewing` step pauses the graph, admin reviews and approves/rejects)
- **Crash recovery** by loading the last checkpoint and resuming
- **Step-level progress** by reading which node the graph is currently executing
- **No new dependencies** — LangGraph and PostgreSQL are already in the stack

### 3.2 PostgreSQL-Backed Job Runner for Everything Else

For ingestion, batch operations, report generation, and periodic tasks, a lightweight job runner backed by a `background_jobs` table in PostgreSQL:

- **Claim-based concurrency** using `SELECT FOR UPDATE SKIP LOCKED` — the same pattern used by production job systems (GoodJob, Que, Oban)
- **Retry with backoff** tracked in the `background_jobs` table
- **Polling loop** inside the FastAPI process (no separate worker)
- **asyncio.Semaphore** for concurrency limits per job type
- **Zero new dependencies** — just PostgreSQL queries

### 3.3 Why No Redis

Redis would be needed for Celery, arq, or Dramatiq. For an MVP with these characteristics:

- Single server, single process
- 1-5 generation jobs per day
- 5-20 document ingestions per week
- 1 periodic SR recalculation every 6 hours

PostgreSQL is already there, already connected, already backed up. Adding Redis means:

- Another container in Docker Compose
- Another persistence layer to back up
- Another failure point to monitor
- Configuration for Redis connection, memory limits, eviction policies

None of this is justified at MVP scale. If SkillNet grows to need distributed workers or sub-second job dispatch, Redis can be added then. The `background_jobs` table and job runner interface remain the same — only the dispatch mechanism changes.

---

## 4. Architecture Design

### 4.1 System Diagram

```
                        FastAPI Application (single process)
    ┌──────────────────────────────────────────────────────────────────┐
    │                                                                  │
    │   ┌─────────────────────────────────────────────────────────┐   │
    │   │                   JobCoordinator                         │   │
    │   │  (starts on app lifespan, manages all background work)  │   │
    │   └──────────┬──────────────┬──────────────┬────────────────┘   │
    │              │              │              │                     │
    │   ┌──────────▼──────┐ ┌────▼──────────┐ ┌▼────────────────┐   │
    │   │ GenerationWorker│ │BackgroundJob  │ │PeriodicScheduler│   │
    │   │                 │ │   Runner      │ │                 │   │
    │   │ LangGraph graph │ │ Polling loop  │ │ asyncio loop    │   │
    │   │ + PostgresSaver │ │ + semaphores  │ │ + cron tasks    │   │
    │   │                 │ │               │ │                 │   │
    │   │ Max concurrency:│ │ Job types:    │ │ Tasks:          │   │
    │   │ 2 simultaneous  │ │ - ingestion   │ │ - SR recalc     │   │
    │   │                 │ │ - bulk_import │ │ - stuck detect  │   │
    │   │                 │ │ - report_gen  │ │ - cleanup       │   │
    │   │                 │ │ - sr_recalc   │ │                 │   │
    │   │                 │ │ - embed_migr  │ │                 │   │
    │   └────────┬────────┘ └──────┬────────┘ └────────┬────────┘   │
    │            │                 │                    │             │
    │   ┌────────▼─────────────────▼────────────────────▼──────────┐ │
    │   │                     PostgreSQL                            │ │
    │   │  ┌──────────────┐  ┌───────────────┐  ┌──────────────┐  │ │
    │   │  │generation_jobs│  │background_jobs │  │langgraph     │  │ │
    │   │  │(+ langgraph  │  │(generic queue) │  │checkpoints   │  │ │
    │   │  │  thread_id)  │  │               │  │(PostgresSaver)│  │ │
    │   │  └──────────────┘  └───────────────┘  └──────────────┘  │ │
    │   └─────────────────────────────────────────────────────────┘ │
    │                                                                │
    │   ┌──────────────────────────────────────────────────────────┐ │
    │   │                  SSE Progress Stream                      │ │
    │   │  Same infrastructure as chat (StreamingResponse)          │ │
    │   └──────────────────────────────────────────────────────────┘ │
    └──────────────────────────────────────────────────────────────────┘
```

### 4.2 New Table: `background_jobs`

Generic job queue for non-generation background tasks.

```sql
CREATE TYPE job_type AS ENUM (
    'document_ingestion',
    'bulk_user_import',
    'feedback_report',
    'sr_recalculation',
    'embedding_migration',
    'checkpoint_cleanup'
);

CREATE TYPE job_status AS ENUM (
    'pending',
    'running',
    'completed',
    'failed',
    'cancelled'
);

CREATE TABLE background_jobs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL REFERENCES organizations(id),
    type            job_type NOT NULL,
    status          job_status NOT NULL DEFAULT 'pending',
    payload         jsonb NOT NULL DEFAULT '{}',
    result          jsonb,
    error_message   text,
    attempt_count   int NOT NULL DEFAULT 0,
    max_attempts    int NOT NULL DEFAULT 3,
    locked_by       text,                       -- worker identifier
    locked_at       timestamptz,
    scheduled_at    timestamptz NOT NULL DEFAULT now(),
    started_at      timestamptz,
    completed_at    timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Claim next job efficiently
CREATE INDEX idx_background_jobs_claimable
    ON background_jobs (scheduled_at)
    WHERE status = 'pending';

-- Find stuck jobs (running but lock expired)
CREATE INDEX idx_background_jobs_stuck
    ON background_jobs (locked_at)
    WHERE status = 'running';

-- Admin listing
CREATE INDEX idx_background_jobs_org_status
    ON background_jobs (org_id, status);
```

### 4.3 Schema Changes to `generation_jobs`

The existing `generation_jobs` table gains columns for LangGraph integration and progress reporting.

```sql
ALTER TABLE generation_jobs
    ADD COLUMN langgraph_thread_id text,
    ADD COLUMN progress jsonb NOT NULL DEFAULT '{}',
    ADD COLUMN cancelled_at timestamptz;

-- Progress JSON structure:
-- {
--   "current_step": "generating",
--   "steps_completed": ["extracting", "structuring"],
--   "steps_remaining": ["generating", "reviewing"],
--   "pct": 50,
--   "detail": "Generating module 3 of 5..."
-- }
```

### 4.4 Background Job Runner

The core polling loop that claims and executes generic background jobs.

```python
# src/workers/job_runner.py

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger("skillnet.workers.job_runner")

# Concurrency limits per job type
CONCURRENCY_LIMITS: dict[str, int] = {
    "document_ingestion": 3,
    "bulk_user_import": 1,
    "feedback_report": 2,
    "sr_recalculation": 1,
    "embedding_migration": 1,
    "checkpoint_cleanup": 1,
}

POLL_INTERVAL_SECONDS = 5
LOCK_TIMEOUT_MINUTES = 30  # Jobs locked longer than this are considered stuck
MAX_BACKOFF_SECONDS = 300  # 5 minutes max between retries


class BackgroundJobRunner:
    """
    PostgreSQL-backed job runner using SELECT FOR UPDATE SKIP LOCKED.

    Runs inside the FastAPI process as an asyncio task. No separate worker
    process needed. Claims jobs from the background_jobs table, executes
    them with concurrency limits, and records results.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        worker_id: str | None = None,
    ):
        self.session_factory = session_factory
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self._semaphores: dict[str, asyncio.Semaphore] = {
            job_type: asyncio.Semaphore(limit)
            for job_type, limit in CONCURRENCY_LIMITS.items()
        }
        self._running = False
        self._active_tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        """Start the polling loop. Call from FastAPI lifespan."""
        self._running = True
        logger.info("BackgroundJobRunner started (worker_id=%s)", self.worker_id)
        while self._running:
            try:
                await self._poll_and_dispatch()
            except Exception:
                logger.exception("Error in job runner poll loop")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def stop(self) -> None:
        """Graceful shutdown. Waits for active tasks to complete."""
        self._running = False
        if self._active_tasks:
            logger.info(
                "Waiting for %d active tasks to complete...",
                len(self._active_tasks),
            )
            await asyncio.gather(*self._active_tasks, return_exceptions=True)
        logger.info("BackgroundJobRunner stopped")

    async def _poll_and_dispatch(self) -> None:
        """Claim the next available job and dispatch it."""
        async with self.session_factory() as session:
            job = await self._claim_next_job(session)
            if job is None:
                return

            job_id, job_type, payload = job["id"], job["type"], job["payload"]
            semaphore = self._semaphores.get(job_type)

            if semaphore is not None and semaphore.locked():
                # All slots for this job type are full — release the claim
                await self._release_claim(session, job_id)
                return

            task = asyncio.create_task(
                self._execute_job(job_id, job_type, payload, semaphore)
            )
            self._active_tasks.add(task)
            task.add_done_callback(self._active_tasks.discard)

    async def _claim_next_job(self, session: AsyncSession) -> dict | None:
        """
        Atomically claim the next pending job using SELECT FOR UPDATE SKIP LOCKED.

        This pattern guarantees:
        - No two workers claim the same job (row-level lock)
        - Workers don't block each other (SKIP LOCKED skips already-claimed rows)
        - Jobs are processed in scheduled_at order (FIFO)
        """
        result = await session.execute(
            text("""
                UPDATE background_jobs
                SET status = 'running',
                    locked_by = :worker_id,
                    locked_at = now(),
                    started_at = now(),
                    attempt_count = attempt_count + 1,
                    updated_at = now()
                WHERE id = (
                    SELECT id FROM background_jobs
                    WHERE status = 'pending'
                      AND scheduled_at <= now()
                    ORDER BY scheduled_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING id, type, payload
            """),
            {"worker_id": self.worker_id},
        )
        row = result.mappings().first()
        await session.commit()
        return dict(row) if row else None

    async def _release_claim(self, session: AsyncSession, job_id: uuid.UUID) -> None:
        """Release a claimed job back to pending (concurrency limit hit)."""
        await session.execute(
            text("""
                UPDATE background_jobs
                SET status = 'pending',
                    locked_by = NULL,
                    locked_at = NULL,
                    started_at = NULL,
                    attempt_count = attempt_count - 1,
                    updated_at = now()
                WHERE id = :job_id
            """),
            {"job_id": job_id},
        )
        await session.commit()

    async def _execute_job(
        self,
        job_id: uuid.UUID,
        job_type: str,
        payload: dict,
        semaphore: asyncio.Semaphore | None,
    ) -> None:
        """Execute a job with semaphore-based concurrency control."""
        if semaphore:
            async with semaphore:
                await self._run_job(job_id, job_type, payload)
        else:
            await self._run_job(job_id, job_type, payload)

    async def _run_job(
        self, job_id: uuid.UUID, job_type: str, payload: dict
    ) -> None:
        """Run the actual job handler and record the result."""
        logger.info("Executing job %s (type=%s)", job_id, job_type)

        try:
            handler = JOB_HANDLERS.get(job_type)
            if handler is None:
                raise ValueError(f"No handler registered for job type: {job_type}")

            async with self.session_factory() as session:
                result = await handler(session, payload)

            # Mark completed
            async with self.session_factory() as session:
                await session.execute(
                    text("""
                        UPDATE background_jobs
                        SET status = 'completed',
                            result = :result,
                            completed_at = now(),
                            locked_by = NULL,
                            updated_at = now()
                        WHERE id = :job_id
                    """),
                    {"job_id": job_id, "result": result},
                )
                await session.commit()

            logger.info("Job %s completed successfully", job_id)

        except Exception as e:
            logger.exception("Job %s failed: %s", job_id, e)
            await self._handle_failure(job_id, str(e))

    async def _handle_failure(self, job_id: uuid.UUID, error: str) -> None:
        """Handle job failure: retry with backoff or mark as permanently failed."""
        async with self.session_factory() as session:
            row = await session.execute(
                text("""
                    SELECT attempt_count, max_attempts
                    FROM background_jobs WHERE id = :job_id
                """),
                {"job_id": job_id},
            )
            job = row.mappings().first()

            if job and job["attempt_count"] < job["max_attempts"]:
                # Schedule retry with exponential backoff
                backoff = min(
                    2 ** job["attempt_count"] * 10,  # 10s, 20s, 40s, 80s...
                    MAX_BACKOFF_SECONDS,
                )
                retry_at = datetime.utcnow() + timedelta(seconds=backoff)

                await session.execute(
                    text("""
                        UPDATE background_jobs
                        SET status = 'pending',
                            error_message = :error,
                            locked_by = NULL,
                            locked_at = NULL,
                            scheduled_at = :retry_at,
                            updated_at = now()
                        WHERE id = :job_id
                    """),
                    {"job_id": job_id, "error": error, "retry_at": retry_at},
                )
                logger.info(
                    "Job %s scheduled for retry in %ds (attempt %d/%d)",
                    job_id, backoff, job["attempt_count"], job["max_attempts"],
                )
            else:
                # Permanently failed
                await session.execute(
                    text("""
                        UPDATE background_jobs
                        SET status = 'failed',
                            error_message = :error,
                            locked_by = NULL,
                            completed_at = now(),
                            updated_at = now()
                        WHERE id = :job_id
                    """),
                    {"job_id": job_id, "error": error},
                )
                logger.error("Job %s permanently failed after %d attempts", job_id,
                             job["attempt_count"] if job else 0)

            await session.commit()


# --- Job handler registry ---

from typing import Callable, Awaitable

JobHandler = Callable[[AsyncSession, dict], Awaitable[dict | None]]

JOB_HANDLERS: dict[str, JobHandler] = {}


def register_job_handler(job_type: str):
    """Decorator to register a handler for a job type."""
    def decorator(func: JobHandler) -> JobHandler:
        JOB_HANDLERS[job_type] = func
        return func
    return decorator
```

### 4.5 Generation Worker

Wraps the LangGraph generation graph with concurrency control and progress tracking.

```python
# src/workers/generation_worker.py

import asyncio
import logging
import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

logger = logging.getLogger("skillnet.workers.generation")

# Generation pipeline steps in order (all graph node names)
GENERATION_STEPS = [
    "extracting",
    "structuring",
    "generating",
    "structure_review",   # interrupt: admin reviews structure
    "reviewing",          # interrupt: admin reviews final content
    "publishing",
    "published",
]

# Map graph node names to generation_jobs status values
NODE_TO_STATUS: dict[str, str] = {
    "extracting": "extracting",
    "structuring": "structuring",
    "generating": "generating",
    "structure_review": "reviewing",
    "reviewing": "reviewing",
    "publishing": "publishing",
    "published": "published",
}

MAX_CONCURRENT_GENERATIONS = 2


class GenerationWorker:
    """
    Manages LangGraph-based generation jobs with PostgreSQL checkpointing.

    Each generation job runs as a LangGraph graph invocation. The graph
    persists its state after each node via PostgresSaver, enabling:
    - Crash recovery (reload checkpoint, resume from last node)
    - Human review interrupt (graph pauses at 'reviewing' node)
    - Progress tracking (read current node from checkpoint)
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        db_connection_string: str,
    ):
        self.session_factory = session_factory
        self.db_connection_string = db_connection_string
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_GENERATIONS)
        self._running = False
        self._active_tasks: dict[uuid.UUID, asyncio.Task] = {}

    async def start(self) -> None:
        """Start the generation worker polling loop."""
        self._running = True
        logger.info("GenerationWorker started (max_concurrent=%d)",
                     MAX_CONCURRENT_GENERATIONS)
        while self._running:
            try:
                await self._poll_pending_jobs()
            except Exception:
                logger.exception("Error in generation worker poll loop")
            await asyncio.sleep(5)

    async def stop(self) -> None:
        """Graceful shutdown. Active generations continue to their next checkpoint."""
        self._running = False
        if self._active_tasks:
            logger.info(
                "Waiting for %d active generations to checkpoint...",
                len(self._active_tasks),
            )
            await asyncio.gather(
                *self._active_tasks.values(), return_exceptions=True
            )
        logger.info("GenerationWorker stopped")

    async def _poll_pending_jobs(self) -> None:
        """Find pending generation jobs and dispatch them."""
        if self._semaphore.locked():
            return  # All slots occupied

        async with self.session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT id, org_id, source_document_id, output_type,
                           triggered_by, langgraph_thread_id
                    FROM generation_jobs
                    WHERE status = 'pending'
                    ORDER BY created_at
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                """)
            )
            job = result.mappings().first()
            if job is None:
                return

            job_id = job["id"]

            # Assign a LangGraph thread ID if not already present (new job)
            thread_id = job["langgraph_thread_id"] or f"gen-{job_id}"
            await session.execute(
                text("""
                    UPDATE generation_jobs
                    SET status = 'extracting',
                        langgraph_thread_id = :thread_id,
                        updated_at = now()
                    WHERE id = :job_id
                """),
                {"job_id": job_id, "thread_id": thread_id},
            )
            await session.commit()

        task = asyncio.create_task(self._run_generation(dict(job), thread_id))
        self._active_tasks[job_id] = task
        task.add_done_callback(lambda t: self._active_tasks.pop(job_id, None))

    async def _run_generation(self, job: dict, thread_id: str) -> None:
        """
        Execute the generation pipeline via LangGraph.

        The graph is defined in src/agents/content/graph.py. Each node
        (extract, structure, generate, review) is a graph node. The
        PostgresSaver persists state after each node completes.
        """
        job_id = job["id"]

        async with self._semaphore:
            logger.info("Starting generation job %s (thread=%s)", job_id, thread_id)

            try:
                # Initialize LangGraph checkpointer
                async with AsyncPostgresSaver.from_conn_string(
                    self.db_connection_string
                ) as checkpointer:
                    await checkpointer.setup()

                    # Import the generation graph
                    from src.agents.content.graph import build_content_graph

                    graph = build_content_graph(checkpointer=checkpointer)
                    config = {"configurable": {"thread_id": thread_id}}

                    # Check if we're resuming from a checkpoint
                    checkpoint = await checkpointer.aget(config)

                    if checkpoint is not None:
                        logger.info(
                            "Resuming job %s from checkpoint", job_id
                        )
                        # Resume: the graph picks up from where it left off
                        async for event in graph.astream(None, config):
                            await self._update_progress(job_id, event)
                    else:
                        # Fresh start: provide initial state
                        initial_state = {
                            "job_id": str(job_id),
                            "org_id": str(job["org_id"]),
                            "source_document_ids": [str(job["source_document_id"])],
                            "output_type": job["output_type"],
                            "triggered_by": str(job["triggered_by"]),
                        }
                        async for event in graph.astream(initial_state, config):
                            await self._update_progress(job_id, event)

                    # Check final state
                    final_state = await graph.aget_state(config)

                    if final_state.next:
                        # Graph is paused (human review interrupt)
                        logger.info(
                            "Job %s paused for human review at: %s",
                            job_id, final_state.next,
                        )
                    else:
                        # Graph completed
                        await self._mark_completed(job_id, final_state.values)

            except asyncio.CancelledError:
                logger.info("Job %s cancelled", job_id)
                await self._mark_cancelled(job_id)
            except Exception as e:
                logger.exception("Job %s failed: %s", job_id, e)
                await self._mark_failed(job_id, str(e))

    async def _update_progress(
        self, job_id: uuid.UUID, event: dict
    ) -> None:
        """Update generation_jobs with current step and progress info."""
        # LangGraph events include the node name that just completed
        node_name = None
        for key in event:
            if key in GENERATION_STEPS:
                node_name = key
                break

        if node_name is None:
            return

        step_idx = GENERATION_STEPS.index(node_name)
        pct = int((step_idx + 1) / len(GENERATION_STEPS) * 100)
        status = NODE_TO_STATUS.get(node_name, node_name)

        progress = {
            "current_step": node_name,
            "steps_completed": GENERATION_STEPS[:step_idx + 1],
            "steps_remaining": GENERATION_STEPS[step_idx + 1:],
            "pct": pct,
        }

        async with self.session_factory() as session:
            await session.execute(
                text("""
                    UPDATE generation_jobs
                    SET status = :status,
                        progress = :progress,
                        updated_at = now()
                    WHERE id = :job_id
                """),
                {
                    "job_id": job_id,
                    "status": status,
                    "progress": progress,
                },
            )
            await session.commit()

        logger.info("Job %s progress: %s (%d%%)", job_id, node_name, pct)

    async def _mark_completed(
        self, job_id: uuid.UUID, final_values: dict
    ) -> None:
        """Mark a generation job as successfully published."""
        async with self.session_factory() as session:
            await session.execute(
                text("""
                    UPDATE generation_jobs
                    SET status = 'published',
                        result_course_id = :course_id,
                        result_manual_id = :manual_id,
                        progress = jsonb_set(progress, '{pct}', '100'),
                        updated_at = now()
                    WHERE id = :job_id
                """),
                {
                    "job_id": job_id,
                    "course_id": final_values.get("course_id"),
                    "manual_id": final_values.get("manual_id"),
                },
            )
            await session.commit()

    async def _mark_failed(self, job_id: uuid.UUID, error: str) -> None:
        """Mark a generation job as failed."""
        async with self.session_factory() as session:
            await session.execute(
                text("""
                    UPDATE generation_jobs
                    SET status = 'failed',
                        error_message = :error,
                        updated_at = now()
                    WHERE id = :job_id
                """),
                {"job_id": job_id, "error": error},
            )
            await session.commit()

    async def _mark_cancelled(self, job_id: uuid.UUID) -> None:
        """Mark a generation job as cancelled."""
        async with self.session_factory() as session:
            await session.execute(
                text("""
                    UPDATE generation_jobs
                    SET status = 'failed',
                        error_message = 'Cancelled by user',
                        cancelled_at = now(),
                        updated_at = now()
                    WHERE id = :job_id
                """),
                {"job_id": job_id},
            )
            await session.commit()

    async def cancel_job(self, job_id: uuid.UUID) -> bool:
        """Cancel a running generation job. Returns True if cancelled."""
        task = self._active_tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            return True

        # If not actively running, just mark as cancelled in DB
        async with self.session_factory() as session:
            result = await session.execute(
                text("""
                    UPDATE generation_jobs
                    SET status = 'failed',
                        error_message = 'Cancelled by user',
                        cancelled_at = now(),
                        updated_at = now()
                    WHERE id = :job_id
                      AND status IN ('pending', 'extracting', 'structuring',
                                     'generating', 'reviewing')
                    RETURNING id
                """),
                {"job_id": job_id},
            )
            cancelled = result.first() is not None
            await session.commit()
            return cancelled
```

### 4.6 Job Coordinator

Orchestrates all background workers. Integrates with FastAPI's lifespan.

```python
# src/workers/coordinator.py

import asyncio
import logging
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from src.workers.job_runner import BackgroundJobRunner
from src.workers.generation_worker import GenerationWorker
from src.workers.periodic_scheduler import PeriodicScheduler

logger = logging.getLogger("skillnet.workers.coordinator")


class JobCoordinator:
    """
    Central orchestrator for all background processing.

    Manages three subsystems:
    1. GenerationWorker — LangGraph-based content generation
    2. BackgroundJobRunner — PostgreSQL-backed generic job queue
    3. PeriodicScheduler — Recurring maintenance tasks

    Started during FastAPI lifespan, stopped on shutdown.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        db_connection_string: str,
    ):
        self.generation_worker = GenerationWorker(
            session_factory=session_factory,
            db_connection_string=db_connection_string,
        )
        self.job_runner = BackgroundJobRunner(
            session_factory=session_factory,
        )
        self.periodic_scheduler = PeriodicScheduler(
            session_factory=session_factory,
        )
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start all background workers as concurrent asyncio tasks."""
        logger.info("JobCoordinator starting all workers...")

        self._tasks = [
            asyncio.create_task(
                self.generation_worker.start(), name="generation-worker"
            ),
            asyncio.create_task(
                self.job_runner.start(), name="job-runner"
            ),
            asyncio.create_task(
                self.periodic_scheduler.start(), name="periodic-scheduler"
            ),
        ]

        logger.info("JobCoordinator: all workers started")

    async def stop(self) -> None:
        """Gracefully stop all workers."""
        logger.info("JobCoordinator stopping all workers...")

        await asyncio.gather(
            self.generation_worker.stop(),
            self.job_runner.stop(),
            self.periodic_scheduler.stop(),
            return_exceptions=True,
        )

        # Cancel any remaining tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("JobCoordinator: all workers stopped")
```

**Integration with FastAPI lifespan:**

```python
# src/main.py (updated lifespan)

from src.workers.coordinator import JobCoordinator

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    coordinator = JobCoordinator(
        session_factory=async_session_factory,
        db_connection_string=settings.DATABASE_URL,
    )
    app.state.coordinator = coordinator
    await coordinator.start()

    yield

    # Shutdown
    await coordinator.stop()
    await engine.dispose()
```

---

## 5. Generation Job Lifecycle

Complete flow from admin click to published course.

### 5.1 Happy Path

```
Admin clicks "Generate course from document"
  │
  ▼
POST /api/v1/courses/{id}/generate
  │
  ├─ Creates generation_jobs row (status='pending')
  ├─ Returns { job_id: "uuid" } immediately (202 Accepted)
  │
  ▼
GenerationWorker picks up job (polling loop)
  │
  ├─ Claims job (SELECT FOR UPDATE SKIP LOCKED)
  ├─ Assigns langgraph_thread_id
  ├─ Sets status='extracting'
  │
  ▼
LangGraph graph executes node: EXTRACT
  │
  ├─ Reads source document from DB / disk
  ├─ Extracts key concepts, topics, learning objectives
  ├─ PostgresSaver checkpoints state
  ├─ Updates generation_jobs.status='structuring'
  │
  ▼
LangGraph graph executes node: STRUCTURE
  │
  ├─ Organizes concepts into modules and lessons
  ├─ Determines exercise types per lesson
  ├─ Maps skills to modules (checkpoint suggestions)
  ├─ PostgresSaver checkpoints state
  ├─ Updates generation_jobs.status='reviewing'
  │
  ▼
LangGraph graph hits INTERRUPT #1 at node: STRUCTURE_REVIEW
  │
  ├─ Graph pauses (LangGraph interrupt())
  ├─ Generation_jobs.status='reviewing'
  ├─ Admin receives notification: "Course structure ready for review"
  │
  ▼
Admin reviews proposed structure (modules, lessons, skill mappings)
  │
  ├─ Can reorder modules, rename lessons, adjust skill mappings
  ├─ Can approve or request restructuring
  │
  ▼
POST /api/v1/generation-jobs/{id}/review  (with action='approve_structure')
  │
  ├─ Resumes the LangGraph graph with human feedback
  ├─ Graph continues to GENERATE node with approved structure
  │
  ▼
LangGraph graph executes node: GENERATE
  │
  ├─ Generates lesson content (LLM calls, potentially multiple)
  ├─ Generates exercises per lesson
  ├─ Generates manual content
  ├─ PostgresSaver checkpoints state
  ├─ Updates generation_jobs.status='reviewing'
  │
  ▼
LangGraph graph hits INTERRUPT #2 at node: REVIEW (final review)
  │
  ├─ Graph pauses (LangGraph interrupt())
  ├─ Generation_jobs.status='reviewing'
  ├─ Admin receives notification: "Course content ready for final review"
  │
  ▼
Admin reviews generated content in the UI
  │
  ├─ Can edit individual lessons, exercises, module order
  ├─ Can approve or request regeneration of specific parts
  │
  ▼
POST /api/v1/generation-jobs/{id}/review  (with action='approve_final')
  │
  ├─ Resumes the LangGraph graph with human feedback
  ├─ Graph executes PUBLISH node
  │
  ▼
LangGraph graph executes node: PUBLISH
  │
  ├─ Writes course, modules, lessons, exercises to DB
  ├─ Writes manual to DB
  ├─ Sets course.status='draft' (admin publishes manually)
  ├─ Updates generation_jobs.status='published'
  ├─ Links result_course_id and result_manual_id
  │
  ▼
Admin publishes when ready
  POST /api/v1/courses/{id}/publish
```

### 5.2 Failure and Recovery

```
Server crashes during GENERATE step
  │
  ▼
Server restarts
  │
  ├─ JobCoordinator starts
  ├─ GenerationWorker resumes polling
  │
  ▼
GenerationWorker finds job with status='generating'
  │
  ├─ Loads langgraph_thread_id from generation_jobs
  ├─ PostgresSaver loads checkpoint for that thread
  ├─ Checkpoint contains state after STRUCTURE completed
  │
  ▼
LangGraph graph resumes from GENERATE node
  │
  ├─ Skips EXTRACT and STRUCTURE (already checkpointed)
  ├─ Continues generation from where it left off
  │
  ▼
Normal flow continues...
```

### 5.3 Cancellation

```
Admin clicks "Cancel" on a running generation job
  │
  ▼
DELETE /api/v1/generation-jobs/{id}
  │
  ├─ Calls GenerationWorker.cancel_job(job_id)
  ├─ If actively running: task.cancel() → CancelledError at next await
  ├─ If pending/paused: marks as failed with 'Cancelled by user'
  │
  ▼
Job marked as failed with cancelled_at timestamp
```

---

## 6. Document Ingestion Lifecycle

### 6.1 End-to-End Flow

```
Admin uploads document
  │
  ▼
POST /api/v1/documents (multipart upload)
  │
  ├─ Saves file to disk (uploads/ directory)
  ├─ Creates documents row (status='pending')
  ├─ Returns document metadata immediately
  │
  ▼
POST /api/v1/documents/{id}/process
  │
  ├─ Creates background_jobs row:
  │     type='document_ingestion'
  │     payload={ "document_id": "uuid", "file_path": "..." }
  ├─ Returns 202 Accepted
  │
  ▼
BackgroundJobRunner claims job
  │
  ├─ SELECT FOR UPDATE SKIP LOCKED
  ├─ Acquires ingestion semaphore (max 3 concurrent)
  │
  ▼
Ingestion handler executes (see rag-retrieval.md section 3.1)
  │
  ├─ Parse document (pymupdf / python-docx)
  ├─ Clean and normalize text
  ├─ Decide strategy (full_text vs chunk+embed)
  │
  ├── Small doc path (<=3 pages):
  │     Store full_text in documents row → done
  │
  ├── Large doc path:
  │     ├─ Chunk by sections (semantic + fixed-size fallback)
  │     ├─ Batch embed (multilingual-e5-small, batches of 64)
  │     │   └─ Per-batch: if batch fails, retry that batch only
  │     ├─ Store chunks in document_chunks
  │     └─ Update documents.status='ready'
  │
  ▼
background_jobs.status='completed'
documents.status='ready'
```

### 6.2 Idempotent Retry

If ingestion fails mid-embedding (e.g., batch 4 of 7 hits an OOM error), the retry strategy is:

```python
# src/workers/handlers/ingestion.py

from src.workers.job_runner import register_job_handler

@register_job_handler("document_ingestion")
async def handle_document_ingestion(
    session: AsyncSession, payload: dict
) -> dict | None:
    """
    Ingestion handler with idempotent retry.

    On retry, skips chunks that already have embeddings stored.
    This avoids re-embedding hundreds of chunks because batch 6/7 failed.
    """
    document_id = UUID(payload["document_id"])
    file_path = Path(payload["file_path"])

    doc = await session.get(Document, document_id)
    doc.status = "processing"
    await session.commit()

    try:
        # Parse and chunk (fast, safe to redo)
        sections = parse_document(file_path)
        full_text = "\n\n".join(s.content for s in sections)
        estimated_pages = max(1, count_tokens(full_text) // 750)

        if estimated_pages <= 3:
            doc.full_text = full_text
            doc.status = "ready"
            await session.commit()
            return {"strategy": "full_text", "pages": estimated_pages}

        chunks = chunk_sections(sections, document_id, doc.title)

        # Check which chunks already exist (idempotent retry)
        existing = await session.execute(
            text("""
                SELECT chunk_index FROM document_chunks
                WHERE document_id = :doc_id AND embedding IS NOT NULL
            """),
            {"doc_id": document_id},
        )
        existing_indices = {row[0] for row in existing}

        # Filter to only un-embedded chunks
        remaining_chunks = [
            c for c in chunks if c.chunk_index not in existing_indices
        ]

        if remaining_chunks:
            embeddings = await embed_chunks(remaining_chunks)
            for chunk, embedding in zip(remaining_chunks, embeddings):
                db_chunk = DocumentChunk(
                    document_id=document_id,
                    content=chunk.content,
                    embedding=embedding.tolist(),
                    chunk_index=chunk.chunk_index,
                    metadata=chunk.metadata,
                )
                session.add(db_chunk)

        doc.embedding_model = "multilingual-e5-small"
        doc.embedding_dim = EMBEDDING_DIM
        doc.status = "ready"
        await session.commit()

        return {
            "strategy": "chunked",
            "total_chunks": len(chunks),
            "new_chunks": len(remaining_chunks),
            "skipped_chunks": len(existing_indices),
        }

    except Exception as e:
        doc.status = "error"
        doc.error_message = str(e)
        await session.commit()
        raise  # Re-raise so the job runner handles retry/failure
```

---

## 7. Concurrency Control

### 7.1 Limits by Job Type

| Job Type | Max Concurrent | Rationale |
|----------|---------------|-----------|
| Generation (LangGraph) | 2 | Each generation job makes many LLM calls. 2 concurrent avoids rate limits and keeps costs predictable. |
| Document ingestion | 3 | CPU-bound embedding is the bottleneck. 3 concurrent saturates a typical 4-core server without thrashing. |
| SR recalculation | 1 | Batch DB operation. Running multiple simultaneously would lock rows and cause contention. |
| Bulk user import | 1 | Sequential by nature (CSV rows). Parallel would risk duplicate-email conflicts. |
| Feedback report | 2 | Single LLM call each. Low cost, can parallel. |
| Embedding migration | 1 | Full table scan + batch updates. Must be exclusive. |

### 7.2 Implementation

Concurrency is enforced at two levels:

**Level 1: asyncio.Semaphore (in-process)**

```python
# Each worker type holds a semaphore
self._generation_semaphore = asyncio.Semaphore(2)
self._ingestion_semaphore = asyncio.Semaphore(3)
```

This prevents the single process from launching too many concurrent tasks. It is fast, zero-overhead, and sufficient for single-process deployment.

**Level 2: SELECT FOR UPDATE SKIP LOCKED (database)**

```sql
SELECT id FROM background_jobs
WHERE status = 'pending'
  AND scheduled_at <= now()
ORDER BY scheduled_at
FOR UPDATE SKIP LOCKED
LIMIT 1
```

This prevents multiple processes (if ever deployed) from claiming the same job. `SKIP LOCKED` means workers never block each other — if a row is locked, the query moves to the next one.

**Why both levels:** The semaphore prevents over-dispatching within the process. The database lock prevents double-claiming across processes. Together they provide correct concurrency control now (single process) and in the future (multiple processes).

---

## 8. Periodic Scheduler

### 8.1 Task Schedule

| Task | Interval | What it Does |
|------|----------|-------------|
| `spaced_repetition_recalc` | Every 6 hours | Recalculates `next_review_at` for all spaced repetition entries where the computed review time may have drifted. Inserts a `background_jobs` row of type `sr_recalculation`. |
| `stuck_job_detection` | Every 15 minutes | Finds jobs with `status='running'` and `locked_at` older than 30 minutes. Resets them to `pending` for retry. Logs a warning. |
| `checkpoint_cleanup` | Every 24 hours | Removes LangGraph checkpoints for generation jobs that completed or failed more than 7 days ago. Prevents unbounded storage growth. |

### 8.2 Implementation

```python
# src/workers/periodic_scheduler.py

import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger("skillnet.workers.periodic")


class PeriodicTask:
    """Defines a recurring task with its interval and handler."""

    def __init__(self, name: str, interval_seconds: int, handler):
        self.name = name
        self.interval_seconds = interval_seconds
        self.handler = handler
        self.last_run: datetime | None = None


class PeriodicScheduler:
    """
    Simple asyncio-based periodic task scheduler.

    No external dependencies. Runs as an asyncio task inside the
    FastAPI process. Each task has a fixed interval and runs
    sequentially (one at a time) to avoid resource contention.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory
        self._running = False
        self._tasks = [
            PeriodicTask(
                name="stuck_job_detection",
                interval_seconds=15 * 60,  # 15 minutes
                handler=self._detect_stuck_jobs,
            ),
            PeriodicTask(
                name="spaced_repetition_recalc",
                interval_seconds=6 * 60 * 60,  # 6 hours
                handler=self._schedule_sr_recalc,
            ),
            PeriodicTask(
                name="checkpoint_cleanup",
                interval_seconds=24 * 60 * 60,  # 24 hours
                handler=self._cleanup_checkpoints,
            ),
        ]

    async def start(self) -> None:
        """Start the periodic scheduler loop."""
        self._running = True
        logger.info("PeriodicScheduler started with %d tasks", len(self._tasks))

        while self._running:
            now = datetime.utcnow()
            for task in self._tasks:
                if task.last_run is None or (
                    now - task.last_run
                ).total_seconds() >= task.interval_seconds:
                    try:
                        logger.info("Running periodic task: %s", task.name)
                        await task.handler()
                        task.last_run = now
                    except Exception:
                        logger.exception(
                            "Periodic task %s failed", task.name
                        )
            await asyncio.sleep(60)  # Check every minute

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        logger.info("PeriodicScheduler stopped")

    async def _detect_stuck_jobs(self) -> None:
        """
        Find and recover stuck jobs.

        A job is stuck if it has status='running' but its lock has expired
        (locked_at older than LOCK_TIMEOUT_MINUTES). This happens when:
        - The process crashed mid-job
        - A job handler hung indefinitely
        - Network timeout on an external call (LLM API)
        """
        async with self.session_factory() as session:
            cutoff = datetime.utcnow() - timedelta(minutes=30)

            # Reset stuck background_jobs
            result = await session.execute(
                text("""
                    UPDATE background_jobs
                    SET status = 'pending',
                        locked_by = NULL,
                        locked_at = NULL,
                        error_message = 'Reset: lock expired (stuck job detection)',
                        updated_at = now()
                    WHERE status = 'running'
                      AND locked_at < :cutoff
                      AND attempt_count < max_attempts
                    RETURNING id, type
                """),
                {"cutoff": cutoff},
            )
            stuck = result.fetchall()
            if stuck:
                for row in stuck:
                    logger.warning(
                        "Stuck job detected and reset: id=%s type=%s",
                        row[0], row[1],
                    )

            # Check stuck generation_jobs
            gen_result = await session.execute(
                text("""
                    SELECT id, status, updated_at
                    FROM generation_jobs
                    WHERE status IN ('extracting', 'structuring', 'generating')
                      AND updated_at < :cutoff
                """),
                {"cutoff": cutoff},
            )
            stuck_gens = gen_result.fetchall()
            for row in stuck_gens:
                logger.warning(
                    "Stuck generation job detected: id=%s status=%s "
                    "last_updated=%s",
                    row[0], row[1], row[2],
                )
                # Reset to pending so the GenerationWorker picks it up
                # and resumes from checkpoint
                await session.execute(
                    text("""
                        UPDATE generation_jobs
                        SET status = 'pending',
                            updated_at = now()
                        WHERE id = :job_id
                    """),
                    {"job_id": row[0]},
                )

            await session.commit()

    async def _schedule_sr_recalc(self) -> None:
        """
        Insert a background job for spaced repetition recalculation.

        The actual recalculation runs as a background_job, not inline,
        so it respects concurrency limits and can be retried on failure.
        """
        async with self.session_factory() as session:
            # Check if one is already pending or running
            existing = await session.execute(
                text("""
                    SELECT id FROM background_jobs
                    WHERE type = 'sr_recalculation'
                      AND status IN ('pending', 'running')
                    LIMIT 1
                """)
            )
            if existing.first() is not None:
                logger.info("SR recalculation already pending/running, skipping")
                return

            # Get the org_id (single-tenant)
            org = await session.execute(
                text("SELECT id FROM organizations LIMIT 1")
            )
            org_row = org.first()
            if org_row is None:
                return

            await session.execute(
                text("""
                    INSERT INTO background_jobs (org_id, type, payload)
                    VALUES (:org_id, 'sr_recalculation', '{}')
                """),
                {"org_id": org_row[0]},
            )
            await session.commit()
            logger.info("Scheduled SR recalculation job")

    async def _cleanup_checkpoints(self) -> None:
        """
        Remove LangGraph checkpoints for completed/failed generation jobs
        older than 7 days.

        LangGraph's PostgresSaver stores checkpoints in its own tables.
        Without cleanup, these grow indefinitely.
        """
        async with self.session_factory() as session:
            cutoff = datetime.utcnow() - timedelta(days=7)

            # Find thread IDs to clean up
            result = await session.execute(
                text("""
                    SELECT langgraph_thread_id
                    FROM generation_jobs
                    WHERE status IN ('published', 'failed')
                      AND updated_at < :cutoff
                      AND langgraph_thread_id IS NOT NULL
                """),
                {"cutoff": cutoff},
            )
            thread_ids = [row[0] for row in result.fetchall()]

            if not thread_ids:
                return

            # LangGraph PostgresSaver uses a 'langgraph_checkpoints' table
            # Clean up checkpoint data for these threads
            for thread_id in thread_ids:
                await session.execute(
                    text("""
                        DELETE FROM langgraph_checkpoints
                        WHERE thread_id = :thread_id
                    """),
                    {"thread_id": thread_id},
                )

            # Clear the thread_id reference
            await session.execute(
                text("""
                    UPDATE generation_jobs
                    SET langgraph_thread_id = NULL
                    WHERE langgraph_thread_id = ANY(:thread_ids)
                """),
                {"thread_ids": thread_ids},
            )

            await session.commit()
            logger.info("Cleaned up %d old checkpoints", len(thread_ids))
```

---

## 9. Progress via SSE

Generation job progress uses the same SSE infrastructure already built for chat streaming.

### 9.1 SSE Endpoint

```python
# src/routes/generation_jobs.py (new endpoint)

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter()

@router.get("/generation-jobs/{job_id}/progress")
async def stream_generation_progress(
    job_id: uuid.UUID,
    user: AdminUser,
    db: DBSession,
    request: Request,
):
    """
    SSE endpoint for real-time generation job progress.

    The client opens this connection and receives step-by-step updates
    as the generation pipeline runs. Same protocol as chat SSE.

    Events:
      event: progress
      data: {"step": "extracting", "pct": 20, "detail": "..."}

      event: review_required
      data: {"message": "Course ready for review"}

      event: completed
      data: {"course_id": "uuid", "manual_id": "uuid"}

      event: failed
      data: {"error": "..."}
    """
    return StreamingResponse(
        _progress_stream(job_id, db, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


async def _progress_stream(
    job_id: uuid.UUID,
    db: AsyncSession,
    request: Request,
):
    """
    Poll the generation_jobs table and yield SSE events.

    Polls every 2 seconds. Stops when the job reaches a terminal state
    (published, failed) or the client disconnects.
    """
    last_status = None

    while True:
        # Check client disconnect
        if await request.is_disconnected():
            return

        result = await db.execute(
            text("""
                SELECT status, progress, error_message,
                       result_course_id, result_manual_id
                FROM generation_jobs WHERE id = :job_id
            """),
            {"job_id": job_id},
        )
        job = result.mappings().first()

        if job is None:
            yield _sse_event("error", {"message": "Job not found"})
            return

        status = job["status"]

        # Only emit when status changes
        if status != last_status:
            last_status = status
            progress = job["progress"] or {}

            if status == "published":
                yield _sse_event("completed", {
                    "course_id": str(job["result_course_id"]),
                    "manual_id": str(job["result_manual_id"]),
                })
                return

            elif status == "failed":
                yield _sse_event("failed", {
                    "error": job["error_message"],
                })
                return

            elif status == "reviewing":
                yield _sse_event("review_required", {
                    "message": "Course ready for review",
                    "progress": progress,
                })
                # Don't return — admin might approve and pipeline continues

            else:
                yield _sse_event("progress", {
                    "step": status,
                    "pct": progress.get("pct", 0),
                    "steps_completed": progress.get("steps_completed", []),
                    "steps_remaining": progress.get("steps_remaining", []),
                })

        await asyncio.sleep(2)


def _sse_event(event_type: str, data: dict) -> str:
    """Format a Server-Sent Event."""
    import json
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
```

### 9.2 Frontend Integration

```ts
// src/api/generation.ts

export function streamGenerationProgress(
  jobId: string,
  callbacks: {
    onProgress: (data: { step: string; pct: number }) => void
    onReviewRequired: () => void
    onCompleted: (data: { course_id: string; manual_id: string }) => void
    onFailed: (data: { error: string }) => void
  },
): EventSource {
  const source = new EventSource(
    `/api/v1/generation-jobs/${jobId}/progress`,
  )

  source.addEventListener('progress', (e) => {
    callbacks.onProgress(JSON.parse(e.data))
  })

  source.addEventListener('review_required', () => {
    callbacks.onReviewRequired()
  })

  source.addEventListener('completed', (e) => {
    callbacks.onCompleted(JSON.parse(e.data))
    source.close()
  })

  source.addEventListener('failed', (e) => {
    callbacks.onFailed(JSON.parse(e.data))
    source.close()
  })

  return source // Caller can close() to disconnect
}
```

---

## 10. Monitoring

### 10.1 Structured Logging

All background workers use Python's `logging` module with structured context:

```python
# src/core/logging.py

import logging
import json
import sys

class JSONFormatter(logging.Formatter):
    """JSON log format for production. Human-readable in dev."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)


def setup_logging(debug: bool = False) -> None:
    """Configure logging for the application."""
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)

    if debug:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
        ))
    else:
        handler.setFormatter(JSONFormatter())

    logging.basicConfig(level=level, handlers=[handler])

    # Silence noisy libraries
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
```

Log output examples:

```
# Dev mode (human-readable)
2026-07-14 10:23:01 INFO     skillnet.workers.job_runner: Executing job a1b2c3 (type=document_ingestion)
2026-07-14 10:23:15 INFO     skillnet.workers.job_runner: Job a1b2c3 completed successfully
2026-07-14 10:23:16 WARNING  skillnet.workers.periodic: Stuck job detected and reset: id=d4e5f6 type=document_ingestion

# Production mode (JSON)
{"ts": "2026-07-14T10:23:01", "level": "INFO", "logger": "skillnet.workers.job_runner", "msg": "Executing job a1b2c3 (type=document_ingestion)"}
```

### 10.2 Health Check Endpoint

```python
# src/routes/health.py

from fastapi import APIRouter
from sqlalchemy import text

router = APIRouter()

@router.get("/health")
async def health_check(db: DBSession) -> dict:
    """
    Health check for the application and background workers.

    Returns the status of:
    - Database connection
    - Background job runner (pending/running/failed counts)
    - Generation worker (active jobs)
    - Periodic scheduler (last run times)
    """
    # Database connectivity
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"

    # Background jobs summary
    result = await db.execute(
        text("""
            SELECT status, COUNT(*) as count
            FROM background_jobs
            WHERE created_at > now() - interval '24 hours'
            GROUP BY status
        """)
    )
    job_counts = {row[0]: row[1] for row in result.fetchall()}

    # Generation jobs summary
    gen_result = await db.execute(
        text("""
            SELECT status, COUNT(*) as count
            FROM generation_jobs
            WHERE created_at > now() - interval '24 hours'
            GROUP BY status
        """)
    )
    gen_counts = {row[0]: row[1] for row in gen_result.fetchall()}

    # Stuck jobs (potential issues)
    stuck_result = await db.execute(
        text("""
            SELECT COUNT(*) FROM background_jobs
            WHERE status = 'running'
              AND locked_at < now() - interval '30 minutes'
        """)
    )
    stuck_count = stuck_result.scalar()

    return {
        "status": "healthy" if db_status == "ok" and stuck_count == 0 else "degraded",
        "database": db_status,
        "background_jobs_24h": job_counts,
        "generation_jobs_24h": gen_counts,
        "stuck_jobs": stuck_count,
    }
```

### 10.3 Stuck Job Detection and Admin Alerts

Stuck jobs detected by the periodic scheduler (section 8) are surfaced to admins through the existing alert system:

```python
# src/services/alert_service.py (additions)

async def _check_stuck_jobs(self, session: AsyncSession) -> list[Alert]:
    """Generate alerts for stuck background and generation jobs."""
    alerts = []

    # Stuck background jobs
    result = await session.execute(
        text("""
            SELECT id, type, locked_at
            FROM background_jobs
            WHERE status = 'running'
              AND locked_at < now() - interval '30 minutes'
        """)
    )
    for row in result.fetchall():
        alerts.append(Alert(
            type="stuck_job",
            severity="high",
            message=(
                f"Background job '{row[1]}' has been running since "
                f"{row[2].isoformat()} without progress"
            ),
            action_url="/admin/jobs",
            related_ids={"job_id": str(row[0])},
        ))

    # Failed generation jobs (last 24h)
    gen_result = await session.execute(
        text("""
            SELECT id, error_message, updated_at
            FROM generation_jobs
            WHERE status = 'failed'
              AND updated_at > now() - interval '24 hours'
        """)
    )
    for row in gen_result.fetchall():
        alerts.append(Alert(
            type="generation_failed",
            severity="medium",
            message=f"Course generation failed: {row[1][:100]}",
            action_url=f"/admin/generation-jobs/{row[0]}",
            related_ids={"generation_job_id": str(row[0])},
        ))

    return alerts
```

### 10.4 Admin Job Dashboard API

```python
# src/routes/generation_jobs.py (additions)

@router.get("/background-jobs")
async def list_background_jobs(
    user: AdminUser,
    db: DBSession,
    status: str | None = None,
    type: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> dict:
    """List background jobs with optional filters."""
    conditions = []
    params: dict = {"offset": offset, "limit": limit}

    if status:
        conditions.append("status = :status")
        params["status"] = status
    if type:
        conditions.append("type = :type")
        params["type"] = type

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    result = await db.execute(
        text(f"""
            SELECT id, type, status, payload, error_message,
                   attempt_count, max_attempts, created_at,
                   started_at, completed_at
            FROM background_jobs
            {where}
            ORDER BY created_at DESC
            OFFSET :offset LIMIT :limit
        """),
        params,
    )

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM background_jobs {where}"),
        params,
    )

    return {
        "items": [dict(row._mapping) for row in result.fetchall()],
        "total": count_result.scalar(),
    }
```

---

## 11. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Hybrid: LangGraph + PostgreSQL job runner** | Uses the right tool for each job type. No unnecessary abstractions. |
| **No Redis for MVP** | PostgreSQL `SELECT FOR UPDATE SKIP LOCKED` provides the same guarantees without a new dependency. At 1-5 jobs/day, polling every 5s is negligible load. |
| **In-process workers (no separate process)** | Single Docker container. One thing to deploy, monitor, and scale. Workers run as asyncio tasks in the FastAPI process. If needed later, workers can be extracted to a separate process without code changes. |
| **Polling over pub/sub for job dispatch** | Polling at 5s intervals on an indexed table is simple and reliable. Pub/sub (LISTEN/NOTIFY) adds complexity for negligible latency improvement at MVP scale. |
| **SSE for progress (not WebSocket)** | Same infrastructure as chat streaming. Unidirectional (server to client). No new protocol to support. |
| **Semaphore + DB lock (two-level concurrency)** | Semaphore prevents over-dispatch in-process. DB lock prevents double-claiming across processes. Correct now and when scaling later. |
| **Job handler registry pattern** | New job types are added by writing a function and decorating with `@register_job_handler("type")`. Zero boilerplate. |
| **Generation progress in DB, not in memory** | Progress survives restarts. Multiple frontends (tabs, devices) see the same state. No shared memory or broadcast needed. |
