import { useState } from 'react';
import { ApiError, commitImport, ImportKind, ImportPreviewResult, previewImport, sendKioskPunch } from '../lib/api';
import { AuditEvent, ExceptionItem, PolicyPack } from '../types/contracts';

/**
 * One CSV cell. Quoting alone does not stop a spreadsheet running a formula: a value that
 * starts with = + - @ (or a tab or carriage return) is executed when the file is opened, and
 * audit fields carry user-supplied text such as a manager's rejection reason. OWASP's rule is to
 * prefix such a value with an apostrophe so it is read as text.
 */
export function csvCell(value: unknown): string {
  let text = String(value ?? '');
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

export function AuditView({ events }: { events: AuditEvent[] }) {
  const exportCsv = () => {
    const header = 'id,trace_id,actor_type,actor_name,action,entity_ref,before,after,ts\n';
    const rows = events
      .map((e) =>
        [e.id, e.trace_id, e.actor_type, e.actor_name, e.action, e.entity_ref, e.before_summary, e.after_summary, e.ts]
          .map((v) => csvCell(v))
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
          <strong>Immutable Append-Only Audit Trail</strong>
          <p className="muted small" style={{ margin: 0 }}>
            Every detection, AI draft, validator gate, and manager decision is logged with a trace ID.
          </p>
        </div>
        <button type="button" className="btn-secondary" onClick={exportCsv}>
          Export CSV
        </button>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Trace ID</th>
              <th>Actor</th>
              <th>Action</th>
              <th>Entity</th>
              <th>Before → After</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.id}>
                <td className="mono small">{e.ts}</td>
                <td className="mono small">{e.trace_id}</td>
                <td>
                  <span className={e.actor_type === 'ai' ? 'badge-ai' : 'badge-neutral'}>{e.actor_name}</span>
                </td>
                <td className="mono small"><strong>{e.action}</strong></td>
                <td className="mono small">{e.entity_ref}</td>
                <td className="small">
                  <span className="muted">{e.before_summary}</span> → <strong>{e.after_summary}</strong>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function KioskView({
  employees,
  onPunchSent,
}: {
  employees: { id: string; name: string }[];
  onPunchSent: (message: string) => void;
}) {
  const [empId, setEmpId] = useState('');
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [punchTime, setPunchTime] = useState('09:05');
  const [kind, setKind] = useState<'in' | 'out' | 'break_start' | 'break_end'>('in');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selected = empId || employees[0]?.id || '';

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await sendKioskPunch({ employeeId: selected, date, time: punchTime, type: kind });
      const found = result.detected_exception_ids.length
        ? `Detection raised ${result.detected_exception_ids.length} exception(s).`
        : 'Detection raised nothing new.';
      onPunchSent(
        result.inserted
          ? `Punch stored (immutable). ${found}`
          : 'That punch was already on file, so nothing changed.'
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'The punch was not sent.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel-card" style={{ maxWidth: 640, padding: 20 }}>
      <h2 style={{ marginTop: 0 }}>Kiosk Punch Simulator</h2>
      <p className="muted">
        Sends one raw clock event to the backend through the same import path a kiosk feed would use.
        The server stores it as an immutable punch and re-runs the rules for that day. Nothing is
        invented here: whatever appears in the inbox was detected by the backend.
      </p>
      {employees.length === 0 ? (
        <div className="banner banner-error">No employees are visible to you yet.</div>
      ) : (
        <form onSubmit={handleSend} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <label className="field-label">
            Employee:
            <select className="input-field" value={selected} onChange={(e) => setEmpId(e.target.value)}>
              {employees.map((emp) => (
                <option key={emp.id} value={emp.id}>
                  {emp.name} ({emp.id})
                </option>
              ))}
            </select>
          </label>
          <label className="field-label">
            Local date:
            <input type="date" className="input-field mono" value={date} onChange={(e) => setDate(e.target.value)} required />
          </label>
          <label className="field-label">
            Local time (employee's timezone):
            <input type="time" className="input-field mono" value={punchTime} onChange={(e) => setPunchTime(e.target.value)} required />
          </label>
          <label className="field-label">
            Event:
            <select className="input-field" value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
              <option value="in">Clock in</option>
              <option value="out">Clock out</option>
              <option value="break_start">Break start</option>
              <option value="break_end">Break end</option>
            </select>
          </label>
          {error && <div className="banner banner-error" role="alert">{error}</div>}
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? 'Sending...' : 'Send punch to backend'}
          </button>
        </form>
      )}
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
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="panel-card" style={{ padding: 18 }}>
        <h3 style={{ marginTop: 0 }}>Harness Guardrails & Kill-Switch</h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24, alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
            <input type="checkbox" checked={aiEnabled} onChange={(e) => onToggleAi(e.target.checked)} />
            AI Proposal Pipeline Enabled (Uncheck for Rules-Only Fallback Mode)
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
            Confidence Gate Threshold:
            <input
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
          <strong>Versioned Jurisdiction Policy Packs (Configuration, Not Code)</strong>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Pack ID & Version</th>
                <th>Jurisdiction</th>
                <th>Daily / Weekly</th>
                <th>OT Rate & Cap</th>
                <th>Rest Break</th>
                <th>Max Spread-Over</th>
              </tr>
            </thead>
            <tbody>
              {policies.map((p) => (
                <tr key={`${p.id}@${p.version}`}>
                  <td className="mono"><strong>{p.id}@{p.version}</strong></td>
                  <td>{p.jurisdiction}</td>
                  <td className="mono">{p.daily_regular_hours}h / {p.weekly_regular_hours}h</td>
                  <td className="mono">{p.overtime_rate}x ({p.quarterly_ot_cap ? `${p.quarterly_ot_cap}h/qtr` : 'no cap'})</td>
                  <td className="mono">{p.rest_minutes}m after {p.rest_after_hours}h</td>
                  <td className="mono">{p.max_spread_hours ? `${p.max_spread_hours}h` : 'N/A'}</td>
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

const SAMPLES: Record<ImportKind, string> = {
  punches:
    'employee_id,timestamp,type,source_event_id\nE-DEMO-1,2026-11-16 09:00,in,sample-1\nE-DEMO-1,2026-11-16 13:00,break_start,sample-2\nE-DEMO-1,2026-11-16 14:00,break_end,sample-3\n',
  shifts:
    'employee_id,shift_id,start,end,planned_break_min\nE-DEMO-1,S-SAMPLE-1,2026-11-16 09:00,2026-11-16 18:00,60\n',
  notes:
    'employee_id,submitted_at,text\nE-DEMO-1,2026-11-16 19:00,"I left at 6:00 pm but forgot to punch out."\n',
};

export function ImportPreviewView({ onImported }: { onImported: (message: string) => void }) {
  const [kind, setKind] = useState<ImportKind>('punches');
  const [content, setContent] = useState(SAMPLES.punches);
  const [preview, setPreview] = useState<ImportPreviewResult | null>(null);
  const [allowPartial, setAllowPartial] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'The request did not complete.');
    } finally {
      setBusy(false);
    }
  };

  const handlePreview = () => run(async () => setPreview(await previewImport(kind, content)));

  const handleImport = () =>
    run(async () => {
      const result = await commitImport(kind, content, allowPartial);
      setPreview(null);
      const attached = Object.keys(result.notes_attached).length;
      onImported(
        `Imported ${result.inserted} new record(s); ${result.duplicates} already on file; ` +
          `${result.detected_exception_ids.length} exception(s) detected` +
          (attached ? `; notes attached to ${attached} exception(s)` : '') +
          '.'
      );
    });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="panel-card" style={{ padding: 18 }}>
        <h2 style={{ marginTop: 0 }}>Import</h2>
        <p className="muted small">
          Paste CSV or JSON. The backend checks every row, skips duplicates, limits you to your own
          employees, and re-runs detection for the days it touches. Times without an offset are read
          in the employee's timezone. Preview writes nothing.
        </p>
        <label className="field-label">
          What are you importing?
          <select
            className="input-field"
            value={kind}
            onChange={(e) => {
              const next = e.target.value as ImportKind;
              setKind(next);
              setContent(SAMPLES[next]);
              setPreview(null);
            }}
          >
            <option value="punches">Clock punches</option>
            <option value="shifts">Scheduled shifts</option>
            <option value="notes">Employee notes</option>
          </select>
        </label>
        <textarea
          className="input-field mono"
          style={{ width: '100%', minHeight: 140, marginTop: 10 }}
          value={content}
          onChange={(e) => {
            setContent(e.target.value);
            setPreview(null);
          }}
          aria-label="Import data"
        />
        {error && <div className="banner banner-error" role="alert" style={{ marginTop: 10 }}>{error}</div>}
        <div className="button-row" style={{ marginTop: 12 }}>
          <button type="button" className="btn-secondary" disabled={busy || !content.trim()} onClick={handlePreview}>
            Preview
          </button>
          <button type="button" className="btn-primary" disabled={busy || !preview || preview.valid === 0} onClick={handleImport}>
            Import {preview ? `${preview.valid} valid row(s)` : ''}
          </button>
          <label className="small" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input type="checkbox" checked={allowPartial} onChange={(e) => setAllowPartial(e.target.checked)} />
            Import the valid rows even if some are invalid
          </label>
        </div>
      </div>

      {preview && (
        <div className="panel-card">
          <div className="toolbar">
            <strong>
              {preview.valid} valid, {preview.invalid} invalid, {preview.duplicates} duplicate
            </strong>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Status</th>
                  <th>What it is</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((r) => {
                  const record = r.punch ?? r.shift ?? r.note;
                  const what = r.punch
                    ? `${r.punch.employee_id} ${r.punch.type} ${r.punch.ts}`
                    : r.shift
                    ? `${r.shift.employee_id} ${r.shift.start} to ${r.shift.end}`
                    : r.note
                    ? `${r.note.employee_id}: "${r.note.text}"`
                    : '—';
                  return (
                    <tr key={r.row_number}>
                      <td className="mono small">#{r.row_number}</td>
                      <td>
                        <span className={r.status === 'valid' ? 'badge-pass' : r.status === 'duplicate' ? 'badge-neutral' : 'badge-escalated'}>
                          {r.status.toUpperCase()}
                        </span>
                      </td>
                      <td className="mono small">{record ? what : '—'}</td>
                      <td className="small">
                        {r.error ? <span style={{ color: r.status === 'invalid' ? '#dc2626' : undefined }}>{r.error}</span> : 'Ready to import'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
