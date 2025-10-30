// ----- Közös segédfüggvények -----
export function uid(pfx = 'id') {
  return `${pfx}_${Math.random().toString(36).slice(2, 9)}`;
}
export const clamp = (n, min, max) => Math.min(max, Math.max(min, n));
export const fmtDateTime = (ms) => new Date(ms).toLocaleString();
export const parseLocalDateTime = (val) => (val ? new Date(val).getTime() : null);

export function setSecondAlignedInterval(cb) {
  const delay = 1000 - (Date.now() % 1000);
  setTimeout(() => {
    cb();
    setInterval(cb, 1000);
  }, delay);
}

export function humanRemaining(ms) {
  const sign = ms < 0 ? -1 : 1; ms = Math.abs(ms);
  const s = Math.floor(ms / 1000);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n) => String(n).padStart(2, '0');
  const core = `${d} nap ${pad(h)}:${pad(m)}:${pad(sec)}`;
  return sign < 0 ? `Lejárt ${core}` : core;
}

export function toHex(color) {
  if (/^#([0-9a-f]{3}){1,2}$/i.test(color)) return color;
  const m = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
  if (!m) return '#6ea8fe';
  return '#' + [m[1], m[2], m[3]].map(n => Number(n).toString(16).padStart(2, '0')).join('');
}

// ----- ICS parser (egyszerű) -----
export function parseICS(icsText) {
  const lines = icsText.replace(/\r/g, '').split(/\n(?=[A-Z-]+[:;])/).map(l => l.trim());
  const events = [];
  let inEvent = false, buf = {};
  for (const raw of lines) {
    if (raw.startsWith('BEGIN:VEVENT')) { inEvent = true; buf = {}; continue; }
    if (raw.startsWith('END:VEVENT')) { inEvent = false; if (buf.dtstart) events.push(buf); buf = {}; continue; }
    if (!inEvent) continue;

    if (raw.startsWith('DTSTART')) buf.dtstart = icsDateToMs(raw);
    else if (raw.startsWith('DTEND')) buf.dtend = icsDateToMs(raw);
    else if (raw.startsWith('SUMMARY:')) buf.summary = raw.slice(8).trim();
    else if (raw.startsWith('UID:')) buf.uid = raw.slice(4).trim();
  }
  return { events };
}

export function icsDateToMs(line) {
  const mTz = line.match(/^DTSTART(?:;TZID=([^:;]+))?:(\d{8}T\d{6}Z?)/);
  if (!mTz) return Date.now();
  const [, , val] = mTz;
  const y = +val.slice(0, 4), mo = +val.slice(4, 6) - 1, d = +val.slice(6, 8),
        hh = +val.slice(9, 11), mm = +val.slice(11, 13), ss = +val.slice(13, 15);
  return val.endsWith('Z') ? Date.UTC(y, mo, d, hh, mm, ss) : new Date(y, mo, d, hh, mm, ss).getTime();
}
