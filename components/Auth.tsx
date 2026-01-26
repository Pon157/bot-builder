
import React, { useState } from 'react';
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (isLogin) {
        const user = await api.login(email, password);
        if (user) {
          onLogin(user);
        } else {
          setError('Неверный email или пароль');
        }
      } else {
        const newUser: User = {
          id: 'user_' + Math.random().toString(36).substr(2, 9),
          username: username || email.split('@')[0],
          email: email,
          password: password,
          subscription: 'FREE',
          balance: 0,
          botsCreated: 0
        };
        const user = await api.register(newUser);
        if (user) {
          onLogin(user);
        } else {
          setError('Ошибка при создании аккаунта');
        }
      }
    } catch (err: any) {
      console.error("Auth catch:", err);
      if (err.name === 'AbortError') {
        setError('Сервер не отвечает (Таймаут). Проверьте порт 8000 на сервере.');
      } else if (err.message.includes('fetch')) {
        setError('Не удалось подключиться к API. Убедитесь, что сервер запущен.');
      } else {
        setError(err.message || 'Произошла ошибка при авторизации');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#050505] px-4 font-sans">
      <div className="w-full max-w-md space-y-8 bg-[#111] p-10 rounded-[2.5rem] border border-zinc-800 shadow-2xl">
        <div className="text-center">
          <div className="mx-auto w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center mb-6 shadow-xl shadow-blue-600/20">
            <span className="font-black text-white text-2xl">BE</span>
          </div>
          <h2 className="text-3xl font-black text-white mb-2">{isLogin ? 'Вход' : 'Регистрация'}</h2>
          <p className="text-[10px] text-zinc-500 uppercase tracking-[0.2em] font-bold">Cloud Bot Infrastructure</p>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 p-4 rounded-2xl text-red-500 text-xs text-center font-bold">
            {error}
          </div>
        )}

        <form className="mt-8 space-y-4" onSubmit={handleSubmit}>
          {!isLogin && (
            <input 
              type="text" required 
              className="w-full bg-black border border-zinc-800 rounded-2xl p-4 text-sm text-white focus:ring-1 focus:ring-blue-500 outline-none transition-all" 
              placeholder="Ваш никнейм" 
              value={username} onChange={(e) => setUsername(e.target.value)} 
            />
          )}
          <input 
            type="email" required 
            className="w-full bg-black border border-zinc-800 rounded-2xl p-4 text-sm text-white focus:ring-1 focus:ring-blue-500 outline-none transition-all" 
            placeholder="Email" 
            value={email} onChange={(e) => setEmail(e.target.value)} 
          />
          <input 
            type="password" required 
            className="w-full bg-black border border-zinc-800 rounded-2xl p-4 text-sm text-white focus:ring-1 focus:ring-blue-500 outline-none transition-all" 
            placeholder="Пароль" 
            value={password} onChange={(e) => setPassword(e.target.value)} 
          />
          <button 
            type="submit" 
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-black py-4 rounded-2xl transition-all shadow-lg shadow-blue-600/30 uppercase tracking-widest text-sm mt-4"
          >
            {loading ? 'Загрузка...' : (isLogin ? 'Авторизоваться' : 'Создать аккаунт')}
          </button>
        </form>

        <div className="text-center">
          <button onClick={() => { setIsLogin(!isLogin); setError(''); }} className="text-[10px] text-zinc-600 hover:text-blue-500 font-bold uppercase tracking-widest transition-all">
            {isLogin ? "Нет аккаунта? Зарегистрироваться" : 'Уже есть аккаунт? Войти'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default Auth;
