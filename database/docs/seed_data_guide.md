# Resolva Seed Data Guide

This document describes the demonstration and testing dataset populated by `database/seeds/seed.py` into `shiftsense.db`.

---

## 1. Core Organizational Hierarchy

### Organization
- **ShiftSense Global Inc.** (`SHIFTSENSE-CORP`): Global enterprise organization hosting multi-regional workforce operations.

### Locations
1. **Bengaluru Tech Center** (`Asia/Kolkata`): Bengaluru, India.
2. **Austin Operations Hub** (`America/Chicago`): Austin, TX, USA.
3. **Chicago Distribution Center** (`America/Chicago`): Chicago, IL, USA.

---

## 2. Statutory Policy Rule Packs & Clauses

The database includes 4 jurisdictional policy packs containing 20 granular policy clauses covering all 7 supported timecard exception types:

### Policy Packs
- **`IN-KA`**: Karnataka Shops & Commercial Establishments Act, 1961 (version: `2026.1`).
- **`US-FED`**: US Fair Labor Standards Act (FLSA) 29 CFR Part 785 (version: `2026.1`).
- **`US-IL`**: Illinois One Day Rest in Seven Act (ODRISA) & Healthcare Staffing (version: `2026.1`).
- **`US-CA`**: California Division of Labor Standards Enforcement & IWC Wage Orders 4 & 5 (version: `2026.1`).

### Policy Clause Coverage Matrix

| Exception Code | Jurisdictions Covered | Key Statutory Articles |
|---|---|---|
| `DUPLICATE_PUNCH` | IN-KA, US-FED, US-IL | Rules on badge de-duplication within 5-minute threshold. |
| `MISSED_IN_PUNCH` | IN-KA, US-FED, US-IL | Shift-start default assumption subject to supervisor signoff. |
| `MISSED_OUT_PUNCH` | IN-KA, US-FED, US-IL | Scheduled shift-end default capping unverified span. |
| `MEAL_BREAK_VIOLATION` | IN-KA, US-FED, US-IL, US-CA | Mandatory 30-min break after 5 hours (20-min under IL ODRISA); 1.0h penalty premium under CA/FLSA. |
| `LATE_ARRIVAL` | IN-KA, US-FED, US-IL | Grace period rules (5-15 min) vs formal tardiness recording. |
| `EARLY_DEPARTURE` | IN-KA, US-FED, US-IL | Authorized early release vs partial shift absence deduction. |
| `UNAUTHORIZED_OVERTIME` | IN-KA, US-FED, US-IL, US-CA | Daily (>8h under CA) and weekly (>40h) overtime pay calculations at 1.5x/2.0x regular rate. |

---

## 3. Employee Roster & Hierarchy

The database models 24 employees with realistic reporting relationships and pay structures across four operating cohorts:

- **Executives & Managers**:
  - Sarah Chen (`MGR-1049`): VP of Workforce Management.
  - David Miller (`MGR-2050`): Site Director (Austin).
  - Rajesh Sharma (`MGR-3051`): Operations Manager (Bengaluru).
  - Priya Sharma: Director of Engineering (Bengaluru).
  - Marcus Vance: Director of Operations (Austin).
  - Dr. Sunita Sen: Chief Medical Officer (Chicago).
- **Clinical & Healthcare Staff (Chicago / US-IL)**:
  - Alex Rivera: Clinical Nurse Specialist (Hourly).
  - Elena Rostova: Staff Registered Nurse (Hourly).
  - Darius Washington: Patient Care Technician (Hourly).
- **Engineering & Operations Support (Bengaluru / IN-KA)**:
  - Deepa Rao: Technical Lead (Salaried).
  - Kavita Reddy: Support Operations Lead (Hourly).
  - Arjun Patel: Senior Software Engineer (Salaried).
  - Naveen Kumar: Senior Cloud Architect (Salaried).
  - Meera Krishnan: Operations Support Analyst (Hourly).
  - Rohan Nair, Sneha Kulkarni, Vikram Joshi, Ananya Deshmukh: Frontline Support & QA Specialists.
- **Logistics, Fulfillment & Compliance (Austin / US-FED & US-CA)**:
  - Sarah Jenkins: Logistics Operations Supervisor (Salaried).
  - Emily Davis, James Wilson, Carlos Rodriguez, Chloe Taylor: Fulfillment & Logistics Specialists (Hourly).
  - Zachary Adams: Materials Handling Specialist (Hourly).
  - Rachel Campbell: Quality Assurance Auditor (Hourly).
  - Brandon Lee: Regional Compliance Specialist (Salaried).

---

## 4. Work Shifts & Clock Punch Telemetry

### Shifts (126 Records)
Scheduled shifts spanning a complete two-week pay period (2026-11-02 through 2026-11-16) covering:
- Morning shifts (07:00 / 08:00 – 15:30 / 16:30 with planned break)
- Evening shifts (14:00 / 15:00 – 22:30 / 23:30 with planned break)
- Operational shifts (09:00 – 18:00 with planned 60-min break)

### Raw Punches (398 Records — Strictly Immutable)
The raw clock punch dataset includes 398 real-world hardware and mobile clock entries.
All 398 punch records are strictly immutable.

### Detected Exceptions (35 Records)
A realistic, diverse distribution of 35 timecard anomalies across all 7 supported categories:
- Missed IN Punches (4)
- Missed OUT Punches (6)
- Late Arrivals (5)
- Early Departures (4)
- Meal Break Violations (6)
- Unauthorized Overtime (6)
- Duplicate Badge Taps (4)
