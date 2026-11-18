import { useEffect, useState } from 'react';
import { checkEditedTime } from '../lib/api';
import { ExceptionItem, Role } from '../types/contracts';
import { PunchTimeline } from './PunchTimeline';

interface ResolutionPanelProps {
  item: ExceptionItem | null;
  role: Role;
  aiEnabled: boolean;
  onClose: () => void;
  onSimulateStale: (itemId: string) => void;
  onRepropose: (itemId: string) => void;
  onDecide: (
    item: ExceptionItem,
    decision: 'approved' | 'edited' | 'rejected',
    details: { editedTime?: string; reasonCode?: string; comment?: string }
  ) => void;
}

export function ResolutionPanel({
  item,
  role,
  aiEnabled,
  onClose,
  onSimulateStale,
  onRepropose,
  onDecide,
}: ResolutionPanelProps) {
  const [mode, setMode] = useState<'review' | 'edit' | 'reject'>('review');
  const [editedTime, setEditedTime] = useState('18:00');
  const [rejectReason, setRejectReason] = useState('INSUFFICIENT_EVIDENCE');
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setMode('review');
    setComment('');
    setSubmitting(false);
    const proposedTs = item?.proposal?.actions.find((a) => a.new_ts)?.new_ts;
    setEditedTime(proposedTs ? proposedTs.slice(11, 16) : '18:00');
  }, [item?.id]);

  // Keyboard shortcuts inside panel: E (Edit), R (Reject), Esc (Cancel/Close)
  useEffect(() => {
    if (!item) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (e.key === 'Escape') {
        if (mode !== 'review') setMode('review');
        else onClose();
        return;
      }
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
      const canEdit = (role === 'manager' || role === 'admin') && item.status !== 'resolved' && mode === 'review';
      if (e.key.toLowerCase() === 'e' && canEdit) setMode('edit');
      if (e.key.toLowerCase() === 'r' && canEdit) setMode('reject');
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [item, role, mode, onClose]);

  if (!item) {
    return (
      <aside className="resolution-panel empty-panel" aria-label="Exception detail">
        <div className="empty-state">
          <h3>Select an exception</h3>
          <p>Click any row or press <strong>J / K</strong> to inspect evidence, citations, and rule checks.</p>
        </div>
      </aside>
    );
  }

  const canDecide = role === 'manager' || role === 'admin';
  const proposal = aiEnabled ? item.proposal : undefined;
  // Syntax only. Whether a correction is allowed is decided by the backend on submit.
  const editCheck = mode === 'edit' ? checkEditedTime(item, editedTime) : null;
  // Rule outcomes always come from the backend validator; the browser never computes them.
  const activeRuleOutcomes = proposal?.rule_outcomes ?? [];

  const handleSubmit = (
    decision: 'approved' | 'edited' | 'rejected',
    details: { editedTime?: string; reasonCode?: string; comment?: string }
  ) => {
    if (!canDecide || submitting) return;
    setSubmitting(true);
    onDecide(item, decision, details);
    setSubmitting(false);
  };

  return (
    <aside className="resolution-panel" aria-label={`Resolution details for ${item.id}`}>
      <div className="panel-header">
        <div>
          <div className="panel-badges">
            <span className={`badge badge-${item.severity}`}>
              {item.severity === 'problem' ? 'PROBLEM (Blocks Pay)' : 'WARNING'}
            </span>
            <span className="mono badge-neutral">{item.code}</span>
            <span className="mono badge-neutral">{item.policy_pack_id}</span>
            <span className="mono badge-neutral">v{item.evidence_version}</span>
          </div>
          <h2>
            {item.employee_name} <span className="mono muted">({item.employee_id})</span>
          </h2>
          <p className="muted small">
            {item.job} • {item.location} • Work Date: <span className="mono">{item.work_date}</span> ({item.timezone})
          </p>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {item.status !== 'resolved' && (
            <>
              <button
                type="button"
                className="btn-primary small"
                title="Ask the backend to draft a correction. It approves nothing."
                onClick={() => onRepropose(item.id)}
              >
                {item.proposal || item.draft_status ? 'Draft again' : 'Draft with AI'}
              </button>
              <button
                type="button"
                className="btn-secondary small"
                title="Re-read this case from the server and check the draft is still current"
                onClick={() => onSimulateStale(item.id)}
              >
                Re-check evidence
              </button>
            </>
          )}
          <button type="button" className="btn-ghost" onClick={onClose} aria-label="Close panel (Esc)">
            ✕
          </button>
        </div>
      </div>

      {item.stale_warning && (
        <div className="banner banner-error" role="alert">
          <strong>Stale draft:</strong> the evidence changed after this draft was generated, so approving it would be refused by the server (HTTP 409). Draft again on the latest evidence.{' '}
          <button type="button" className="btn-primary" style={{ marginLeft: 8, padding: '4px 10px' }} onClick={() => onRepropose(item.id)}>
            Draft on latest evidence
          </button>
        </div>
      )}

      {!canDecide && (
        <div className="banner banner-warn" role="alert">
          <strong>Access Denied for Edits ({role}):</strong> Only an authorized <code>manager</code> can approve, edit, or reject timecard corrections.
        </div>
      )}

      {item.status === 'resolved' && item.resolution && (
        <div className="banner banner-success">
          <strong>Resolved ({item.resolution.decision.toUpperCase()})</strong> by {item.resolution.decided_by} • Trace{' '}
          <span className="mono">{item.resolution.trace_id}</span>
          {item.resolution.comment ? ` — "${item.resolution.comment}"` : ''}
        </div>
      )}

      <PunchTimeline item={item} editedTimeHHMM={mode === 'edit' ? editedTime : null} />

      <div className="card-block">
        <div className="section-label">Observed Facts (Immutable Source Records)</div>
        <ul className="punch-list">
          {item.punches.map((p) => (
            <li key={p.id} className="mono small">
              <strong>{p.type.toUpperCase()}</strong> — {p.ts} ({p.source} / {p.device_id}) [ID: {p.id}]
            </li>
          ))}
        </ul>
        {item.employee_note && (
          <div className="untrusted-note">
            <span className="untrusted-tag">UNTRUSTED EMPLOYEE NOTE (EVIDENCE ONLY)</span>
            <p>"{item.employee_note}"</p>
          </div>
        )}
      </div>

      <div className="diff-grid">
        <div className="diff-box">
          <span className="section-label">Before Correction</span>
          <div className="mono">Regular: {item.before_hours.regular_hours}</div>
          <div className="mono">Overtime: {item.before_hours.overtime_hours}</div>
          <div className="small muted">{item.before_hours.pay_status}</div>
        </div>
        <div className="diff-box diff-after">
          <span className="section-label">After Proposed Fix</span>
          <div className="mono">Regular: {item.after_hours?.regular_hours ?? item.before_hours.regular_hours}</div>
          <div className="mono">Overtime: {item.after_hours?.overtime_hours ?? item.before_hours.overtime_hours}</div>
          <div className="small">{item.after_hours?.pay_status ?? 'Manual manager resolution required'}</div>
        </div>
      </div>

      {!aiEnabled ? (
        <div className="banner banner-warn">
          <strong>AI Kill-Switch Active (Rules-Only Mode):</strong> AI proposal generation is disabled. Deterministic detection and manual manager resolution remain active.
        </div>
      ) : proposal ? (
        <div className="ai-card">
          <div className="ai-card-header">
            <span className="badge-ai">AI DRAFT</span>
            <span className="mono small">
              Confidence: <strong>{Math.round(proposal.confidence * 100)}%</strong> • Model: {proposal.model_id} • Prompt: {proposal.prompt_hash}
            </span>
          </div>
          <p className="ai-rationale">{proposal.rationale}</p>
          {proposal.actions.length > 0 && (
            <div className="proposed-actions">
              <span className="section-label">Proposed Action</span>
              {proposal.actions.map((act, idx) => (
                <div key={idx} className="action-pill">
                  <code className="mono">{act.type}</code>
                  {act.new_ts && <strong className="mono"> → {act.new_ts}</strong>}
                  <span>: {act.note}</span>
                </div>
              ))}
            </div>
          )}
          {proposal.missing_information.length > 0 && (
            <div className="escalation-box">
              <strong>Escalated — Missing Information:</strong>
              <ul>
                {proposal.missing_information.map((m, i) => (
                  <li key={i}>{m}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="citations-block">
            <span className="section-label">Grounded Policy Citations ({proposal.citations.length})</span>
            {proposal.citations.map((c) => (
              <div key={c.chunk_id} className="citation-item">
                <span className="mono citation-id">{c.chunk_id}</span>
                <p className="small">"{c.quote}"</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {activeRuleOutcomes.length > 0 && (
        <div className="card-block">
          <div className="section-label">
            Backend Rules Validator ({activeRuleOutcomes.filter((r) => r.passed).length}/{activeRuleOutcomes.length} Passed)
          </div>
          <div className="rules-grid">
            {activeRuleOutcomes.map((r) => (
              <div
                key={r.rule}
                className={`rule-row ${
                  r.passed
                    ? 'rule-pass'
                    : r.outcome === 'insufficient_evidence'
                    ? 'rule-unknown'
                    : 'rule-fail'
                }`}
              >
                <span className="rule-icon">
                  {r.passed
                    ? '✓ PASS'
                    : r.outcome === 'insufficient_evidence'
                    ? '? NEEDS EVIDENCE'
                    : '✕ FAIL'}
                </span>
                <span className="mono rule-code">{r.rule}</span>
                <span className="small">{r.detail}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {mode === 'edit' && (
        <div className="edit-box">
          <div className="section-label">Manual Manager Correction (the backend re-validates it on submit)</div>
          <label className="field-label">
            Corrected Out-Punch Time ({item.timezone}):
            <input type="time" value={editedTime} onChange={(e) => setEditedTime(e.target.value)} className="input-field mono" />
          </label>
          <label className="field-label">
            Audit Note (optional):
            <input type="text" placeholder="e.g., Confirmed exit timestamp with security log" value={comment} onChange={(e) => setComment(e.target.value)} className="input-field" />
          </label>
          {editCheck && !editCheck.valid && (
            <div className="banner banner-error" role="alert">{editCheck.error}</div>
          )}
          <div className="button-row">
            <button type="button" className="btn-primary" disabled={!canDecide || !editCheck?.valid || submitting} onClick={() => handleSubmit('edited', { editedTime, comment })}>
              Save & Re-Validate Edit
            </button>
            <button type="button" className="btn-secondary" onClick={() => setMode('review')}>Cancel (Esc)</button>
          </div>
        </div>
      )}

      {mode === 'reject' && (
        <div className="edit-box">
          <div className="section-label">Reject Proposal (Reason Code Required)</div>
          <label className="field-label">
            Reason Code:
            <select value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} className="input-field">
              <option value="INSUFFICIENT_EVIDENCE">INSUFFICIENT_EVIDENCE — Needs employee confirmation</option>
              <option value="POLICY_MISMATCH">POLICY_MISMATCH — Incorrect pay/break treatment</option>
              <option value="UNAUTHORIZED_OT">UNAUTHORIZED_OT — Overtime not pre-approved</option>
              <option value="TIME_INACCURATE">TIME_INACCURATE — Suggested timestamp disagrees with log</option>
            </select>
          </label>
          <label className="field-label">
            Manager Comment:
            <input type="text" placeholder="Explain why proposal is rejected..." value={comment} onChange={(e) => setComment(e.target.value)} className="input-field" />
          </label>
          <div className="button-row">
            <button type="button" className="btn-danger" disabled={!canDecide || submitting} onClick={() => handleSubmit('rejected', { reasonCode: rejectReason, comment })}>
              Confirm Rejection
            </button>
            <button type="button" className="btn-secondary" onClick={() => setMode('review')}>Cancel (Esc)</button>
          </div>
        </div>
      )}

      {mode === 'review' && item.status !== 'resolved' && (
        <div className="panel-footer">
          <button
            type="button"
            className="btn-primary"
            disabled={!canDecide || Boolean(item.stale_warning) || !proposal || !proposal.validator_passed || proposal.decision === 'escalate' || submitting}
            onClick={() => handleSubmit('approved', {})}
          >
            Approve Proposal (A)
          </button>
          <button type="button" className="btn-secondary" disabled={!canDecide} onClick={() => setMode('edit')}>
            Edit Fix (E)
          </button>
          <button type="button" className="btn-danger-outline" disabled={!canDecide} onClick={() => setMode('reject')}>
            Reject (R)
          </button>
        </div>
      )}
    </aside>
  );
}
