"""Genera datos de ejemplo: inventario interno (CSV) y manuales externos (PDF)."""
import csv
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fpdf import FPDF
from fpdf.enums import XPos, YPos

CROP = 8  # mm de margen para diseno sin cortes

REPUESTOS = [
    ("ALT-01", "Alternador 12V 90A", "Bosch", "Sistema electrico", "Suzuki Swift 2014-2019; Kia Rio 4 2017-2021", 289990, 7),
    ("ALT-02", "Alternador 12V 110A", "Bosch", "Sistema electrico", "Hyundai Accent 2012-2019", 329990, 4),
    ("ALT-03", "Alternador 12V 70A", "Denso", "Sistema electrico", "Chevrolet Sail 2013-2019; Chevrolet Corsa 2005-2011", 169990, 12),
    ("BAT-01", "Bateria 660CCA 12V", "Moura", "Sistema electrico", "Varios (ver manual)", 119990, 25),
    ("COR-01", "Correa alternador 1.130mm", "Gates", "Sistema electrico", "Suzuki Swift 2014-2019; Hyundai Accent 2012-2019", 15990, 40),
    ("EMP-01", "Kit embrague 200mm", "Valeo", "Transmision", "Chevrolet Spark 2011-2019", 219990, 6),
    ("EMP-02", "Kit embrague 215mm", "Valeo", "Transmision", "Hyundai Accent 2012-2019; Kia Rio 4 2017-2021", 249990, 9),
    ("EMP-05", "Kit embrague 190mm", "Sachs", "Transmision", "Suzuki Swift 2014-2019", 189990, 5),
    ("FRN-01", "Juego pastillas freno delantero", "TRW", "Frenos", "Kia Rio 4 2017-2021", 44990, 30),
    ("FRN-02", "Juego pastillas freno delantero", "Brembo", "Frenos", "Hyundai Accent 2012-2019", 49990, 18),
    ("FLT-01", "Filtro de aceite 15600-44410", "Mann", "Servicio (mantencion)", "Suzuki Swift 2014-2019", 7990, 60),
    ("FLT-02", "Filtro de aire motor", "Mann", "Servicio (mantencion)", "Hyundai Accent 2012-2019; Kia Rio 4 2017-2021", 12990, 45),
]

MANUALES = {
    "manual_alternador.pdf": {
        "titulo": "MANUAL TECNICO - ALTERNADOR 12V 90A",
        "secciones": [
            ("Descripcion", "Alternador de 12V y 90A de carga nominal, apto para motores de 1000 a 1500 cc. "
             "Entrega corriente estabilizada para el sistema electrico del vehiculo y carga de bateria."),
            ("Especificaciones", "Voltaje nominal: 14V. Corriente nominal: 90A. Poles: 12. "
             "Polea compatible: correas de 5 canales y 6 canales segun motor. "
             "Conexion de tres cables: B+ (salida principal), D+ (luz de carga) y W (tacometro)."),
            ("Compatibilidad", "Suzuki Swift 2014-2019 (1.4L) y Kia Rio 4 2017-2021 (1.4 MPi). "
             "Verificar soportes y polea antes de instalar."),
        ],
    },
    "manual_kit_embrague.pdf": {
        "titulo": "MANUAL TECNICO - KIT EMBRAGUE 200MM",
        "secciones": [
            ("Descripcion", "Kit compuesto por disco, plato de presion y release bearing (ruleman de empuje). "
             "150 componentes probados en fabrica, para transmision manual de 5 marchas."),
            ("Especificaciones", "Diametro de disco: 200mm. Tipo de spline: 20 estrias x 15.9mm. "
             "Fuerza plato: 4.8kN. Par transmisible: 148 Nm."),
            ("Compatibilidad", "Chevrolet Spark 2011-2019 (1.2L y 1.4L). "
             "Requiere reemplazo simultaneo del ruleman guia y retorno del sistema hidraulico."),
        ],
    },
}


def _generar_inventory() -> str:
    ruta = os.path.join("data", "internal", "inventory.csv")
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["codigo", "descripcion", "marca", "categoria", "vehiculos_compatibles", "precio", "stock"]
        )
        for r in REPUESTOS:
            writer.writerow(r)
    return ruta


def _generar_pdf(nombre: str, contenido: dict) -> str:
    ruta = os.path.join("data", "external", "manuales", nombre)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_margins(CROP, CROP, CROP)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, contenido["titulo"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    for titulo, texto in contenido["secciones"]:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, titulo, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(0, 6, texto)
        pdf.ln(2)
    pdf.output(ruta)
    return ruta


def main() -> int:
    print("Generando inventario interno (CSV)...")
    csv_ruta = _generar_inventory()
    print(f"✓ {csv_ruta} ({len(REPUESTOS)} repuestos)")

    for nombre, contenido in MANUALES.items():
        pdf_ruta = _generar_pdf(nombre, contenido)
        print(f"✓ {pdf_ruta}")

    print("Datos de ejemplo listos")
    return 0


if __name__ == "__main__":
    sys.exit(main())