from PIL import Image, ImageDraw, ImageFont
import os
from datetime import datetime

def get_text_size(text, f):
    try:
        # Pillow 10+
        box = f.getbbox(str(text))
        return box[2] - box[0], box[3] - box[1]
    except AttributeError:
        # Older Pillow
        return f.getsize(str(text))

def generate_multi_table_report(sections, study_code, output_path="quota_report.png"):
    """
    Renders multiple table sections vertically into one compact image.
    sections: list of { title, data_map, ordered_first_nodes, ordered_leaf_nodes, sorted_rows }
    """
    # Stylistic constants
    PADDING = 30
    CELL_PADDING_H = 15
    CELL_PADDING_V = 10
    HEADER_BG = (45, 52, 71) 
    HEADER_TEXT = (255, 255, 255)
    CELL_BG = (255, 255, 255)
    CELL_BG_ALT = (248, 249, 252) 
    HIGHLIGHT_BG = (255, 230, 100) # Yellow for filled
    HIGHLIGHT_TEXT = (100, 80, 0)   
    EXCEEDED_BG = (255, 204, 204)  # Red for exceeded
    EXCEEDED_TEXT = (180, 0, 0)    
    BORDER_COLOR = (218, 220, 224)
    TEXT_COLOR = (60, 64, 67)
    PRIMARY_LABEL_COLOR = (32, 33, 36)
    
    # Font setup
    font, bold_font, title_font, section_font, footer_font = None, None, None, None, None
    possible_fonts = ["C:\\Windows\\Fonts\\arial.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    possible_bolds = ["C:\\Windows\\Fonts\\arialbd.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]

    for fp in possible_fonts:
        if os.path.exists(fp):
            font = ImageFont.truetype(fp, 16)
            footer_font = ImageFont.truetype(fp, 13)
            break
    for bp in possible_bolds:
        if os.path.exists(bp):
            bold_font = ImageFont.truetype(bp, 16)
            section_font = ImageFont.truetype(bp, 19)
            title_font = ImageFont.truetype(bp, 24)
            break
    
    if not font: font = footer_font = ImageFont.load_default()
    if not bold_font: bold_font = section_font = title_font = ImageFont.load_default()

    def wrap_text(text, max_chars=12):
        if len(text) <= max_chars: return [text]
        # Split by space or slash
        import re
        parts = re.split(r'([ /])', text)
        lines = []
        curr = ""
        for p in parts:
            if len(curr) + len(p) <= max_chars:
                curr += p
            else:
                if curr: lines.append(curr.strip())
                curr = p
        if curr: lines.append(curr.strip())
        return lines

    # Pre-calculate section layouts
    calculated_sections = []
    max_img_w = 400

    for sec in sections:
        data_map = sec['data_map']
        ordered_first_nodes = sec['ordered_first_nodes']
        ordered_leaf_nodes = sec['ordered_leaf_nodes']
        sorted_rows = sec['sorted_rows']
        display_mode = sec.get('display_mode', 'both') # 'both', 'target', or 'current'
        
        flat_cols = []
        wrapped_headers = {} 
        for fn in ordered_first_nodes:
            for ln in ordered_leaf_nodes[fn]:
                flat_cols.append((fn, ln))
                wrapped_headers[(fn, ln)] = wrap_text(ln, 11)
        
        row_totals = {r: {'current': 0, 'target': 0, 'any_exceeded': False} for r in sorted_rows}
        col_totals = {(fn, ln): {'current': 0, 'target': 0, 'any_exceeded': False} for fn, ln in flat_cols}
        grand_total = {'current': 0, 'target': 0, 'any_exceeded': False}

        for r in sorted_rows:
            for fn, ln in flat_cols:
                if fn in data_map.get(r, {}) and ln in data_map[r][fn]:
                    d = data_map[r][fn][ln]
                    curr, targ = d['current'], d['target']
                    if curr > targ:
                        row_totals[r]['any_exceeded'] = True
                        col_totals[(fn, ln)]['any_exceeded'] = True
                        grand_total['any_exceeded'] = True
                    row_totals[r]['current'] += curr
                    row_totals[r]['target'] += targ
                    col_totals[(fn, ln)]['current'] += curr
                    col_totals[(fn, ln)]['target'] += targ
                    grand_total['current'] += curr
                    grand_total['target'] += targ

        # Column Widths
        col0_w = max([get_text_size(r, bold_font)[0] for r in sorted_rows + ["Total"]] + [get_text_size("Cat.", bold_font)[0]]) + 2 * CELL_PADDING_H
        col_widths = [col0_w]
        for fn, ln in flat_cols:
            lines = wrapped_headers[(fn, ln)]
            max_header_w = max([get_text_size(line, bold_font)[0] for line in lines + [fn]])
            
            max_val_w = 0
            for r in sorted_rows:
                if fn in data_map.get(r, {}) and ln in data_map[r][fn]:
                    d = data_map[r][fn][ln]
                    val = str(d['target'] if display_mode == 'target' else (d['current'] if display_mode == 'current' else f"{d['current']}/{d['target']}"))
                    max_val_w = max(max_val_w, get_text_size(val, font)[0])
            ct = col_totals[(fn, ln)]
            ct_val = str(ct['target'] if display_mode == 'target' else (ct['current'] if display_mode == 'current' else f"{ct['current']}/{ct['target']}"))
            max_val_w = max(max_val_w, get_text_size(ct_val, bold_font)[0])
            
            col_widths.append(max(max_header_w, max_val_w) + 2 * CELL_PADDING_H)
        
        # Total Column width
        all_row_tot_vals = []
        for r in sorted_rows:
            rt = row_totals[r]
            all_row_tot_vals.append(str(rt['target'] if display_mode == 'target' else (rt['current'] if display_mode == 'current' else f"{rt['current']}/{rt['target']}")))
        gt_val = str(grand_total['target'] if display_mode == 'target' else (grand_total['current'] if display_mode == 'current' else f"{grand_total['current']}/{grand_total['target']}"))
        
        max_total_w = max([get_text_size(v, bold_font)[0] for v in all_row_tot_vals + [gt_val, "Total"]])
        col_widths.append(max_total_w + 2 * CELL_PADDING_H)
        
        table_w = sum(col_widths)
        max_img_w = max(max_img_w, table_w + 2 * PADDING)
        
        calculated_sections.append({
            'sec': sec,
            'flat_cols': flat_cols,
            'wrapped_headers': wrapped_headers,
            'col_widths': col_widths,
            'row_totals': row_totals,
            'col_totals': col_totals,
            'grand_total': grand_total,
            'table_w': table_w,
            'display_mode': display_mode,
            'header_bg': sec.get('header_bg', HEADER_BG)
        })

    # Total Image Elevation
    header_h = 70
    footer_h = 50
    total_h = header_h + footer_h
    row_h = get_text_size("AnyText", bold_font)[1] + 2 * CELL_PADDING_V

    for cs in calculated_sections:
        total_h += 40 # Section title
        total_h += (len(cs['sec']['sorted_rows']) + 3) * row_h # +2 header rows + 1 total row
        total_h += 30 # Margin after section

    img = Image.new('RGB', (max_img_w, total_h), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 1. Main Title
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    title_text = f"REPORTE: {study_code.upper()}"
    tw, _ = get_text_size(title_text, title_font)
    draw.text(((max_img_w - tw)//2, 20), title_text, fill=PRIMARY_LABEL_COLOR, font=title_font)

    curr_y = header_h

    # 2. Sections
    for cs in calculated_sections:
        sec = cs['sec']
        h_bg = cs['header_bg']
        display_mode = cs['display_mode']
        
        draw.text((PADDING, curr_y), sec['title'].upper(), fill=h_bg, font=section_font)
        curr_y += 30
        
        start_x = PADDING
        col_w = cs['col_widths']
        flat_cols = cs['flat_cols']
        sorted_rows = sec['sorted_rows']
        data_map = sec['data_map']
        
        # Header Row 1 (Groups)
        cx = start_x
        draw.rectangle([cx, curr_y, cx + col_w[0], curr_y + 2*row_h], fill=h_bg, outline=BORDER_COLOR)
        cat_w, cat_h = get_text_size("Cat.", bold_font)
        draw.text((cx + (col_w[0] - cat_w)//2, curr_y + (2*row_h - cat_h)//2), "Cat.", fill=HEADER_TEXT, font=bold_font)
        cx += col_w[0]
        
        flat_idx = 0
        for fn in sec['ordered_first_nodes']:
            num_spanned = len(sec['ordered_leaf_nodes'][fn])
            span_w = sum(col_w[flat_idx + 1 : flat_idx + 1 + num_spanned])
            draw.rectangle([cx, curr_y, cx + span_w, curr_y + row_h], fill=h_bg, outline=BORDER_COLOR)
            tw, th = get_text_size(fn, bold_font)
            draw.text((cx + (span_w - tw)//2, curr_y + (row_h - th)//2), fn, fill=HEADER_TEXT, font=bold_font)
            
            lx = cx
            for ln in sec['ordered_leaf_nodes'][fn]:
                ln_w = col_w[flat_idx + 1]
                lines = cs['wrapped_headers'][(fn, ln)]
                draw.rectangle([lx, curr_y + row_h, lx + ln_w, curr_y + 2*row_h], fill=h_bg, outline=BORDER_COLOR)
                
                # Draw lines centered vertically and horizontally
                line_h = get_text_size("A", bold_font)[1]
                total_text_h = len(lines) * line_h
                ty = curr_y + row_h + (row_h - total_text_h)//2
                for line in lines:
                    lw, lh = get_text_size(line, bold_font)
                    draw.text((lx + (ln_w - lw)//2, ty), line, fill=HEADER_TEXT, font=bold_font)
                    ty += line_h
                
                lx += ln_w
                flat_idx += 1
            cx += span_w
        
        # Total Column Header
        draw.rectangle([cx, curr_y, cx + col_w[-1], curr_y + 2*row_h], fill=h_bg, outline=BORDER_COLOR)
        tw, th = get_text_size("Total", bold_font)
        draw.text((cx + (col_w[-1] - tw)//2, curr_y + (2*row_h - th)//2), "Total", fill=HEADER_TEXT, font=bold_font)
        
        curr_y += 2 * row_h
        
        # Data Rows
        for r_idx, r_label in enumerate(sorted_rows):
            cx = start_x
            bg = CELL_BG if r_idx % 2 == 1 else CELL_BG_ALT
            draw.rectangle([cx, curr_y, cx + col_w[0], curr_y + row_h], fill=bg, outline=BORDER_COLOR)
            draw.text((cx + CELL_PADDING_H, curr_y + (row_h - get_text_size(r_label, bold_font)[1])//2), r_label, fill=PRIMARY_LABEL_COLOR, font=bold_font)
            cx += col_w[0]
            
            for c_idx, (fn, ln) in enumerate(flat_cols):
                cw = col_w[c_idx+1]
                val_str = ""
                cell_bg = bg
                is_hl, is_ex = False, False
                if fn in data_map.get(r_label, {}) and ln in data_map[r_label][fn]:
                    d = data_map[r_label][fn][ln]
                    # Format value based on mode
                    if display_mode == 'target': val_str = str(d['target'])
                    elif display_mode == 'current': val_str = str(d['current'])
                    else: val_str = f"{d['current']}/{d['target']}"
                    
                    # Highlighting (Always compare current vs target regardless of what is displayed)
                    if d['current'] > d['target']: is_ex, cell_bg = True, EXCEEDED_BG
                    elif d['current'] == d['target'] and d['target'] > 0: is_hl, cell_bg = True, HIGHLIGHT_BG
                
                # Only highlight progress table (current), goal table stays clean? 
                # User said "colores... forma es lo que quiero cambiar", but mockup showed colors in pending.
                # I'll apply colors to both by default as it was, but it's more useful in 'current' mode.
                # If we are in 'target' mode, maybe we don't highlight? No, user said "siempre siguiendo lo del amarillo y rojo".
                draw.rectangle([cx, curr_y, cx + cw, curr_y + row_h], fill=cell_bg, outline=BORDER_COLOR)
                if val_str:
                    tw, th = get_text_size(val_str, bold_font if (is_hl or is_ex) else font)
                    color = EXCEEDED_TEXT if is_ex else (HIGHLIGHT_TEXT if is_hl else TEXT_COLOR)
                    draw.text((cx + (cw - tw)//2, curr_y + (row_h - th)//2), val_str, fill=color, font=bold_font if (is_hl or is_ex) else font)
                cx += cw
                
            # Row Totals
            rt = cs['row_totals'][r_label]
            if display_mode == 'target': rt_str = str(rt['target'])
            elif display_mode == 'current': rt_str = str(rt['current'])
            else: rt_str = f"{rt['current']}/{rt['target']}"
            
            is_hl = rt['current'] == rt['target'] and rt['target'] > 0 and not rt['any_exceeded']
            is_ex = rt['current'] > rt['target']
            bg_tot = EXCEEDED_BG if is_ex else (HIGHLIGHT_BG if is_hl else bg)
            draw.rectangle([cx, curr_y, cx + col_w[-1], curr_y + row_h], fill=bg_tot, outline=BORDER_COLOR)
            tw, th = get_text_size(rt_str, bold_font)
            color = EXCEEDED_TEXT if is_ex else (HIGHLIGHT_TEXT if is_hl else TEXT_COLOR)
            draw.text((cx + (col_w[-1]-tw)//2, curr_y + (row_h-th)//2), rt_str, fill=color, font=bold_font)
            curr_y += row_h

        # Section Totals
        cx = start_x
        draw.rectangle([cx, curr_y, cx + col_w[0], curr_y + row_h], fill=h_bg, outline=BORDER_COLOR)
        tw, th = get_text_size("Total", bold_font)
        draw.text((cx + (col_w[0] - tw)//2, curr_y + (row_h - th)//2), "Total", fill=HEADER_TEXT, font=bold_font)
        cx += col_w[0]

        for c_idx, (fn, ln) in enumerate(flat_cols):
            ct = cs['col_totals'][(fn, ln)]
            if display_mode == 'target': ct_str = str(ct['target'])
            elif display_mode == 'current': ct_str = str(ct['current'])
            else: ct_str = f"{ct['current']}/{ct['target']}"
            
            is_hl = ct['current'] == ct['target'] and ct['target'] > 0 and not ct['any_exceeded']
            is_ex = ct['current'] > ct['target']
            bg_tot = EXCEEDED_BG if is_ex else (HIGHLIGHT_BG if is_hl else CELL_BG_ALT)
            draw.rectangle([cx, curr_y, cx + col_w[c_idx+1], curr_y + row_h], fill=bg_tot, outline=BORDER_COLOR)
            tw, th = get_text_size(ct_str, bold_font)
            color = EXCEEDED_TEXT if is_ex else (HIGHLIGHT_TEXT if is_hl else TEXT_COLOR)
            draw.text((cx + (col_w[c_idx+1]-tw)//2, curr_y + (row_h-th)//2), ct_str, fill=color, font=bold_font)
            cx += col_w[c_idx+1]
        
        gt = cs['grand_total']
        if display_mode == 'target': gt_str = str(gt['target'])
        elif display_mode == 'current': gt_str = str(gt['current'])
        else: gt_str = f"{gt['current']}/{gt['target']}"
        
        is_hl = gt['current'] == gt['target'] and gt['target'] > 0 and not gt['any_exceeded']
        is_ex = gt['current'] > gt['target']
        bg_gt = EXCEEDED_BG if is_ex else (HIGHLIGHT_BG if is_hl else CELL_BG_ALT)
        draw.rectangle([cx, curr_y, cx + col_w[-1], curr_y + row_h], fill=bg_gt, outline=BORDER_COLOR)
        tw, th = get_text_size(gt_str, bold_font)
        color = EXCEEDED_TEXT if is_ex else (HIGHLIGHT_TEXT if is_hl else TEXT_COLOR)
        draw.text((cx + (col_w[-1]-tw)//2, curr_y + (row_h-th)//2), gt_str, fill=color, font=bold_font)
        
        curr_y += row_h + 30 # Spacer between sections

    # Footer
    footer = f"Reporte automático AZ Marketing - {timestamp}"
    fw, _ = get_text_size(footer, footer_font)
    draw.text(((max_img_w - fw)//2, total_h - 25), footer, fill=(128, 128, 128), font=footer_font)

    img.save(output_path)
    return output_path

# Keep the original function as a wrapper for backward compatibility
def generate_quota_table_image(data_map, ordered_first_nodes, ordered_leaf_nodes, sorted_rows, study_code, output_path="quota_report.png"):
    sec1 = {
        'title': 'Cuota a Realizar',
        'data_map': data_map,
        'ordered_first_nodes': ordered_first_nodes,
        'ordered_leaf_nodes': ordered_leaf_nodes,
        'sorted_rows': sorted_rows,
        'display_mode': 'target',
        'header_bg': (70, 130, 180) # Steel Blue
    }
    sec2 = {
        'title': 'Cuota Realizada',
        'data_map': data_map,
        'ordered_first_nodes': ordered_first_nodes,
        'ordered_leaf_nodes': ordered_leaf_nodes,
        'sorted_rows': sorted_rows,
        'display_mode': 'current',
        'header_bg': (230, 126, 34) # Carrot Orange
    }
    return generate_multi_table_report([sec1, sec2], study_code, output_path)
