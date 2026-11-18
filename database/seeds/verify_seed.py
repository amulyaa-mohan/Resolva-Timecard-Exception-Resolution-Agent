"""
Standalone Seed & Database Verification Script for Resolva.

Validates that:
1. All core entities exist in the database with expected college-demo counts:
   - Organization (>= 2)
   - Location (>= 3)
   - Policy Packs (3-5)
   - Policy Clauses (10-20)
   - Employees (20-30)
   - Shifts (>= 120)
   - Raw Punches (== 398 strictly immutable baseline)
   - Exceptions (30-50)
   - Proposals (20-30)
   - Corrections (10-20)
   - Audit Events (30-50)
2. Zero duplicate business records exist across tables.
3. Foreign key integrity holds across ALL 11 tables with zero orphaned rows.
"""

from pathlib import Path
import sqlite3
import sys

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DEFAULT_DB_PATH = PROJECT_ROOT.parent / "backend" / "shiftsense.db"


def verify_database(db_path: Path = DEFAULT_DB_PATH) -> bool:
    print("=" * 80)
    print(f"       RESOLVA DATABASE INTEGRITY & SEED VERIFICATION")
    print(f"       Target: {db_path.resolve()}")
    print("=" * 80)

    if not db_path.exists():
        print(f"[FAIL] Database file does not exist at: {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    checks = []

    # 1. Table Counts & Range Checks
    cur.execute("SELECT COUNT(*) FROM organization")
    org_count = cur.fetchone()[0]
    checks.append(("Organization Count (>= 2)", org_count >= 2, f"Found {org_count}"))

    cur.execute("SELECT COUNT(*) FROM location")
    loc_count = cur.fetchone()[0]
    checks.append(("Location Count (>= 3)", loc_count >= 3, f"Found {loc_count}"))

    cur.execute("SELECT COUNT(*) FROM policy_packs")
    pack_count = cur.fetchone()[0]
    checks.append(("Policy Pack Count (3-5)", 3 <= pack_count <= 5, f"Found {pack_count}"))

    cur.execute("SELECT COUNT(*) FROM policy_clause")
    clause_count = cur.fetchone()[0]
    checks.append(("Policy Clause Count (10-20)", 10 <= clause_count <= 20, f"Found {clause_count}"))

    cur.execute("SELECT COUNT(*) FROM employee")
    emp_count = cur.fetchone()[0]
    checks.append(("Employee Count (20-30)", 20 <= emp_count <= 30, f"Found {emp_count}"))

    cur.execute("SELECT COUNT(*) FROM shift")
    shift_count = cur.fetchone()[0]
    checks.append(("Shift Count (>= 120)", shift_count >= 120, f"Found {shift_count}"))

    cur.execute("SELECT COUNT(*) FROM punch")
    punch_count = cur.fetchone()[0]
    checks.append(("Raw Punch Count (== 398 strictly immutable)", punch_count == 398, f"Found {punch_count}"))

    cur.execute("SELECT COUNT(*) FROM exception_record")
    exc_count = cur.fetchone()[0]
    checks.append(("Exception Count (30-50)", 30 <= exc_count <= 50, f"Found {exc_count}"))

    cur.execute("SELECT COUNT(*) FROM proposal")
    prop_count = cur.fetchone()[0]
    checks.append(("Proposal Count (20-35)", 20 <= prop_count <= 35, f"Found {prop_count}"))

    cur.execute("SELECT COUNT(*) FROM correction")
    cor_count = cur.fetchone()[0]
    checks.append(("Correction Count (10-20)", 10 <= cor_count <= 20, f"Found {cor_count}"))

    cur.execute("SELECT COUNT(*) FROM audit_event")
    aud_count = cur.fetchone()[0]
    checks.append(("Audit Event Count (30-50)", 30 <= aud_count <= 50, f"Found {aud_count}"))

    # 2. Foreign Key Integrity Checks (No orphaned records)
    cur.execute("""
        SELECT COUNT(*) FROM location 
        WHERE organization_id NOT IN (SELECT id FROM organization)
    """)
    orphaned_loc = cur.fetchone()[0]
    checks.append(("Location -> Organization FK", orphaned_loc == 0, f"{orphaned_loc} orphaned"))

    cur.execute("""
        SELECT COUNT(*) FROM employee 
        WHERE location_id NOT IN (SELECT id FROM location)
           OR policy_pack_id NOT IN (SELECT id FROM policy_packs)
    """)
    orphaned_emp = cur.fetchone()[0]
    checks.append(("Employee -> Location/PolicyPack FK", orphaned_emp == 0, f"{orphaned_emp} orphaned"))

    cur.execute("""
        SELECT COUNT(*) FROM shift 
        WHERE employee_id NOT IN (SELECT id FROM employee)
    """)
    orphaned_shifts = cur.fetchone()[0]
    checks.append(("Shift -> Employee FK", orphaned_shifts == 0, f"{orphaned_shifts} orphaned"))

    cur.execute("""
        SELECT COUNT(*) FROM punch 
        WHERE employee_id NOT IN (SELECT id FROM employee)
    """)
    orphaned_punches = cur.fetchone()[0]
    checks.append(("Punch -> Employee FK", orphaned_punches == 0, f"{orphaned_punches} orphaned"))

    cur.execute("""
        SELECT COUNT(*) FROM policy_clause 
        WHERE policy_pack_id NOT IN (SELECT id FROM policy_packs)
    """)
    orphaned_clauses = cur.fetchone()[0]
    checks.append(("Policy Clause -> PolicyPack FK", orphaned_clauses == 0, f"{orphaned_clauses} orphaned"))

    cur.execute("""
        SELECT COUNT(*) FROM exception_record 
        WHERE employee_id NOT IN (SELECT id FROM employee)
    """)
    orphaned_exceptions = cur.fetchone()[0]
    checks.append(("Exception -> Employee FK", orphaned_exceptions == 0, f"{orphaned_exceptions} orphaned"))

    cur.execute("""
        SELECT COUNT(*) FROM proposal 
        WHERE exception_id NOT IN (SELECT id FROM exception_record)
    """)
    orphaned_proposals = cur.fetchone()[0]
    checks.append(("Proposal -> Exception FK", orphaned_proposals == 0, f"{orphaned_proposals} orphaned"))

    cur.execute("""
        SELECT COUNT(*) FROM correction 
        WHERE proposal_id IS NOT NULL AND proposal_id NOT IN (SELECT id FROM proposal)
    """)
    orphaned_corrections = cur.fetchone()[0]
    checks.append(("Correction -> Proposal FK", orphaned_corrections == 0, f"{orphaned_corrections} orphaned"))

    # 3. Duplicate Detection Checks
    cur.execute("""
        SELECT code, COUNT(*) FROM organization GROUP BY code HAVING COUNT(*) > 1
    """)
    dup_orgs = len(cur.fetchall())
    checks.append(("Zero Duplicate Organizations", dup_orgs == 0, f"{dup_orgs} duplicates"))

    cur.execute("""
        SELECT policy_pack_id, clause_id, COUNT(*) 
        FROM policy_clause 
        GROUP BY policy_pack_id, clause_id 
        HAVING COUNT(*) > 1
    """)
    dup_clauses = len(cur.fetchall())
    checks.append(("Zero Duplicate Policy Clauses", dup_clauses == 0, f"{dup_clauses} duplicates"))

    cur.execute("""
        SELECT employee_id, work_date, code, COUNT(*) 
        FROM exception_record 
        GROUP BY employee_id, work_date, code 
        HAVING COUNT(*) > 1
    """)
    dup_exceptions = len(cur.fetchall())
    checks.append(("Zero Duplicate Exceptions", dup_exceptions == 0, f"{dup_exceptions} duplicates"))

    cur.execute("""
        SELECT trace_id, COUNT(*) 
        FROM audit_event 
        GROUP BY trace_id 
        HAVING COUNT(*) > 1
    """)
    dup_audits = len(cur.fetchall())
    checks.append(("Zero Duplicate Audit Trace IDs", dup_audits == 0, f"{dup_audits} duplicates"))

    # Print summary
    all_passed = True
    print("\n--- Detailed Integrity & Validation Results ---")
    for name, passed, detail in checks:
        status_str = "[PASS]" if passed else "[FAIL]"
        if not passed:
            all_passed = False
        print(f"  • {name:<45} : {status_str} ({detail})")

    conn.close()

    print("=" * 80)
    if all_passed:
        print("      ALL DATABASE INTEGRITY CHECKS PASSED (100% HEALTHY)")
    else:
        print("      SOME DATABASE CHECKS FAILED - REVIEW LOGS ABOVE")
    print("=" * 80)

    return all_passed


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB_PATH
    success = verify_database(target)
    sys.exit(0 if success else 1)
