/**
 * NAS Storage Monitor — Google Sheet back end.
 *
 * The dashboard (https://andersonreports.github.io/NAS-Storage-monitor/) sends every
 * "Update data" save here, and this script writes the rows into that NAS's tab.
 *
 * One-time setup (in the NAS STORAGE sheet: Extensions → Apps Script):
 *   1. Paste this file over the default Code.gs and change EDIT_KEY below. Save.
 *   2. Pick "setup" in the function list at the top and click Run (allow access when asked).
 *   3. Deploy → New deployment → gear icon → Web app → Execute as: Me, Who has access: Anyone → Deploy.
 *   4. Copy the Web app URL (ends in /exec) and add it to the dashboard.
 */
const EDIT_KEY = 'change-this-key';   // typed on the dashboard when saving

const TABS = ['CMC', 'NGS'];
const HEAD = ['Date', 'Department', 'Users', 'Samples', 'Copied (GB)', '% data copied'];
const WIDTHS = [100, 230, 100, 80, 110, 120];
const FIRST_DATE = '2026-10-07';      // date given to rows that were in a tab before it had a Date column

const DEPARTMENTS = [
  ['user1', 'Haematology'], ['user2', 'Haematology'], ['user3', 'Haematology'], ['user4', 'Nephrology'],
  ['user5', 'Cytogenetics'], ['user6', 'Medical Genetics'], ['user7', 'Molecular Endocrinology'],
  ['user8', 'Molecular Pathology'], ['user9', 'Neurophysiology'], ['germline', 'Germline'], ['somatic', 'Somatic'],
];

/** Run once. Keeps existing rows: adds the Date column in front of them, never deletes data. */
function setup() {
  const ss = SpreadsheetApp.getActive();
  TABS.forEach(name => migrate(ss.getSheetByName(name) || ss.insertSheet(name)));
  const d = ss.getSheetByName('Departments') || ss.insertSheet('Departments');
  if (String(d.getRange(1, 1).getValue()).toLowerCase() !== 'username') {
    d.clear();
    d.getRange(1, 1, 1, 2).setValues([['Username', 'Department']]);
    d.getRange(2, 1, DEPARTMENTS.length, 2).setValues(DEPARTMENTS);
  }
  styleHeader(d.getRange(1, 1, 1, 2));
  d.setFrozenRows(1); d.setColumnWidth(1, 110); d.setColumnWidth(2, 220);
}

/** Turn whatever is in the tab into the HEAD layout, keeping department rows that have data. */
function migrate(sh) {
  const vals = sh.getDataRange().getValues();
  const h = vals.findIndex(r => r.some(c => String(c).trim().toLowerCase() === 'department'));
  let rows = [];
  if (h >= 0) {
    const head = vals[h].map(c => String(c).trim().toLowerCase());
    const col = re => head.findIndex(c => re.test(c));
    const ci = { date: col(/^date$/), dep: col(/^department/), share: col(/dest|share|username|^users?$/),
      smp: col(/^samples$/), cop: col(/^copied/), pct: col(/%.*copied/) };
    const get = (r, i) => i >= 0 ? r[i] : '';
    rows = vals.slice(h + 1)
      .filter(r => String(get(r, ci.dep)).trim() && !/^total/i.test(String(get(r, ci.dep))))
      .filter(r => [ci.smp, ci.cop, ci.pct].some(i => i >= 0 && r[i] !== '' && r[i] !== null))
      .map(r => [ci.date >= 0 ? dateKey(r[ci.date]) : FIRST_DATE, String(get(r, ci.dep)).trim(), clean(get(r, ci.share)).toLowerCase(),
        num(get(r, ci.smp)), num(get(r, ci.cop)), pct(get(r, ci.pct))]);
  }
  sh.clear();
  formatTab(sh);
  rewrite(sh, rows);
}

function formatTab(sh) {
  sh.getRange(1, 1, 1, HEAD.length).setValues([HEAD]);
  styleHeader(sh.getRange(1, 1, 1, HEAD.length));
  sh.setFrozenRows(1);
  WIDTHS.forEach((w, i) => sh.setColumnWidth(i + 1, w));
  const n = sh.getMaxRows() - 1;
  sh.getRange(2, 1, n, 3).setNumberFormat('@');           // Date (yyyy-mm-dd), Department, Users as text
  sh.getRange(2, 4, n, 1).setNumberFormat('#,##0');
  sh.getRange(2, 5, n, 1).setNumberFormat('#,##0.##');
  sh.getRange(2, 6, n, 1).setNumberFormat('0.0%');
  sh.getRange(2, 4, n, 3).setHorizontalAlignment('right');
  if (sh.getFilter()) sh.getFilter().remove();
  sh.getRange(1, 1, sh.getMaxRows(), HEAD.length).createFilter();
}

function styleHeader(r) {
  r.setFontWeight('bold').setBackground('#1f4e79').setFontColor('#ffffff').setVerticalAlignment('middle');
}

function clean(v) { const s = String(v == null ? '' : v).trim(); return s === '-' || /^n\/?a$/i.test(s) ? '' : s; }
function num(v) { const s = String(v == null ? '' : v).replace(/[,%\s]/g, ''); return s === '' || isNaN(Number(s)) ? '' : Number(s); }
/** % as a fraction for the 0.0% format: 66.8, "66.8%" and 0.668 all become 0.668 */
function pct(v) {
  if (v === '' || v === null || v === undefined) return '';
  const n = typeof v === 'number' ? v : num(v);
  if (n === '') return '';
  return Math.round((typeof v === 'number' && n <= 1 ? n : n / 100) * 10000) / 10000;
}

function dateKey(v) {
  if (v instanceof Date) return Utilities.formatDate(v, SpreadsheetApp.getActive().getSpreadsheetTimeZone(), 'yyyy-MM-dd');
  const s = String(v).trim(); return /^\d{4}-\d{2}-\d{2}/.test(s) ? s.slice(0, 10) : FIRST_DATE;
}

function existing(sh) {
  const last = sh.getLastRow();
  if (last < 2) return [];
  return sh.getRange(2, 1, last - 1, HEAD.length).getValues().filter(r => String(r[1]).trim()).map(r => { r[0] = dateKey(r[0]); return r; });
}

/** Newest date first; within a date the order the rows were saved in. */
function rewrite(sh, rows) {
  const last = sh.getLastRow();
  if (last > 1) sh.getRange(2, 1, last - 1, HEAD.length).clearContent();
  rows = rows.map((r, i) => [r, i]).sort((a, b) => b[0][0].localeCompare(a[0][0]) || a[1] - b[1]).map(x => x[0]);
  if (rows.length) sh.getRange(2, 1, rows.length, HEAD.length).setValues(rows);
}

function doPost(e) {
  try {
    const b = JSON.parse(e.postData.contents);
    if (b.key !== EDIT_KEY) return out({ ok: false, error: 'Wrong edit key' });
    if (TABS.indexOf(b.tab) < 0) return out({ ok: false, error: 'Unknown tab: ' + b.tab });
    if (!/^\d{4}-\d{2}-\d{2}$/.test(b.date || '')) return out({ ok: false, error: 'Date must be yyyy-mm-dd' });
    const lock = LockService.getScriptLock();
    lock.waitLock(30000);
    try {
      const sh = SpreadsheetApp.getActive().getSheetByName(b.tab);
      if (String(sh.getRange(1, 1).getValue()) !== 'Date') migrate(sh);
      const keep = existing(sh).filter(r => r[0] !== b.date);
      if (b.action === 'delete') { rewrite(sh, keep); return out({ ok: true }); }
      if (b.action !== 'save') return out({ ok: false, error: 'Unknown action' });
      const rows = (b.rows || []).filter(r => String(r.department || '').trim()).map(r =>
        [b.date, String(r.department).trim(), clean(r.share).toLowerCase(), num(r.samples), num(r.copied_gb), pct(r.pct_copied)]);
      rewrite(sh, keep.concat(rows));
      return out({ ok: true, saved: rows.length });
    } finally {
      lock.releaseLock();
    }
  } catch (err) {
    return out({ ok: false, error: String(err && err.message || err) });
  }
}

function doGet() { return out({ ok: true, app: 'NAS Storage Monitor', tabs: TABS }); }

function out(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }
