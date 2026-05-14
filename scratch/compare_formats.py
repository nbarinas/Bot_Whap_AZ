import sys
import os

# Add backend to path
sys.path.append(os.path.abspath('backend'))

from render_utils import generate_multi_table_report, get_pilot_sections

# 1. Define Standard Data
data_demo = {
    '-': {
        '20-35': {'BA': {'current': 13, 'target': 25}, 'MB': {'current': 3, 'target': 25}},
        '36-55': {'BA': {'current': 5, 'target': 25}, 'MB': {'current': 7, 'target': 25}}
    }
}
data_pt = {
    '-': {
        'Tipo': {
            'Parque': {'current': 10, 'target': 20},
            'Iglesia': {'current': 10, 'target': 10}
        }
    }
}

sections = [
    { 
        'title': 'Cuota Demográfica', 
        'data_map': data_demo, 
        'ordered_first_nodes': ['20-35', '36-55'], 
        'ordered_leaf_nodes': {'20-35': ['BA', 'MB'], '36-55': ['BA', 'MB']}, 
        'sorted_rows': ['-'] 
    },
    { 
        'title': 'Cuota Tipos de Puntos', 
        'data_map': data_pt, 
        'ordered_first_nodes': ['Tipo'], 
        'ordered_leaf_nodes': {'Tipo': ['Parque', 'Iglesia']}, 
        'sorted_rows': ['-'] 
    }
]

study_code = "ASCENSOR RC"

# Generate Standard Image
print("Generating Standard format...")
generate_multi_table_report(sections, study_code, "format_standard.png")

# Generate Pilot Image
print("Generating Pilot format...")
pilot_sections = get_pilot_sections(sections)
generate_multi_table_report(pilot_sections, study_code, "format_pilot.png")

print("Files saved: format_standard.png, format_pilot.png")
