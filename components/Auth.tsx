
import React, { useState, useEffect } from 'react';
import { User } from '../types';
import { api } from '../services/apiService';

interface AuthProps {
  onLogin: (user: User) => void;
}

const Auth: React.FC<AuthProps> = ({ onLogin }) => {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [username, setUsername] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [serverStatus, setServerStatus] = useState<'checking' | 'online' | 'offline'>('checking');

  const checkServer = async () => {
    setServerStatus('checking');
    const isOnline = await api.checkConnection();
    setServerStatus(isOnline ? 'online' : 'offline');
    if (!isOnline) {
      setError('Сервер недоступен. Проверьте порт 8000 и Firewall.');
    } else {
      setError('');
    }
  };

  useEffect(() => {
    checkServer();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (serverStatus !== 'online') {
      setError('Сначала восстановите связь с сервером (порт 8000).');
      return;
    }
    setError('');
    setLoading(true);

    try {
      if (isLogin) {
        const user = await api.login(email, password);
        if (user) onLogin(user);
        else setError('Неверный логин или пароль');
      } else {
        const newUser: User = {
          id: 'u_' + Math.random().toString(36).substr(2, 5),
          username: username || email.split('@')[0],
          email,
          password,
          subscription: 'FREE',
          balance: 0,
          botsCreated: 0
        };
        const user = await api.register(newUser);
        if (user) onLogin(user);
        else setError('Ошибка регистрации');
      }
    } catch (err: any) {
      setError(err.message || 'Ошибка сети (Timeout)');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#050505] px-4">
      <div className="w-full max-w-md space-y-6 bg-[#111] p-10 rounded-[2.5rem] border border-zinc-800 shadow-2xl">
        <div className="text-center">
          <div className="mx-auto w-12 h-12 bg-blue-600 rounded-xl flex items-center justify-center mb-4">
            <span className="font-black text-white text-xl">BE</span>
          </div>
          <h2 className="text-2xl font-black text-white">{isLogin ? 'Вход' : 'Регистрация'}</h2>
          
          <div className="mt-4 flex items-center justify-center gap-2">
            <div className={`w-2 h-2 rounded-full ${serverStatus === 'online' ? 'bg-green-500' : serverStatus === 'offline' ? 'bg-red-500' : 'bg-zinc-600 animate-pulse'}`}></div>
            <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
              API Status: {serverStatus}
            </span>
            {serverStatus === 'offline' && (
              <button onClick={checkServer} className="text-[10px] text-blue-500 hover:underline ml-2">Обновить</button>
            )}
          </div>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 p-4 rounded-2xl">
            <p className="text-red-500 text-[11px] text-center font-bold leading-relaxed">
              {error}
              {serverStatus === 'offline' && (
                <span className="block mt-2 text-zinc-400 font-mono text-[9px] bg-black p-2 rounded">
                  Выполните в терминале сервера:<br/>
                  sudo ufw allow 8000/tcp
                </span>
              )}
            </p>
          </div>
        )}

        <form className="space-y-4" onSubmit={handleSubmit}>
          {!isLogin && (
            <input type="text" required className="w-full bg-black border border-zinc-800 rounded-2xl p-4 text-sm text-white outline-none focus:ring-1 focus:ring-blue-500" placeholder="Username" value={username} onChange={e => setUsername(e.target.value)} />
          )}
          <input type="email" required className="w-full bg-black border border-zinc-800 rounded-2xl p-4 text-sm text-white outline-none focus:ring-1 focus:ring-blue-500" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} />
          <input type="password" required className="w-full bg-black border border-zinc-800 rounded-2xl p-4 text-sm text-white outline-none focus:ring-1 focus:ring-blue-500" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} />
          
          <button type="submit" disabled={loading} className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-black py-4 rounded-2xl transition-all uppercase tracking-widest text-xs">
            {loading ? 'Загрузка...' : (isLogin ? 'Войти' : 'Создать аккаунт')}
          </button>
        </form>

        <button onClick={() => { setIsLogin(!isLogin); setError(''); }} className="w-full text-[10px] text-zinc-600 hover:text-blue-500 font-bold uppercase tracking-widest">
          {isLogin ? "Нет аккаунта? Регистрация" : 'Уже есть аккаунт? Вход'}
        </button>
      </div>
    </div>
  );
};

export default Auth;
