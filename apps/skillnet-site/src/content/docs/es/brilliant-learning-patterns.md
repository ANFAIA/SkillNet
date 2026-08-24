---
title: "Patrones de aprendizaje estilo Brilliant"
order: 40
section: "extensibility"
---

# Patrones de experiencia de Brilliant aplicables a SkillNet

**Fecha de observacion:** 2026-08-12  
**Estado:** referencia de diseno y propuesta de experimentos; no describe funcionalidad ya
implementada.  
**Alcance:** distribucion de lecciones, profundidad interactiva, progresion, feedback y navegacion.

Este documento no propone copiar la interfaz, el contenido ni las mecanicas propietarias de
Brilliant. Extrae patrones observables de sus superficies publicas y los traduce a decisiones que
encajan con OpenUI, los `NodeKnowledgePack` y Didact.

## 1. Que se observo directamente

Las afirmaciones de esta seccion proceden de paginas publicas de Brilliant; no requieren acceso a
una cuenta ni reconstruyen contenido protegido.

### Jerarquia y navegacion

- El catalogo agrupa cursos en **Learning Paths** ordenados desde fundamentos hasta aplicacion, con
  checkpoints regulares. Un camino recomienda una secuencia, pero Premium permite saltar a
  cualquier leccion; el nivel gratuito conserva avance secuencial.
- La ficha publica de *Solving Equations* presenta una jerarquia visible de **curso -> 13 niveles ->
  4-7 lecciones por nivel -> Level Review**. Declara 68 lecciones y 895 ejercicios. La persona puede
  ver el mapa completo, pero la accion principal sigue siendo empezar o continuar la siguiente
  leccion.
- Los nombres muestran una progresion de acciones y modelos: encontrar desconocidos, construir
  expresiones, sustituir, distribuir, factorizar, combinar, trabajar con desigualdades y razonar
  con sistemas. No es una lista plana de temas independientes.

Fuentes: [catalogo publico](https://brilliant.org/courses/),
[Solving Equations](https://brilliant.org/courses/pre-algebra/),
[Learning Paths](https://brilliant.org/help/features/what-are-learning-paths/).

### Ritmo de aprendizaje

- Brilliant describe sus lecciones como explicaciones breves mezcladas con problemas manipulables,
  simulaciones y feedback inmediato.
- En *Solving Equations* afirma que cada leccion comienza con un problema en el borde de lo que la
  persona ya comprende, que exige un salto mental pequeno. Primero permite probar; los nombres y la
  teoria formal aparecen despues de construir intuicion.
- Para un concepto no generan una unica pregunta: describen una rampa de dificultad, variaciones y
  casos limite. Su referencia publica habla de mas de veinte problemas por concepto en algunos
  cursos.
- En cursos de programacion buscan una **actividad central que escale de simple a compleja**. En su
  ejemplo de procesamiento de imagenes, la misma superficie permite descomponer operaciones,
  combinarlas y recibir una consecuencia visual inmediata.

Fuentes: [Solving Equations: action first](https://blog.brilliant.org/solving-equations/),
[Hand-crafted, machine-made](https://blog.brilliant.org/hand-crafted-machine-made/),
[Decomposition and Abstraction](https://blog.brilliant.org/decomposition-and-abstraction/),
[Brilliant Basics](https://brilliant.org/help/using-brilliant/).

### Profundidad de interaccion y feedback

- La interaccion no se limita a seleccionar una respuesta: los ejemplos publicos incluyen arrastrar
  una tangente, equilibrar pesos, construir ecuaciones, configurar filtros, manipular circuitos y
  observar consecuencias.
- El feedback principal puede estar en el propio sistema: una balanza se inclina, una imagen cambia
  o una simulacion deja de alcanzar el objetivo. Despues puede aparecer una explicacion o una pista.
- Koji usa el estado de la leccion, los intentos incorrectos y los puntos de bloqueo. Puede senalar
  una region, anotar una grafica o introducir una pregunta intermedia. Su ayuda aumenta al comenzar
  y se retira cuando toca demostrar conocimiento.
- Brilliant no considera suficiente que una actividad compile. Sus evals comprueban correccion,
  solucionabilidad, claridad visual, consistencia de estados, estados imposibles y plausibilidad del
  modelo. Una actividad fallida se descarta antes de revision humana.

Fuentes: [Koji y feedback contextual](https://blog.brilliant.org/a-world-class-tutor-in-every-home/),
[evals de juegos educativos](https://blog.brilliant.org/when-almost-right-is-catastrophically-wrong-evals-for-ai-learning-games/).

## 2. Inferencias de diseno

Estas son interpretaciones, no afirmaciones publicadas literalmente por Brilliant.

### "Una idea por pantalla" significa una mision, no un widget

La unidad util parece ser un **beat cognitivo**: una pregunta, decision o manipulacion principal. Un
beat puede ser pequeno y resolverse en una pantalla, pero una actividad rica puede conservarse
durante varias fases:

```text
reto -> exploracion -> consecuencia -> pista/reintento -> formalizacion -> variacion
```

Todas esas fases pueden ocurrir dentro de una misma simulacion si siguen respondiendo a la misma
pregunta. Separarlas en seis tarjetas no la hace mas clara. Del mismo modo, una pantalla con tabla,
texto, test y acordeon puede seguir siendo plana si contiene varias misiones que compiten.

### La variedad valiosa ocurre a lo largo de la secuencia

Brilliant parece priorizar continuidad de una metafora o actividad central dentro de un curso
--balanza, patron visual, filtro de imagen-- y variar problemas, restricciones y dificultad. Por
tanto, la variedad no debe medirse solo como numero de tipos Didact por pantalla. Hay tres niveles:

1. **profundidad local:** estados, acciones, feedback y reintentos dentro de una actividad;
2. **variacion de practica:** nuevos casos de la misma capacidad sin cambiar de objetivo;
3. **cambio de representacion:** otra perspectiva cuando aporta comprension o transferencia.

### El feedback es parte del componente, no texto posterior

Cuando la consecuencia de una accion es visible dentro del modelo, la persona puede formular y
corregir hipotesis. Un mensaje generico de correcto/incorrecto no sustituye esa relacion causal. La
explicacion textual sigue siendo util, pero debe responder al intento concreto y no ocupar el lugar
de la experiencia.

## 3. Contraste con SkillNet y Didact

### Lo que ya esta bien encaminado

- `NodeKnowledgePack` separa invariantes y evidencia de la narracion final.
- La arquitectura distingue objetivo, mision, representacion, componente y apoyo.
- El resolver entrega una shortlist, en vez de mostrar todo Didact al modelo.
- `ActivityDefinition` permite separar configuracion publica, evaluacion privada y estado del
  alumno.
- `Declined`, los requisitos de puertos y los validadores por componente evitan fingir simulaciones
  o inventar datasets.
- OpenUI sigue creando la composicion en el momento; Didact aporta superficies declarativas y no un
  segundo motor de cursos.

### El hueco actual

El pipeline decide bien **que componente puede aparecer**, pero todavia no representa con suficiente
claridad **como se desarrolla una experiencia durante varias fases**. El nodo y la pantalla tienden
a coincidir. Eso favorece dos fallos:

- componer varios bloques breves alrededor de una explicacion y llamarlo riqueza;
- generar una actividad rica como una configuracion aislada, sin rampa, variaciones ni feedback
  adaptado al intento.

Tambien falta expresar continuidad: dos nodos consecutivos pueden seleccionar componentes distintos
aunque pedagogicamente convenga conservar la misma mecanica y aumentar una sola dificultad.

## 4. Direccion recomendada

### 4.1 Anadir un plan de beats, no otra plantilla de pantalla

Entre el plan de experiencia y OpenUI conviene introducir una secuencia pequena y tipada:

```text
LearningExperiencePlan
  -> beats[2..5]
       mission
       phase: challenge | explore | formalize | vary | apply | checkpoint | reflect
       evidence_required
       activity_ref opcional
       support_policy
       page_boundary_reason
  -> OpenUI genera solo el beat actual
```

No deben aparecer siempre las siete fases. El plan elige las minimas que exige el objetivo y puede
mantener un mismo `activity_ref` entre beats. Asi, el curso sigue siendo on-the-fly sin reconstruir
la intencion pedagogica en cada pantalla.

### 4.2 Regla para decidir el salto de pantalla

Mantener la actividad actual cuando:

- sigue la misma mision y el mismo modelo causal;
- el siguiente paso depende del estado o intento anterior;
- cambiar de superficie haria perder manipulacion, comparacion o contexto.

Crear una pantalla nueva cuando:

- cambia la accion cognitiva principal;
- comienza una variacion que debe medirse sin ayudas anteriores;
- se pasa de exploracion a transferencia o checkpoint;
- la densidad o accesibilidad hacen que la composicion deje de ser operable.

La frontera se registra como razon de politica, no se delega a una preferencia estetica del LLM.

### 4.3 Elegir una mecanica central por tramo

Cada nivel o pequeno grupo de nodos deberia poder congelar un `core_mechanic_id`. El resolver sigue
admitiendo alternativas, pero favorece continuidad mientras la mecanica:

- produzca la evidencia requerida;
- admita la siguiente dificultad;
- siga siendo accesible;
- no fuerce datos que la fuente no contiene.

Esto no reduce la personalizacion: una persona puede recibir mas pistas, otra una entrada mas
directa y otra una representacion alternativa. Lo estable es el objetivo y la coherencia del tramo,
no una pantalla canonica compartida.

### 4.4 Contrato minimo de feedback rico

Un componente evaluable deberia declarar, cuando aplique:

1. consecuencia observable de la accion;
2. diagnostico basado en el intento, no en la identidad;
3. escalera de pistas;
4. posibilidad de reintentar sin revelar inmediatamente;
5. explicacion o solucion tras evidencia suficiente;
6. evento que permita reducir apoyo en intentos posteriores.

Para simulaciones se anaden alcance de estados, invariantes y plausibilidad. Para preguntas cerradas,
la clave permanece en servidor.

## 5. Siguiente ronda de experimentos

No conviene redisenar toda la navegacion aun. Primero hay que comprobar si la secuencia produce una
experiencia mejor que la pantalla actual.

### Experimento A: pantalla compuesta frente a beats

Mismo `NodeKnowledgePack`, objetivo y perfil:

- control: una pantalla OpenUI actual;
- tratamiento: 3 beats (`challenge -> explore/formalize -> checkpoint`) con continuidad de estado.

Medir cobertura, acciones significativas, feedback ligado al intento, reintentos, tiempo total,
latencia visible, tokens, validez a la primera y evaluacion ciega de coherencia.

### Experimento B: variedad de componentes frente a profundidad

- variante 1: tres o cuatro componentes distintos y superficiales;
- variante 2: una actividad Didact con tres estados y feedback;
- variante 3: actividad rica mas un checkpoint distinto.

La hipotesis es que 2 o 3 superaran a 1 cuando el componente modela realmente el fenomeno. No se
debe asumir: debe medirse por objetivo y tipo de fuente.

### Experimento C: continuidad de mecanica

Comparar tres nodos independientes frente a un tramo que conserva `core_mechanic_id` y aumenta una
sola dificultad por nodo. Medir comprension del modelo, transferencia al caso final y sensacion de
repeticion.

### Experimento D: ayuda adaptativa

Misma actividad y verdad, variando solo `support_policy`: entrada directa, pista inicial o escalera
de pistas. Verificar que la personalizacion cambia la ayuda de forma causal sin alterar criterios de
exito ni hechos de fuente.

## 6. Decision provisional

La siguiente evolucion no deberia ser "una pantalla igual a una idea" como regla literal, ni
"muchos componentes por pantalla". La unidad debe ser una **mision cognitiva con profundidad
variable**. Una pantalla puede contener una actividad rica de varias fases; una leccion puede usar
varias pantallas cuando cambia la accion o se necesita un checkpoint independiente.

La aportacion mas transferible de Brilliant para SkillNet no es su estetica. Es esta combinacion:

```text
mapa visible + progresion intencional + accion antes de teoria
+ mecanica central que escala + feedback en contexto + evaluacion del sistema completo
```

SkillNet puede conservar su ventaja diferencial --generacion personalizada on-the-fly-- si genera
la configuracion y el apoyo de cada beat desde una intencion congelada, en vez de inventar de nuevo
la pedagogia completa en cada render.
