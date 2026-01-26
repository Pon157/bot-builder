
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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // In a real app, this would be an API call
    // Added missing properties: subscription, balance, botsCreated to satisfy User type
    const mockUser: User = {
      id: Math.random().toString(36).substr(2, 9),
      username: username || email.split('@')[0],
      email: email,
      subscription: 'FREE',
      balance: 0,
      botsCreated: 0
    };
    onLogin(mockUser);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0a0a] px-4">
      <div className="w-full max-w-md space-y-8 bg-[#121212] p-10 rounded-3xl border border-zinc-800 shadow-2xl">
        <div className="text-center">
          <div className="mx-auto w-12 h-12 bg-blue-600 rounded-xl flex items-center justify-center mb-4">
            <span className="font-bold text-white text-lg">BE</span>
          </div>
          <h2 className="text-3xl font-bold tracking-tight text-white">
            {isLogin ? 'Welcome Back' : 'Create Account'}
          </h2>
          <p className="mt-2 text-sm text-zinc-500">
            {isLogin ? 'Access your bot infrastructure' : 'Start building autonomous bots today'}
          </p>
        </div>

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          <div className="space-y-4">
            {!isLogin && (
              <div>
                <label className="block text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-2">Username</label>
                <input
                  type="text"
                  required
                  className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-xl p-3 text-sm text-white focus:ring-1 focus:ring-blue-500 focus:outline-none transition-all"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
              </div>
            )}
            <div>
              <label className="block text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-2">Email Address</label>
              <input
                type="email"
                required
                className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-xl p-3 text-sm text-white focus:ring-1 focus:ring-blue-500 focus:outline-none transition-all"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-2">Password</label>
              <input
                type="password"
                required
                className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-xl p-3 text-sm text-white focus:ring-1 focus:ring-blue-500 focus:outline-none transition-all"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
          </div>

          <button
            type="submit"
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-4 rounded-xl transition-all shadow-lg shadow-blue-600/20"
          >
            {isLogin ? 'Sign In' : 'Sign Up'}
          </button>
        </form>

        <div className="text-center pt-4">
          <button
            onClick={() => setIsLogin(!isLogin)}
            className="text-xs text-zinc-500 hover:text-blue-400 font-medium uppercase tracking-widest transition-colors"
          >
            {isLogin ? "Don't have an account? Sign Up" : 'Already have an account? Sign In'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default Auth;
