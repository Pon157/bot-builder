import React, { useState, useEffect } from 'react';
import { User } from '../types';
import { api } from '../services/apiService';
import { Mail, Lock, User as UserIcon, ShieldCheck, ArrowLeft, RefreshCw, ExternalLink } from 'lucide-react';

interface AuthProps {
  onLogin: (user: User) => void;
}

type AuthMode = 'login' | 'register' | 'verify' | 'forgot' | 'reset';

const Auth: React.FC<AuthProps> = ({ onLogin }) => {
  const [mode, setMode] = useState<AuthMode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [username, setUsername] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [serverStatus, setServerStatus] = useState<'checking' | 'online' | 'offline'>('checking');

  // Ссылка на документы в твоем репозитории
  const GITHUB_RAW_URL = "https://raw.githubusercontent.com/Pon157/bot-builder/main";

  const checkServer = async () => {
    setServerStatus('checking');
    const isOnline = await api.checkConnection();
    setServerStatus(isOnline ? 'online' : 'offline');
  };

  useEffect(() => { checkServer(); }, []);

  const handleRequestVerification = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const result = await api.requestVerification(email);
      if (result === true) {
        setMode('verify');
      } else {
        setError(typeof result === 'string' ? result : 'Ошибка отправки кода');
      }
    } catch (err: any) {
      setError(err.message || 'Нет связи с сервером');
    }
    setLoading(false);
  };

  const handleVerifyAndRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
        const user = await api.verifyAndRegister({ email, code, password, username });
        if (user) {
            onLogin(user);
        }
    } catch (err: any) {
        setError(err.message || 'Ошибка регистрации');
    }
    setLoading(false);
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
        const user = await api.login(email, password);
        if (user) onLogin(user);
    } catch (err: any) {
        setError(err.message || 'Ошибка входа');
    }
    setLoading(false);
  };

  const handleForgotPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
        const result = await api.forgotPassword(email);
        if (result === true) setMode('reset');
        else setError(typeof result === 'string' ? result : 'Ошибка');
    } catch (err: any) {
        setError(err.message || 'Ошибка сервера');
    }
    setLoading(false);
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
        const success = await api.resetPassword({ email, code, newPassword: password });
        if (success) {
            alert('Пароль успешно изменен!');
            setMode('login');
        }
    } catch (err: any) {
        setError(err.message || 'Неверный код или ошибка сервера');
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#050505] px-4 font-sans text-zinc-300">
      <div className="w-full max-w-md space-y-6 bg-[#111] p-10 rounded-[2.5rem] border border-zinc-800 shadow-2xl relative overflow-hidden">
        <div className="absolute -top-24 -right-24 w-48 h-48 bg-blue-600/10 blur-[100px] rounded-full"></div>
        
        <div className="text-center relative z-10">
          <div className="mx-auto w-14 h-14 bg-blue-600 rounded-2xl flex items-center justify-center mb-6 shadow-lg shadow-blue-600/20">
            <ShieldCheck className="text-white w-8 h-8" />
          </div>
          <h2 className="text-3xl font-black text-white tracking-tight">
            {mode === 'login' && 'Вход'}
            {mode === 'register' && 'Регистрация'}
            {mode === 'verify' && 'Подтверждение'}
            {mode === 'forgot' && 'Сброс пароля'}
            {mode === 'reset' && 'Новый пароль'}
          </h2>
          
          <div className="mt-4 flex items-center justify-center gap-2">
            <div className={`w-1.5 h-1.5 rounded-full ${serverStatus === 'online' ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.5)]' : 'bg-red-500 animate-pulse'}`}></div>
            <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
              API Server: {serverStatus}
            </span>
          </div>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 p-4 rounded-2xl animate-in fade-in slide-in-from-top-2">
            <p className="text-red-500 text-[11px] text-center font-bold">{error}</p>
          </div>
        )}

        <div className="relative z-10">
          {mode === 'login' && (
            <form className="space-y-4" onSubmit={handleLogin}>
              <div className="relative">
                <Mail className="absolute left-4 top-4 w-4 h-4 text-zinc-600" />
                <input type="email" required className="w-full bg-black border border-zinc-800 rounded-2xl p-4 pl-12 text-sm text-white focus:ring-1 focus:ring-blue-500 outline-none transition-all" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} />
              </div>
              <div className="relative">
                <Lock className="absolute left-4 top-4 w-4 h-4 text-zinc-600" />
                <input type="password" required className="w-full bg-black border border-zinc-800 rounded-2xl p-4 pl-12 text-sm text-white focus:ring-1 focus:ring-blue-500 outline-none transition-all" placeholder="Пароль" value={password} onChange={e => setPassword(e.target.value)} />
              </div>
              <button type="submit" disabled={loading} className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-black py-4 rounded-2xl transition-all uppercase tracking-widest text-xs shadow-lg shadow-blue-600/20">
                {loading ? 'Вход...' : 'Войти'}
              </button>
              <div className="flex justify-between items-center px-2">
                <button type="button" onClick={() => setMode('forgot')} className="text-[10px] text-zinc-600 hover:text-blue-500 font-bold uppercase tracking-widest transition-colors">Забыли пароль?</button>
                <button type="button" onClick={() => setMode('register')} className="text-[10px] text-blue-500 hover:underline font-bold uppercase tracking-widest">Создать аккаунт</button>
              </div>
            </form>
          )}

          {mode === 'register' && (
            <form className="space-y-4" onSubmit={handleRequestVerification}>
              <div className="relative">
                <UserIcon className="absolute left-4 top-4 w-4 h-4 text-zinc-600" />
                <input type="text" required className="w-full bg-black border border-zinc-800 rounded-2xl p-4 pl-12 text-sm text-white focus:ring-1 focus:ring-blue-500 outline-none transition-all" placeholder="Имя пользователя" value={username} onChange={e => setUsername(e.target.value)} />
              </div>
              <div className="relative">
                <Mail className="absolute left-4 top-4 w-4 h-4 text-zinc-600" />
                <input type="email" required className="w-full bg-black border border-zinc-800 rounded-2xl p-4 pl-12 text-sm text-white focus:ring-1 focus:ring-blue-500 outline-none transition-all" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} />
              </div>
              <div className="relative">
                <Lock className="absolute left-4 top-4 w-4 h-4 text-zinc-600" />
                <input type="password" required className="w-full bg-black border border-zinc-800 rounded-2xl p-4 pl-12 text-sm text-white focus:ring-1 focus:ring-blue-500 outline-none transition-all" placeholder="Придумайте пароль" value={password} onChange={e => setPassword(e.target.value)} />
              </div>
              <button type="submit" disabled={loading} className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-black py-4 rounded-2xl transition-all uppercase tracking-widest text-xs">
                {loading ? 'Отправка...' : 'Отправить код'}
              </button>
              <button type="button" onClick={() => setMode('login')} className="w-full text-[10px] text-zinc-600 hover:text-white font-bold uppercase tracking-widest flex items-center justify-center gap-2">
                <ArrowLeft className="w-3 h-3" /> Назад к входу
              </button>
            </form>
          )}

          {mode === 'verify' && (
            <form className="space-y-4 text-center" onSubmit={handleVerifyAndRegister}>
              <p className="text-zinc-500 text-xs mb-4">Мы отправили код на <b>{email.toLowerCase()}</b>. Введите его ниже.</p>
              <input 
                type="text" 
                required 
                maxLength={6} 
                className="w-full bg-black border border-blue-500/50 rounded-2xl p-6 text-2xl font-black text-center text-white tracking-[0.5em] focus:ring-2 focus:ring-blue-500 outline-none" 
                placeholder="000000" 
                value={code} 
                onChange={e => setCode(e.target.value)} 
              />
              <button type="submit" disabled={loading} className="w-full bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white font-black py-4 rounded-2xl transition-all uppercase tracking-widest text-xs">
                {loading ? 'Проверка...' : 'Завершить регистрацию'}
              </button>
              <button type="button" onClick={() => setMode('register')} className="text-[10px] text-zinc-600 hover:text-blue-500 font-bold uppercase tracking-widest">Изменить Email</button>
            </form>
          )}

          {mode === 'forgot' && (
            <form className="space-y-4" onSubmit={handleForgotPassword}>
              <p className="text-zinc-500 text-xs text-center mb-4">Введите Email для восстановления доступа.</p>
              <div className="relative">
                <Mail className="absolute left-4 top-4 w-4 h-4 text-zinc-600" />
                <input type="email" required className="w-full bg-black border border-zinc-800 rounded-2xl p-4 pl-12 text-sm text-white focus:ring-1 focus:ring-blue-500 outline-none transition-all" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} />
              </div>
              <button type="submit" disabled={loading} className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-black py-4 rounded-2xl transition-all uppercase tracking-widest text-xs">
                {loading ? 'Поиск...' : 'Сбросить пароль'}
              </button>
              <button type="button" onClick={() => setMode('login')} className="w-full text-[10px] text-zinc-600 hover:text-white font-bold uppercase tracking-widest flex items-center justify-center gap-2">
                <ArrowLeft className="w-3 h-3" /> Назад
              </button>
            </form>
          )}

          {mode === 'reset' && (
            <form className="space-y-4" onSubmit={handleResetPassword}>
              <p className="text-zinc-500 text-xs text-center mb-4">Код сброса отправлен на почту.</p>
              <input 
                type="text" 
                required 
                maxLength={6} 
                className="w-full bg-black border border-red-500/30 rounded-2xl p-4 text-xl font-black text-center text-white tracking-[0.3em] outline-none" 
                placeholder="Код из письма" 
                value={code} 
                onChange={e => setCode(e.target.value)} 
              />
              <div className="relative">
                <Lock className="absolute left-4 top-4 w-4 h-4 text-zinc-600" />
                <input type="password" required className="w-full bg-black border border-zinc-800 rounded-2xl p-4 pl-12 text-sm text-white focus:ring-1 focus:ring-blue-500 outline-none" placeholder="Новый пароль" value={password} onChange={e => setPassword(e.target.value)} />
              </div>
              <button type="submit" disabled={loading} className="w-full bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white font-black py-4 rounded-2xl transition-all uppercase tracking-widest text-xs">
                {loading ? 'Обновление...' : 'Сменить пароль'}
              </button>
            </form>
          )}
        </div>

        {/* НИЖНИЙ БЛОК: СТАТУС И ЮРИДИЧЕСКАЯ ИНФОРМАЦИЯ */}
        <div className="pt-6 border-t border-zinc-800/50 space-y-5">
          <div className="flex justify-center">
             <button onClick={checkServer} className="flex items-center gap-2 text-[9px] font-black uppercase tracking-[0.2em] text-zinc-700 hover:text-zinc-400 transition-colors">
                <RefreshCw className={`w-3 h-3 ${serverStatus === 'checking' ? 'animate-spin' : ''}`} /> Обновить статус
             </button>
          </div>

          <div className="flex flex-col items-center gap-3">
            <div className="flex items-center gap-4">
              <a 
                href={`${GITHUB_RAW_URL}/user_agreement.pdf`} 
                target="_blank" 
                rel="noreferrer"
                className="text-[10px] font-bold text-zinc-500 hover:text-blue-500 transition-colors flex items-center gap-1"
              >
                Соглашение
              </a>
              <span className="w-1 h-1 bg-zinc-800 rounded-full"></span>
              <a 
                href={`${GITHUB_RAW_URL}/privacy_policy.pdf`} 
                target="_blank" 
                rel="noreferrer"
                className="text-[10px] font-bold text-zinc-500 hover:text-blue-500 transition-colors flex items-center gap-1"
              >
                Конфиденциальность
              </a>
            </div>
            <p className="text-[9px] text-zinc-600 text-center leading-relaxed max-w-[240px]">
              Продолжая работу, вы принимаете условия использования сервиса и обработки данных.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Auth;
              <div className="relative">
                <Lock className="absolute left-4 top-4 w-4 h-4 text-zinc-600" />
                <input type="password" required className="w-full bg-black border border-zinc-800 rounded-2xl p-4 pl-12 text-sm text-white focus:ring-1 focus:ring-blue-500 outline-none" placeholder="Новый пароль" value={password} onChange={e => setPassword(e.target.value)} />
              </div>
              <button type="submit" disabled={loading} className="w-full bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white font-black py-4 rounded-2xl transition-all uppercase tracking-widest text-xs">
                {loading ? 'Обновление...' : 'Сменить пароль'}
              </button>
            </form>
          )}
        </div>

        <div className="pt-6 border-t border-zinc-800/50 flex justify-center">
             <button onClick={checkServer} className="flex items-center gap-2 text-[9px] font-black uppercase tracking-[0.2em] text-zinc-700 hover:text-zinc-400 transition-colors">
                <RefreshCw className={`w-3 h-3 ${serverStatus === 'checking' ? 'animate-spin' : ''}`} /> Обновить статус
             </button>
        </div>
      </div>
    </div>
  );
};

export default Auth;
