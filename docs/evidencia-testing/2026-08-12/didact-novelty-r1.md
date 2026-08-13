# Colapso de ranking y novedad útil acotada — R1

Se añadió un detector de colapso del primer candidato y una política **solo
experimental**, no conectada al runtime. Considera colapso que un mismo componente ocupe
la primera posición en al menos el 70 % de cinco o más decisiones.

La novedad no es una nueva puntuación capaz de vencer la calidad. Solo desempata un grupo
que ya coincide exactamente en ranking, presentación preferida, productor, affordances y
evidencia. Misión, requisitos, accesibilidad y preferencia ya fueron gates anteriores. Si
un candidato ofrece evidencia distinta o tiene peor ranking, la novedad no puede moverlo
por delante.

La tanda offline de 24 escenarios sobre los 34 tipos obtuvo:

| Estrategia | primeros componentes únicos | cuota dominante | colapso |
|---|---:|---:|---:|
| ranking actual, ventana top-5 | 8 | 29,17 % | no |
| novedad acotada, mismo universo | 9 | 29,17 % | no |

La mejora es pequeña y deliberadamente conservadora. Los 24 escenarios preservaron
exactamente el conjunto elegible. Esto no justifica activar la política todavía; muestra
que se puede añadir variedad sin convertirla en aleatoriedad ni saltarse requisitos.

El banco contrafactual live encontró además un caso más preocupante que el agregado
sintético: en el fixture `extintor`, el mismo primer candidato apareció en 6/6 renders,
por lo que marca colapso del 100 %. Tras eliminar perfil/proyección de la firma causal, las
experiencias observables fueron idénticas y la adaptación correcta pasó de un falso 100 %
a **0 %**. El resultado fixture no evalúa un modelo, pero sí prueba que el detector ya no
premia entradas diferentes cuando la salida es la misma.

