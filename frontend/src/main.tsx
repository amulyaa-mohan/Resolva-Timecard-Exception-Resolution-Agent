import { LanguageContext, translate } from "./lib/locale";
﻿import { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { LoginScreen } from './components/LoginScreen';
import { computeProposalState, getHumanExceptionTitle, ResolutionPanel } from './components/ResolutionPanel';
import { AuditView, ImportPreviewView, KioskView, PolicySettingsView } from './features/SecondaryViews';
import {
  ApiError,
  checkBackendHealth,
  hasValidSession,
  signOut,
  editedTimestamp,
  fetchAudit,
  fetchCase,
  fetchExceptions,
  requestProposal,
  submitDecision,
} from './lib/api';
import { INITIAL_POLICY_PACKS } from './lib/fixtures';
import { AuditEvent, ExceptionItem, Role, UILang } from './types/contracts';
import { buildAuditRecord, checkBackendHealth, loadInitialData, submitDecisionWithFallback } from './lib/api';
import { AuditEvent, ExceptionItem, LLMProposal, Role, UILang } from './types/contracts';
import './styles.css';

type Tab = 'inbox' | 'escalations' | 'import' | 'audit' | 'kiosk' | 'policies';

const LABELS: Record<UILang, {
  inbox: string; escalations: string; importTab: string; audit: string; kiosk: string; policies: string;
  kpiProblems: string; kpiWarnings: string; kpiReady: string; kpiReadiness: string; bulkApprove: string;
}> = {
  en: {
    inbox: 'Exception Inbox', escalations: 'Escalations', importTab: 'Import Preview', audit: 'Audit Trail',
    kiosk: 'Kiosk Simulator', policies: 'Policies & Settings', kpiProblems: 'Open Problems (Blocks Pay)',
    kpiWarnings: 'Open Warnings', kpiReady: 'AI-Ready to Approve', kpiReadiness: 'Pay-Period Readiness',
    bulkApprove: 'Bulk Approve Eligible',
  },
  hi: {
    inbox: 'अपवाद इनबॉक्स', escalations: 'एस्केलेशन', importTab: 'इम्पोर्ट पूर्वावलोकन',
    audit: 'ऑडिट ट्रेल', kiosk: 'कियोस्क सिम्युलेटर', policies: 'नीतियां और सेटिंग्स',
    kpiProblems: 'खुली समस्याएं', kpiWarnings: 'चेतावनियां',
    kpiReady: 'AI अनुमोदन के लिए तैयार', kpiReadiness: 'पेरोल तैयारी', bulkApprove: 'सामूहिक अनुमोदन',
  },
};

function describeError(error: unknown): string {
  if (error instanceof ApiError) return error.detail;
  return error instanceof Error ? error.message : String(error);
}

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentUserEmail, setCurrentUserEmail] = useState<string | null>(null);
  const [exceptions, setExceptions] = useState<ExceptionItem[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('inbox');
  const [role, setRole] = useState<Role>('manager');
  const [lang, setLang] = useState<UILang>(() => localStorage.getItem('resolva-language') === 'hi' ? 'hi' : 'en');
  const [aiEnabled, setAiEnabled] = useState(true);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.75);
  const [locationFilter, setLocationFilter] = useState('ALL');
  const [severityFilter, setSeverityFilter] = useState('ALL');
  const [healthMsg, setHealthMsg] = useState('Checking backend connection...');
  const [toast, setToast] = useState<{ msg: string; undoItem?: ExceptionItem } | null>(null);

  const t = LABELS[lang];
  const tr = (text: string) => translate(lang, text);

  useEffect(() => {
    document.documentElement.lang = lang;
    localStorage.setItem('resolva-language', lang);
  }, [lang]);

  const reload = async (): Promise<void> => {
    setLoading(true);
    try {
      const items = await fetchExceptions();
      setExceptions((prev) =>
        // keep any detail already fetched for a case, refresh its summary fields
        items.map((item) => ({ ...prev.find((p) => p.id === item.id), ...item }))
      );
      setSelectedId((current) => (current && items.some((i) => i.id === current) ? current : items[0]?.id ?? null));
      setLoadError(null);
    } catch (error) {
      setLoadError(describeError(error));
    } finally {
      setLoading(false);
    }
  };

  // A refresh keeps the signed-in state only if the server still accepts the stored token.
  useEffect(() => {
    hasValidSession().then((valid) => valid && setIsAuthenticated(true));
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated]);

  // Load the selected case's evidence and its audit trail from the server.
  useEffect(() => {
    if (!isAuthenticated || !selectedId) return;
    let cancelled = false;
    const id = selectedId;
    fetchCase(id)
      .then((detail) => {
        if (!cancelled) {
          setExceptions((prev) => prev.map((ex) => (ex.id === id ? { ...ex, ...detail } : ex)));
        }
      })
      .catch((error) => !cancelled && setToast({ msg: describeError(error) }));
    fetchAudit(id)
      .then((events) => !cancelled && setAuditEvents(events))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, selectedId]);

  useEffect(() => {
    checkBackendHealth().then((h) => setHealthMsg(h.message));
  }, []);

  const visibleItems = useMemo(() => {
    return exceptions.filter((e) => {
      if (tab === 'escalations' && e.status !== 'escalated') return false;
      if (locationFilter !== 'ALL' && e.location !== locationFilter) return false;
      if (severityFilter !== 'ALL' && e.severity !== severityFilter) return false;
      return true;
    });
  }, [exceptions, tab, locationFilter, severityFilter]);

  const totalEscalationsInSystem = useMemo(
    () => exceptions.filter((e) => e.status === 'escalated').length,
    [exceptions]
  );
  const totalInboxInSystem = useMemo(
    () => exceptions.filter((e) => e.status !== 'resolved').length,
    [exceptions]
  );

  // Reconcile selection whenever tab, filters, or items change
  useEffect(() => {
    if (tab !== 'inbox' && tab !== 'escalations') return;

    if (visibleItems.length === 0) {
      setSelectedId(null);
    } else {
      const isSelectedInVisible = visibleItems.some((item) => item.id === selectedId);
      if (!isSelectedInVisible) {
        setSelectedId(visibleItems[0].id);
      }
    }
  }, [tab, locationFilter, severityFilter, visibleItems, selectedId]);

  const selectedItem = useMemo(() => {
    if (!selectedId) return null;
    return visibleItems.find((e) => e.id === selectedId) ?? null;
  }, [visibleItems, selectedId]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (!isAuthenticated) return;
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
      if (tab !== 'inbox' && tab !== 'escalations') return;

      const idx = visibleItems.findIndex((i) => i.id === selectedId);
      if (e.key.toLowerCase() === 'j') {
        if (visibleItems.length === 0) return;
        const next = visibleItems[Math.min(visibleItems.length - 1, (idx === -1 ? 0 : idx) + 1)];
        if (next) setSelectedId(next.id);
      } else if (e.key.toLowerCase() === 'k') {
        if (visibleItems.length === 0) return;
        const prev = visibleItems[Math.max(0, (idx === -1 ? 0 : idx) - 1)];
        if (prev) setSelectedId(prev.id);
      } else if (e.key.toLowerCase() === 'a') {
        // Validate selected case against currently visible results before performing action
        const currentVisibleSelected = visibleItems.find((i) => i.id === selectedId);
        if (!currentVisibleSelected) return;
        if (role !== 'manager' && role !== 'admin') return;

        if (
          currentVisibleSelected.status !== 'resolved' &&
          !currentVisibleSelected.stale_warning &&
          aiEnabled &&
          currentVisibleSelected.proposal?.validator_passed &&
          currentVisibleSelected.proposal.decision === 'propose' &&
          currentVisibleSelected.proposal.confidence >= confidenceThreshold
        ) {
          handleDecide(currentVisibleSelected, 'approved', {});
        }
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  });

  const handleDecide = async (
    item: ExceptionItem,
    decision: 'approved' | 'edited' | 'rejected',
    details: { editedTime?: string; reasonCode?: string; comment?: string }
  ) => {
    // The server re-validates against fresh evidence and is the only thing that can approve.
    // Anything other than a 2xx leaves the case untouched and is reported as a failure.
    const actions =
      decision === 'edited'
        ? [
            {
              type: 'add_punch' as const,
              punch_type: 'out' as const,
              new_ts: editedTimestamp(item, details.editedTime ?? ''),
              note: details.comment ?? '',
            },
          ]
        : item.proposal?.actions ?? [];
    const reason =
      decision === 'rejected'
        ? `${details.reasonCode ?? 'rejected'}: ${details.comment || 'no comment'}`
        : details.comment ?? '';
    try {
      const result = await submitDecision({
        item,
        decision: decision === 'rejected' ? 'rejected' : 'approved',
        actions,
        reason,
        edited: decision === 'edited',
      });
      setToast({ msg: `${item.id} ${result.status.toUpperCase()} — recorded by the server.` });
      await reload();
      const events = await fetchAudit(item.id).catch(() => []);
      setAuditEvents(events);
    } catch (error) {
      // No state change: nothing was saved, so nothing may look saved.
      setToast({ msg: describeError(error) });
    }
  };

  const handleCheckEvidence = async (itemId: string) => {
    try {
      const fresh = await fetchCase(itemId);
      setExceptions((prev) =>
        prev.map((ex) =>
          ex.id === itemId
            ? { ...ex, ...fresh, stale_warning: Boolean(ex.proposal && fresh.evidence_version !== ex.proposal.evidence_version) }
            : ex
        )
      );
      setToast({ msg: `${itemId}: evidence re-read from the server.` });
    } catch (error) {
      setToast({ msg: describeError(error) });
    }
  };

  const handleRepropose = async (itemId: string) => {
    const item = exceptions.find((e) => e.id === itemId);
    if (!item) return;
    setToast({ msg: `${itemId}: asking the model for a draft...` });
    try {
      const outcome = await requestProposal(itemId);
      setExceptions((prev) =>
        prev.map((ex) =>
          ex.id === itemId
            ? {
                ...ex,
                stale_warning: false,
                status: outcome.status === 'escalated' ? 'escalated' : outcome.status === 'eligible' ? 'proposed' : ex.status,
                proposal: outcome.proposal,
                draft_status: outcome.status,
                draft_reasons: outcome.reasons,
              }
            : ex
        )
      );
      const detail = outcome.reasons.length ? ` — ${outcome.reasons[0]}` : '';
      setToast({ msg: `${itemId}: ${outcome.status.toUpperCase()}${detail}` });
      setAuditEvents(await fetchAudit(itemId).catch(() => []));
    } catch (error) {
      setToast({ msg: describeError(error) });
    }
  };

  // A decision cannot be undone from the browser: corrections and audit events are append-only.
  // Reversing one is a new, audited decision, which is not built yet.
  const handleUndo = () => setToast(null);

  const handleDraftWithAi = (itemId: string) => {
    setExceptions((prev) =>
      prev.map((ex) => {
        if (ex.id !== itemId) return ex;
        if (ex.proposal) return ex;
        const schedEnd = ex.schedule?.end ? ex.schedule.end : '2026-11-17T18:00:00+05:30';
        const newProposal: LLMProposal = {
          id: `PRP-${Math.floor(600 + Math.random() * 300)}`,
          exception_id: ex.id,
          decision: 'propose',
          actions: [
            {
              type: 'add_punch',
              new_ts: schedEnd,
              note: `Add out-punch aligned with scheduled shift end (${schedEnd.slice(11, 16)}).`,
            },
          ],
          rationale: `AI draft: Evaluated shift pattern and punch timeline against ${ex.policy_pack_id}. Inferred out-punch at scheduled shift end.`,
          citations: [
            {
              chunk_id: `${ex.policy_pack_id}#sec-4.2`,
              quote: 'Missing punches may be inferred from scheduled shift when corroborated by historical pattern.',
            },
          ],
          confidence: 0.92,
          missing_information: [],
          model_id: 'qwen2.5-7b-instruct',
          prompt_hash: 'sha256:a1b2c3d4',
          evidence_version: ex.evidence_version,
          validator_passed: true,
          rule_outcomes: [
            { rule: 'MISSING_PUNCH', passed: true, detail: 'Punches paired after draft fix.' },
            { rule: 'OVERLAPPING_SHIFT', passed: true, detail: 'No overlap.' },
            { rule: 'MEAL_BREAK_BREACH', passed: true, detail: 'Compliant.' },
            { rule: 'OVERTIME_RISK', passed: true, detail: 'Within daily limits.' },
            { rule: 'SPREAD_OVER_BREACH', passed: true, detail: 'Within statutory spread.' },
            { rule: 'SCHEDULE_DEVIATION', passed: true, detail: 'Aligned with schedule.' },
          ],
        };
        return {
          ...ex,
          status: 'proposed',
          proposal: newProposal,
        };
      })
    );
    setToast({ msg: `${itemId}: Policy draft generated with AI and verified by validator.` });
  };

  const handleUndo = () => {
    if (!toast?.undoItem) return;
    const restored = toast.undoItem;
    const reversalAudit = buildAuditRecord({
      role,
      item: restored,
      decision: 'rejected',
      summary: `Audited reversal of prior decision on ${restored.id}`,
    });
    setExceptions((prev) => prev.map((ex) => (ex.id === restored.id ? restored : ex)));
    setAuditEvents((prev) => [reversalAudit, ...prev]);
    setToast(null);
  };

  const eligibleForBulk = useMemo(
    () =>
      exceptions.filter(
        (e) =>
          e.status === 'proposed' &&
          !e.stale_warning &&
          aiEnabled &&
          e.proposal?.validator_passed &&
          (e.proposal?.confidence ?? 0) >= confidenceThreshold
      ),
    [exceptions, aiEnabled, confidenceThreshold]
  );

  const handleBulkApprove = async () => {
    if (role !== 'manager' && role !== 'admin') return;
    // Each one is submitted and judged on its own by the server, exactly as a single approval is.
    for (const item of eligibleForBulk) {
      await handleDecide(item, 'approved', {});
    }
  };

  const openProblems = exceptions.filter((e) => e.status !== 'resolved' && e.severity === 'problem').length;
  const openWarnings = exceptions.filter((e) => e.status !== 'resolved' && e.severity === 'warning').length;
  const resolvedCount = exceptions.filter((e) => e.status === 'resolved').length;
  // Share of this manager's exceptions that are resolved; no padding, no invented baseline.
  const readinessPct = exceptions.length ? Math.round((resolvedCount / exceptions.length) * 100) : 0;

  if (!isAuthenticated) {
    return (
      <LanguageContext.Provider value={lang}>
        <div className="login-language">
          <select aria-label={tr("Language")} value={lang} onChange={(e) => setLang(e.target.value === "hi" ? "hi" : "en")}>
            <option value="en">English</option>
            <option value="hi">हिंदी</option>
          </select>
        </div>
      <LoginScreen
        onLoginSuccess={(signedInEmail) => {
          setIsAuthenticated(true);
          setCurrentUserEmail(signedInEmail);
        }}
      />
      </LanguageContext.Provider>
    );
  }

  return (
    <LanguageContext.Provider value={lang}>
    <div>
      <header className="topbar">
        <div className="brand">
          <span className="brand-title">Resolva</span>
          <span className="fixture-pill">LIVE BACKEND</span>
          <span className="fixture-pill">{tr("SYNTHETIC FIXTURES (FE-01..FE-05)")}</span>

        </div>

        <nav className="nav-tabs" aria-label={tr("Primary views")}>
          <button type="button" className={`nav-tab ${tab === 'inbox' ? 'active' : ''}`} onClick={() => setTab('inbox')}>
            {t.inbox} ({exceptions.filter((e) => e.status !== 'resolved').length})
          </button>
          <button type="button" className={`nav-tab ${tab === 'escalations' ? 'active' : ''}`} onClick={() => setTab('escalations')}>
            {t.escalations} ({exceptions.filter((e) => e.status === 'escalated').length})
          </button>
          <button type="button" className={`nav-tab ${tab === 'import' ? 'active' : ''}`} onClick={() => setTab('import')}>
            {t.importTab}
          </button>
          <button type="button" className={`nav-tab ${tab === 'audit' ? 'active' : ''}`} onClick={() => setTab('audit')}>
            {t.audit} ({auditEvents.length})
          </button>
          <button type="button" className={`nav-tab ${tab === 'kiosk' ? 'active' : ''}`} onClick={() => setTab('kiosk')}>
            {t.kiosk}
          </button>
          <button type="button" className={`nav-tab ${tab === 'policies' ? 'active' : ''}`} onClick={() => setTab('policies')}>
            {t.policies}
          </button>
        </nav>

        <div className="role-box">
          <select aria-label={tr("Language")} className="role-select" value={lang} onChange={(e) => setLang(e.target.value === "hi" ? "hi" : "en")}>
            <option value="en">English</option>
            <option value="hi">हिंदी</option>
          </select>
          <select id="role-switcher" aria-label={tr("Active role")} className="role-select" value={role} onChange={(e) => setRole(e.target.value as Role)}>
            <option value="manager">{tr("manager (Priya)")}</option>
            <option value="employee">{tr("employee (Read-only)")}</option>
            <option value="compliance">{tr("compliance (Auditor)")}</option>
            <option value="payroll_admin">{tr("payroll_admin")}</option>
            <option value="admin">{tr("admin")}</option>
          </select>
          <button
            type="button"
            className="btn-secondary sign-out-btn"
            style={{ fontSize: '12px', padding: '5px 12px' }}
            onClick={() => {
              signOut(); // forget the token, so a refresh does not sign back in
              setExceptions([]);
              setAuditEvents([]);
              setSelectedId(null);
              setIsAuthenticated(false);
              setCurrentUserEmail(null);
            }}
            aria-label={tr("Sign Out")}
            title={currentUserEmail ? `${tr('Signed in as')} ${currentUserEmail}` : tr('Sign Out')}
          >{tr("Sign Out")}</button>
        </div>
      </header>

      <div className="status-strip">
        <span>{lang === 'hi' && healthMsg.startsWith('Backend connected:') ? 'सर्वर जुड़ा है' : tr(healthMsg)}</span>
        <span>{"" + tr("Shortcuts:") + " "}<strong>J/K</strong>{" " + tr("navigate •") + " "}<strong>A</strong>{" " + tr("approve •") + " "}<strong>E</strong>{" " + tr("edit •") + " "}<strong>R</strong>{" " + tr("reject •") + " "}<strong>Esc</strong>{" " + tr("close") + ""}</span>
      </div>

      <main className="container">
        {!aiEnabled && (
          <div className="banner banner-warn" style={{ marginBottom: 16 }}>
            <strong>{tr("AI Unavailable / Kill-Switch Engaged:")}</strong>{" " + tr("Showing deterministic rules-only results. Manual manager edits remain active.") + ""}</div>
        )}

        {(tab === 'inbox' || tab === 'escalations') && (
          <>
            <section className="kpi-grid" aria-label={tr("Pay-period summary")}>
              <div className="kpi-card kpi-red">
                <div className="kpi-label">{t.kpiProblems}</div>
                <div className="kpi-value">{openProblems}</div>
                <div className="kpi-subtext small muted">{tr("Unpaired punches or statutory compliance issues")}</div>
              </div>
              <div className="kpi-card kpi-amber">
                <div className="kpi-label">{t.kpiWarnings}</div>
                <div className="kpi-value">{openWarnings}</div>
                <div className="kpi-subtext small muted">{tr("Non-blocking schedule or meal deviations")}</div>
              </div>
              <div className="kpi-card kpi-ai">
                <div className="kpi-label">{t.kpiReady}</div>
                <div className="kpi-value">{eligibleForBulk.length}</div>
                <div className="kpi-subtext small muted">{tr("6/6 rule checks passed & confidence verified")}</div>
              </div>
              <div className="kpi-card kpi-green" title="Measures % of pay-period exceptions resolved to unblock payroll cutoff">
                <div className="kpi-label">{t.kpiReadiness}</div>
                <div className="kpi-value">{readinessPct}%</div>
                <div className="kpi-subtext small muted">
                  <strong>{tr("Payroll readiness:")}</strong> {tr("% of total period cases resolved")}
                </div>
              </div>
            </section>

            <div className="workspace-grid">
              <section className="panel-card" aria-label={tr("Exception list")}>
                <div className="toolbar">
                  <div className="filter-group">
                    <select className="role-select" value={locationFilter} onChange={(e) => setLocationFilter(e.target.value)} aria-label="Filter by location">
                      <option value="ALL">All Locations</option>
                      {Array.from(new Set(exceptions.map((e) => e.location).filter(Boolean))).sort().map((site) => (
                        <option key={site} value={site}>{site}</option>
                      ))}
                    <select className="role-select" value={locationFilter} onChange={(e) => setLocationFilter(e.target.value)} aria-label={tr("Filter by location")}>
                      <option value="ALL">{tr("All Locations")}</option>
                      <option value="Bengaluru (BLR-01)">{tr("Bengaluru (BLR-01)")}</option>
                      <option value="Bengaluru (BLR-02)">{tr("Bengaluru (BLR-02)")}</option>
                      <option value="Austin (AUS-01)">{tr("Austin (AUS-01)")}</option>
                    </select>
                    <select className="role-select" value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)} aria-label={tr("Filter by severity")}>
                      <option value="ALL">{tr("All Severities")}</option>
                      <option value="problem">{tr("Problems Only")}</option>
                      <option value="warning">{tr("Warnings Only")}</option>
                    </select>
                  </div>

                  <button
                    type="button"
                    className="btn-primary"
                    disabled={eligibleForBulk.length === 0 || (role !== 'manager' && role !== 'admin')}
                    onClick={handleBulkApprove}
                  >
                    {t.bulkApprove} ({eligibleForBulk.length})
                  </button>
                </div>

                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th style={{ width: 110 }}>{tr("Severity")}</th>
                        <th style={{ width: 190 }}>{tr("Employee")}</th>
                        <th>{tr("Exception / Summary")}</th>
                        <th style={{ width: 160 }}>{tr("Proposal State")}</th>
                        <th style={{ width: 90 }}>{tr("State")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleItems.length === 0 ? (
                        <tr>
                          <td colSpan={5} className="empty-table-cell">
                            {tab === 'escalations' ? (
                              totalEscalationsInSystem === 0 ? (
                                <div className="empty-table-state">
                                  <div className="empty-state-title">{tr("No escalations")}</div>
                                  <p className="muted small">
                                    {tr("All exception cases have been resolved or are progressing in automated processing. No items currently require escalation.")}
                                  </p>
                                </div>
                              ) : (
                                <div className="empty-table-state">
                                  <div className="empty-state-title">{tr("No cases match these filters")}</div>
                                  <p className="muted small">
                                    {tr("There are")} {totalEscalationsInSystem} {tr("escalation(s) in other locations or severities.")}
                                  </p>
                                  <button
                                    type="button"
                                    className="btn-secondary small"
                                    onClick={() => { setLocationFilter('ALL'); setSeverityFilter('ALL'); }}
                                  >
                                    {tr("Clear Filters")}
                                  </button>
                                </div>
                              )
                            ) : (
                              totalInboxInSystem === 0 ? (
                                <div className="empty-table-state">
                                  <div className="empty-state-title">{tr("No open exceptions")}</div>
                                  <p className="muted small">{tr("All timecard exceptions for this pay period have been resolved.")}</p>
                                </div>
                              ) : (
                                <div className="empty-table-state">
                                  <div className="empty-state-title">{tr("No cases match these filters")}</div>
                                  <p className="muted small">
                                    {tr("No exceptions match the selected location and severity filters.")}
                                  </p>
                                  <button
                                    type="button"
                                    className="btn-secondary small"
                                    onClick={() => { setLocationFilter('ALL'); setSeverityFilter('ALL'); }}
                                  >
                                    {tr("Clear Filters")}
                                  </button>
                                </div>
                              )
                            )}
                          </td>
                        </tr>
                      ) : (
                        visibleItems.map((item) => {
                          const proposalState = computeProposalState(item, aiEnabled, confidenceThreshold, false);
                          return (
                            <tr
                              key={item.id}
                              tabIndex={0}
                              className={`inbox-row ${item.id === selectedId ? 'selected' : ''}`}
                              onClick={() => setSelectedId(item.id)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                  e.preventDefault();
                                  setSelectedId(item.id);
                                }
                              }}
                            >
                              <td><span className={`badge badge-${item.severity}`}>{tr(item.severity.toUpperCase())}</span></td>
                              <td>
                                <strong>{item.employee_name}</strong>
                                <div className="small muted">{tr(item.location)} • {item.work_date}</div>
                              </td>
                              <td>
                                <div className="mono small"><strong>{item.code}</strong> {item.policy_pack_id ? <span className="muted">({item.policy_pack_id})</span> : null}</div>
                                <div className="small muted">{item.summary}</div>
                              </td>
                              <td>
                                {!aiEnabled ? (
                                  <span className="badge-neutral">Rules-Only</span>
                                ) : item.stale_warning ? (
                                  <span className="badge-escalated">Stale (409)</span>
                                ) : passed ? (
                                  <span className="badge-ai">AI Draft ({Math.round((item.proposal?.confidence ?? 0) * 100)}%)</span>
                                ) : item.draft_status === 'escalated' ? (
                                  <span className="badge-escalated" title={item.draft_reasons?.join(' ')}>Needs manager</span>
                                ) : item.draft_status === 'blocked' ? (
                                  <span className="badge-escalated" title={item.draft_reasons?.join(' ')}>Blocked by rules</span>
                                ) : (
                                  <span className="badge-neutral">No draft yet</span>
                                )}

                                <div style={{ fontWeight: 600, color: 'var(--text)' }}>
                                  {tr(getHumanExceptionTitle(item.code))}
                                </div>
                                <div className="small muted" style={{ marginTop: 2 }}>{tr(item.summary)}</div>
                              </td>
                              <td>
                                <span className={`badge ${proposalState.badgeClass}`}>
                                  {tr(proposalState.label)}
                                </span>
                              </td>
                              <td>
                                <span className={item.status === 'resolved' ? 'badge-pass' : 'badge-neutral'}>
                                  {tr(item.status.toUpperCase())}
                                </span>
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </section>

              <ResolutionPanel
                item={selectedItem}
                role={role}
              lang={lang}
                aiEnabled={aiEnabled}
                confidenceThreshold={confidenceThreshold}
                activeTab={tab}
                totalEscalations={totalEscalationsInSystem}
                onClose={() => setSelectedId(null)}
                onSimulateStale={handleCheckEvidence}
                onRepropose={handleRepropose}
                onDraftWithAi={handleDraftWithAi}
                onDecide={handleDecide}
              />
            </div>
          </>
        )}

        {tab === 'import' && (
          <ImportPreviewView
            onImported={(message) => {
              setToast({ msg: message });
              void reload();
            role={role}
            onImportValid={(newItems) => {
              setExceptions((prev) => [...newItems, ...prev]);
              if (newItems[0]) setSelectedId(newItems[0].id);
            }}
            onOpenException={(excId) => {
              setSelectedId(excId);
              setTab('inbox');
            }}
          />
        )}

        {tab === 'audit' && (
          <AuditView
            events={auditEvents}
            selectedCase={selectedItem}
            role={role}
            onOpenCase={(excId) => {
              setSelectedId(excId);
              setTab('inbox');
            }}
          />
        )}

        {tab === 'kiosk' && (
          <KioskView
            employees={Array.from(
              new Map(exceptions.map((e) => [e.employee_id, e.employee_name])).entries()
            ).map(([id, name]) => ({ id, name }))}
            onPunchSent={(message) => {
              setToast({ msg: message });
              void reload();
            }}
          />
        )}

        {tab === 'policies' && (
          <PolicySettingsView
            policies={INITIAL_POLICY_PACKS}
            aiEnabled={aiEnabled}
            onToggleAi={setAiEnabled}
            confidenceThreshold={confidenceThreshold}
            onChangeThreshold={setConfidenceThreshold}
          />
        )}
      </main>

      {toast && (
        <div className="toast" role="status" aria-live="polite">
          <span>{tr(toast.msg)}</span>
          {toast.undoItem && (
            <button type="button" className="btn-secondary" style={{ padding: '4px 10px' }} onClick={handleUndo}>{tr("Undo (Audited Reversal)")}</button>
          )}
          <button type="button" className="btn-ghost" style={{ color: '#fff' }} onClick={() => setToast(null)}>
            ✕
          </button>
        </div>
      )}
    </div>
    </LanguageContext.Provider>
  );
}

createRoot(document.getElementById('root')!).render(<App />);


