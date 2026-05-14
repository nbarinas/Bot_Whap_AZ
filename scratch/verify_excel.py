import sys
import os

# Add current directory to path to import models and database
sys.path.append(os.getcwd())

from backend import models, database
import pandas as pd
import io
from sqlalchemy.orm import Session
from datetime import datetime

def test_excel_logic():
    print("Testing Excel generation logic...")
    
    # Mock data
    summary_data = [
        {"Categoría": "Edad", "Valor": "20-35", "Tipo de Punto": "Centro Comercial", "Meta (Objetivo)": 20, "Ejecutado": 15, "% Avance": "75%"},
        {"Categoría": "Edad", "Valor": "36-55", "Tipo de Punto": "Centro Comercial", "Meta (Objetivo)": 25, "Ejecutado": 25, "% Avance": "100%"}
    ]
    df_summary = pd.DataFrame(summary_data)
    
    details_data = [
        {"Fecha": "2026-04-21 12:00:00", "Supervisor (WhatsApp)": "3136623816", "Tipo de Punto": "Centro Comercial", "Categoría": "Edad", "Valor": "20-35", "Encuestador": "Juan Pérez"},
        {"Fecha": "2026-04-21 12:05:00", "Supervisor (WhatsApp)": "3136623816", "Tipo de Punto": "Centro Comercial", "Categoría": "Edad", "Valor": "36-55", "Encuestador": "Ana María"}
    ]
    df_details = pd.DataFrame(details_data)
    
    # Generate Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_summary.to_excel(writer, index=False, sheet_name='Resumen de Cuotas')
        df_details.to_excel(writer, index=False, sheet_name='Detalle de Registros')
        
        # Style check (simulation)
        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            print(f"Sheet {sheet_name} generated with {worksheet.max_row} rows.")

    output.seek(0)
    with open("scratch/test_report.xlsx", "wb") as f:
        f.write(output.read())
    
    print("Excel saved to scratch/test_report.xlsx for verification.")

if __name__ == "__main__":
    try:
        test_excel_logic()
    except Exception as e:
        print(f"Error during test: {e}")
