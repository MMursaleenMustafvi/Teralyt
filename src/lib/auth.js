// Accounts and sessions, kept in this browser until the backend exists (then the same functions call the API).
// Three roles from the use case diagram: End User, Society Head, System Administrator.
// Passwords are stored only as a SHA-256 hash; five wrong passwords lock the account for five minutes;
// Society Head accounts need an administrator's approval; administrators cannot sign up, only log in.
import { get, set, update, useStored, now, audit } from './store.js';

export const ROLES = { user: 'End User', head: 'Society Head', admin: 'System Administrator' };
export const HOME = { user: '/dashboard', head: '/society', admin: '/admin' };
export const DEMO_PASSWORD = 'Terralyt@2026';
const DEMO = [
  { name: 'Ali Raza', email: 'user@terralyt.pk', role: 'user' },
  { name: 'Sana Khan', email: 'head@terralyt.pk', role: 'head' },
  { name: 'System Admin', email: 'admin@terralyt.pk', role: 'admin' }
];
const MAX_TRIES = 5, LOCK_MS = 5 * 60 * 1000;

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
export function passwordProblem(pw) {
  if (pw.length < 8) return 'Use at least 8 characters.';
  if (!/[A-Za-z]/.test(pw) || !/\d/.test(pw)) return 'Use letters and at least one number.';
  return '';
}

async function hash(text) {
  if (window.crypto && crypto.subtle) {
    const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode('terralyt:' + text));
    return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
  }
  // not a secure context (e.g. opened over the LAN by IP): a plain 53-bit hash; the backend will replace this
  let h1 = 0xdeadbeef, h2 = 0x41c6ce57;
  for (const ch of 'terralyt:' + text) { const c = ch.charCodeAt(0); h1 = Math.imul(h1 ^ c, 2654435761); h2 = Math.imul(h2 ^ c, 1597334677); }
  return 'w' + ((h2 >>> 0) * 4294967296 + (h1 >>> 0)).toString(16);
}

export async function ensureAccounts() {
  const users = get('users', null);
  if (users && users.length) return users;
  const h = await hash(DEMO_PASSWORD);
  const seeded = DEMO.map((u, i) => ({ id: i + 1, ...u, hash: h, status: 'Active', created: now(), demo: true }));
  set('users', seeded);
  return seeded;
}

export const getSession = () => get('session', null);
export function useSession() { return useStored('session', null); }
export function logout() {
  const s = getSession();
  if (s) audit(s.name, 'Logged out', ROLES[s.role]);
  set('session', null);
}

export async function login(email, password, role) {
  email = String(email || '').trim().toLowerCase();
  if (!EMAIL_RE.test(email)) return { ok: false, msg: 'Enter a valid email address.' };
  if (!password) return { ok: false, msg: 'Enter your password.' };
  const users = await ensureAccounts();
  const locks = get('locks', {}), lk = locks[email];
  if (lk && lk.until && Date.now() < lk.until) {
    return { ok: false, msg: `Too many wrong passwords. This account is locked for ${Math.ceil((lk.until - Date.now()) / 60000)} more minute(s).` };
  }
  const u = users.find(x => x.email === email);
  const h = await hash(password);
  if (!u || u.hash !== h) {
    const tries = (lk && lk.until && Date.now() < lk.until ? lk.tries : (lk ? lk.tries : 0)) + 1;
    update('locks', {}, l => ({ ...l, [email]: tries >= MAX_TRIES ? { tries: 0, until: Date.now() + LOCK_MS } : { tries, until: 0 } }));
    if (tries >= MAX_TRIES) { audit(email, 'Account locked', MAX_TRIES + ' wrong passwords'); return { ok: false, msg: 'Too many wrong passwords. The account is locked for 5 minutes.' }; }
    return { ok: false, msg: `Email or password is not correct. ${MAX_TRIES - tries} attempt(s) left before the account locks.` };
  }
  if (role && u.role !== role) return { ok: false, msg: `This account is registered as ${ROLES[u.role]}, not ${ROLES[role]}.` };
  if (u.status === 'Pending') return { ok: false, msg: 'Your Society Head account is waiting for an administrator to approve it.' };
  if (u.status === 'Disabled') return { ok: false, msg: 'This account is disabled. Contact the administrator.' };
  update('locks', {}, l => { const c = { ...l }; delete c[email]; return c; });
  const session = { id: u.id, name: u.name, email: u.email, role: u.role, since: now() };
  set('session', session);
  update('users', [], l => l.map(x => x.id === u.id ? { ...x, lastLogin: now() } : x));
  audit(u.name, 'Logged in', ROLES[u.role]);
  return { ok: true, session };
}

export async function signup({ name, email, password, role }) {
  name = String(name || '').trim(); email = String(email || '').trim().toLowerCase();
  if (name.length < 2) return { ok: false, field: 'name', msg: 'Enter your full name.' };
  if (!EMAIL_RE.test(email)) return { ok: false, field: 'email', msg: 'Enter a valid email address.' };
  const pp = passwordProblem(password || ''); if (pp) return { ok: false, field: 'password', msg: pp };
  if (!['user', 'head'].includes(role)) return { ok: false, field: 'role', msg: 'Choose End User or Society Head.' };
  const users = await ensureAccounts();
  if (users.some(u => u.email === email)) return { ok: false, field: 'email', msg: 'An account with this email already exists. Log in instead.' };
  const u = { id: Math.max(0, ...users.map(x => x.id)) + 1, name, email, role, hash: await hash(password), status: role === 'head' ? 'Pending' : 'Active', created: now() };
  set('users', [...users, u]);
  audit(name, 'Signed up', ROLES[role] + (u.status === 'Pending' ? ' (waiting for approval)' : ''));
  if (u.status === 'Pending') return { ok: true, pending: true };
  const session = { id: u.id, name: u.name, email: u.email, role: u.role, since: now() };
  set('session', session);
  return { ok: true, session };
}

// ---- administrator: manage accounts ----
export async function addUser(by, { name, email, role, password }) {
  name = String(name || '').trim(); email = String(email || '').trim().toLowerCase();
  if (name.length < 2) return { ok: false, msg: 'Enter the full name.' };
  if (!EMAIL_RE.test(email)) return { ok: false, msg: 'Enter a valid email address.' };
  if (!ROLES[role]) return { ok: false, msg: 'Choose a role.' };
  const pp = passwordProblem(password || ''); if (pp) return { ok: false, msg: 'Temporary password: ' + pp };
  const users = await ensureAccounts();
  if (users.some(u => u.email === email)) return { ok: false, msg: 'An account with this email already exists.' };
  set('users', [...users, { id: Math.max(0, ...users.map(x => x.id)) + 1, name, email, role, hash: await hash(password), status: 'Active', created: now() }]);
  audit(by, 'Added user', `${name} (${ROLES[role]})`);
  return { ok: true };
}
export function setUser(by, id, changes, what) {
  update('users', [], l => l.map(u => u.id === id ? { ...u, ...changes } : u));
  const u = get('users', []).find(x => x.id === id);
  audit(by, what, u ? `${u.name} (${u.email})` : String(id));
}
export function removeUser(by, id) {
  const u = get('users', []).find(x => x.id === id);
  update('users', [], l => l.filter(x => x.id !== id));
  audit(by, 'Removed user', u ? `${u.name} (${u.email})` : String(id));
}
