import { useMemo, useState } from 'react';
import { ExceptionItem } from '../types/contracts';
import { useTranslation } from '../lib/locale';

interface PunchTimelineProps {
  item: ExceptionItem;
  editedTimeHHMM?: string | null;
}

interface TimelineMarkerData {
  id: string;
  minutes: number;
  timeFormatted: string;
  type: string;
  displayType: string;
  category: 'raw' | 'ai' | 'edit';
  source: string;
  deviceId: string;
  tooltip: string;
  tier: number;
  leftPct: number;
}

function isoToMinutes(iso: string): number {
  const timePart = iso.slice(11, 16);
  const [h, m] = timePart.split(':').map(Number);
  return (h || 0) * 60 + (m || 0);
}

function hhmmToMinutes(hhmm: string): number | null {
  const [h, m] = hhmm.split(':').map(Number);
  if (Number.isNaN(h) || Number.isNaN(m)) return null;
  return h * 60 + m;
}

export function PunchTimeline({ item, editedTimeHHMM }: PunchTimelineProps) {
  const { tr } = useTranslation();
  const [activeTooltip, setActiveTooltip] = useState<string | null>(null);

  // 1. Gather all event times to compute the actual displayed window dynamically
  const { startHour, endHour, spanMinutes } = useMemo(() => {
    const allMins: number[] = [];

    if (item.schedule) {
      allMins.push(isoToMinutes(item.schedule.start));
      allMins.push(isoToMinutes(item.schedule.end));
    }

    item.punches.forEach((p) => allMins.push(isoToMinutes(p.ts)));

    const proposedAction = item.proposal?.actions.find((a) => a.new_ts);
    if (proposedAction?.new_ts) {
      allMins.push(isoToMinutes(proposedAction.new_ts));
    }

    if (editedTimeHHMM) {
      const em = hhmmToMinutes(editedTimeHHMM);
      if (em !== null) allMins.push(em);
    }

    const minM = allMins.length > 0 ? Math.min(...allMins) : 8 * 60;
    const maxM = allMins.length > 0 ? Math.max(...allMins) : 18 * 60;

    let sHour = Math.max(0, Math.floor(minM / 60) - 1);
    let eHour = Math.min(24, Math.ceil(maxM / 60) + 1);

    // Maintain minimum span of 10 hours for comfortable viewing
    if (eHour - sHour < 10) {
      const pad = 10 - (eHour - sHour);
      sHour = Math.max(0, sHour - Math.floor(pad / 2));
      eHour = Math.min(24, sHour + 10);
    }

    return {
      startHour: sHour,
      endHour: eHour,
      spanMinutes: (eHour - sHour) * 60,
    };
  }, [item, editedTimeHHMM]);

  const toPct = (mins: number) => {
    const startMin = startHour * 60;
    const endMin = endHour * 60;
    const clamped = Math.max(startMin, Math.min(endMin, mins));
    return ((clamped - startMin) / spanMinutes) * 100;
  };

  // 2. Schedule shift positions
  const schedStart = item.schedule ? toPct(isoToMinutes(item.schedule.start)) : null;
  const schedEnd = item.schedule ? toPct(isoToMinutes(item.schedule.end)) : null;

  // 3. Compute and stagger punch markers
  const markers: TimelineMarkerData[] = useMemo(() => {
    const rawList: Omit<TimelineMarkerData, 'tier' | 'leftPct'>[] = [];

    // Observed raw punches
    item.punches.forEach((p) => {
      const mins = isoToMinutes(p.ts);
      const timeFmt = p.ts.slice(11, 16);
      const displayType =
        p.type === 'break_start'
          ? tr('Break Start')
          : p.type === 'break_end'
          ? tr('Break End')
          : p.type === 'in'
          ? tr('Clock In')
          : tr('Clock Out');

      rawList.push({
        id: p.id,
        minutes: mins,
        timeFormatted: timeFmt,
        type: p.type,
        displayType,
        category: 'raw',
        source: p.source ?? 'kiosk',
        deviceId: p.device_id ?? 'device',
        tooltip: `${displayType} at ${timeFmt} (${p.source ?? 'kiosk'} / ${p.device_id ?? 'device'}) [ID: ${p.id}]`,
      });
    });

    // AI proposed punch
    const proposedAction = item.proposal?.actions.find((a) => a.new_ts);
    if (!editedTimeHHMM && proposedAction?.new_ts) {
      const mins = isoToMinutes(proposedAction.new_ts);
      const timeFmt = proposedAction.new_ts.slice(11, 16);
      rawList.push({
        id: 'marker-ai-proposed',
        minutes: mins,
        timeFormatted: timeFmt,
        type: proposedAction.type,
        displayType: tr('AI Proposed Out'),
        category: 'ai',
        source: 'AI Policy Grounded',
        deviceId: item.proposal?.model_id ?? 'qwen',
        tooltip: `AI Proposed Out-Punch: ${timeFmt} (${proposedAction.note})`,
      });
    }

    // Manager live edit punch
    if (editedTimeHHMM) {
      const em = hhmmToMinutes(editedTimeHHMM);
      if (em !== null) {
        rawList.push({
          id: 'marker-manager-edit',
          minutes: em,
          timeFormatted: editedTimeHHMM,
          type: 'manual_edit',
          displayType: tr('Manager Edit'),
          category: 'edit',
          source: 'Manager Live Input',
          deviceId: 'Console',
          tooltip: `Manager Corrected Time: ${editedTimeHHMM} (${item.timezone})`,
        });
      }
    }

    // Sort chronologically
    rawList.sort((a, b) => a.minutes - b.minutes);

    // Stagger close events (< 40 minutes apart) into alternating tiers to prevent overlap
    let lastTier = 0;
    let lastMins = -999;

    return rawList.map((m) => {
      let tier = 0;
      if (m.minutes - lastMins < 40) {
        tier = (lastTier + 1) % 2;
      } else {
        tier = 0;
      }
      lastMins = m.minutes;
      lastTier = tier;

      return {
        ...m,
        tier,
        leftPct: toPct(m.minutes),
      };
    });
  }, [item, editedTimeHHMM, startHour, endHour, spanMinutes, tr]);

  // Generate 2-hour axis ticks across actual range
  const ticks: number[] = [];
  for (let h = startHour; h <= endHour; h += 2) {
    ticks.push(h);
  }

  return (
    <div className="timeline-card" role="region" aria-label="Punch and schedule timeline">
      <div className="timeline-header">
        <div>
          <span className="section-label">{tr("Shift & Punch Timeline")}</span>
          <span className="small muted">
            {tr("Displaying")} {String(startHour).padStart(2, '0')}:00 – {String(endHour).padStart(2, '0')}:00 ({item.timezone})
          </span>
        </div>
        <div className="timeline-legend" aria-hidden="true">
          <span className="legend-item"><i className="dot-sched" /> {tr("Scheduled")}</span>
          <span className="legend-item"><i className="dot-raw" /> {tr("Raw Punch")}</span>
          {markers.some((m) => m.category === 'ai') && (
            <span className="legend-item"><i className="dot-ai" /> {tr("AI Proposed")}</span>
          )}
          {markers.some((m) => m.category === 'edit') && (
            <span className="legend-item"><i className="dot-edit" /> {tr("Manager Edit")}</span>
          )}
        </div>
      </div>

      <div className="timeline-track" aria-hidden="true">
        {/* Scheduled shift bar */}
        {schedStart !== null && schedEnd !== null && schedEnd > schedStart && (
          <div
            className="timeline-schedule-bar"
            style={{ left: `${schedStart}%`, width: `${schedEnd - schedStart}%` }}
            title={`${tr("Scheduled")} ${item.schedule?.start.slice(11, 16)} – ${item.schedule?.end.slice(11, 16)}`}
          >
            <span>
              {tr("Sched") + " "}{item.schedule?.start.slice(11, 16)}–{item.schedule?.end.slice(11, 16)}
            </span>
          </div>
        )}

        {/* Staggered punch and proposal markers */}
        {markers.map((m) => {
          const isAi = m.category === 'ai';
          const isEdit = m.category === 'edit';
          const markerClass = isAi
            ? 'ai-proposed'
            : isEdit
            ? 'manager-edit'
            : `raw-${m.type}`;

          return (
            <div
              key={m.id}
              tabIndex={0}
              role="button"
              className={`timeline-marker ${markerClass} tier-${m.tier}`}
              style={{ left: `${m.leftPct}%` }}
              title={m.tooltip}
              aria-label={m.tooltip}
              onMouseEnter={() => setActiveTooltip(m.tooltip)}
              onMouseLeave={() => setActiveTooltip(null)}
              onFocus={() => setActiveTooltip(m.tooltip)}
              onBlur={() => setActiveTooltip(null)}
            >
              <div className="marker-pin" />
              {m.tier === 1 && <div className="marker-stem" />}
              <div className="marker-label">
                {isAi
                  ? `AI ${m.timeFormatted}`
                  : isEdit
                  ? `Edit ${m.timeFormatted}`
                  : `${m.type === 'break_start' ? 'brk_in' : m.type === 'break_end' ? 'brk_out' : m.type} ${m.timeFormatted}`}
              </div>
            </div>
          );
        })}
      </div>

      {activeTooltip && (
        <div className="timeline-live-tooltip small mono" role="status">
          {activeTooltip}
        </div>
      )}

      <div className="timeline-axis" aria-hidden="true">
        {ticks.map((hr) => (
          <span key={hr}>{String(hr).padStart(2, '0')}:00</span>
        ))}
      </div>

      {/* Accessible event list for screen readers and keyboard users */}
      <details className="timeline-accessible-log">
        <summary className="small muted">
          <span>{tr("Accessible punch & shift log")} ({markers.length} {tr("events")})</span>
        </summary>
        <div className="timeline-events-table-wrap">
          <table className="timeline-events-table small">
            <thead>
              <tr>
                <th>{tr("Time")} ({item.timezone})</th>
                <th>{tr("Event Type")}</th>
                <th>{tr("Source & Device")}</th>
                <th>{tr("Record ID")}</th>
              </tr>
            </thead>
            <tbody>
              {item.schedule && (
                <tr>
                  <td className="mono">{item.schedule.start.slice(11, 16)} – {item.schedule.end.slice(11, 16)}</td>
                  <td><strong>{tr("Scheduled Shift")}</strong></td>
                  <td className="muted">{item.schedule.location} ({item.schedule.job})</td>
                  <td className="mono muted">{item.schedule.id}</td>
                </tr>
              )}
              {markers.map((m) => (
                <tr key={m.id}>
                  <td className="mono"><strong>{m.timeFormatted}</strong></td>
                  <td>{m.displayType}</td>
                  <td className="muted">{m.source} ({m.deviceId})</td>
                  <td className="mono muted">{m.id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
