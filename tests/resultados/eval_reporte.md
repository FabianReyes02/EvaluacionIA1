# Evidencia de pruebas — Evaluacion del agente Repuestos Sur

**Fecha:** 2026-10-22T15:12:45  
**Resultado:** 18/18 (100.0%) — meta 85%  
**Proveedor / modelo:** groq / openai/gpt-oss-120b  
**Tokens gastados:** 101404

| Caso | Tipo | Resultado | Herramientas | Guardrails | Tokens | Reintentos | Detalle |
|---|---|---|---|---|---|---|---|
| C01 | busqueda | ✅ | buscar_repuesto | — | 6566 | 0 | cumple |
| C02 | busqueda | ✅ | buscar_repuesto | — | 6636 | 0 | cumple |
| C03 | validacion | ✅ | — | — | 4197 | 0 | cumple |
| C04 | validacion | ✅ | — | — | 3307 | 0 | cumple |
| C05 | negativa | ✅ | — | — | 3360 | 0 | cumple |
| C06 | negativa | ✅ | buscar_repuesto | — | 6593 | 0 | cumple |
| C07 | alerta_stock | ✅ | buscar_repuesto | — | 6586 | 0 | cumple |
| C08 | fuera_de_contexto | ✅ | — | — | 3169 | 0 | cumple |
| C09 | rag_manual | ✅ | buscar_en_manual | — | 6871 | 0 | cumple |
| C10 | compatibilidad | ✅ | verificar_compatibilidad | — | 6550 | 0 | cumple |
| C11 | guardrail | ✅ | — | codigo_inexistente:XYZ-99 | 3463 | 0 | cumple |
| C12 | escritura | ✅ | exportar_cotizacion | — | 7976 | 0 | cumple |
| C13 | memoria_escritura | ✅ | recordar_dato | — | 6398 | 0 | cumple |
| C14 | memoria_lectura | ✅ | recuperar_memoria | — | 6414 | 0 | cumple |
| C15 | conversacional | ✅ | — | — | 3189 | 0 | cumple |
| C16 | escritura_correo | ✅ | enviar_cotizacion_email | — | 6717 | 0 | cumple |
| C17 | venta | ✅ | registrar_venta | — | 6684 | 0 | cumple |
| C18 | recomendacion | ✅ | recomendar_repuesto | — | 6728 | 0 | cumple |

## Detalle por caso

### C01 — Busqueda normal con marca, modelo y anio correctos ✅
- **Entrada:** ['Necesito un alternador para un Suzuki Swift 2015']
- **Por que se evalua:** Debe recuperar el repuesto real del CSV citando su codigo (IE1).
- **Sesion:** `eval-C01` | LLM: True | duración 3.6s | reintentos 429: 0
- **Respuesta:**

```
Para tu Suzuki Swift 2015 encontré los siguientes alternadores:

- **[ALT-01] Alternador 12 V 90 A** - $289 990 - Stock: 7 unidades.  
- **[COR-01] Correa de alternador 1.130 mm** - $15 990 - Stock: 40 unidades.  
```

### C02 — Busqueda filtrada por tipo de repuesto ✅
- **Entrada:** ['¿Cuánto cuesta el filtro de aceite para un Hyundai Accent 2016?']
- **Por que se evalua:** Filtra por tipo de pieza dentro del inventario compatible.
- **Sesion:** `eval-C02` | LLM: True | duración 35.7s | reintentos 429: 0
- **Respuesta:**

```
Lo siento, en nuestro inventario no contamos con un **filtro de aceite** para el Hyundai Accent 2016.  

La coincidencia más cercana que sí está disponible es:

- **[FLT-02] Filtro de aire motor** - $12.990 - Stock: 45 unidades.

Si necesitas otro tipo de filtro o tienes alguna otra consulta, avísame y con gusto te ayudo.
```

### C03 — El cliente no entrega marca, modelo ni anio ✅
- **Entrada:** ['Quiero un repuesto para mi auto']
- **Por que se evalua:** Fase de validacion: pide los datos obligatorios antes de buscar (IE5/IE6).
- **Sesion:** `eval-C03` | LLM: True | duración 0.7s | reintentos 429: 0
- **Respuesta:**

```
¡Claro! Para encontrar el repuesto correcto necesito los datos de tu auto:

- Marca  
- Modelo  
- Año  

¿Me los puedes indicar, por favor?
```

### C04 — Anio fuera de rango ✅
- **Entrada:** ['Repuestos para un Suzuki Swift 1800']
- **Por que se evalua:** Detecta un anio imposible y explica el problema sin inventar.
- **Sesion:** `eval-C04` | LLM: True | duración 1.4s | reintentos 429: 0
- **Respuesta:**

```
¡Claro! Para buscar los repuestos compatibles necesito saber el año de tu Suzuki Swift. ¿Podrías indicármelo, por favor?
```

### C05 — Marca que no existe en el inventario ✅
- **Entrada:** ['Necesito repuestos para un Ferrari 488 2020']
- **Por que se evalua:** Regla no negociable: niega sin inventar repuestos ni codigos.
- **Sesion:** `eval-C05` | LLM: True | duración 1.6s | reintentos 429: 0
- **Respuesta:**

```
No tengo información suficiente: el vehículo **Ferrari 488 2020** no está incluido en nuestro catálogo de repuestos. Si necesita repuestos para alguno de los modelos que manejamos (Suzuki Swift, Kia Rio 4, Hyundai Accent, Chevrolet Sail, Chevrolet Corsa o Chevrolet Spark), por favor indíquelo y con gusto le ayudo.
```

### C06 — Modelo inexistente para una marca valida ✅
- **Entrada:** ['¿Tienen un repuesto para un Suzuki Corolla 2015?']
- **Por que se evalua:** Diagnostica que el problema es el modelo, no la marca.
- **Sesion:** `eval-C06` | LLM: True | duración 21.3s | reintentos 429: 0
- **Respuesta:**

```
No tengo información suficiente: el modelo **Suzuki Corolla 2015** no está registrado en nuestro inventario. Si necesita repuestos para otro modelo de Suzuki (por ejemplo, Swift) o para otra marca, indíquelo y lo busco.
```

### C07 — Repuesto con stock critico (ALT-02, stock 4) ✅
- **Entrada:** ['Necesito un alternador para un Hyundai Accent 2016']
- **Por que se evalua:** Alerta explicita de stock critico, exigida por el encargo (Fase 4).
- **Sesion:** `eval-C07` | LLM: True | duración 11.3s | reintentos 429: 0
- **Respuesta:**

```
Para tu Hyundai Accent 2016 tengo disponible:

- **[ALT-02] Alternador 12 V 110 A** - $329 990 - Stock: **4 unidades** *(STOCK BAJO)*  

¿Te gustaría que te envíe una cotización o proceder con la compra?
```

### C08 — Pregunta ajena al negocio ✅
- **Entrada:** ['¿Cuál es la capital de Francia?']
- **Por que se evalua:** Se mantiene en el rol y redirige al tema (IE5/IE6).
- **Sesion:** `eval-C08` | LLM: True | duración 7.3s | reintentos 429: 0
- **Respuesta:**

```
Lo siento, pero solo puedo ayudar con repuestos automotrices y consultas relacionadas con vehículos. Si tienes alguna pregunta sobre tu auto o necesitas información de repuestos, estaré encantado de asistirte.
```

### C09 — Consulta tecnica que solo esta en el manual PDF ✅
- **Entrada:** ['¿Qué amperaje tiene el alternador de 90A según el manual técnico?']
- **Por que se evalua:** RAG sobre manuales con cita de la fuente (IE1/IE2).
- **Sesion:** `eval-C09` | LLM: True | duración 36.4s | reintentos 429: 0
- **Respuesta:**

```
Según el manual técnico, el alternador de 12 V tiene una **corriente nominal de 90 A**【manual_alternador.pdf - pagina 1】.
```

### C10 — Verificacion de compatibilidad de un codigo puntual ✅
- **Entrada:** ['¿El kit embrague EMP-02 sirve para un Kia Rio 4 2018?']
- **Por que se evalua:** Cruza el repuesto con el vehiculo usando la fuente interna.
- **Sesion:** `eval-C10` | LLM: True | duración 10.6s | reintentos 429: 0
- **Respuesta:**

```
Sí, el kit de embrague **EMP-02** es compatible con tu Kia Rio 4 2018.

[EMP-02] Kit embrague 215 mm - $249 990 - Stock: 9 unidades.
```

### C11 — El cliente pregunta por un codigo inexistente ✅
- **Entrada:** ['¿Tienen el repuesto XYZ-99 en stock?']
- **Por que se evalua:** El guardrail post-LLM marca el codigo que no existe en el CSV.
- **Sesion:** `eval-C11` | LLM: True | duración 11.2s | reintentos 429: 0
- **Respuesta:**

```
No tengo información suficiente para responder. Necesito saber la marca, modelo y año del vehículo para poder verificar si el repuesto **XYZ-99 (no verificado)** está disponible en nuestro inventario.

[Guardrail] No puedo confirmar el repuesto XYZ-99: no existe en el inventario de la tienda.
```

### C12 — El cliente pide cotizar y el sistema escribe un archivo ✅
- **Entrada:** ['Cotiza el alternador ALT-01 y el filtro FLT-01 por favor']
- **Por que se evalua:** Tool de ESCRITURA real: genera data/exports/cotizacion_*.json.
- **Sesion:** `eval-C12` | LLM: True | duración 1.8s | reintentos 429: 0
- **Respuesta:**

```
Cotización generada correctamente. Si deseas que te la envíe por correo, por favor indícame la dirección de email.
```

### C13 — El cliente entrega un dato que debe recordarse ✅
- **Entrada:** ['Guarda en tu memoria que mi auto es un Suzuki Swift 2015']
- **Por que se evalua:** Escritura en memoria de LARGO PLAZO (IE3/IE4).
- **Sesion:** `eval-memoria` | LLM: True | duración 2.4s | reintentos 429: 0
- **Respuesta:**

```
¡Listo! He guardado que tu auto es un **Suzuki Swift 2015**. Si necesitas repuestos o información, solo avísame.
```

### C14 — En una SESION NUEVA pide un dato guardado en la anterior ✅
- **Entrada:** ['¿Sabes qué vehículo tengo?']
- **Por que se evalua:** Recuperacion de contexto entre sesiones: memoria persistente (IE3/IE4).
- **Sesion:** `eval-memoria-2` | LLM: True | duración 15.2s | reintentos 429: 0
- **Respuesta:**

```
Sí, recuerdo que tu vehículo es un **Suzuki Swift 2015**.
```

### C15 — Saludo social sin intencion de compra ✅
- **Entrada:** ['Hola, ¿cómo estás?']
- **Por que se evalua:** Respuesta cortes sin llamar herramientas ni inventar datos.
- **Sesion:** `eval-C15` | LLM: True | duración 0.9s | reintentos 429: 0
- **Respuesta:**

```
¡Hola! Muy bien, gracias. ¿En qué puedo ayudarte con los repuestos para tu vehículo?
```

### C16 — El cliente pide cotizar y enviar la cotizacion por correo ✅
- **Entrada:** ['Cotiza el alternador ALT-01 y envíamela por correo a juan.perez@ejemplo.com']
- **Por que se evalua:** Tool de ENVIO: arma el correo con los precios del inventario y lo manda por SMTP real (modo por defecto); deja la cotización en data/exports/ y el envío registrado en envios.jsonl. Sin credenciales SMTP el correo queda preparado en un .eml y la tool lo dice.
- **Sesion:** `eval-C16` | LLM: True | duración 2.3s | reintentos 429: 0
- **Respuesta:**

```
Cotización preparada, **no se envió**: la cotización con el código **ALT-01** quedó guardada en  
`C:\Users\matia\OneDrive\Escritorio\Agente\EvaluacionIA1\data\exports\cotizacion_20261022_151202.eml` (modo dry-run). Contiene 1 ítem por **$289.990**.  

Quedo a disposición para enviarla cuando lo desee.
```

### C17 — El cliente confirma la compra: se registra la venta y baja el stock ✅
- **Entrada:** ['Confirmo la compra del ALT-02, llévalo']
- **Por que se evalua:** Tool de ESCRITURA en la base de datos interna: la venta descuenta el stock real (ALT-02 pasa de 4 a 3) y devuelve la referencia de la venta. El evaluador comprueba el stock antes y despues en la BD.
- **Sesion:** `eval-C17` | LLM: True | duración 9.8s | reintentos 429: 0
- **Respuesta:**

```
¡Listo! La compra quedó registrada:

- **Referencia:** V-0001  
- **Código:** ALT-02  
- **Total:** $329.990  

El stock del artículo pasó a **3 unidades** (STOCK BAJO, quedan menos de 5).  

¡Gracias por tu compra! 🚗💨
```

### C18 — El cliente pide una recomendacion: la tool cruza inventario, compatibilidad y manual ✅
- **Entrada:** ['¿Qué repuesto me recomiendas para un Suzuki Swift 2015?']
- **Por que se evalua:** Tool de RECOMENDACION: pipeline completo del encargo (RAG interno + RAG externo + compatibilidad) con el codigo del repuesto y la cita de la fuente (IE1/IE2/IE4).
- **Sesion:** `eval-C18` | LLM: True | duración 2.8s | reintentos 429: 0
- **Respuesta:**

```
Para tu Suzuki Swift 2015 te recomiendo el siguiente repuesto:

[ALT-01] Alternador 12 V 90 A - $289.990 - Stock: 7 unidades.

Es compatible con tu modelo (verificado en el manual técnico).  

¿Te gustaría que te envíe una cotización o deseas más información sobre este alternador?
```
