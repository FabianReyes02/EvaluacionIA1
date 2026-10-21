# Evidencia de pruebas — Evaluacion del agente Repuestos Sur

**Fecha:** 2026-10-21T19:06:13  
**Resultado:** 16/16 (100.0%) — meta 85%  
**Proveedor / modelo:** groq / openai/gpt-oss-120b  
**Tokens gastados:** 67045

| Caso | Tipo | Resultado | Herramientas | Guardrails | Tokens | Reintentos | Detalle |
|---|---|---|---|---|---|---|---|
| C01 | busqueda | ✅ | buscar_repuesto | — | 4869 | 0 | cumple |
| C02 | busqueda | ✅ | buscar_repuesto | — | 4960 | 0 | cumple |
| C03 | validacion | ✅ | — | — | 2354 | 0 | cumple |
| C04 | validacion | ✅ | — | — | 2413 | 0 | cumple |
| C05 | negativa | ✅ | buscar_repuesto | — | 5039 | 0 | cumple |
| C06 | negativa | ✅ | buscar_repuesto | — | 5148 | 0 | cumple |
| C07 | alerta_stock | ✅ | buscar_repuesto | — | 4942 | 0 | cumple |
| C08 | fuera_de_contexto | ✅ | — | — | 2353 | 0 | cumple |
| C09 | rag_manual | ✅ | buscar_en_manual | — | 5230 | 0 | cumple |
| C10 | compatibilidad | ✅ | verificar_compatibilidad | — | 4875 | 0 | cumple |
| C11 | guardrail | ✅ | — | codigo_inexistente:XYZ-99 | 2749 | 0 | cumple |
| C12 | escritura | ✅ | exportar_cotizacion | — | 5085 | 0 | cumple |
| C13 | memoria_escritura | ✅ | recordar_dato | — | 4787 | 0 | cumple |
| C14 | memoria_lectura | ✅ | recuperar_memoria | — | 4835 | 0 | cumple |
| C15 | conversacional | ✅ | — | — | 2384 | 0 | cumple |
| C16 | escritura_correo | ✅ | enviar_cotizacion_email | — | 5022 | 0 | cumple |

## Detalle por caso

### C01 — Busqueda normal con marca, modelo y anio correctos ✅
- **Entrada:** ['Necesito un alternador para un Suzuki Swift 2015']
- **Por que se evalua:** Debe recuperar el repuesto real del CSV citando su codigo (IE1).
- **Sesion:** `eval-C01` | LLM: True | duración 2.0s | reintentos 429: 0
- **Respuesta:**

```
Para tu Suzuki Swift 2015 encontré el alternador disponible:

[ALT-01] Alternador 12 V 90 A - $289 990 - Stock: 7 unidades.
```

### C02 — Busqueda filtrada por tipo de repuesto ✅
- **Entrada:** ['¿Cuánto cuesta el filtro de aceite para un Hyundai Accent 2016?']
- **Por que se evalua:** Filtra por tipo de pieza dentro del inventario compatible.
- **Sesion:** `eval-C02` | LLM: True | duración 1.8s | reintentos 429: 0
- **Respuesta:**

```
No tengo disponible un **filtro de aceite** para el Hyundai Accent 2016. La coincidencia más cercana que sí está en nuestro inventario es:

[FLT-02] Filtro de aire motor - $12 990 - Stock: 45 unidades.
```

### C03 — El cliente no entrega marca, modelo ni anio ✅
- **Entrada:** ['Quiero un repuesto para mi auto']
- **Por que se evalua:** Fase de validacion: pide los datos obligatorios antes de buscar (IE5/IE6).
- **Sesion:** `eval-C03` | LLM: True | duración 0.6s | reintentos 429: 0
- **Respuesta:**

```
¡Claro! Para poder buscar el repuesto correcto, necesito los datos de tu vehículo:

- Marca  
- Modelo  
- Año  

¿Me los puedes indicar, por favor?
```

### C04 — Anio fuera de rango ✅
- **Entrada:** ['Repuestos para un Suzuki Swift 1800']
- **Por que se evalua:** Detecta un anio imposible y explica el problema sin inventar.
- **Sesion:** `eval-C04` | LLM: True | duración 0.8s | reintentos 429: 0
- **Respuesta:**

```
¡Claro! Para buscar los repuestos correctos necesito saber el año de tu Suzuki Swift. ¿Podrías indicarme el modelo (por ejemplo, 2015, 2017, etc.)?
```

### C05 — Marca que no existe en el inventario ✅
- **Entrada:** ['Necesito repuestos para un Ferrari 488 2020']
- **Por que se evalua:** Regla no negociable: niega sin inventar repuestos ni codigos.
- **Sesion:** `eval-C05` | LLM: True | duración 1.9s | reintentos 429: 0
- **Respuesta:**

```
Lo siento, pero en nuestro inventario solo contamos con repuestos para las siguientes marcas y modelos:

- Suzuki Swift (2014-2019)  
- Kia Rio 4 (2017-2021)  
- Hyundai Accent (2012-2019)  
- Chevrolet Sail (2013-2019)  
- Chevrolet Corsa (2005-2011)  
- Chevrolet Spark (2011-2019)

No disponemos de repuestos para un Ferrari 488 2020. Si necesitas ayuda con alguno de los vehículos listados, por favor indícame la marca, modelo y año.
```

### C06 — Modelo inexistente para una marca valida ✅
- **Entrada:** ['¿Tienen un repuesto para un Suzuki Corolla 2015?']
- **Por que se evalua:** Diagnostica que el problema es el modelo, no la marca.
- **Sesion:** `eval-C06` | LLM: True | duración 4.1s | reintentos 429: 0
- **Respuesta:**

```
No tengo información suficiente para el modelo **Suzuki Corolla 2015**; en nuestro inventario la marca Suzuki solo cuenta repuestos para el modelo **Swift**. Si necesita repuestos para un Suzuki Swift, indíquelo y con gusto le busco las opciones.
```

### C07 — Repuesto con stock critico (ALT-02, stock 4) ✅
- **Entrada:** ['Necesito un alternador para un Hyundai Accent 2016']
- **Por que se evalua:** Alerta explicita de stock critico, exigida por el encargo (Fase 4).
- **Sesion:** `eval-C07` | LLM: True | duración 14.5s | reintentos 429: 0
- **Respuesta:**

```
Para tu Hyundai Accent 2016 encontré el siguiente alternador:

[ALT-02] Alternador 12V 110A - $329 990 - Stock: 4 unidades (STOCK BAJO).

¿Te gustaría que lo cotice o necesitas más información?
```

### C08 — Pregunta ajena al negocio ✅
- **Entrada:** ['¿Cuál es la capital de Francia?']
- **Por que se evalua:** Se mantiene en el rol y redirige al tema (IE5/IE6).
- **Sesion:** `eval-C08` | LLM: True | duración 0.8s | reintentos 429: 0
- **Respuesta:**

```
Lo siento, solo puedo ayudar con repuestos automotrices y consultas relacionadas con vehículos. Si tienes alguna duda sobre tu auto o necesitas información de repuestos, estaré encantado de asistirte.
```

### C09 — Consulta tecnica que solo esta en el manual PDF ✅
- **Entrada:** ['¿Qué amperaje tiene el alternador de 90A según el manual técnico?']
- **Por que se evalua:** RAG sobre manuales con cita de la fuente (IE1/IE2).
- **Sesion:** `eval-C09` | LLM: True | duración 16.8s | reintentos 429: 0
- **Respuesta:**

```
Según el manual técnico, el alternador de 12 V tiene una **corriente nominal de 90 A**【manual_alternador.pdf - página 1】.
```

### C10 — Verificacion de compatibilidad de un codigo puntual ✅
- **Entrada:** ['¿El kit embrague EMP-02 sirve para un Kia Rio 4 2018?']
- **Por que se evalua:** Cruza el repuesto con el vehiculo usando la fuente interna.
- **Sesion:** `eval-C10` | LLM: True | duración 3.5s | reintentos 429: 0
- **Respuesta:**

```
Sí, el kit de embrague **EMP-02** es compatible con tu Kia Rio 4 2018.

[EMP-02] Kit embrague 215 mm - $249 990 - Stock: 9 unidades.
```

### C11 — El cliente pregunta por un codigo inexistente ✅
- **Entrada:** ['¿Tienen el repuesto XYZ-99 en stock?']
- **Por que se evalua:** El guardrail post-LLM marca el codigo que no existe en el CSV.
- **Sesion:** `eval-C11` | LLM: True | duración 11.0s | reintentos 429: 0
- **Respuesta:**

```
No tengo información suficiente para responder. Necesito saber el vehículo (marca, modelo y año) al que corresponde el repuesto XYZ-99 (no verificado) para poder buscarlo en nuestro inventario.

[Guardrail] No puedo confirmar el repuesto XYZ-99: no existe en el inventario de la tienda.
```

### C12 — El cliente pide cotizar y el sistema escribe un archivo ✅
- **Entrada:** ['Cotiza el alternador ALT-01 y el filtro FLT-01 por favor']
- **Por que se evalua:** Tool de ESCRITURA real: genera data/exports/cotizacion_*.json.
- **Sesion:** `eval-C12` | LLM: True | duración 17.3s | reintentos 429: 0
- **Respuesta:**

```
Cotización realizada para los códigos ALT-01 y FLT-01.  
Total: $297.980.  

La cotización quedó guardada en el archivo `cotizacion_20261021_190837.json`.  

Si deseas que te la envíe por correo, indícame la dirección de email.
```

### C13 — El cliente entrega un dato que debe recordarse ✅
- **Entrada:** ['Guarda en tu memoria que mi auto es un Suzuki Swift 2015']
- **Por que se evalua:** Escritura en memoria de LARGO PLAZO (IE3/IE4).
- **Sesion:** `eval-memoria` | LLM: True | duración 1.3s | reintentos 429: 0
- **Respuesta:**

```
¡Listo! He guardado que tu auto es un **Suzuki Swift 2015**. Si necesitas repuestos o información, solo avísame.
```

### C14 — En una SESION NUEVA pide un dato guardado en la anterior ✅
- **Entrada:** ['¿Sabes qué vehículo tengo?']
- **Por que se evalua:** Recuperacion de contexto entre sesiones: memoria persistente (IE3/IE4).
- **Sesion:** `eval-memoria-2` | LLM: True | duración 1.5s | reintentos 429: 0
- **Respuesta:**

```
Sí, recuerdo que tu vehículo es un **Suzuki Swift 2015**. ¿En qué puedo ayudarte con los repuestos para ese modelo?
```

### C15 — Saludo social sin intencion de compra ✅
- **Entrada:** ['Hola, ¿cómo estás?']
- **Por que se evalua:** Respuesta cortes sin llamar herramientas ni inventar datos.
- **Sesion:** `eval-C15` | LLM: True | duración 0.7s | reintentos 429: 0
- **Respuesta:**

```
¡Hola! Muy bien, gracias. ¿En qué puedo ayudarte con los repuestos para tu vehículo?
```

### C16 — El cliente pide cotizar y enviar la cotizacion por correo ✅
- **Entrada:** ['Cotiza el alternador ALT-01 y envíamela por correo a juan.perez@ejemplo.com']
- **Por que se evalua:** Tool de ENVIO: arma el correo con los precios del CSV y deja la cotización en data/exports/ (modo dry-run por defecto: no sale a internet).
- **Sesion:** `eval-C16` | LLM: True | duración 15.5s | reintentos 429: 0
- **Respuesta:**

```
Cotización preparada, no se envió. El archivo cotizacion_20261021_190942.eml está listo con el alternador ALT-01 (precio $289.990). Si deseas que la enviemos, indícame la dirección de correo a la que debe enviarse.
```
