import sys
import os
from unittest.mock import MagicMock

# Add backend to path
sys.path.append(os.path.abspath('backend'))

import render_utils

# Create dummy data
std_sections = [{
    'title': 'Test Quota',
    'data_map': {'Row 1': {'Group 1': {'Leaf 1': {'current': 5, 'target': 10}}}},
    'ordered_first_nodes': ['Group 1'],
    'ordered_leaf_nodes': {'Group 1': ['Leaf 1']},
    'sorted_rows': ['Row 1']
}]

print("Testing get_pilot_sections...")
pilot_sections = render_utils.get_pilot_sections(std_sections)

if len(pilot_sections) == 2:
    print("✅ Success: Pilot sections expanded to 2 tables.")
    print(f"   Table 1 Title: {pilot_sections[0]['title']}")
    print(f"   Table 2 Title: {pilot_sections[1]['title']}")
else:
    print(f"❌ Error: Expected 2 sections, got {len(pilot_sections)}")

# Test Rendering Standard
print("\nRendering Standard Image...")
render_utils.generate_multi_table_report(std_sections, "TEST_STD", "test_std.png")
if os.path.exists("test_std.png"):
    print("✅ Success: Standard image generated.")
else:
    print("❌ Error: Standard image not generated.")

# Test Rendering Pilot
print("\nRendering Pilot Image...")
render_utils.generate_multi_table_report(pilot_sections, "TEST_PILOT", "test_pilot.png")
if os.path.exists("test_pilot.png"):
    print("✅ Success: Pilot image generated.")
else:
    print("❌ Error: Pilot image not generated.")

print("\nLogic Check:")
PILOT_PHONES = ["3136623816", "573136623816"]
test_phones = ["12345", "3136623816"]

for p in test_phones:
    is_pilot = p in PILOT_PHONES
    print(f"Phone {p} is_pilot: {is_pilot} -> {'NEW FORMAT' if is_pilot else 'OLD FORMAT'}")
