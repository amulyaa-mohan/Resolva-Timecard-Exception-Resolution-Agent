import { useEffect, useState } from 'react';
import { previewManualEditValidation } from '../lib/api';
import { ExceptionItem, Role } from '../types/contracts';
import { PunchTimeline } from './PunchTimeline';

interface ResolutionPanelProps {
  item: ExceptionItem | null;
  role: Role;
  aiEnabled: boolean;
  onClose: () => void;
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
  const editCheck =
    mode === 'edit' ? previewManualEditValidation(item, editedTime) : null;
  const activeRuleOutcomes =
    mode === 'edit' && editCheck
      ? editCheck.outcomes
      : proposal?.rule_outcomes ?? [];

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
      {/* Header */}
      <div className="panel-header">
        <div>
          <div className="panel-badges">
            <span className={`badge badge-${item.severity}`}>
              {item.severity === 'problem' ? 'PROBLEM (Blocks Pay)' : 'WARNING'}
            </span>
            <span className="mono badge-neutral">{item.code}</span>
            <span className="mono badge-neutral">{item.policy_pack_id}</span>
          </div>
          <h2>
            {item.employee_name}{' '}
            <span className="mono muted">({item.employee_id})</span>
          </h2>
          <p className="muted small">
            {item.job} • {item.location} • Work Date: <span className="mono">{item.work_date}</span> ({item.timezone})
          </p>
        </div>
        <button type="button" className="btn-ghost" onClick={onClose} aria-label="Close panel">
          ✕
        </button>
      </div>

      {/* Role authorization warning */}
      {!canDecide && (
        <div className="banner banner-warn" role="alert">
          <strong>Read-only role ({role}):</strong> Only an authorized <code>manager</code> can approve, edit, or reject timecard corrections. Switch role in the top header to decide.
        </div>
      )}

      {/* Already resolved state */}
      {item.status === 'resolved' && item.resolution && (
        <div className="banner banner-success">
          <strong>Resolved ({item.resolution.decision.toUpperCase()})</strong> by {item.resolution.decided_by} • Trace{' '}
          <span className="mono">{item.resolution.trace_id}</span>
          {item.resolution.comment ? ` — "${item.resolution.comment}"` : ''}
        </div>
      )}

      {/* Observed Evidence Section */}
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

      {/* Before / After Hours Diff */}
      <div className="diff-grid">
        <div className="diff-box">
          <span className="section-label">Before Correction</span>
          <div className="mono">Regular: {item.before_hours.regular_hours}</div>
          <div className="mono">Overtime: {item.before_hours.overtime_hours}</div>
          <div className="small muted">{item.before_hours.pay_status}</div>
        </div>
        <div className="diff-box diff-after">
          <span className="section-label">After Proposed Fix</span>
          <div className="mono">
            Regular: {item.after_hours?.regular_hours ?? item.before_hours.regular_hours}
          </div>
          <div className="mono">
            Overtime: {item.after_hours?.overtime_hours ?? item.before_hours.overtime_hours}
          </div>
          <div className="small">
            {item.after_hours?.pay_status ?? 'Manual manager resolution required'}
          </div>
        </div>
      </div>

      {/* AI Proposal Card (Strictly Violet Labeled) */}
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

          {/* Policy Citations */}
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

      {/* Deterministic Validator Checklist */}
      {activeRuleOutcomes.length > 0 && (
        <div className="card-block">
          <div className="section-label">
            Deterministic Rules Validator ({activeRuleOutcomes.filter((r) => r.passed).length}/{activeRuleOutcomes.length} Passed)
          </div>
          <div className="rules-grid">
            {activeRuleOutcomes.map((r) => (
              <div key={r.rule} className={`rule-row ${r.passed ? 'rule-pass' : 'rule-fail'}`}>
                <span className="rule-icon">{r.passed ? '✓ PASS' : '✕ FAIL'}</span>
                <span className="mono rule-code">{r.rule}</span>
                <span className="small">{r.detail}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Interactive Edit Mode */}
      {mode === 'edit' && (
        <div className="edit-box">
          <div className="section-label">Manual Manager Correction (Live Validator Re-Check)</div>
          <label className="field-label">
            Corrected Out-Punch Time ({item.timezone}):
            <input
              type="time"
              value={editedTime}
              onChange={(e) => setEditedTime(e.target.value)}
              className="input-field mono"
            />
          </label>
          <label className="field-label">
            Audit Note (optional):
            <input
              type="text"
              placeholder="e.g., Confirmed exit timestamp with security log"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="input-field"
            />
          </label>
          {editCheck && !editCheck.valid && (
            <div className="banner banner-error" role="alert">
              {editCheck.error}
            </div>
          )}
          <div className="button-row">
            <button
              type="button"
              className="btn-primary"
              disabled={!canDecide || !editCheck?.valid || submitting}
              onClick={() => handleSubmit('edited', { editedTime, comment })}
            >
              Save & Re-Validate Edit
            </button>
            <button type="button" className="btn-secondary" onClick={() => setMode('review')}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Interactive Reject Mode */}
      {mode === 'reject' && (
        <div className="edit-box">
          <div className="section-label">Reject Proposal (Reason Code Required)</div>
          <label className="field-label">
            Reason Code:
            <select
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              className="input-field"
            >
              <option value="INSUFFICIENT_EVIDENCE">INSUFFICIENT_EVIDENCE — Needs employee confirmation</option>
              <option value="POLICY_MISMATCH">POLICY_MISMATCH — Incorrect pay/break treatment</option>
              <option value="UNAUTHORIZED_OT">UNAUTHORIZED_OT — Overtime not pre-approved</option>
              <option value="TIME_INACCURATE">TIME_INACCURATE — Suggested timestamp disagrees with log</option>
            </select>
          </label>
          <label className="field-label">
            Manager Comment:
            <input
              type="text"
              placeholder="Explain why proposal is rejected..."
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="input-field"
            />
          </label>
          <div className="button-row">
            <button
              type="button"
              className="btn-danger"
              disabled={!canDecide || submitting}
              onClick={() => handleSubmit('rejected', { reasonCode: rejectReason, comment })}
            >
              Confirm Rejection
            </button>
            <button type="button" className="btn-secondary" onClick={() => setMode('review')}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Primary Action Footer */}
      {mode === 'review' && item.status !== 'resolved' && (
        <div className="panel-footer">
          <button
            type="button"
            className="btn-primary"
            disabled={!canDecide || !proposal || !proposal.validator_passed || proposal.decision === 'escalate' || submitting}
            title={
              !proposal?.validator_passed
                ? 'Blocked: AI proposal did not pass deterministic validation'
                : 'Approve AI proposal (Shortcut: A)'
            }
            onClick={() => handleSubmit('approved', {})}
          >
            Approve Proposal (A)
          </button>
          <button
            type="button"
            className="btn-secondary"
            disabled={!canDecide}
            onClick={() => setMode('edit')}
          >
            Edit Fix (E)
          </button>
          <button
            type="button"
            className="btn-danger-outline"
            disabled={!canDecide}
            onClick={() => setMode('reject')}
          >
            Reject (R)
          </button>
        </div>
      )}
    </aside>
  );
}
