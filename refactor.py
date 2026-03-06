import re

with open('backend/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

helper = """
def build_study_report(db, study_code):
    from sqlalchemy import func
    from datetime import datetime, date
    import json
    
    today = date.today()
    start_of_day = datetime(today.year, today.month, today.day)
    
    all_study_quotas = db.query(models.BotQuota).filter(models.BotQuota.study_code == study_code).all()
    quota_ids = [q.id for q in all_study_quotas]
    
    matrix_msg = f"📊 *Estado General: {study_code.upper()}*\\n"
    
    grouped_quotas = {}
    for q in all_study_quotas:
        parts = q.category.split(' | ') if '|' in q.category else [q.category]
        parts.append(q.value)
        path_tuple = tuple(p.strip() for p in parts if p.strip())
        
        if not path_tuple:
            continue
        first_node = path_tuple[0]
        rest = " | ".join(path_tuple[1:])
        if first_node not in grouped_quotas:
            grouped_quotas[first_node] = []
        
        grouped_quotas[first_node].append(f"  {rest}: {q.current_count}/{q.target_count}")
    
    for group_name, lines in grouped_quotas.items():
        matrix_msg += f"\\n*{group_name}*\\n"
        matrix_msg += "\\n".join(lines)
        
    daily_stats = db.query(
        models.QuotaSubmission.phone_number,
        func.count(models.QuotaSubmission.id)
    ).filter(
        models.QuotaSubmission.bot_quota_id.in_(quota_ids),
        models.QuotaSubmission.is_deleted == 0,
        models.QuotaSubmission.submitted_at >= start_of_day
    ).group_by(models.QuotaSubmission.phone_number).all()
    
    stats_msg = "\\n\\n📈 *Rendimiento Hoy:*\\n"
    total_today = 0
    for p_num, count in daily_stats:
        stats_msg += f"📞 {p_num}: {count} encuestas\\n"
        total_today += count
    
    if total_today == 0:
        stats_msg += "No hay encuestas hoy aún."
    else:
        stats_msg += f"Total hoy: {total_today}"
        
    return f"\\n{matrix_msg}\\n{stats_msg}"

def compute_next_bot_step(db, ctx, phone=""):
"""

content = content.replace('def compute_next_bot_step(db, ctx, phone=""):', helper)

delete_old = """            if last_sub:
                last_sub.is_deleted = 1
                quota = db.query(models.BotQuota).get(last_sub.bot_quota_id)
                quota.current_count -= 1
                reply = "✅ Se ha borrado tu última encuesta registrada con éxito."
            else:"""

delete_new = """            if last_sub:
                last_sub.is_deleted = 1
                quota = db.query(models.BotQuota).get(last_sub.bot_quota_id)
                quota.current_count -= 1
                
                report = build_study_report(db, study_code)
                reply = f"✅ Se ha borrado tu última encuesta registrada con éxito.\\n{report}"
            else:"""

content = content.replace(delete_old, delete_new)

add_old_pattern = r"# Calculate daily summary[\s\S]*?return f\"{base_reply}\\n{matrix_msg}{stats_msg}\", \"IDLE\""

add_new = """report = build_study_report(db, study_code)
        
        base_reply = f"✅ ¡Guardado! Faltan {quota.target_count - quota.current_count} encuestas de esta cuota."
        return f"{base_reply}{report}", "IDLE\""""

content = re.sub(add_old_pattern, add_new, content)

with open('backend/main.py', 'w', encoding='utf-8') as f:
    f.write(content)
