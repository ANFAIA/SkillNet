---
title: "Procesamiento en segundo plano"
order: 10
section: "core"
---

# Procesamiento en Segundo Plano

> **Estado: v1.** Resuelve el punto **(abierto)** de [architecture.md](architecture.md): "Background processing. Ingestion and content generation are long-running tasks. Queue system (Celery, Dramatiq, etc.) vs LangGraph's built-in persistence."

---

## 1. Requisitos

SkillNet tiene varias operaciones que no pueden completarse dentro de un ciclo normal de peticion HTTP:

| Operacion | Duracion | Caracteristicas |
|-----------|----------|-----------------|
| Generacion de curso (pipeline de LLM) | 2-10 min | Multi-paso, necesita seguimiento de progreso, interrupcion para revision humana |
| Ingesta de documentos (parseo + chunking + embeddings) | 30s-3 min | Embeddings intensivos en CPU/GPU, reintento idempotente por chunk |
| Recalculo de repeticion espaciada | 10-60s | Lote periodico, sin usuario esperando |
| Importacion masiva de usuarios (CSV) | 5-30s | Seguimiento de errores por fila |
| Generacion de informe de feedback de curso | 15-45s | Llamada a LLM, un solo paso |
| Migracion del modelo de embeddings | 5-30 min | En segundo plano, interrumpible |

**Requisitos funcionales:**

1. **Seguimiento de progreso.** El admin ve que paso se esta ejecutando en los trabajos de generacion (extrayendo, estructurando, generando, revisando). Los empleados ven el estado de ingesta de los documentos subidos.
2. **Reintento a nivel de paso.** Si el paso 3/5 falla, se reintenta desde el paso 3, no desde el 1. Los pasos de generacion y los lotes de embeddings son reintentables individualmente.
3. **Limites de concurrencia.** Las llamadas a LLM son costosas y tienen limite de tasa. El sistema debe acotar los trabajos de generacion e ingesta simultaneos.
4. **Cancelacion.** Un admin puede cancelar un trabajo de generacion en curso. El sistema detiene el pipeline en el siguiente punto de control.
5. **Durabilidad ante reinicios.** Si el servidor se reinicia a mitad de una generacion, el trabajo se reanuda desde el ultimo punto de control, no desde cero.
6. **Sin latencia percibida por el usuario.** Todas las operaciones de larga duracion devuelven inmediatamente un ID de trabajo. El cliente sigue el progreso mediante polling o SSE.

**No-requisitos para el MVP:**

- Distribucion multi-nodo (despliegue en un unico servidor)
- Colas con prioridad (FIFO es suficiente a la escala del MVP)
- Limitacion de tasa por usuario (single-tenant, disparos solo desde admin)
- Programacion de trabajos desde la UI (solo tareas periodicas del sistema)

---

## 2. Evaluacion de Opciones

Se evaluaron cinco enfoques para un MVP self-hosted y single-tenant.

### 2.1 Persistencia de LangGraph (checkpointing integrado)

LangGraph ofrece `SqliteSaver` y `PostgresSaver` para persistir el estado del grafo entre nodos. El pipeline de generacion ya es un grafo de LangGraph con nodos definidos (extrayendo, estructurando, generando, revisando).

| Aspecto | Valoracion |
|--------|------------|
| **Encaje con el pipeline de generacion** | Excelente. El pipeline ya es un grafo. El checkpointing viene integrado. |
| **Interrupcion/reanudacion** | Nativa. `interrupt()` pausa el grafo, la entrada humana lo reanuda. |
| **Recuperacion ante caidas** | Automatica. Se carga el checkpoint y se reanuda desde el ultimo nodo completado. |
| **Encaje con ingesta/trabajos por lotes** | Pobre. No son workflows con forma de grafo. Forzarlos en LangGraph anade complejidad. |
| **Control de concurrencia** | Ninguno integrado. Hay que gestionarlo externamente. |
| **Dependencias** | Ya presentes (LangGraph es una dependencia central para la orquestacion de agentes). |

**Veredicto:** Perfecto para el pipeline de generacion. Herramienta equivocada para todo lo demas.

### 2.2 Celery + Redis

El estandar de la industria para tareas en segundo plano en Python.

| Aspecto | Valoracion |
|--------|------------|
| **Madurez** | Probado en batalla, ecosistema enorme. |
| **Reintento/concurrencia** | Excelente. Politicas de reintento por tarea, concurrencia de workers, limites de tasa. |
| **Monitorizacion** | Panel Flower, sistema de eventos rico. |
| **Dependencias** | Anade Redis (infraestructura nueva), Celery (libreria pesada), proceso worker separado. |
| **Despliegue** | Docker Compose crece: app + worker + Redis + beat (scheduler). |
| **Para un MVP single-tenant** | Sobreingenieria. La sobrecarga operativa de Redis + workers de Celery supera el beneficio cuando se ejecutan de 1 a 5 trabajos al dia. |

**Veredicto:** Herramienta correcta a escala. Demasiada infraestructura para un MVP que hace un puñado de trabajos diarios.

### 2.3 arq (cola async sobre Redis)

Alternativa async y ligera a Celery, construida sobre Redis.

| Aspecto | Valoracion |
|--------|------------|
| **Simplicidad** | Mucho mas simple que Celery. Async-nativo, boilerplate minimo. |
| **Dependencias** | Sigue requiriendo Redis. |
| **Caracteristicas** | Reintento basico, tareas cron, almacenamiento de resultados. Sin grafos de workflow. |
| **Comunidad** | Mas pequeña que Celery, menos probada en batalla. |

**Veredicto:** Mejor que Celery para este caso de uso, pero sigue requiriendo Redis, una dependencia que el sistema no necesita por lo demas.

### 2.4 FastAPI BackgroundTasks + Polling sobre BD

Usar `BackgroundTasks` integrado de FastAPI para fire-and-forget, con una tabla de base de datos que hace seguimiento del estado del trabajo.

| Aspecto | Valoracion |
|--------|------------|
| **Dependencias** | Cero. Usa el PostgreSQL y el FastAPI ya existentes. |
| **Simplicidad** | Muy simple para el camino feliz. |
| **Durabilidad** | Ninguna. `BackgroundTasks` se ejecuta en el propio proceso. Un reinicio del servidor pierde la tarea. Sin checkpoint, sin reintento. |
| **Concurrencia** | Manual (semaforos de asyncio). |
| **Seguimiento de progreso** | Via polling a la BD: funciona pero sin push. |

**Veredicto:** Demasiado fragil para trabajos de generacion de varios minutos. Aceptable solo para tareas de menos de 30s que puedan reintentarse desde cero.

### 2.5 Dramatiq

Cola de tareas respaldada por Redis o RabbitMQ. API mas simple que Celery, mejores valores por defecto.

| Aspecto | Valoracion |
|--------|------------|
| **Simplicidad** | Mas limpia que Celery, buen sistema de middleware. |
| **Dependencias** | Requiere Redis o RabbitMQ (el mismo problema que Celery/arq). |
| **Soporte async** | Limitado. Dramatiq es sync-first. SkillNet es async-first (FastAPI + asyncpg + AsyncOpenAI). |

**Veredicto:** Su diseño sync-first choca con la pila async de SkillNet. Sigue requiriendo un broker de mensajes.

### 2.6 Matriz Resumen

| Criterio | LangGraph | Celery+Redis | arq | BackgroundTasks+BD | Dramatiq |
|-----------|-----------|-------------|-----|-------------------|----------|
| Encaje con el pipeline de generacion | +++| + | + | -- | + |
| Encaje con trabajos genericos | -- | +++ | ++ | + | ++ |
| Cero dependencias nuevas | +++ | -- | -- | +++ | -- |
| Recuperacion ante caidas | +++ | ++ | + | -- | ++ |
| Async-nativo | ++ | + | +++ | +++ | -- |
| Complejidad para el MVP | ++ | -- | + | +++ | - |

---

## 3. Recomendacion: Enfoque Hibrido

Usar la herramienta adecuada para cada tipo de trabajo, sin nuevas dependencias de infraestructura.

### 3.1 Persistencia de LangGraph para el Pipeline de Generacion

El pipeline de generacion (creacion de curso + manual) ya esta modelado como un grafo de estado de LangGraph. Usar el `PostgresSaver` integrado de LangGraph para el checkpointing nos da:

- **Interrupcion/reanudacion** para la revision humana (el paso `reviewing` pausa el grafo, el admin revisa y aprueba/rechaza)
- **Recuperacion ante caidas** cargando el ultimo checkpoint y reanudando
- **Progreso a nivel de paso** leyendo que nodo esta ejecutando el grafo en cada momento
- **Sin dependencias nuevas**: LangGraph y PostgreSQL ya estan en la pila

### 3.2 Ejecutor de Trabajos sobre PostgreSQL para Todo lo Demas

Para ingesta, operaciones por lotes, generacion de informes y tareas periodicas, un ejecutor de trabajos ligero respaldado por una tabla `background_jobs` en PostgreSQL:

- **Concurrencia basada en reclamacion** usando `SELECT FOR UPDATE SKIP LOCKED`, el mismo patron que usan sistemas de trabajos en produccion (GoodJob, Que, Oban)
- **Reintento con backoff** registrado en la tabla `background_jobs`
- **Bucle de polling** dentro del proceso de FastAPI (sin worker separado)
- **asyncio.Semaphore** para limites de concurrencia por tipo de trabajo
- **Sin dependencias nuevas**: solo consultas a PostgreSQL

### 3.3 Por Que No Redis

Redis haria falta para Celery, arq o Dramatiq. Para un MVP con estas caracteristicas:

- Un unico servidor, un unico proceso
- 1-5 trabajos de generacion al dia
- 5-20 ingestas de documentos por semana
- 1 recalculo periodico de SR cada 6 horas

PostgreSQL ya esta ahi, ya conectado, ya con copias de seguridad. Añadir Redis significa:

- Otro contenedor en Docker Compose
- Otra capa de persistencia que respaldar
- Otro punto de fallo que monitorizar
- Configuracion de la conexion a Redis, limites de memoria, politicas de expulsion

Nada de esto esta justificado a la escala del MVP. Si SkillNet crece y necesita workers distribuidos o un despacho de trabajos por debajo del segundo, Redis puede añadirse entonces. La tabla `background_jobs` y la interfaz del ejecutor de trabajos se mantienen igual; solo cambia el mecanismo de despacho.

---

## 4. Diseño de la Arquitectura

### 4.1 Diagrama del Sistema

```
                        Aplicacion FastAPI (proceso unico)
    ┌──────────────────────────────────────────────────────────────────┐
    │                                                                  │
    │   ┌─────────────────────────────────────────────────────────┐   │
    │   │                   JobCoordinator                         │   │
    │   │  (arranca en el lifespan de la app, gestiona todo el     │   │
    │   │   trabajo en segundo plano)                              │   │
    │   └──────────┬──────────────┬──────────────┬────────────────┘   │
    │              │              │              │                     │
    │   ┌──────────▼──────┐ ┌────▼──────────┐ ┌▼────────────────┐   │
    │   │ GenerationWorker│ │BackgroundJob  │ │PeriodicScheduler│   │
    │   │                 │ │   Runner      │ │                 │   │
    │   │ Grafo LangGraph │ │ Bucle polling │ │ Bucle asyncio   │   │
    │   │ + PostgresSaver │ │ + semaforos   │ │ + tareas cron   │   │
    │   │                 │ │               │ │                 │   │
    │   │ Concurrencia    │ │ Tipos de      │ │ Tareas:         │   │
    │   │ maxima:         │ │ trabajo:      │ │ - recalc SR     │   │
    │   │ 2 simultaneos   │ │ - ingestion   │ │ - deteccion     │   │
    │   │                 │ │ - bulk_import │ │   atascados     │   │
    │   │                 │ │ - report_gen  │ │ - limpieza      │   │
    │   │                 │ │ - sr_recalc   │ │                 │   │
    │   │                 │ │ - embed_migr  │ │                 │   │
    │   └────────┬────────┘ └──────┬────────┘ └────────┬────────┘   │
    │            │                 │                    │             │
    │   ┌────────▼─────────────────▼────────────────────▼──────────┐ │
    │   │                     PostgreSQL                            │ │
    │   │  ┌──────────────┐  ┌───────────────┐  ┌──────────────┐  │ │
    │   │  │generation_jobs│  │background_jobs │  │langgraph     │  │ │
    │   │  │(+ langgraph  │  │(cola generica) │  │checkpoints   │  │ │
    │   │  │  thread_id)  │  │               │  │(PostgresSaver)│  │ │
    │   │  └──────────────┘  └───────────────┘  └──────────────┘  │ │
    │   └─────────────────────────────────────────────────────────┘ │
    │                                                                │
    │   ┌──────────────────────────────────────────────────────────┐ │
    │   │                  Stream SSE de Progreso                   │ │
    │   │  Misma infraestructura que el chat (StreamingResponse)    │ │
    │   └──────────────────────────────────────────────────────────┘ │
    └──────────────────────────────────────────────────────────────────┘
```

### 4.2 Nueva Tabla: `background_jobs`

Cola generica de trabajos para tareas de segundo plano que no son de generacion.

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
    locked_by       text,                       -- identificador del worker
    locked_at       timestamptz,
    scheduled_at    timestamptz NOT NULL DEFAULT now(),
    started_at      timestamptz,
    completed_at    timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Reclamar el siguiente trabajo de forma eficiente
CREATE INDEX idx_background_jobs_claimable
    ON background_jobs (scheduled_at)
    WHERE status = 'pending';

-- Encontrar trabajos atascados (en ejecucion pero con el lock caducado)
CREATE INDEX idx_background_jobs_stuck
    ON background_jobs (locked_at)
    WHERE status = 'running';

-- Listado del admin
CREATE INDEX idx_background_jobs_org_status
    ON background_jobs (org_id, status);
```

### 4.3 Cambios de Esquema en `generation_jobs`

La tabla existente `generation_jobs` gana columnas para la integracion con LangGraph y el reporte de progreso.

```sql
ALTER TABLE generation_jobs
    ADD COLUMN langgraph_thread_id text,
    ADD COLUMN progress jsonb NOT NULL DEFAULT '{}',
    ADD COLUMN cancelled_at timestamptz;

-- Estructura del JSON de progreso:
-- {
--   "current_step": "generating",
--   "steps_completed": ["extracting", "structuring"],
--   "steps_remaining": ["generating", "reviewing"],
--   "pct": 50,
--   "detail": "Generating module 3 of 5..."
-- }
```

### 4.4 Ejecutor de Trabajos en Segundo Plano

El bucle de polling central que reclama y ejecuta trabajos genericos en segundo plano.

```python
# src/workers/job_runner.py

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger("skillnet.workers.job_runner")

# Limites de concurrencia por tipo de trabajo
CONCURRENCY_LIMITS: dict[str, int] = {
    "document_ingestion": 3,
    "bulk_user_import": 1,
    "feedback_report": 2,
    "sr_recalculation": 1,
    "embedding_migration": 1,
    "checkpoint_cleanup": 1,
}

POLL_INTERVAL_SECONDS = 5
LOCK_TIMEOUT_MINUTES = 30  # Los trabajos bloqueados durante mas tiempo se consideran atascados
MAX_BACKOFF_SECONDS = 300  # 5 minutos maximo entre reintentos


class BackgroundJobRunner:
    """
    Ejecutor de trabajos respaldado por PostgreSQL usando SELECT FOR UPDATE SKIP LOCKED.

    Se ejecuta dentro del proceso de FastAPI como una tarea de asyncio. No hace
    falta un proceso worker separado. Reclama trabajos de la tabla background_jobs,
    los ejecuta con limites de concurrencia y registra los resultados.
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
        """Arranca el bucle de polling. Llamar desde el lifespan de FastAPI."""
        self._running = True
        logger.info("BackgroundJobRunner started (worker_id=%s)", self.worker_id)
        while self._running:
            try:
                await self._poll_and_dispatch()
            except Exception:
                logger.exception("Error in job runner poll loop")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def stop(self) -> None:
        """Apagado ordenado. Espera a que las tareas activas terminen."""
        self._running = False
        if self._active_tasks:
            logger.info(
                "Waiting for %d active tasks to complete...",
                len(self._active_tasks),
            )
            await asyncio.gather(*self._active_tasks, return_exceptions=True)
        logger.info("BackgroundJobRunner stopped")

    async def _poll_and_dispatch(self) -> None:
        """Reclama el siguiente trabajo disponible y lo despacha."""
        async with self.session_factory() as session:
            job = await self._claim_next_job(session)
            if job is None:
                return

            job_id, job_type, payload = job["id"], job["type"], job["payload"]
            semaphore = self._semaphores.get(job_type)

            if semaphore is not None and semaphore.locked():
                # Todos los huecos para este tipo de trabajo estan ocupados: liberar la reclamacion
                await self._release_claim(session, job_id)
                return

            task = asyncio.create_task(
                self._execute_job(job_id, job_type, payload, semaphore)
            )
            self._active_tasks.add(task)
            task.add_done_callback(self._active_tasks.discard)

    async def _claim_next_job(self, session: AsyncSession) -> dict | None:
        """
        Reclama atomicamente el siguiente trabajo pendiente usando SELECT FOR UPDATE SKIP LOCKED.

        Este patron garantiza:
        - Que dos workers no reclamen el mismo trabajo (lock a nivel de fila)
        - Que los workers no se bloqueen entre si (SKIP LOCKED salta las filas ya reclamadas)
        - Que los trabajos se procesen en orden de scheduled_at (FIFO)
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
        """Devuelve un trabajo reclamado al estado pending (limite de concurrencia alcanzado)."""
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
        """Ejecuta un trabajo con control de concurrencia basado en semaforo."""
        if semaphore:
            async with semaphore:
                await self._run_job(job_id, job_type, payload)
        else:
            await self._run_job(job_id, job_type, payload)

    async def _run_job(
        self, job_id: uuid.UUID, job_type: str, payload: dict
    ) -> None:
        """Ejecuta el handler real del trabajo y registra el resultado."""
        logger.info("Executing job %s (type=%s)", job_id, job_type)

        try:
            handler = JOB_HANDLERS.get(job_type)
            if handler is None:
                raise ValueError(f"No handler registered for job type: {job_type}")

            async with self.session_factory() as session:
                result = await handler(session, payload)

            # Marcar como completado
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
        """Gestiona el fallo de un trabajo: reintento con backoff o fallo permanente."""
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
                # Programar reintento con backoff exponencial
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
                # Fallo permanente
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


# --- Registro de handlers de trabajo ---

from typing import Callable, Awaitable

JobHandler = Callable[[AsyncSession, dict], Awaitable[dict | None]]

JOB_HANDLERS: dict[str, JobHandler] = {}


def register_job_handler(job_type: str):
    """Decorador para registrar un handler para un tipo de trabajo."""
    def decorator(func: JobHandler) -> JobHandler:
        JOB_HANDLERS[job_type] = func
        return func
    return decorator
```

### 4.5 Generation Worker

Envuelve el grafo de generacion de LangGraph con control de concurrencia y seguimiento de progreso.

```python
# src/workers/generation_worker.py

import asyncio
import logging
import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

logger = logging.getLogger("skillnet.workers.generation")

# Pasos del pipeline de generacion en orden (todos son nombres de nodos del grafo)
GENERATION_STEPS = [
    "extracting",
    "structuring",
    "generating",
    "structure_review",   # interrupcion: el admin revisa la estructura
    "reviewing",          # interrupcion: el admin revisa el contenido final
    "publishing",
    "published",
]

# Mapea los nombres de nodo del grafo a los valores de status de generation_jobs
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
    Gestiona los trabajos de generacion basados en LangGraph con checkpointing en PostgreSQL.

    Cada trabajo de generacion se ejecuta como una invocacion de un grafo de LangGraph.
    El grafo persiste su estado tras cada nodo mediante PostgresSaver, lo que permite:
    - Recuperacion ante caidas (recargar el checkpoint, reanudar desde el ultimo nodo)
    - Interrupcion para revision humana (el grafo se pausa en el nodo 'reviewing')
    - Seguimiento de progreso (leer el nodo actual desde el checkpoint)
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
        """Arranca el bucle de polling del generation worker."""
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
        """Apagado ordenado. Las generaciones activas continuan hasta su siguiente checkpoint."""
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
        """Busca trabajos de generacion pendientes y los despacha."""
        if self._semaphore.locked():
            return  # Todos los huecos ocupados

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

            # Asigna un thread ID de LangGraph si aun no lo tiene (trabajo nuevo)
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
        Ejecuta el pipeline de generacion via LangGraph.

        El grafo esta definido en src/agents/content/graph.py. Cada nodo
        (extract, structure, generate, review) es un nodo del grafo. El
        PostgresSaver persiste el estado tras completar cada nodo.
        """
        job_id = job["id"]

        async with self._semaphore:
            logger.info("Starting generation job %s (thread=%s)", job_id, thread_id)

            try:
                # Inicializa el checkpointer de LangGraph
                async with AsyncPostgresSaver.from_conn_string(
                    self.db_connection_string
                ) as checkpointer:
                    await checkpointer.setup()

                    # Importa el grafo de generacion
                    from src.agents.content.graph import build_content_graph

                    graph = build_content_graph(checkpointer=checkpointer)
                    config = {"configurable": {"thread_id": thread_id}}

                    # Comprueba si estamos reanudando desde un checkpoint
                    checkpoint = await checkpointer.aget(config)

                    if checkpoint is not None:
                        logger.info(
                            "Resuming job %s from checkpoint", job_id
                        )
                        # Reanudacion: el grafo continua desde donde lo dejo
                        async for event in graph.astream(None, config):
                            await self._update_progress(job_id, event)
                    else:
                        # Arranque en frio: se provee el estado inicial
                        initial_state = {
                            "job_id": str(job_id),
                            "org_id": str(job["org_id"]),
                            "source_document_ids": [str(job["source_document_id"])],
                            "output_type": job["output_type"],
                            "triggered_by": str(job["triggered_by"]),
                        }
                        async for event in graph.astream(initial_state, config):
                            await self._update_progress(job_id, event)

                    # Comprueba el estado final
                    final_state = await graph.aget_state(config)

                    if final_state.next:
                        # El grafo esta pausado (interrupcion de revision humana)
                        logger.info(
                            "Job %s paused for human review at: %s",
                            job_id, final_state.next,
                        )
                    else:
                        # El grafo se ha completado
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
        """Actualiza generation_jobs con el paso actual y la info de progreso."""
        # Los eventos de LangGraph incluyen el nombre del nodo que acaba de completarse
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
        """Marca un trabajo de generacion como publicado con exito."""
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
        """Marca un trabajo de generacion como fallido."""
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
        """Marca un trabajo de generacion como cancelado."""
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
        """Cancela un trabajo de generacion en ejecucion. Devuelve True si se cancelo."""
        task = self._active_tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            return True

        # Si no esta activamente en ejecucion, simplemente se marca como cancelado en la BD
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

Orquesta todos los workers de segundo plano. Se integra con el lifespan de FastAPI.

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
    Orquestador central para todo el procesamiento en segundo plano.

    Gestiona tres subsistemas:
    1. GenerationWorker — generacion de contenido basada en LangGraph
    2. BackgroundJobRunner — cola generica de trabajos respaldada por PostgreSQL
    3. PeriodicScheduler — tareas de mantenimiento recurrentes

    Se arranca durante el lifespan de FastAPI y se detiene en el shutdown.
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
        """Arranca todos los workers en segundo plano como tareas concurrentes de asyncio."""
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
        """Detiene todos los workers de forma ordenada."""
        logger.info("JobCoordinator stopping all workers...")

        await asyncio.gather(
            self.generation_worker.stop(),
            self.job_runner.stop(),
            self.periodic_scheduler.stop(),
            return_exceptions=True,
        )

        # Cancela cualquier tarea restante
        for task in self._tasks:
            if not task.done():
                task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("JobCoordinator: all workers stopped")
```

**Integracion con el lifespan de FastAPI:**

```python
# src/main.py (lifespan actualizado)

from src.workers.coordinator import JobCoordinator

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Arranque
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    coordinator = JobCoordinator(
        session_factory=async_session_factory,
        db_connection_string=settings.DATABASE_URL,
    )
    app.state.coordinator = coordinator
    await coordinator.start()

    yield

    # Apagado
    await coordinator.stop()
    await engine.dispose()
```

---

## 5. Ciclo de Vida de un Trabajo de Generacion

Flujo completo desde el clic del admin hasta el curso publicado.

### 5.1 Camino Feliz

```
El admin hace clic en "Generar curso a partir de documento"
  │
  ▼
POST /api/v1/courses/{id}/generate
  │
  ├─ Crea una fila en generation_jobs (status='pending')
  ├─ Devuelve { job_id: "uuid" } inmediatamente (202 Accepted)
  │
  ▼
El GenerationWorker recoge el trabajo (bucle de polling)
  │
  ├─ Reclama el trabajo (SELECT FOR UPDATE SKIP LOCKED)
  ├─ Asigna langgraph_thread_id
  ├─ Fija status='extracting'
  │
  ▼
El grafo de LangGraph ejecuta el nodo: EXTRACT
  │
  ├─ Lee el documento fuente de la BD / disco
  ├─ Extrae conceptos clave, temas, objetivos de aprendizaje
  ├─ PostgresSaver guarda el checkpoint del estado
  ├─ Actualiza generation_jobs.status='structuring'
  │
  ▼
El grafo de LangGraph ejecuta el nodo: STRUCTURE
  │
  ├─ Organiza los conceptos en modulos y lecciones
  ├─ Determina los tipos de ejercicio por leccion
  ├─ Mapea skills a modulos (sugerencias de checkpoint)
  ├─ PostgresSaver guarda el checkpoint del estado
  ├─ Actualiza generation_jobs.status='reviewing'
  │
  ▼
El grafo de LangGraph llega a la INTERRUPCION #1 en el nodo: STRUCTURE_REVIEW
  │
  ├─ El grafo se pausa (interrupt() de LangGraph)
  ├─ generation_jobs.status='reviewing'
  ├─ El admin recibe una notificacion: "Estructura del curso lista para revision"
  │
  ▼
El admin revisa la estructura propuesta (modulos, lecciones, mapeos de skills)
  │
  ├─ Puede reordenar modulos, renombrar lecciones, ajustar mapeos de skills
  ├─ Puede aprobar o solicitar una reestructuracion
  │
  ▼
POST /api/v1/generation-jobs/{id}/review  (con action='approve_structure')
  │
  ├─ Reanuda el grafo de LangGraph con el feedback humano
  ├─ El grafo continua hacia el nodo GENERATE con la estructura aprobada
  │
  ▼
El grafo de LangGraph ejecuta el nodo: GENERATE
  │
  ├─ Genera el contenido de las lecciones (llamadas a LLM, potencialmente varias)
  ├─ Genera los ejercicios por leccion
  ├─ Genera el contenido del manual
  ├─ PostgresSaver guarda el checkpoint del estado
  ├─ Actualiza generation_jobs.status='reviewing'
  │
  ▼
El grafo de LangGraph llega a la INTERRUPCION #2 en el nodo: REVIEW (revision final)
  │
  ├─ El grafo se pausa (interrupt() de LangGraph)
  ├─ generation_jobs.status='reviewing'
  ├─ El admin recibe una notificacion: "Contenido del curso listo para revision final"
  │
  ▼
El admin revisa el contenido generado en la UI
  │
  ├─ Puede editar lecciones individuales, ejercicios, orden de modulos
  ├─ Puede aprobar o solicitar la regeneracion de partes concretas
  │
  ▼
POST /api/v1/generation-jobs/{id}/review  (con action='approve_final')
  │
  ├─ Reanuda el grafo de LangGraph con el feedback humano
  ├─ El grafo ejecuta el nodo PUBLISH
  │
  ▼
El grafo de LangGraph ejecuta el nodo: PUBLISH
  │
  ├─ Escribe el curso, modulos, lecciones y ejercicios en la BD
  ├─ Escribe el manual en la BD
  ├─ Fija course.status='draft' (el admin publica manualmente)
  ├─ Actualiza generation_jobs.status='published'
  ├─ Enlaza result_course_id y result_manual_id
  │
  ▼
El admin publica cuando esta listo
  POST /api/v1/courses/{id}/publish
```

### 5.2 Fallo y Recuperacion

```
El servidor se cae durante el paso GENERATE
  │
  ▼
El servidor se reinicia
  │
  ├─ Arranca el JobCoordinator
  ├─ El GenerationWorker reanuda el polling
  │
  ▼
El GenerationWorker encuentra un trabajo con status='generating'
  │
  ├─ Carga langgraph_thread_id desde generation_jobs
  ├─ PostgresSaver carga el checkpoint de ese thread
  ├─ El checkpoint contiene el estado tras completarse STRUCTURE
  │
  ▼
El grafo de LangGraph se reanuda desde el nodo GENERATE
  │
  ├─ Se saltan EXTRACT y STRUCTURE (ya con checkpoint)
  ├─ Continua la generacion desde donde se quedo
  │
  ▼
El flujo normal continua...
```

### 5.3 Cancelacion

```
El admin hace clic en "Cancelar" sobre un trabajo de generacion en curso
  │
  ▼
DELETE /api/v1/generation-jobs/{id}
  │
  ├─ Llama a GenerationWorker.cancel_job(job_id)
  ├─ Si esta activamente en ejecucion: task.cancel() → CancelledError en el siguiente await
  ├─ Si esta pendiente/pausado: se marca como fallido con 'Cancelled by user'
  │
  ▼
El trabajo se marca como fallido con un timestamp cancelled_at
```

---

## 6. Ciclo de Vida de la Ingesta de Documentos

### 6.1 Flujo de Extremo a Extremo

```
El admin sube un documento
  │
  ▼
POST /api/v1/documents (subida multipart)
  │
  ├─ Guarda el fichero en disco (directorio uploads/)
  ├─ Crea una fila en documents (status='pending')
  ├─ Devuelve los metadatos del documento inmediatamente
  │
  ▼
POST /api/v1/documents/{id}/process
  │
  ├─ Crea una fila en background_jobs:
  │     type='document_ingestion'
  │     payload={ "document_id": "uuid", "file_path": "..." }
  ├─ Devuelve 202 Accepted
  │
  ▼
El BackgroundJobRunner reclama el trabajo
  │
  ├─ SELECT FOR UPDATE SKIP LOCKED
  ├─ Adquiere el semaforo de ingesta (maximo 3 concurrentes)
  │
  ▼
Se ejecuta el handler de ingesta (ver rag-retrieval.md seccion 3.1)
  │
  ├─ Parsea el documento (pymupdf / python-docx)
  ├─ Limpia y normaliza el texto
  ├─ Decide la estrategia (full_text vs chunk+embed)
  │
  ├── Camino de documento pequeño (<=3 paginas):
  │     Guarda full_text en la fila de documents → listo
  │
  ├── Camino de documento grande:
  │     ├─ Divide por secciones (semantico + fallback de tamaño fijo)
  │     ├─ Genera embeddings por lotes (multilingual-e5-small, lotes de 64)
  │     │   └─ Por lote: si un lote falla, se reintenta solo ese lote
  │     ├─ Guarda los chunks en document_chunks
  │     └─ Actualiza documents.status='ready'
  │
  ▼
background_jobs.status='completed'
documents.status='ready'
```

### 6.2 Reintento Idempotente

Si la ingesta falla a mitad del embedding (p. ej., el lote 4 de 7 sufre un error de OOM), la estrategia de reintento es:

```python
# src/workers/handlers/ingestion.py

from src.workers.job_runner import register_job_handler

@register_job_handler("document_ingestion")
async def handle_document_ingestion(
    session: AsyncSession, payload: dict
) -> dict | None:
    """
    Handler de ingesta con reintento idempotente.

    En cada reintento, se saltan los chunks que ya tienen embeddings guardados.
    Esto evita re-generar embeddings de cientos de chunks porque fallo el lote 6/7.
    """
    document_id = UUID(payload["document_id"])
    file_path = Path(payload["file_path"])

    doc = await session.get(Document, document_id)
    doc.status = "processing"
    await session.commit()

    try:
        # Parseo y chunking (rapido, seguro de rehacer)
        sections = parse_document(file_path)
        full_text = "\n\n".join(s.content for s in sections)
        estimated_pages = max(1, count_tokens(full_text) // 750)

        if estimated_pages <= 3:
            doc.full_text = full_text
            doc.status = "ready"
            await session.commit()
            return {"strategy": "full_text", "pages": estimated_pages}

        chunks = chunk_sections(sections, document_id, doc.title)

        # Comprueba que chunks ya existen (reintento idempotente)
        existing = await session.execute(
            text("""
                SELECT chunk_index FROM document_chunks
                WHERE document_id = :doc_id AND embedding IS NOT NULL
            """),
            {"doc_id": document_id},
        )
        existing_indices = {row[0] for row in existing}

        # Filtra solo los chunks sin embedding
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
        raise  # Se relanza para que el job runner gestione el reintento/fallo
```

---

## 7. Control de Concurrencia

### 7.1 Limites por Tipo de Trabajo

| Tipo de trabajo | Concurrencia maxima | Razonamiento |
|----------|---------------|-----------|
| Generacion (LangGraph) | 2 | Cada trabajo de generacion hace muchas llamadas a LLM. 2 concurrentes evita limites de tasa y mantiene los costes predecibles. |
| Ingesta de documentos | 3 | El embedding intensivo en CPU es el cuello de botella. 3 concurrentes satura un servidor tipico de 4 nucleos sin sobrecargarlo. |
| Recalculo de SR | 1 | Operacion de BD por lotes. Ejecutar varias simultaneamente bloquearia filas y causaria contencion. |
| Importacion masiva de usuarios | 1 | Secuencial por naturaleza (filas de CSV). En paralelo arriesgaria conflictos de email duplicado. |
| Informe de feedback | 2 | Una sola llamada a LLM cada uno. Coste bajo, se puede paralelizar. |
| Migracion de embeddings | 1 | Escaneo completo de tabla + actualizaciones por lotes. Debe ser exclusiva. |

### 7.2 Implementacion

La concurrencia se aplica en dos niveles:

**Nivel 1: asyncio.Semaphore (en el proceso)**

```python
# Cada tipo de worker mantiene un semaforo
self._generation_semaphore = asyncio.Semaphore(2)
self._ingestion_semaphore = asyncio.Semaphore(3)
```

Esto evita que el proceso unico lance demasiadas tareas concurrentes. Es rapido, sin sobrecarga, y suficiente para un despliegue de un unico proceso.

**Nivel 2: SELECT FOR UPDATE SKIP LOCKED (base de datos)**

```sql
SELECT id FROM background_jobs
WHERE status = 'pending'
  AND scheduled_at <= now()
ORDER BY scheduled_at
FOR UPDATE SKIP LOCKED
LIMIT 1
```

Esto evita que multiples procesos (si alguna vez se despliegan) reclamen el mismo trabajo. `SKIP LOCKED` implica que los workers nunca se bloquean entre si: si una fila esta bloqueada, la consulta pasa a la siguiente.

**Por que ambos niveles:** El semaforo evita el sobre-despacho dentro del proceso. El lock de base de datos evita la doble reclamacion entre procesos. Juntos ofrecen un control de concurrencia correcto ahora (proceso unico) y en el futuro (multiples procesos).

---

## 8. Periodic Scheduler

### 8.1 Calendario de Tareas

| Tarea | Intervalo | Que hace |
|------|----------|-------------|
| `spaced_repetition_recalc` | Cada 6 horas | Recalcula `next_review_at` para todas las entradas de repeticion espaciada cuyo momento de revision calculado pueda haber derivado. Inserta una fila en `background_jobs` de tipo `sr_recalculation`. |
| `stuck_job_detection` | Cada 15 minutos | Busca trabajos con `status='running'` y `locked_at` con mas de 30 minutos de antiguedad. Los devuelve a `pending` para reintentarlos. Registra un aviso. |
| `checkpoint_cleanup` | Cada 24 horas | Elimina los checkpoints de LangGraph de trabajos de generacion completados o fallidos hace mas de 7 dias. Evita un crecimiento de almacenamiento sin limite. |

### 8.2 Implementacion

```python
# src/workers/periodic_scheduler.py

import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger("skillnet.workers.periodic")


class PeriodicTask:
    """Define una tarea recurrente con su intervalo y su handler."""

    def __init__(self, name: str, interval_seconds: int, handler):
        self.name = name
        self.interval_seconds = interval_seconds
        self.handler = handler
        self.last_run: datetime | None = None


class PeriodicScheduler:
    """
    Planificador de tareas periodicas simple basado en asyncio.

    Sin dependencias externas. Se ejecuta como una tarea de asyncio dentro
    del proceso de FastAPI. Cada tarea tiene un intervalo fijo y se ejecutan
    secuencialmente (una a la vez) para evitar contencion de recursos.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory
        self._running = False
        self._tasks = [
            PeriodicTask(
                name="stuck_job_detection",
                interval_seconds=15 * 60,  # 15 minutos
                handler=self._detect_stuck_jobs,
            ),
            PeriodicTask(
                name="spaced_repetition_recalc",
                interval_seconds=6 * 60 * 60,  # 6 horas
                handler=self._schedule_sr_recalc,
            ),
            PeriodicTask(
                name="checkpoint_cleanup",
                interval_seconds=24 * 60 * 60,  # 24 horas
                handler=self._cleanup_checkpoints,
            ),
        ]

    async def start(self) -> None:
        """Arranca el bucle del planificador periodico."""
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
            await asyncio.sleep(60)  # Comprueba cada minuto

    async def stop(self) -> None:
        """Detiene el planificador."""
        self._running = False
        logger.info("PeriodicScheduler stopped")

    async def _detect_stuck_jobs(self) -> None:
        """
        Encuentra y recupera trabajos atascados.

        Un trabajo esta atascado si tiene status='running' pero su lock ha
        caducado (locked_at con mas antiguedad que LOCK_TIMEOUT_MINUTES).
        Esto ocurre cuando:
        - El proceso se cayo a mitad del trabajo
        - Un handler de trabajo se quedo colgado indefinidamente
        - Timeout de red en una llamada externa (API de LLM)
        """
        async with self.session_factory() as session:
            cutoff = datetime.utcnow() - timedelta(minutes=30)

            # Restablece los background_jobs atascados
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

            # Comprueba generation_jobs atascados
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
                # Se restablece a pending para que el GenerationWorker lo recoja
                # y lo reanude desde el checkpoint
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
        Inserta un background job para el recalculo de repeticion espaciada.

        El recalculo real se ejecuta como un background_job, no en linea,
        de modo que respeta los limites de concurrencia y puede reintentarse
        ante un fallo.
        """
        async with self.session_factory() as session:
            # Comprueba si ya hay uno pendiente o en ejecucion
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

            # Obtiene el org_id (single-tenant)
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
        Elimina los checkpoints de LangGraph de trabajos de generacion
        completados/fallidos con mas de 7 dias de antiguedad.

        El PostgresSaver de LangGraph guarda los checkpoints en sus propias
        tablas. Sin limpieza, crecerian indefinidamente.
        """
        async with self.session_factory() as session:
            cutoff = datetime.utcnow() - timedelta(days=7)

            # Encuentra los thread IDs a limpiar
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

            # El PostgresSaver de LangGraph usa una tabla 'langgraph_checkpoints'
            # Se limpian los datos de checkpoint de estos threads
            for thread_id in thread_ids:
                await session.execute(
                    text("""
                        DELETE FROM langgraph_checkpoints
                        WHERE thread_id = :thread_id
                    """),
                    {"thread_id": thread_id},
                )

            # Limpia la referencia al thread_id
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

## 9. Progreso via SSE

El progreso de los trabajos de generacion usa la misma infraestructura SSE ya construida para el streaming del chat.

### 9.1 Endpoint SSE

```python
# src/routes/generation_jobs.py (nuevo endpoint)

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
    Endpoint SSE para el progreso en tiempo real de un trabajo de generacion.

    El cliente abre esta conexion y recibe actualizaciones paso a paso
    mientras se ejecuta el pipeline de generacion. Mismo protocolo que el SSE del chat.

    Eventos:
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
            "X-Accel-Buffering": "no",  # Desactiva el buffering de nginx
        },
    )


async def _progress_stream(
    job_id: uuid.UUID,
    db: AsyncSession,
    request: Request,
):
    """
    Sondea la tabla generation_jobs y emite eventos SSE.

    Sondea cada 2 segundos. Se detiene cuando el trabajo alcanza un estado
    terminal (published, failed) o el cliente se desconecta.
    """
    last_status = None

    while True:
        # Comprueba la desconexion del cliente
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

        # Solo emite cuando el status cambia
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
                # No hace return: el admin puede aprobar y el pipeline continua

            else:
                yield _sse_event("progress", {
                    "step": status,
                    "pct": progress.get("pct", 0),
                    "steps_completed": progress.get("steps_completed", []),
                    "steps_remaining": progress.get("steps_remaining", []),
                })

        await asyncio.sleep(2)


def _sse_event(event_type: str, data: dict) -> str:
    """Formatea un Server-Sent Event."""
    import json
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
```

### 9.2 Integracion en el Frontend

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

  return source // El llamante puede invocar close() para desconectarse
}
```

---

## 10. Monitorizacion

### 10.1 Logging Estructurado

Todos los workers de segundo plano usan el modulo `logging` de Python con contexto estructurado:

```python
# src/core/logging.py

import logging
import json
import sys

class JSONFormatter(logging.Formatter):
    """Formato de log JSON para produccion. Legible por humanos en dev."""

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
    """Configura el logging de la aplicacion."""
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)

    if debug:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
        ))
    else:
        handler.setFormatter(JSONFormatter())

    logging.basicConfig(level=level, handlers=[handler])

    # Silencia las librerias ruidosas
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
```

Ejemplos de salida de log:

```
# Modo dev (legible por humanos)
2026-07-14 10:23:01 INFO     skillnet.workers.job_runner: Executing job a1b2c3 (type=document_ingestion)
2026-07-14 10:23:15 INFO     skillnet.workers.job_runner: Job a1b2c3 completed successfully
2026-07-14 10:23:16 WARNING  skillnet.workers.periodic: Stuck job detected and reset: id=d4e5f6 type=document_ingestion

# Modo produccion (JSON)
{"ts": "2026-07-14T10:23:01", "level": "INFO", "logger": "skillnet.workers.job_runner", "msg": "Executing job a1b2c3 (type=document_ingestion)"}
```

### 10.2 Endpoint de Health Check

```python
# src/routes/health.py

from fastapi import APIRouter
from sqlalchemy import text

router = APIRouter()

@router.get("/health")
async def health_check(db: DBSession) -> dict:
    """
    Health check para la aplicacion y los workers en segundo plano.

    Devuelve el estado de:
    - Conexion a la base de datos
    - Ejecutor de trabajos en segundo plano (conteos de pending/running/failed)
    - Generation worker (trabajos activos)
    - Periodic scheduler (ultimas ejecuciones)
    """
    # Conectividad a la base de datos
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"

    # Resumen de background jobs
    result = await db.execute(
        text("""
            SELECT status, COUNT(*) as count
            FROM background_jobs
            WHERE created_at > now() - interval '24 hours'
            GROUP BY status
        """)
    )
    job_counts = {row[0]: row[1] for row in result.fetchall()}

    # Resumen de generation jobs
    gen_result = await db.execute(
        text("""
            SELECT status, COUNT(*) as count
            FROM generation_jobs
            WHERE created_at > now() - interval '24 hours'
            GROUP BY status
        """)
    )
    gen_counts = {row[0]: row[1] for row in gen_result.fetchall()}

    # Trabajos atascados (posibles problemas)
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

### 10.3 Deteccion de Trabajos Atascados y Alertas al Admin

Los trabajos atascados detectados por el periodic scheduler (seccion 8) se muestran a los admins a traves del sistema de alertas ya existente:

```python
# src/services/alert_service.py (adiciones)

async def _check_stuck_jobs(self, session: AsyncSession) -> list[Alert]:
    """Genera alertas para background jobs y generation jobs atascados."""
    alerts = []

    # Background jobs atascados
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

    # Generation jobs fallidos (ultimas 24h)
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

### 10.4 API del Panel de Trabajos del Admin

```python
# src/routes/generation_jobs.py (adiciones)

@router.get("/background-jobs")
async def list_background_jobs(
    user: AdminUser,
    db: DBSession,
    status: str | None = None,
    type: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> dict:
    """Lista background jobs con filtros opcionales."""
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

## 11. Decisiones de Diseño Clave

| Decision | Razonamiento |
|----------|-----------|
| **Hibrido: LangGraph + ejecutor de trabajos sobre PostgreSQL** | Usa la herramienta adecuada para cada tipo de trabajo. Sin abstracciones innecesarias. |
| **Sin Redis para el MVP** | `SELECT FOR UPDATE SKIP LOCKED` de PostgreSQL ofrece las mismas garantias sin una dependencia nueva. A 1-5 trabajos/dia, un polling cada 5s es una carga insignificante. |
| **Workers en el mismo proceso (sin proceso separado)** | Un unico contenedor Docker. Una sola cosa que desplegar, monitorizar y escalar. Los workers se ejecutan como tareas de asyncio dentro del proceso de FastAPI. Si hace falta mas adelante, se pueden extraer a un proceso separado sin cambios de codigo. |
| **Polling en vez de pub/sub para el despacho de trabajos** | El polling a intervalos de 5s sobre una tabla indexada es simple y fiable. Pub/sub (LISTEN/NOTIFY) añade complejidad por una mejora de latencia despreciable a la escala del MVP. |
| **SSE para el progreso (no WebSocket)** | Misma infraestructura que el streaming del chat. Unidireccional (del servidor al cliente). Sin protocolo nuevo que soportar. |
| **Semaforo + lock de BD (concurrencia en dos niveles)** | El semaforo evita el sobre-despacho dentro del proceso. El lock de BD evita la doble reclamacion entre procesos. Correcto ahora y al escalar mas adelante. |
| **Patron de registro de handlers de trabajo** | Los tipos de trabajo nuevos se añaden escribiendo una funcion y decorandola con `@register_job_handler("type")`. Boilerplate cero. |
| **Progreso de generacion en BD, no en memoria** | El progreso sobrevive a los reinicios. Multiples frontends (pestañas, dispositivos) ven el mismo estado. No hace falta memoria compartida ni broadcast. |
