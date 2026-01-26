
import React, { useState } from 'react';
import { User } from '../types';

interface AuthProps {
  onLogin: (user: User) => void;
}

const Auth: React.FC<AuthProps> = ({ onLogin }) => {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [username, setUsername] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    const usersStr = localStorage.getItem('botengine_users_db') || '[]';
    const users: User[] = JSON.parse(usersStr);

    if (isLogin) {
      const foundUser = users.find(u => u.email === email && u.password === password);
      if (foundUser) {
        onLogin(foundUser);
      } else {
        setError('Неверный email или пароль');
      }
    } else {
      if (users.find(u => u.email === email)) {
        setError('Пользователь с таким email уже существует');
        return;
      }
      
      const newUser: User = {
        id: Math.random().toString(36).substr(2, 9),
        username: username || email.split('@')[0],
        email: email,
        password: password,
        subscription: 'FREE',
        balance: 0,
        botsCreated: 0
      };
      
      users.push(newUser);
      localStorage.setItem('botengine_users_db', JSON.stringify(users));
      onLogin(newUser);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0a0a] px-4">
      <div className="w-full max-w-md space-y-8 bg-[#121212] p-10 rounded-3xl border border-zinc-800 shadow-2xl">
        <div className="text-center">
          <div className="mx-auto w-12 h-12 bg-blue-600 rounded-xl flex items-center justify-center mb-4">
            <span className="font-bold text-white text-lg">BE</span>
          </div>
          <h2 className="text-3xl font-bold tracking-tight text-white">
            {isLogin ? 'Авторизация' : 'Регистрация'}
          </h2>
          <p className="mt-2 text-sm text-zinc-500">
            {isLogin ? 'Войдите в свою инфраструктуру' : 'Создайте аккаунт для управления ботами'}
          </p>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 p-3 rounded-xl text-red-500 text-xs text-center">
            {error}
          </div>
        )}

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          <div className="space-y-4">
            {!isLogin && (
              <div>
                <label className="block text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-2">Имя пользователя</label>
                <input
                  type="text" required
                  className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-xl p-3 text-sm text-white focus:ring-1 focus:ring-blue-500 focus:outline-none transition-all"
                  value={username} onChange={(e) => setUsername(e.target.value)}
                />
              </div>
            )}
            <div>
              <label className="block text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-2">Email</label>
              <input
                type="email" required
                className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-xl p-3 text-sm text-white focus:ring-1 focus:ring-blue-500 focus:outline-none transition-all"
                value={email} onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-2">Пароль</label>
              <input
                type="password" required
                className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-xl p-3 text-sm text-white focus:ring-1 focus:ring-blue-500 focus:outline-none transition-all"
                value={password} onChange={(e) => setPassword(e.target.value)}
              />
            </div>
          </div>

          <button
            type="submit"
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-4 rounded-xl transition-all shadow-lg shadow-blue-600/20"
          >
            {isLogin ? 'Войти' : 'Создать аккаунт'}
          </button>
        </form>

        <div className="text-center pt-4">
          <button
            onClick={() => setIsLogin(!isLogin)}
            className="text-xs text-zinc-500 hover:text-blue-400 font-medium uppercase tracking-widest transition-colors"
          >
            {isLogin ? "Нет аккаунта? Регистрация" : 'Уже есть аккаунт? Войти'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default Auth;
