import { useEffect, useState } from 'react';
import { checkEditedTime } from '../lib/api';
import { ExceptionItem, Role, UILang } from '../types/contracts';
import { RecordedPunchesCard } from './RecordedPunchesCard';
import { PunchTimeline } from './PunchTimeline';
import { useTranslation } from '../lib/locale';

export const EXCEPTION_TYPE_TITLES: Record<string, string> = {
  MISSING_PUNCH: 'Missing punch',
  SPREAD_OVER_BREACH: 'Spread-over limit exceeded',
  MEAL_BREAK_BREACH: 'Meal break compliance breach',
  OVERTIME_RISK: 'Overtime limit risk',
  OVERLAPPING_SHIFT: 'Overlapping shift schedule',
  SCHEDULE_DEVIATION: 'Schedule deviation',
};

export function getHumanExceptionTitle(code: string): string {
  return EXCEPTION_TYPE_TITLES[code] || code.replace(/_/g, ' ');
}

export type ProposalState =
  | 'resolved'
  | 'stale'
  | 'escalated'
  | 'blocked'
  | 'eligible'
  | 'generating'
  | 'no_draft';

export interface ProposalStateDetails {
  state: ProposalState;
  label: string;
  badgeClass: string;
  description: string;
  canApprove: boolean;
  approvalDisabledReason?: string;
}

export function computeProposalState(
  item: ExceptionItem,
  aiEnabled: boolean,
  confidenceThreshold: number,
  isGenerating: boolean
): ProposalStateDetails {
  if (isGenerating) {
    return {
      state: 'generating',
      label: 'Generating AI Draft...',
      badgeClass: 'badge-generating',
      description: 'Generating policy-grounded recommendation and running deterministic rule checks.',
      canApprove: false,
      approvalDisabledReason: 'Draft generation is currently in progress.',
    };
  }

  if (item.status === 'resolved') {
    return {
      state: 'resolved',
      label: `Resolved (${item.resolution?.decision.toUpperCase() ?? 'APPROVED'})`,
      badgeClass: 'badge-pass',
      description: item.resolution
        ? `Decided by ${item.resolution.decided_by} (Trace ${item.resolution.trace_id}).`
        : 'Recorded by the server. See the audit trail for who decided and when.',
      canApprove: false,
      approvalDisabledReason: 'This exception has already been resolved.',
    };
  }

  if (item.stale_warning) {
    return {
      state: 'stale',
      label: 'Stale Proposal (HTTP 409)',
      badgeClass: 'badge-escalated',
      description: 'Underlying punch evidence was updated after this draft was generated.',
      canApprove: false,
      approvalDisabledReason: 'Approval is blocked by concurrency guard (HTTP 409). Click "Re-check evidence" to refresh.',
    };
  }

  if (!aiEnabled) {
    return {
      state: 'blocked',
      label: 'Rules-Only (AI Disabled)',
      badgeClass: 'badge-neutral',
      description: 'AI draft generation is disabled via kill-switch. Manual manager resolution required.',
      canApprove: false,
      approvalDisabledReason: 'AI is disabled. Please resolve via "Edit Fix" or "Reject".',
    };
  }

  // The backend ran the pipeline but returned no usable draft: show its own reason.
  if (!item.proposal && (item.draft_status === 'blocked' || item.draft_status === 'escalated')) {
    const escalated = item.draft_status === 'escalated';
    const reason = item.draft_reasons?.[0] ?? 'The backend did not produce a draft that can be approved.';
    return {
      state: escalated ? 'escalated' : 'blocked',
      label: escalated ? 'Escalated for Review' : 'Validation Blocked',
      badgeClass: escalated ? 'badge-escalated' : 'badge-problem',
      description: reason,
      canApprove: false,
      approvalDisabledReason: reason,
    };
  }

  if (!item.proposal) {
    return {
      state: 'no_draft',
      label: 'No proposal yet',
      badgeClass: 'badge-neutral',
      description: 'No AI proposal has been generated for this exception yet.',
      canApprove: false,
      approvalDisabledReason: 'No proposal exists yet. Click "Draft with AI" or use "Edit Fix" to resolve manually.',
    };
  }

  const { proposal } = item;

  if (proposal.decision === 'escalate' || item.status === 'escalated') {
    return {
      state: 'escalated',
      label: 'Escalated for Review',
      badgeClass: 'badge-escalated',
      description: item.draft_reasons?.[0] ?? 'This case needs a manager review and cannot be approved automatically.',
      canApprove: false,
      approvalDisabledReason: 'Proposal is escalated for compliance/manager review; cannot be automated.',
    };
  }

  if (!proposal.validator_passed || proposal.confidence < confidenceThreshold) {
    const reason = !proposal.validator_passed
      ? item.draft_reasons?.[0] ?? 'Deterministic validator checks failed.'
      : `AI confidence (${Math.round(proposal.confidence * 100)}%) is below threshold (${Math.round(confidenceThreshold * 100)}%).`;
    return {
      state: 'blocked',
      label: 'Validation Blocked',
      badgeClass: 'badge-problem',
      description: reason,
      canApprove: false,
      approvalDisabledReason: reason,
    };
  }

  return {
    state: 'eligible',
    label: `AI-Ready (${Math.round(proposal.confidence * 100)}%)`,
    badgeClass: 'badge-ai',
    description: 'Passed all deterministic rule validations and meets confidence threshold.',
    canApprove: true,
  };
}

export interface ResolutionPanelProps {
  item: ExceptionItem | null;
  role: Role;
  lang?: UILang;
  aiEnabled: boolean;
  confidenceThreshold?: number;
  activeTab?: string;
  totalEscalations?: number;
  onClose: () => void;
  /** Re-read the case's evidence from the server; marks the draft stale if it changed. */
  onCheckEvidence: (id: string) => Promise<void>;
  /** Ask the backend for a new draft on the latest evidence. */
  onRepropose: (id: string) => Promise<void>;
  onDecide: (
    item: ExceptionItem,
    decision: 'approved' | 'edited' | 'rejected',
    details: { editedTime?: string; reasonCode?: string; comment?: string }
  ) => Promise<void>;
}

export function ResolutionPanel({
  item,
  role,
  lang = 'en',
  aiEnabled,
  confidenceThreshold = 0.75,
  activeTab = 'inbox',
  totalEscalations = 0,
  onClose,
  onCheckEvidence,
  onRepropose,
  onDecide,
}: ResolutionPanelProps) {
  const { tr } = useTranslation();
  const [mode, setMode] = useState<'review' | 'edit' | 'reject'>('review');
  const [editedTime, setEditedTime] = useState('18:00');
  const [rejectReason, setRejectReason] = useState('INSUFFICIENT_EVIDENCE');
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  useEffect(() => {
    setMode('review');
    setComment('');
    setSubmitting(false);
    setIsGenerating(false);
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

  const copyToClipboard = (key: string, text: string) => {
    navigator.clipboard?.writeText(text).then(() => {
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 2000);
    });
  };

  const runBusy = async (work: () => Promise<void>) => {
    if (!item || isGenerating) return;
    setIsGenerating(true);
    try {
      await work();
    } finally {
      setIsGenerating(false);
    }
  };
  const handleDraftClick = () => runBusy(() => onRepropose(item!.id));
  const handleRecheckClick = () => runBusy(() => onCheckEvidence(item!.id));

  // Empty state handling
  if (!item) {
    return (
      <aside className="resolution-panel empty-panel" aria-label={tr("Exception detail")}>
        <div className="empty-state">
          {activeTab === 'escalations' ? (
            <>
              <h3>{tr("No Escalation Selected")}</h3>
              <p className="muted">
                {totalEscalations === 0
                  ? tr("There are no active escalations requiring attention in the system.")
                  : tr("No escalation is currently selected. Adjust filters or pick an escalation from the list.")}
              </p>
            </>
          ) : (
            <>
              <h3>{tr("Select an exception")}</h3>
              <p className="muted">{tr("Click any row or press")} <strong>J / K</strong> {tr("to inspect evidence, citations, and rule checks.")}</p>
            </>
          )}
        </div>
      </aside>
    );
  }

  const canDecide = role === 'manager' || role === 'admin';
  const proposalStateInfo = computeProposalState(item, aiEnabled, confidenceThreshold, isGenerating);
  const proposal = aiEnabled ? item.proposal : undefined;
  // Only the time format is checked here. Whether the correction is allowed is decided by the
  // backend's deterministic validator when the decision is submitted.
  const editCheck = mode === 'edit' ? checkEditedTime(item, editedTime) : null;
  const activeRuleOutcomes = mode === 'edit' ? [] : proposal?.rule_outcomes ?? [];

  const handleSubmit = async (
    decision: 'approved' | 'edited' | 'rejected',
    details: { editedTime?: string; reasonCode?: string; comment?: string }
  ) => {
    if (!canDecide || submitting) return;
    setSubmitting(true);
    try {
      await onDecide(item, decision, details);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <aside className="resolution-panel" aria-label={`${tr("Exception detail")} · ${item.id}`}>
      {/* 1. Header with clear human hierarchy and responsive wrapping actions */}
      <div className="panel-header">
        <div className="panel-header-main">
          <div className="panel-badges">
            <span className={`badge ${proposalStateInfo.badgeClass}`}>
              {tr(proposalStateInfo.label)}
            </span>
            <span className={`badge badge-${item.severity}`}>
              {tr(item.severity === 'problem' ? 'PROBLEM (Blocks Pay)' : 'WARNING')}
            </span>
            <span className="badge-neutral mono">{item.policy_pack_id}</span>
          </div>

          <div className="panel-title-block">
            <div className="human-exception-type">
              {tr(getHumanExceptionTitle(item.code))}
            </div>
            <h2 className="panel-employee-heading">
              {item.employee_name} <span className="mono muted" style={{ fontSize: '13px', fontWeight: 400 }}>({item.employee_id})</span>
            </h2>
            <div className="panel-meta-line muted small">
              <span>{tr(item.job)}</span> • <span>{tr(item.location)}</span> • <span>{tr("Work Date:")} <strong className="tnum">{item.work_date}</strong> ({item.timezone})</span>
            </div>
          </div>
        </div>

        <div className="panel-header-actions">
          {(!item.proposal || item.status === 'open') && item.status !== 'resolved' && (
            <button
              type="button"
              className="btn-primary small action-btn-visible"
              disabled={isGenerating || !aiEnabled}
              onClick={handleDraftClick}
              title={tr("Draft with AI policy proposal")}
            >
              {isGenerating ? tr('Drafting...') : tr('Draft with AI')}
            </button>
          )}

          {item.status !== 'resolved' && (
            <button
              type="button"
              className="btn-secondary small action-btn-visible"
              disabled={isGenerating}
              onClick={handleRecheckClick}
              title={tr("Re-read this case's evidence from the server")}
            >
              {tr("Re-check evidence")}
            </button>
          )}


          <button
            type="button"
            className="btn-ghost"
            onClick={onClose}
            aria-label={tr("Close panel (Esc)")}
            title={tr("Close panel (Esc)")}
          >
            ✕
          </button>
        </div>
      </div>

      {/* 2. Proposal / Readiness Status Banners */}
      {item.stale_warning && (
        <div className="banner banner-error" role="alert">
          <div>
            <strong>{tr("Stale Proposal Blocked (HTTP 409):")}</strong> {tr("The punch evidence changed after this draft was generated. Approval is blocked until a new draft is made.")}{' '}
            <button type="button" className="btn-primary small" style={{ marginLeft: 8 }} onClick={handleDraftClick} disabled={isGenerating}>
              {tr("Re-Propose on Latest Evidence")}
            </button>
          </div>
        </div>
      )}

      {!canDecide && (
        <div className="banner banner-warn" role="alert">
          <strong>{tr("Read-Only Mode")} ({role}):</strong> {tr("Only an authorized")} <code>{tr("manager")}</code> {tr("or admin can approve, edit, or reject timecard exceptions.")}
        </div>
      )}

      {item.status === 'resolved' && item.resolution && (
        <div className="banner banner-success" role="status">
          <strong>{tr("Resolved")} ({item.resolution.decision.toUpperCase()})</strong> {tr("by")} {item.resolution.decided_by} at {item.resolution.decided_at.slice(0, 16)} • {tr("Trace")}{' '}
          <span className="mono">{item.resolution.trace_id}</span>
          {item.resolution.comment ? ` — "${item.resolution.comment}"` : ''}
        </div>
      )}

      {/* 3. Timeline with non-overlapping break markers, actual range, and timezone */}
      <PunchTimeline item={item} editedTimeHHMM={mode === 'edit' ? editedTime : null} />

      {/* 4. Observed Facts (Recorded punches card with copyable IDs and language prop) */}
      <RecordedPunchesCard item={item} lang={lang} />

      {item.employee_note && (
        <div className="card-block">
          <div className="untrusted-note" style={{ marginTop: 0 }}>
            <span className="untrusted-tag">{tr("UNTRUSTED EMPLOYEE NOTE (EVIDENCE ONLY)")}</span>
            <p>"{item.employee_note}"</p>
          </div>
        </div>
      )}

      {/* 5. Before & After Hours Diff Breakdown */}
      <div className="diff-grid">
        <div className="diff-box">
          <span className="section-label">{tr("Before Correction")}</span>
          <div className="hours-line">{tr("Regular:")} {item.before_hours.regular_hours}</div>
          <div className="hours-line">{tr("Overtime:")} {item.before_hours.overtime_hours}</div>
          <div className="small muted">{tr(item.before_hours.pay_status)}</div>
        </div>
        <div className="diff-box diff-after">
          <span className="section-label">{tr("After Proposed Fix")}</span>
          <div className="hours-line">{tr("Regular:")} {item.after_hours?.regular_hours ?? item.before_hours.regular_hours}</div>
          <div className="hours-line">{tr("Overtime:")} {item.after_hours?.overtime_hours ?? item.before_hours.overtime_hours}</div>
          <div className="small">{tr(item.after_hours?.pay_status ?? 'Manual manager resolution required')}</div>
        </div>
      </div>

      {/* 6. AI Proposal / No-Draft / Escalation State */}
      {!aiEnabled ? (
        <div className="banner banner-warn">
          <strong>{tr("AI Kill-Switch Active (Rules-Only Mode):")}</strong> {tr("AI proposal drafting is disabled. Deterministic detection and manual manager edits remain active.")}
        </div>
      ) : !proposal ? (
        <div className="ai-card" style={{ background: '#f8fafc', borderColor: '#e2e8f0' }}>
          <div className="ai-card-header">
            <span className="badge-neutral">{tr("NO PROPOSAL YET")}</span>
          </div>
          <p className="small muted" style={{ margin: '6px 0' }}>
            {tr('No automated proposal has been generated for this exception. Click')} <strong>"{tr("Draft with AI")}"</strong> {tr('in the header to evaluate policy rules and infer a recommendation, or use')} <strong>"{tr("Edit Fix")}"</strong> {tr('below to resolve manually.')}
          </p>
        </div>
      ) : (
        <div className="ai-card">
          <div className="ai-card-header">
            <span className="badge-ai">{tr("AI DRAFT")}</span>
            <span className="small tnum">{tr("Confidence:")} <strong>{Math.round(proposal.confidence * 100)}%</strong> • {tr("Model:")} <code className="mono">{proposal.model_id}</code></span>
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
      )}

      {/* 7. Deterministic Validator Checklist */}
      {activeRuleOutcomes.length > 0 && (
        <div className="card-block">
          <div className="section-label">{tr("Deterministic Rules Validator (")}{activeRuleOutcomes.filter((r) => r.passed).length}/{activeRuleOutcomes.length}{" " + tr("Passed)")}</div>
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

      {/* 8. Expandable Technical Details (IDs, Evidence Hash, Canonical Codes, Versioning) */}
      <details className="tech-details-box">
        <summary className="tech-details-summary">
          <span>{tr("Technical Identifiers & Audit Details")}</span>
          <span className="mono small muted">{item.id}</span>
        </summary>
        <div className="tech-details-body">
          <div className="tech-grid">
            <div className="tech-item">
              <span className="tech-label">{tr("Canonical Code:")}</span>
              <div className="tech-val-row">
                <code className="mono">{item.code}</code>
                <button
                  type="button"
                  className="tech-copy-btn"
                  onClick={() => copyToClipboard('code', item.code)}
                >
                  {copiedKey === 'code' ? tr('Copied!') : tr('Copy')}
                </button>
              </div>
            </div>

            <div className="tech-item">
              <span className="tech-label">{tr("Exception ID:")}</span>
              <div className="tech-val-row">
                <code className="mono">{item.id}</code>
                <button
                  type="button"
                  className="tech-copy-btn"
                  onClick={() => copyToClipboard('id', item.id)}
                >
                  {copiedKey === 'id' ? tr('Copied!') : tr('Copy')}
                </button>
              </div>
            </div>

            <div className="tech-item">
              <span className="tech-label">{tr("Employee ID:")}</span>
              <div className="tech-val-row">
                <code className="mono">{item.employee_id}</code>
                <button
                  type="button"
                  className="tech-copy-btn"
                  onClick={() => copyToClipboard('empid', item.employee_id)}
                >
                  {copiedKey === 'empid' ? tr('Copied!') : tr('Copy')}
                </button>
              </div>
            </div>

            <div className="tech-item">
              <span className="tech-label">{tr("Evidence Version:")}</span>
              <div className="tech-val-row">
                <code className="mono">v{item.evidence_version}</code>
              </div>
            </div>

            <div className="tech-item">
              <span className="tech-label">{tr("Policy Pack:")}</span>
              <div className="tech-val-row">
                <code className="mono">{item.policy_pack_id}</code>
              </div>
            </div>

            {proposal?.prompt_hash && (
              <div className="tech-item">
                <span className="tech-label">{tr("Prompt Hash:")}</span>
                <div className="tech-val-row">
                  <code className="mono">{proposal.prompt_hash}</code>
                  <button
                    type="button"
                    className="tech-copy-btn"
                    onClick={() => copyToClipboard('phash', proposal.prompt_hash)}
                  >
                    {copiedKey === 'phash' ? tr('Copied!') : tr('Copy')}
                  </button>
                </div>
              </div>
            )}

            {proposal?.model_id && (
              <div className="tech-item">
                <span className="tech-label">{tr("Model ID:")}</span>
                <div className="tech-val-row">
                  <code className="mono">{proposal.model_id}</code>
                </div>
              </div>
            )}

            {item.resolution?.trace_id && (
              <div className="tech-item">
                <span className="tech-label">{tr("Resolution Trace:")}</span>
                <div className="tech-val-row">
                  <code className="mono">{item.resolution.trace_id}</code>
                  <button
                    type="button"
                    className="tech-copy-btn"
                    onClick={() => copyToClipboard('trace', item.resolution!.trace_id)}
                  >
                    {copiedKey === 'trace' ? tr('Copied!') : tr('Copy')}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </details>

      {/* 9. Interactive Modes: Edit Form, Reject Form, Review Buttons */}
      {mode === 'edit' && (
        <div className="edit-box">
          <div className="section-label">{tr("Manual Manager Correction (validated by the server on save)")}</div>
          <label className="field-label">{tr("Corrected Out-Punch Time (")}{item.timezone}):
            <input type="time" value={editedTime} onChange={(e) => setEditedTime(e.target.value)} className="input-field tnum" />
          </label>
          <label className="field-label">
            {tr("Audit Note (optional):")}
            <input type="text" placeholder={tr("e.g., Confirmed exit timestamp with security badge log")} value={comment} onChange={(e) => setComment(e.target.value)} className="input-field" />
          </label>
          {editCheck && !editCheck.valid && (
            <div className="banner banner-error" role="alert">{tr(editCheck.error ?? '')}</div>
          )}
          <div className="button-row">
            <button type="button" className="btn-primary" disabled={!canDecide || !editCheck?.valid || submitting} onClick={() => handleSubmit('edited', { editedTime, comment })}>
              {tr("Save & Re-Validate Edit")}
            </button>
            <button type="button" className="btn-secondary" onClick={() => setMode('review')}>
              {tr("Cancel (Esc)")}
            </button>
          </div>
        </div>
      )}

      {mode === 'reject' && (
        <div className="edit-box">
          <div className="section-label">{tr("Reject Proposal (Reason Code Required)")}</div>
          <label className="field-label">{tr("Reason Code:")}
            <select value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} className="input-field">
              <option value="INSUFFICIENT_EVIDENCE">{tr("INSUFFICIENT_EVIDENCE — Needs employee confirmation")}</option>
              <option value="POLICY_MISMATCH">{tr("POLICY_MISMATCH — Incorrect pay/break treatment")}</option>
              <option value="UNAUTHORIZED_OT">{tr("UNAUTHORIZED_OT — Overtime not pre-approved")}</option>
              <option value="TIME_INACCURATE">{tr("TIME_INACCURATE — Suggested timestamp disagrees with log")}</option>
            </select>
          </label>
          <label className="field-label">{tr("Manager Comment:")}
            <input type="text" placeholder={tr("Explain why proposal is rejected...")} value={comment} onChange={(e) => setComment(e.target.value)} className="input-field" />
          </label>
          <div className="button-row">
            <button type="button" className="btn-danger" disabled={!canDecide || submitting} onClick={() => handleSubmit('rejected', { reasonCode: rejectReason, comment })}>
              {tr("Confirm Rejection")}
            </button>
            <button type="button" className="btn-secondary" onClick={() => setMode('review')}>
              {tr("Cancel (Esc)")}
            </button>
          </div>
        </div>
      )}

      {mode === 'review' && item.status !== 'resolved' && (
        <div className="panel-footer-container">
          <div className="panel-footer">
            <button
              type="button"
              className="btn-primary"
              disabled={!canDecide || !proposalStateInfo.canApprove || submitting}
              onClick={() => handleSubmit('approved', {})}
              aria-describedby={!proposalStateInfo.canApprove ? 'approval-disabled-reason' : undefined}
            >
              {tr("Approve Proposal (A)")}
            </button>
            <button type="button" className="btn-secondary" disabled={!canDecide} onClick={() => setMode('edit')}>
              {tr("Edit Fix (E)")}
            </button>
            <button type="button" className="btn-danger-outline" disabled={!canDecide} onClick={() => setMode('reject')}>
              {tr("Reject (R)")}
            </button>
          </div>

          {!proposalStateInfo.canApprove && proposalStateInfo.approvalDisabledReason && (
            <div id="approval-disabled-reason" className="approval-disabled-note small muted">
              <span>ⓘ {tr("Approval disabled:")}</span> {tr(proposalStateInfo.approvalDisabledReason)}
            </div>
          )}
        </div>
      )}
    </aside>
  );
}
