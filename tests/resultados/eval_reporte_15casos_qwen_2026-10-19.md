# Evidencia de pruebas — Evaluacion del agente Repuestos Sur

**Fecha:** 2026-10-19T17:49:59  
**Resultado:** 15/15 (100.0%) — meta 85%  
**Tokens gastados:** 47012

| Caso | Tipo | Resultado | Herramientas | Guardrails | Tokens | Reintentos | Detalle |
|---|---|---|---|---|---|---|---|
| C01 | busqueda | ✅ | buscar_repuesto | — | 4337 | 0 | cumple |
| C02 | busqueda | ✅ | buscar_repuesto | — | 4304 | 0 | cumple |
| C03 | validacion | ✅ | — | — | 2053 | 0 | cumple |
| C04 | validacion | ✅ | — | — | 2040 | 0 | cumple |
| C05 | negativa | ✅ | — | — | 2132 | 0 | cumple |
| C06 | negativa | ✅ | — | — | 2064 | 0 | cumple |
| C07 | alerta_stock | ✅ | buscar_repuesto | — | 4367 | 0 | cumple |
| C08 | fuera_de_contexto | ✅ | — | — | 2053 | 0 | cumple |
| C09 | rag_manual | ✅ | buscar_en_manual | — | 4758 | 0 | cumple |
| C10 | compatibilidad | ✅ | verificar_compatibilidad | — | 4309 | 0 | cumple |
| C11 | guardrail | ✅ | — | codigo_inexistente:XYZ-99 | 2072 | 0 | cumple |
| C12 | escritura | ✅ | exportar_cotizacion | — | 4256 | 0 | cumple |
| C13 | memoria_escritura | ✅ | recordar_dato | — | 4182 | 0 | cumple |
| C14 | memoria_lectura | ✅ | — | — | 2049 | 0 | cumple |
| C15 | conversacional | ✅ | — | — | 2036 | 0 | cumple |

## Detalle por caso

### C01 — Busqueda normal con marca, modelo y anio correctos ✅
- **Entrada:** ['Necesito un alternador para un Suzuki Swift 2015']
- **Por que se evalua:** Debe recuperar el repuesto real del CSV citando su codigo (IE1).
- **Sesion:** `eval-C01` | LLM: True | duración 1.6s | reintentos 429: 0
- **Respuesta:**

```
Para tu Suzuki Swift 2015 encontré:

[ALT-01] Alternador 12V 90A - $289.990 - Stock: 7 unidades.

También tengo la correa del alternador por si la necesitas:
[COR-01] Correa alternador 1.130mm - $15.990 - Stock: 40 unidades.

¿Quieres que te cotice alguno o necesitas más detalles técnicos?
```

### C02 — Busqueda filtrada por tipo de repuesto ✅
- **Entrada:** ['¿Cuánto cuesta el filtro de aceite para un Hyundai Accent 2016?']
- **Por que se evalua:** Filtra por tipo de pieza dentro del inventario compatible.
- **Sesion:** `eval-C02` | LLM: True | duración 1.7s | reintentos 429: 0
- **Respuesta:**

```
Para tu Hyundai Accent 2016 encontré 1 repuesto:

[FLT-02] Filtro de aire motor - $12.990 - Stock: 45 unidades.

Ojo: el inventario trae un filtro de aire, no de aceite. No tengo registro de un filtro de aceite para ese vehículo, así que no puedo darte precio ni stock de ese. ¿Quieres que busque otro tipo de repuesto o que revise el manual técnico?
```

### C03 — El cliente no entrega marca, modelo ni anio ✅
- **Entrada:** ['Quiero un repuesto para mi auto']
- **Por que se evalua:** Fase de validacion: pide los datos obligatorios antes de buscar (IE5/IE6).
- **Sesion:** `eval-C03` | LLM: True | duración 0.6s | reintentos 429: 0
- **Respuesta:**

```
¡Hola! Con gusto te ayudo. Para buscar el repuesto correcto necesito saber:

- Marca, modelo y año de tu auto
- Qué repuesto necesitas (por ejemplo: alternador, pastillas de freno, filtro, kit de embrague, etc.)

¿Me los pasas?
```

### C04 — Anio fuera de rango ✅
- **Entrada:** ['Repuestos para un Suzuki Swift 1800']
- **Por que se evalua:** Detecta un anio imposible y explica el problema sin inventar.
- **Sesion:** `eval-C04` | LLM: True | duración 0.6s | reintentos 429: 0
- **Respuesta:**

```
¡Hola! Para buscar repuestos para tu Suzuki Swift necesito el **año** del vehículo (el catálogo cubre desde 2014 a 2019).

¿De qué año es tu Swift?
```

### C05 — Marca que no existe en el inventario ✅
- **Entrada:** ['Necesito repuestos para un Ferrari 488 2020']
- **Por que se evalua:** Regla no negociable: niega sin inventar repuestos ni codigos.
- **Sesion:** `eval-C05` | LLM: True | duración 0.7s | reintentos 429: 0
- **Respuesta:**

```
No cuento con repuestos para Ferrari 488 2020. Nuestro inventario cubre solo estos vehículos:

- Suzuki Swift 2014-2019
- Kia Rio 4 2017-2021
- Hyundai Accent 2012-2019
- Chevrolet Sail 2013-2019
- Chevrolet Corsa 2005-2011
- Chevrolet Spark 2011-2019

¿Tienes alguno de estos modelos? Con gusto te busco el repuesto que necesites.
```

### C06 — Modelo inexistente para una marca valida ✅
- **Entrada:** ['¿Tienen un repuesto para un Suzuki Corolla 2015?']
- **Por que se evalua:** Diagnostica que el problema es el modelo, no la marca.
- **Sesion:** `eval-C06` | LLM: True | duración 0.6s | reintentos 429: 0
- **Respuesta:**

```
No tengo un "Suzuki Corolla" en mi catálogo. El Corolla es de Toyota, no de Suzuki, y no cuento con repuestos para Toyota en inventario.

¿Podrías confirmarme la marca, modelo y año exactos de tu vehículo? Así puedo buscar el repuesto que necesitas.
```

### C07 — Repuesto con stock critico (ALT-02, stock 4) ✅
- **Entrada:** ['Necesito un alternador para un Hyundai Accent 2016']
- **Por que se evalua:** Alerta explicita de stock critico, exigida por el encargo (Fase 4).
- **Sesion:** `eval-C07` | LLM: True | duración 21.1s | reintentos 429: 0
- **Respuesta:**

```
Para tu Hyundai Accent 2016 encontré:

[ALT-02] Alternador 12V 110A - $329.990 - Stock: 4 unidades (STOCK BAJO, quedan menos de 5).

También está disponible la correa del alternador por si la necesitas:
[COR-01] Correa alternador 1.130mm - $15.990 - Stock: 40 unidades.

¿Quieres que te cotice alguno o ambos?
```

### C08 — Pregunta ajena al negocio ✅
- **Entrada:** ['¿Cuál es la capital de Francia?']
- **Por que se evalua:** Se mantiene en el rol y redirige al tema (IE5/IE6).
- **Sesion:** `eval-C08` | LLM: True | duración 2.1s | reintentos 429: 0
- **Respuesta:**

```
¡Hola! Solo puedo ayudarte con repuestos y vehículos. Para tu consulta sobre la capital de Francia, te sugiero consultar una enciclopedia.

¿En qué puedo ayudarte con los repuestos de tu auto? Si me dices marca, modelo y año, puedo buscar el repuesto que necesites.
```

### C09 — Consulta tecnica que solo esta en el manual PDF ✅
- **Entrada:** ['¿Qué amperaje tiene el alternador de 90A según el manual técnico?']
- **Por que se evalua:** RAG sobre manuales con cita de la fuente (IE1/IE2).
- **Sesion:** `eval-C09` | LLM: True | duración 24.2s | reintentos 429: 0
- **Respuesta:**

```
Según el manual técnico (manual_alternador.pdf, pág. 1), el alternador de 90A tiene estas especificaciones:

- Corriente nominal: 90A
- Voltaje nominal: 14V
- Poles: 12
- Polea compatible: correas de 5 y 6 canales según motor
- Conexión de 3 cables: B+ (salida principal), D+ (luz de carga) y W (tacómetro)

Es apto para motores de 1000 a 1500 cc. ¿Quieres que te busque el precio y stock para algún vehículo en particular?
```

### C10 — Verificacion de compatibilidad de un codigo puntual ✅
- **Entrada:** ['¿El kit embrague EMP-02 sirve para un Kia Rio 4 2018?']
- **Por que se evalua:** Cruza el repuesto con el vehiculo usando la fuente interna.
- **Sesion:** `eval-C10` | LLM: True | duración 19.8s | reintentos 429: 0
- **Respuesta:**

```
Sí, el [EMP-02] Kit embrague 215mm es compatible con tu Kia Rio 4 2018.

Detalles:
- Precio: $249.990
- Stock: 9 unidades
- Compatibilidad registrada: Hyundai Accent 2012-2019 y Kia Rio 4 2017-2021

¿Quieres que lo cotice o que revise algo más?
```

### C11 — El cliente pregunta por un codigo inexistente ✅
- **Entrada:** ['¿Tienen el repuesto XYZ-99 en stock?']
- **Por que se evalua:** El guardrail post-LLM marca el codigo que no existe en el CSV.
- **Sesion:** `eval-C11` | LLM: True | duración 2.9s | reintentos 429: 0
- **Respuesta:**

```
No tengo información sobre un repuesto con código XYZ-99 (no verificado) en nuestro inventario. Para ayudarte, necesito que me indiques la marca, modelo y año de tu vehículo, y el tipo de repuesto que buscas (por ejemplo, alternador, pastillas de freno, filtro, etc.). Con esos datos puedo buscar en el inventario y confirmarte disponibilidad y precio.

[Guardrail] No puedo confirmar el repuesto XYZ-99: no existe en el inventario de la tienda.
```

### C12 — El cliente pide cotizar y el sistema escribe un archivo ✅
- **Entrada:** ['Cotiza el alternador ALT-01 y el filtro FLT-01 por favor']
- **Por que se evalua:** Tool de ESCRITURA real: genera data/exports/cotizacion_*.json.
- **Sesion:** `eval-C12` | LLM: True | duración 20.1s | reintentos 429: 0
- **Respuesta:**

```
Listo, cotización guardada con 2 ítems por un total de $297.980.

Detalle:
- [ALT-01] Alternador
- [FLT-01] Filtro

El archivo quedó en data/exports/cotizacion_20261019_174832.json. ¿Quieres que verifique compatibilidad con algún vehículo o que agregue más repuestos?
```

### C13 — El cliente entrega un dato que debe recordarse ✅
- **Entrada:** ['Guarda en tu memoria que mi auto es un Suzuki Swift 2015']
- **Por que se evalua:** Escritura en memoria de LARGO PLAZO (IE3/IE4).
- **Sesion:** `eval-memoria` | LLM: True | duración 19.7s | reintentos 429: 0
- **Respuesta:**

```
Listo, guardé que tu auto es un Suzuki Swift 2015. ¿En qué más te ayudo?
```

### C14 — En una SESION NUEVA pide un dato guardado en la anterior ✅
- **Entrada:** ['¿Sabes qué vehículo tengo?']
- **Por que se evalua:** Recuperacion de contexto entre sesiones: memoria persistente (IE3/IE4).
- **Sesion:** `eval-memoria-2` | LLM: True | duración 2.7s | reintentos 429: 0
- **Respuesta:**

```
Sí, según lo que tengo guardado, tu vehículo es un **Suzuki Swift 2015**. ¿En qué puedo ayudarte con él?
```

### C15 — Saludo social sin intencion de compra ✅
- **Entrada:** ['Hola, ¿cómo estás?']
- **Por que se evalua:** Respuesta cortes sin llamar herramientas ni inventar datos.
- **Sesion:** `eval-C15` | LLM: True | duración 1.6s | reintentos 429: 0
- **Respuesta:**

```
¡Hola! Estoy muy bien, gracias. ¿En qué puedo ayudarte hoy con los repuestos?
```
