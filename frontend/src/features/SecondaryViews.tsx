import { useTranslation } from "../lib/locale";
﻿import { useState } from 'react';
import { AuditEvent, ExceptionItem, PolicyPack } from '../types/contracts';

export function AuditView({ events }: { events: AuditEvent[] }) {
  const { lang, tr } = useTranslation();
  const formatDate = new Intl.DateTimeFormat(lang, {
    dateStyle: 'medium', timeStyle: 'medium', timeZone: 'UTC',
  });
  const exportCsv = () => {
    const header = 'id,trace_id,actor_type,actor_name,action,entity_ref,before,after,ts\n';
    const rows = events
      .map((e) =>
        [e.id, e.trace_id, e.actor_type, e.actor_name, e.action, e.entity_ref, e.before_summary, e.after_summary, e.ts]
          .map((v) => `"${String(v).replace(/"/g, '""')}"`)
          .join(',')
      )
      .join('\n');
    const blob = new Blob([header + rows], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'resolva-audit-trail.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="panel-card">
      <div className="toolbar">
        <div>
          <strong>{tr("Immutable Append-Only Audit Trail")}</strong>
          <p className="muted small" style={{ margin: 0 }}>{tr("Every detection, AI draft, validator gate, and manager decision is logged with a trace ID.")}</p>
        </div>
        <button type="button" className="btn-secondary" onClick={exportCsv}>{tr("Export CSV")}</button>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{tr("Timestamp")}</th>
              <th>{tr("Trace ID")}</th>
              <th>{tr("Actor")}</th>
              <th>{tr("Action")}</th>
              <th>{tr("Entity")}</th>
              <th>{tr("Before → After")}</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.id}>
                <td className="small" title={e.ts}>
                  {Number.isFinite(Date.parse(e.ts)) ? (
                    <time dateTime={e.ts}>{formatDate.format(new Date(e.ts))} UTC</time>
                  ) : e.ts}
                </td>
                <td className="mono small">{e.trace_id}</td>
                <td>
                  <span className={e.actor_type === 'ai' ? 'badge-ai' : 'badge-neutral'}>{e.actor_name.replace(/^(RulesEngine|ProposalPipeline|ValidatorGate)\b/, tr)}</span>
                </td>
                <td className="small" title={e.action}><strong>{tr(e.action)}</strong></td>
                <td className="mono small">{e.entity_ref}</td>
                <td className="small">
                  {e.before_summary && <span className="muted">{tr(e.before_summary)}</span>}
                  {e.before_summary && e.after_summary && ' → '}
                  {e.after_summary && <strong>{tr(e.after_summary)}</strong>}
                  {!e.before_summary && !e.after_summary && tr('No change recorded')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function KioskView({ onSimulatePunch }: { onSimulatePunch: (newExc: ExceptionItem) => void }) {
  const { tr } = useTranslation();
  const [empId, setEmpId] = useState('EMP-BLR-07');
  const [empName, setEmpName] = useState('Meera Krishnan');
  const [punchTime, setPunchTime] = useState('09:05');
  const [editedNote, setNote] = useState<string>();
  const note = editedNote ?? tr('Clocked in at Bengaluru store kiosk; forgot evening out-punch.');

  const handleIngest = (e: React.FormEvent) => {
    e.preventDefault();
    const id = `EXC-${Math.floor(106 + Math.random() * 890)}`;
    const newExc: ExceptionItem = {
      id,
      code: 'MISSING_PUNCH',
      severity: 'problem',
      employee_id: empId,
      employee_name: empName,
      job: 'Cashier',
      location: 'Bengaluru (BLR-01)',
      timezone: 'IST (UTC+05:30)',
      policy_pack_id: 'IN-KA@2025.1',
      work_date: '2026-11-17',
      status: 'proposed',
      evidence_version: 1,
      summary: `Live kiosk clock-in at ${punchTime} IST without matching clock-out punch.`,
      employee_note: note,
      schedule: {
        id: 'SHD-912',
        employee_id: empId,
        start: '2026-11-17T09:00:00+05:30',
        end: '2026-11-17T18:00:00+05:30',
        planned_break_min: 60,
        location: 'Bengaluru (BLR-01)',
        job: 'Cashier',
      },
      punches: [
        {
          id: `PNC-${Math.floor(9200 + Math.random() * 700)}`,
          employee_id: empId,
          ts: `2026-11-17T${punchTime}:00+05:30`,
          type: 'in',
          source: 'kiosk',
          device_id: 'KIOSK-BLR-01',
        },
      ],
      before_hours: { regular_hours: '0.00 h', overtime_hours: '0.00 h', pay_status: 'Blocked (unpaired in-punch)' },
      after_hours: { regular_hours: '8.92 h', overtime_hours: '0.00 h', pay_status: 'Payable (Regular)' },
      proposal: {
        id: `PRP-${Math.floor(600 + Math.random() * 300)}`,
        exception_id: id,
        decision: 'propose',
        actions: [{ type: 'add_punch', new_ts: '2026-11-17T18:00:00+05:30', note: 'Infer scheduled shift end 18:00 IST.' }],
        rationale: `Detected unpaired clock-in at ${punchTime} IST on scheduled 09:00–18:00 IST shift. Proposed 18:00 IST out-punch passes all 6 deterministic rules.`,
        citations: [{ chunk_id: 'IN-KA@2025.1#sec-4.2', quote: 'Missing out-punches may be inferred within ±30 minutes of scheduled shift end.' }],
        confidence: 0.91,
        missing_information: [],
        model_id: 'qwen2.5-7b-instruct',
        prompt_hash: 'sha256:9f82c1a4',
        evidence_version: 1,
        validator_passed: true,
        rule_outcomes: [
          { rule: 'MISSING_PUNCH', passed: true, detail: 'Paired with 18:00 IST proposed out-punch.' },
          { rule: 'OVERLAPPING_SHIFT', passed: true, detail: 'No overlap.' },
          { rule: 'MEAL_BREAK_BREACH', passed: true, detail: 'Within policy.' },
          { rule: 'OVERTIME_RISK', passed: true, detail: 'Within 9h daily limit.' },
          { rule: 'SPREAD_OVER_BREACH', passed: true, detail: 'Within 12h spread-over.' },
          { rule: 'SCHEDULE_DEVIATION', passed: true, detail: 'Within 7 min tolerance.' },
        ],
      },
    };
    onSimulatePunch(newExc);
  };

  return (
    <div className="panel-card" style={{ maxWidth: 640, padding: 20 }}>
      <h2 style={{ marginTop: 0 }}>{tr("Kiosk Punch Simulator (Live Event Demo)")}</h2>
      <p className="muted">{tr("Simulates a raw immutable punch event entering the deterministic rules detector and routing an AI-drafted proposal into the Manager Inbox.")}</p>
      <form onSubmit={handleIngest} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <label className="field-label">{tr("Employee ID:")}<input className="input-field mono" value={empId} onChange={(e) => setEmpId(e.target.value)} required />
        </label>
        <label className="field-label">{tr("Employee Name:")}<input className="input-field" value={empName} onChange={(e) => setEmpName(e.target.value)} required />
        </label>
        <label className="field-label">{tr("Clock-In Time (IST):")}<input type="time" className="input-field mono" value={punchTime} onChange={(e) => setPunchTime(e.target.value)} required />
        </label>
        <label className="field-label">{tr("Employee Note (Untrusted Evidence):")}<input className="input-field" value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        <button type="submit" className="btn-primary">{tr("Post Raw Punch & Trigger Detection")}</button>
      </form>
    </div>
  );
}

export function PolicySettingsView({
  policies,
  aiEnabled,
  onToggleAi,
  confidenceThreshold,
  onChangeThreshold,
}: {
  policies: PolicyPack[];
  aiEnabled: boolean;
  onToggleAi: (v: boolean) => void;
  confidenceThreshold: number;
  onChangeThreshold: (v: number) => void;
}) {
  const { tr } = useTranslation();
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="panel-card" style={{ padding: 18 }}>
        <h3 style={{ marginTop: 0 }}>{tr("Harness Guardrails & Kill-Switch")}</h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24, alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
            <input type="checkbox" checked={aiEnabled} onChange={(e) => onToggleAi(e.target.checked)} />{tr("AI Proposal Pipeline Enabled (Uncheck for Rules-Only Fallback Mode)")}</label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>{tr("Confidence Gate Threshold:")}<input
              type="range"
              min="0.50"
              max="0.95"
              step="0.05"
              value={confidenceThreshold}
              onChange={(e) => onChangeThreshold(Number(e.target.value))}
            />
            <span className="mono">{Math.round(confidenceThreshold * 100)}%</span>
          </label>
        </div>
      </div>

      <div className="panel-card">
        <div className="toolbar">
          <strong>{tr("Versioned Jurisdiction Policy Packs (Configuration, Not Code)")}</strong>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{tr("Pack ID & Version")}</th>
                <th>{tr("Jurisdiction")}</th>
                <th>{tr("Daily / Weekly")}</th>
                <th>{tr("OT Rate & Cap")}</th>
                <th>{tr("Rest Break")}</th>
                <th>{tr("Max Spread-Over")}</th>
              </tr>
            </thead>
            <tbody>
              {policies.map((p) => (
                <tr key={`${p.id}@${p.version}`}>
                  <td className="mono"><strong>{p.id}@{p.version}</strong></td>
                  <td>{tr(p.jurisdiction)}</td>
                  <td>{p.daily_regular_hours}{tr(" hours")} / {p.weekly_regular_hours}{tr(" hours")}</td>
                  <td>{p.overtime_rate}× ({p.quarterly_ot_cap ? `${p.quarterly_ot_cap}${tr(" hours per quarter")}` : tr("no cap")})</td>
                  <td>{p.rest_minutes}{tr(" min after ")}{p.rest_after_hours}{tr(" hours")}</td>
                  <td>{p.max_spread_hours ? `${p.max_spread_hours}${tr(" hours")}` : tr('N/A')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

const SAMPLE_CSV = `employee_id,employee_name,work_date,in_time,out_time,location
EMP-BLR-11,Nandini Rao,2026-11-17,09:00,,Bengaluru (BLR-01)
EMP-BLR-12,Karthik Hegde,2026-11-17,09:15,18:10,Bengaluru (BLR-02)
,Unknown Worker,2026-11-17,09:00,18:00,Bengaluru (BLR-01)
EMP-AUS-09,Hannah Brooks,11/17/2026,08:00,17:00,Austin (AUS-01)`;

export function ImportPreviewView({ onImportValid }: { onImportValid: (items: ExceptionItem[]) => void }) {
  const { tr } = useTranslation();
  const [csvInput, setCsvInput] = useState(SAMPLE_CSV);
  const [rows, setRows] = useState<import('../types/contracts').ImportRow[]>(() =>
    []
  );

  // Lazy parse on render/button click
  const parsedRows = rows.length > 0 ? rows : (() => {
    const lines = csvInput.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    if (lines.length <= 1) return [];
    return lines.slice(1).map((line, idx) => {
      const [employee_id = '', employee_name = '', work_date = '', in_time = '', out_time = '', location = ''] = line.split(',').map((c) => c.trim());
      const row_num = idx + 2;
      if (!employee_id || !employee_name) return { row_num, employee_id, employee_name, work_date, in_time, out_time, location, valid: false, error: 'Missing employee_id or employee_name.' };
      if (!/^\d{4}-\d{2}-\d{2}$/.test(work_date)) return { row_num, employee_id, employee_name, work_date, in_time, out_time, location, valid: false, error: 'Invalid work_date (expected YYYY-MM-DD).' };
      if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(in_time)) return { row_num, employee_id, employee_name, work_date, in_time, out_time, location, valid: false, error: 'Invalid in_time (expected HH:MM).' };
      return { row_num, employee_id, employee_name, work_date, in_time, out_time, location: location || 'Bengaluru (BLR-01)', valid: true };
    });
  })();

  const validMissingPunches = parsedRows.filter((r) => r.valid && !r.out_time);

  const handleImport = () => {
    const created: ExceptionItem[] = validMissingPunches.map((r, i) => ({
      id: `EXC-${210 + i}`,
      code: 'MISSING_PUNCH',
      severity: 'problem',
      employee_id: r.employee_id,
      employee_name: r.employee_name,
      job: 'Associate',
      location: r.location,
      timezone: r.location.includes('Austin') ? 'CST (UTC-06:00)' : 'IST (UTC+05:30)',
      policy_pack_id: r.location.includes('Austin') ? 'US-FED+CA@2025.1' : 'IN-KA@2025.1',
      work_date: r.work_date,
      status: 'proposed',
      evidence_version: 1,
      summary: `Imported shift ${r.in_time} missing out-punch.`,
      punches: [
        { id: `PNC-IMP-${i}`, employee_id: r.employee_id, ts: `${r.work_date}T${r.in_time}:00+05:30`, type: 'in', source: 'badge', device_id: 'CSV-IMPORT' },
      ],
      before_hours: { regular_hours: '0.00 h', overtime_hours: '0.00 h', pay_status: 'Blocked (missing out-punch)' },
      after_hours: { regular_hours: '8.00 h', overtime_hours: '0.00 h', pay_status: 'Payable (Regular)' },
      proposal: {
        id: `PRP-IMP-${i}`,
        exception_id: `EXC-${210 + i}`,
        decision: 'propose',
        actions: [{ type: 'add_punch', new_ts: `${r.work_date}T18:00:00+05:30`, note: 'Inferred scheduled end 18:00.' }],
        rationale: 'Imported CSV shift had unpaired clock-in; proposed scheduled end timestamp.',
        citations: [{ chunk_id: 'IN-KA@2025.1#sec-4.2', quote: 'Missing out-punches may be inferred within ±30 minutes of scheduled shift end.' }],
        confidence: 0.89,
        missing_information: [],
        model_id: 'qwen2.5-7b-instruct',
        prompt_hash: 'sha256:9f82c1a4',
        evidence_version: 1,
        validator_passed: true,
        rule_outcomes: [{ rule: 'MISSING_PUNCH', passed: true, detail: 'Paired with 18:00 out-punch.' }],
      },
    }));
    onImportValid(created);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="panel-card" style={{ padding: 18 }}>
        <h2 style={{ marginTop: 0 }}>{tr("Schedule & Punch Import Preview (FE-04)")}</h2>
        <p className="muted small">{tr("Validates CSV/JSON rows before ingestion. Invalid rows are flagged and blocked; valid unpaired rows route to the Exception Inbox.")}</p>
        <textarea className="input-field code-editor mono"
          rows={6}
          style={{ width: '100%' }}
          value={csvInput}
          onChange={(e) => {
            setCsvInput(e.target.value);
            setRows([]);
          }}
        />
        <div className="button-row" style={{ marginTop: 12 }}>
          <button type="button" className="btn-primary" disabled={validMissingPunches.length === 0} onClick={handleImport}>{tr("Import Valid Exception Rows to Inbox (")}{validMissingPunches.length})
          </button>
        </div>
      </div>

      <div className="panel-card">
        <div className="toolbar">
          <strong>{tr("Row-Level Validation Preview (")}{parsedRows.filter((r) => r.valid).length}{" " + tr("Valid /") + " "}{parsedRows.filter((r) => !r.valid).length}{" " + tr("Invalid)") + ""}</strong>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{tr("Row")}</th>
                <th>{tr("Status")}</th>
                <th>{tr("Employee")}</th>
                <th>{tr("Work Date & Punches")}</th>
                <th>{tr("Validation Detail")}</th>
              </tr>
            </thead>
            <tbody>
              {parsedRows.map((r) => (
                <tr key={r.row_num}>
                  <td className="mono small">#{r.row_num}</td>
                  <td>
                    <span className={r.valid ? 'badge-pass' : 'badge-escalated'}>
                      {tr(r.valid ? 'VALID' : 'INVALID ROW')}
                    </span>
                  </td>
                  <td className="small"><strong>{r.employee_name || '—'}</strong> ({r.employee_id || tr('Missing ID')})</td>
                  <td className="small">{r.work_date} | {r.in_time || tr('Not recorded')} → {r.out_time || tr('Not recorded')}</td>
                  <td className="small">{r.valid ? tr('Ready for ingestion') : <span style={{ color: '#dc2626' }}>{tr(r.error ?? "")}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

