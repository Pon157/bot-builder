import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Megaphone, Mail, Lock, Eye, EyeOff, Loader2,
  AlertTriangle, ArrowLeft, CheckCircle, KeyRound, RefreshCw
} from 'lucide-react';

const post = async (url: string, body: object) => {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || 'Ошибка сервера');
  return data;
};

type Screen = 'login' | 'register' | 'register_code' | 'forgot' | 'reset_code';

// ─── EmailCodeInput ─────────────────────────────────────────────────────────────
const EmailCodeInput: React.FC<{
  value: string; onChange: (v: string) => void; disabled?: boolean;
}> = ({ value, onChange, disabled }) => (
  <input
    value={value}
    onChange={e => onChange(e.target.value.replace(/\D/g, '').slice(0, 6))}
    disabled={disabled}
    inputMode="numeric"
    pattern="[0-9]*"
    maxLength={6}
    autoComplete="one-time-code"
    placeholder="_ _ _ _ _ _"
    className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3 text-center text-xl font-mono text-white tracking-[0.5em] focus:outline-none focus:border-amber-500 transition-colors disabled:opacity-50"
  />
);

// ─── Standalone field components (outside main component to avoid re-mount) ────
// БАГ-ФИХ: Если объявлять InputEmail/InputPassword внутри AdsAuth,
// React при каждом ре-рендере считает их новыми типами и размонтирует DOM-узел,
// что сбрасывает фокус и переносит набор текста в другой инпут.
// Решение: вынести в отдельные компоненты вне тела AdsAuth.

interface EmailFieldProps {
  value: string;
  onChange: (v: string) => void;
}
const EmailField: React.FC<EmailFieldProps> = ({ value, onChange }) => (
  <div>
    <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5">Email</label>
    <div className="relative">
      <Mail size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-600 pointer-events-none" />
      <input
        type="email"
        value={value}
        onChange={e => onChange(e.target.value)}
        autoComplete="email"
        autoFocus
        className="w-full bg-zinc-900 border border-zinc-800 rounded-xl pl-9 pr-3 py-2.5 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-amber-500 transition-colors"
        placeholder="agency@company.com"
      />
    </div>
  </div>
);

interface PasswordFieldProps {
  label?: string;
  placeholder?: string;
  value: string;
  onChange: (v: string) => void;
  showPwd: boolean;
  onToggleShow: () => void;
  autoComplete?: string;
}
const PasswordField: React.FC<PasswordFieldProps> = ({
  label = 'Пароль',
  placeholder = '••••••••',
  value,
  onChange,
  showPwd,
  onToggleShow,
  autoComplete = 'current-password',
}) => (
  <div>
    <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5">{label}</label>
    <div className="relative">
      <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-600 pointer-events-none" />
      <input
        type={showPwd ? 'text' : 'password'}
        value={value}
        onChange={e => onChange(e.target.value)}
        autoComplete={autoComplete}
        minLength={6}
        className="w-full bg-zinc-900 border border-zinc-800 rounded-xl pl-9 pr-9 py-2.5 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-amber-500 transition-colors"
        placeholder={placeholder}
      />
      <button
        type="button"
        onClick={onToggleShow}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-600 hover:text-zinc-400"
      >
        {showPwd ? <EyeOff size={14} /> : <Eye size={14} />}
      </button>
    </div>
  </div>
);

interface PasswordConfirmFieldProps {
  value: string;
  password: string;
  onChange: (v: string) => void;
  showPwd: boolean;
  onToggleShow: () => void;
}
const PasswordConfirmField: React.FC<PasswordConfirmFieldProps> = ({ value, password, onChange, showPwd, onToggleShow }) => (
  <div>
    <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5">Повторите пароль</label>
    <div className="relative">
      <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-600 pointer-events-none" />
      <input
        type={showPwd ? 'text' : 'password'}
        value={value}
        onChange={e => onChange(e.target.value)}
        autoComplete="new-password"
        className={`w-full bg-zinc-900 border rounded-xl pl-9 pr-9 py-2.5 text-sm text-white placeholder-zinc-600 focus:outline-none transition-colors ${
          value && password !== value ? 'border-red-500/50 focus:border-red-500' : 'border-zinc-800 focus:border-amber-500'
        }`}
        placeholder="••••••••"
      />
      <button
        type="button"
        onClick={onToggleShow}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-600 hover:text-zinc-400"
      >
        {showPwd ? <EyeOff size={14} /> : <Eye size={14} />}
      </button>
    </div>
    {value && password !== value && (
      <p className="text-[10px] text-red-400 mt-1 ml-1">Пароли не совпадают</p>
    )}
  </div>
);

// ─── Main Component ─────────────────────────────────────────────────────────────
const AdsAuth: React.FC = () => {
  const navigate = useNavigate();

  const [screen,    setScreen]   = useState<Screen>('login');
  const [email,     setEmail]    = useState('');
  const [password,  setPassword] = useState('');
  const [password2, setPassword2] = useState('');
  const [code,      setCode]     = useState('');
  const [showPwd,   setShowPwd]  = useState(false);
  const [loading,   setLoading]  = useState(false);
  const [error,     setError]    = useState('');
  const [success,   setSuccess]  = useState('');
  const [cooldown,  setCooldown] = useState(0);

  const err   = (msg: string) => { setError(msg); setLoading(false); };
  const ok    = (msg: string) => { setSuccess(msg); setLoading(false); };
  const reset = () => { setError(''); setSuccess(''); };

  const startCooldown = (sec = 60) => {
    setCooldown(sec);
    const t = setInterval(() => {
      setCooldown(prev => { if (prev <= 1) { clearInterval(t); return 0; } return prev - 1; });
    }, 1000);
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password) return err('Заполните все поля');
    setLoading(true); reset();
    try {
      const data = await post('/api/ads/auth/login', { email: email.trim().toLowerCase(), password });
      localStorage.setItem('ads_agent_token', data.token);
      localStorage.setItem('ads_agent', JSON.stringify({ ...data.agent, password_hash: undefined }));
      navigate('/ads');
    } catch (e: any) { err(e.message); }
  };

  const handleRegisterStep1 = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password || !password2) return err('Заполните все поля');
    if (password.length < 6) return err('Пароль минимум 6 символов');
    if (password !== password2) return err('Пароли не совпадают');
    setLoading(true); reset();
    try {
      await post('/api/ads/auth/send-code', { email: email.trim().toLowerCase(), type: 'register' });
      startCooldown(60);
      setScreen('register_code');
      ok('Код отправлен на почту. Проверьте «Входящие» и «Спам».');
    } catch (e: any) { err(e.message); }
  };

  const handleRegisterStep2 = async (e: React.FormEvent) => {
    e.preventDefault();
    if (code.length < 6) return err('Введите 6-значный код из письма');
    setLoading(true); reset();
    try {
      const data = await post('/api/ads/auth/register-verify', {
        email: email.trim().toLowerCase(), password, code
      });
      localStorage.setItem('ads_agent_token', data.token);
      localStorage.setItem('ads_agent', JSON.stringify({ ...data.agent, password_hash: undefined }));
      navigate('/ads');
    } catch (e: any) { err(e.message); }
  };

  const handleForgotStep1 = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return err('Введите email');
    setLoading(true); reset();
    try {
      await post('/api/ads/auth/send-code', { email: email.trim().toLowerCase(), type: 'reset' });
      startCooldown(60);
      setScreen('reset_code');
      ok('Код сброса отправлен на почту.');
    } catch (e: any) { err(e.message); }
  };

  const handleResetStep2 = async (e: React.FormEvent) => {
    e.preventDefault();
    if (code.length < 6) return err('Введите 6-значный код');
    if (!password || password.length < 6) return err('Пароль минимум 6 символов');
    if (password !== password2) return err('Пароли не совпадают');
    setLoading(true); reset();
    try {
      await post('/api/ads/auth/reset-password', {
        email: email.trim().toLowerCase(), code, newPassword: password
      });
      ok('Пароль успешно изменён!');
      setTimeout(() => {
        setScreen('login'); setCode(''); setPassword(''); setPassword2(''); setSuccess('');
      }, 2000);
    } catch (e: any) { err(e.message); }
  };

  const resendCode = async () => {
    if (cooldown > 0) return;
    setLoading(true); reset();
    const type = screen === 'register_code' ? 'register' : 'reset';
    try {
      await post('/api/ads/auth/send-code', { email: email.trim().toLowerCase(), type });
      startCooldown(60);
      ok('Код отправлен повторно.');
    } catch (e: any) { err(e.message); }
    setLoading(false);
  };

  const Feedback = () => (<>
    {error   && <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-xs"><AlertTriangle size={13} className="shrink-0" />{error}</div>}
    {success && <div className="flex items-center gap-2 p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-400 text-xs"><CheckCircle size={13} className="shrink-0" />{success}</div>}
  </>);

  const SubmitBtn: React.FC<{ label: string }> = ({ label }) => (
    <button type="submit" disabled={loading}
      className="w-full py-3 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 disabled:from-zinc-800 disabled:to-zinc-800 disabled:text-zinc-600 rounded-xl text-sm font-black text-black uppercase tracking-widest transition-all flex items-center justify-center gap-2 mt-1">
      {loading && <Loader2 size={15} className="animate-spin" />}
      {loading ? 'Загрузка...' : label}
    </button>
  );

  const togglePwd = () => setShowPwd(p => !p);

  return (
    <div className="min-h-screen bg-[#060608] flex flex-col items-center justify-center p-6"
      style={{ backgroundImage: 'radial-gradient(ellipse 80% 40% at 50% 0%, rgba(234,179,8,0.07), transparent)' }}>
      <div className="w-full max-w-sm">

        {/* Back */}
        <button onClick={() => {
          if (['register_code', 'reset_code'].includes(screen)) {
            setScreen(screen === 'register_code' ? 'register' : 'forgot');
            setCode(''); reset();
          } else if (['register', 'forgot'].includes(screen)) {
            setScreen('login'); reset();
          } else {
            navigate('/');
          }
        }} className="flex items-center gap-1.5 text-zinc-600 hover:text-zinc-400 text-xs font-bold uppercase tracking-widest mb-8 transition-colors">
          <ArrowLeft size={14} /> {['login', 'register'].includes(screen) ? 'Назад' : 'Вернуться'}
        </button>

        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-14 h-14 bg-gradient-to-br from-amber-500 to-orange-600 rounded-2xl flex items-center justify-center mb-3 shadow-lg shadow-amber-500/25">
            <Megaphone size={24} className="text-white" />
          </div>
          <h1 className="text-xl font-black text-white tracking-tight">BotEngine Ads</h1>
          <p className="text-zinc-500 text-xs mt-1 text-center">Рекламная платформа для Telegram-ботов</p>
        </div>

        {/* ── LOGIN ─────────────────────────────────────────────────────────── */}
        {screen === 'login' && (<>
          <div className="flex gap-1 p-1 bg-zinc-900 border border-zinc-800 rounded-2xl mb-6">
            <button type="button" onClick={() => { setScreen('login'); reset(); }}
              className="flex-1 py-2 rounded-xl text-[11px] font-black uppercase tracking-widest transition-all bg-amber-500 text-black">Войти</button>
            <button type="button" onClick={() => { setScreen('register'); reset(); }}
              className="flex-1 py-2 rounded-xl text-[11px] font-black uppercase tracking-widest transition-all text-zinc-500 hover:text-zinc-300">Регистрация</button>
          </div>
          <form onSubmit={handleLogin} className="space-y-3">
            <EmailField value={email} onChange={setEmail} />
            <PasswordField
              value={password} onChange={setPassword}
              showPwd={showPwd} onToggleShow={togglePwd}
              autoComplete="current-password"
            />
            <Feedback />
            <SubmitBtn label="Войти" />
            <button type="button" onClick={() => { setScreen('forgot'); reset(); setCode(''); setPassword(''); setPassword2(''); }}
              className="w-full text-center text-xs text-zinc-600 hover:text-amber-400 transition-colors mt-1">
              Забыли пароль?
            </button>
          </form>
        </>)}

        {/* ── REGISTER step 1 ─────────────────────────────────────────────── */}
        {screen === 'register' && (<>
          <div className="flex gap-1 p-1 bg-zinc-900 border border-zinc-800 rounded-2xl mb-6">
            <button type="button" onClick={() => { setScreen('login'); reset(); }}
              className="flex-1 py-2 rounded-xl text-[11px] font-black uppercase tracking-widest transition-all text-zinc-500 hover:text-zinc-300">Войти</button>
            <button type="button" className="flex-1 py-2 rounded-xl text-[11px] font-black uppercase tracking-widest transition-all bg-amber-500 text-black">Регистрация</button>
          </div>
          <form onSubmit={handleRegisterStep1} className="space-y-3">
            <EmailField value={email} onChange={setEmail} />
            <PasswordField
              label="Пароль" placeholder="Минимум 6 символов"
              value={password} onChange={setPassword}
              showPwd={showPwd} onToggleShow={togglePwd}
              autoComplete="new-password"
            />
            <PasswordConfirmField
              value={password2} password={password}
              onChange={setPassword2}
              showPwd={showPwd} onToggleShow={togglePwd}
            />
            <Feedback />
            <SubmitBtn label="Получить код по email" />
          </form>
        </>)}

        {/* ── REGISTER step 2 — verify code ───────────────────────────────── */}
        {screen === 'register_code' && (
          <form onSubmit={handleRegisterStep2} className="space-y-4">
            <div className="text-center mb-2">
              <KeyRound size={28} className="text-amber-400 mx-auto mb-2" />
              <h2 className="text-sm font-black text-white">Подтверждение email</h2>
              <p className="text-xs text-zinc-500 mt-1">Код отправлен на <span className="text-amber-400 font-bold">{email}</span></p>
            </div>
            <div>
              <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5">6-значный код</label>
              <EmailCodeInput value={code} onChange={setCode} disabled={loading} />
            </div>
            <Feedback />
            <SubmitBtn label="Создать аккаунт" />
            <button type="button" onClick={resendCode} disabled={cooldown > 0 || loading}
              className="w-full flex items-center justify-center gap-1.5 text-xs text-zinc-600 hover:text-amber-400 disabled:text-zinc-700 transition-colors">
              <RefreshCw size={11} />
              {cooldown > 0 ? `Повторная отправка через ${cooldown}с` : 'Отправить код повторно'}
            </button>
          </form>
        )}

        {/* ── FORGOT step 1 ───────────────────────────────────────────────── */}
        {screen === 'forgot' && (
          <form onSubmit={handleForgotStep1} className="space-y-3">
            <div className="text-center mb-4">
              <h2 className="text-sm font-black text-white">Сброс пароля</h2>
              <p className="text-xs text-zinc-500 mt-1">Введите email для получения кода</p>
            </div>
            <EmailField value={email} onChange={setEmail} />
            <Feedback />
            <SubmitBtn label="Отправить код" />
          </form>
        )}

        {/* ── FORGOT step 2 — reset code ──────────────────────────────────── */}
        {screen === 'reset_code' && (
          <form onSubmit={handleResetStep2} className="space-y-3">
            <div className="text-center mb-2">
              <KeyRound size={28} className="text-amber-400 mx-auto mb-2" />
              <h2 className="text-sm font-black text-white">Новый пароль</h2>
              <p className="text-xs text-zinc-500 mt-1">Код отправлен на <span className="text-amber-400 font-bold">{email}</span></p>
            </div>
            <div>
              <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5">6-значный код из письма</label>
              <EmailCodeInput value={code} onChange={setCode} disabled={loading} />
            </div>
            <PasswordField
              label="Новый пароль" placeholder="Минимум 6 символов"
              value={password} onChange={setPassword}
              showPwd={showPwd} onToggleShow={togglePwd}
              autoComplete="new-password"
            />
            <PasswordConfirmField
              value={password2} password={password}
              onChange={setPassword2}
              showPwd={showPwd} onToggleShow={togglePwd}
            />
            <Feedback />
            <SubmitBtn label="Изменить пароль" />
            <button type="button" onClick={resendCode} disabled={cooldown > 0 || loading}
              className="w-full flex items-center justify-center gap-1.5 text-xs text-zinc-600 hover:text-amber-400 disabled:text-zinc-700 transition-colors">
              <RefreshCw size={11} />
              {cooldown > 0 ? `Повторная отправка через ${cooldown}с` : 'Отправить код повторно'}
            </button>
          </form>
        )}

        {/* Info block */}
        {['login', 'register'].includes(screen) && (
          <div className="mt-8 p-4 bg-zinc-900/60 border border-zinc-800 rounded-2xl">
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2 font-bold">Как работает</div>
            <ol className="space-y-1.5 text-xs text-zinc-500">
              {[
                'Создайте рекламный пост — текст до 250 символов',
                'Пост проходит модерацию (до 24 часов)',
                'Пополните баланс через ЮКассу и купите показы',
                'Реклама показывается в free-ботах · 0.2 ₽ / показ',
              ].map((s, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="text-amber-500 font-bold shrink-0">{i + 1}.</span>{s}
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </div>
  );
};

export default AdsAuth;
