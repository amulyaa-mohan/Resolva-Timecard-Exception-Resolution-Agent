
﻿import { useState } from 'react';
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
=======
import { useEffect, useId, useMemo, useState } from 'react';
import {
  commitImportWithFallback,
  detectImportFormat,
  fetchCaseAuditWithFallback,
  ImportCommitSummary,
  ImportKind,
  ImportPreviewItem,
  ImportPreviewSummary,
  previewImportWithFallback,
} from '../lib/api';
import { useTranslation } from '../lib/locale';
import { AuditEvent, ExceptionItem, PolicyPack, Role } from '../types/contracts';

const FRIENDLY_EVENT_LABELS: Record<string, string> = {
  PROPOSAL_GENERATED: 'Proposal generated',
  PROPOSAL_VALIDATED: 'Proposal generated',
  EVIDENCE_ATTACHED: 'Evidence attached',
  NOTE_ATTACHED: 'Evidence attached',
  IMPORT_COMMITTED: 'Evidence attached',
  EXCEPTION_DETECTED: 'Exception detected',
  LIVE_PUNCH_EXCEPTION_DETECTED: 'Exception detected',
  PROPOSAL_ESCALATED: 'Escalated for review',
  DECISION_APPROVED: 'Approved by manager',
  DECISION_EDITED: 'Edited by manager',
  DECISION_REJECTED: 'Rejected by manager',
  DECISION_UNDONE: 'Decision reversed',
  USER_LOGIN: 'Signed in',
};

const EXCEPTION_CODE_LABELS: Record<string, string> = {
  MISSING_PUNCH: 'Missing clock-out',
  SPREAD_OVER_BREACH: 'Spread-over breach',
  MEAL_BREAK_BREACH: 'Late meal break',
  OVERTIME_RISK: 'Overtime risk',
  OVERLAPPING_SHIFT: 'Overlapping shift',
  SCHEDULE_DEVIATION: 'Schedule deviation',
};

function resolveAuditTimezone(rawTz?: string): { iana: string; shortLabel: string } {
  const tz = (rawTz ?? '').trim();
  if (/cst|chicago|-06:00/i.test(tz)) return { iana: 'America/Chicago', shortLabel: 'CST' };
  if (/pst|los_angeles|-08:00/i.test(tz)) return { iana: 'America/Los_Angeles', shortLabel: 'PST' };
  if (/est|new_york|-05:00/i.test(tz)) return { iana: 'America/New_York', shortLabel: 'EST' };
  return { iana: 'Asia/Kolkata', shortLabel: 'IST' };
}

function formatWorkDateLabel(workDate: string, ianaTz: string): string {
  const parsed = new Date(`${workDate}T12:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return workDate;
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: ianaTz,
  }).format(parsed);
}

function formatAuditEventTime(isoTs: string, ianaTz: string, shortLabel: string): string {
  const dt = new Date(isoTs);
  if (Number.isNaN(dt.getTime())) return isoTs;
  const datePart = new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    timeZone: ianaTz,
  }).format(dt);
  const timePart = new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: ianaTz,
  }).format(dt);
  return `${datePart}, ${timePart} ${shortLabel}`;
}

function humanizeEventLabel(action: string): string {
  const key = action.trim().toUpperCase();
  if (FRIENDLY_EVENT_LABELS[key]) return FRIENDLY_EVENT_LABELS[key];
  const cleaned = key.replace(/_/g, ' ').toLowerCase();
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

function humanizeActor(ev: AuditEvent): string {
  const rawName = (ev.actor_name ?? '').trim();
  const action = ev.action.toUpperCase();
  if (ev.actor_type === 'ai' || /proposalpipeline|qwen|ollama|mock/i.test(rawName)) {
    return 'AI (demo)';
  }
  if (action.includes('EVIDENCE') || action.includes('IMPORT') || /import/i.test(rawName)) {
    return 'Import';
  }
  if (ev.actor_type === 'system') {
    if (/validator/i.test(rawName)) return 'Validator gate';
    if (/rulesengine|kiosk/i.test(rawName)) return 'Rules engine';
    return rawName || 'System';
  }
  return rawName || 'Manager';
}

function extractModelId(ev: AuditEvent): string | undefined {
  if (ev.model_id) return ev.model_id;
  const match = /\(([^)]+)\)/.exec(ev.actor_name);
  if (match && (ev.actor_type === 'ai' || /qwen|llama|gpt|claude|mock/i.test(match[1]))) {
    return match[1];
  }
  return undefined;
}

function deriveOutcomeSummary(ev: AuditEvent): string {
  const action = ev.action.toUpperCase();
  const after = (ev.after_summary ?? '').trim();

  if (action === 'PROPOSAL_VALIDATED' || action === 'PROPOSAL_GENERATED') {
    if (/escalat/i.test(after)) return 'Escalated for manager review';
    if (/block/i.test(after)) return 'Blocked by deterministic policy check';
    return 'Eligible for manager review';
  }
  if (action === 'EXCEPTION_DETECTED' || action === 'LIVE_PUNCH_EXCEPTION_DETECTED') {
    if (/MISSING_PUNCH/i.test(after)) return 'Unmatched or missing work punch';
    if (/SPREAD_OVER_BREACH/i.test(after)) return 'Spread-over exceeds statutory cap';
    if (/MEAL_BREAK_BREACH/i.test(after)) return 'Meal break started past statutory window';
    if (/OVERTIME_RISK/i.test(after)) return 'Projected weekly hours exceed cap';
  }
  if (action === 'PROPOSAL_ESCALATED') {
    return after.replace(/^Blocked\s*&\s*escalated:\s*/i, 'Blocked: ') || 'Routed for manual manager review';
  }
  return after;
}

function sanitizeCsvCell(val: unknown): string {
  const str = String(val ?? '');
  const guarded = /^[=+\-@\t\r]/.test(str) ? `'${str}` : str;
  return `"${guarded.replace(/"/g, '""')}"`;
}

async function copyTextSafe(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const el = document.createElement('textarea');
    el.value = text;
    el.style.position = 'fixed';
    el.style.opacity = '0';
    document.body.appendChild(el);
    el.select();
    document.execCommand('copy');
    document.body.removeChild(el);
  }
}

export function AuditView({
  events,
  selectedCase = null,
  role = 'manager',
  onOpenCase,
}: {
  events: AuditEvent[];
  selectedCase?: ExceptionItem | null;
  role?: Role;
  onOpenCase?: (exceptionId: string) => void;
}) {
  const { tr } = useTranslation();
  const [scope, setScope] = useState<'case' | 'all'>(selectedCase ? 'case' : 'all');
  const [serverCaseEvents, setServerCaseEvents] = useState<AuditEvent[] | null>(null);
  const [expandedIds, setExpandedIds] = useState<Record<string, boolean>>({});
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const headingId = useId();

  useEffect(() => {
    setScope(selectedCase ? 'case' : 'all');
    setServerCaseEvents(null);
    if (selectedCase) {
      fetchCaseAuditWithFallback(selectedCase.id, role).then((rows) => {
        if (rows && rows.length > 0) setServerCaseEvents(rows);
      });
    }
  }, [selectedCase?.id, role]);

  const caseFilteredEvents = useMemo(() => {
    if (!selectedCase) return events;
    if (serverCaseEvents && serverCaseEvents.length > 0) return serverCaseEvents;
    return events.filter(
      (ev) =>
        ev.entity_ref.includes(selectedCase.id) ||
        ev.entity_ref.includes(selectedCase.employee_id) ||
        (selectedCase.proposal?.id ? ev.entity_ref.includes(selectedCase.proposal.id) : false)
    );
  }, [events, selectedCase, serverCaseEvents]);

  const displayedEvents = scope === 'case' && selectedCase ? caseFilteredEvents : events;
  const tzInfo = resolveAuditTimezone(selectedCase?.timezone);


  const exportCsv = () => {
    const header = 'id,trace_id,actor_type,actor_name,action,entity_ref,before,after,ts\n';
    const rows = displayedEvents
      .map((e) =>
        [e.id, e.trace_id, e.actor_type, e.actor_name, e.action, e.entity_ref, e.before_summary, e.after_summary, e.ts]
          .map((v) => csvCell(v))

          .map(sanitizeCsvCell)

          .join(',')
      )
      .join('\n');
    const blob = new Blob([header + rows], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = scope === 'case' && selectedCase ? `resolva-audit-${selectedCase.id.toLowerCase()}.csv` : 'resolva-audit-trail.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const toggleDetails = (id: string) => {
    setExpandedIds((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const handleCopy = async (key: string, value: string) => {
    await copyTextSafe(value);
    setCopiedKey(key);
    window.setTimeout(() => {
      setCopiedKey((prev) => (prev === key ? null : prev));
    }, 1800);
  };

  const caseReasonLabel = selectedCase
    ? EXCEPTION_CODE_LABELS[selectedCase.code] ?? selectedCase.code.replace(/_/g, ' ')
    : '';
  const caseWorkDateLabel = selectedCase ? formatWorkDateLabel(selectedCase.work_date, tzInfo.iana) : '';

  return (
    <section className="audit-shell" aria-labelledby={headingId}>
      <div className="panel-card">
        <div className="audit-header">
          <div className="audit-header-main">
            <h1 id={headingId} className="page-title">
              {tr("Audit trail")}
            </h1>

            {scope === 'case' && selectedCase ? (
              <p className="audit-scope-line">
                <strong>{selectedCase.employee_name}</strong>
                <span aria-hidden="true"> · </span>
                <span>{caseReasonLabel}</span>
                <span aria-hidden="true"> · </span>
                <span>Work date: {caseWorkDateLabel}</span>
                <span className="audit-scope-code">({selectedCase.id})</span>
              </p>
            ) : (
              <p className="audit-scope-line">
                All workspace activity ({events.length} {events.length === 1 ? 'event' : 'events'}) · Times shown in {tzInfo.shortLabel}
              </p>
            )}
          </div>

          <div className="audit-header-actions">
            {selectedCase && (
              <div className="audit-scope-switch" role="group" aria-label="Audit scope">
                <button
                  type="button"
                  className={scope === 'case' ? 'audit-scope-btn active' : 'audit-scope-btn'}
                  aria-pressed={scope === 'case'}
                  onClick={() => setScope('case')}
                >
                  Selected case ({caseFilteredEvents.length})
                </button>
                <button
                  type="button"
                  className={scope === 'all' ? 'audit-scope-btn active' : 'audit-scope-btn'}
                  aria-pressed={scope === 'all'}
                  onClick={() => setScope('all')}
                >
                  All activity ({events.length})
                </button>
              </div>
            )}
            {selectedCase && onOpenCase && (
              <button type="button" className="btn-secondary" onClick={() => onOpenCase(selectedCase.id)}>
                {tr("Open case")}
              </button>
            )}
            <button type="button" className="btn-secondary" disabled={displayedEvents.length === 0} onClick={exportCsv}>
              {tr("Export CSV")}
            </button>
          </div>
        </div>

        {displayedEvents.length === 0 ? (
          <div className="audit-empty-state">
            <p className="audit-empty-title">No audit events recorded yet</p>
            <p className="small muted" style={{ margin: '4px 0 0' }}>
              Detections, evidence imports, AI proposals, and manager decisions appear here automatically.
            </p>
          </div>
        ) : (
          <div className="audit-list-wrap">
            <div className="audit-grid-head" aria-hidden="true">
              <span>Event</span>
              <span>Actor</span>
              <span>Time</span>
              <span className="sr-only">Details</span>
            </div>

            <ul className="audit-event-list">
              {displayedEvents.map((ev) => {
                const isOpen = Boolean(expandedIds[ev.id]);
                const drawerId = `audit-details-${ev.id}`;
                const eventLabel = humanizeEventLabel(ev.action);
                const outcome = deriveOutcomeSummary(ev);
                const actorLabel = humanizeActor(ev);
                const timeLabel = formatAuditEventTime(ev.ts, tzInfo.iana, tzInfo.shortLabel);
                const modelId = extractModelId(ev);
                const beforeText = (ev.before_summary ?? '').trim();
                const afterText = (ev.after_summary ?? '').trim();
                const hasBeforeAfter = Boolean(beforeText && afterText && beforeText !== afterText);

                return (
                  <li key={ev.id} className="audit-event-row">
                    <div className="audit-event-main">
                      <div className="audit-col-event">
                        <div className="audit-event-title">{eventLabel}</div>
                        {outcome && <div className="audit-event-outcome">{outcome}</div>}
                      </div>

                      <div className="audit-col-actor">
                        <span className={ev.actor_type === 'ai' ? 'badge-ai' : 'badge-neutral'}>{actorLabel}</span>
                      </div>

                      <div className="audit-col-time tnum">{timeLabel}</div>

                      <div className="audit-col-toggle">
                        <button
                          type="button"
                          className="source-disclosure-toggle"
                          aria-expanded={isOpen}
                          aria-controls={drawerId}
                          onClick={() => toggleDetails(ev.id)}
                        >
                          <span>{tr("Technical details")}</span>
                          <span aria-hidden="true">{isOpen ? '▾' : '▸'}</span>
                        </button>
                      </div>
                    </div>

                    {isOpen && (
                      <div id={drawerId} className="audit-tech-drawer">
                        <dl className="audit-tech-grid">
                          <div className="audit-tech-pair">
                            <dt>Exact timestamp</dt>
                            <dd className="mono">{ev.ts}</dd>
                          </div>

                          <div className="audit-tech-pair">
                            <dt>Event code</dt>
                            <dd className="mono">{ev.action}</dd>
                          </div>

                          {ev.id && (
                            <div className="audit-tech-pair">
                              <dt>Event ID</dt>
                              <dd className="audit-copy-row">
                                <code className="mono">{ev.id}</code>
                                <button
                                  type="button"
                                  className="btn-secondary source-copy-btn"
                                  aria-label={`Copy event ID ${ev.id}`}
                                  onClick={() => handleCopy(`${ev.id}-id`, ev.id)}
                                >
                                  {copiedKey === `${ev.id}-id` ? 'Copied' : 'Copy'}
                                </button>
                              </dd>
                            </div>
                          )}

                          {ev.trace_id && (
                            <div className="audit-tech-pair">
                              <dt>Trace ID</dt>
                              <dd className="audit-copy-row">
                                <code className="mono">{ev.trace_id}</code>
                                <button
                                  type="button"
                                  className="btn-secondary source-copy-btn"
                                  aria-label={`Copy trace ID ${ev.trace_id}`}
                                  onClick={() => handleCopy(`${ev.id}-trace`, ev.trace_id)}
                                >
                                  {copiedKey === `${ev.id}-trace` ? 'Copied' : 'Copy'}
                                </button>
                              </dd>
                            </div>
                          )}

                          {ev.entity_ref && (
                            <div className="audit-tech-pair">
                              <dt>Entity ID</dt>
                              <dd className="audit-copy-row">
                                <code className="mono">{ev.entity_ref}</code>
                                <button
                                  type="button"
                                  className="btn-secondary source-copy-btn"
                                  aria-label={`Copy entity ID ${ev.entity_ref}`}
                                  onClick={() => handleCopy(`${ev.id}-entity`, ev.entity_ref)}
                                >
                                  {copiedKey === `${ev.id}-entity` ? 'Copied' : 'Copy'}
                                </button>
                              </dd>
                            </div>
                          )}

                          {modelId && (
                            <div className="audit-tech-pair">
                              <dt>Provider / model</dt>
                              <dd className="mono">{modelId}</dd>
                            </div>
                          )}

                          {ev.evidence_hash && (
                            <div className="audit-tech-pair">
                              <dt>Record hash</dt>
                              <dd className="audit-copy-row">
                                <code className="mono">{ev.evidence_hash}</code>
                                <button
                                  type="button"
                                  className="btn-secondary source-copy-btn"
                                  aria-label={`Copy hash ${ev.evidence_hash}`}
                                  onClick={() => handleCopy(`${ev.id}-hash`, ev.evidence_hash!)}
                                >
                                  {copiedKey === `${ev.id}-hash` ? 'Copied' : 'Copy'}
                                </button>
                              </dd>
                            </div>
                          )}
                        </dl>

                        {hasBeforeAfter && (
                          <div className="audit-diff-box">
                            <div className="audit-diff-item">
                              <span className="audit-diff-label">Before</span>
                              <code className="mono">{beforeText}</code>
                            </div>
                            <div className="audit-diff-item">
                              <span className="audit-diff-label">After</span>
                              <code className="mono">{afterText}</code>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}

const SAMPLE_BY_KIND: Record<ImportKind, string> = {
  punches: `employee_id,timestamp,type,source_event_id
EMP-BLR-11,2026-11-17T09:00:00+05:30,in,kiosk-blr-901
EMP-BLR-11,2026-11-17T13:05:00+05:30,break_start,kiosk-blr-902
EMP-BLR-12,2026-11-17T09:15:00+05:30,in,kiosk-blr-903
EMP-BLR-11,2026-11-17T09:00:00+05:30,in,kiosk-blr-901
EMP-AUS-09,,in,kiosk-aus-904`,
  shifts: `employee_id,shift_id,start,end,planned_break_min
EMP-BLR-11,SHD-951,2026-11-18T09:00:00+05:30,2026-11-18T18:00:00+05:30,60
EMP-BLR-12,SHD-952,2026-11-18T10:00:00+05:30,2026-11-18T19:00:00+05:30,60
EMP-BLR-11,SHD-951,2026-11-18T09:00:00+05:30,2026-11-18T18:00:00+05:30,60
EMP-AUS-09,SHD-953,2026-11-18T17:00:00-06:00,2026-11-18T09:00:00-06:00,30`,
  notes: `employee_id,text,submitted_at,note_id
EMP-BLR-11,Forgot to clock out at kiosk before catching evening shuttle.,2026-11-17T18:12:00+05:30,NOTE-801
EMP-BLR-11,Forgot to clock out at kiosk before catching evening shuttle.,2026-11-17T18:12:00+05:30,NOTE-801
EMP-BLR-12,,2026-11-17T18:20:00+05:30,NOTE-802`,
};

const FORMAT_GUIDANCE: Record<ImportKind, { columns: string; placeholder: string }> = {
  punches: {
    columns: 'employee_id, timestamp, type, source_event_id (optional: date, time, source, device_id)',
    placeholder: 'employee_id,timestamp,type,source_event_id\nEMP-BLR-11,2026-11-17T09:00:00+05:30,in,kiosk-blr-901',
  },
  shifts: {
    columns: 'employee_id, shift_id, start, end, planned_break_min',
    placeholder: 'employee_id,shift_id,start,end,planned_break_min\nEMP-BLR-11,SHD-951,2026-11-18T09:00:00+05:30,2026-11-18T18:00:00+05:30,60',
  },
  notes: {
    columns: 'employee_id, text, submitted_at, note_id',
    placeholder: 'employee_id,text,submitted_at,note_id\nEMP-BLR-11,Missed clock-out at gate,2026-11-17T18:12:00+05:30,NOTE-801',
  },
};

const FRIENDLY_PUNCH_EVENT: Record<string, string> = {
  in: 'Clock in',
  out: 'Clock out',
  break_start: 'Break started',
  break_end: 'Break ended',
};

export function ImportPreviewView({
  onImportValid,
  role = 'manager',
  onOpenException,
}: {
  onImportValid: (items: ExceptionItem[]) => void;
  role?: Role;
  onOpenException?: (exceptionId: string) => void;
}) {
  const { tr } = useTranslation();
  const [kind, setKind] = useState<ImportKind>('punches');
  const [rawInput, setRawInput] = useState('');
  const [isSampleLoaded, setIsSampleLoaded] = useState(false);
  const [preview, setPreview] = useState<ImportPreviewSummary | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [allowPartial, setAllowPartial] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [commitError, setCommitError] = useState<string | null>(null);
  const [commitResult, setCommitResult] = useState<ImportCommitSummary | null>(null);
  const [expandedRows, setExpandedRows] = useState<Record<number, boolean>>({});
  const [copiedRowId, setCopiedRowId] = useState<string | null>(null);
  const headingId = useId();

  const canWrite = role === 'manager' || role === 'admin';
  const detectedFormat = detectImportFormat(rawInput);
  const currentStep = commitResult ? 3 : preview ? 2 : 1;

  const invalidatePreview = () => {
    setPreview(null);
    setAllowPartial(false);
    setCommitResult(null);
    setCommitError(null);
    setExpandedRows({});
  };

  const handleKindChange = (nextKind: ImportKind) => {
    setKind(nextKind);
    setIsSampleLoaded(false);
    invalidatePreview();
  };

  const handleInputChange = (value: string) => {
    setRawInput(value);
    setIsSampleLoaded(false);
    invalidatePreview();
  };

  const handleLoadSample = () => {
    setRawInput(SAMPLE_BY_KIND[kind]);
    setIsSampleLoaded(true);
    invalidatePreview();
  };

  const handleClear = () => {
    setRawInput('');
    setIsSampleLoaded(false);
    invalidatePreview();
  };

  const handlePreview = async () => {
    if (!rawInput.trim() || previewing) return;
    setPreviewing(true);
    setCommitError(null);
    setCommitResult(null);
    const summary = await previewImportWithFallback({
      kind,
      format: detectedFormat,
      content: rawInput,
      role,
    });
    setPreview(summary);
    setAllowPartial(false);
    setPreviewing(false);
  };

  const hasCoexistingValidAndInvalid = Boolean(preview && preview.valid > 0 && preview.invalid > 0);
  const canCommit = Boolean(
    preview &&
      canWrite &&
      preview.valid > 0 &&
      (preview.invalid === 0 || allowPartial)
  );

  const blockedReason = useMemo(() => {
    if (!preview) return null;
    if (!canWrite) {
      return `Import unavailable for role “${role}”. Switch to manager or admin to commit attendance records.`;
    }
    if (preview.valid === 0) {
      return 'Import unavailable because there are 0 valid rows. Fix the row errors above and preview again.';
    }
    if (preview.invalid > 0 && !allowPartial) {
      return `Import blocked because ${preview.invalid} ${preview.invalid === 1 ? 'row is' : 'rows are'} invalid. Select “Import valid rows only” or fix the invalid rows and preview again.`;
    }
    return null;
  }, [preview, canWrite, role, allowPartial]);

  const handleCommit = async () => {
    if (!preview || !canCommit || committing) return;
    setCommitting(true);
    setCommitError(null);
    const outcome = await commitImportWithFallback({
      kind,
      format: detectedFormat,
      content: rawInput,
      allowPartial,
      preview,
      role,
    });
    setCommitting(false);
    if (!outcome.ok || !outcome.result) {
      setCommitError(outcome.error ?? 'Import could not be completed.');
      return;
    }
    setCommitResult(outcome.result);
    if (outcome.result.created_exceptions.length > 0) {
      onImportValid(outcome.result.created_exceptions);
    }
  };

  const toggleRowDetails = (rowNum: number) => {
    setExpandedRows((prev) => ({ ...prev, [rowNum]: !prev[rowNum] }));
  };

  const handleCopySourceId = async (key: string, val: string) => {
    await copyTextSafe(val);
    setCopiedRowId(key);
    window.setTimeout(() => {
      setCopiedRowId((prev) => (prev === key ? null : prev));
    }, 1800);
  };

  const renderRowCells = (row: ImportPreviewItem) => {
    const empDisplay = row.employee_name
      ? `${row.employee_name} (${row.employee_id || '—'})`
      : row.employee_id || '—';

    if (kind === 'punches') {
      const eventText = row.event_code
        ? FRIENDLY_PUNCH_EVENT[row.event_code] ?? row.event_code
        : '—';
      return (
        <>
          <td className="tnum">{row.row_number}</td>
          <td>
            <strong>{empDisplay}</strong>
          </td>
          <td className="tnum">{row.local_time || '—'}</td>
          <td>{eventText}</td>
        </>
      );
    }

    if (kind === 'shifts') {
      return (
        <>
          <td className="tnum">{row.row_number}</td>
          <td>
            <strong>{empDisplay}</strong>
          </td>
          <td className="tnum">{row.shift_window || '—'}</td>
          <td className="tnum">{typeof row.planned_break_min === 'number' ? `${row.planned_break_min} min` : '—'}</td>
        </>
      );
    }

    return (
      <>
        <td className="tnum">{row.row_number}</td>
        <td>
          <strong>{empDisplay}</strong>
        </td>
        <td className="tnum">{row.local_time || '—'}</td>
        <td className="import-note-cell">{row.note_excerpt || '—'}</td>
      </>
    );
  };

  return (
    <section className="import-shell" aria-labelledby={headingId}>
      <div className="import-header">
        <div>
          <h1 id={headingId} className="page-title">
            {tr("Import attendance")}
          </h1>
          <p className="import-subtitle">{tr("Paste CSV or JSON and preview the rows before importing.")}</p>
        </div>

        <ol className="import-stepper" aria-label="Import progress">
          <li className={currentStep === 1 ? 'step-item active' : 'step-item done'} aria-current={currentStep === 1 ? 'step' : undefined}>
            {tr("1. Paste data")}
          </li>
          <li aria-hidden="true" className="step-sep">â†’</li>
          <li className={currentStep === 2 ? 'step-item active' : currentStep > 2 ? 'step-item done' : 'step-item'} aria-current={currentStep === 2 ? 'step' : undefined}>
            {tr("2. Review rows")}
          </li>
          <li aria-hidden="true" className="step-sep">â†’</li>
          <li className={currentStep === 3 ? 'step-item active' : 'step-item'} aria-current={currentStep === 3 ? 'step' : undefined}>
            3. Import
          </li>
        </ol>
      </div>

      <div className="panel-card import-card">
        <div className="import-controls-bar">
          <div className="import-type-group">
            <label htmlFor="import-kind-select" className="import-inline-label">
              {tr("Import type")}
            </label>
            <select
              id="import-kind-select"
              className="role-select"
              value={kind}
              onChange={(e) => handleKindChange(e.target.value as ImportKind)}
            >
              <option value="punches">{tr("Clock punches")}</option>
              <option value="shifts">{tr("Scheduled shifts")}</option>
              <option value="notes">{tr("Employee notes")}</option>
            </select>
            {isSampleLoaded && <span className="badge-neutral">Sample data loaded</span>}
          </div>

          <div className="button-row">
            {rawInput.trim().length > 0 && (
              <button type="button" className="btn-ghost" onClick={handleClear}>
                Clear
              </button>
            )}
            <button type="button" className="btn-secondary" onClick={handleLoadSample}>
              {tr("Load sample")}
            </button>
          </div>
        </div>

        <div className="import-editor-layout">
          <div className="import-editor-col">
            <div className="import-field-header">
              <label htmlFor="import-data-editor" className="import-field-label">
                {tr("Attendance data (CSV or JSON)")}
              </label>
              {rawInput.trim() && (
                <span className="mono badge-neutral">{detectedFormat.toUpperCase()}</span>
              )}
            </div>
            <textarea
              id="import-data-editor"
              className="import-editor"
              rows={8}
              spellCheck={false}
              autoCapitalize="off"
              autoCorrect="off"
              placeholder={FORMAT_GUIDANCE[kind].placeholder}
              value={rawInput}
              onChange={(e) => handleInputChange(e.target.value)}
            />
          </div>

          <aside className="import-guidance-box" aria-label="Format help">
            <div className="import-guidance-title">{tr("Format help")}</div>
            <p className="import-guidance-text">
              Times without an offset use the employee’s timezone.
            </p>
            <div className="import-guidance-sub">{tr("Supported columns")}</div>
            <code className="mono import-columns-code">{FORMAT_GUIDANCE[kind].columns}</code>
            <p className="import-guidance-text" style={{ marginTop: 8 }}>
              {tr("Paste a CSV table with a header row or a JSON array of objects.")}
            </p>
          </aside>
        </div>

        <div className="import-action-bar">
          <button
            type="button"
            className="btn-primary"
            disabled={!rawInput.trim() || previewing}
            onClick={handlePreview}
          >
            {previewing ? 'Previewing”¦' : 'Preview rows'}
          </button>
          {!rawInput.trim() && (
            <span className="small muted">Paste CSV or JSON above, or click “Load sample”.</span>
          )}
        </div>
      </div>

      {preview && (
        <div className="panel-card import-card">
          <div className="import-preview-header">
            <div>
              <h2 className="card-heading">Preview summary</h2>
              <p className="import-counts-line tnum">
                <span className="count-valid">{preview.valid} valid</span>
                <span aria-hidden="true"> · </span>
                <span className="count-dup">{preview.duplicates} {preview.duplicates === 1 ? 'duplicate' : 'duplicates'}</span>
                <span aria-hidden="true"> · </span>
                <span className="count-invalid">{preview.invalid} invalid</span>
              </p>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Employee</th>
                  {kind === 'punches' && (
                    <>
                      <th>Local time</th>
                      <th>Event</th>
                    </>
                  )}
                  {kind === 'shifts' && (
                    <>
                      <th>Shift window (Local)</th>
                      <th>Break</th>
                    </>
                  )}
                  {kind === 'notes' && (
                    <>
                      <th>Submitted (Local)</th>
                      <th>Note excerpt</th>
                    </>
                  )}
                  <th>Result</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row) => {
                  const isExpanded = Boolean(expandedRows[row.row_number]);
                  const detailId = `import-row-detail-${row.row_number}`;
                  return (
                    <>
                      <tr key={row.row_number}>
                        {renderRowCells(row)}
                        <td>
                          {row.status === 'valid' && <span className="badge-pass">Valid</span>}
                          {row.status === 'duplicate' && (
                            <span className="badge badge-warning">
                              Duplicate{row.duplicate_of ? ` (row ${row.duplicate_of})` : ''}
                            </span>
                          )}
                          {row.status === 'invalid' && (
                            <div className="import-row-error-cell">
                              <span className="badge-escalated">Invalid</span>
                              {row.error && <span className="import-error-msg">{row.error}</span>}
                            </div>
                          )}
                        </td>
                        <td>
                          <button
                            type="button"
                            className="source-disclosure-toggle"
                            aria-expanded={isExpanded}
                            aria-controls={detailId}
                            onClick={() => toggleRowDetails(row.row_number)}
                          >
                            <span>Details</span>
                            <span aria-hidden="true">{isExpanded ? '▾' : '▸'}</span>
                          </button>
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr key={`${row.row_number}-details`} className="import-detail-row">
                          <td colSpan={6}>
                            <div id={detailId} className="audit-tech-drawer" style={{ marginTop: 0 }}>
                              <dl className="audit-tech-grid">
                                {row.source_event_id && (
                                  <div className="audit-tech-pair">
                                    <dt>Source record ID</dt>
                                    <dd className="audit-copy-row">
                                      <code className="mono">{row.source_event_id}</code>
                                      <button
                                        type="button"
                                        className="btn-secondary source-copy-btn"
                                        onClick={() => handleCopySourceId(`${row.row_number}-src`, row.source_event_id!)}
                                      >
                                        {copiedRowId === `${row.row_number}-src` ? 'Copied' : 'Copy'}
                                      </button>
                                    </dd>
                                  </div>
                                )}
                                {row.raw_timestamp && (
                                  <div className="audit-tech-pair">
                                    <dt>Exact timestamp</dt>
                                    <dd className="mono">{row.raw_timestamp}</dd>
                                  </div>
                                )}
                                {row.event_code && (
                                  <div className="audit-tech-pair">
                                    <dt>Event code</dt>
                                    <dd className="mono">{row.event_code}</dd>
                                  </div>
                                )}
                                {row.timezone && (
                                  <div className="audit-tech-pair">
                                    <dt>Employee timezone</dt>
                                    <dd className="mono">{row.timezone}</dd>
                                  </div>
                                )}
                              </dl>
                              <div className="audit-diff-item" style={{ marginTop: 8 }}>
                                <span className="audit-diff-label">Raw row payload</span>
                                <code className="mono">{JSON.stringify(row.raw_row)}</code>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="import-commit-footer">
            {hasCoexistingValidAndInvalid && (
              <label className="partial-import-toggle">
                <input
                  type="checkbox"
                  checked={allowPartial}
                  onChange={(e) => setAllowPartial(e.target.checked)}
                />
                <span>
                  Import valid rows only ({preview.valid} valid, skip {preview.invalid} invalid)
                </span>
              </label>
            )}

            <div className="import-commit-row">
              <button
                type="button"
                className="btn-primary"
                disabled={!canCommit || committing}
                onClick={handleCommit}
              >
                {committing
                  ? 'Importing”¦'
                  : `Import ${preview.valid} ${preview.valid === 1 ? 'row' : 'rows'}`}
              </button>
            </div>

            {blockedReason && (
              <p className="import-blocked-msg" role="status">
                {blockedReason}
              </p>
            )}

            {commitError && (
              <div className="banner banner-error" role="alert" style={{ marginTop: 10 }}>
                {commitError}
              </div>
            )}
          </div>
        </div>
      )}

      {commitResult && (
        <div className="banner banner-success import-completion-banner" role="status">
          <div className="import-completion-main">
            <strong>
              Imported {commitResult.inserted} {commitResult.inserted === 1 ? 'row' : 'rows'}
            </strong>
            <span>
              {' '}
              · Skipped {commitResult.skipped} ({commitResult.duplicates}{' '}
              {commitResult.duplicates === 1 ? 'duplicate' : 'duplicates'}, {commitResult.invalid} invalid)
            </span>
            <span className="muted"> · Batch </span>
            <code className="mono">{commitResult.batch_id}</code>
          </div>

          {commitResult.detected_exception_ids.length > 0 && onOpenException && (
            <div className="button-row" style={{ marginTop: 8 }}>
              {commitResult.detected_exception_ids.map((excId) => (
                <button
                  key={excId}
                  type="button"
                  className="btn-secondary"
                  onClick={() => onOpenException(excId)}
                >
                  Open {excId} in Inbox â†’
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
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

export function KioskView({ onSimulatePunch }: { onSimulatePunch: (newExc: ExceptionItem) => void }) {
  const { tr } = useTranslation();
  const [empId, setEmpId] = useState('EMP-BLR-07');
  const [empName, setEmpName] = useState('Meera Krishnan');
  const [punchTime, setPunchTime] = useState('09:05');
  const [editedNote, setNote] = useState<string>();
  const note = editedNote ?? tr('Clocked in at Bengaluru store kiosk; forgot evening out-punch.');


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
    <div className="panel-card kiosk-card">
      <h2 className="kiosk-title">{tr("Kiosk Punch Simulator (Live Event Demo)")}</h2>
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
                  <td>{tr(p.jurisdiction)}</td>
                  <td>{p.daily_regular_hours}{tr(" hours")} / {p.weekly_regular_hours}{tr(" hours")}</td>
                  <td>{p.overtime_rate}× ({p.quarterly_ot_cap ? `${p.quarterly_ot_cap}${tr(" hours per quarter")}` : tr("no cap")})</td>
                  <td>{p.rest_minutes}{tr(" min after ")}{p.rest_after_hours}{tr(" hours")}</td>
                  <td>{p.max_spread_hours ? `${p.max_spread_hours}${tr(" hours")}` : tr('N/A')}</td>
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
