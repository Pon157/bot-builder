import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Megaphone, Mail, Lock, Eye, EyeOff, Loader2, AlertTriangle, ArrowLeft } from 'lucide-react';

const AdsAuth: React.FC = () => {
  const navigate = useNavigate();
  const [mode, setMode]         = useState<'login' | 'register'>('login');
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd]   = useState(false);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setError('');
    const endpoint = mode === 'login' ? '/api/ads/auth/login' : '/api/ads/auth/register';
    try {
      const r = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase(), password })
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || 'Ошибка авторизации');
      localStorage.setItem('ads_agent_token', data.token);
      localStorage.setItem('ads_agent', JSON.stringify({ ...data.agent, password_hash: undefined }));
      navigate('/ads');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#060608] flex flex-col items-center justify-center p-6"
      style={{
        backgroundImage: 'radial-gradient(ellipse 80% 40% at 50% 0%, rgba(234,179,8,0.07), transparent)',
      }}>

      <div className="w-full max-w-sm">
        {/* Back */}
        <button onClick={() => navigate('/')} className="flex items-center gap-1.5 text-zinc-600 hover:text-zinc-400 text-xs font-bold uppercase tracking-widest mb-8 transition-colors">
          <ArrowLeft size={14} /> Назад
        </button>

        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-14 h-14 bg-gradient-to-br from-amber-500 to-orange-600 rounded-2xl flex items-center justify-center mb-3 shadow-lg shadow-amber-500/25">
            <Megaphone size={24} className="text-white" />
          </div>
          <h1 className="text-xl font-black text-white tracking-tight">BotEngine Ads</h1>
          <p className="text-zinc-500 text-xs mt-1 text-center">
            Рекламная платформа для продвижения в Telegram-ботах
          </p>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 p-1 bg-zinc-900 border border-zinc-800 rounded-2xl mb-6">
          {(['login', 'register'] as const).map(m => (
            <button
              key={m}
              onClick={() => { setMode(m); setError(''); }}
              className={`flex-1 py-2 rounded-xl text-[11px] font-black uppercase tracking-widest transition-all
                ${mode === m ? 'bg-amber-500 text-black' : 'text-zinc-500 hover:text-zinc-300'}`}
            >
              {m === 'login' ? 'Войти' : 'Регистрация'}
            </button>
          ))}
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5">Email</label>
            <div className="relative">
              <Mail size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-600 pointer-events-none" />
              <input
                type="email" value={email} onChange={e => setEmail(e.target.value)}
                required autoFocus
                className="w-full bg-zinc-900 border border-zinc-800 rounded-xl pl-9 pr-3 py-2.5 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-amber-500 transition-colors"
                placeholder="agency@company.com"
              />
            </div>
          </div>

          <div>
            <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5">Пароль</label>
            <div className="relative">
              <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-600 pointer-events-none" />
              <input
                type={showPwd ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)}
                required minLength={6}
                className="w-full bg-zinc-900 border border-zinc-800 rounded-xl pl-9 pr-9 py-2.5 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-amber-500 transition-colors"
                placeholder={mode === 'register' ? 'Минимум 6 символов' : '••••••••'}
              />
              <button type="button" onClick={() => setShowPwd(!showPwd)} className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-600 hover:text-zinc-400 transition-colors">
                {showPwd ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>

          {error && (
            <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-xs">
              <AlertTriangle size={13} className="shrink-0" /> {error}
            </div>
          )}

          <button type="submit" disabled={loading}
            className="w-full py-3 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 disabled:from-zinc-800 disabled:to-zinc-800 disabled:text-zinc-600 rounded-xl text-sm font-black text-black uppercase tracking-widest transition-all flex items-center justify-center gap-2 mt-2">
            {loading && <Loader2 size={15} className="animate-spin" />}
            {loading ? 'Загрузка...' : mode === 'login' ? 'Войти' : 'Создать аккаунт'}
          </button>
        </form>

        {/* Info */}
        <div className="mt-8 p-4 bg-zinc-900/60 border border-zinc-800 rounded-2xl">
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2 font-bold">Как работает</div>
          <ol className="space-y-1.5 text-xs text-zinc-500">
            <li className="flex items-start gap-2">
              <span className="text-amber-500 font-bold shrink-0">1.</span>
              Создайте рекламный пост — текст до 250 символов
            </li>
            <li className="flex items-start gap-2">
              <span className="text-amber-500 font-bold shrink-0">2.</span>
              Пост проходит модерацию (до 24 часов)
            </li>
            <li className="flex items-start gap-2">
              <span className="text-amber-500 font-bold shrink-0">3.</span>
              Пополните баланс через Юкасса и купите показы
            </li>
            <li className="flex items-start gap-2">
              <span className="text-amber-500 font-bold shrink-0">4.</span>
              Реклама показывается в free-ботах · <b className="text-amber-400">0.2 ₽ / показ</b>
            </li>
          </ol>
        </div>
      </div>
    </div>
  );
};

export default AdsAuth;
