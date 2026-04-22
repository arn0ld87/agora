import os
import sys

# Add backend directory to sys.path to allow imports
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, backend_dir)

from app.utils.validation import (
    validate_project_id,
    validate_simulation_id,
    validate_report_id,
    validate_graph_id,
    validate_task_id
)

def test_validators():
    print("Testing ID validators for path traversal and injection...")

    cases = [
        ("proj_0123456789ab", True),
        ("proj_0123456789a", False),
        ("proj_0123456789abc", False),
        ("../etc/passwd", False),
        ("proj_0123456789ab/../", False),
        ("sim_0123456789ab", True),
        ("report_0123456789ab", True),
        ("550e8400-e29b-41d4-a716-446655440000", True), # UUID
        ("0123456789abcdef0123456789abcdef", True), # 32-char hex
        ("'; DROP TABLE students; --", False),
    ]

    all_passed = True
    for val, expected in cases:
        # Test all validators that match the prefix or are generic
        if val.startswith("proj_"):
            result = validate_project_id(val)
        elif val.startswith("sim_"):
            result = validate_simulation_id(val)
        elif val.startswith("report_"):
            result = validate_report_id(val)
        elif "-" in val or len(val) == 32:
            result = validate_graph_id(val) and validate_task_id(val)
        else:
            # For malicious strings, all should return False
            result = any([
                validate_project_id(val),
                validate_simulation_id(val),
                validate_report_id(val),
                validate_graph_id(val),
                validate_task_id(val)
            ])
            result = not result # We expect all to be False
            expected = True # So result should be True if all are False

        if result == expected:
            print(f"[PASS] Value: {val}")
        else:
            print(f"[FAIL] Value: {val} (expected {expected}, got {result})")
            all_passed = False

    return all_passed

if __name__ == "__main__":
    if test_validators():
        print("\nAll security validations passed!")
        sys.exit(0)
    else:
        print("\nSecurity validation failures detected.")
        sys.exit(1)
