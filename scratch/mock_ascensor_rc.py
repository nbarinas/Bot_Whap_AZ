import sys
import os

# Add backend to path
sys.path.append(os.path.abspath('backend'))

from render_utils import generate_quota_table_image

data_map = {
    '-': {
        '20-35': {
            'BA': {'current': 13, 'target': 25},
            'MB': {'current': 3, 'target': 25},
            'MT': {'current': 0, 'target': 0}
        },
        '36-55': {
            'BA': {'current': 5, 'target': 25},
            'MB': {'current': 7, 'target': 25},
            'MT': {'current': 0, 'target': 0}
        }
    }
}

ordered_first_nodes = ['20-35', '36-55']
ordered_leaf_nodes = {
    '20-35': ['BA', 'MB', 'MT'],
    '36-55': ['BA', 'MB', 'MT']
}
sorted_rows = ['-']
study_code = 'ASCENSOR RC'
output_path = 'mock_ascensor_rc.png'

print(f"Generating mock for {study_code}...")
generate_quota_table_image(data_map, ordered_first_nodes, ordered_leaf_nodes, sorted_rows, study_code, output_path)
print(f"File saved to {output_path}")
