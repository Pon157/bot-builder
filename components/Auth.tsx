
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

    const usersStr = localStorage.getItem('global_accounts_db') || '[]';
    const users: User[] = JSON.parse(usersStr);

    if (isLogin) {
      const foundUser = users.find(u => u.email === email && u.password === password);
      if (foundUser) {
        onLogin(foundUser);
      } else {
        setError('Некорректный логин или пароль');
      }
    } else {
      if (users.find(u => u.email === email)) {
        setError('Этот email уже занят');
        return;
      }
      
      const newUser: User = {
        id: 'u_' + Math.random().toString(36).substr(2, 9),
        username: username || email.split('@')[0],
        email: email,
        password: password,
        subscription: 'FREE',
        balance: 0,
        botsCreated: 0
      };
      
      users.push(newUser);
      localStorage.setItem('global_accounts_db', JSON.stringify(users));
      onLogin(newUser);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#050505] px-4 font-sans">
      <div className="w-full max-w-md space-y-8 bg-[#121212] p-10 rounded-3xl border border-zinc-800 shadow-2xl">
        <div className="text-center">
          <div className="mx-auto w-14 h-14 bg-blue-600 rounded-2xl flex items-center justify-center mb-6 shadow-xl shadow-blue-600/20">
            <span className="font-black text-white text-xl">BE</span>
          </div>
          <h2 className="text-3xl font-black text-white mb-2">{isLogin ? 'Вход' : 'Регистрация'}</h2>
          <p className="text-sm text-zinc-500 uppercase tracking-widest font-bold">BotEngine Cloud Infrastructure</p>
        </div>

        {error && <div className="bg-red-500/10 border border-red-500/20 p-4 rounded-xl text-red-500 text-xs text-center font-bold">{error}</div>}

        <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
          {!isLogin && (
            <input type="text" required className="w-full bg-black border border-zinc-800 rounded-xl p-4 text-sm text-white focus:ring-1 focus:ring-blue-500 outline-none" placeholder="Имя профиля" value={username} onChange={(e) => setUsername(e.target.value)} />
          )}
          <input type="email" required className="w-full bg-black border border-zinc-800 rounded-xl p-4 text-sm text-white focus:ring-1 focus:ring-blue-500 outline-none" placeholder="Email адрес" value={email} onChange={(e) => setEmail(e.target.value)} />
          <input type="password" required className="w-full bg-black border border-zinc-800 rounded-xl p-4 text-sm text-white focus:ring-1 focus:ring-blue-500 outline-none" placeholder="Пароль" value={password} onChange={(e) => setPassword(e.target.value)} />
          <button type="submit" className="w-full bg-blue-600 hover:bg-blue-700 text-white font-black py-4 rounded-xl transition-all shadow-lg shadow-blue-600/30 uppercase tracking-widest">
            {isLogin ? 'Авторизоваться' : 'Создать Личность'}
          </button>
        </form>

        <div className="text-center">
          <button onClick={() => setIsLogin(!isLogin)} className="text-xs text-zinc-600 hover:text-blue-500 font-bold uppercase tracking-widest transition-all">
            {isLogin ? "Нет аккаунта? Стать резидентом" : 'Уже в системе? Войти'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default Auth;
