// vz-utils.js  —  közös segédfüggvények (ES module)

// ---------------------------------------------------------------------
// Általános utilok
// ---------------------------------------------------------------------

export function uid(prefix = 'id') {
  // Rövid, ütközés-szegény UID kliens oldali objektumokhoz
  const r = Math.random().toString(36).slice(2, 8);
  const t = Date.now().toString(36).slice(-6);
  return `${prefix}_${t}${r}`;
}

export function clamp(n, min, max) {
  return Math.min(Math.max(n, min), max);
}

export function toHex(input) {
  // Elfogad: "#rrggbb", "#rgb", "rgb(r,g,b)", "rgba(r,g,b,a)"
  if (!input) return '#000000';
  const s = String(input).trim();

  // #rrggbb vagy #rgb
  if (/^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(s)) {
    if (s.length === 4) {
      // #abc -> #aabbcc
      return '#' + [...s.slice(1)].map(ch => ch + ch).join('');
    }
    return s.toLowerCase();
  }

  // rgb/rgba
  const m = /^rgba?\(\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})/i.exec(s);
  if (m) {
    const r = clamp(parseInt(m[1], 10), 0, 255);
    const g = clamp(parseInt(m[2], 10), 0, 255);
    const b = clamp(parseInt(m[3], 10), 0, 255);
    const hex = (x) => x.toString(16).padStart(2, '0');
    return `#${hex(r)}${hex(g)}${hex(b)}`;
  }

  // Nem ismert: hagyjuk békén (hátha CSS név)
  return s;
}

// ---------------------------------------------------------------------
// Dátum/idő utilok
// ---------------------------------------------------------------------

export function fmtDateTime(ms) {
  // 2025. 03. 09. 14:05 formátum (helyi idő)
  const d = new Date(ms);
  const y = d.getFullYear();
  const M = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const h = String(d.getHours()).padStart(2, '0');
  const m = String(d.getMinutes()).padStart(2, '0');
  return `${y}. ${M}. ${day}. ${h}:${m}`;
}

export function parseLocalDateTime(localStr) {
  // "YYYY-MM-DDTHH:MM" (input[type=datetime-local]) -> epoch ms helyi időből
  // Safari eltérően viselkedhet, ezért kézzel parszolunk.
  if (!localStr) return Date.now();
  // engedjük másodpercet is, ha véletlenül érkezik: "YYYY-MM-DDTHH:MM[:SS]"
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(localStr);
  if (!m) {
    const t = Date.parse(localStr);
    return isNaN(t) ? Date.now() : t;
  }
  const [_, Y, Mo, D, H, Mi, S] = m;
  const ms = new Date(
    Number(Y),
    Number(Mo) - 1,
    Number(D),
    Number(H),
    Number(Mi),
    S ? Number(S) : 0,
    0
  ).getTime();
  return ms;
}

export function setSecondAlignedInterval(callback) {
  // másodperchez igazított ismétlés
  try { callback(); } catch {}
  const startIn = 1000 - (Date.now() % 1000);
  setTimeout(() => {
    try { callback(); } catch {}
    setInterval(() => { try { callback(); } catch {} }, 1000);
  }, startIn);
}

export function humanRemaining(ms) {
  // Rövid, magyaros visszaszámláló: "3 nap 04:05:06" / "04:05:06" / "00:12"
  if (ms <= 0) return '0:00';
  let s = Math.floor(ms / 1000);
  const days = Math.floor(s / 86400);
  s -= days * 86400;
  const h = Math.floor(s / 3600); s -= h * 3600;
  const m = Math.floor(s / 60);   s -= m * 60;

  const hh = String(h).padStart(2, '0');
  const mm = String(m).padStart(2, '0');
  const ss = String(s).padStart(2, '0');

  if (days > 0) return `${days} nap ${hh}:${mm}:${ss}`;
  if (h > 0)    return `${hh}:${mm}:${ss}`;
  return `${mm}:${ss}`;
}

// ---------------------------------------------------------------------
// ICS parser — javított változat
//  - RFC5545 line folding (unfolding)
//  - DTSTART prioritás (ha nincs: DTEND → DUE → DTSTAMP)
//  - TZID= paraméter kezelése (egyszerűsítve: nem konvertálunk zónát, helyi időnek vesszük)
//  - Allday (DATE) → helyi éjfél
//  - Duplikátum szűrés: UID + RECURRENCE-ID
// ---------------------------------------------------------------------

function icsUnfold(text) {
  // CRLF normalizálás és folding feloldása: \n + SPACE/TAB => sorok egyesítése
  const norm = String(text).replace(/\r\n|\r/g, '\n');
  return norm.replace(/\n[ \t]/g, '');
}

function icsParseDate(val, tzid) {
  // YYYYMMDD vagy YYYYMMDDTHHMMSS(Z)
  const v = String(val).trim();

  const mDate = /^(\d{4})(\d{2})(\d{2})$/.exec(v);
  if (mDate) {
    const y = +mDate[1], M = +mDate[2], d = +mDate[3];
    // Egész napos esemény: helyi éjfél
    return new Date(y, M - 1, d, 0, 0, 0).getTime();
  }

  const mDT = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(Z)?$/.exec(v);
  if (mDT) {
    const y = +mDT[1], M = +mDT[2], d = +mDT[3];
    const h = +mDT[4], mi = +mDT[5], s = +mDT[6];
    const z = mDT[7] === 'Z';
    if (z) {
      // UTC
      return Date.UTC(y, M - 1, d, h, mi, s);
    }
    // Van TZID paraméter? Most egyszerűen helyi időnek értelmezzük.
    // (Ha kell igazi zóna-kezelés, külön lib szükséges.)
    return new Date(y, M - 1, d, h, mi, s).getTime();
  }

  // Tartalék: hagyjuk a JS parserre
  const t = Date.parse(v);
  return isNaN(t) ? Date.now() : t;
}

export function parseICS(text) {
  const lines = icsUnfold(text).split('\n');
  const events = [];
  const seen = new Set(); // UID + RECURRENCE-ID kulcsok

  let cur = null;

  for (const line of lines) {
    if (line === 'BEGIN:VEVENT') { cur = {}; continue; }
    if (line === 'END:VEVENT') {
      if (cur) {
        const ts =
          cur.__dtstart ??
          cur.__dtend ??
          cur.__due ??
          cur.__dtstamp;

        if (ts != null) {
          const key = `${cur.__uid || ''}__${cur.__rid || ''}`;
          if (!seen.has(key)) {
            events.push({
              summary: (cur.__summary || '').trim(),
              dtstart: ts
            });
            seen.add(key);
          }
        }
      }
      cur = null;
      continue;
    }
    if (!cur) continue;

    // PROPNAME[;PARAMS]:VALUE
    const m = /^([A-Z-]+)(;[^:]*)?:(.*)$/i.exec(line);
    if (!m) continue;
    const prop = m[1].toUpperCase();
    const params = m[2] || '';
    const value = m[3] || '';

    if (prop === 'SUMMARY') {
      cur.__summary = value.replace(/\\n/g, ' ').replace(/\\,/g, ',');
    } else if (prop === 'UID') {
      cur.__uid = value.trim();
    } else if (prop === 'RECURRENCE-ID') {
      const tzid = /TZID=([^;:]+)/i.exec(params)?.[1];
      cur.__rid = icsParseDate(value, tzid);
    } else if (prop === 'DTSTART' || prop.startsWith('DTSTART;')) {
      const tzid = /TZID=([^;:]+)/i.exec(params)?.[1];
      cur.__dtstart = icsParseDate(value, tzid);
    } else if (prop === 'DTEND' || prop.startsWith('DTEND;')) {
      const tzid = /TZID=([^;:]+)/i.exec(params)?.[1];
      cur.__dtend = icsParseDate(value, tzid);
    } else if (prop === 'DUE' || prop.startsWith('DUE;')) {
      const tzid = /TZID=([^;:]+)/i.exec(params)?.[1];
      cur.__due = icsParseDate(value, tzid);
    } else if (prop === 'DTSTAMP') {
      cur.__dtstamp = icsParseDate(value, null);
    }
    // A többi mezőt most nem használjuk (RRULE, LOCATION stb.)
  }

  // Idő szerinti növekvő sorrend
  events.sort((a, b) => a.dtstart - b.dtstart);

  return { events };
}
