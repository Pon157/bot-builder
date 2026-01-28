
import React, { useState } from 'react';
import { User } from '../types';
import { api } from '../services/apiService';
import { Key, ShoppingCart, Calendar, ShieldCheck, Clock } from 'lucide-react';

interface ProfileProps {
  user: User;
  onUpdateUser: (user: User) => void;
}

const Profile: React.FC<ProfileProps> = ({ user, onUpdateUser }) => {
  const [activationKey, setActivationKey] = useState('');
  const [isActivating, setIsActivating] = useState(false);

  const handleActivate = async () => {
    if (!activationKey) return;
    setIsActivating(true);
    try {
      const res = await api.activateLicense(user.id, activationKey);
      if (res && res.status === 'ok') {
        onUpdateUser({ ...user, licenseExpiresAt: res.newExpiry, activeKey: activationKey });
        alert("Лицензия успешно продлена!");
        setActivationKey('');
      } else {
        alert("Ошибка активации: Неверный формат или ключ не найден");
      }
    } catch (e) {
      alert("Ошибка сервера при активации");
    } finally {
      setIsActivating(false);
    }
  };

  const daysRemaining = Math.max(0, Math.ceil((user.licenseExpiresAt - Date.now()) / (1000 * 60 * 60 * 24)));
  const isExpired = daysRemaining === 0;

  return (
    <div className="space-y-12 animate-in fade-in duration-500">
      <header>
        <h1 className="text-3xl font-bold mb-2 text-white">Управление лицензией</h1>
        <p className="text-zinc-500">Ваш аккаунт и статус доступа к конструктору.</p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-8">
            <section className="bg-[#121212] border border-zinc-800 rounded-3xl p-8 relative overflow-hidden shadow-2xl">
                <div className={`absolute top-0 right-0 p-8 opacity-10 ${isExpired ? 'text-red-500' : 'text-blue-500'}`}>
                    {isExpired ? <Clock className="w-32 h-32" /> : <ShieldCheck className="w-32 h-32" />}
                </div>

                <div className="flex items-center gap-6 mb-8 relative z-10">
                    <div className="w-20 h-20 bg-blue-600 rounded-2xl flex items-center justify-center text-3xl font-bold text-white shadow-xl shadow-blue-600/10">
                        {user.username.charAt(0).toUpperCase()}
                    </div>
                    <div>
                        <h2 className="text-2xl font-bold text-white">{user.username}</h2>
                        <p className="text-zinc-500 text-sm">{user.email}</p>
                        <div className="mt-2 flex gap-2">
                             <span className={`text-[10px] font-black px-2 py-0.5 rounded uppercase tracking-tighter border ${isExpired ? 'bg-red-500/10 text-red-500 border-red-500/20' : 'bg-green-500/10 text-green-500 border-green-500/20'}`}>
                                {isExpired ? 'Лицензия истекла' : 'Лицензия активна'}
                             </span>
                        </div>
                    </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 relative z-10">
                    <div className="bg-zinc-900/50 p-6 rounded-2xl border border-zinc-800">
                        <p className="text-[10px] text-zinc-500 uppercase font-bold mb-1 tracking-widest">Осталось дней</p>
                        <p className={`text-4xl font-black ${daysRemaining < 5 ? 'text-red-500' : 'text-white'}`}>{daysRemaining}</p>
                    </div>
                    <div className="bg-zinc-900/50 p-6 rounded-2xl border border-zinc-800">
                        <p className="text-[10px] text-zinc-500 uppercase font-bold mb-1 tracking-widest">Истекает</p>
                        <p className="text-xl font-bold text-white">{new Date(user.licenseExpiresAt).toLocaleDateString()}</p>
                    </div>
                </div>
            </section>

            <section className="bg-[#111] border border-zinc-800 rounded-[2rem] p-8 space-y-6">
                <h3 className="text-xl font-bold flex items-center gap-2 text-white">
                    <Key className="w-5 h-5 text-blue-500" />
                    Активация ключа
                </h3>
                <div className="flex flex-col md:flex-row gap-4">
                    <input 
                        className="flex-1 bg-black border border-zinc-800 rounded-xl p-4 text-sm font-mono text-white outline-none focus:border-blue-500 transition-colors"
                        placeholder="BOT-1-XXXX-XXXX"
                        value={activationKey}
                        onChange={e => setActivationKey(e.target.value)}
                    />
                    <button 
                        onClick={handleActivate}
                        disabled={isActivating || !activationKey}
                        className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-black px-8 py-4 rounded-xl transition-all uppercase tracking-widest text-xs whitespace-nowrap"
                    >
                        {isActivating ? 'Активация...' : 'Активировать'}
                    </button>
                </div>
                <p className="text-[10px] text-zinc-600 font-bold uppercase tracking-widest text-center">
                    Вставьте ключ из бота после подтверждения оплаты оператором
                </p>
            </section>
        </div>

        <div className="space-y-6">
            <div className="bg-blue-600/10 border border-blue-500/20 rounded-3xl p-8 flex flex-col items-center text-center">
                <ShoppingCart className="w-12 h-12 text-blue-500 mb-4" />
                <h3 className="text-lg font-bold text-white mb-2">Нужен ключ?</h3>
                <p className="text-xs text-zinc-400 mb-6 leading-relaxed">
                    Купите ключ в нашем официальном боте за звезды ⭐ или через поддержку.
                    <br/><br/>
                    1 месяц — 50 звезд ⭐<br/>
                    2 месяца — 100 звезд ⭐<br/>
                    <b>Оптовые скидки</b> при заказе от 3-х ключей.
                </p>
                <a 
                    href="https://t.me/Kotickr" 
                    target="_blank" 
                    rel="noreferrer"
                    className="w-full bg-white text-black font-black py-4 rounded-xl uppercase tracking-widest text-xs hover:bg-zinc-200 transition-all shadow-xl"
                >
                    Купить через Telegram
                </a>
            </div>

            <div className="bg-zinc-900/50 border border-zinc-800 rounded-3xl p-6">
                <h3 className="text-sm font-bold mb-4 uppercase tracking-widest text-zinc-500">Важная информация</h3>
                <ul className="text-xs text-zinc-400 space-y-3">
                    <li className="flex gap-2">
                        <span className="text-blue-500 font-bold">●</span>
                        Бесплатный период 30 дней доступен 1 раз.
                    </li>
                    <li className="flex gap-2">
                        <span className="text-blue-500 font-bold">●</span>
                        При активации нового ключа сроки суммируются.
                    </li>
                    <li className="flex gap-2">
                        <span className="text-blue-500 font-bold">●</span>
                        Если лицензия истекла, боты автоматически остановятся.
                    </li>
                </ul>
            </div>
        </div>
      </div>
    </div>
  );
};

export default Profile;
