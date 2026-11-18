import { useTranslation } from "../lib/locale";
﻿import { useEffect, useState } from 'react';
import { previewManualEditValidation } from '../lib/api';
import { ExceptionItem, Role, UILang } from '../types/contracts';
import { RecordedPunchesCard } from './RecordedPunchesCard';
import { PunchTimeline } from './PunchTimeline';

interface ResolutionPanelProps {
  item: ExceptionItem | null;
  role: Role;
  lang?: UILang;
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
  lang = 'en',
  aiEnabled,
  onClose,
  onSimulateStale,
  onRepropose,
  onDecide,
}: ResolutionPanelProps) {
  const { tr } = useTranslation();
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
      <aside className="resolution-panel empty-panel" aria-label={tr("Exception detail")}>
        <div className="empty-state">
          <h3>{tr("Select an exception")}</h3>
          <p>{"" + tr("Click any row or press") + " "}<strong>J / K</strong>{" " + tr("to inspect evidence, citations, and rule checks.") + ""}</p>
        </div>
      </aside>
    );
  }

  const canDecide = role === 'manager' || role === 'admin';
  const proposal = aiEnabled ? item.proposal : undefined;
  const editCheck = mode === 'edit' ? previewManualEditValidation(item, editedTime) : null;
  const activeRuleOutcomes = mode === 'edit' && editCheck ? editCheck.outcomes : proposal?.rule_outcomes ?? [];

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
    <aside className="resolution-panel" aria-label={`${tr("Exception detail")} · ${item.id}`}>
      <div className="panel-header">
        <div>
          <div className="panel-badges">
            <span className={`badge badge-${item.severity}`}>
              {tr(item.severity === 'problem' ? 'PROBLEM (Blocks Pay)' : 'WARNING')}
            </span>
            <span className="badge-neutral" title={item.code}>{tr(item.code)}</span>
            <span className="mono badge-neutral">{item.policy_pack_id}</span>
            <span className="mono badge-neutral">v{item.evidence_version}</span>
          </div>
          <h2>
            {item.employee_name} <span className="mono muted">({item.employee_id})</span>
          </h2>
          <p className="muted small">
            {tr(item.job)} • {tr(item.location)}{" " + tr("• Work Date:") + " "}<span className="tnum">{item.work_date}</span> ({item.timezone})
          </p>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {item.status !== 'resolved' && !item.stale_warning && (
            <button
              type="button"
              className="btn-secondary small"
              title={tr("Simulate a new punch arriving while viewing this proposal")}
              onClick={() => onSimulateStale(item.id)}
            >{tr("Simulate Stale (409)")}</button>
          )}
          <button type="button" className="btn-ghost" onClick={onClose} aria-label={tr("Close panel (Esc)")}>
            ✕
          </button>
        </div>
      </div>

      {item.stale_warning && (
        <div className="banner banner-error" role="alert">
          <strong>{tr("Stale Proposal Blocked (HTTP 409):")}</strong>{" " + tr("Underlying punch evidence updated to v") + ""}{item.evidence_version + 1}{" " + tr("after this AI draft was generated. Approval is blocked until re-proposed.") + ""}{' '}
          <button type="button" className="btn-primary" style={{ marginLeft: 8, padding: '4px 10px' }} onClick={() => onRepropose(item.id)}>{tr("Re-Propose on Latest Evidence")}</button>
        </div>
      )}

      {!canDecide && (
        <div className="banner banner-warn" role="alert">
          <strong>{tr("Access Denied for Edits (")}{role}):</strong>{" " + tr("Only an authorized") + " "}<code>{tr("manager")}</code>{" " + tr("can approve, edit, or reject timecard corrections.") + ""}</div>
      )}

      {item.status === 'resolved' && item.resolution && (
        <div className="banner banner-success">
          <strong>{tr("Resolved (")}{item.resolution.decision.toUpperCase()})</strong>{" " + tr("by") + " "}{item.resolution.decided_by}{" " + tr("• Trace") + ""}{' '}
          <span className="mono">{item.resolution.trace_id}</span>
          {item.resolution.comment ? ` — "${item.resolution.comment}"` : ''}
        </div>
      )}

      <PunchTimeline item={item} editedTimeHHMM={mode === 'edit' ? editedTime : null} />

      <RecordedPunchesCard item={item} lang={lang} />

      {item.employee_note && (
        <div className="card-block">
          <div className="untrusted-note" style={{ marginTop: 0 }}>
            <span className="untrusted-tag">{tr("UNTRUSTED EMPLOYEE NOTE (EVIDENCE ONLY)")}</span>
            <p>"{item.employee_note}"</p>
          </div>
        </div>
      )}

      <div className="diff-grid">
        <div className="diff-box">
          <span className="section-label">{tr("Before Correction")}</span>
          <div className="hours-line">{"" + tr("Regular:") + " "}{item.before_hours.regular_hours}</div>
          <div className="hours-line">{"" + tr("Overtime:") + " "}{item.before_hours.overtime_hours}</div>
          <div className="small muted">{tr(item.before_hours.pay_status)}</div>
        </div>
        <div className="diff-box diff-after">
          <span className="section-label">{tr("After Proposed Fix")}</span>
          <div className="hours-line">{"" + tr("Regular:") + " "}{item.after_hours?.regular_hours ?? item.before_hours.regular_hours}</div>
          <div className="hours-line">{"" + tr("Overtime:") + " "}{item.after_hours?.overtime_hours ?? item.before_hours.overtime_hours}</div>
          <div className="small">{tr(item.after_hours?.pay_status ?? 'Manual manager resolution required')}</div>
        </div>
      </div>

      {!aiEnabled ? (
        <div className="banner banner-warn">
          <strong>{tr("AI Kill-Switch Active (Rules-Only Mode):")}</strong>{" " + tr("AI proposal generation is disabled. Deterministic detection and manual manager resolution remain active.") + ""}</div>
      ) : proposal ? (
        <div className="ai-card">
          <div className="ai-card-header">
            <span className="badge-ai">{tr("AI DRAFT")}</span>
            <span className="small tnum">{"" + tr("Confidence:") + " "}<strong>{Math.round(proposal.confidence * 100)}%</strong>{" " + tr("• Model:") + " "}<code className="mono">{proposal.model_id}</code>{" " + tr("• Prompt:") + " "}<code className="mono">{proposal.prompt_hash}</code></span>
          </div>
          <p className="ai-rationale">{tr(proposal.rationale)}</p>
          {proposal.actions.length > 0 && (
            <div className="proposed-actions">
              <span className="section-label">{tr("Proposed Action")}</span>
              {proposal.actions.map((act, idx) => (
                <div key={idx} className="action-pill">
                  <code className="mono">{act.type}</code>
                  {act.new_ts && <strong className="mono"> → {act.new_ts}</strong>}
                  <span>: {tr(act.note ?? '')}</span>
                </div>
              ))}
            </div>
          )}
          {proposal.missing_information.length > 0 && (
            <div className="escalation-box">
              <strong>{tr("Escalated — Missing Information:")}</strong>
              <ul>
                {proposal.missing_information.map((m, i) => (
                  <li key={i}>{tr(m)}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="citations-block">
            <span className="section-label">{tr("Grounded Policy Citations (")}{proposal.citations.length})</span>
            {proposal.citations.map((c) => (
              <div key={c.chunk_id} className="citation-item">
                <span className="mono citation-id">{c.chunk_id}</span>
                <p className="small">"{tr(c.quote)}"</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {activeRuleOutcomes.length > 0 && (
        <div className="card-block">
          <div className="section-label">{tr("Deterministic Rules Validator (")}{activeRuleOutcomes.filter((r) => r.passed).length}/{activeRuleOutcomes.length}{" " + tr("Passed)") + ""}</div>
          <div className="rules-grid">
            {activeRuleOutcomes.map((r) => (
              <div key={r.rule} className={`rule-row ${r.passed ? 'rule-pass' : 'rule-fail'}`}>
                <span className="rule-icon">{tr(r.passed ? '✓ PASS' : '✕ FAIL')}</span>
                <span className="rule-code" title={r.rule}>{tr(r.rule)}</span>
                <span className="small">{tr(r.detail)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {mode === 'edit' && (
        <div className="edit-box">
          <div className="section-label">{tr("Manual Manager Correction (Live Validator Re-Check)")}</div>
          <label className="field-label">{tr("Corrected Out-Punch Time (")}{item.timezone}):
            <input type="time" value={editedTime} onChange={(e) => setEditedTime(e.target.value)} className="input-field tnum" />
          </label>
          <label className="field-label">{tr("Audit Note (optional):")}<input type="text" placeholder={tr("e.g., Confirmed exit timestamp with security log")} value={comment} onChange={(e) => setComment(e.target.value)} className="input-field" />
          </label>
          {editCheck && !editCheck.valid && (
            <div className="banner banner-error" role="alert">{tr(editCheck.error ?? '')}</div>
          )}
          <div className="button-row">
            <button type="button" className="btn-primary" disabled={!canDecide || !editCheck?.valid || submitting} onClick={() => handleSubmit('edited', { editedTime, comment })}>{tr("Save & Re-Validate Edit")}</button>
            <button type="button" className="btn-secondary" onClick={() => setMode('review')}>{tr("Cancel (Esc)")}</button>
          </div>
        </div>
      )}

      {mode === 'reject' && (
        <div className="edit-box">
          <div className="section-label">{tr("Reject Proposal (Reason Code Required)")}</div>
          <label className="field-label">{tr("Reason Code:")}<select value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} className="input-field">
              <option value="INSUFFICIENT_EVIDENCE">{tr("INSUFFICIENT_EVIDENCE — Needs employee confirmation")}</option>
              <option value="POLICY_MISMATCH">{tr("POLICY_MISMATCH — Incorrect pay/break treatment")}</option>
              <option value="UNAUTHORIZED_OT">{tr("UNAUTHORIZED_OT — Overtime not pre-approved")}</option>
              <option value="TIME_INACCURATE">{tr("TIME_INACCURATE — Suggested timestamp disagrees with log")}</option>
            </select>
          </label>
          <label className="field-label">{tr("Manager Comment:")}<input type="text" placeholder={tr("Explain why proposal is rejected...")} value={comment} onChange={(e) => setComment(e.target.value)} className="input-field" />
          </label>
          <div className="button-row">
            <button type="button" className="btn-danger" disabled={!canDecide || submitting} onClick={() => handleSubmit('rejected', { reasonCode: rejectReason, comment })}>{tr("Confirm Rejection")}</button>
            <button type="button" className="btn-secondary" onClick={() => setMode('review')}>{tr("Cancel (Esc)")}</button>
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
          >{tr("Approve Proposal (A)")}</button>
          <button type="button" className="btn-secondary" disabled={!canDecide} onClick={() => setMode('edit')}>{tr("Edit Fix (E)")}</button>
          <button type="button" className="btn-danger-outline" disabled={!canDecide} onClick={() => setMode('reject')}>{tr("Reject (R)")}</button>
        </div>
      )}
    </aside>
  );
}



