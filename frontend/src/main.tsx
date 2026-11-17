import { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ResolutionPanel } from './components/ResolutionPanel';
import { AuditView, ImportPreviewView, KioskView, PolicySettingsView } from './features/SecondaryViews';
import { buildAuditRecord, checkBackendHealth, loadInitialData, submitDecisionWithFallback } from './lib/api';
import { AuditEvent, ExceptionItem, Role, UILang } from './types/contracts';
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
  kn: {
    inbox: 'ವಿನಾಯಿತಿ ಇನ್‌ಬಾಕ್ಸ್ (Inbox)', escalations: 'ಹೆಚ್ಚುವರಿ ಪರಿಶೀಲನೆ (Escalations)', importTab: 'ಆಮದು ಪೂರ್ವವೀಕ್ಷಣೆ (Import)',
    audit: 'ಲೆಕ್ಕಪರಿಶೋಧನೆ (Audit)', kiosk: 'ಕಿಯೋಸ್ಕ್ ಸಿಮ್ಯುಲೇಟರ್', policies: 'ನೀತಿಗಳು (Policies)',
    kpiProblems: 'ತೆರೆದ ಸಮಸ್ಯೆಗಳು (Problems)', kpiWarnings: 'ಎಚ್ಚರಿಕೆಗಳು (Warnings)',
    kpiReady: 'AI ಅನುಮೋದನೆಗೆ ಸಿದ್ಧ', kpiReadiness: 'ವೇತನ ಸಿದ್ಧತೆ (Readiness)', bulkApprove: 'ಸಾಮೂಹಿಕ ಅನುಮೋದನೆ (Bulk Approve)',
  },
  hi: {
    inbox: 'अपवाद इनबॉक्स (Inbox)', escalations: 'एस्केलेशन (Escalations)', importTab: 'इम्पोर्ट पूर्वावलोकन (Import)',
    audit: 'ऑडिट ट्रेल (Audit)', kiosk: 'कियोस्क सिम्युलेटर', policies: 'नीतियां और सेटिंग्स',
    kpiProblems: 'खुली समस्याएं (Problems)', kpiWarnings: 'चेतावनियां (Warnings)',
    kpiReady: 'AI अनुमोदन के लिए तैयार', kpiReadiness: 'पेरोल तैयारी (Readiness)', bulkApprove: 'सामूहिक अनुमोदन (Bulk Approve)',
  },
};

function App() {
  const initial = useMemo(() => loadInitialData(), []);
  const [exceptions, setExceptions] = useState<ExceptionItem[]>(initial.exceptions);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>(initial.auditEvents);
  const [selectedId, setSelectedId] = useState<string | null>(initial.exceptions[0]?.id ?? null);
  const [tab, setTab] = useState<Tab>('inbox');
  const [role, setRole] = useState<Role>('manager');
  const [lang, setLang] = useState<UILang>('en');
  const [aiEnabled, setAiEnabled] = useState(true);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.75);
  const [locationFilter, setLocationFilter] = useState('ALL');
  const [severityFilter, setSeverityFilter] = useState('ALL');
  const [healthMsg, setHealthMsg] = useState('Checking backend connection...');
  const [toast, setToast] = useState<{ msg: string; undoItem?: ExceptionItem } | null>(null);

  const t = LABELS[lang];

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

  const selectedItem = useMemo(
    () => exceptions.find((e) => e.id === selectedId) ?? null,
    [exceptions, selectedId]
  );

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
      if (tab !== 'inbox' && tab !== 'escalations') return;

      const idx = visibleItems.findIndex((i) => i.id === selectedId);
      if (e.key.toLowerCase() === 'j') {
        const next = visibleItems[Math.min(visibleItems.length - 1, idx + 1)];
        if (next) setSelectedId(next.id);
      } else if (e.key.toLowerCase() === 'k') {
        const prev = visibleItems[Math.max(0, idx - 1)];
        if (prev) setSelectedId(prev.id);
      } else if (e.key.toLowerCase() === 'a' && selectedItem && (role === 'manager' || role === 'admin')) {
        if (
          selectedItem.status !== 'resolved' &&
          !selectedItem.stale_warning &&
          aiEnabled &&
          selectedItem.proposal?.validator_passed &&
          selectedItem.proposal.confidence >= confidenceThreshold
        ) {
          handleDecide(selectedItem, 'approved', {});
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

  return (
    <div>
      <header className="topbar">
        <div className="brand">
          <span className="brand-title">Resolva</span>
          <span className="fixture-pill">SYNTHETIC FIXTURES (FE-01..FE-05)</span>
        </div>

        <nav className="nav-tabs" aria-label="Primary views">
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
          <select aria-label="Language" className="role-select" value={lang} onChange={(e) => setLang(e.target.value as UILang)}>
            <option value="en">EN</option>
            <option value="kn">ಕನ್ನಡ (KN)</option>
            <option value="hi">हिंदी (HI)</option>
          </select>
          <select id="role-switcher" aria-label="Active role" className="role-select mono" value={role} onChange={(e) => setRole(e.target.value as Role)}>
            <option value="manager">manager (Priya)</option>
            <option value="employee">employee (Read-only)</option>
            <option value="compliance">compliance (Auditor)</option>
            <option value="payroll_admin">payroll_admin</option>
            <option value="admin">admin</option>
          </select>
        </div>
      </header>

      <div className="status-strip">
        <span>{healthMsg}</span>
        <span>Shortcuts: <strong>J/K</strong> navigate • <strong>A</strong> approve • <strong>E</strong> edit • <strong>R</strong> reject • <strong>Esc</strong> close</span>
      </div>

      <main className="container">
        {!aiEnabled && (
          <div className="banner banner-warn" style={{ marginBottom: 16 }}>
            <strong>AI Unavailable / Kill-Switch Engaged:</strong> Showing deterministic rules-only results. Manual manager edits remain active.
          </div>
        )}

        {(tab === 'inbox' || tab === 'escalations') && (
          <>
            <section className="kpi-grid" aria-label="Pay-period summary">
              <div className="kpi-card kpi-red">
                <div className="kpi-label">{t.kpiProblems}</div>
                <div className="kpi-value">{openProblems}</div>
              </div>
              <div className="kpi-card kpi-amber">
                <div className="kpi-label">{t.kpiWarnings}</div>
                <div className="kpi-value">{openWarnings}</div>
              </div>
              <div className="kpi-card kpi-violet">
                <div className="kpi-label">{t.kpiReady}</div>
                <div className="kpi-value">{eligibleForBulk.length}</div>
              </div>
              <div className="kpi-card kpi-green">
                <div className="kpi-label">{t.kpiReadiness}</div>
                <div className="kpi-value">{readinessPct}%</div>
              </div>
            </section>

            <div className="workspace-grid">
              <section className="panel-card" aria-label="Exception list">
                <div className="toolbar">
                  <div className="filter-group">
                    <select className="role-select" value={locationFilter} onChange={(e) => setLocationFilter(e.target.value)} aria-label="Filter by location">
                      <option value="ALL">All Locations</option>
                      <option value="Bengaluru (BLR-01)">Bengaluru (BLR-01)</option>
                      <option value="Bengaluru (BLR-02)">Bengaluru (BLR-02)</option>
                      <option value="Austin (AUS-01)">Austin (AUS-01)</option>
                    </select>
                    <select className="role-select" value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)} aria-label="Filter by severity">
                      <option value="ALL">All Severities</option>
                      <option value="problem">Problems Only</option>
                      <option value="warning">Warnings Only</option>
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
                        <th>Severity</th>
                        <th>Employee</th>
                        <th>Canonical Code</th>
                        <th>AI / Validator Status</th>
                        <th>State</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleItems.length === 0 ? (
                        <tr>
                          <td colSpan={5} style={{ textAlign: 'center', padding: 24 }} className="muted">
                            No exceptions match the current filter.
                          </td>
                        </tr>
                      ) : (
                        visibleItems.map((item) => {
                          const passed = aiEnabled && !item.stale_warning && item.proposal?.validator_passed && (item.proposal?.confidence ?? 0) >= confidenceThreshold;
                          return (
                            <tr
                              key={item.id}
                              className={`inbox-row ${item.id === selectedId ? 'selected' : ''}`}
                              onClick={() => setSelectedId(item.id)}
                            >
                              <td><span className={`badge badge-${item.severity}`}>{item.severity.toUpperCase()}</span></td>
                              <td>
                                <strong>{item.employee_name}</strong>
                                <div className="small muted">{item.location} • {item.work_date}</div>
                              </td>
                              <td>
                                <div className="mono small"><strong>{item.code}</strong> <span className="muted">({item.policy_pack_id})</span></div>
                                <div className="small muted">{item.summary}</div>
                              </td>
                              <td>
                                {!aiEnabled ? (
                                  <span className="badge-neutral">Rules-Only</span>
                                ) : item.stale_warning ? (
                                  <span className="badge-escalated">Stale (409)</span>
                                ) : passed ? (
                                  <span className="badge-ai">AI Draft ({Math.round((item.proposal?.confidence ?? 0) * 100)}%)</span>
                                ) : (
                                  <span className="badge-escalated">Escalated / Blocked</span>
                                )}
                              </td>
                              <td>
                                <span className={item.status === 'resolved' ? 'badge-pass' : 'badge-neutral'}>
                                  {item.status.toUpperCase()}
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
                aiEnabled={aiEnabled}
                onClose={() => setSelectedId(null)}
                onSimulateStale={handleSimulateStale}
                onRepropose={handleRepropose}
                onDecide={handleDecide}
              />
            </div>
          </>
        )}

        {tab === 'import' && (
          <ImportPreviewView
            onImportValid={(newItems) => {
              setExceptions((prev) => [...newItems, ...prev]);
              if (newItems[0]) setSelectedId(newItems[0].id);
              setTab('inbox');
              setToast({ msg: `Imported ${newItems.length} valid exception(s) into Inbox.` });
            }}
          />
        )}

        {tab === 'audit' && <AuditView events={auditEvents} />}

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
          <span>{toast.msg}</span>
          {toast.undoItem && (
            <button type="button" className="btn-secondary" style={{ padding: '4px 10px' }} onClick={handleUndo}>
              Undo (Audited Reversal)
            </button>
          )}
          <button type="button" className="btn-ghost" style={{ color: '#fff' }} onClick={() => setToast(null)}>
            ✕
          </button>
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<App />);
