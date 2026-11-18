import { useTranslation } from "../lib/locale";
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
  const { tr } = useTranslation();
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

  const punchLabels = {
    in: 'Clock in',
    out: 'Clock out',
    break_start: 'Break started',
    break_end: 'Break ended',
  };
  const markers = item.punches.map((p) => ({
    id: `raw-${p.id}`,
    kind: 'raw',
    left: toPct(isoToMinutes(p.ts)),
    label: tr(punchLabels[p.type] ?? p.type),
    time: p.ts.slice(11, 16),
  }));
  if (proposedPct !== null && proposedAction?.new_ts) {
    markers.push({ id: 'proposed', kind: 'ai-proposed', left: proposedPct,
      label: tr('AI Proposed'), time: proposedAction.new_ts.slice(11, 16) });
  }
  if (editedPct !== null && editedTimeHHMM) {
    markers.push({ id: 'edited', kind: 'manager-edit', left: editedPct,
      label: tr('Manager Edit'), time: editedTimeHHMM });
  }

  return (
    <div className="timeline-card">
      <div className="timeline-header">
        <span className="section-label">{tr("24-Hour Shift & Punch Evidence (")}{item.timezone})</span>
        <div className="timeline-legend">
          <span className="legend-item"><i className="dot-sched" />{" " + tr("Scheduled") + ""}</span>
          <span className="legend-item"><i className="dot-raw" />{" " + tr("Raw Punch (Immutable)") + ""}</span>
          {proposedPct !== null && (
            <span className="legend-item"><i className="dot-ai" />{" " + tr("AI Proposed") + ""}</span>
          )}
          {editedPct !== null && (
            <span className="legend-item"><i className="dot-edit" />{" " + tr("Manager Edit") + ""}</span>
          )}
        </div>
      </div>

      <div className="timeline-track">
        {/* Scheduled shift ghost bar */}
        {schedStart !== null && schedEnd !== null && schedEnd > schedStart && (
          <div
            className="timeline-schedule-bar"
            style={{ left: `${schedStart}%`, width: `${schedEnd - schedStart}%` }}
            title={`${tr("Scheduled")} ${item.schedule?.start.slice(11, 16)} – ${item.schedule?.end.slice(11, 16)}`}
          >
            <span>{"" + tr("Sched") + " "}{item.schedule?.start.slice(11, 16)}–{item.schedule?.end.slice(11, 16)}
            </span>
          </div>
        )}

        {markers.map((marker) => (
          <div key={marker.id} className={`timeline-marker ${marker.kind}`}
            style={{ left: `${marker.left}%` }} title={`${marker.label} ${marker.time}`}>
            <div className="marker-pin" />
          </div>
        ))}
      </div>

      <div className="timeline-axis">
        {ticks.map((hr) => (
          <span key={hr}>{String(hr).padStart(2, '0')}:00</span>
        ))}
      </div>
      {markers.length > 0 && (
        <ul className="timeline-events">
          {markers.map((marker) => (
            <li key={marker.id} className={marker.kind}>
              <span className="tnum">{marker.time}</span> {marker.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
