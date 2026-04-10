from PIL import Image, ImageDraw, ImageFont
import os

def generate_quota_table_image(data_map, ordered_first_nodes, ordered_leaf_nodes, sorted_rows, study_code, output_path="quota_report.png"):
    """
    Renders a complex hierarchical quota table image.
    data_map: { row_label: { first_node: { leaf_node: {current, target} } } }
    ordered_first_nodes: list of unique cities/categories for columns
    ordered_leaf_nodes: { first_node: [leaf_nodes] }
    sorted_rows: list of labels for Y axis (e.g. age ranges)
    """
    # Stylistic constants
    PADDING = 30
    CELL_PADDING_H = 15
    CELL_PADDING_V = 12
    HEADER_BG = (45, 52, 71) # Deep professional blue
    HEADER_TEXT = (255, 255, 255)
    CELL_BG = (255, 255, 255)
    CELL_BG_ALT = (248, 249, 252) # Very light gray-blue
    HIGHLIGHT_BG = (255, 248, 204) # Soft yellow for filled quotas
    HIGHLIGHT_TEXT = (140, 110, 0) # Darker gold/brown for contrast
    BORDER_COLOR = (218, 220, 224)
    TEXT_COLOR = (60, 64, 67)
    PRIMARY_LABEL_COLOR = (32, 33, 36)
    
    # Font setup
    try:
        # Standard paths on Windows
        font_path = "C:\\Windows\\Fonts\\arial.ttf"
        font_bold_path = "C:\\Windows\\Fonts\\arialbd.ttf"
        
        font = ImageFont.truetype(font_path, 14)
        bold_font = ImageFont.truetype(font_bold_path, 14)
        title_font = ImageFont.truetype(font_bold_path, 20)
        footer_font = ImageFont.truetype(font_path, 11)
    except:
        # Fallback for other OS or if fonts missing
        font = ImageFont.load_default()
        bold_font = ImageFont.load_default()
        title_font = ImageFont.load_default()
        footer_font = ImageFont.load_default()

    def get_text_size(text, f):
        box = f.getbbox(str(text))
        return box[2] - box[0], box[3] - box[1]

    # Process flattened columns
    # We'll have: Row Label | (FN, LN) | (FN, LN) ...
    flat_cols = []
    for fn in ordered_first_nodes:
        for ln in ordered_leaf_nodes[fn]:
            flat_cols.append((fn, ln))
            
    # Calculate Column Widths
    # Col 0 is "Categoria/Rango"
    col0_w = max([get_text_size(r, bold_font)[0] for r in sorted_rows] + [get_text_size("Categoría", bold_font)[0]]) + 2 * CELL_PADDING_H
    
    col_widths = [col0_w]
    for fn, ln in flat_cols:
        # Check header text and data text
        max_w = max(get_text_size(fn, bold_font)[0], get_text_size(ln, bold_font)[0])
        for r in sorted_rows:
            if fn in data_map.get(r, {}) and ln in data_map[r][fn]:
                d = data_map[r][fn][ln]
                val_str = f"{d['current']}/{d['target']}"
                max_w = max(max_w, get_text_size(val_str, font)[0])
        col_widths.append(max_w + 2 * CELL_PADDING_H)

    # Row Heights
    row_height = 0
    header_rows = 2 # One for first_node, one for leaf_node
    for r in sorted_rows + ["Header"]:
        _, h = get_text_size("AnyText", bold_font)
        row_height = max(row_height, h + 2 * CELL_PADDING_V)

    # Totals
    table_w = sum(col_widths)
    table_h = (len(sorted_rows) + header_rows) * row_height
    img_w = table_w + 2 * PADDING
    img_h = table_h + 100 # Extra space for title and timestamp

    img = Image.new('RGB', (img_w, img_h), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Draw Title
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = f"ESTADO DE CUOTAS: {study_code.upper()}"
    tw, _ = get_text_size(title, title_font)
    draw.text(((img_w - tw)//2, 25), title, fill=PRIMARY_LABEL_COLOR, font=title_font)
    
    footer = f"Generado automáticamente el {timestamp}"
    fw, fh = get_text_size(footer, footer_font)
    draw.text(((img_w - fw)//2, img_h - 25), footer, fill=(128, 128, 128), font=footer_font)

    # Table Starting Point
    start_y = 80
    
    # Draw Headers
    # 1. First Node Row (Cities/Main Categories)
    current_x = PADDING
    draw.rectangle([current_x, start_y, current_x + col_widths[0], start_y + 2*row_height], fill=HEADER_BG, outline=BORDER_COLOR)
    _, th = get_text_size("Categoría", bold_font)
    draw.text((current_x + (col_widths[0] - get_text_size("Categoría", bold_font)[0])//2, start_y + (2*row_height - th)//2), "Categoría", fill=HEADER_TEXT, font=bold_font)
    
    current_x += col_widths[0]
    flat_idx = 0
    for fn in ordered_first_nodes:
        num_spanned = len(ordered_leaf_nodes[fn])
        span_w = sum(col_widths[flat_idx + 1 : flat_idx + 1 + num_spanned])
        
        # Draw merge cell for First Node
        draw.rectangle([current_x, start_y, current_x + span_w, start_y + row_height], fill=HEADER_BG, outline=BORDER_COLOR)
        tw, th = get_text_size(fn, bold_font)
        draw.text((current_x + (span_w - tw)//2, start_y + (row_height - th)//2), fn, fill=HEADER_TEXT, font=bold_font)
        
        # Draw Leaf Nodes below
        leaf_x = current_x
        for ln in ordered_leaf_nodes[fn]:
            ln_w = col_widths[flat_idx + 1]
            draw.rectangle([leaf_x, start_y + row_height, leaf_x + ln_w, start_y + 2*row_height], fill=HEADER_BG, outline=BORDER_COLOR)
            tw, th = get_text_size(ln, bold_font)
            draw.text((leaf_x + (ln_w - tw)//2, start_y + row_height + (row_height - th)//2), ln, fill=HEADER_TEXT, font=bold_font)
            leaf_x += ln_w
            flat_idx += 1
            
        current_x += span_w

    # Draw Data Rows
    current_y = start_y + 2 * row_height
    for r_idx, r_label in enumerate(sorted_rows):
        current_x = PADDING
        
        # Row Label
        bg = CELL_BG if r_idx % 2 == 1 else CELL_BG_ALT
        draw.rectangle([current_x, current_y, current_x + col_widths[0], current_y + row_height], fill=bg, outline=BORDER_COLOR)
        draw.text((current_x + CELL_PADDING_H, current_y + (row_height - th)//2), r_label, fill=PRIMARY_LABEL_COLOR, font=bold_font)
        
        current_x += col_widths[0]
        for c_idx, (fn, ln) in enumerate(flat_cols):
            cell_w = col_widths[c_idx + 1]
            cell_bg = bg
            
            val_str = ""
            is_highlight = False
            if fn in data_map.get(r_label, {}) and ln in data_map[r_label][fn]:
                d = data_map[r_label][fn][ln]
                val_str = f"{d['current']}/{d['target']}"
                if d['current'] >= d['target']:
                    is_highlight = True
                    cell_bg = HIGHLIGHT_BG
            
            draw.rectangle([current_x, current_y, current_x + cell_w, current_y + row_height], fill=cell_bg, outline=BORDER_COLOR)
            
            if val_str:
                tw, th = get_text_size(val_str, font if not is_highlight else bold_font)
                color = HIGHLIGHT_TEXT if is_highlight else TEXT_COLOR
                draw.text((current_x + (cell_w - tw)//2, current_y + (row_height - th)//2), val_str, fill=color, font=bold_font if is_highlight else font)
            
            current_x += cell_w
            
        current_y += row_height

    # Save
    img.save(output_path)
    return output_path

if __name__ == "__main__":
    # Internal Mock Test
    mock_data = {
        '18-30': {'Norte': {'MT': {'current': 12, 'target': 12}, 'MB': {'current': 5, 'target': 12}}, 
                  'Centro': {'MT': {'current': 11, 'target': 11}, 'MB': {'current': 3, 'target': 11}}},
        '31-45': {'Norte': {'MT': {'current': 8, 'target': 12}, 'MB': {'current': 12, 'target': 12}},
                  'Centro': {'MT': {'current': 2, 'target': 11}, 'MB': {'current': 11, 'target': 11}}}
    }
    mock_fn = ['Norte', 'Centro']
    mock_ln = {'Norte': ['MT', 'MB'], 'Centro': ['MT', 'MB']}
    mock_rows = ['18-30', '31-45']
    
    generate_quota_table_image(mock_data, mock_fn, mock_ln, mock_rows, "TEST_LOCAL_RENDER", "mock_quota_render.png")
    print("Mock render created at mock_quota_render.png")
