---
title: "Comunicación entre agentes"
order: 58
section: "research"
group: "multi-agent"
---

# Comunicación entre agentes

## El problema

Un único agente trabajando para una persona es el caso fácil. Los problemas empiezan cuando los agentes **se comunican entre personas** · mi agente y el de mi vecino, o un equipo donde cada quien ejecuta el suyo y tienen que intercambiar conocimiento para sacar el trabajo adelante. En el instante en que dos agentes pertenecientes a personas distintas hablan, aparece una pregunta que un agente solitario nunca enfrenta: cuando mi agente le pide algo al tuyo, ¿qué puede revelar el tuyo, y qué puede aceptar el mío? Cada agente se sienta sobre un cuerpo de conocimiento que no es todo compartible · parte es privado de su dueño, parte se comparte para una tarea y no para la siguiente.

Los protocolos de agentes de hoy no responden a esto. A2A, y la pila a su alrededor como MCP para herramientas, manejan cómo los agentes se encuentran y se autentican entre sí · demostrar que un agente es quien dice ser · y luego devuelven la pregunta más difícil, qué puede revelar uno a otro, a cada implementación. En la práctica, la frontera termina viviendo como una **norma blanda**: una línea en un `CLAUDE.md`, una nota de "no compartas esto", una skill que dice "usa solo el catálogo público." Esa prosa es **probabilística**. Describe una frontera; no aplica ninguna; que se respete depende del modelo que la lea. A medida que los agentes se sitúan cada vez más entre las personas y su conocimiento, eso es dejar mucho a la buena voluntad · y es el mismo muro con el que esta investigación ya chocó desde el lado de la clasificación: la privacidad es una decisión humana, no una propiedad del texto, y no se puede confiar en un lector probabilístico para vigilarla.

Así que la pregunta que vale la pena hacer es esta: **¿puede hacerse determinista la frontera que rige qué cruza entre agentes** · decidida por una regla, fuera del agente, de la misma manera cada vez · y sostenerse incluso entre dos agentes que nunca fueron presentados?

## La forma de la respuesta

La decisión tiene que salir de la buena voluntad del agente y posarse sobre algo que el agente no pueda doblegar. El movimiento es adjuntarla a los **datos**: cada pieza de conocimiento lleva una etiqueta, cada solicitante lleva lo que se le permite tener, y lo que puede cruzar es una simple comparación entre ambos, hecha en la puerta en lugar de discutida dentro del agente.

```yaml
---
compartment: jose:budget
---
```

La comparación es de inclusión de conjuntos · puedes recibir una pieza si tus compartimentos contienen el suyo. Donde la capa blanda *describe* una frontera, esta *decide*. Descansa sobre tres piezas, tomadas en orden: qué puede cruzar, qué cruzó, y dónde se encuentran los agentes.

## 1. El protocolo · qué puede cruzar

El acceso normalmente se concede a una *relación*: este agente puede alcanzar aquel recurso. Eso es lo que asume A2A, y funciona cuando ambos fueron presentados y aprovisionados de antemano · bien dentro de una sola empresa, imposible entre agentes que se encuentran por primera vez. Poner el permiso sobre los **datos** elimina la presentación. Una pieza lleva sus compartimentos, un solicitante lleva los suyos, y lo que puede cruzar es la inclusión entre ambos · sin audiencia nombrada, nada cableado por par. Entre mi agente y el de un vecino que nunca conocí, la pieza establece sus propios términos, el solicitante trae sus propias afirmaciones, y la frontera las resuelve en el acto.

La preocupación obvia es que un solicitante que lleva sus propias etiquetas podría simplemente mentir sobre ellas. No puede, porque una etiqueta es afirmada por el **dueño** de ese compartimento, no escrita por quien pregunta. El agente de mi vecino puede presentar "Jose me concedió `jose:budget`," y eso solo se sostiene porque Jose lo firmó, o lo escribió en algún lugar que solo Jose puede escribir. Puedes llevar una afirmación; no puedes falsificar de quién es. Esta es la razón por la que la etiqueta viaja con los datos mientras la autoridad se queda con el dueño · juntas son lo que hace que una afirmación llevada sea confiable sin que nadie haya sido registrado de antemano.

Dos propiedades más hacen de esto algo más que un reetiquetado. Una pieza **derivada** de otras hereda la *unión* de sus etiquetas: un resumen construido a partir de dos compartimentos solo puede cruzar hacia alguien que posea ambos, así que la frontera sigue al conocimiento a medida que el agente lo reelabora, no solo dónde se archivó primero. Y como la verificación se sitúa en la puerta · en el camino hacia el contexto del agente y en el camino de salida · la garantía más firme resulta ser la más simple: una pieza que el agente nunca recibe es una que no puede transmitir. Eso es deliberado. No se puede confiar en que un agente probabilístico retenga lo que ya se le ha dado, así que el control nunca se lo pide; decide qué se le da al agente en primer lugar. El control vive en la frontera, como ya argumentan las notas de coordinación, y la etiqueta es lo que permite que esa frontera decida de forma determinista en lugar de caso por caso.

## 2. Trazabilidad · qué cruzó

Una norma blanda no deja rastro de si se obedeció. Si un agente ignora "no compartas esto", nada en el sistema lo nota, y no hay nada que señalar después. Una frontera determinista cambia eso simplemente por ser el único lugar por donde todo pasa: cada cruce puede quedar registrado · qué se leyó, qué se emitió, qué etiqueta lo autorizó, y en qué dirección.

El registro se mantiene en la frontera, no por el agente, por la misma razón que la decisión también lo está · no se puede confiar en que un componente probabilístico informe honestamente sobre sí mismo. Por sí solo, el registro no previene nada; su valor es el alcance. Cubre los casos que no pueden prevenirse de forma determinista, y el más claro de ellos es la agregación: varias piezas, cada una individualmente al alcance de alguien, que juntas revelan algo que ninguna revelaba por sí sola. Una regla por pieza no puede verlo venir. Un registro puede mostrarlo después · este solicitante extrajo estas piezas, en esta ventana, y su combinación cruzó una línea. Lo que no se puede bloquear se vuelve al menos **detectable y atribuible**, que es la diferencia entre un incidente que se puede investigar y uno del que nunca te enteras.

## 3. El espacio de trabajo · dónde se encuentran los agentes

Todo esto tiene que vivir en algún lugar. El espacio de trabajo es el espacio compartido donde varias personas y sus agentes se encuentran · y, crucialmente, no comparten todo lo que hay en él. Las etiquetas dividen un espacio en regiones privadas y compartidas: estar almacenado en el mismo lugar no es lo mismo que ser visible. Mis notas privadas, las notas privadas de mi vecino, y la parte en la que trabajamos juntos se sientan en el mismo espacio de trabajo, y las etiquetas · no carpetas separadas, no servidores separados · deciden quién ve qué.

Es también donde vive "quién tiene qué compartimentos", y vive de una manera deliberadamente no centralizada. No hay un directorio global de las habilitaciones de todos que construir y mantener sincronizado. Cada dueño declara solo sus propios compartimentos · una lista pequeña que controla, sobre su propio espacio de nombres · y eso basta, porque un solicitante solo necesita probar los compartimentos relevantes para la pieza que tiene delante. Nadie tiene que sostener el cuadro completo.

Dos cosas, entonces, definen el espacio: el **protocolo** (qué puede cruzar) y la **trazabilidad** (qué cruzó). Todo lo demás · cómo cada persona configura, ejecuta, u orquesta sus propios agentes dentro de él · se deja abierto a propósito. El espacio de trabajo es menos una herramienta particular que un lugar donde estas fronteras se sostienen sin importar las herramientas que cada parte traiga consigo.

## Por qué importa aquí

El caso cerrado de un solo dueño apenas necesita nada de esto · una carpeta y un hábito suelen bastar. Lo que lo obliga es el caso abierto y compartido que crea la comunicación entre agentes: una plataforma donde muchas organizaciones y personas tienen conocimiento solapado-pero-no-idéntico, equipos que deben compartir para sacar el trabajo adelante sin exponerlo todo, agentes actuando en nombre de personas distintas al mismo tiempo. Ahí, una norma escrita por relación ni escala ni obliga, mientras que una etiqueta que viaja con los datos hace ambas cosas. Es, al final, el lado de la aplicación de lo que concluyó la investigación de fronteras semánticas · el humano decide qué es privado, y el único trabajo de la máquina es sostener esa línea, de la misma manera cada vez.

## Decisiones tomadas, caminos dejados de lado

- Dentro de un espacio que ya es de confianza, la frontera se aplica mediante etiquetas de escritura controlada · solo un dueño escribe las suyas propias · no mediante criptografía. Defenderse de un host comprometido es un problema separado y más pesado, dejado de lado aquí.
- Sin directorio central de quién-sabe-qué. Cada dueño declara solo sus propios compartimentos; no hay nada global que acordar o mantener.
- La identidad · demostrar que eres quien dices ser · se trata como una dependencia externa, no parte de esto. El modelo solo necesita un identificador verificado y los compartimentos que lleva; cómo se demuestran queda fuera de alcance.

## Preguntas abiertas

- **Agregación** · piezas individualmente al alcance que se combinan en algo más. Las verificaciones por pieza la pierden (también abierta en las notas principales de coordinación).
- **Cruzar una frontera de confianza** · una frontera se sostiene solo donde el runtime está controlado. Una vez que una pieza está dentro del runtime de otra persona, la garantía caduca.
- **Sobreclasificación** · una unión cautelosa deriva hacia marcarlo todo con la máxima restricción. Cuándo es seguro rebajar una etiqueta de nuevo queda sin resolver.

Ver las [notas de coordinación](https://github.com/ANFAIA/SkillNet/blob/main/README.md) para el modelo circundante · mandatos, aduana de frontera, y los cinco protocolos.

## Implementación concreta

[DBP (Data Boundary Protocol)](https://github.com/JoseEstevez520/DBP) es una implementación de referencia de estas ideas. Proporciona verificaciones deterministas de frontera, acceso a compartimentos basado en etiquetas, herencia (unión de etiquetas en datos derivados), una traza de auditoría inmutable, y escalación R7 para anulaciones con humano en el bucle. Implementado en Python con 292 pruebas, un sistema de despliegue de 16 agentes, y bancos de rendimiento (>50K verificaciones/seg).
