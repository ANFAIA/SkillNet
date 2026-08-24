---
title: "Guía rápida"
order: 1
section: "start"
---

# Ejecutar SkillNet

En orden, de arriba a abajo. Nada que saltarse, y solo una cosa que decidir (paso 2).

Si eres un agente de IA y te han pedido "arrancar el proyecto", este fichero es la respuesta completa.
Todo lo demás es detalle que todavía no necesitas.

## Paso 0 — Lo que necesitas

Docker con Compose v2. `docker compose version` debe imprimir 2.x.

Nada más: Python, Node y PostgreSQL corren todos dentro de los contenedores.

## Paso 1 — Clonar y copiar la configuración

```bash
git clone https://github.com/ANFAIA/SkillNet.git
cd SkillNet
cp .env.example .env
```

## Paso 2 — Decidir qué lo impulsa

Esta es la única decisión real, y todo lo demás se deriva de ella. Elige una fila, pon esos
valores en tu `.env`, y sigue adelante.

| Quiero usar… | Poner en `.env` | Qué te cuesta |
|---|---|---|
| **Una clave de API** *(recomendado)* | `LLM_API_KEY=sk-…` — nada más | Rápido: segundos por pantalla, alrededor de 0.01 USD por curso generado. Los valores por defecto `gpt-4o-mini` y `text-embedding-3-small` ya coinciden con el esquema de la base de datos y ambos funcionan con esta única clave. Cualquier proveedor de [litellm](https://docs.litellm.ai/docs/providers) funciona en su lugar — pon `LLM_MODEL=anthropic/claude-sonnet-4-20250514`, `deepseek/deepseek-chat`, `groq/llama-3.1-8b-instant`… |
| **Un modelo local** | Nada — usa el overlay del paso 3 | Gratis, privado, sin conexión. Pero **lento**: medido ~185 s para generar una pantalla de lección en CPU. Necesita ~8 GB de RAM y ~5 GB de disco. Bien para probarlo sin cuenta; no es cómodo para uso real. |
| **Nada en absoluto** | `LLM_MODEL=fixture/local` y `EMBEDDING_MODEL=fixture/local` | Gratis e instantáneo, pero solo se renderizan las pantallas con una respuesta grabada. Suficiente para navegar por la interfaz; no para autorar un curso. |

Elijas lo que elijas, siempre hacen falta dos valores:

| Variable | Cómo rellenarla |
|---|---|
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `POSTGRES_PASSWORD` | El mismo generador. **Solo letras, dígitos, `-` y `_`** |

La restricción de la contraseña no es una preferencia de estilo. Se interpola en una URL de
conexión sin escapar, así que un `@`, `:`, `/` o `#` — exactamente lo que produce un gestor de
contraseñas — rompe la URL, y la API entonces falla al acceder a la base de datos con un error
que nunca menciona la contraseña.

`.env.example` ya trae credenciales de demo funcionando (`admin@skillnet.dev` / `admin123`),
así que no hay nada más que configurar. Los cursos dinámicos (v2) no necesitan ningún flag — los
datos de la semilla ya incluyen un curso dinámico validado, y cualquier curso nuevo puede optar
por ello por curso.

## Paso 3 — Arrancarlo

```bash
docker compose up -d --build
```

O, si elegiste el modelo local en el paso 2:

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up -d --build
```

Una construcción en frío tarda un par de minutos. El overlay de ollama también descarga los
modelos (unos cuantos GB) antes de que la API arranque, así que dale tiempo al primer arranque.
Ver [`docker-compose.ollama.yml`](docker-compose.ollama.yml) para saber qué hace y qué ids de
modelo son válidos.

## Paso 4 — Cargar los datos de demo

**Este paso es para *explorar* la demo.** Un despliegue real se lo salta: creas tu propio
contenido en la aplicación — subes un documento o describes un tema y dejas que genere un
curso. Ejecuta esto solo si quieres el ejemplo ya preparado para navegar.

```bash
docker compose exec api uv run python -m src.seed_learning_demo
```

El arranque crea la organización y el usuario administrador, pero ningún curso, documento ni
empleado. Sin esta semilla entras a un panel vacío — que es exactamente lo correcto para una
instalación nueva, y simplemente una base de datos vacía si tu intención era probar la demo.

Esta semilla es la demo pública y de marca propia de SkillNet, sobre el tema meta de **cómo
aprendemos**: cuatro cursos cortos estilo Brilliant ("Cómo aprende tu cerebro", "Sesgos
cognitivos", "La ciencia de los hábitos", "Memoria y olvido"), todos generados y validados en el
momento de la semilla, más tres aprendices demo con estilos de aprendizaje declarados distintos.
El curso escaparate lleva un podcast y una infografía por nodo para que aparezcan los
componentes multimedia dentro de la lección; los otros tres llevan un podcast a nivel de curso.
Es idempotente y reejecutable (reutiliza un curso ya validado con el mismo título), e imprime
cada cuenta y el resultado por curso. La generación se apoya en el LLM, así que una ejecución
completa es lenta — eso es esperado.

> La demo anterior (una panadería-cafetería española) se ha retirado y eliminado del código.
> `seed_learning_demo` es la demo pública por defecto; al ejecutarse también limpia cualquier
> resto de datos de la panadería-cafetería en el org por defecto de las bases de datos de dev
> que todavía los arrastren.

También hay una semilla v1 mucho más pequeña, `src.seed_demo` (1 empleado y 16 skills), que es
anterior a los cursos dinámicos y existe para comparar con la ruta estática antigua.

### Modo de espacio de trabajo individual

Por defecto, un despliegue corre en modo `organization` (una empresa/equipo/clase, el flujo de
arriba). El otro modo es `individual`: una persona que instala SkillNet para sí misma y a la vez
administra y aprende — sin empleados, talento, asignaciones ni informes de organización. Ver
[`docs/design/audience-modes.md`](docs/design/audience-modes.md).

El modo es un ajuste estable por despliegue, elegido de una de estas dos formas:

- **Asistente de primer arranque (UI).** Si dejas `ADMIN_EMAIL`/`ADMIN_PASSWORD` sin definir, la
  primera vez que abres la aplicación muestra una pantalla `/setup`: eliges el modo
  (Organización / Solo yo), creas el propietario, y quedas conectado. El asistente se cierra
  definitivamente en cuanto existe un propietario.
- **Sin interfaz (`.env`).** Define el propietario y el modo antes del primer arranque (el modo
  solo se lee cuando se crea la fila de organización por primera vez):

  ```bash
  WORKSPACE_MODE=individual   # en tu .env, junto a ADMIN_EMAIL / ADMIN_PASSWORD
  ```

## Paso 5 — Abrirlo

<http://localhost:3000>

| Rol | Email | Contraseña |
|------|-------|----------|
| **Admin** | `admin@skillnet.dev` | `admin123` |
| Aprendiz — metáforas + audio (ve el podcast dentro de la lección) | `ana@skillnet.dev` | `aprender2026` |
| Aprendiz — definiciones primero + visual (ve la infografía dentro de la lección) | `bruno@skillnet.dev` | `aprender2026` |
| Aprendiz — **sin** perfil, para recorrer el asistente de onboarding | `carla@skillnet.dev` | `aprender2026` |

Conéctate como admin para autorar cursos, o como empleado para tomarlos.

## ¿Funcionó?

```bash
curl http://localhost:3000/api/v1/health
```

`database` debe decir `connected` y `embeddings.status` debe decir `ok`.

Si `embeddings.status` es `mismatch`, la respuesta también indica exactamente qué cambiar. Vale
la pena comprobarlo, porque una dimensión de embedding equivocada es la única mala configuración
que falla en silencio: los documentos parecen ingeridos pero nada puede recuperarlos, y el tutor
responde desde fuentes más débiles sin decirlo.

## Desarrollar el frontend (recarga en caliente)

El contenedor `web` en `:3000` es la construcción de **producción** — una imagen nginx generada
en `docker compose build`. Reconstruirla por cada retoque de CSS es la vía lenta y **no** es
cómo se desarrolla la UI. Para trabajo de frontend, ejecuta la API y la base de datos en Docker
y el frontend con **Vite en el host**, que recarga en caliente al guardar:

```bash
# 1. API + BD en Docker (el overlay de dev publica la API en 127.0.0.1:8000)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db api

# 2. Frontend en el host — lo único que necesita Node (≥20) + pnpm en local
pnpm --dir apps/skillnet-web install      # solo la primera vez
pnpm --dir apps/skillnet-web dev          # servidor de desarrollo de Vite
```

Luego abre **<http://localhost:5173>** (el puerto de Vite), **no** el 3000. Vite proxya `/api`
hacia `http://127.0.0.1:8000`, así que habla con la API dockerizada; apúntalo a otro sitio con
`SKILLNET_API_PROXY`. Edita cualquier cosa bajo `apps/skillnet-web/src` y el cambio aparece al
instante — **sin `docker compose build web`**.

Reconstruye el contenedor `web` solo para comprobar el paquete de producción real:
`docker compose build web && docker compose up -d web` → servido en `:3000`.

## Cuando algo va mal

| Síntoma | Causa |
|---|---|
| `docker compose up` se queja de una variable que falta | `SECRET_KEY` o `POSTGRES_PASSWORD` está vacía en `.env` |
| La API no puede llegar a la base de datos, el error no menciona la contraseña | La contraseña contiene `@`, `:`, `/`, `#` o `?`. Ver paso 2 |
| El panel está vacío tras iniciar sesión | Se saltó el paso 4 |
| `embeddings.status: mismatch` en `/health` | `EMBEDDING_DIMENSIONS` no coincide con la columna. El mensaje dice qué hacer |
| Los cursos existen pero se abren en blanco, usando `fixture/local` | No hay grabación para ese prompt. Esperado; usa una clave de API o el modelo local |
| Algo en `.env` parece estar siendo ignorado | Probablemente lo es. Solo las variables listadas en `docker-compose.yml` llegan al contenedor — no hay `env_file`. Añádela al bloque `environment:` de `api` |

Logs: `docker compose logs -f api`.

## Puertos

Un `docker compose up -d` por defecto publica **solo el 3000**. La API y la base de datos son
accesibles solo desde dentro de la red de compose, porque nginx es donde viven las cabeceras de
seguridad y el límite de subida.

Todo lo opcional se enlaza a `127.0.0.1`: el `8000` y `5432` del overlay de desarrollo, más
`api-fixtures` (8001), `a2a` (5000) y `ollama` (11434). No cambies esos a `0.0.0.0` en una red
compartida — Docker publica puertos con reglas DNAT que **atraviesan el cortafuegos del host**.

`web` en `3000` es la excepción deliberada; es la puerta de entrada. Si lo sirves más allá de
localhost por HTTP plano, ten en cuenta que `COOKIE_SECURE` es `false` por defecto, así que las
cookies de sesión viajan sin cifrar. Ponlo detrás de TLS y define `COOKIE_SECURE=true`.

## Detenerlo

```bash
docker compose down       # detener, conservar los datos
docker compose down -v    # detener, destruir la base de datos y las subidas
```

---

**Siguiente:** [`README.md`](README.md) para saber qué es SkillNet y cómo funciona,
[`AGENTS.md`](AGENTS.md) para las convenciones y fronteras al cambiar el código, y
[`docs/design/docker-deployment.md`](docs/design/docker-deployment.md) para saber por qué el
despliegue tiene esta forma.
