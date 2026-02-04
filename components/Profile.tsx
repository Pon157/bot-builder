
import React, { useState } from 'react';
import { User, BotConfig } from '../types';
import { api } from '../services/apiService';
import { Key, ShoppingCart, Bot as BotIcon } from 'lucide-react';

interface ProfileProps {
  user: User;
  bots: BotConfig[];
  onUpdateBots: (bots: BotConfig[]) => void;
}

const Profile: React.FC<ProfileProps> = ({ user, bots, onUpdateBots }) => {
  const [activationKey, setActivationKey] = useState('');
  const [selectedBotId, setSelectedBotId] = useState('');
  const [isActivating, setIsActivating] = useState(false);

  const handleActivate = async () => {
    if (!activationKey || !selectedBotId) return;
    setIsActivating(true);
    try {
      const res = await api.activateLicense(selectedBotId, activationKey);
      if (res && res.status === 'ok') {
        const updatedBots = bots.map(b => b.id === selectedBotId ? { ...b, license_expires_at: res.newExpiry } : b);
        onUpdateBots(updatedBots);
        alert("Лицензия бота успешно продлена!");
        setActivationKey('');
      } else {
        alert("Ошибка активации: " + (res.message || "Неверный ключ"));
      }
    } catch (e) {
      alert("Ошибка сервера при активации");
    } finally {
      setIsActivating(false);
    }
  };

  return (
    <div className="space-y-8 md:space-y-12 animate-in fade-in duration-500 pb-10">
      <header>
        <h1 className="text-2xl md:text-3xl font-bold mb-2 text-white">Управление лицензиями</h1>
        <p className="text-sm text-zinc-500">Активируйте ключи для конкретных ботов. Один ключ — один бот.</p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 md:gap-8">
        <div className="lg:col-span-2 space-y-6 md:space-y-8">
            <section className="bg-[#121212] border border-zinc-800 rounded-[1.5rem] md:rounded-[2.5rem] p-5 md:p-8 shadow-2xl">
                <h3 className="text-lg md:text-xl font-bold text-white mb-6 flex items-center gap-2">
                    <BotIcon className="w-5 h-5 text-blue-500" />
                    Ваши инстансы
                </h3>
                <div className="space-y-3">
                    {bots.map(bot => {
                        const expiry = Number(bot.license_expires_at) || 0;
                        const days = Math.max(0, Math.ceil((expiry - Date.now()) / (1000 * 3600 * 24)));
                        const expired = days === 0;
                        return (
                            <div key={bot.id} className="flex flex-col sm:flex-row sm:items-center justify-between p-4 bg-black border border-zinc-800 rounded-2xl gap-3">
                                <div>
                                    <p className="text-sm font-bold text-white truncate max-w-[200px]">{bot.name}</p>
                                    <p className="text-[10px] text-zinc-500 font-mono">{bot.id}</p>
                                </div>
                                <div className="text-left sm:text-right">
                                    <p className={`text-xs font-black uppercase tracking-widest ${expired ? 'text-red-500' : 'text-green-500'}`}>
                                        {expired ? 'Истекла' : `${days} дн.`}
                                    </p>
                                    <p className="text-[9px] text-zinc-600">До {expiry > 0 ? new Date(expiry).toLocaleDateString() : '---'}</p>
                                </div>
                            </div>
                        );
                    })}
                    {bots.length === 0 && <p className="text-center text-zinc-600 py-10 uppercase text-[10px] font-bold">Нет созданных ботов</p>}
                </div>
            </section>

            <section className="bg-[#111] border border-zinc-800 rounded-[1.5rem] md:rounded-[2.5rem] p-5 md:p-8 space-y-6">
                <h3 className="text-lg md:text-xl font-bold flex items-center gap-2 text-white">
                    <Key className="w-5 h-5 text-blue-500" />
                    Активация ключа
                </h3>
                <div className="space-y-4">
                    <label className="block">
                        <span className="text-[10px] font-bold text-zinc-500 uppercase mb-2 block">Выберите бота для продления</span>
                        <select 
                            className="w-full bg-black border border-zinc-800 rounded-xl p-4 text-sm text-white outline-none focus:border-blue-500 appearance-none"
                            value={selectedBotId}
                            onChange={e => setSelectedBotId(e.target.value)}
                        >
                            <option value="">-- Выбрать из списка --</option>
                            {bots.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                        </select>
                    </label>
                    
                    <div className="flex flex-col gap-4">
                        <input 
                            className="w-full bg-black border border-zinc-800 rounded-xl p-4 text-sm font-mono text-white outline-none focus:border-blue-500 transition-colors"
                            placeholder="BOT-1-XXXX-XXXX"
                            value={activationKey}
                            onChange={e => setActivationKey(e.target.value)}
                        />
                        <button 
                            onClick={handleActivate}
                            disabled={isActivating || !activationKey || !selectedBotId}
                            className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-black px-8 py-4 rounded-xl transition-all uppercase tracking-widest text-xs shadow-lg shadow-blue-600/20"
                        >
                            {isActivating ? 'Активация...' : 'Активировать'}
                        </button>
                    </div>
                </div>
                <p className="text-[10px] text-zinc-600 font-bold uppercase tracking-widest text-center leading-relaxed">
                    Ключ привязывается только к выбранному боту и не может быть перенесен
                </p>
            </section>
        </div>

        <div className="space-y-6">
            <div className="bg-blue-600/10 border border-blue-500/20 rounded-3xl p-6 md:p-8 flex flex-col items-center text-center">
                <ShoppingCart className="w-10 h-10 md:w-12 md:h-12 text-blue-500 mb-4" />
                <h3 className="text-lg font-bold text-white mb-2">Ценообразование</h3>
                <div className="text-xs text-zinc-400 mb-6 space-y-2">
                    <p>Каждый бот требует отдельной подписки.</p>
                    <div className="py-2 bg-black/40 rounded-xl border border-blue-500/10 mt-2">
                      <p className="text-white font-bold">1 бот / 1 мес — 50 звезд ⭐</p>
                      <p className="text-white font-bold">1 бот / 3 мес — 120 звезд ⭐</p>
                    </div>
                </div>
                <a href="https://t.me/Kotickr" target="_blank" className="w-full bg-white text-black font-black py-4 rounded-xl uppercase tracking-widest text-xs hover:bg-zinc-200 transition-all shadow-xl text-center">Купить через Telegram</a>
            </div>
        </div>
      </div>
    </div>
  );
};

export default Profile;
