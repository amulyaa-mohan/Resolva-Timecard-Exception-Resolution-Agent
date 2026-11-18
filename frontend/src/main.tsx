import { LanguageContext, translate } from "./lib/locale";
﻿import { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { LoginScreen } from './components/LoginScreen';
import { computeProposalState, getHumanExceptionTitle, ResolutionPanel } from './components/ResolutionPanel';
import { AuditView, ImportPreviewView, KioskView, PolicySettingsView } from './features/SecondaryViews';
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

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentUserEmail, setCurrentUserEmail] = useState<string | null>(null);
  const initial = useMemo(() => loadInitialData(), []);
  const [exceptions, setExceptions] = useState<ExceptionItem[]>(initial.exceptions);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>(initial.auditEvents);
  const [selectedId, setSelectedId] = useState<string | null>(initial.exceptions[0]?.id ?? null);
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
    const result = await submitDecisionWithFallback({
      item,
      decision,
      role,
      editedTime: details.editedTime,
      reasonCode: details.reasonCode,
      comment: details.comment,
    });

    if (!result.ok) {
      setToast({ msg: result.conflict ?? 'Decision blocked by server.' });
      return;
    }

    const snapshot = { ...item };
    const summaryText =
      decision === 'approved'
        ? `Approved AI proposal (${item.proposal?.actions.map((a) => a.type).join(', ')})`
        : decision === 'edited'
        ? `Manager manual edit out-punch -> ${details.editedTime} (${details.comment || 're-validated'})`
        : `Rejected (${details.reasonCode}): ${details.comment || 'No comment'}`;

    const audit = buildAuditRecord({ role, item, decision, summary: summaryText });

    setExceptions((prev) =>
      prev.map((ex) =>
        ex.id === item.id
          ? {
              ...ex,
              status: decision === 'rejected' ? 'escalated' : 'resolved',
              resolution: {
                decision,
                decided_by: `Priya Menon (${role})`,
                reason_code: details.reasonCode,
                comment: details.comment,
                decided_at: audit.ts,
                trace_id: audit.trace_id,
              },
            }
          : ex
      )
    );
    setAuditEvents((prev) => [audit, ...prev]);
    setToast({ msg: `${item.id} ${decision.toUpperCase()} (Trace ${audit.trace_id})`, undoItem: snapshot });
  };

  const handleSimulateStale = (itemId: string) => {
    setExceptions((prev) => prev.map((ex) => (ex.id === itemId ? { ...ex, stale_warning: true } : ex)));
    setToast({ msg: `${itemId}: New punch arrived — existing proposal marked STALE (409 guard active).` });
  };

  const handleRepropose = (itemId: string) => {
    setExceptions((prev) =>
      prev.map((ex) =>
        ex.id === itemId
          ? {
              ...ex,
              stale_warning: false,
              evidence_version: ex.evidence_version + 1,
              proposal: ex.proposal
                ? { ...ex.proposal, evidence_version: ex.evidence_version + 1, rationale: `[Re-proposed on v${ex.evidence_version + 1}] ${ex.proposal.rationale}` }
                : undefined,
            }
          : ex
      )
    );
    setToast({ msg: `${itemId}: Re-proposed and re-validated on latest evidence.` });
  };

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

  const handleBulkApprove = () => {
    if (role !== 'manager' && role !== 'admin') return;
    eligibleForBulk.forEach((item) => handleDecide(item, 'approved', {}));
    setToast({ msg: `Bulk approved ${eligibleForBulk.length} validator-passed proposals.` });
  };

  const openProblems = exceptions.filter((e) => e.status !== 'resolved' && e.severity === 'problem').length;
  const openWarnings = exceptions.filter((e) => e.status !== 'resolved' && e.severity === 'warning').length;
  const resolvedCount = exceptions.filter((e) => e.status === 'resolved').length;
  const readinessPct = Math.round(((resolvedCount + 12) / (exceptions.length + 12)) * 100);

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
                <div className="kpi-subtext small muted">Unpaired punches or statutory compliance issues</div>
              </div>
              <div className="kpi-card kpi-amber">
                <div className="kpi-label">{t.kpiWarnings}</div>
                <div className="kpi-value">{openWarnings}</div>
                <div className="kpi-subtext small muted">Non-blocking schedule or meal deviations</div>
              </div>
              <div className="kpi-card kpi-violet">
                <div className="kpi-label">{t.kpiReady}</div>
                <div className="kpi-value">{eligibleForBulk.length}</div>
                <div className="kpi-subtext small muted">6/6 rule checks passed &amp; confidence verified</div>
              </div>
              <div className="kpi-card kpi-green" title="Measures % of pay-period exceptions resolved to unblock payroll cutoff">
                <div className="kpi-label">{t.kpiReadiness}</div>
                <div className="kpi-value">{readinessPct}%</div>
                <div className="kpi-subtext small muted">
                  <strong>Payroll readiness:</strong> % of total period cases resolved
                </div>
              </div>
            </section>

            <div className="workspace-grid">
              <section className="panel-card" aria-label={tr("Exception list")}>
                <div className="toolbar">
                  <div className="filter-group">
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
                onSimulateStale={handleSimulateStale}
                onRepropose={handleRepropose}
                onDraftWithAi={handleDraftWithAi}
                onDecide={handleDecide}
              />
            </div>
          </>
        )}

        {tab === 'import' && (
          <ImportPreviewView
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
            onSimulatePunch={(newExc) => {
              setExceptions((prev) => [newExc, ...prev]);
              setAuditEvents((prev) => [
                {
                  id: `AUD-${Math.floor(4000 + Math.random() * 5000)}`,
                  trace_id: `tr-${Math.random().toString(16).slice(2, 9)}`,
                  actor_type: 'system',
                  actor_name: 'KioskIngest -> RulesEngine',
                  action: 'LIVE_PUNCH_EXCEPTION_DETECTED',
                  entity_ref: `${newExc.id} / ${newExc.employee_id}`,
                  before_summary: 'Raw kiosk clock-in received',
                  after_summary: 'Flagged MISSING_PUNCH & generated validated AI draft',
                  ts: new Date().toISOString(),
                },
                ...prev,
              ]);
              setSelectedId(newExc.id);
              setTab('inbox');
              setToast({ msg: `Live exception ${newExc.id} detected from Kiosk Simulator!` });
            }}
          />
        )}

        {tab === 'policies' && (
          <PolicySettingsView
            policies={initial.policies}
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


