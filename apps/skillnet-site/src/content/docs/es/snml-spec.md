---
title: "Especificación SNML"
order: 32
section: "core"
---

# SNML: especificación del lenguaje de marcado de SkillNet

> **Estado: sustituido. No describe el código actual.** SNML fue el formato de contenido
> propuesto en v1: Markdown válido con bloques delimitados por `:::` para componentes
> interactivos. Nunca se implementó, y no queda ninguna referencia a SNML en
> `apps/skillnet-api` ni en `apps/skillnet-web`.

## Qué se usa en su lugar

El contenido de una lección no viaja como marcado, sino como **`ui_spec`**: una
representación intermedia en JSON que los agentes emiten y que el frontend renderiza con el
kit de componentes OpenUI. La decisión y sus consecuencias están en
[OpenUI: adopción](/docs/openui-adoption), y el vocabulario de bloques congelado en
[Cursos dinámicos (v2)](/docs/dynamic-courses) §5.

| Lo que SNML proponía | Lo que hay en el código |
|---|---|
| Marcado de texto con bloques `:::` | `ui_spec` en JSON, emitido por los agentes de render |
| Analizador por líneas o expresiones regulares | Validación por esquema sobre el `ui_spec` |
| Dos modos de renderizado (doc y web) | Un solo renderizador de componentes (`UiSpecRenderer`) |
| Autoría manual por un administrador | Generación por el pipeline multiagente, con edición del esquema |

## Por qué se conserva esta página

Sigue publicada porque otras páginas la citan como el origen de decisiones que sí se
mantuvieron —la estructura por encabezados como frontera de fragmentación, y el reparto de
ejercicios por nivel de Bloom— y porque explica por qué el formato final es una IR en JSON y
no un formato de autoría. La especificación completa, con su sintaxis y sus ejemplos, se
retiró: describía un formato que no existe.
