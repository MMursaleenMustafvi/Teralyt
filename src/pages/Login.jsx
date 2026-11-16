import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Logo, useTitle } from '../components/ui.jsx';
import { BASE } from '../lib/data.js';
import { login, logout, useSession, HOME, ROLES, DEMO_PASSWORD, EMAIL_RE } from '../lib/auth.js';

export function AuthFrame({ title, text, children }) {
  return (
    <div className="auth2">
      <div className="aimg"><Link className="brand" to="/" style={{ padding: 0 }}><Logo />Terralyt</Link><div><h2>{title}</h2><p style={{ color: '#cdbd9f' }}>{text}</p></div></div>
      <div className="af"><div>{children}</div></div>
    </div>
  );
}

export default function Login() {
  useTitle('Log in');
  const [q] = useSearchParams(), nav = useNavigate(), s = useSession();
  const [email, setEmail] = useState(''), [pw, setPw] = useState(''), [role, setRole] = useState(q.get('role') && ROLES[q.get('role')] ? q.get('role') : 'user');
  const [msg, setMsg] = useState(''), [busy, setBusy] = useState(false), [show, setShow] = useState(false), [forgot, setForgot] = useState(false);
  const next = q.get('next');
  const submit = async e => {
    e.preventDefault(); setMsg('');
    if (!EMAIL_RE.test(email.trim())) return setMsg('Enter a valid email address.');
    if (!pw) return setMsg('Enter your password.');
    setBusy(true);
    const r = await login(email, pw, role);
    setBusy(false);
    if (!r.ok) return setMsg(r.msg);
    nav(next && next.startsWith('/') ? next : HOME[r.session.role], { replace: true });
  };
  const demo = r => { setRole(r); setEmail(r + '@terralyt.pk'); setPw(DEMO_PASSWORD); setMsg(''); };
  return (
    <AuthFrame title="Satellite evidence, not guesswork." text="Evaluate FDA City from anywhere.">
      <img className="full" src={BASE + 'logo-full.png'} alt="Terralyt" />
      {s && <div className="note">You are logged in as <b>{s.name}</b> ({ROLES[s.role]}). <Link to={HOME[s.role]}>Continue</Link> · <a href="#/login" onClick={e => { e.preventDefault(); logout(); }}>Log out</a></div>}
      <h1 style={{ textAlign: 'center' }}>Welcome back</h1><p className="mut" style={{ textAlign: 'center' }}>Log in to your account.</p>
      <form onSubmit={submit} noValidate>
        <label htmlFor="em">Email</label><input id="em" type="email" autoComplete="username" placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)} />
        <label htmlFor="pw">Password</label>
        <div className="pwrow"><input id="pw" type={show ? 'text' : 'password'} autoComplete="current-password" placeholder="••••••••" value={pw} onChange={e => setPw(e.target.value)} /><button type="button" className="pweye" onClick={() => setShow(x => !x)}>{show ? 'Hide' : 'Show'}</button></div>
        <label htmlFor="rl">Role</label><select id="rl" value={role} onChange={e => setRole(e.target.value)}>{Object.entries(ROLES).map(([k, t]) => <option key={k} value={k}>{t}</option>)}</select>
        {msg && <p className="ferr" role="alert">{msg}</p>}
        <button className="btn" style={{ width: '100%' }} disabled={busy}>{busy ? 'Checking…' : 'Log in'}</button>
      </form>
      <p className="mut" style={{ textAlign: 'center' }}><a href="#/login" onClick={e => { e.preventDefault(); setForgot(x => !x); }}>Forgot password?</a> · <Link to="/signup">Create account</Link></p>
      {forgot && <div className="note">Password reset needs the email service of the backend, which is not connected yet. Ask the System Administrator to set a new password for you.</div>}
      <div className="note">Administrators can only log in. Five wrong passwords lock an account for five minutes.</div>
      <div className="demo"><b>Demo accounts</b> (until the backend is connected, accounts are kept in this browser). Password <code>{DEMO_PASSWORD}</code>
        <div className="demob">{Object.entries(ROLES).map(([k, t]) => <button key={k} type="button" className="btn o sm" onClick={() => demo(k)}>{t}</button>)}</div></div>
    </AuthFrame>
  );
}
