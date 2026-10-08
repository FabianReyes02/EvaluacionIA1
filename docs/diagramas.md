# Diagramas de orquestación y flujos — Repuestos Sur (EP2, IE7/IE9)

> Fuente para el informe de 5 páginas y el README. Renderizan en GitHub
> (bloques `mermaid`). Decisiones asociadas en `agents.md` D6/D9/D10/D12.

## 1. Orquestación general del agente (IE7)

```mermaid
flowchart TD
    U[Usuario: chat web / CLI] --> CTX[Contexto: catalogo CSV + memoria largo plazo + resumen sesion]
    CTX --> LLM[LLM Groq qwen-27b / OpenAI gpt-4o-mini<br/>planifica: elige tool y argumentos]
    LLM --> T{Tool llamada?}
    T -- si --> TJ[buscar_repuesto / buscar_en_manual / verificar_compatibilidad / recordar_dato / recuperar_memoria / exportar_cotizacion]
    TJ --> OBS[Observacion: texto plano de la tool]
    OBS --> LLM
    T -- no --> RESP[Respuesta del modelo]
    RESP --> GR[Guardrails post-LLM<br/>codigos contra CSV + alerta stock < 5]
    GR --> TR[Traza logs/trace.jsonl + memoria corto plazo]
    TR --> U
    TJ -.-> RAG[(ChromaDB: manuales + inventario + memoria)]
    GR -.-> CSV[(inventory.csv)]
```

Lectura: el LLM nunca toca CSV ni Chroma directo; solo decide qué tool
llamar (`agent/agent.py`, `agent/tools.py`). Los guardrails (`agent/guardrails.py`)
re-verifican en código, no solo en prompt (D10). Memoria corto plazo: ventana
10 turnos; largo plazo: JSONL + Chroma semántico (D9).

## 2. Flujo: búsqueda y cotización (IE9, caso feliz)

```mermaid
sequenceDiagram
    participant C as Cliente
    participant A as Agente create_agent
    participant I as buscar_repuesto CSV
    participant M as buscar_en_manual RAG
    participant E as exportar_cotizacion
    C->>A: Suzuki Swift 2015, necesito alternador
    A->>I: buscar_repuesto(Suzuki, Swift, 2015, alternador)
    I-->>A: ALT-01 $289.990 stock 7 + alerta si <5
    A->>M: buscar_en_manual(alternador 12V 90A specs)
    M-->>A: [manual_alternador.pdf p.1] 90A/14V...
    A->>A: guardrails: codigo existe? stock ok?
    A-->>C: recomendado + precio + cita manual + codigo
    C->>A: coticemos ALT-01
    A->>E: exportar_cotizacion([ALT-01])
    E-->>A: data/exports/cotizacion_*.json
    A-->>C: total + ruta archivo
```

Evidencia real: casos C01/C09/C12 en `tests/resultados/eval_reporte.md`.

## 3. Flujo: negativa sin fuente + alerta stock (IE9, regla no negociable)

```mermaid
flowchart TD
    Q[Consulta: Ferrari 488 2020 / codigo XYZ-99 / ALT-02 stock 4] --> B[buscar_repuesto / verificar_compatibilidad]
    B --> H{Hay respaldo en CSV o manual?}
    H -- no --> N[Responder no tengo informacion suficiente + no inventar codigo]
    H -- si --> S{Stock < 5 o agotado?}
    S -- si --> AL[Respuesta + ALERTA STOCK + guardrail agrega alerta si el LLM la omitio]
    S -- no --> OK[Respuesta normal con codigo y precio]
    N --> G[Guardrail: codigo inexistente -> marca no verificado]
    AL --> G
    OK --> G
```

Evidencia real: C05/C06 negativa, C07 alerta, C11 guardrail.

## 4. Memoria y límite de tasa (D9/D12)

```mermaid
flowchart LR
    S1[Sesion web / eval-memoria: recordar_dato vehiculo] --> J[data/memory/memoria.jsonl + coleccion Chroma memoria]
    J --> S2[Sesion nueva eval-memoria-2: recuperar_memoria]
    S2 --> R[Respuesta usa dato recordado sin pedirlo de nuevo]
    LLM429[LLM 429 OTPM 1000 tok/min] --> RT[Retry 3 intentos 20s/40s/60s solo 429<br/>AGENT_RETRY_ATTEMPTS / AGENT_RETRY_BASE_S]
    RT --> FB[Fallback: mensaje saturacion + busqueda directa CSV]
```
