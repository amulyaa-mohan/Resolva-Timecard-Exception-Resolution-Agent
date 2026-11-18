"""
Seed Data Script for Resolva / ShiftSense – Timecard Exception Resolution Agent.

Populates the SQLite database (`shiftsense.db`) with realistic, deterministic demo data:
1. One global organization: ShiftSense Global Inc.
2. Two operational locations:
   - Bengaluru, India (Asia/Kolkata)
   - Austin, USA (America/Chicago)
3. Two policy rule packs:
   - IN-KA (Karnataka Shops & Commercial Establishments Act)
   - US-FED (US Federal FLSA Standard Policy)
4. 15 employees distributed across locations with multi-tier managerial hierarchies
   and both hourly and salaried pay types.
5. Two weeks of scheduled work shifts (Monday 2026-11-02 to Friday 2026-11-13).
6. Realistic raw clock punches containing standard punch sequences alongside
   targeted realistic anomalies (missed OUT, missed IN, short meal breaks,
   unauthorized overtime, early departures, double badge taps, tardiness)
   for demonstrating automated exception detection.

The script is strictly idempotent: re-running it will not generate duplicate records.
"""

import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Ensure 'backend' directory is on sys.path for direct script execution
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sqlmodel import Session, select
from database import create_db_and_tables, engine
from app.models import (
    Employee,
    Location,
    Organization,
    PayType,
    PolicyClause,
    PolicyPack,
    Punch,
    PunchSource,
    PunchType,
    Shift,
)


def seed_database(session: Session) -> Dict[str, int]:
    """
    Inserts realistic demo data into SQLite database in an idempotent manner.
    Returns a dictionary summarizing records created during this run.
    """
    stats = {
        "organizations_created": 0,
        "locations_created": 0,
        "policy_packs_created": 0,
        "policy_clauses_created": 0,
        "employees_created": 0,
        "shifts_created": 0,
        "punches_created": 0,
    }

    # --------------------------------------------------------------------------
    # 1. Organization
    # --------------------------------------------------------------------------
    org = session.exec(
        select(Organization).where(Organization.code == "CORP-SHIFTSENSE")
    ).first()
    if not org:
        org = Organization(
            name="ShiftSense Global Inc.",
            code="CORP-SHIFTSENSE",
        )
        session.add(org)
        session.commit()
        session.refresh(org)
        stats["organizations_created"] += 1
        print(f"[SEED] Created Organization: {org.name} ({org.code})")
    else:
        print(f"[SEED] Using existing Organization: {org.name} ({org.code})")

    # --------------------------------------------------------------------------
    # 2. Locations (Bengaluru, India and Austin, USA)
    # --------------------------------------------------------------------------
    blr = session.exec(
        select(Location).where(
            Location.organization_id == org.id, Location.city == "Bengaluru"
        )
    ).first()
    if not blr:
        blr = Location(
            name="Bengaluru Development Center",
            city="Bengaluru",
            country="India",
            timezone="Asia/Kolkata",
            organization_id=org.id,
        )
        session.add(blr)
        stats["locations_created"] += 1

    atx = session.exec(
        select(Location).where(
            Location.organization_id == org.id, Location.city == "Austin"
        )
    ).first()
    if not atx:
        atx = Location(
            name="Austin Operations Hub",
            city="Austin",
            country="USA",
            timezone="America/Chicago",
            organization_id=org.id,
        )
        session.add(atx)
        stats["locations_created"] += 1

    session.commit()
    session.refresh(blr)
    session.refresh(atx)
    print(f"[SEED] Locations: Bengaluru (ID: {blr.id}), Austin (ID: {atx.id})")

    # --------------------------------------------------------------------------
    # 3. Policy Packs (IN-KA and US-FED)
    # --------------------------------------------------------------------------
    pack_in = session.exec(
        select(PolicyPack).where(
            PolicyPack.code == "IN-KA", PolicyPack.version == "1.0.0"
        )
    ).first()
    if not pack_in:
        pack_in = PolicyPack(
            code="IN-KA",
            name="Karnataka Shops & Commercial Establishments Act",
            version="1.0.0",
            jurisdiction="Karnataka, India",
            is_active=True,
        )
        session.add(pack_in)
        stats["policy_packs_created"] += 1

    pack_us = session.exec(
        select(PolicyPack).where(
            PolicyPack.code == "US-FED", PolicyPack.version == "1.0.0"
        )
    ).first()
    if not pack_us:
        pack_us = PolicyPack(
            code="US-FED",
            name="US Federal Fair Labor Standards Act (FLSA)",
            version="1.0.0",
            jurisdiction="United States",
            is_active=True,
        )
        session.add(pack_us)
        stats["policy_packs_created"] += 1

    session.commit()
    session.refresh(pack_in)
    session.refresh(pack_us)
    print(f"[SEED] Policy Packs: {pack_in.code} (ID: {pack_in.id}), {pack_us.code} (ID: {pack_us.id})")

    # --------------------------------------------------------------------------
    # 3b. Policy Clauses (IN-KA and US-FED)
    # --------------------------------------------------------------------------
    policy_clauses_blueprint = [
        # === IN-KA Policy Clauses (Karnataka, India) ===
        {
            "policy_pack_id": pack_in.id,
            "clause_id": "IN-KA-DUPLICATE-PUNCH-01",
            "section": "Attendance Recording & Duplicate Badge Policy",
            "content": "When consecutive identical punches (such as multiple IN or OUT taps) are recorded within a short threshold (under 5 minutes), the supervisor should verify if the action was an accidental double badge tap. The earlier punch timestamp is retained as the authoritative event, and duplicate taps are dismissed after supervisor review.",
            "source_doc": "Karnataka Operations Policy Handbook (Demo)",
        },
        {
            "policy_pack_id": pack_in.id,
            "clause_id": "IN-KA-MISSED-IN-PUNCH-01",
            "section": "Shift Inception & Missing Clock-In Correction",
            "content": "If an employee performs work activities or records subsequent break/out punches without an initial clock-in punch, an exception is flagged. The supervisor must review secondary records (badge logs or scheduled shift start) and propose an inferred clock-in time aligned with the scheduled shift inception.",
            "source_doc": "Karnataka Operations Policy Handbook (Demo)",
        },
        {
            "policy_pack_id": pack_in.id,
            "clause_id": "IN-KA-MISSED-OUT-PUNCH-01",
            "section": "Shift Conclusion & Missing Clock-Out Resolution",
            "content": "Employees who clock in but fail to record an end-of-shift clock-out punch trigger a missing punch exception. The supervisor or automated resolution agent should infer the conclusion time using the scheduled shift end or the last verified activity, subject to manager confirmation.",
            "source_doc": "Karnataka Operations Policy Handbook (Demo)",
        },
        {
            "policy_pack_id": pack_in.id,
            "clause_id": "IN-KA-MEAL-BREAK-01",
            "section": "Mandatory Rest Interval & Break Requirements",
            "content": "Employees working a standard shift exceeding five continuous hours must be provided an uninterrupted rest interval of at least 60 minutes. Any recorded break falling short of the required interval by more than 5 minutes constitutes a break violation requiring supervisory acknowledgment.",
            "source_doc": "Karnataka Commercial Establishments Guidelines (Demo)",
        },
        {
            "policy_pack_id": pack_in.id,
            "clause_id": "IN-KA-LATE-ARRIVAL-01",
            "section": "Shift Punctuality & Grace Window Policy",
            "content": "A standard grace tolerance of up to 7 minutes is permitted after the scheduled shift start time. Clock-in events occurring beyond this 7-minute threshold are classified as late arrivals. For delays over 30 minutes, formal manager review or partial leave deduction may be evaluated.",
            "source_doc": "Karnataka Operations Policy Handbook (Demo)",
        },
        {
            "policy_pack_id": pack_in.id,
            "clause_id": "IN-KA-EARLY-DEPARTURE-01",
            "section": "Shift Early Departure & Partial Day Policy",
            "content": "Employees clocking out earlier than scheduled shift end by more than 30 minutes trigger an early departure exception. The supervisor must review whether the early departure was pre-approved or requires reconciliation against partial-day leave balances.",
            "source_doc": "Karnataka Operations Policy Handbook (Demo)",
        },
        {
            "policy_pack_id": pack_in.id,
            "clause_id": "IN-KA-UNAUTHORIZED-OVERTIME-01",
            "section": "Overtime Authorization, Limits & Premium Compensation",
            "content": "Working hours exceeding 9 hours daily or 48 hours weekly require prior management authorization and are compensable at twice the regular rate of wages (2.0x). Overtime hours exceeding scheduled shift end by more than 30 minutes must be reviewed to verify whether operational requirements justified the overtime.",
            "source_doc": "Karnataka Commercial Establishments Guidelines (Demo)",
        },

        # === US-FED Policy Clauses (United States Federal with Overlays) ===
        {
            "policy_pack_id": pack_us.id,
            "clause_id": "US-FED-DUPLICATE-PUNCH-01",
            "section": "Timekeeping Double Badge Tap & Error Filtering",
            "content": "Consecutive identical punch entries registered within 5 minutes of each other represent electronic timeclock double taps. The system retains the primary punch timestamp and flags secondary consecutive records for automated consolidation or supervisor dismissal.",
            "source_doc": "US Federal & State Operations Handbook (Demo)",
        },
        {
            "policy_pack_id": pack_us.id,
            "clause_id": "US-FED-MISSED-IN-PUNCH-01",
            "section": "Incomplete Timecard & Missing Clock-In Policy",
            "content": "When shift activity or clock-out timestamps exist without a corresponding opening clock-in punch, timecard completeness standards require reconciliation. The supervisor must corroborate arrival time using scheduled shift start or physical access logs to complete the payroll record.",
            "source_doc": "US Federal Wage & Hour Guidelines (Demo)",
        },
        {
            "policy_pack_id": pack_us.id,
            "clause_id": "US-FED-MISSED-OUT-PUNCH-01",
            "section": "Incomplete Timecard & Missing Clock-Out Policy",
            "content": "An open shift lacking a concluding punch must be reconciled prior to payroll finalization. Supervisors should review the scheduled shift duration and employee attestation to establish an approved shift conclusion timestamp.",
            "source_doc": "US Federal Wage & Hour Guidelines (Demo)",
        },
        {
            "policy_pack_id": pack_us.id,
            "clause_id": "US-FED-MEAL-BREAK-01",
            "section": "Meal Period & Rest Break Compliance (California Overlay)",
            "content": "Non-exempt employees scheduled for shifts exceeding 5 hours must be provided a timely, duty-free meal break of at least 30 minutes before the end of the fifth hour. Recorded breaks shorter than 30 minutes or delayed past 5 hours trigger a meal break violation and supervisory review for premium pay eligibility.",
            "source_doc": "California Operations Handbook Overlay (Demo)",
        },
        {
            "policy_pack_id": pack_us.id,
            "clause_id": "US-FED-LATE-ARRIVAL-01",
            "section": "Attendance Punctuality & Rounding Tolerance",
            "content": "In accordance with standard 7-minute rounding guidelines, arrival punches up to 7 minutes after the scheduled start are accommodated within normal attendance tolerances. Clock-in timestamps exceeding this threshold are flagged as tardiness for supervisory review.",
            "source_doc": "US Federal Wage & Hour Guidelines (Demo)",
        },
        {
            "policy_pack_id": pack_us.id,
            "clause_id": "US-FED-EARLY-DEPARTURE-01",
            "section": "Early Departure & Unfulfilled Scheduled Hours",
            "content": "Clock-out events recorded more than 30 minutes prior to scheduled shift conclusion are identified as early departures. Supervisors must verify whether the early release was manager-directed or if unpaid partial-shift reconciliation applies.",
            "source_doc": "US Federal & State Operations Handbook (Demo)",
        },
        {
            "policy_pack_id": pack_us.id,
            "clause_id": "US-FED-UNAUTHORIZED-OVERTIME-01",
            "section": "Overtime Authorization & 40-Hour Workweek Standard",
            "content": "All hours worked by non-exempt employees in excess of 40 hours in a workweek must be compensated at not less than 1.5 times the regular rate. Unapproved working time exceeding shift end by more than 30 minutes must be reviewed to ensure lawful payment while addressing timecard authorization compliance.",
            "source_doc": "US Federal Wage & Hour Guidelines (Demo)",
        },
    ]

    for clause_data in policy_clauses_blueprint:
        existing_clause = session.exec(
            select(PolicyClause).where(
                PolicyClause.policy_pack_id == clause_data["policy_pack_id"],
                PolicyClause.clause_id == clause_data["clause_id"],
            )
        ).first()
        if not existing_clause:
            clause = PolicyClause(**clause_data)
            session.add(clause)
            stats["policy_clauses_created"] += 1

    session.commit()
    print(f"[SEED] Policy Clauses: Processed {len(policy_clauses_blueprint)} demo clauses across IN-KA and US-FED.")

    # --------------------------------------------------------------------------
    # 4. Employees (15 total: distributed across Bengaluru and Austin)
    # --------------------------------------------------------------------------
    employees_blueprint = [
        # --- Bengaluru Team (8 employees) ---
        {
            "key": "priya",
            "name": "Priya Sharma",
            "loc_id": blr.id,
            "job": "Director of Engineering",
            "pay_type": PayType.SALARIED,
            "pack_id": pack_in.id,
            "mgr_key": None,
        },
        {
            "key": "deepa",
            "name": "Deepa Rao",
            "loc_id": blr.id,
            "job": "Technical Lead",
            "pay_type": PayType.SALARIED,
            "pack_id": pack_in.id,
            "mgr_key": "priya",
        },
        {
            "key": "kavita",
            "name": "Kavita Reddy",
            "loc_id": blr.id,
            "job": "Support Operations Lead",
            "pay_type": PayType.HOURLY,
            "pack_id": pack_in.id,
            "mgr_key": "priya",
        },
        {
            "key": "arjun",
            "name": "Arjun Patel",
            "loc_id": blr.id,
            "job": "Senior Software Engineer",
            "pay_type": PayType.SALARIED,
            "pack_id": pack_in.id,
            "mgr_key": "priya",
        },
        {
            "key": "rohan",
            "name": "Rohan Nair",
            "loc_id": blr.id,
            "job": "Customer Support Specialist",
            "pay_type": PayType.HOURLY,
            "pack_id": pack_in.id,
            "mgr_key": "kavita",
        },
        {
            "key": "sneha",
            "name": "Sneha Kulkarni",
            "loc_id": blr.id,
            "job": "Customer Support Specialist",
            "pay_type": PayType.HOURLY,
            "pack_id": pack_in.id,
            "mgr_key": "kavita",
        },
        {
            "key": "vikram",
            "name": "Vikram Joshi",
            "loc_id": blr.id,
            "job": "Data Operations Associate",
            "pay_type": PayType.HOURLY,
            "pack_id": pack_in.id,
            "mgr_key": "kavita",
        },
        {
            "key": "ananya",
            "name": "Ananya Deshmukh",
            "loc_id": blr.id,
            "job": "QA Automation Engineer",
            "pay_type": PayType.HOURLY,
            "pack_id": pack_in.id,
            "mgr_key": "deepa",
        },
        # --- Austin Team (7 employees) ---
        {
            "key": "marcus",
            "name": "Marcus Vance",
            "loc_id": atx.id,
            "job": "Director of Operations",
            "pay_type": PayType.SALARIED,
            "pack_id": pack_us.id,
            "mgr_key": None,
        },
        {
            "key": "sarah",
            "name": "Sarah Jenkins",
            "loc_id": atx.id,
            "job": "Logistics Operations Supervisor",
            "pay_type": PayType.SALARIED,
            "pack_id": pack_us.id,
            "mgr_key": "marcus",
        },
        {
            "key": "david",
            "name": "David Miller",
            "loc_id": atx.id,
            "job": "Warehouse Shift Supervisor",
            "pay_type": PayType.HOURLY,
            "pack_id": pack_us.id,
            "mgr_key": "sarah",
        },
        {
            "key": "emily",
            "name": "Emily Davis",
            "loc_id": atx.id,
            "job": "Inventory Specialist",
            "pay_type": PayType.HOURLY,
            "pack_id": pack_us.id,
            "mgr_key": "david",
        },
        {
            "key": "james",
            "name": "James Wilson",
            "loc_id": atx.id,
            "job": "Logistics Specialist",
            "pay_type": PayType.HOURLY,
            "pack_id": pack_us.id,
            "mgr_key": "david",
        },
        {
            "key": "carlos",
            "name": "Carlos Rodriguez",
            "loc_id": atx.id,
            "job": "Dispatch Coordinator",
            "pay_type": PayType.HOURLY,
            "pack_id": pack_us.id,
            "mgr_key": "david",
        },
        {
            "key": "chloe",
            "name": "Chloe Taylor",
            "loc_id": atx.id,
            "job": "Fulfillment Associate",
            "pay_type": PayType.HOURLY,
            "pack_id": pack_us.id,
            "mgr_key": "david",
        },
    ]

    emp_lookup: Dict[str, Employee] = {}

    # Step 4a: Create employee records
    for eb in employees_blueprint:
        emp = session.exec(select(Employee).where(Employee.name == eb["name"])).first()
        if not emp:
            emp = Employee(
                name=eb["name"],
                location_id=eb["loc_id"],
                job=eb["job"],
                pay_type=eb["pay_type"],
                policy_pack_id=eb["pack_id"],
            )
            session.add(emp)
            session.commit()
            session.refresh(emp)
            stats["employees_created"] += 1
        emp_lookup[eb["key"]] = emp

    # Step 4b: Wire managerial hierarchy
    for eb in employees_blueprint:
        mgr_key = eb["mgr_key"]
        emp = emp_lookup[eb["key"]]
        if mgr_key and mgr_key in emp_lookup:
            desired_mgr_id = emp_lookup[mgr_key].id
            if emp.manager_id != desired_mgr_id:
                emp.manager_id = desired_mgr_id
                session.add(emp)
    session.commit()
    print(f"[SEED] Employees mapped: {len(emp_lookup)} (Hourly: 10, Salaried: 5)")

    # --------------------------------------------------------------------------
    # 5. Scheduled Shifts (Two Weeks: Monday 2026-11-02 to Friday 2026-11-13)
    # --------------------------------------------------------------------------
    # Generate 10 business days across the two-week reference window
    base_date = date(2026, 11, 2)
    work_days: List[date] = []
    curr = base_date
    while len(work_days) < 10:
        if curr.weekday() < 5:  # Monday through Friday
            work_days.append(curr)
        curr += timedelta(days=1)

    # Tracked employees scheduled for operational shifts (hourly staff + shift supervisors)
    tracked_staff_keys = [
        "kavita", "rohan", "sneha", "vikram", "ananya",
        "david", "emily", "james", "carlos", "chloe",
    ]

    for day_idx, work_day in enumerate(work_days):
        for key in tracked_staff_keys:
            emp = emp_lookup[key]
            is_blr = (emp.location_id == blr.id)

            if is_blr:
                # Bengaluru standard workday: 09:00 - 18:00 (Break: 60 mins)
                shift_start = datetime.combine(work_day, time(9, 0))
                shift_end = datetime.combine(work_day, time(18, 0))
                planned_break = 60
                break_start_time = time(13, 0)
                device_name = "KIOSK-BLR-01"
            else:
                # Austin standard workday: 08:00 - 16:30 (Break: 30 mins)
                shift_start = datetime.combine(work_day, time(8, 0))
                shift_end = datetime.combine(work_day, time(16, 30))
                planned_break = 30
                break_start_time = time(12, 0)
                device_name = "KIOSK-ATX-02"

            # Check for existing scheduled shift
            existing_shift = session.exec(
                select(Shift).where(
                    Shift.employee_id == emp.id, Shift.start == shift_start
                )
            ).first()

            if not existing_shift:
                shift = Shift(
                    employee_id=emp.id,
                    start=shift_start,
                    end=shift_end,
                    planned_break_min=planned_break,
                )
                session.add(shift)
                stats["shifts_created"] += 1

            # ------------------------------------------------------------------
            # 6. Raw Timecard Punches with Targeted Inconsistencies
            # ------------------------------------------------------------------
            # Construct realistic punch events with specific anomaly injections
            day_punches: List[Tuple[datetime, PunchType, PunchSource]] = []

            # Anomaly 1: Sneha Kulkarni on Week 1 Wednesday (2026-11-04) -> Missed OUT punch
            if key == "sneha" and day_idx == 2:
                day_punches = [
                    (shift_start + timedelta(minutes=2), PunchType.IN, PunchSource.KIOSK),
                    (datetime.combine(work_day, break_start_time), PunchType.BREAK_START, PunchSource.KIOSK),
                    (datetime.combine(work_day, break_start_time) + timedelta(minutes=planned_break), PunchType.BREAK_END, PunchSource.KIOSK),
                    # Missing OUT punch!
                ]

            # Anomaly 2: James Wilson on Week 1 Thursday (2026-11-05) -> Missed IN punch
            elif key == "james" and day_idx == 3:
                day_punches = [
                    # Missing IN punch!
                    (datetime.combine(work_day, break_start_time), PunchType.BREAK_START, PunchSource.KIOSK),
                    (datetime.combine(work_day, break_start_time) + timedelta(minutes=planned_break), PunchType.BREAK_END, PunchSource.KIOSK),
                    (shift_end + timedelta(minutes=1), PunchType.OUT, PunchSource.KIOSK),
                ]

            # Anomaly 3: Carlos Rodriguez on Week 1 Tuesday (2026-11-03) -> Short Meal Break (10m instead of 30m)
            elif key == "carlos" and day_idx == 1:
                day_punches = [
                    (shift_start - timedelta(minutes=3), PunchType.IN, PunchSource.KIOSK),
                    (datetime.combine(work_day, time(12, 15)), PunchType.BREAK_START, PunchSource.KIOSK),
                    (datetime.combine(work_day, time(12, 25)), PunchType.BREAK_END, PunchSource.KIOSK),  # Only 10 min break!
                    (shift_end + timedelta(minutes=2), PunchType.OUT, PunchSource.KIOSK),
                ]

            # Anomaly 4: Emily Davis on Week 1 Friday (2026-11-06) -> Unauthorized Overtime (+2h 50m late out)
            elif key == "emily" and day_idx == 4:
                day_punches = [
                    (shift_start - timedelta(minutes=1), PunchType.IN, PunchSource.KIOSK),
                    (datetime.combine(work_day, break_start_time), PunchType.BREAK_START, PunchSource.KIOSK),
                    (datetime.combine(work_day, break_start_time) + timedelta(minutes=planned_break), PunchType.BREAK_END, PunchSource.KIOSK),
                    (datetime.combine(work_day, time(19, 20)), PunchType.OUT, PunchSource.KIOSK),  # Overtime out!
                ]

            # Anomaly 5: Rohan Nair on Week 2 Tuesday (2026-11-10) -> Early Departure (left mid-day at 13:30)
            elif key == "rohan" and day_idx == 6:
                day_punches = [
                    (shift_start + timedelta(minutes=4), PunchType.IN, PunchSource.MOBILE),
                    (datetime.combine(work_day, time(13, 30)), PunchType.OUT, PunchSource.MOBILE),  # Left early!
                ]

            # Anomaly 6: Chloe Taylor on Week 2 Thursday (2026-11-12) -> Double badge tap IN
            elif key == "chloe" and day_idx == 8:
                day_punches = [
                    (shift_start + timedelta(seconds=12), PunchType.IN, PunchSource.KIOSK),
                    (shift_start + timedelta(seconds=48), PunchType.IN, PunchSource.KIOSK),  # Duplicate IN!
                    (datetime.combine(work_day, break_start_time), PunchType.BREAK_START, PunchSource.KIOSK),
                    (datetime.combine(work_day, break_start_time) + timedelta(minutes=planned_break), PunchType.BREAK_END, PunchSource.KIOSK),
                    (shift_end + timedelta(minutes=2), PunchType.OUT, PunchSource.KIOSK),
                ]

            # Anomaly 7: Vikram Joshi on Week 2 Monday (2026-11-09) -> Severe Tardy (+1h 45m late IN)
            elif key == "vikram" and day_idx == 5:
                day_punches = [
                    (datetime.combine(work_day, time(10, 45)), PunchType.IN, PunchSource.WEB),  # 1h 45m late arrival!
                    (datetime.combine(work_day, break_start_time), PunchType.BREAK_START, PunchSource.WEB),
                    (datetime.combine(work_day, break_start_time) + timedelta(minutes=planned_break), PunchType.BREAK_END, PunchSource.WEB),
                    (shift_end + timedelta(minutes=3), PunchType.OUT, PunchSource.WEB),
                ]

            else:
                # Standard clean shift punch cycle (IN, BREAK_START, BREAK_END, OUT)
                punch_source = PunchSource.KIOSK if (day_idx % 3 != 0) else PunchSource.MOBILE
                # Natural minor variations (-2 to +3 minutes around shift boundaries)
                in_offset = (day_idx % 5) - 2
                out_offset = (day_idx % 4) + 1
                day_punches = [
                    (shift_start + timedelta(minutes=in_offset), PunchType.IN, punch_source),
                    (datetime.combine(work_day, break_start_time), PunchType.BREAK_START, punch_source),
                    (datetime.combine(work_day, break_start_time) + timedelta(minutes=planned_break), PunchType.BREAK_END, punch_source),
                    (shift_end + timedelta(minutes=out_offset), PunchType.OUT, punch_source),
                ]

            # Insert punches idempotently
            for punch_ts, punch_type, punch_source in day_punches:
                existing_punch = session.exec(
                    select(Punch).where(
                        Punch.employee_id == emp.id,
                        Punch.ts == punch_ts,
                        Punch.type == punch_type,
                    )
                ).first()

                if not existing_punch:
                    punch = Punch(
                        employee_id=emp.id,
                        ts=punch_ts,
                        type=punch_type,
                        source=punch_source,
                        device_id=device_name,
                    )
                    session.add(punch)
                    stats["punches_created"] += 1

    session.commit()
    return stats


def print_database_summary(session: Session) -> None:
    """
    Prints the total record counts for all key entities in the database.
    """
    org_count = len(session.exec(select(Organization)).all())
    loc_count = len(session.exec(select(Location)).all())
    pack_count = len(session.exec(select(PolicyPack)).all())
    clause_count = len(session.exec(select(PolicyClause)).all())
    emp_count = len(session.exec(select(Employee)).all())
    shift_count = len(session.exec(select(Shift)).all())
    punch_count = len(session.exec(select(Punch)).all())

    print("\n" + "=" * 60)
    print("           SHIFTSENSE DATABASE SUMMARY")
    print("=" * 60)
    print(f" Organizations : {org_count}")
    print(f" Locations     : {loc_count} (Bengaluru, Austin)")
    print(f" Policy Packs  : {pack_count} (IN-KA, US-FED)")
    print(f" Policy Clauses: {clause_count} (Demo attendance rules)")
    print(f" Employees     : {emp_count} (Hourly & Salaried with managers)")
    print(f" Shifts        : {shift_count} (2 weeks scheduled)")
    print(f" Punches       : {punch_count} (Raw timecard events with anomalies)")
    print("=" * 60)


def main() -> None:
    """
    Main entry point for running the seed script directly.
    """
    print("[INFO] Ensuring database tables are initialized...")
    create_db_and_tables()

    print("[INFO] Seeding database with realistic demo data...")
    with Session(engine) as session:
        stats = seed_database(session)
        print("\n[INFO] Seeding pass completed:")
        for k, v in stats.items():
            print(f"  • {k}: {v}")

        print_database_summary(session)


if __name__ == "__main__":
    main()
