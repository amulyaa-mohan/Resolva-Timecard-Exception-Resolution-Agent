import { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ResolutionPanel } from './components/ResolutionPanel';
import { AuditView, KioskView, PolicySettingsView } from './features/SecondaryViews';
import { buildAuditRecord, checkBackendHealth, loadInitialData } from './lib/api';
import { AuditEvent, ExceptionItem, Role } from './types/contracts';
import './styles.css';

type Tab = 'inbox' | 'escalations' | 'audit' | 'kiosk' | 'policies';

function App() {
  const initial = useMemo(() => loadInitialData(), []);
  const [exceptions, setExceptions] = useState<ExceptionItem[]>(initial.exceptions);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>(initial.auditEvents);
  const [selectedId, setSelectedId] = useState<string | null>(initial.exceptions[0]?.id ?? null);
  const [tab, setTab] = useState<Tab>('inbox');
  const [role, setRole] = useState<Role>('manager');
  const [aiEnabled, setAiEnabled] = useState(true);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.75);
  const [locationFilter, setLocationFilter] = useState('ALL');
  const [severityFilter, setSeverityFilter] = useState('ALL');
  const [healthMsg, setHealthMsg] = useState('Checking backend connection...');
  const [toast, setToast] = useState<{ msg: string; undoItem?: ExceptionItem } | null>(null);

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

  const handleDecide = (
    item: ExceptionItem,
    decision: 'approved' | 'edited' | 'rejected',
    details: { editedTime?: string; reasonCode?: string; comment?: string }
  ) => {
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
          <span className="fixture-pill">SYNTHETIC FIXTURES (FE-01 / FE-02)</span>
        </div>

        <nav className="nav-tabs" aria-label="Primary views">
          <button type="button" className={`nav-tab ${tab === 'inbox' ? 'active' : ''}`} onClick={() => setTab('inbox')}>
            Exception Inbox ({exceptions.filter((e) => e.status !== 'resolved').length})
          </button>
          <button type="button" className={`nav-tab ${tab === 'escalations' ? 'active' : ''}`} onClick={() => setTab('escalations')}>
            Escalations ({exceptions.filter((e) => e.status === 'escalated').length})
          </button>
          <button type="button" className={`nav-tab ${tab === 'audit' ? 'active' : ''}`} onClick={() => setTab('audit')}>
            Audit Trail ({auditEvents.length})
          </button>
          <button type="button" className={`nav-tab ${tab === 'kiosk' ? 'active' : ''}`} onClick={() => setTab('kiosk')}>
            Kiosk Simulator
          </button>
          <button type="button" className={`nav-tab ${tab === 'policies' ? 'active' : ''}`} onClick={() => setTab('policies')}>
            Policies & Settings
          </button>
        </nav>

        <div className="role-box">
          <label htmlFor="role-switcher"><strong>Active Role:</strong></label>
          <select
            id="role-switcher"
            className="role-select mono"
            value={role}
            onChange={(e) => setRole(e.target.value as Role)}
          >
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
        <span>Shortcuts: <strong>J / K</strong> move selection • <strong>A</strong> approve eligible item</span>
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
                <div className="kpi-label">Open Problems (Blocks Pay)</div>
                <div className="kpi-value">{openProblems}</div>
              </div>
              <div className="kpi-card kpi-amber">
                <div className="kpi-label">Open Warnings</div>
                <div className="kpi-value">{openWarnings}</div>
              </div>
              <div className="kpi-card kpi-violet">
                <div className="kpi-label">AI-Ready to Approve</div>
                <div className="kpi-value">{eligibleForBulk.length}</div>
              </div>
              <div className="kpi-card kpi-green">
                <div className="kpi-label">Pay-Period Readiness</div>
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
                    Bulk Approve Eligible ({eligibleForBulk.length})
                  </button>
                </div>

                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Severity</th>
                        <th>Employee</th>
                        <th>Exception</th>
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
                          const passed = aiEnabled && item.proposal?.validator_passed && (item.proposal?.confidence ?? 0) >= confidenceThreshold;
                          return (
                            <tr
                              key={item.id}
                              className={`inbox-row ${item.id === selectedId ? 'selected' : ''}`}
                              onClick={() => setSelectedId(item.id)}
                            >
                              <td>
                                <span className={`badge badge-${item.severity}`}>
                                  {item.severity.toUpperCase()}
                                </span>
                              </td>
                              <td>
                                <strong>{item.employee_name}</strong>
                                <div className="small muted">{item.location} • {item.work_date}</div>
                              </td>
                              <td>
                                <div className="mono small"><strong>{item.code}</strong></div>
                                <div className="small muted">{item.summary}</div>
                              </td>
                              <td>
                                {!aiEnabled ? (
                                  <span className="badge-neutral">Rules-Only</span>
                                ) : passed ? (
                                  <span className="badge-ai">
                                    AI Draft ({Math.round((item.proposal?.confidence ?? 0) * 100)}%)
                                  </span>
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
                onDecide={handleDecide}
              />
            </div>
          </>
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
        <div className="toast" role="status">
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
