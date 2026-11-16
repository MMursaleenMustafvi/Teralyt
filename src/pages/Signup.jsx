import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useTitle } from '../components/ui.jsx';
import { AuthFrame } from './Login.jsx';
import { BASE } from '../lib/data.js';
import { signup, passwordProblem, HOME } from '../lib/auth.js';

export default function Signup() {
  useTitle('Sign up');
  const nav = useNavigate();
  const [f, setF] = useState({ name: '', email: '', password: '', confirm: '', role: 'user', agree: false });
  const [err, setErr] = useState({}), [busy, setBusy] = useState(false), [pending, setPending] = useState(false);
  const ch = k => e => setF(x => ({ ...x, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));
  const strength = f.password ? (passwordProblem(f.password) ? 'weak' : f.password.length >= 12 && /[^A-Za-z0-9]/.test(f.password) ? 'strong' : 'good') : '';
  const submit = async e => {
    e.preventDefault();
    const er = {};
    if (f.password !== f.confirm) er.confirm = 'The two passwords do not match.';
    if (!f.agree) er.agree = 'Please accept that forecasts are estimates and status comes from records.';
    setErr(er); if (Object.keys(er).length) return;
    setBusy(true);
    const r = await signup(f);
    setBusy(false);
    if (!r.ok) return setErr({ [r.field || 'form']: r.msg });
    if (r.pending) return setPending(true);
    nav(HOME[r.session.role], { replace: true });
  };
  if (pending) return (
    <AuthFrame title="Create your account in a minute." text="Buyers, investors and Society Heads welcome.">
      <img className="full" src={BASE + 'logo-full.png'} alt="Terralyt" />
      <h1 style={{ textAlign: 'center' }}>Request sent</h1>
      <div className="note">Society Head accounts are approved by the System Administrator before the first log in. You can log in as soon as your account is approved.</div>
      <Link className="btn" style={{ width: '100%' }} to="/login?role=head">Go to log in</Link>
    </AuthFrame>
  );
  const E = ({ k }) => (err[k] ? <p className="ferr">{err[k]}</p> : null);
  return (
    <AuthFrame title="Create your account in a minute." text="Buyers, investors and Society Heads welcome.">
      <img className="full" src={BASE + 'logo-full.png'} alt="Terralyt" />
      <h1 style={{ textAlign: 'center' }}>Get started</h1><p className="mut" style={{ textAlign: 'center' }}>Free for the FDA City pilot.</p>
      <form onSubmit={submit} noValidate>
        <label htmlFor="nm">Full name</label><input id="nm" autoComplete="name" value={f.name} onChange={ch('name')} /><E k="name" />
        <label htmlFor="em">Email</label><input id="em" type="email" autoComplete="email" value={f.email} onChange={ch('email')} /><E k="email" />
        <label htmlFor="pw">Password</label><input id="pw" type="password" autoComplete="new-password" value={f.password} onChange={ch('password')} />
        {strength && <p className={'pws ' + strength}>Password strength: {strength}{strength === 'weak' ? ' (' + passwordProblem(f.password) + ')' : ''}</p>}<E k="password" />
        <label htmlFor="pw2">Confirm password</label><input id="pw2" type="password" autoComplete="new-password" value={f.confirm} onChange={ch('confirm')} /><E k="confirm" />
        <label htmlFor="rl">I am a</label><select id="rl" value={f.role} onChange={ch('role')}><option value="user">End User (buyer / investor)</option><option value="head">Society Head (needs approval)</option></select><E k="role" />
        <label className="chk"><input type="checkbox" checked={f.agree} onChange={ch('agree')} /> I understand that forecasts are model estimates, not guarantees, and plot status comes from society records.</label><E k="agree" />
        <E k="form" />
        <button className="btn" style={{ width: '100%' }} disabled={busy}>{busy ? 'Creating…' : 'Create account'}</button>
      </form>
      <p className="mut" style={{ textAlign: 'center' }}>Already registered? <Link to="/login">Log in</Link></p>
    </AuthFrame>
  );
}
