#!/usr/bin/env python
"""Banco de calidad de la generacion de cursos (v2, `src/agents/runtime`).

Para que sirve
==============

Para poder decir **"antes 60 %, ahora 80 %"** en vez de "me parece que va mejor".
Se toca un prompt, un umbral o un modelo (todos los diales estan listados en
``docs/design/tuning.md``), se lanza esto, y sale una tabla comparada con la
ejecucion anterior mas un volcado de **cada salida que fallo con el motivo exacto**.
Un porcentaje sin los fallos delante no arregla nada, asi que las dos cosas salen
siempre juntas.

    # sin clave, para comprobar que el banco funciona (usa FixtureLLMService)
    uv run python scripts/quality_bench.py --offline

    # de verdad, contra el proveedor configurado en .env
    uv run python scripts/quality_bench.py --repeat 3

    # un solo encargo, cambiando de modelo
    uv run python scripts/quality_bench.py --only extintor --model groq/openai/gpt-oss-120b

Es un **script, no un test**: el nombre no casa con ``test_*.py``, asi que
``pytest`` no lo recoge. Hace llamadas de red reales y cuesta dinero; una suite
no puede depender de eso.

Que se mide y que se finge
==========================

Se ejecuta el pipeline **real**: ``run_node_render`` -> ``build_node_graph()`` ->
los ocho nodos de ``src/agents/runtime/nodes.py``, el router de dos niveles, los
prompts de ``src/llm/prompts/runtime.py``, la puerta de ``src/render/gate.py`` y el
parser/serializador de OpenUI. Nada de copiar un prompt en el script: lo que se
mide tiene que ser lo que corre en produccion, o la medida no vale.

Se fingen **tres costuras**, y solo tres:

1. **La sesion de base de datos.** No hay Postgres en la maquina del dueno todavia.
   ``BenchSession`` responde las mismas consultas que ``load_context`` y
   ``persist_render`` hacen, en memoria. La alternativa era no poder medir hasta
   tener Docker levantado.
2. **El SSE.** ``publish`` se recoge en una lista y ``wait_for_subscriber`` devuelve
   ``True`` al instante: no hay navegador esperando, y medio segundo de espera por
   render mentiria sobre la latencia.
3. **``litellm.acompletion``**, envuelto (no sustituido) para inyectar un
   ``User-Agent`` propio y reintentar los 429 con retroceso exponencial. Va **por
   debajo** de ``LLMService``, asi que el grafo no se entera: un 429 no puede
   colarse como si fuera un fallo de calidad.

Lo que **no** se finge: la puerta, la validacion, el bucle de reparacion, el
fallback a la leccion semilla y la regla de calibracion de §6.4.

Restriccion de seguridad
========================

La reactividad de OpenUI sigue apagada, aqui igual que en produccion: este script
no pasa ``allow_reactive``, no toca ``settings.RENDER_ALLOW_REACTIVE`` y no ensena
sintaxis reactiva en ningun prompt. Los volcados de fallos contienen ``raw_dsl``
(la salida cruda del modelo) **a proposito** — son para leerlos en un editor, no
para servirlos a un navegador — y ``answer_key`` no se escribe en ningun fichero.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import contextvars
import hashlib
import json
import math
import os
import random
import re
import statistics
import sys
import time
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# `python scripts/quality_bench.py` pone `scripts/` en sys.path, no la raiz del
# paquete. Se anade explicitamente para que el script funcione desde cualquier cwd.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

import litellm  # noqa: E402

from src.config import settings  # noqa: E402
from src.core import sse  # noqa: E402
from src.models import (  # noqa: E402
    ActivityDefinition,
    ActivityState,
    Course,
    CourseDeliveryMode,
    CourseNode,
    CourseSchemaStatus,
    LearnerExperience,
    LearnerNodeState,
    LearnerProfile,
    Lesson,
    LlmUsageLog,
    LearningProfile,
    NodeCriticality,
    NodeRender,
    NodeRenderStatus,
    NodeState,
    UiFormat,
)
from src.render.kit import LLM_COMPONENT_NAMES  # noqa: E402

# --------------------------------------------------------------------------------------
# Diales del propio banco
# --------------------------------------------------------------------------------------

#: Los bloques que el modelo PUEDE emitir — el denominador de la cobertura de catalogo.
#: ``Markdown`` queda fuera a proposito: ``llm_emittable`` es falso y solo lo escribe
#: ``fallback_seed``, asi que contarlo premiaria justo el desenlace que no queremos.
EMITTABLE_BLOCKS: tuple[str, ...] = LLM_COMPONENT_NAMES

#: El User-Agent por defecto de Python recibe **403 de Groq** (medido). Cualquier cadena
#: identificable sirve; lo que no sirve es no poner ninguna.
BENCH_USER_AGENT = "SkillNet-QualityBench/1.0 (+https://github.com/skillnet/skillnet)"

#: Reintentos ante 429 **dentro** del shim del proveedor, por llamada.
RATE_LIMIT_MAX_RETRIES = 5
RATE_LIMIT_BASE_DELAY = 4.0
RATE_LIMIT_MAX_DELAY = 90.0

#: Tarifas en USD por millon de tokens, ``(entrada, salida)``.
#:
#: **Compruebalas contra la pagina de precios de tu proveedor antes de creerte la
#: columna de coste**: cambian, y un banco que inventa numeros es peor que uno que
#: no los da. Un modelo que no este aqui sale con coste ``None`` y el informe lo dice
#: en voz alta en vez de estimarlo. Con ``--price-in`` / ``--price-out`` se pisa la
#: tabla entera sin tocar el fichero.
PRICES: dict[str, tuple[float, float]] = {
    "groq/llama-3.1-8b-instant": (0.05, 0.08),
    "groq/openai/gpt-oss-120b": (0.15, 0.75),
    "groq/llama-3.3-70b-versatile": (0.59, 0.79),
}

#: Modelo que activa ``FixtureLLMService`` (cualquier id que empiece por ``fixture/``).
OFFLINE_MODEL = "fixture/bench"

SCHEMA_VERSION = 1

#: Las dos representaciones que el banco puede comparar. ``pack`` es una costura del
#: banco: no existe en el runtime ni se persiste. Su unico efecto es sustituir el valor
#: de ``source_context`` *despues* de que ``load_context`` haya recuperado la fuente real.
#: Eso evita medir dos recuperaciones distintas como si fuesen una mejora pedagogica.
BENCH_ARMS = ("raw", "pack")

# ``structural`` is the cheap control that only wraps the original source in headings.
# ``generated`` runs the real two-pass NodeKnowledgePack generator once per node and
# reuses that reviewed dossier across every learner/render repetition.
PACK_SOURCES = ("structural", "generated")

# Ids fijos: un `cache_key` estable entre ejecuciones hace comparables dos tandas.
ORG_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
COURSE_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000003")
DOC_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000004")
LESSON_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000005")


# --------------------------------------------------------------------------------------
# El corpus: 10 encargos de pyme espanola, cada uno con su aprendiz
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PackFactCheck:
    fact_id: str
    required_terms: tuple[str, ...]


@dataclass(frozen=True)
class Encargo:
    """Un nodo de curso mas la persona que lo va a leer.

    Los perfiles son **deliberadamente distintos entre si**: si todos fueran el mismo
    dependiente de 30 anos, el banco mediria el prompt pero no la personalizacion, que
    es justo la parte de v2 que puede salir mal sin que nadie se entere.
    """

    name: str
    title: str
    summary: str
    outcome: str
    criticality: str
    default_ui_format: str
    source_text: str
    seed_lesson: str

    # --- el aprendiz ---
    role_title: str
    sector: str
    experience_level: str
    preset: str
    #: < 3 -> periodo de calibracion (§6.4): NO hay llamada a `decide_formato`.
    nodes_completed: int
    intent_density: int
    scaffold_band: str = "neutral"
    short_blocks: bool = False
    mastery: float = 0.0
    node_state: str = "learning"
    consecutive_correct: int = 0
    consecutive_failed: int = 0
    last_error_kind: str | None = None
    tutor_signals: tuple[str, ...] = ()

    #: Solo en `--offline`: cuantos intentos de `genera_ui` se guionizan como invalidos
    #: antes de emitir uno bueno. 0 = acierta a la primera, 1 = lo rescata la reparacion,
    #: 2 = acaba en fallback. Sirve para que la tanda offline ejercite los tres caminos.
    offline_bad_attempts: int = 0
    #: Gold facts used only by the pack experiment. Every term in one check must appear
    #: in the canonical pack payload; these labels never enter a generation prompt.
    pack_fact_checks: tuple[PackFactCheck, ...] = ()


CORPUS: tuple[Encargo, ...] = (
    Encargo(
        name="devoluciones-tienda",
        title="Plazo y condiciones de devolucion",
        summary=(
            "Las devoluciones se aceptan durante 30 dias naturales desde la entrega, "
            "con ticket y producto sin usar."
        ),
        outcome="Resolver una devolucion en caja sin consultar al encargado",
        criticality="recommended",
        default_ui_format="explanation",
        source_text=(
            "POLITICA DE DEVOLUCIONES Y CAMBIOS\n\n"
            "1. Plazo. El cliente dispone de 30 dias naturales desde la fecha de entrega "
            "para devolver un articulo. El plazo se cuenta desde la fecha impresa en el "
            "ticket, no desde la fecha de la compra online.\n\n"
            "2. Condiciones. El articulo debe presentarse sin usar, con su embalaje "
            "original y todas las etiquetas. Se exige el ticket de compra o el "
            "justificante de pago con tarjeta.\n\n"
            "3. Reembolso. Se devuelve por el mismo medio de pago. En efectivo solo si la "
            "compra fue en efectivo y no supera los 150 euros; por encima de esa cantidad "
            "se emite transferencia y la autoriza el encargado.\n\n"
            "4. Excepciones. No se admiten devoluciones de ropa interior, articulos de "
            "higiene personal ni productos personalizados. Los articulos rebajados si "
            "admiten devolucion, pero solo como cambio o vale.\n\n"
            "5. Producto defectuoso. Fuera del plazo de 30 dias, un producto defectuoso "
            "se tramita por garantia (3 anos desde la entrega) y no por devolucion."
        ),
        seed_lesson=(
            "# Devoluciones\n\n"
            "Plazo: **30 dias naturales** desde la entrega.\n\n"
            "Hace falta ticket y producto sin usar, con etiquetas."
        ),
        role_title="Dependienta",
        sector="comercio minorista de moda",
        experience_level="some",
        preset="standard",
        nodes_completed=7,
        intent_density=3,
    ),
    Encargo(
        name="extintor",
        title="Uso del extintor de polvo ABC",
        summary=(
            "Un extintor de polvo ABC se usa con la regla PAS y solo sobre conatos, "
            "nunca sobre un fuego ya extendido."
        ),
        outcome="Sofocar un conato de incendio con el extintor mas cercano sin ponerse en riesgo",
        criticality="critical",
        default_ui_format="exercise",
        source_text=(
            "MANUAL DE AUTOPROTECCION - USO DE EXTINTORES PORTATILES\n\n"
            "Tipo de extintor. Los extintores del local son de polvo polivalente ABC de "
            "6 kg. Sirven para solidos (A), liquidos (B) y gases (C). NO se usan sobre "
            "equipos electricos en tension por encima de 1.000 V ni sobre aceite de "
            "freidora (fuego de clase F), para el que hay una manta ignifuga en cocina.\n\n"
            "Secuencia de uso (regla PAS):\n"
            "P - Quitar el Pasador de seguridad tirando de la anilla.\n"
            "A - Apuntar la boquilla a la base de la llama, no a las llamas.\n"
            "S - Presionar la maneta y barrer en Sigzag desde una distancia de 2 a 3 metros.\n\n"
            "Antes de actuar. Comprobar que hay una via de salida a la espalda. Nunca dar "
            "la espalda al fuego. Un extintor de 6 kg dura entre 8 y 12 segundos de "
            "descarga continua: no da para dos intentos.\n\n"
            "Cuando NO actuar. Si el fuego supera la altura de la cintura, si hay humo "
            "denso o si el conato lleva mas de un minuto, se evacua y se avisa al 112. "
            "La consigna es siempre: avisar, evacuar y solo despues extinguir."
        ),
        seed_lesson=(
            "# Extintor ABC\n\n"
            "Regla **PAS**: Pasador, Apuntar a la base, Sigzag.\n\n"
            "Si el fuego pasa de la cintura: evacuar y llamar al 112."
        ),
        role_title="Mozo de almacen",
        sector="logistica",
        experience_level="none",
        preset="focus",
        nodes_completed=1,  # calibracion: no hay llamada a decide_formato
        intent_density=3,
        scaffold_band="novice",
        offline_bad_attempts=1,
    ),
    Encargo(
        name="alergenos-hosteleria",
        title="Los 14 alergenos de declaracion obligatoria",
        summary=(
            "Todo plato servido debe poder declararse frente a los 14 alergenos del "
            "Reglamento 1169/2011, por escrito y sin depender de la memoria del camarero."
        ),
        outcome="Responder a un cliente que pregunta por un alergeno sin arriesgarse a un error",
        criticality="critical",
        default_ui_format="mixed",
        source_text=(
            "INFORMACION AL CONSUMIDOR SOBRE ALERGENOS (Reglamento UE 1169/2011)\n\n"
            "Los 14 alergenos de declaracion obligatoria son: cereales con gluten, "
            "crustaceos, huevos, pescado, cacahuetes, soja, leche, frutos de cascara, "
            "apio, mostaza, granos de sesamo, dioxido de azufre y sulfitos (por encima de "
            "10 mg/kg), altramuces y moluscos.\n\n"
            "Obligaciones del establecimiento. La informacion debe estar disponible por "
            "escrito y accesible antes de que el cliente pida. No basta con 'preguntar al "
            "cocinero'. La ficha de cada plato se guarda en la carpeta roja de barra y se "
            "actualiza cada vez que cambia un proveedor.\n\n"
            "Contaminacion cruzada. Freir un rebozado con gluten en el mismo aceite que "
            "una patata la convierte en no apta para celiacos. Las tablas y los cuchillos "
            "de la zona sin gluten son los de mango verde y no salen de esa zona.\n\n"
            "Si hay duda. Si no se puede garantizar por escrito que un plato esta libre de "
            "un alergeno, se dice que no y se ofrece otro plato. Nunca se responde 'creo "
            "que no lleva'. Una reaccion anafilactica es una urgencia vital."
        ),
        seed_lesson=(
            "# Alergenos\n\n"
            "Son **14** y estan por escrito en la carpeta roja de barra.\n\n"
            "Si no se puede garantizar por escrito, se dice que no."
        ),
        role_title="Camarero de sala",
        sector="hosteleria",
        experience_level="some",
        preset="standard",
        nodes_completed=4,
        intent_density=4,
        pack_fact_checks=(
            PackFactCheck("allergen-count", ("14 alergenos",)),
            PackFactCheck("written-before-order", ("por escrito", "antes")),
            PackFactCheck("red-folder", ("carpeta roja",)),
            PackFactCheck("cross-contact-oil", ("mismo aceite", "gluten")),
            PackFactCheck("green-tools", ("mango verde",)),
            PackFactCheck("never-guess", ("creo que no lleva",)),
            PackFactCheck("anaphylaxis", ("urgencia vital",)),
        ),
    ),
    Encargo(
        name="proteccion-datos",
        title="Datos personales de clientes en el mostrador",
        summary=(
            "Un dato personal solo se pide si hace falta para la gestion, se guarda el "
            "tiempo minimo y no se comenta delante de terceros."
        ),
        outcome="Tramitar una ficha de cliente sin incumplir el RGPD",
        criticality="recommended",
        default_ui_format="explanation",
        source_text=(
            "PROTECCION DE DATOS - INSTRUCCIONES PARA PERSONAL DE ATENCION\n\n"
            "Principio de minimizacion. Solo se piden los datos necesarios para la gestion "
            "concreta. Para una reparacion en garantia hacen falta nombre, telefono y "
            "numero de serie: no hace falta el DNI ni la fecha de nacimiento.\n\n"
            "Consentimiento. Para enviar publicidad hace falta una casilla marcada "
            "activamente por el cliente. Una casilla premarcada no es consentimiento "
            "valido. El consentimiento se puede retirar en cualquier momento y hay que "
            "atender la retirada en el acto.\n\n"
            "Conservacion. Las fichas de reparacion se conservan 5 anos por obligacion "
            "mercantil. Las listas de correo se depuran cada 24 meses sin actividad.\n\n"
            "En el mostrador. No se dicen datos de un cliente en voz alta si hay otra "
            "persona en la cola. La pantalla se bloquea al ausentarse (tecla Windows + L). "
            "No se anotan datos en papeles sueltos: o van al sistema, o no existen.\n\n"
            "Brecha de seguridad. Un portatil perdido, un correo enviado a la direccion "
            "equivocada o un armario de fichas abierto toda la noche son brechas. Se avisa "
            "al responsable el mismo dia: hay 72 horas para notificar a la AEPD."
        ),
        seed_lesson=(
            "# Datos personales\n\n"
            "Pide **solo lo necesario** y no lo comentes delante de otros clientes.\n\n"
            "Una brecha se avisa el mismo dia: hay 72 horas para notificarla."
        ),
        role_title="Administrativa de atencion al cliente",
        sector="servicios tecnicos",
        experience_level="experienced",
        preset="fast",
        nodes_completed=11,
        intent_density=2,
        scaffold_band="advanced",
        consecutive_correct=2,
    ),
    Encargo(
        name="higiene-alimentaria",
        title="Cadena de frio y temperaturas de conservacion",
        summary=(
            "Cada familia de producto tiene una temperatura maxima de conservacion y una "
            "franja de peligro entre 5 y 65 grados que hay que cruzar rapido."
        ),
        outcome="Registrar y corregir una temperatura fuera de rango antes de que el producto se pierda",
        criticality="critical",
        default_ui_format="chart",
        source_text=(
            "PLAN DE HIGIENE - CONTROL DE TEMPERATURAS (APPCC)\n\n"
            "Temperaturas maximas de conservacion:\n"
            "- Camara de refrigerado de carne: 4 grados C\n"
            "- Camara de refrigerado de pescado: 2 grados C\n"
            "- Camara de lacteos y postres: 6 grados C\n"
            "- Congelador: -18 grados C\n"
            "- Vitrina de servicio en caliente: 65 grados C minimo\n\n"
            "Zona de peligro. Entre 5 y 65 grados C las bacterias se multiplican. Un "
            "producto cocinado tiene que bajar de 65 a 10 grados en menos de 2 horas, y de "
            "10 a 4 grados en las 4 horas siguientes.\n\n"
            "Registro. Se anota la temperatura de cada camara dos veces al dia, a la "
            "apertura y al cierre, en la hoja de registro. Una lectura fuera de rango se "
            "anota igualmente: borrar o no apuntar una desviacion es la falta grave, no la "
            "desviacion.\n\n"
            "Que hacer con una desviacion. Menos de 2 grados por encima y menos de 2 horas: "
            "se traslada el genero a otra camara y se sigue. Mas de eso: se retira el "
            "genero, se etiqueta como no apto y se avisa al responsable."
        ),
        seed_lesson=(
            "# Temperaturas\n\n"
            "Carne 4 C, pescado 2 C, lacteos 6 C, congelador -18 C, caliente 65 C minimo.\n\n"
            "Zona de peligro: entre 5 y 65 grados."
        ),
        role_title="Ayudante de cocina",
        sector="restauracion colectiva",
        experience_level="some",
        preset="standard",
        nodes_completed=5,
        intent_density=3,
    ),
    Encargo(
        name="prevencion-riesgos",
        title="Manipulacion manual de cargas",
        summary=(
            "Una carga se levanta con las piernas, pegada al cuerpo y sin girar el tronco; "
            "por encima de 25 kg no se levanta a mano."
        ),
        outcome="Levantar y depositar una carga sin lesionarse la espalda",
        criticality="critical",
        default_ui_format="exercise",
        source_text=(
            "EVALUACION DE RIESGOS - MANIPULACION MANUAL DE CARGAS (RD 487/1997)\n\n"
            "Limites. El peso maximo recomendado en condiciones ideales es de 25 kg para "
            "un trabajador adulto sano. Baja a 15 kg para mujeres, jovenes y trabajadores "
            "mayores, y a 40 kg solo en manipulacion esporadica por personal entrenado.\n\n"
            "Tecnica correcta:\n"
            "1. Separar los pies a la anchura de los hombros, uno ligeramente adelantado.\n"
            "2. Doblar las rodillas manteniendo la espalda recta, nunca doblar la espalda.\n"
            "3. Agarrar la carga firmemente con las dos manos.\n"
            "4. Levantar suavemente estirando las piernas, con la carga pegada al cuerpo.\n"
            "5. No girar el tronco con la carga en alto: mover los pies.\n\n"
            "Factores que agravan el riesgo: carga voluminosa que impide ver los pies, "
            "suelo resbaladizo o con desnivel, giros del tronco, levantar por encima de la "
            "altura de los hombros, y ritmo impuesto por una cinta.\n\n"
            "Ayudas disponibles. Transpaleta manual en muelle, carro de plataforma en "
            "pasillo central y ventosa de vacio para las cajas de mas de 20 kg. Si la carga "
            "pasa de 25 kg se pide ayuda a un companero o se usa la transpaleta: no hay "
            "premio por hacerlo solo."
        ),
        seed_lesson=(
            "# Cargas\n\n"
            "Rodillas dobladas, **espalda recta**, carga pegada al cuerpo.\n\n"
            "Mas de 25 kg: transpaleta o companero."
        ),
        role_title="Operario de linea de envasado",
        sector="industria alimentaria",
        experience_level="none",
        preset="focus",
        nodes_completed=2,  # calibracion
        intent_density=3,
        scaffold_band="novice",
        short_blocks=True,
        consecutive_failed=1,
        last_error_kind="procedural",
    ),
    Encargo(
        name="atencion-reclamaciones",
        title="Atencion telefonica de una reclamacion",
        summary=(
            "Una reclamacion por telefono se escucha entera sin interrumpir, se resume "
            "para confirmar, y se cierra con un compromiso con fecha."
        ),
        outcome="Cerrar una llamada de reclamacion con un compromiso concreto y registrado",
        criticality="recommended",
        default_ui_format="mixed",
        source_text=(
            "PROTOCOLO DE ATENCION TELEFONICA DE RECLAMACIONES\n\n"
            "Fase 1 - Escucha. Se deja hablar al cliente hasta el final sin interrumpir, "
            "aunque se sepa la respuesta a la segunda frase. Interrumpir alarga la llamada: "
            "el cliente vuelve a empezar desde el principio.\n\n"
            "Fase 2 - Reformulacion. Se resume lo que ha dicho con las propias palabras del "
            "cliente: 'Entonces, si le he entendido bien, el pedido llego el martes y "
            "faltaban dos unidades'. Confirmar antes de resolver evita resolver el problema "
            "equivocado.\n\n"
            "Fase 3 - Disculpa por el efecto, no por la culpa. 'Siento las molestias que le "
            "ha causado' se puede decir siempre. 'Hemos cometido un error' solo cuando "
            "consta que lo hubo.\n\n"
            "Fase 4 - Compromiso. Toda llamada se cierra con QUE se va a hacer, QUIEN lo va "
            "a hacer y CUANDO. 'Le llamo yo el jueves antes de las 12' es un compromiso. "
            "'Lo miramos' no lo es.\n\n"
            "Fase 5 - Registro. Se anota en el CRM antes de colgar la siguiente llamada, no "
            "al final del turno. Plazo maximo de respuesta a una reclamacion escrita: 30 "
            "dias naturales.\n\n"
            "Escalado. Si el cliente pide hablar con un responsable, se pasa. No se discute "
            "esa peticion y no se deja en espera mas de 60 segundos sin volver a la linea."
        ),
        seed_lesson=(
            "# Reclamaciones por telefono\n\n"
            "Escuchar entero, **reformular**, disculparse por el efecto y cerrar con un "
            "compromiso con fecha.\n\nRegistrar en el CRM antes de la siguiente llamada."
        ),
        role_title="Teleoperadora de postventa",
        sector="distribucion de material electrico",
        experience_level="some",
        preset="standard",
        nodes_completed=6,
        intent_density=4,
        consecutive_failed=2,
        last_error_kind="conceptual",
        tutor_signals=("reforzar_con_ejemplo",),
        pack_fact_checks=(
            PackFactCheck("listen", ("sin interrumpir",)),
            PackFactCheck("reformulate", ("propias palabras", "confirmar")),
            PackFactCheck("effect-not-blame", ("efecto", "culpa")),
            PackFactCheck("commitment", ("que", "quien", "cuando")),
            PackFactCheck("crm-timing", ("crm", "antes")),
            PackFactCheck("written-deadline", ("30 dias naturales",)),
            PackFactCheck("hold-limit", ("60 segundos",)),
        ),
    ),
    Encargo(
        name="apertura-cierre-caja",
        title="Arqueo de apertura y cierre de caja",
        summary=(
            "La caja se abre con un fondo fijo contado y se cierra cuadrando efectivo, "
            "tarjeta y vales contra el informe Z."
        ),
        outcome="Cuadrar la caja al cierre y documentar un descuadre",
        criticality="critical",
        default_ui_format="exercise",
        source_text=(
            "PROCEDIMIENTO DE APERTURA Y CIERRE DE CAJA\n\n"
            "Apertura. El fondo fijo es de 200 euros en cambio: 40 en monedas de 1 y 2 "
            "euros, 30 en monedas pequenas, 80 en billetes de 5 y 50 en billetes de 10. Se "
            "cuenta delante del encargado y se firma la hoja de apertura. Un fondo que no "
            "cuadra a la apertura es del turno anterior, y solo se puede reclamar antes de "
            "hacer la primera venta.\n\n"
            "Durante el turno. Retirada de efectivo cada vez que la caja supera 600 euros: "
            "se mete en el buzon de seguridad con su sobre numerado. No se guardan billetes "
            "de 200 y 500 en el cajon: van directos al buzon.\n\n"
            "Cierre. Se saca el informe Z del TPV. Se cuenta el efectivo, se resta el fondo "
            "fijo de 200 euros y el resultado debe coincidir con la linea de efectivo del Z. "
            "Los pagos con tarjeta se comparan con el cierre del datafono, y los vales con "
            "los justificantes grapados.\n\n"
            "Descuadres. Hasta 5 euros de diferencia se anota en la hoja de cierre y se "
            "sigue. Por encima de 5 euros se recuenta una segunda vez y, si persiste, se "
            "avisa al encargado antes de irse. Un descuadre no comunicado el mismo dia es "
            "una falta, aunque sean 6 euros."
        ),
        seed_lesson=(
            "# Caja\n\n"
            "Fondo fijo **200 euros**, contado delante del encargado.\n\n"
            "Al cierre: informe Z, restar el fondo y cuadrar. Descuadre de mas de 5 euros, "
            "se avisa el mismo dia."
        ),
        role_title="Encargado de turno",
        sector="supermercado de proximidad",
        experience_level="experienced",
        preset="fast",
        nodes_completed=9,
        intent_density=3,
        scaffold_band="advanced",
        mastery=0.55,
        consecutive_correct=1,
        pack_fact_checks=(
            PackFactCheck("float", ("fondo fijo", "200 euros")),
            PackFactCheck("opening-claim", ("primera venta",)),
            PackFactCheck("cash-withdrawal", ("600 euros", "buzon")),
            PackFactCheck("z-report", ("informe z", "resta")),
            PackFactCheck("card-and-vouchers", ("datafono", "vales")),
            PackFactCheck("mismatch-threshold", ("5 euros", "segunda vez")),
            PackFactCheck("same-day", ("mismo dia", "falta")),
        ),
    ),
    Encargo(
        name="epi-taller",
        title="Equipos de proteccion individual en el taller",
        summary=(
            "Cada tarea del taller tiene su EPI obligatorio, y trabajar sin el no es una "
            "decision personal sino una falta disciplinaria."
        ),
        outcome="Elegir el EPI correcto para la tarea que se va a hacer",
        criticality="recommended",
        default_ui_format="explanation",
        source_text=(
            "NORMAS DE USO DE EQUIPOS DE PROTECCION INDIVIDUAL (EPI)\n\n"
            "Obligatorios en todo el taller: calzado de seguridad con puntera (S3) y ropa "
            "de trabajo ajustada. Prohibidas las mangas sueltas, los cordones colgando y "
            "las pulseras cerca de maquinaria rotativa.\n\n"
            "Por tarea:\n"
            "- Amolado y corte: pantalla facial completa, no solo gafas. Guantes anticorte "
            "nivel 5 y proteccion auditiva (tapones o cascos, 85 dB es el limite).\n"
            "- Soldadura: pantalla de soldadura con filtro DIN 11, mandil de cuero, "
            "polainas y guantes largos. Nunca lentillas bajo la pantalla.\n"
            "- Manipulacion de quimicos: guantes de nitrilo, gafas de montura integral y "
            "revisar la ficha de seguridad ANTES de abrir el envase.\n"
            "- Trabajo en altura por encima de 2 metros: arnes anclado a linea de vida.\n\n"
            "Estado del EPI. Un EPI danado no protege: unas gafas rayadas, un casco con "
            "fisura o unos guantes con un corte se cambian, no se apuran. El recambio esta "
            "en el armario de la entrada y no hace falta pedir permiso para cogerlo.\n\n"
            "Responsabilidad. La empresa esta obligada a facilitarlos y el trabajador a "
            "usarlos. Trabajar sin el EPI de la tarea es falta grave segun el convenio."
        ),
        seed_lesson=(
            "# EPI\n\n"
            "Calzado de seguridad y ropa ajustada **siempre**.\n\n"
            "Cada tarea suma los suyos: pantalla, guantes, proteccion auditiva o arnes."
        ),
        role_title="Mecanico de mantenimiento",
        sector="taller mecanico industrial",
        experience_level="some",
        preset="standard",
        nodes_completed=3,
        intent_density=3,
        offline_bad_attempts=2,  # acaba en fallback: el banco tiene que medir tambien eso
    ),
    Encargo(
        name="residuos-taller",
        title="Segregacion de residuos peligrosos",
        summary=(
            "Los residuos peligrosos del taller van a su contenedor etiquetado y no pueden "
            "mezclarse ni tirarse al desague."
        ),
        outcome="Depositar cada residuo en el contenedor correcto y anotar la retirada",
        criticality="contextual",
        default_ui_format="explanation",
        source_text=(
            "GESTION DE RESIDUOS PELIGROSOS EN TALLER\n\n"
            "Contenedores y colores:\n"
            "- Bidon amarillo: aceite usado de motor y de corte. Nunca mezclar con "
            "anticongelante.\n"
            "- Bidon azul: anticongelante y liquido de frenos.\n"
            "- Bidon rojo: disolventes, pinturas y trapos impregnados.\n"
            "- Caja verde: filtros de aceite escurridos al menos 24 horas.\n"
            "- Contenedor gris con tapa: baterias de plomo, siempre en posicion vertical.\n\n"
            "Prohibiciones absolutas. Ningun residuo liquido va al desague, ni siquiera "
            "diluido. No se mezclan familias: un bidon con mezcla se clasifica como el "
            "residuo mas peligroso que contenga y multiplica el coste de retirada.\n\n"
            "Etiquetado. Cada bidon lleva la etiqueta con el codigo LER, la fecha de "
            "apertura y el pictograma. Un residuo peligroso no puede almacenarse mas de 6 "
            "meses desde la fecha de apertura del bidon.\n\n"
            "Registro. Cada retirada por el gestor autorizado genera un documento de "
            "identificacion que se archiva 3 anos. Sin ese documento la retirada no existe "
            "para la administracion."
        ),
        seed_lesson=(
            "# Residuos\n\n"
            "Amarillo aceite, azul anticongelante, rojo disolventes, verde filtros.\n\n"
            "Nada liquido al desague, y nunca mezclar familias."
        ),
        role_title="Aprendiz de taller",
        sector="taller de automocion",
        experience_level="unknown",
        preset="standard",
        nodes_completed=8,
        intent_density=5,
    ),
)

CORPUS_BY_NAME: dict[str, Encargo] = {e.name: e for e in CORPUS}


# --------------------------------------------------------------------------------------
# Brazo experimental: dossier Markdown local, sin acoplar al runtime
# --------------------------------------------------------------------------------------


def _digest(value: str) -> str:
    """Huella corta, estable y segura para comparar contexto sin volcarlo dos veces."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PackAtom:
    """Una unidad de fuente que el brazo ``pack`` puede trazar.

    El banco no pretende adivinar aun que hechos son opcionales. Por eso todos los
    atomos de la fuente son invariantes: este primer A/B mide el formato y la seleccion
    determinista, no una eliminacion silenciosa de conocimiento.
    """

    id: str
    text: str
    ordinal: int
    kind: str
    invariant: bool = True


@dataclass(frozen=True)
class SelectedKnowledge:
    """La porcion reproducible del pack que se entrega al generador."""

    markdown: str
    atom_ids: tuple[str, ...]
    invariant_ids: tuple[str, ...]


@dataclass(frozen=True)
class GeneratedPackArtifact:
    selection: SelectedKnowledge
    pack_hash: str
    pack_payload: dict[str, Any]
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int | None
    fact_coverage: float
    matched_fact_ids: tuple[str, ...]
    missing_fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class PackBenchPolicy:
    extractor_max_tokens: int = 1_600
    reviewer_max_tokens: int = 1_600
    min_invariants: int = 1
    max_atoms: int = 24
    min_fact_coverage: float = 1.0
    require_evidence: bool = False

    def __post_init__(self) -> None:
        if not 256 <= self.extractor_max_tokens <= 4_096:
            raise ValueError("extractor_max_tokens must be 256..4096")
        if not 256 <= self.reviewer_max_tokens <= 4_096:
            raise ValueError("reviewer_max_tokens must be 256..4096")
        if self.min_invariants < 1:
            raise ValueError("min_invariants must be positive")
        if self.max_atoms < self.min_invariants:
            raise ValueError("max_atoms must be >= min_invariants")
        if not 0 <= self.min_fact_coverage <= 1:
            raise ValueError("min_fact_coverage must be between 0 and 1")


@dataclass(frozen=True)
class PackAssessment:
    """Quality-policy result kept even when a generated pack is rejected."""

    atom_count: int
    invariant_count: int
    required_evidence_count: int
    fact_coverage: float
    matched_fact_ids: tuple[str, ...]
    missing_fact_ids: tuple[str, ...]
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


_GENERATED_PACKS: dict[str, GeneratedPackArtifact] = {}


def _fold_for_coverage(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(
        "".join(char for char in decomposed if not unicodedata.combining(char)).split()
    )


def evaluate_pack_facts(
    pack_payload: dict[str, Any], checks: tuple[PackFactCheck, ...]
) -> tuple[float, tuple[str, ...], tuple[str, ...]]:
    """Measure gold-fact coverage over model-owned semantic fields only."""

    semantic = {
        key: pack_payload.get(key, [])
        for key in (
            "evidence_specs",
            "must_preserve",
            "selectable",
            "generable_slots",
            "missing_data",
        )
    }
    haystack = _fold_for_coverage(json.dumps(semantic, ensure_ascii=False))
    matched = tuple(
        check.fact_id
        for check in checks
        if all(_fold_for_coverage(term) in haystack for term in check.required_terms)
    )
    missing = tuple(check.fact_id for check in checks if check.fact_id not in matched)
    coverage = len(matched) / len(checks) if checks else 1.0
    return coverage, matched, missing


def assess_completed_pack(
    completed: Any, encargo: Encargo, policy: PackBenchPolicy
) -> PackAssessment:
    """Evaluate a completed production pack without discarding failed experiments."""

    atom_count = len(completed.atoms)
    invariant_count = sum(
        item.get("category") == "must_preserve" for item in completed.atoms
    )
    coverage, matched, missing = evaluate_pack_facts(
        completed.pack_payload, encargo.pack_fact_checks
    )
    required_evidence = sum(
        bool(item.get("required"))
        for item in completed.pack_payload.get("evidence_specs", [])
    )
    failures: list[str] = []
    if completed.pack_payload.get("status") != "ready":
        failures.append("pack status is not ready")
    if invariant_count < policy.min_invariants:
        failures.append(
            f"invariants {invariant_count} < minimum {policy.min_invariants}"
        )
    if atom_count > policy.max_atoms:
        failures.append(f"atoms {atom_count} > maximum {policy.max_atoms}")
    if coverage < policy.min_fact_coverage:
        failures.append(
            f"fact coverage {coverage:.1%} < minimum {policy.min_fact_coverage:.1%}; "
            f"missing={','.join(missing)}"
        )
    if policy.require_evidence and required_evidence == 0:
        failures.append("no required evidence specification")
    return PackAssessment(
        atom_count=atom_count,
        invariant_count=invariant_count,
        required_evidence_count=required_evidence,
        fact_coverage=coverage,
        matched_fact_ids=matched,
        missing_fact_ids=missing,
        failures=tuple(failures),
    )


@dataclass(frozen=True)
class KnowledgePack:
    """Dossier Markdown local construido desde el ``source_context`` ya recuperado.

    No es una nueva fuente de verdad ni una tabla. Es deliberadamente local al script
    para que el experimento pueda descartarse sin dejar modelos, migraciones o codigo de
    produccion. El parser conserva cada bloque no vacio; el selector solo puede reordenar
    atomos no criticos en una fase futura, y hoy entrega todos los invariantes.
    """

    source_digest: str
    atoms: tuple[PackAtom, ...]

    @classmethod
    def from_source(cls, source: str) -> KnowledgePack:
        normalized = source.strip()
        blocks = [
            re.sub(r"\n{3,}", "\n\n", block.strip())
            for block in re.split(r"\n\s*\n", normalized)
            if block.strip()
        ]
        digest = _digest(source)
        atoms = tuple(
            PackAtom(
                id=f"a{ordinal:03d}-{_digest(block)[:10]}",
                text=block,
                ordinal=ordinal,
                kind=_pack_atom_kind(block),
            )
            for ordinal, block in enumerate(blocks, start=1)
        )
        return cls(source_digest=digest, atoms=atoms)

    def select(self, *, profile: dict[str, Any] | None = None) -> SelectedKnowledge:
        """Seleccion conservadora y determinista.

        ``profile`` se acepta para que el contrato ya exprese la futura seleccion por
        aprendiz. En esta primera prueba no cambia los hechos seleccionados: no se puede
        atribuir una mejora al pack si a la vez dejamos caer material de la fuente.
        """
        del profile
        selected = tuple(sorted(self.atoms, key=lambda atom: atom.ordinal))
        atom_ids = tuple(atom.id for atom in selected)
        invariant_ids = tuple(atom.id for atom in selected if atom.invariant)
        lines = [
            "# Dossier de referencia del nodo",
            "",
            "El siguiente material conserva los hechos de la fuente y puede organizarse "
            "en una experiencia adaptada. No inventes reglas fuera de este dossier.",
            "",
        ]
        for atom in selected:
            lines.extend(
                [
                    f"## Material {atom.ordinal} ({atom.kind})",
                    "",
                    atom.text,
                    "",
                ]
            )
        return SelectedKnowledge(
            markdown="\n".join(lines).rstrip() + "\n",
            atom_ids=atom_ids,
            invariant_ids=invariant_ids,
        )


def _pack_atom_kind(block: str) -> str:
    """Etiqueta determinista, solo para trazabilidad del benchmark."""
    first = block.lstrip().splitlines()[0] if block.strip() else ""
    if first.startswith("#"):
        return "heading"
    if re.match(r"(?:[-*]|\d+[.)])\s", first):
        return "list"
    if any(marker in block.lower() for marker in ("nunca", "obligatorio", "prohib", "alerta")):
        return "constraint"
    return "paragraph"


async def prepare_generated_packs(
    corpus: list[Encargo], *, llm: Any, policy: PackBenchPolicy | None = None
) -> dict[str, GeneratedPackArtifact]:
    """Run the production two-pass pack generator once per benchmark node.

    This remains a benchmark seam: rows are not written to PostgreSQL. The generator,
    contract, source fingerprint, Markdown projection and telemetry are the production
    implementations; only persistence is omitted so an A/B cannot alter a real course.
    """

    from src.knowledge_pack.configured_generator import ConfiguredKnowledgePackGenerator
    from src.services.node_knowledge_pack_service import KnowledgePackSnapshot

    policy = policy or PackBenchPolicy()
    generator = ConfiguredKnowledgePackGenerator(
        llm,
        extractor_max_tokens=policy.extractor_max_tokens,
        reviewer_max_tokens=policy.reviewer_max_tokens,
    )
    artifacts: dict[str, GeneratedPackArtifact] = {}
    for encargo in corpus:
        session = build_session(encargo)
        fingerprint = _digest(encargo.source_text)
        completed = await generator.generate(
            course=session.course,
            node=session.node,
            source_context=encargo.source_text,
            snapshot=KnowledgePackSnapshot(
                org_id=ORG_ID,
                course_id=COURSE_ID,
                node_id=session.node.id,
                source_fingerprint=fingerprint,
                schema_version=SCHEMA_VERSION,
                generator_version="knowledge-pack/v1-bench",
            ),
        )
        assessment = assess_completed_pack(completed, encargo, policy)
        if assessment.failures:
            raise ValueError(
                f"pack {encargo.name} failed quality policy: "
                f"{'; '.join(assessment.failures)}"
            )
        must_preserve = tuple(
            str(item["atom_id"])
            for item in completed.atoms
            if item.get("category") == "must_preserve"
        )
        atom_ids = tuple(str(item["atom_id"]) for item in completed.atoms)
        artifacts[encargo.name] = GeneratedPackArtifact(
            selection=SelectedKnowledge(
                markdown=completed.markdown,
                atom_ids=atom_ids,
                invariant_ids=must_preserve,
            ),
            pack_hash=completed.pack_hash,
            pack_payload=completed.pack_payload,
            input_tokens=completed.input_tokens,
            output_tokens=completed.output_tokens,
            duration_ms=completed.duration_ms,
            fact_coverage=assessment.fact_coverage,
            matched_fact_ids=assessment.matched_fact_ids,
            missing_fact_ids=assessment.missing_fact_ids,
        )
    return artifacts


# --------------------------------------------------------------------------------------
# Costura 1: la base de datos, en memoria
# --------------------------------------------------------------------------------------


@dataclass
class _BenchUser:
    """Lo unico que el runtime lee de ``users``."""

    id: uuid.UUID
    org_id: uuid.UUID
    accessibility: dict = field(default_factory=dict)


@dataclass
class _BenchDocument:
    """<= 5 paginas -> ``load_source_context`` toma la rama ``full_text``, sin embeddings."""

    id: uuid.UUID
    title: str
    full_text: str
    page_count: int = 2


class _Result:
    """El poco de la API de ``Result`` que los repositorios usan."""

    def __init__(self, rows: list) -> None:
        self._rows = list(rows)

    def scalars(self) -> _Result:
        return self

    def all(self) -> list:
        return list(self._rows)

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> Any:
        return self._rows[0] if self._rows else 0


class BenchSession:
    """Una sesion que responde mirando el SQL, como la de ``tests/test_runtime_graph.py``.

    Se construye una por encargo, asi que cada render arranca con la tabla
    ``node_renders`` vacia: sin eso, el segundo pase de ``--repeat`` encontraria su
    propio ``cache_key`` ya servido y el banco mediria la cache en lugar de medir la
    generacion.
    """

    def __init__(
        self,
        *,
        node: CourseNode,
        course: Course,
        user: _BenchUser,
        profile: LearnerProfile,
        node_state: LearnerNodeState,
        document: _BenchDocument,
        lesson: Lesson,
    ) -> None:
        self.node = node
        self.course = course
        self.user = user
        self.profile = profile
        self.node_state = node_state
        self.document = document
        self.lesson = lesson
        self.renders: list[NodeRender] = []
        self.usage: list[LlmUsageLog] = []
        self.activity_definitions: list[ActivityDefinition] = []
        self.activity_states: list[ActivityState] = []
        self.node_states: list[LearnerNodeState] = [node_state]
        self._added: list[Any] = []

    # -- consultas -------------------------------------------------------------

    async def execute(self, query: Any) -> _Result:
        sql = str(query)
        if "FROM organizations" in sql:
            # Vacio a proposito: sin overrides de organizacion, los dos niveles del
            # router resuelven desde `settings`, que es lo que el banco controla.
            return _Result([])
        if "FROM learner_profiles" in sql:
            return _Result([self.profile])
        if "FROM learner_node_states" in sql:
            return _Result(list(self.node_states))
        if "FROM node_knowledge_packs" in sql:
            # El brazo generated inyecta su pack tras load_context. La sesión del
            # banco no simula persistencia y debe responder honestamente que no hay
            # un pack READY en PostgreSQL, igual para raw y pack.
            return _Result([])
        if "FROM activity_definitions" in sql:
            rows = list(self.activity_definitions)
            values = set(_params(query).values())
            if values:
                rows = [
                    row
                    for row in rows
                    if row.id in values
                    or row.org_id in values
                    or row.definition_key in values
                    or row.version in values
                ]
            return _Result(rows)
        if "FROM activity_states" in sql:
            rows = list(self.activity_states)
            values = set(_params(query).values())
            if values:
                rows = [
                    row
                    for row in rows
                    if row.activity_id in values or row.user_id in values
                ]
            return _Result(rows)
        if "FROM node_renders" in sql:
            rows = list(self.renders)
            wanted = {v for v in _params(query).values() if isinstance(v, str)}
            if wanted:
                rows = [r for r in rows if r.cache_key in wanted]
            if "node_renders.status = " in sql:
                rows = [
                    r
                    for r in rows
                    if r.status == NodeRenderStatus.READY and not r.is_preview
                ]
            return _Result(rows)
        if "FROM document_chunks" in sql:
            return _Result([])
        if "FROM media_artifacts" in sql:
            # Ofertas de media del broker (nodes.py:load_context -> media_broker.
            # ready_media_for_node). El banco no genera podcasts ni infografias, asi
            # que no hay ningun artefacto READY: lista vacia, y el prompt no ve el
            # bloque de ofertas. Sin esta rama los 10 encargos mueren en load_context
            # con AssertionError y el banco deja de medir nada.
            return _Result([])
        if "FROM source_images" in sql:
            # Igual que arriba: sin imagenes extraidas del documento, el prompt no
            # ofrece SourceImage. El banco mide texto, no material grafico.
            return _Result([])
        if "FROM course_nodes" in sql:
            # Nodos-hermanos (nodes.py:load_context, para no repetir ideas entre
            # pantallas). El banco monta UN solo nodo por encargo, asi que no hay
            # hermanos: lista vacia. Sin esta rama el runtime nuevo rompe los 10
            # encargos con AssertionError y el banco deja de medir nada.
            return _Result([])
        raise AssertionError(f"consulta inesperada en el banco: {sql}")

    async def get(self, model: type, pk: Any) -> Any:
        name = model.__name__
        if name == "CourseNode":
            return self.node if pk == self.node.id else None
        if name == "Course":
            return self.course if pk == self.course.id else None
        if name == "Lesson":
            return self.lesson if pk == self.lesson.id else None
        if name == "User":
            return self.user if pk == self.user.id else None
        if name == "Document":
            return self.document if pk == self.document.id else None
        if name == "NodeRender":
            return next((r for r in self.renders if r.id == pk), None)
        if name == "ActivityDefinition":
            return next((r for r in self.activity_definitions if r.id == pk), None)
        if name == "ActivityState":
            return next((r for r in self.activity_states if r.id == pk), None)
        raise AssertionError(f"get({name}, {pk}) inesperado en el banco")

    # -- escrituras ------------------------------------------------------------

    def add(self, obj: Any) -> None:
        self._added.append(obj)

    def add_all(self, objs: Any) -> None:
        self._added.extend(objs)

    async def delete(self, obj: Any) -> None:  # pragma: no cover - el grafo no borra
        raise AssertionError("el grafo de runtime no borra nada")

    async def flush(self) -> None:
        for obj in self._added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
            if isinstance(obj, NodeRender) and obj not in self.renders:
                self.renders.append(obj)
            elif isinstance(obj, LlmUsageLog) and obj not in self.usage:
                self.usage.append(obj)
            elif isinstance(obj, ActivityDefinition) and obj not in self.activity_definitions:
                self.activity_definitions.append(obj)
            elif isinstance(obj, ActivityState) and obj not in self.activity_states:
                self.activity_states.append(obj)
            elif isinstance(obj, LearnerNodeState) and obj not in self.node_states:
                self.node_states.append(obj)

    async def commit(self) -> None:
        await self.flush()

    async def rollback(self) -> None:
        pass

    # -- usable como el propio `async_session_factory` -------------------------

    def __call__(self) -> BenchSession:
        return self

    async def __aenter__(self) -> BenchSession:
        return self

    async def __aexit__(self, *exc_info: Any) -> bool:
        return False


def _params(query: Any) -> dict:
    try:
        return dict(query.compile().params)
    except Exception:  # pragma: no cover - solo para construcciones exoticas
        return {}


def build_session(encargo: Encargo) -> BenchSession:
    """Monta el contexto completo de un encargo como filas de base de datos."""
    node = CourseNode(
        org_id=ORG_ID,
        course_id=COURSE_ID,
        title=encargo.title,
        summary=encargo.summary,
        outcome=encargo.outcome,
        criticality=NodeCriticality(encargo.criticality),
        position=1,
        source_document_id=DOC_ID,
        source_headings=[],
        mastery_threshold=None,
        default_ui_format=UiFormat(encargo.default_ui_format),
        seed_lesson_id=LESSON_ID,
        probe_items=[],
        probe_answer_key={},
        estimated_minutes=6,
    )
    node.id = _node_id(encargo)
    node.archived = False
    node.reviewed_at = datetime.now(timezone.utc)

    course = Course(
        org_id=ORG_ID,
        title=f"Curso: {encargo.title}",
        outcome=encargo.outcome,
        delivery_mode=CourseDeliveryMode.DYNAMIC,
        schema_status=CourseSchemaStatus.VALIDATED,
        schema_version=SCHEMA_VERSION,
        intent_density=encargo.intent_density,
    )
    course.id = COURSE_ID

    profile = LearnerProfile(
        org_id=ORG_ID,
        user_id=USER_ID,
        role_title=encargo.role_title,
        sector=encargo.sector,
        goal="no tener que preguntar",  # nunca viaja al LLM (§3.3)
        experience_level=LearnerExperience(encargo.experience_level),
        preset=LearningProfile(encargo.preset),
        format_vector={"texto": 0.6, "ejercicio": 0.4, "codigo": 0.0, "dato": 0.0},
        nodes_completed=encargo.nodes_completed,
        tutor_notes=_tutor_notes(encargo),
    )
    profile.id = uuid.uuid4()

    state = LearnerNodeState(
        user_id=USER_ID,
        node_id=node.id,
        state=NodeState(encargo.node_state),
        mastery=encargo.mastery,
        scaffold_band=encargo.scaffold_band,
    )
    state.id = uuid.uuid4()
    state.consecutive_correct = encargo.consecutive_correct
    state.consecutive_failed = encargo.consecutive_failed
    state.last_error_kind = encargo.last_error_kind
    state.active_render_id = None
    state.render_pinned = False

    lesson = Lesson(
        module_id=uuid.uuid4(),
        title=encargo.title,
        content=encargo.seed_lesson,
        position=1,
    )
    lesson.id = LESSON_ID

    return BenchSession(
        node=node,
        course=course,
        user=_BenchUser(
            id=USER_ID,
            org_id=ORG_ID,
            accessibility={"short_blocks": True} if encargo.short_blocks else {},
        ),
        profile=profile,
        node_state=state,
        document=_BenchDocument(
            id=DOC_ID, title=f"Manual: {encargo.title}", full_text=encargo.source_text
        ),
        lesson=lesson,
    )


def _node_id(encargo: Encargo) -> uuid.UUID:
    """Un uuid estable por encargo: el ``cache_key`` entra en el JSON y debe ser
    comparable entre ejecuciones."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"skillnet-bench/{encargo.name}")


def _tutor_notes(encargo: Encargo) -> dict:
    if not encargo.tutor_signals:
        return {}
    node_id = str(_node_id(encargo))
    return {
        "version": 1,
        "signals": [
            {"node_id": node_id, "action": action} for action in encargo.tutor_signals
        ],
    }


# --------------------------------------------------------------------------------------
# Costura 2: el SSE
# --------------------------------------------------------------------------------------


class SseCollector:
    """Recoge los eventos en vez de mandarlos a un navegador que no existe."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []

    async def publish(self, channel: str, event_type: str, data: dict) -> None:
        self.events.append((channel, event_type, data))

    async def wait_for_subscriber(self, channel: str, timeout: float = 0.5) -> bool:
        # `True` sin esperar: medio segundo por render falsearia la latencia medida.
        return True

    def types(self) -> list[str]:
        return [kind for _, kind, _ in self.events]


# --------------------------------------------------------------------------------------
# Costura 3: el proveedor (User-Agent propio + retroceso ante 429)
# --------------------------------------------------------------------------------------


@dataclass
class ProviderStats:
    calls: int = 0
    rate_limited: int = 0
    rate_limit_seconds: float = 0.0
    transient_retries: int = 0
    exhausted: int = 0


_RETRY_AFTER_RE = re.compile(r"(?:try again in|retry after)\s+([0-9.]+)\s*s", re.I)

#: Errores transitorios que merecen retroceso. Son los mismos que ``src/llm/client.py``
#: reintenta con tenacity; aqui se envuelven **por debajo** para poder contarlos y para
#: cubrir tambien ``stream()``, que en el cliente no lleva reintento.
def _retryable_types() -> tuple[type[BaseException], ...]:
    return (
        litellm.RateLimitError,
        litellm.APIConnectionError,
        litellm.Timeout,
        litellm.InternalServerError,
        litellm.ServiceUnavailableError,
    )


def _retry_after_seconds(exc: BaseException) -> float | None:
    """Segundos que el proveedor pide esperar, si los dice.

    Groq los manda en la cabecera ``retry-after`` y ademas en el cuerpo del error
    ("Please try again in 7.2s"). Se leen los dos porque litellm no siempre expone
    la respuesta cruda.
    """
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        raw = headers.get("retry-after") or headers.get("Retry-After")
        try:
            if raw is not None:
                return float(raw)
        except (TypeError, ValueError):
            pass
    match = _RETRY_AFTER_RE.search(str(exc))
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def install_provider_shim(stats: ProviderStats, *, user_agent: str) -> None:
    """Envuelve ``litellm.acompletion``: User-Agent propio y retroceso ante 429.

    Va **por debajo** de ``LLMService`` a proposito. Si el reintento viviera arriba, un
    429 llegaria al grafo como excepcion, el grafo lo mandaria a ``fallback_seed`` y el
    informe contaria como fallo de calidad lo que solo es el plan gratuito diciendo
    "espera". Aqui el pipeline ni se entera, y el coste de esperar queda registrado
    aparte en ``rate_limit_seconds``.
    """
    original = litellm.acompletion
    retryable = _retryable_types()

    async def shim(**kwargs: Any) -> Any:
        headers = dict(kwargs.pop("extra_headers", None) or {})
        headers.setdefault("User-Agent", user_agent)
        delay = RATE_LIMIT_BASE_DELAY
        for attempt in range(RATE_LIMIT_MAX_RETRIES + 1):
            try:
                stats.calls += 1
                return await original(extra_headers=headers, **kwargs)
            except retryable as exc:
                is_rate_limit = isinstance(exc, litellm.RateLimitError)
                if attempt >= RATE_LIMIT_MAX_RETRIES:
                    stats.exhausted += 1
                    raise
                wait = _retry_after_seconds(exc) or delay
                wait = min(wait, RATE_LIMIT_MAX_DELAY) + random.uniform(0.0, 0.75)
                if is_rate_limit:
                    stats.rate_limited += 1
                else:
                    stats.transient_retries += 1
                stats.rate_limit_seconds += wait
                print(
                    f"    [espera] {type(exc).__name__}: durmiendo {wait:.1f}s "
                    f"(intento {attempt + 1}/{RATE_LIMIT_MAX_RETRIES})",
                    flush=True,
                )
                await asyncio.sleep(wait)
                delay = min(delay * 2, RATE_LIMIT_MAX_DELAY)
        raise AssertionError("inalcanzable")  # pragma: no cover

    litellm.acompletion = shim


# --------------------------------------------------------------------------------------
# Modo offline: FixtureLLMService con guion
# --------------------------------------------------------------------------------------

#: Programas OpenUI validos, uno por formato. Se usan solo en `--offline`.
_OFFLINE_PROGRAMS: dict[str, str] = {
    "explanation": (
        'root = Stack([intro, pasos, aviso], "md")\n'
        'intro = TextContent("Esto te sirve para resolverlo tu sin preguntar.", "lead")\n'
        'pasos = StepSequence("Como se hace", ["Comprobar la condicion", '
        '"Aplicar la regla", "Registrar lo hecho"])\n'
        'aviso = Callout("warn", "Fuera de plazo la regla cambia: consulta antes de decidir.")\n'
    ),
    "exercise": (
        'root = Stack([enunciado, q1], "md")\n'
        'enunciado = TextContent("Un caso real de tu puesto, para resolverlo ahora.", "lead")\n'
        'q1 = QuizItem("q1", "test", "apply", "Que haces primero?", '
        '["Aplicar la regla", "Avisar al responsable", "Dejarlo para luego"])\n'
        "---ANSWER-KEY---\n"
        '{"q1": {"correct": 0, "explanation": "La regla se aplica antes de escalar."}}\n'
    ),
    "chart": (
        'root = Stack([intro, grafico], "md")\n'
        'intro = TextContent("Los numeros que tienes que reconocer de un vistazo.", "lead")\n'
        'grafico = Chart("bar", "Valores de referencia", ["A", "B", "C"], [4, 2, 6])\n'
    ),
    "mixed": (
        'root = Stack([intro, aviso, q1], "md")\n'
        'intro = TextContent("Primero la regla, y despues la compruebas.", "lead")\n'
        'aviso = Callout("info", "La regla se aplica siempre, tambien cuando hay prisa.")\n'
        'q1 = QuizItem("q1", "true_false", "understand", '
        '"La regla admite excepciones por prisa?", [])\n'
        "---ANSWER-KEY---\n"
        '{"q1": {"correct": false, "explanation": "La prisa no es una excepcion."}}\n'
    ),
}

#: Programa invalido: argumentos con nombre y la clave de respuestas colada como una
#: declaracion mas. Son los dos fallos que los modelos de verdad han cometido en este
#: banco (ver ``_UI_REPAIR_HEADER``), y por eso son estos y no otros.
#:
#: Aqui habia, hasta el 2026-07-27, una llamada partida en dos lineas. Se quito porque
#: **dejo de ser un fallo**: partir una declaracion mientras haya un corchete abierto es
#: OpenUI Lang valido y el parser lo acepta desde ``src/render/lines.py``. Un fixture
#: "invalido" que en realidad es valido mide otra cosa que la que dice medir.
_OFFLINE_INVALID = (
    'root = Stack(children = [intro], gap = "md")\n'
    'intro = TextContent("Un texto cualquiera.", "lead")\n'
    'clave = {"q1": {"correct": 1}}\n'
)



#: Blueprints JSON per format for the multi-agent offline bench.
_OFFLINE_BLUEPRINTS: dict[str, str] = {
    "explanation": json.dumps({"blocks": [
        {"id": "intro", "type": "TextContent", "intent": "enganchar", "variant": "lead"},
        {"id": "pasos", "type": "StepSequence", "intent": "concepto"},
        {"id": "aviso", "type": "Callout", "intent": "refuerzo"},
    ]}, ensure_ascii=False),
    "exercise": json.dumps({"blocks": [
        {"id": "enunciado", "type": "TextContent", "intent": "enganchar", "variant": "lead"},
        {"id": "q1", "type": "QuizItem", "intent": "verificar", "item_type": "test", "bloom": "apply"},
    ]}, ensure_ascii=False),
    "chart": json.dumps({"blocks": [
        {"id": "intro", "type": "TextContent", "intent": "enganchar", "variant": "lead"},
        {"id": "grafico", "type": "Chart", "intent": "concepto"},
    ]}, ensure_ascii=False),
    "mixed": json.dumps({"blocks": [
        {"id": "intro", "type": "TextContent", "intent": "enganchar", "variant": "lead"},
        {"id": "aviso", "type": "Callout", "intent": "refuerzo"},
        {"id": "q1", "type": "QuizItem", "intent": "verificar", "item_type": "test", "bloom": "understand"},
    ]}, ensure_ascii=False),
}

#: Content-only declarations per format (no root, no QuizItem/DragOrder).
_OFFLINE_CONTENT: dict[str, str] = {
    "explanation": (
        'intro = TextContent("Esto te sirve para resolverlo tu sin preguntar.", "lead")\n'
        'pasos = StepSequence("Como se hace", ["Comprobar la condicion", '
        '"Aplicar la regla", "Registrar lo hecho"])\n'
        'aviso = Callout("warn", "Fuera de plazo la regla cambia: consulta antes de decidir.")\n'
    ),
    "exercise": (
        'enunciado = TextContent("Un caso real de tu puesto, para resolverlo ahora.", "lead")\n'
    ),
    "chart": (
        'intro = TextContent("Los numeros que tienes que reconocer de un vistazo.", "lead")\n'
        'grafico = Chart("bar", "Valores de referencia", ["A", "B", "C"], [4, 2, 6])\n'
    ),
    "mixed": (
        'intro = TextContent("Primero la regla, y despues la compruebas.", "lead")\n'
        'aviso = Callout("info", "La regla se aplica siempre, tambien cuando hay prisa.")\n'
    ),
}

#: Interaction-only declarations + answer key per format.
_OFFLINE_INTERACTION: dict[str, str] = {
    "exercise": (
        'q1 = QuizItem("q1", "test", "apply", "Que haces primero?", '
        '["Aplicar la regla", "Avisar al responsable", "Dejarlo para luego", "Ignorarlo"])\n'
        "---ANSWER-KEY---\n"
        '{"q1": {"correct": 0, "explanation": "La regla se aplica antes de escalar."}}\n'
    ),
    "mixed": (
        'q1 = QuizItem("q1", "true_false", "understand", '
        '"La regla admite excepciones por prisa?", ["Verdadero", "Falso", "Depende del caso", "Solo si es urgente"])\n'
        "---ANSWER-KEY---\n"
        '{"q1": {"correct": 1, "explanation": "La prisa no es una excepcion."}}\n'
    ),
}


class _OfflinePlan:
    """El guion del encargo en curso: cuantos intentos salen mal antes de salir bien."""

    def __init__(self) -> None:
        self.ui_format = "explanation"
        self.bad_attempts = 0
        self._generated = 0

    def reset(self, *, ui_format: str, bad_attempts: int) -> None:
        self.ui_format = ui_format
        self.bad_attempts = bad_attempts
        self._generated = 0

    def next_program(self) -> str:
        index = self._generated
        self._generated += 1
        if index < self.bad_attempts:
            return _OFFLINE_INVALID
        return _OFFLINE_PROGRAMS.get(self.ui_format, _OFFLINE_PROGRAMS["explanation"])

    def blueprint_json(self) -> str:
        return _OFFLINE_BLUEPRINTS.get(self.ui_format, _OFFLINE_BLUEPRINTS["explanation"])

    def content_declarations(self) -> str:
        return _OFFLINE_CONTENT.get(self.ui_format, _OFFLINE_CONTENT["explanation"])

    def interaction_declarations(self) -> str:
        return _OFFLINE_INTERACTION.get(self.ui_format, "")

    def decide_json(self) -> str:
        return json.dumps(
            {"ui_format": self.ui_format, "rationale": "guion del banco en modo offline"},
            ensure_ascii=False,
        )


OFFLINE_PLAN = _OfflinePlan()


def install_offline_llm(fixture_dir: Path) -> None:
    """Hace que ``maybe_fixture_llm`` construya un ``FixtureLLMService`` auto-sembrado.

    ``FixtureLLMService`` resuelve por hash exacto de (system, user), asi que un corpus
    nuevo no tiene grabaciones y fallaria en la primera llamada. En vez de duplicar aqui
    la construccion de los prompts — que es exactamente la copia que este banco existe
    para evitar — la subclase **graba la respuesta guionizada la primera vez que ve un
    prompt** y a partir de ahi replica por el camino normal de replay.

    Se sustituye la clase en ``src.llm.fixtures`` en lugar de la funcion
    ``maybe_fixture_llm``, para que el unico punto de construccion de LLM del proyecto
    siga siendo el unico punto de construccion.
    """
    from src.llm import fixtures as fixtures_module
    from src.llm.prompts.runtime import FORMAT_DECIDER_SYSTEM

    #: Substrings that identify the multi-agent prompts without importing the
    #: full system prompt (which would pull in ``render_prompt()``).
    _BLUEPRINT_MARKER = "SkillNet. Tu trabajo es decidir la ESTRUCTURA"
    _CONTENT_WRITER_MARKER = "SkillNet Content Writer: tu tarea especifica"
    _INTERACTION_MARKER = "SkillNet Interaction Designer: tu tarea especifica"
    _ACTIVITY_AUTHOR_MARKER = "Disenas UNA actividad educativa Didact"

    def _activity_fixture(user_prompt: str) -> str:
        payload = json.loads(user_prompt)
        candidates = list(payload.get("candidate_component_ids") or ())
        refs = list(payload.get("allowed_source_refs") or ())
        component_id = candidates[0]
        definitions: dict[str, dict[str, Any]] = {
            "didact.rubric": {
                "criteria": [{
                    "id": "criterion-1", "label": "Aplicacion del procedimiento",
                    "levels": [
                        {"id": "level-1", "label": "Necesita apoyo"},
                        {"id": "level-2", "label": "Aplicacion correcta"},
                    ],
                }],
            },
            "didact.self-explanation-prompt": {
                "prompt": "Explica como aplicarias el procedimiento de la fuente.",
                "scaffolds": ["Identifica primero el paso decisivo."],
            },
            "didact.concept-map": {"definition": {
                "id": "map-1", "title": "Relaciona las ideas",
                "nodes": [
                    {"id": "n1", "label": "Situacion"},
                    {"id": "n2", "label": "Respuesta"},
                ],
                "initialRelations": [],
            }},
            "didact.drawing-response": {"definition": {
                "id": "drawing-1", "title": "Representa el proceso",
                "instructions": "Dibuja la secuencia descrita en la fuente.",
                "tools": ["freehand", "line"],
            }},
            "didact.equation-workbench": {"definition": {
                "id": "equation-1", "title": "Comprueba la relacion",
                "instructions": "Transforma la expresion paso a paso.",
                "initialExpression": "x = x",
            }},
            "didact.evidence-annotation": {"definition": {
                "id": "evidence-1", "title": "Clasifica la evidencia",
                "segments": [{"id": "s1", "text": "Fragmento de la fuente"}],
                "categories": [{"id": "c1", "label": "Evidencia"}],
            }},
            "didact.measurement-lab": {"definition": {
                "id": "measure-1", "title": "Registra una lectura",
                "instrument": {
                    "kind": "linear", "min": 0, "max": 10, "step": 1, "unit": "u"
                },
                "observedReading": 5,
            }},
            "didact.data-explorer": {"definition": {
                "schemaVersion": "1.0.0", "id": "data-1", "title": "Explora los datos",
                "axes": {
                    "x": {"label": "Caso", "domain": {"scale": "linear", "min": 0, "max": 1}},
                    "y": {"label": "Valor", "domain": {"scale": "linear", "min": 0, "max": 1}},
                },
                "series": [{
                    "id": "series-1", "label": "Fuente", "kind": "line",
                    "source": {"kind": "points", "points": [
                        {"id": "p1", "x": 0, "y": 0}, {"id": "p2", "x": 1, "y": 1}
                    ]},
                }],
                "table": {
                    "source": "series",
                    "caption": "Datos de la fuente",
                    "includeSeriesIds": ["series-1"],
                },
            }},
        }
        return json.dumps(
            {
                "component_id": component_id,
                "definition": definitions.get(component_id, {}),
                "source_refs": refs[:1],
            },
            ensure_ascii=False,
        )

    fixture_dir.mkdir(parents=True, exist_ok=True)
    settings.LLM_FIXTURE_DIR = str(fixture_dir)
    base = fixtures_module.FixtureLLMService

    class BenchFixtureLLM(base):  # type: ignore[valid-type, misc]
        def _resolve(self, system_prompt: str, user_prompt: str) -> str:
            key = fixtures_module.FixtureLLMService.key_for(system_prompt, user_prompt)
            if key not in fixtures_module.load_index(self._dir):
                is_decider = system_prompt.strip() == FORMAT_DECIDER_SYSTEM.strip()
                if is_decider:
                    response = OFFLINE_PLAN.decide_json()
                    use_case = "decide_formato"
                elif _BLUEPRINT_MARKER in system_prompt:
                    response = OFFLINE_PLAN.blueprint_json()
                    use_case = "blueprint"
                elif _CONTENT_WRITER_MARKER in system_prompt:
                    response = OFFLINE_PLAN.content_declarations()
                    use_case = "content_writer"
                elif _INTERACTION_MARKER in system_prompt:
                    response = OFFLINE_PLAN.interaction_declarations()
                    use_case = "interaction_designer"
                elif _ACTIVITY_AUTHOR_MARKER in system_prompt:
                    response = _activity_fixture(user_prompt)
                    use_case = "runtime_activity_authoring"
                else:
                    response = OFFLINE_PLAN.next_program()
                    use_case = "genera_ui"
                fixtures_module.write_fixture(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response=response,
                    relative_path=f"bench/{key}.txt",
                    use_case=use_case,
                    directory=self._dir,
                )
            return super()._resolve(system_prompt, user_prompt)

    fixtures_module.FixtureLLMService = BenchFixtureLLM  # type: ignore[misc]


# --------------------------------------------------------------------------------------
# Instrumentacion: que paso en cada intento, y por que
# --------------------------------------------------------------------------------------

#: Prompts de la llamada en curso, para el volcado de fallos. Es un contextvar porque el
#: shim del proveedor no recibe el `request_id`; los registros de nodo, que si lo reciben,
#: van por `_RECORDERS`, que no puede perderse aunque LangGraph cambie de tarea.
_CURRENT: contextvars.ContextVar[Recorder | None] = contextvars.ContextVar(
    "quality_bench_recorder", default=None
)

_RECORDERS: dict[str, Recorder] = {}

_GRAPH_NODE_NAMES = (
    "load_context",
    "probe_gate",
    "decide_formato",
    "author_activity",
    "genera_ui",
    "validate_ui",
    "persist_render",
    "fallback_seed",
    "skip_node",
)


@dataclass
class Attempt:
    """Un paso por ``genera_ui`` + ``validate_ui``."""

    index: int
    ui_format: str = "?"
    tier: str = "?"
    model: str = "?"
    raw_dsl: str = ""
    tokens_in: int | None = None
    tokens_out: int | None = None
    duration_ms: int = 0
    ok: bool = False
    errors: list[str] = field(default_factory=list)
    system_prompt: str = ""
    user_prompt: str = ""


@dataclass
class Recorder:
    """Todo lo que hace falta para explicar un render, recogido mientras corre."""

    encargo: str
    request_id: str
    arm: str = "raw"
    #: ``source_digest`` siempre es la fuente recuperada por el runtime. ``context_digest``
    #: es lo que finalmente vio el generador (igual en raw, el Markdown del pack en pack).
    source_digest: str = ""
    context_digest: str = ""
    context_kind: str = "raw_source"
    atom_ids: list[str] = field(default_factory=list)
    invariant_atom_ids: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)
    decide_called: bool = False
    decide_tokens_in: int | None = None
    decide_tokens_out: int | None = None
    decide_model: str = ""
    format_rationale: str = ""
    activity_authoring_status: str = "not_observed"
    authored_activity: dict[str, Any] | None = None
    activity_system_prompt: str = ""
    activity_user_prompt: str = ""
    activity_model: str = ""
    activity_tokens_in: int | None = None
    activity_tokens_out: int | None = None
    activity_duration_ms: int = 0
    ui_format: str = "?"
    tier: str = "?"
    source_chars: int = 0
    cache_key: str = ""
    terminal: str = ""
    #: Los prompts los aporta el shim del proveedor, que ve los `messages` exactos.
    pending_prompts: list[tuple[str, str]] = field(default_factory=list)

    def attempt(self, index: int) -> Attempt:
        while len(self.attempts) <= index:
            self.attempts.append(Attempt(index=len(self.attempts)))
        return self.attempts[index]


def install_node_instrumentation() -> None:
    """Envuelve los ocho nodos del grafo con un grabador que solo observa.

    Se parchean los nombres en ``src.agents.runtime.graph``, no en ``...nodes``:
    ``graph.py`` los importo a su propio espacio de nombres y ``build_node_graph()`` los
    resuelve al llamarse, asi que este es el sitio donde el parche llega al grafo real.
    El cuerpo de cada nodo se ejecuta sin tocar.
    """
    from src.agents.runtime import graph as graph_module

    for name in _GRAPH_NODE_NAMES:
        original = getattr(graph_module, name)
        setattr(graph_module, name, _wrap_node(name, original))


def _wrap_node(name: str, original: Any) -> Any:
    async def wrapper(state: dict) -> dict:
        recorder = _RECORDERS.get(str(state.get("request_id") or ""))
        before_in = state.get("tokens_in")
        before_out = state.get("tokens_out")
        result = await original(state)
        if name == "load_context" and recorder is not None:
            result = _replace_bench_context(result, recorder)
        if recorder is not None:
            _record(recorder, name, state, result, before_in, before_out)
        return result

    wrapper.__name__ = f"bench_{name}"
    return wrapper


def _replace_bench_context(result: dict, recorder: Recorder) -> dict:
    """Sustituye *solo* ``source_context`` para el brazo ``pack``.

    Se ejecuta despues del ``load_context`` real. De este modo node/profile/cache key,
    recuperacion, filas y resto del estado siguen siendo los de produccion; la comparacion
    cambia una unica variable y deja en el resultado las dos huellas para verificarlo.
    """
    raw_source = str(result.get("source_context") or "")
    pack = KnowledgePack.from_source(raw_source)
    recorder.source_digest = pack.source_digest
    # Tambien se anotan en raw: asi una fila A/B deja claro que ambos brazos partieron del
    # mismo conjunto de hechos, aunque solo pack los entregue como Markdown estructurado.
    raw_selection = pack.select(profile=result.get("profile"))
    recorder.atom_ids = list(raw_selection.atom_ids)
    recorder.invariant_atom_ids = list(raw_selection.invariant_ids)
    if recorder.arm == "raw":
        recorder.context_kind = "raw_source"
        recorder.context_digest = recorder.source_digest
        return result

    generated = _GENERATED_PACKS.get(recorder.encargo)
    selected = generated.selection if generated is not None else pack.select(
        profile=result.get("profile")
    )
    recorder.context_kind = (
        "generated_knowledge_pack" if generated is not None else "knowledge_pack"
    )
    recorder.context_digest = _digest(selected.markdown)
    recorder.atom_ids = list(selected.atom_ids)
    recorder.invariant_atom_ids = list(selected.invariant_ids)
    replacement = dict(result)
    replacement["source_context"] = selected.markdown
    return replacement


def _record(
    recorder: Recorder,
    name: str,
    state: dict,
    result: dict,
    before_in: int | None,
    before_out: int | None,
) -> None:
    recorder.steps.append(name)

    if name == "load_context":
        recorder.source_chars = len(str(result.get("source_context") or ""))
        recorder.cache_key = str(result.get("cache_key") or "")

    elif name == "decide_formato":
        recorder.ui_format = str(result.get("ui_format") or "?")
        recorder.tier = str(result.get("tier") or "?")
        recorder.format_rationale = str(result.get("format_rationale") or "")
        # Durante la calibracion (§6.4) no hay llamada, y por eso no hay tokens.
        recorder.decide_called = "tokens_in" in result or "tokens_out" in result
        recorder.decide_tokens_in = result.get("tokens_in")
        recorder.decide_tokens_out = result.get("tokens_out")
        if recorder.decide_called and recorder.pending_prompts:
            recorder.pending_prompts.pop(0)

    elif name == "author_activity":
        recorder.activity_authoring_status = str(
            result.get("activity_authoring_status") or "unknown"
        )
        authored = result.get("authored_activity")
        recorder.authored_activity = dict(authored) if isinstance(authored, dict) else None
        recorder.activity_model = settings.LLM_RUNTIME_FAST_MODEL or settings.LLM_MODEL
        recorder.activity_tokens_in = _delta(before_in, result.get("tokens_in"))
        recorder.activity_tokens_out = _delta(before_out, result.get("tokens_out"))
        recorder.activity_duration_ms = int(result.get("duration_ms") or 0) - int(
            state.get("duration_ms") or 0
        )
        # This call happens before genera_ui.  Consuming its prompt here prevents the
        # authoring prompt from being falsely attributed to the screen generator.
        if recorder.pending_prompts:
            recorder.activity_system_prompt, recorder.activity_user_prompt = (
                recorder.pending_prompts.pop(0)
            )

    elif name == "genera_ui":
        index = int(state.get("retry_count") or 0)
        attempt = recorder.attempt(index)
        attempt.ui_format = str(state.get("ui_format") or recorder.ui_format)
        attempt.tier = str(state.get("tier") or recorder.tier)
        attempt.model = str(result.get("model") or "?")
        attempt.raw_dsl = str(result.get("raw_dsl") or "")
        attempt.tokens_in = _delta(before_in, result.get("tokens_in"))
        attempt.tokens_out = _delta(before_out, result.get("tokens_out"))
        attempt.duration_ms = int(result.get("duration_ms") or 0) - int(
            state.get("duration_ms") or 0
        )
        if recorder.pending_prompts:
            attempt.system_prompt, attempt.user_prompt = recorder.pending_prompts.pop(0)

    elif name == "validate_ui":
        index = max(0, int(state.get("retry_count") or 0))
        attempt = recorder.attempt(index)
        attempt.ok = result.get("ui_spec") is not None
        attempt.errors = list(result.get("validation_errors") or [])

    elif name in ("persist_render", "fallback_seed", "skip_node"):
        recorder.terminal = name


def _delta(before: int | None, after: int | None) -> int | None:
    """Los nodos acumulan tokens en el estado; aqui interesa lo que costo ESTE intento."""
    if after is None:
        return None
    return int(after) - int(before or 0)


def install_prompt_capture() -> None:
    """Recoge los ``messages`` exactos que salen hacia el proveedor.

    Se engancha encima del shim de red, asi que ve lo mismo que ve el proveedor: los
    prompts del volcado de fallos no son una reconstruccion, son los que se enviaron.
    """
    original = litellm.acompletion

    async def capture(**kwargs: Any) -> Any:
        recorder = _CURRENT.get()
        if recorder is not None:
            messages = kwargs.get("messages") or []
            system = "\n".join(
                str(m.get("content") or "") for m in messages if m.get("role") == "system"
            )
            user = "\n".join(
                str(m.get("content") or "") for m in messages if m.get("role") != "system"
            )
            recorder.pending_prompts.append((system, user))
        return await original(**kwargs)

    litellm.acompletion = capture


def install_offline_prompt_capture() -> None:
    """El equivalente para ``--offline``, donde no hay llamada de red que interceptar."""
    from src.llm import fixtures as fixtures_module

    base = fixtures_module.FixtureLLMService

    class CapturingFixtureLLM(base):  # type: ignore[valid-type, misc]
        def _resolve(self, system_prompt: str, user_prompt: str) -> str:
            recorder = _CURRENT.get()
            if recorder is not None:
                recorder.pending_prompts.append((system_prompt, user_prompt))
            return super()._resolve(system_prompt, user_prompt)

    fixtures_module.FixtureLLMService = CapturingFixtureLLM  # type: ignore[misc]


# --------------------------------------------------------------------------------------
# Una ejecucion
# --------------------------------------------------------------------------------------

OUTCOMES = ("first_pass", "repaired", "fallback", "skipped", "infra_error")


@dataclass
class RunResult:
    encargo: str
    repeat: int
    #: ``raw`` conserva el pipeline de hoy; ``pack`` solo cambia ``source_context`` en
    #: este banco. Nunca se mezclan sus agregados.
    arm: str
    context: str
    outcome: str
    ui_format: str
    tier: str
    model: str
    decide_called: bool
    attempts: int
    seconds: float
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float | None
    tokens_measured: bool
    render_status: str
    steps: list[str]
    cache_key: str
    source_digest: str = ""
    context_digest: str = ""
    context_chars: int = 0
    atom_ids: list[str] = field(default_factory=list)
    invariant_atom_ids: list[str] = field(default_factory=list)
    ui_signature: str = ""
    reason: str = ""
    #: Tipos de bloque del spec que REALMENTE se sirvio, uno por aparicion. Es la medida
    #: que faltaba: un render valido con tres TextContent seguidos pasa todas las demas
    #: columnas y aun asi es la pantalla que el dueno rechazo.
    block_types: list[str] = field(default_factory=list)
    #: Observación del planificador experimental. Nunca interviene en el render; se guarda
    #: aquí para comparar la decisión viva con la propuesta sombra por perfil y encargo.
    plan_trace: dict[str, Any] | None = None
    # Spec canónico realmente servido. ``answer_key`` vive en otra columna y no entra.
    ui_spec: dict[str, Any] | None = None
    #: Server-owned rich activity, when the optional authoring node materialised one.
    #: Private answer data is deliberately absent from the public projection returned by
    #: the node.  The full draft remains in the exact captured prompt/response attempt.
    activity_authoring_status: str = "not_observed"
    authored_activity: dict[str, Any] | None = None


async def run_one(
    encargo: Encargo,
    repeat: int,
    *,
    arm: str = "raw",
    offline: bool,
    prices: dict[str, tuple[float, float]],
) -> tuple[RunResult, Recorder]:
    """Un render completo por el pipeline real, con su contexto en memoria."""
    from src.agents.runtime.runner import run_node_render

    if arm not in BENCH_ARMS:
        raise ValueError(f"brazo desconocido: {arm}")

    session = build_session(encargo)
    _patch_session_factory(session)

    if offline:
        OFFLINE_PLAN.reset(
            ui_format=encargo.default_ui_format,
            bad_attempts=encargo.offline_bad_attempts,
        )

    request_id = uuid.uuid4().hex
    recorder = Recorder(encargo=encargo.name, request_id=request_id, arm=arm)
    _RECORDERS[request_id] = recorder
    token = _CURRENT.set(recorder)

    state: dict[str, Any] = {
        "request_id": request_id,
        "org_id": str(ORG_ID),
        "user_id": str(USER_ID),
        "course_id": str(COURSE_ID),
        "node_id": str(session.node.id),
        "backend": settings.RENDER_BACKEND,
        "is_preview": False,
        "schema_version": SCHEMA_VERSION,
        "retry_count": 0,
        "validation_errors": [],
        "answer_key": {},
        "error": None,
        "current_step": "pending",
    }

    started = time.monotonic()
    failure: BaseException | None = None
    final: dict[str, Any] = {}
    try:
        final = await run_node_render(state)
    except Exception as exc:  # noqa: BLE001 - un fallo de infraestructura es un dato
        failure = exc
    finally:
        elapsed = time.monotonic() - started
        _CURRENT.reset(token)
        _RECORDERS.pop(request_id, None)

    render = session.renders[-1] if session.renders else None
    result = _classify(
        encargo=encargo,
        repeat=repeat,
        arm=arm,
        recorder=recorder,
        final=final,
        render=render,
        elapsed=elapsed,
        failure=failure,
        prices=prices,
    )
    return result, recorder


def _classify(
    *,
    encargo: Encargo,
    repeat: int,
    arm: str,
    recorder: Recorder,
    final: dict,
    render: NodeRender | None,
    elapsed: float,
    failure: BaseException | None,
    prices: dict[str, tuple[float, float]],
) -> RunResult:
    """Traduce el estado final a uno de los cinco desenlaces.

    ``infra_error`` esta separado de ``fallback`` a proposito: un 429 agotado o una clave
    caducada no dicen nada sobre la calidad del prompt, y mezclarlos convertiria una tarde
    de rate limits en una regresion imaginaria.
    """
    attempts = len(recorder.attempts)
    ok_attempts = [a for a in recorder.attempts if a.ok]
    reason = ""

    if failure is not None:
        outcome = "infra_error"
        reason = f"{type(failure).__name__}: {failure}"
    elif recorder.terminal == "skip_node":
        outcome = "skipped"
    elif recorder.terminal == "persist_render" and ok_attempts:
        outcome = "first_pass" if ok_attempts[0].index == 0 else "repaired"
    else:
        outcome = "fallback"
        infra = _infra_reason(final, recorder)
        if infra:
            outcome = "infra_error"
            reason = infra
        else:
            last = recorder.attempts[-1] if recorder.attempts else None
            reason = "; ".join(last.errors) if last and last.errors else str(
                final.get("error") or "el grafo acabo en fallback sin errores de validacion"
            )

    tokens_in, tokens_out, measured = _tokens(recorder)
    cost = _cost(recorder, prices)

    return RunResult(
        encargo=encargo.name,
        repeat=repeat,
        arm=arm,
        context=recorder.context_kind,
        outcome=outcome,
        ui_format=recorder.ui_format,
        tier=recorder.tier,
        model=(recorder.attempts[-1].model if recorder.attempts else recorder.decide_model),
        decide_called=recorder.decide_called,
        attempts=attempts,
        seconds=round(elapsed, 3),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost,
        tokens_measured=measured,
        render_status=(_plain(render.status) if render is not None else "sin fila"),
        steps=list(recorder.steps),
        cache_key=recorder.cache_key,
        source_digest=recorder.source_digest,
        context_digest=recorder.context_digest,
        context_chars=recorder.source_chars,
        atom_ids=list(recorder.atom_ids),
        invariant_atom_ids=list(recorder.invariant_atom_ids),
        ui_signature=_ui_signature(render),
        reason=reason[:400],
        block_types=_block_types(render),
        plan_trace=(
            dict(final["plan_trace"])
            if isinstance(final.get("plan_trace"), dict)
            else None
        ),
        ui_spec=(
            dict(render.ui_spec)
            if render is not None and isinstance(render.ui_spec, dict)
            else None
        ),
        activity_authoring_status=recorder.activity_authoring_status,
        authored_activity=recorder.authored_activity,
    )


def _block_types(render: NodeRender | None) -> list[str]:
    """Los tipos de bloque del ``ui_spec`` persistido, uno por aparicion.

    Se lee de la fila y no del estado del grafo a proposito: la fila lleva el spec
    **canonico**, el que ``gate.canonicalize`` re-serializo y el unico que llega al
    navegador. Un intento rechazado no cuenta aunque hubiera usado un Table precioso.
    """
    spec = getattr(render, "ui_spec", None)
    if not isinstance(spec, dict):
        return []
    components = spec.get("components")
    if not isinstance(components, list):
        return []
    return [
        str(component.get("type"))
        for component in components
        if isinstance(component, dict) and component.get("type")
    ]


def _ui_signature(render: NodeRender | None) -> str:
    """Huella del spec canonico servido, no de la salida cruda del modelo."""
    spec = getattr(render, "ui_spec", None)
    if not isinstance(spec, dict):
        return ""
    canonical = json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _digest(canonical)


_INFRA_MARKERS = (
    "RateLimitError",
    "AuthenticationError",
    "PermissionDeniedError",
    "APIConnectionError",
    "Timeout",
    "ServiceUnavailableError",
    "InternalServerError",
    "BadRequestError",
    "ContextWindowExceeded",
)


def _infra_reason(final: dict, recorder: Recorder) -> str:
    """Distingue "el proveedor fallo" de "el modelo escribio mal el programa"."""
    message = str(final.get("error") or "")
    if any(marker in message for marker in _INFRA_MARKERS):
        return message[:400]
    if not recorder.attempts and recorder.terminal == "fallback_seed":
        return message[:400] or "no se llego a generar nada"
    return ""


def _tokens(recorder: Recorder) -> tuple[int | None, int | None, bool]:
    values_in = [recorder.decide_tokens_in, recorder.activity_tokens_in] + [
        a.tokens_in for a in recorder.attempts
    ]
    values_out = [recorder.decide_tokens_out, recorder.activity_tokens_out] + [
        a.tokens_out for a in recorder.attempts
    ]
    known_in = [v for v in values_in if v is not None]
    known_out = [v for v in values_out if v is not None]
    measured = bool(known_in or known_out)
    return (
        sum(known_in) if known_in else None,
        sum(known_out) if known_out else None,
        measured,
    )


def _cost(recorder: Recorder, prices: dict[str, tuple[float, float]]) -> float | None:
    """Coste por modelo real, no por 'el modelo del render'.

    ``decide_formato`` corre en el nivel barato y ``genera_ui`` puede correr en el caro,
    asi que sumar sus tokens y multiplicar por una sola tarifa se equivoca justo en los
    formatos que mas cuestan (``chart`` y ``mixed``).
    """
    total = 0.0
    seen_any = False
    entries: list[tuple[str, int | None, int | None]] = [
        (recorder.decide_model, recorder.decide_tokens_in, recorder.decide_tokens_out),
        (
            recorder.activity_model,
            recorder.activity_tokens_in,
            recorder.activity_tokens_out,
        ),
    ]
    entries.extend((a.model, a.tokens_in, a.tokens_out) for a in recorder.attempts)
    for model, tin, tout in entries:
        if not model or (tin is None and tout is None):
            continue
        tariff = prices.get(model)
        if tariff is None:
            return None
        seen_any = True
        total += (tin or 0) / 1e6 * tariff[0] + (tout or 0) / 1e6 * tariff[1]
    return round(total, 6) if seen_any else None


def _plain(value: Any) -> str:
    return str(getattr(value, "value", value))


def _patch_session_factory(session: BenchSession) -> None:
    """Apunta las dos importaciones de ``async_session_factory`` a esta sesion."""
    from src.agents.runtime import errors as runtime_errors
    from src.agents.runtime import nodes as runtime_nodes

    runtime_nodes.async_session_factory = session  # type: ignore[assignment]
    runtime_errors.async_session_factory = session  # type: ignore[assignment]


# --------------------------------------------------------------------------------------
# Informe
# --------------------------------------------------------------------------------------


def percentile(values: list[float], fraction: float) -> float:
    """Percentil por interpolacion lineal. Con una sola medida devuelve esa medida."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


@dataclass
class Aggregate:
    runs: int = 0
    first_pass: int = 0
    repaired: int = 0
    fallback: int = 0
    skipped: int = 0
    infra_error: int = 0
    seconds: list[float] = field(default_factory=list)
    tokens_in: list[int] = field(default_factory=list)
    tokens_out: list[int] = field(default_factory=list)
    cost: float = 0.0
    cost_known: bool = True
    #: Cuantas veces aparecio cada tipo de bloque en los specs servidos.
    blocks: collections.Counter[str] = field(default_factory=collections.Counter)
    #: Tipos distintos por render, para poder decir "una pantalla usa 2,1 tipos de media"
    #: ademas de "la tanda entera toco 3 de 9".
    distinct_per_run: list[int] = field(default_factory=list)

    def add(self, run: RunResult) -> None:
        self.runs += 1
        setattr(self, run.outcome, getattr(self, run.outcome) + 1)
        self.seconds.append(run.seconds)
        if run.block_types:
            self.blocks.update(run.block_types)
            self.distinct_per_run.append(len(set(run.block_types)))
        if run.tokens_in is not None:
            self.tokens_in.append(run.tokens_in)
        if run.tokens_out is not None:
            self.tokens_out.append(run.tokens_out)
        if run.cost_usd is None:
            self.cost_known = False
        else:
            self.cost += run.cost_usd

    @property
    def graded(self) -> int:
        """Ejecuciones que dicen algo sobre la calidad (sin fallos de infraestructura)."""
        return self.first_pass + self.repaired + self.fallback

    @property
    def types_used(self) -> list[str]:
        """Tipos emitibles que aparecieron al menos una vez, en el orden del catalogo."""
        return [name for name in EMITTABLE_BLOCKS if self.blocks.get(name)]

    @property
    def types_unused(self) -> list[str]:
        return [name for name in EMITTABLE_BLOCKS if not self.blocks.get(name)]

    def rate(self, field_name: str) -> float:
        base = self.graded
        if base == 0:
            return 0.0
        return 100.0 * getattr(self, field_name) / base

    def summary(self) -> dict:
        return {
            "runs": self.runs,
            "graded": self.graded,
            "first_pass": self.first_pass,
            "repaired": self.repaired,
            "fallback": self.fallback,
            "skipped": self.skipped,
            "infra_error": self.infra_error,
            "first_pass_pct": round(self.rate("first_pass"), 1),
            "repaired_pct": round(self.rate("repaired"), 1),
            "fallback_pct": round(self.rate("fallback"), 1),
            "p50_seconds": round(percentile(self.seconds, 0.50), 2),
            "p95_seconds": round(percentile(self.seconds, 0.95), 2),
            "mean_tokens_in": round(statistics.fmean(self.tokens_in), 1)
            if self.tokens_in
            else None,
            "mean_tokens_out": round(statistics.fmean(self.tokens_out), 1)
            if self.tokens_out
            else None,
            "cost_usd_total": round(self.cost, 6) if self.cost_known else None,
            "cost_usd_per_run": round(self.cost / self.runs, 6)
            if self.cost_known and self.runs
            else None,
            # --- cobertura del catalogo (§5.3) ---------------------------------
            "distinct_block_types": len(self.types_used),
            "block_type_coverage_pct": round(
                100.0 * len(self.types_used) / len(EMITTABLE_BLOCKS), 1
            ),
            "mean_distinct_types_per_render": round(
                statistics.fmean(self.distinct_per_run), 2
            )
            if self.distinct_per_run
            else None,
            "block_types": dict(self.blocks.most_common()),
            "block_types_unused": self.types_unused,
        }


def print_table(per_encargo: dict[str, Aggregate], total: Aggregate) -> None:
    header = (
        f"{'encargo':<24} {'n':>3} {'1a':>4} {'rep':>4} {'fb':>4} {'err':>4} "
        f"{'p50 s':>7} {'p95 s':>7} {'tok in':>8} {'tok out':>8} {'USD/run':>10}"
    )
    print()
    print(header)
    print("-" * len(header))
    for name in sorted(per_encargo):
        _print_row(name, per_encargo[name])
    print("-" * len(header))
    _print_row("TOTAL", total)


def _print_row(name: str, agg: Aggregate) -> None:
    summary = agg.summary()
    cost = summary["cost_usd_per_run"]
    print(
        f"{name:<24} {agg.runs:>3} "
        f"{agg.first_pass:>4} {agg.repaired:>4} {agg.fallback:>4} {agg.infra_error:>4} "
        f"{summary['p50_seconds']:>7.2f} {summary['p95_seconds']:>7.2f} "
        f"{_num(summary['mean_tokens_in']):>8} {_num(summary['mean_tokens_out']):>8} "
        f"{('%.6f' % cost) if cost is not None else 'n/d':>10}"
    )


def _num(value: Any) -> str:
    return "n/d" if value is None else f"{value:.0f}"


def print_coverage(total: Aggregate) -> None:
    """Que parte del catalogo se uso de verdad.

    Esta seccion existe por un fallo que ninguna de las columnas de arriba veia. El nodo
    de los catorce alergenos salio ``ready``, a la primera segun la fila, con cuatro
    bloques validos — y era un parrafo con catorce cosas separadas por comas, porque el
    modelo solo habia usado ``TextContent`` y ``Callout``. Un render puede ser
    perfectamente valido y aun asi ser la pantalla equivocada, y "3 de 9" es el numero que
    lo dice en voz alta.
    """
    used = total.types_used
    print()
    print(
        f"Cobertura del catalogo: {len(used)} de {len(EMITTABLE_BLOCKS)} tipos emitibles "
        f"({100.0 * len(used) / len(EMITTABLE_BLOCKS):.0f} %)"
    )
    if total.distinct_per_run:
        print(
            f"  Tipos distintos por pantalla (media): "
            f"{statistics.fmean(total.distinct_per_run):.2f}"
        )
    total_blocks = sum(total.blocks.values()) or 1
    for name in EMITTABLE_BLOCKS:
        count = total.blocks.get(name, 0)
        share = 100.0 * count / total_blocks
        mark = "  " if count else "->"
        print(f"  {mark} {name:<14} {count:>4}  {share:>5.1f} %")
    if total.types_unused:
        print(f"  Sin usar ni una vez: {', '.join(total.types_unused)}")


def aggregate_by_arm(
    results: list[RunResult],
) -> dict[str, tuple[dict[str, Aggregate], Aggregate]]:
    """Agrega cada brazo por separado; sumar raw y pack seria una metrica inventada."""
    grouped: dict[str, tuple[dict[str, Aggregate], Aggregate]] = {}
    for run in results:
        per_encargo, total = grouped.setdefault(run.arm, ({}, Aggregate()))
        per_encargo.setdefault(run.encargo, Aggregate()).add(run)
        total.add(run)
    return grouped


def print_comparison(current: dict, previous: dict | None) -> None:
    if previous is None:
        print(
            "\nNo hay ejecucion anterior con la que comparar. La siguiente vez saldra "
            "aqui el 'antes -> ahora'."
        )
        return
    before_arms = previous.get("arms")
    after_arms = current.get("arms")
    # Los JSON antiguos llevaban un total unico. Se leen como raw para que el banco siga
    # pudiendo comparar baselines anteriores sin atribuirlos accidentalmente al pack.
    if not isinstance(before_arms, dict):
        before_arms = {"raw": {"total": previous.get("total") or {}}}
    if not isinstance(after_arms, dict):
        after_arms = {"raw": {"total": current.get("total") or {}}}
    common = [arm for arm in BENCH_ARMS if arm in before_arms and arm in after_arms]
    if not common:
        print("\nNo hay un brazo comun con la ejecucion anterior para comparar.")
        return
    print(
        f"\nComparado con {previous.get('run_id', '?')} "
        f"(fast={previous.get('model_fast', '?')}, heavy={previous.get('model_heavy', '?')}):"
    )
    rows = (
        ("acierto a la primera", "first_pass_pct", "%", 1, True),
        ("rescatados por reparacion", "repaired_pct", "%", 1, False),
        ("acaban en fallback", "fallback_pct", "%", 1, False),
        ("latencia p50", "p50_seconds", "s", 2, False),
        ("latencia p95", "p95_seconds", "s", 2, False),
        ("tokens de salida (media)", "mean_tokens_out", "", 0, False),
        ("coste por render", "cost_usd_per_run", " USD", 6, False),
        ("tipos de bloque usados", "distinct_block_types", f"/{len(EMITTABLE_BLOCKS)}", 0, True),
        ("tipos por pantalla (media)", "mean_distinct_types_per_render", "", 2, True),
    )
    for arm in common:
        if len(common) > 1:
            print(f"  brazo {arm}:")
        before = (before_arms[arm] or {}).get("total") or {}
        after = (after_arms[arm] or {}).get("total") or {}
        for label, key, unit, digits, higher_is_better in rows:
            old = before.get(key)
            new = after.get(key)
            if old is None or new is None:
                print(
                    f"  {label:<28} {_fmt(old, unit, digits):>12}  ->  "
                    f"{_fmt(new, unit, digits):>12}"
                )
                continue
            delta = new - old
            arrow = "="
            if abs(delta) > 1e-9:
                improved = delta > 0 if higher_is_better else delta < 0
                arrow = "MEJOR" if improved else "PEOR"
            print(
                f"  {label:<28} {_fmt(old, unit, digits):>12}  ->  "
                f"{_fmt(new, unit, digits):>12}   ({delta:+.{digits}f}{unit}) {arrow}"
            )


def _fmt(value: Any, unit: str, digits: int) -> str:
    if value is None:
        return "n/d"
    return f"{value:.{digits}f}{unit}"


# --------------------------------------------------------------------------------------
# Volcado de fallos
# --------------------------------------------------------------------------------------


def dump_failure(
    directory: Path,
    encargo: Encargo,
    run: RunResult,
    recorder: Recorder,
    *,
    dump_prompts: bool,
) -> Path:
    """Escribe el fallo entero, legible, en un fichero.

    Lleva la salida cruda del modelo y los mensajes del validador **literales**: "line 4:
    expected ')'" se puede arreglar y "programa invalido" no. Nunca lleva ``answer_key``.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run.outcome}--{run.arm}--{encargo.name}--r{run.repeat}.md"

    lines: list[str] = [
        f"# {encargo.name} ({run.arm}, pase {run.repeat}) -> {run.outcome}",
        "",
        f"- Motivo: {run.reason or '(sin motivo registrado)'}",
        f"- Formato elegido: {run.ui_format} (nivel {run.tier}, modelo {run.model})",
        f"- decide_formato llamo al LLM: {'si' if run.decide_called else 'no (calibracion, §6.4)'}",
        f"- Justificacion del formato: {recorder.format_rationale or '(ninguna)'}",
        f"- Estado de node_renders: {run.render_status}",
        f"- Pasos del grafo: {' -> '.join(run.steps)}",
        f"- Segundos: {run.seconds}",
        f"- cache_key: {run.cache_key}",
        f"- Contexto: {run.context} ({run.context_digest or 'sin huella'})",
        f"- Fuente recuperada: {run.source_digest or 'sin huella'}",
        f"- Atomos seleccionados: {', '.join(run.atom_ids) or '(raw)'}",
        f"- Invariantes: {', '.join(run.invariant_atom_ids) or '(raw)'}",
        f"- Firma UI: {run.ui_signature or '(sin spec servido)'}",
        "",
        "## El aprendiz",
        "",
        f"- Puesto: {encargo.role_title} ({encargo.sector})",
        f"- Experiencia: {encargo.experience_level} | preset: {encargo.preset}",
        f"- Nodos completados: {encargo.nodes_completed} | densidad del curso: "
        f"{encargo.intent_density} | short_blocks: {encargo.short_blocks}",
        f"- Banda de andamiaje: {encargo.scaffold_band} | maestria: {encargo.mastery}",
        f"- Aciertos/fallos seguidos: {encargo.consecutive_correct}/"
        f"{encargo.consecutive_failed} | ultimo error: {encargo.last_error_kind}",
        "",
        "## El nodo",
        "",
        f"- Titulo: {encargo.title}",
        f"- Criticidad: {encargo.criticality} | formato por defecto: "
        f"{encargo.default_ui_format}",
        f"- Fuente entregada al prompt: {recorder.source_chars} caracteres",
        "",
    ]

    for attempt in recorder.attempts:
        lines.extend(
            [
                f"## Intento {attempt.index} "
                f"({'valido' if attempt.ok else 'RECHAZADO'})",
                "",
                f"- Modelo: {attempt.model} | nivel: {attempt.tier} | "
                f"{attempt.duration_ms} ms",
                f"- Tokens: entrada {attempt.tokens_in}, salida {attempt.tokens_out}",
                "",
            ]
        )
        if attempt.errors:
            lines.append("### Lo que dijo el validador")
            lines.append("")
            lines.extend(f"- {error}" for error in attempt.errors)
            lines.append("")
        lines.extend(
            [
                "### Salida cruda del modelo",
                "",
                "```",
                attempt.raw_dsl.rstrip() or "(vacia)",
                "```",
                "",
            ]
        )
        if attempt.user_prompt:
            lines.extend(
                [
                    "### Prompt de usuario enviado",
                    "",
                    "```",
                    attempt.user_prompt.rstrip(),
                    "```",
                    "",
                ]
            )
        if dump_prompts and attempt.system_prompt:
            lines.extend(
                [
                    "### Prompt de sistema enviado",
                    "",
                    "```",
                    attempt.system_prompt.rstrip(),
                    "```",
                    "",
                ]
            )

    if not recorder.attempts:
        lines.extend(
            [
                "## No hubo ningun intento de generacion",
                "",
                "El render se fue a fallback antes de llamar al modelo. Mira el motivo "
                "de arriba: casi siempre es la conexion, la clave o el limite de peticiones.",
                "",
            ]
        )

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# --------------------------------------------------------------------------------------
# Persistencia y comparacion entre ejecuciones
# --------------------------------------------------------------------------------------


def load_previous(runs_dir: Path, explicit: Path | None) -> dict | None:
    if explicit is not None:
        try:
            return json.loads(explicit.read_text(encoding="utf-8"))
        except OSError as exc:
            print(f"No se pudo leer {explicit}: {exc}")
            return None
    if not runs_dir.exists():
        return None
    candidates = sorted(runs_dir.glob("quality-*.json"))
    for path in reversed(candidates):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return None


# --------------------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quality_bench",
        description=(
            "Mide la calidad de la generacion de nodos por el pipeline real. "
            "Los diales que puedes tocar estan en docs/design/tuning.md."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--model",
        help="Modelo para los DOS niveles del router (atajo de --model-fast + --model-heavy).",
    )
    parser.add_argument("--model-fast", help="Modelo del nivel 'fast' (LLM_RUNTIME_FAST_MODEL).")
    parser.add_argument("--model-heavy", help="Modelo del nivel 'heavy' (LLM_RUNTIME_HEAVY_MODEL).")
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Pases por encargo. La generacion no es determinista: 1 pase no dice nada.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Solo estos encargos (repetible, o separados por comas).",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Usa FixtureLLMService: sin clave, sin red, deterministico.",
    )
    parser.add_argument(
        "--arm",
        choices=("raw", "pack", "both"),
        default="raw",
        help=(
            "Representacion de contexto: raw conserva produccion; pack prueba un dossier "
            "Markdown local; both ejecuta y agrega los dos por separado."
        ),
    )
    parser.add_argument(
        "--pack-source",
        choices=PACK_SOURCES,
        default="structural",
        help=(
            "Origen del brazo pack: structural solo estructura la misma fuente; "
            "generated ejecuta extractor+revisor reales una vez por nodo (solo online)."
        ),
    )
    parser.add_argument("--pack-extractor-tokens", type=int, default=1_600)
    parser.add_argument("--pack-reviewer-tokens", type=int, default=1_600)
    parser.add_argument("--pack-min-invariants", type=int, default=1)
    parser.add_argument("--pack-max-atoms", type=int, default=24)
    parser.add_argument("--pack-min-fact-coverage", type=float, default=1.0)
    parser.add_argument(
        "--pack-require-evidence",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=_PACKAGE_ROOT / "bench_out",
        help="Directorio de salida (JSON con fecha + volcado de fallos).",
    )
    parser.add_argument(
        "--compare",
        type=Path,
        help="JSON concreto con el que comparar. Por defecto, la ejecucion anterior.",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=None,
        help=(
            "Segundos de espera entre encargos. Por defecto 1.0 en linea y 0 offline: "
            "el plan gratuito de Groq da 429 con facilidad."
        ),
    )
    parser.add_argument(
        "--price-in",
        type=float,
        help="USD por millon de tokens de entrada, pisando la tabla PRICES.",
    )
    parser.add_argument(
        "--price-out",
        type=float,
        help="USD por millon de tokens de salida, pisando la tabla PRICES.",
    )
    parser.add_argument(
        "--dump-prompts",
        action="store_true",
        help="Incluye tambien el prompt de sistema completo en el volcado de fallos.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Lista el corpus y sale.",
    )
    parser.add_argument("--seed", type=int, default=None, help="Semilla del jitter de espera.")
    return parser


def select_corpus(only: list[str]) -> list[Encargo]:
    if not only:
        return list(CORPUS)
    wanted: list[str] = []
    for entry in only:
        wanted.extend(part.strip() for part in entry.split(",") if part.strip())
    unknown = [name for name in wanted if name not in CORPUS_BY_NAME]
    if unknown:
        raise SystemExit(
            f"Encargos desconocidos: {', '.join(unknown)}.\n"
            f"Disponibles: {', '.join(e.name for e in CORPUS)}"
        )
    return [CORPUS_BY_NAME[name] for name in wanted]


def resolve_prices(args: argparse.Namespace) -> dict[str, tuple[float, float]]:
    if args.price_in is None and args.price_out is None:
        return dict(PRICES)

    class _Flat(dict):
        """Una tarifa unica para cualquier modelo, cuando el dueno la pasa a mano."""

        def get(self, key: Any, default: Any = None) -> Any:  # type: ignore[override]
            return (args.price_in or 0.0, args.price_out or 0.0)

    return _Flat()


async def run_bench(args: argparse.Namespace) -> int:
    global _GENERATED_PACKS

    corpus = select_corpus(args.only)
    arms = BENCH_ARMS if args.arm == "both" else (args.arm,)
    prices = resolve_prices(args)
    try:
        pack_policy = PackBenchPolicy(
            extractor_max_tokens=args.pack_extractor_tokens,
            reviewer_max_tokens=args.pack_reviewer_tokens,
            min_invariants=args.pack_min_invariants,
            max_atoms=args.pack_max_atoms,
            min_fact_coverage=args.pack_min_fact_coverage,
            require_evidence=args.pack_require_evidence,
        )
    except ValueError as exc:
        print(f"Politica pack invalida: {exc}", file=sys.stderr)
        return 2
    pause = args.pause if args.pause is not None else (0.0 if args.offline else 1.0)
    if args.seed is not None:
        random.seed(args.seed)

    # --- configuracion de modelo ------------------------------------------------
    if args.offline:
        settings.LLM_MODEL = OFFLINE_MODEL
        settings.LLM_RUNTIME_FAST_MODEL = OFFLINE_MODEL
        settings.LLM_RUNTIME_HEAVY_MODEL = OFFLINE_MODEL
        settings.EMBEDDING_MODEL = OFFLINE_MODEL
        install_offline_llm(args.out / "fixtures")
        install_offline_prompt_capture()
    else:
        if args.model:
            settings.LLM_RUNTIME_FAST_MODEL = args.model
            settings.LLM_RUNTIME_HEAVY_MODEL = args.model
        if args.model_fast:
            settings.LLM_RUNTIME_FAST_MODEL = args.model_fast
        if args.model_heavy:
            settings.LLM_RUNTIME_HEAVY_MODEL = args.model_heavy

    from src.agents.runtime.router import tier_config

    model_fast = tier_config({}, "fast").model
    model_heavy = tier_config({}, "heavy").model

    if not args.offline and not settings.LLM_API_KEY:
        print(
            "No hay LLM_API_KEY. Pon una en apps/skillnet-api/.env o lanza con --offline.",
            file=sys.stderr,
        )
        return 2
    if args.offline and args.pack_source == "generated" and "pack" in arms:
        print(
            "--pack-source generated necesita un modelo real; usa structural con --offline.",
            file=sys.stderr,
        )
        return 2

    # --- costuras ---------------------------------------------------------------
    stats = ProviderStats()
    collector = SseCollector()
    sse.publish = collector.publish  # type: ignore[assignment]
    sse.wait_for_subscriber = collector.wait_for_subscriber  # type: ignore[assignment]
    if not args.offline:
        install_provider_shim(stats, user_agent=BENCH_USER_AGENT)
        install_prompt_capture()
    install_node_instrumentation()

    _GENERATED_PACKS = {}
    if args.pack_source == "generated" and "pack" in arms:
        from src.agents.runtime.router import tier_llm

        print(f"Preparando {len(corpus)} packs revisados en segundo plano experimental...")
        try:
            _GENERATED_PACKS = await prepare_generated_packs(
                corpus, llm=tier_llm({}, "heavy"), policy=pack_policy
            )
        except Exception as exc:  # noqa: BLE001 - a broken arm must abort the comparison.
            causes: list[str] = []
            cause = exc.__cause__
            while cause is not None:
                causes.append(f"{type(cause).__name__}: {cause}")
                cause = cause.__cause__
            print(
                f"No se pudieron preparar los packs: {type(exc).__name__}: {exc}"
                + ("\nCausa de validacion: " + " <- ".join(causes) if causes else ""),
                file=sys.stderr,
            )
            return 2

    started_at = datetime.now(timezone.utc)
    run_id = f"quality-{started_at.strftime('%Y%m%d-%H%M%S')}"
    out_dir = args.out
    failures_dir = out_dir / "failures" / run_id
    runs_dir = out_dir / "runs"

    total_runs = len(corpus) * args.repeat * len(arms)
    print(f"Banco de calidad SkillNet - {run_id}")
    print(f"  modo       : {'offline (fixtures)' if args.offline else 'en linea'}")
    print(f"  modelo fast: {model_fast}")
    print(f"  modelo heavy: {model_heavy}")
    print(f"  brazo(s)   : {', '.join(arms)}")
    if "pack" in arms:
        print(f"  pack source: {args.pack_source}")
    print(
        f"  encargos   : {len(corpus)} x {args.repeat} pases x {len(arms)} brazo(s) "
        f"= {total_runs} renders"
    )
    print(f"  salida     : {out_dir}")

    results: list[RunResult] = []
    dumped: list[str] = []
    index = 0
    for repeat in range(1, args.repeat + 1):
        for encargo in corpus:
            for arm in arms:
                index += 1
                print(
                    f"[{index:>3}/{total_runs}] {encargo.name} ({arm}, pase {repeat}) ... ",
                    end="",
                    flush=True,
                )
                run, recorder = await run_one(
                    encargo, repeat, arm=arm, offline=args.offline, prices=prices
                )
                results.append(run)
                marker = {
                    "first_pass": "OK a la primera",
                    "repaired": "OK tras reparar",
                    "fallback": "FALLBACK",
                    "skipped": "saltado (ya dominado)",
                    "infra_error": "ERROR DE INFRAESTRUCTURA",
                }[run.outcome]
                print(f"{marker} [{run.ui_format}/{run.tier}] {run.seconds:.2f}s")
                if run.outcome in ("fallback", "repaired", "infra_error"):
                    path = dump_failure(
                        failures_dir,
                        encargo,
                        run,
                        recorder,
                        dump_prompts=args.dump_prompts,
                    )
                    dumped.append(str(path))
                    print(f"    volcado -> {path.name}")
                if pause and index < total_runs:
                    await asyncio.sleep(pause)

    # --- agregacion -------------------------------------------------------------
    aggregates = aggregate_by_arm(results)
    for arm in arms:
        per_encargo, total = aggregates[arm]
        print(f"\nBrazo {arm}")
        print_table(per_encargo, total)
        print_coverage(total)

    if stats.rate_limited or stats.exhausted:
        print(
            f"\nLimite de peticiones: {stats.rate_limited} esperas "
            f"({stats.rate_limit_seconds:.0f}s dormidos), {stats.exhausted} agotadas."
        )
    if any(not total.cost_known for _, total in aggregates.values()):
        print(
            "\nColumna de coste en 'n/d': algun modelo no tiene tarifa en PRICES "
            "(scripts/quality_bench.py) y el banco no se inventa precios. "
            "Anadelo alli o pasa --price-in/--price-out."
        )
    if any(not r.tokens_measured for r in results):
        unmeasured = sum(1 for r in results if not r.tokens_measured)
        print(
            f"\n{unmeasured} de {len(results)} renders sin contabilidad de tokens: el "
            "proveedor no la devolvio. Los tokens y el coste de esos renders no cuentan."
        )

    arm_payload = {
        arm: {
            "total": total.summary(),
            "per_encargo": {
                name: aggregate.summary() for name, aggregate in sorted(per_encargo.items())
            },
        }
        for arm, (per_encargo, total) in aggregates.items()
    }
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "offline": bool(args.offline),
        "model_fast": model_fast,
        "model_heavy": model_heavy,
        "repeat": args.repeat,
        "arms": arm_payload,
        "corpus": [e.name for e in corpus],
        "prompt_version": _prompt_version(),
        "catalog_version": _catalog_version(),
        "provider": asdict(stats),
        "pack_source": args.pack_source,
        "pack_policy": asdict(pack_policy),
        "pack_preparation": {
            name: {
                "pack_hash": artifact.pack_hash,
                "pack_payload": artifact.pack_payload,
                "markdown": artifact.selection.markdown,
                "input_tokens": artifact.input_tokens,
                "output_tokens": artifact.output_tokens,
                "duration_ms": artifact.duration_ms,
                "atom_count": len(artifact.selection.atom_ids),
                "invariant_count": len(artifact.selection.invariant_ids),
                "fact_coverage": round(artifact.fact_coverage, 4),
                "matched_fact_ids": list(artifact.matched_fact_ids),
                "missing_fact_ids": list(artifact.missing_fact_ids),
            }
            for name, artifact in sorted(_GENERATED_PACKS.items())
        },
        "runs": [asdict(r) for r in results],
        "failure_dumps": dumped,
    }
    # Compatibilidad deliberada con los informes raw anteriores. En ``both`` no existe
    # total global: promediar los brazos esconderia exactamente el efecto que se mide.
    if len(arms) == 1:
        payload["total"] = arm_payload[arms[0]]["total"]
        payload["per_encargo"] = arm_payload[arms[0]]["per_encargo"]

    previous = load_previous(runs_dir, args.compare)
    print_comparison(payload, previous)

    runs_dir.mkdir(parents=True, exist_ok=True)
    json_path = runs_dir / f"{run_id}.json"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(f"\nResultado guardado en {json_path}")
    if dumped:
        print(f"Fallos volcados en {failures_dir} ({len(dumped)} ficheros)")

    return 1 if all(total.infra_error and not total.graded for _, total in aggregates.values()) else 0


def _prompt_version() -> str:
    from src.llm.prompts.runtime import PROMPT_VERSION

    return PROMPT_VERSION


def _catalog_version() -> str:
    try:
        from src.render.prompt import catalog_version

        return catalog_version()
    except Exception as exc:  # noqa: BLE001 - el artefacto puede no estar generado
        return f"(no disponible: {type(exc).__name__})"


def main() -> int:
    args = build_parser().parse_args()
    if args.list:
        print(f"{'encargo':<24} {'criticidad':<12} {'formato':<12} {'aprendiz'}")
        for encargo in CORPUS:
            print(
                f"{encargo.name:<24} {encargo.criticality:<12} "
                f"{encargo.default_ui_format:<12} "
                f"{encargo.role_title} / {encargo.sector} "
                f"({encargo.experience_level}, {encargo.preset}, "
                f"{encargo.nodes_completed} nodos)"
            )
        return 0
    if args.repeat < 1:
        raise SystemExit("--repeat tiene que ser al menos 1")
    return asyncio.run(run_bench(args))


if __name__ == "__main__":
    os.environ.setdefault("LITELLM_LOG", "ERROR")
    raise SystemExit(main())
