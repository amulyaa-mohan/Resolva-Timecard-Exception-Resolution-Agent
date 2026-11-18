import { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { LoginScreen } from './components/LoginScreen';
import { ResolutionPanel } from './components/ResolutionPanel';
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
  const [lang, setLang] = useState<UILang>('en');
  const [aiEnabled, setAiEnabled] = useState(true);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.75);
  const [locationFilter, setLocationFilter] = useState('ALL');
  const [severityFilter, setSeverityFilter] = useState('ALL');
  const [healthMsg, setHealthMsg] = useState('Checking backend connection...');
  const [toast, setToast] = useState<{ msg: string; undoItem?: ExceptionItem } | null>(null);

  const t = LABELS[lang];

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

  const selectedItem = useMemo(
    () => exceptions.find((e) => e.id === selectedId) ?? null,
    [exceptions, selectedId]
  );

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (!isAuthenticated) return;
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
      <LoginScreen
        onLoginSuccess={(signedInEmail) => {
          setIsAuthenticated(true);
          setCurrentUserEmail(signedInEmail);
        }}
      />
    );
  }

  return (
    <div>
      <header className="topbar">
        <div className="brand">
          <span className="brand-title">Resolva</span>
          <span className="fixture-pill">LIVE BACKEND</span>
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
            aria-label="Sign Out"
            title={currentUserEmail ? `Signed in as ${currentUserEmail}` : 'Sign Out'}
          >
            Sign Out
          </button>
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
                      {Array.from(new Set(exceptions.map((e) => e.location).filter(Boolean))).sort().map((site) => (
                        <option key={site} value={site}>{site}</option>
                      ))}
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
                onSimulateStale={handleCheckEvidence}
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
