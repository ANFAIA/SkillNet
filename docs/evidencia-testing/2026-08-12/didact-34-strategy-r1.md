# Estrategias para usar los 34 componentes Didact — síntesis R1

Fecha: 2026-08-12
Estado: experimentación offline; no conectado a producción

## Decisión de producto que se está probando

Los 34 componentes forman el inventario creativo de SkillNet. Una shortlist es memoria
de trabajo para una decisión, no una whitelist ni una eliminación permanente. Un
componente complejo puede requerir autoría estructurada, datos, media, persistencia o un
runtime específico; esa necesidad se registra como trabajo pendiente y no como motivo
para borrarlo del catálogo.

## Estrategias comparadas

### 1. Oportunidades durante la creación del curso

Después de producir el esquema y el knowledge pack de cada nodo se prepara, en segundo
plano, una cartera de experiencias posibles. No contiene la pantalla final ni texto
personalizado: conserva intención pedagógica, grounding, capacidades, puertos y los ejes
que todavía puede adaptar el runtime.

| Variante | Opciones | Tipos cubiertos en el corpus | Diversidad local | Margen de cambio por perfil | Contexto |
|---|---:|---:|---:|---:|---:|
| Relevancia | 5 | 30/34 | 0,429 | 0,21 | ~829 tokens |
| Balanceada | 5 | 23/34 | **0,624** | 0,38 | ~829 tokens |
| Exploratoria | 8 | 26/34 | 0,587 | **0,68** | ~1.148 tokens |

Las tres consideraron 34/34 componentes por nodo y conservaron 100% de grounding.

### 2. Recuperación progresiva en runtime

El runtime comienza con tres candidatos, amplía a cinco si la experiencia es débil y
abre el catálogo de 34 mediante un productor especializado si todavía falta una
capacidad educativa.

| Métrica | Top 5 fijo | Progresivo 3→5→34 |
|---|---:|---:|
| Calidad proxy | 91,46 | **94,27** |
| Ajuste a preferencia | 53,9% | **66,7%** |
| Ajuste al tema | 94,9% | **98,7%** |
| Entropía de selecciones | 4,239 | **4,393** |
| Contexto proxy | **5,0** | 24,96 |
| Latencia proxy | **5,0** | 43,27 |

El catálogo completo se abrió en 53,8% de las ejecuciones. Mejora calidad y
personalización, pero el umbral probado escala con demasiada frecuencia y debe afinarse.

### 3. Especialistas multiagente

Cinco especialistas por capacidad —contenido, evaluación, media, simulación y
determinista— proponen al mismo árbitro tipado. La unión de sus inventarios es 34/34.

| Variante | Riqueza | Grounding | Cambio causal | Trabajo total | Camino crítico paralelo |
|---|---:|---:|---:|---:|---:|
| Central completa | **0,664** | 0,158 | 0,090 | **2.968** | 2.968 |
| Especialistas | 0,628 | **0,258** | **0,133** | 3.789 | **2.085** |
| Especialistas + expansión | 0,647 | 0,200 | 0,100 | 3.890 | 2.127 |

Los especialistas mejoran grounding y sensibilidad al perfil, pero no ganan todavía en
riqueza y hacen más trabajo total. No justifican ejecutarse siempre.

## Arquitectura provisional ganadora

La evidencia favorece una composición de las tres estrategias:

```text
esquema del curso
  → knowledge pack por nodo
  → cartera automática de 5–8 oportunidades, derivada de los 34
  → personalización on the fly dentro de la cartera
  → gate de riqueza, grounding y viabilidad
      → suficiente: materializar la experiencia
      → insuficiente: ampliar 3→5→34 y llamar al especialista necesario
  → ActivityDefinition validada
  → OpenUI/Didact lazy
```

La cartera debería aparecer de forma opcional dentro del desplegable del nodo del
esquema, no como un paso obligatorio. El creador puede favorecer o evitar una familia y
pedir más alternativas, mientras el camino normal continúa automáticamente.

## Qué no se concluye todavía

- Los proxies no prueban calidad de generación LLM ni aprendizaje real.
- Cubrir más nombres de componentes no equivale a mayor riqueza.
- No está calibrado el umbral que decide cuándo abrir los 34.
- No se ha demostrado que ocho oportunidades superen cinco en el curso final.
- Faltan ejemplos generados y evaluados a ciegas con modelos pequeños, tokens, coste y
  latencia de pared.

## Próxima ronda

Comparar, sobre los mismos knowledge packs y perfiles:

1. cartera balanceada de 5;
2. cartera exploratoria de 8;
3. cartera de 5 con expansión progresiva;
4. cartera de 5 con especialista condicional;
5. catálogo completo como control de techo.

La promoción exige gates válidos, mayor calidad pedagógica en cola baja, diferencia
causal entre perfiles cuando proceda y una relación coste/calidad mejor que el control.
