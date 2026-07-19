# CLAUDE.md — SkillNet

## Estado actual (2026-07-18)

### 1. Arrancar Docker Desktop (si no esta corriendo)
```bash
powershell.exe -Command "Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe'"
```
Esperar ~30s. Verificar: `docker ps`
Docker CLI necesita PATH: `export PATH="/c/Program Files/Docker/Docker/resources/bin:$PATH"`

### 2. Levantar SkillNet
```bash
cd C:\Users\sonde\Documents\Trabajo\Anfaia\repo
docker compose up --build -d
```
Acceder a `http://localhost:3000`

### 3. Credenciales de prueba
- Admin: admin@skillnet.dev / admin123
- Empleado: empleado@skillnet.dev / empleado123
- LLM: DeepSeek (API key en .env)

### 4. Tareas pendientes v1
- [ ] Probar e2e: subir doc → generar curso → empleado toma curso → ejercicios → chat
- [ ] Iterar prompts de generacion con docs reales hasta que salgan cursos usables
- [ ] Los features ya implementados (editar curso, dashboard real, reset password) necesitan test e2e
- [ ] Commitear los 3 fixes del primer despliegue (access_token FK, stats union_all, CreateCourse TS)

### 5. Contexto del repo
- Backend: `apps/skillnet-api/` (FastAPI + LangGraph + pgvector)
- Frontend: `apps/skillnet-web/` (React 19 + TanStack Query)
- Docker: `docker-compose.yml` (db + api + web)
- `.env` ya creado con DeepSeek config
- Git: solo rama `main`, autoria solo de Jose, sin Co-Authored-By
- Vault de Obsidian: `C:\Users\sonde\Documents\Obsidian Vault\15_TRABAJO\SkillNet\`
- NUNCA usar memoria de Claude (.claude/memory/), usar el vault de Obsidian

### 6. Bugs arreglados en primer despliegue (2026-07-18)
- `access_token.py`: FK apuntaba a tabla "user" (fastapi-users default) en vez de "users" → override user_id
- `stats.py`: CompoundSelect.union_all() no funciona encadenado en SQLAlchemy 2.x → usar union_all() como funcion
- `CreateCourse.tsx`: BadgeVariant "default" no existe → "primary", ExerciseContent cast → double cast via unknown
