#!/usr/bin/env python3
"""P1 (bateria defensa): higiene de repo, patrones peligrosos y secretos.

No levanta servidor ni gasta tokens de LLM. Ejecutar desde la raiz:
    python scripts/security_checks.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Archivos/carpetas que NO deben estar trackeados por git (excepto ejemplos permitidos).
TRACKED_FORBIDDEN = [
    (re.compile(r"^\.env$"), "archivo de secretos .env"),
    (re.compile(r"^chroma_db/"), "directorio ChromaDB (artefacto)"),
    (re.compile(r"^logs/"), "logs locales"),
    (re.compile(r"^data/memory/.*\.jsonl$"), "memorias JSONL runtime"),
    (re.compile(r"^data/exports/.*"), "salidas/exports runtime"),
    (re.compile(r"^data/internal/tienda.*\.db.*$"), "BD SQLite runtime"),
    (re.compile(r"^data/internal/.*_eval\.csv$"), "CSV de eval aislado"),
]

# Busqueda solo en estos directorios versionados (evitar .venv, caches).
SCAN_DIRS = ["agent", "tools", "web", "scripts", "tests", "ingestion"]

# Patrones sospechosos en codigo (heurstica; revisar falsos positivos).
DANGEROUS_PATTERNS = [
    (re.compile(r"\beval\s*\("), "eval("),
    (re.compile(r"\bexec\s*\("), "exec("),
    (re.compile(r"__import__\s*\("), "__import__("),
    (re.compile(r"\bsubprocess\."), "subprocess."),
    (re.compile(r"os\.system\s*\("), "os.system("),
    (re.compile(r"shell\s*=\s*True"), "shell=True"),
]

# Cadenas de secreto que no deben aparecer en archivos trackeados (salvo .env.example/docs permitidos).
SECRET_HITS_ALLOWLIST_PATHS = {".env.example", "docs/CHECKLIST_ENTREGA.md", "README.md"}
SECRET_REGEX = re.compile(
    r"(GROQ_API_KEY\s*=\s*[\"']?gsk_|OPENAI_API_KEY\s*=\s*[\"']?sk-|SMTP_PASSWORD\s*=\s*[\"']?[^\"'\s]+)",
    re.IGNORECASE,
)


def git_tracked_files() -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "ls-files"], cwd=ROOT, text=True, encoding="utf-8", errors="replace"
        )
        return [line.strip() for line in out.splitlines() if line.strip()]
    except Exception as exc:
        print(f"[WARN] No se pudo ejecutar git ls-files: {exc}", file=sys.stderr)
        return []


def check_tracked_forbidden(tracked: list[str]) -> list[dict]:
    findings: list[dict] = []
    for path in tracked:
        for pat, desc in TRACKED_FORBIDDEN:
            if pat.search(path):
                findings.append({"path": path, "rule": desc})
                break
    return findings


def iter_python_like_files() -> list[Path]:
    files: list[Path] = []
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".py", ".js", ".html", ".ts"}:
                files.append(p)
    return files


def check_dangerous_patterns() -> list[dict]:
    findings: list[dict] = []
    for p in iter_python_like_files():
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines, start=1):
            if "security_checks.py" in str(p):
                continue
            for pat, label in DANGEROUS_PATTERNS:
                if pat.search(line):
                    findings.append(
                        {
                            "path": str(p.relative_to(ROOT)),
                            "line": i,
                            "pattern": label,
                            "snippet": line.strip()[:200],
                        }
                    )
    return findings


def check_secrets(tracked: list[str]) -> list[dict]:
    findings: list[dict] = []
    for rel in tracked:
        if rel in SECRET_HITS_ALLOWLIST_PATHS or rel.endswith(".example"):
            continue
        if not (rel.endswith(".py") or rel.endswith(".md") or rel.endswith(".json") or rel.endswith(".txt") or rel.endswith(".env")):
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if SECRET_REGEX.search(text):
            findings.append({"path": rel, "note": "posible secreto hardcodeado (revisar manualmente)"})
    return findings


def main() -> int:
    out_dir = ROOT / "tests" / "resultados" / "security"
    out_dir.mkdir(parents=True, exist_ok=True)

    tracked = git_tracked_files()
    forbidden = check_tracked_forbidden(tracked)
    dangerous = check_dangerous_patterns()
    secrets = check_secrets(tracked)

    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "tracked_files_count": len(tracked),
        "tracked_forbidden": forbidden,
        "dangerous_patterns": dangerous,
        "secret_scan_hits": secrets,
        "summary": {
            "tracked_forbidden_ok": len(forbidden) == 0,
            "dangerous_patterns_ok": len(dangerous) == 0,
            "secret_scan_ok": len(secrets) == 0,
        },
    }

    (out_dir / "p1_security_checks.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines: list[str] = [
        "# P1 — security_checks (generado)",
        f"Fecha: {report['timestamp']}",
        "",
        "## 1.1 Archivos trackeados que NO deberian estar (esperado: ninguno)",
    ]
    if forbidden:
        for f in forbidden:
            lines.append(f"- FAIL: `{f['path']}` ({f['rule']})")
    else:
        lines.append("- OK: ninguno detectado")
    lines += ["", "## 1.2 Patrones peligrosos (heuristica)", ""]
    if dangerous:
        for f in dangerous[:120]:
            lines.append(f"- `{f['path']}:{f['line']}` [{f['pattern']}] `{f['snippet']}`")
        if len(dangerous) > 120:
            lines.append(f"- ... y {len(dangerous) - 120} mas")
    else:
        lines.append("- OK: ninguno detectado en rutas escaneadas")
    lines += ["", "## 1.3 Posibles secretos en archivos trackeados", ""]
    if secrets:
        for f in secrets:
            lines.append(f"- REVISAR: `{f['path']}` — {f['note']}")
    else:
        lines.append("- OK: sin coincidencias heuristicas (aun asi revisar .env local)")

    (out_dir / "p1_security_checks.md").write_text("\n".join(lines), encoding="utf-8")

    print("P1 escrito en:", out_dir / "p1_security_checks.md")
    print("JSON:", out_dir / "p1_security_checks.json")
    ok = report["summary"]["tracked_forbidden_ok"] and report["summary"]["dangerous_patterns_ok"]
    # secretos: solo advertencia por defecto
    if report["summary"]["secret_scan_hits"] if False else secrets:
        print("[WARN] Revisa hits de secretos en el reporte.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
