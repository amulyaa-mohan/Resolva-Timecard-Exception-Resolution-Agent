import { useId, useState } from 'react';
import { ExceptionItem, PunchEvent, UILang } from '../types/contracts';

interface RecordedPunchesCardProps {
  item: ExceptionItem;
  lang?: UILang;
}

const COPY: Record<
  UILang,
  {
    title: string;
    events: Record<PunchEvent['type'], string>;
    sources: Record<string, string>;
    missingClockOut: string;
    missingClockOutHint: string;
    viewSource: string;
    emptyPunches: string;
    copyId: string;
    copied: string;
    recordId: string;
    rawTimestamp: string;
    eventCode: string;
    sourceLabel: string;
    deviceLabel: string;
  }
> = {
  en: {
    title: 'Recorded punches',
    events: {
      in: 'Clock in',
      out: 'Clock out',
      break_start: 'Break started',
      break_end: 'Break ended',
    },
    sources: {
      import: 'Imported',
      imported: 'Imported',
      kiosk: 'Kiosk',
      mobile: 'Mobile',
      badge: 'Badge',
      web: 'Web',
    },
    missingClockOut: 'Clock-out missing',
    missingClockOutHint: 'No clock-out punch was recorded for this shift.',
    viewSource: 'View source records',
    emptyPunches: 'No punches recorded for this shift.',
    copyId: 'Copy ID',
    copied: 'Copied',
    recordId: 'Record ID',
    rawTimestamp: 'ISO timestamp',
    eventCode: 'Event code',
    sourceLabel: 'Source',
    deviceLabel: 'Device',
  },
  kn: {
    title: 'ದಾಖಲಾದ ಪಂಚ್‌ಗಳು (Recorded punches)',
    events: {
      in: 'ಕೆಲಸಕ್ಕೆ ಹಾಜರು (Clock in)',
      out: 'ಕೆಲಸದಿಂದ ನಿರ್ಗಮನ (Clock out)',
      break_start: 'ವಿರಾಮ ಪ್ರಾರಂಭ (Break started)',
      break_end: 'ವಿರಾಮ ಮುಕ್ತಾಯ (Break ended)',
    },
    sources: {
      import: 'ಆಮದು (Imported)',
      imported: 'ಆಮದು (Imported)',
      kiosk: 'ಕಿಯೋಸ್ಕ್ (Kiosk)',
      mobile: 'ಮೊಬೈಲ್ (Mobile)',
      badge: 'ಬ್ಯಾಡ್ಜ್ (Badge)',
      web: 'ವೆಬ್ (Web)',
    },
    missingClockOut: 'ನಿರ್ಗಮನ ಪಂಚ್ ಕಾಣೆಯಾಗಿದೆ (Clock-out missing)',
    missingClockOutHint: 'ಈ ಪಾಳಿಗೆ ಯಾವುದೇ ಕ್ಲಾಕ್-ಔಟ್ ದಾಖಲಾಗಿಲ್ಲ.',
    viewSource: 'ಮೂಲ ದಾಖಲೆಗಳನ್ನು ವೀಕ್ಷಿಸಿ',
    emptyPunches: 'ಈ ಪಾಳಿಗೆ ಯಾವುದೇ ಪಂಚ್‌ಗಳು ದಾಖಲಾಗಿಲ್ಲ.',
    copyId: 'ID ನಕಲಿಸಿ',
    copied: 'ನಕಲಿಸಲಾಗಿದೆ',
    recordId: 'ದಾಖಲೆ ID',
    rawTimestamp: 'ISO ಸಮಯ',
    eventCode: 'ಕೋಡ್',
    sourceLabel: 'ಮೂಲ',
    deviceLabel: 'ಸಾಧನ',
  },
  hi: {
    title: 'दर्ज किए गए पंच (Recorded punches)',
    events: {
      in: 'क्लॉक इन (Clock in)',
      out: 'क्लॉक आउट (Clock out)',
      break_start: 'ब्रेक शुरू (Break started)',
      break_end: 'ब्रेक समाप्त (Break ended)',
    },
    sources: {
      import: 'आयातित (Imported)',
      imported: 'आयातित (Imported)',
      kiosk: 'कियोस्क (Kiosk)',
      mobile: 'मोबाइल (Mobile)',
      badge: 'बैज (Badge)',
      web: 'वेब (Web)',
    },
    missingClockOut: 'क्लॉक-आउट गायब है (Clock-out missing)',
    missingClockOutHint: 'इस शिफ्ट के लिए कोई क्लॉक-आउट पंच दर्ज नहीं किया गया।',
    viewSource: 'स्रोत रिकॉर्ड देखें',
    emptyPunches: 'इस शिफ्ट के लिए कोई पंच दर्ज नहीं है।',
    copyId: 'ID कॉपी करें',
    copied: 'कॉपी हो गया',
    recordId: 'रिकॉर्ड ID',
    rawTimestamp: 'ISO समय',
    eventCode: 'इवेंट कोड',
    sourceLabel: 'स्रोत',
    deviceLabel: 'डिवाइस',
  },
};

function resolveIanaTimezone(rawTz?: string): string {
  const tz = (rawTz ?? '').trim();
  if (!tz) return 'Asia/Kolkata';
  if (/ist|kolkata|calcutta|\+05:30/i.test(tz)) return 'Asia/Kolkata';
  if (/cst|chicago|-06:00/i.test(tz)) return 'America/Chicago';
  if (/pst|los_angeles|-08:00/i.test(tz)) return 'America/Los_Angeles';
  if (/est|new_york|-05:00/i.test(tz)) return 'America/New_York';
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: tz }).format(new Date());
    return tz;
  } catch {
    return 'Asia/Kolkata';
  }
}

function formatWorkDate(workDate: string, ianaTz: string): string {
  const parsed = new Date(`${workDate}T12:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return workDate;
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: ianaTz,
  }).format(parsed);
}

function formatPunchInTimezone(
  isoTs: string,
  ianaTz: string
): { time: string; isoDate: string; shortDate: string } {
  const date = new Date(isoTs);
  if (Number.isNaN(date.getTime())) {
    return { time: isoTs.slice(11, 16) || isoTs, isoDate: isoTs.slice(0, 10), shortDate: '' };
  }

  const time = new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: ianaTz,
  }).format(date);

  const ymdParts = new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone: ianaTz,
  }).formatToParts(date);
  const year = ymdParts.find((p) => p.type === 'year')?.value ?? '';
  const month = ymdParts.find((p) => p.type === 'month')?.value ?? '';
  const day = ymdParts.find((p) => p.type === 'day')?.value ?? '';
  const isoDate = year && month && day ? `${year}-${month}-${day}` : '';

  const shortDate = new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    timeZone: ianaTz,
  }).format(date);

  return { time, isoDate, shortDate };
}

function isPresentMeta(val?: string | null): val is string {
  if (!val) return false;
  const cleaned = val.trim();
  if (!cleaned) return false;
  return !/^(null|undefined|none|n\/a|-)$/i.test(cleaned);
}

export function RecordedPunchesCard({ item, lang = 'en' }: RecordedPunchesCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const disclosureId = useId();
  const t = COPY[lang];

  const ianaTz = resolveIanaTimezone(item.timezone);
  const formattedDate = formatWorkDate(item.work_date, ianaTz);

  const formattedPunches = item.punches.map((punch) => {
    const local = formatPunchInTimezone(punch.ts, ianaTz);
    const crossedMidnight = Boolean(local.isoDate && item.work_date && local.isoDate !== item.work_date);
    const rawSource = isPresentMeta(punch.source) ? punch.source.trim() : '';
    const sourceText = rawSource
      ? t.sources[rawSource.toLowerCase()] ?? rawSource.charAt(0).toUpperCase() + rawSource.slice(1)
      : '';
    const deviceText = isPresentMeta(punch.device_id) ? punch.device_id.trim() : '';

    return {
      punch,
      time: local.time,
      shortDate: local.shortDate,
      crossedMidnight,
      eventLabel: t.events[punch.type] ?? punch.type,
      sourceText,
      rawSource,
      deviceText,
    };
  });

  const hasOutPunch = item.punches.some((p) => p.type === 'out');
  const hasInPunch = item.punches.some((p) => p.type === 'in');
  const explicitlyMissingOut =
    !hasOutPunch &&
    ((item.code === 'MISSING_PUNCH' && (hasInPunch || /clock-out|out-punch/i.test(item.summary))) ||
      /missing\s+(clock[- ]?out|out[- ]?punch)/i.test(item.summary));

  const handleCopyId = async (id: string) => {
    try {
      await navigator.clipboard.writeText(id);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = id;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    }
    setCopiedId(id);
    window.setTimeout(() => {
      setCopiedId((prev) => (prev === id ? null : prev));
    }, 1800);
  };

  return (
    <section className="recorded-punches-card" aria-labelledby={`${disclosureId}-heading`}>
      <div className="recorded-punches-header">
        <h3 id={`${disclosureId}-heading`} className="recorded-punches-title">
          {t.title}
        </h3>
        <p className="recorded-punches-subtitle">
          <span>{formattedDate}</span>
          <span aria-hidden="true"> · </span>
          <span>{ianaTz}</span>
        </p>
      </div>

      {formattedPunches.length === 0 ? (
        <p className="muted small" style={{ margin: '8px 0' }}>
          {t.emptyPunches}
        </p>
      ) : (
        <ul className="recorded-punches-list">
          {formattedPunches.map(({ punch, time, shortDate, crossedMidnight, eventLabel, sourceText }) => (
            <li key={punch.id} className="recorded-punch-row">
              <div className="recorded-punch-time-cell">
                <span className="recorded-punch-time">{time}</span>
                {crossedMidnight && shortDate && (
                  <span className="recorded-punch-nextday" title="Crossed midnight into next calendar day">
                    {shortDate}
                  </span>
                )}
              </div>
              <span className="recorded-punch-event">{eventLabel}</span>
              {sourceText && <span className="recorded-punch-source">{sourceText}</span>}
            </li>
          ))}
        </ul>
      )}

      {explicitlyMissingOut && (
        <div className="missing-clockout-notice" role="note">
          <span className="missing-clockout-dot" aria-hidden="true" />
          <div>
            <div className="missing-clockout-title">{t.missingClockOut}</div>
            <div className="missing-clockout-sub">{t.missingClockOutHint}</div>
          </div>
        </div>
      )}

      <div className="source-disclosure-footer">
        <button
          type="button"
          className="source-disclosure-toggle"
          aria-expanded={expanded}
          aria-controls={disclosureId}
          onClick={() => setExpanded((prev) => !prev)}
        >
          <span>{t.viewSource}</span>
          <span className="source-disclosure-chevron" aria-hidden="true">
            {expanded ? '▾' : '▸'}
          </span>
        </button>

        {expanded && (
          <div id={disclosureId} className="source-records-drawer">
            {formattedPunches.map(({ punch, rawSource, deviceText }) => (
              <div key={punch.id} className="source-record-item">
                <div className="source-record-top">
                  <div className="source-record-id-group">
                    <span className="source-meta-label">{t.recordId}:</span>
                    <code className="mono source-record-id">{punch.id}</code>
                  </div>
                  <button
                    type="button"
                    className="btn-secondary source-copy-btn"
                    aria-label={`${t.copyId} ${punch.id}`}
                    onClick={() => handleCopyId(punch.id)}
                  >
                    {copiedId === punch.id ? t.copied : t.copyId}
                  </button>
                </div>

                <dl className="source-record-meta">
                  <div className="source-meta-pair">
                    <dt>{t.rawTimestamp}</dt>
                    <dd className="mono">{punch.ts}</dd>
                  </div>
                  <div className="source-meta-pair">
                    <dt>{t.eventCode}</dt>
                    <dd className="mono">{punch.type}</dd>
                  </div>
                  {rawSource && (
                    <div className="source-meta-pair">
                      <dt>{t.sourceLabel}</dt>
                      <dd className="mono">{rawSource}</dd>
                    </div>
                  )}
                  {deviceText && (
                    <div className="source-meta-pair">
                      <dt>{t.deviceLabel}</dt>
                      <dd className="mono">{deviceText}</dd>
                    </div>
                  )}
                </dl>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
