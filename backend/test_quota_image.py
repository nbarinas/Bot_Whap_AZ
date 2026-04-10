from sqlalchemy.orm import Session
from sqlalchemy import text
import sys
import os

# Add backend to path to import models and database
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend import models, database, render_utils

def generate_sample_from_db():
    db = next(database.get_db())
    try:
        # Get the first study code we find
        study = db.query(models.BotQuota.study_code).first()
        if not study:
            print("No studies found in DB.")
            return
        
        study_code = study.study_code
        print(f"Generating sample for study: {study_code}")
        
        all_study_quotas = db.query(models.BotQuota).filter(models.BotQuota.study_code == study_code).all()
        
        col_tree = {} 
        row_keys = set()
        data_map = {} 

        for q in all_study_quotas:
            parts = q.category.split(' | ') if '|' in q.category else [q.category]
            parts.append(q.value)
            path_tuple = tuple(p.strip() for p in parts if p.strip())
            
            if not path_tuple: continue
                
            first_node = path_tuple[0]
            if len(path_tuple) > 2:
                middle_str = " | ".join(path_tuple[1:-1])
                leaf_node = path_tuple[-1]
            elif len(path_tuple) == 2:
                middle_str = "-"
                leaf_node = path_tuple[-1]
            else:
                middle_str = "-"
                leaf_node = path_tuple[0]
                
            if first_node not in col_tree:
                col_tree[first_node] = set()
            col_tree[first_node].add(leaf_node)
            row_keys.add(middle_str)
            
            if middle_str not in data_map: data_map[middle_str] = {}
            if first_node not in data_map[middle_str]: data_map[middle_str][first_node] = {}
                
            data_map[middle_str][first_node][leaf_node] = {
                'current': q.current_count,
                'target': q.target_count
            }

        ordered_first_nodes = sorted(list(col_tree.keys()))
        ordered_leaf_nodes = {fn: sorted(list(col_tree[fn])) for fn in ordered_first_nodes}
        sorted_rows = sorted(list(row_keys))

        # Render
        output = "sample_quota_report.png"
        render_utils.generate_quota_table_image(
            data_map, ordered_first_nodes, ordered_leaf_nodes, sorted_rows, study_code, output
        )
        print(f"Sample generated: {os.path.abspath(output)}")
        
    finally:
        db.close()

if __name__ == "__main__":
    generate_sample_from_db()
