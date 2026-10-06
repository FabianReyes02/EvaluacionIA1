"""Agente: orquestacion LLM con LangChain, prompts, busqueda RAG y trazabilidad.

Modulos:
    llm_client.py  cliente LLM intercambiable (Groq/OpenAI)
    prompts.py     system prompt y prompts puntuales de la CLI
    rag.py         ingesta PDF/CSV -> embeddings -> ChromaDB (Fase 1)
    tools.py       herramientas de consulta, escritura y memoria
    memory.py      memoria de corto y largo plazo
    guardrails.py  verificacion post-LLM (codigos y stock)
    trace.py       log JSONL de decisiones
    agent.py       orquestador: plan -> tool -> observacion -> respuesta
"""
