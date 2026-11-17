import { ExceptionItem } from '../types/contracts';

interface PunchTimelineProps {
  item: ExceptionItem;
  editedTimeHHMM?: string | null;
}

function isoToMinutes(iso: string): number {
  const timePart = iso.slice(11, 16); // HH:MM in local timestamp
  const [h, m] = timePart.split(':').map(Number);
  return h * 60 + m;
}

function hhmmToMinutes(hhmm: string): number | null {
  const [h, m] = hhmm.split(':').map(Number);
  if (Number.isNaN(h) || Number.isNaN(m)) return null;
  return h * 60 + m;
}

export function PunchTimeline({ item, editedTimeHHMM }: PunchTimelineProps) {
  // Timeline window: 06:00 (360m) to 22:00 (1320m) = 960 minutes span
  const startMin = 6 * 60;
  const endMin = 22 * 60;
  const span = endMin - startMin;

  const toPct = (mins: number) => {
    const clamped = Math.max(startMin, Math.min(endMin, mins));
    return ((clamped - startMin) / span) * 100;
  };

  const schedStart = item.schedule ? toPct(isoToMinutes(item.schedule.start)) : null;
  const schedEnd = item.schedule ? toPct(isoToMinutes(item.schedule.end)) : null;

  const proposedAction = item.proposal?.actions.find((a) => a.new_ts);
  const proposedPct =
    !editedTimeHHMM && proposedAction?.new_ts
      ? toPct(isoToMinutes(proposedAction.new_ts))
      : null;

  const editedMins = editedTimeHHMM ? hhmmToMinutes(editedTimeHHMM) : null;
  const editedPct = editedMins !== null ? toPct(editedMins) : null;

  const ticks = [6, 8, 10, 12, 14, 16, 18, 20, 22];

  return (
    <div className="timeline-card">
      <div className="timeline-header">
        <span className="section-label">24-Hour Shift & Punch Evidence ({item.timezone})</span>
        <div className="timeline-legend">
          <span className="legend-item"><i className="dot-sched" /> Scheduled</span>
          <span className="legend-item"><i className="dot-raw" /> Raw Punch (Immutable)</span>
          {proposedPct !== null && (
            <span className="legend-item"><i className="dot-ai" /> AI Proposed</span>
          )}
          {editedPct !== null && (
            <span className="legend-item"><i className="dot-edit" /> Manager Edit</span>
          )}
        </div>
      </div>

      <div className="timeline-track">
        {/* Scheduled shift ghost bar */}
        {schedStart !== null && schedEnd !== null && schedEnd > schedStart && (
          <div
            className="timeline-schedule-bar"
            style={{ left: `${schedStart}%`, width: `${schedEnd - schedStart}%` }}
            title={`Scheduled: ${item.schedule?.start.slice(11, 16)} – ${item.schedule?.end.slice(11, 16)}`}
          >
            <span>
              Sched {item.schedule?.start.slice(11, 16)}–{item.schedule?.end.slice(11, 16)}
            </span>
          </div>
        )}

        {/* Raw immutable punches */}
        {item.punches.map((p) => {
          const left = toPct(isoToMinutes(p.ts));
          return (
            <div
              key={p.id}
              className={`timeline-marker raw-${p.type}`}
              style={{ left: `${left}%` }}
              title={`${p.type.toUpperCase()} at ${p.ts.slice(11, 16)} (${p.source} / ${p.device_id})`}
            >
              <div className="marker-pin" />
              <div className="marker-label">
                {p.type === 'break_start' ? 'brk_in' : p.type === 'break_end' ? 'brk_out' : p.type}{' '}
                {p.ts.slice(11, 16)}
              </div>
            </div>
          );
        })}

        {/* AI Proposed Punch */}
        {proposedPct !== null && proposedAction?.new_ts && (
          <div
            className="timeline-marker ai-proposed"
            style={{ left: `${proposedPct}%` }}
            title={`AI Proposed: ${proposedAction.new_ts.slice(11, 16)}`}
          >
            <div className="marker-pin" />
            <div className="marker-label">AI {proposedAction.new_ts.slice(11, 16)}</div>
          </div>
        )}

        {/* Manager Live Edit Marker */}
        {editedPct !== null && editedTimeHHMM && (
          <div
            className="timeline-marker manager-edit"
            style={{ left: `${editedPct}%` }}
            title={`Manager Edit: ${editedTimeHHMM}`}
          >
            <div className="marker-pin" />
            <div className="marker-label">Edit {editedTimeHHMM}</div>
          </div>
        )}
      </div>

      <div className="timeline-axis">
        {ticks.map((hr) => (
          <span key={hr}>{String(hr).padStart(2, '0')}:00</span>
        ))}
      </div>
    </div>
  );
}
