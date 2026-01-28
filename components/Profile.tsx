
import React, { useState } from 'react';
import { User, BotConfig } from '../types';
import { api } from '../services/apiService';
import { Key, ShoppingCart, Calendar, ShieldCheck, Clock, Bot as BotIcon } from 'lucide-react';

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
        const updatedBots = bots.map(b => b.id === selectedBotId ? { ...b, licenseExpiresAt: res.newExpiry } : b);
        onUpdateBots(updatedBots);
        alert("Лицензия бота успешно продлена!");
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

  return (
    <div className="space-y-12 animate-in fade-in duration-500">
      <header>
        <h1 className="text-3xl font-bold mb-2 text-white">Управление лицензиями</h1>
        <p className="text-zinc-500">Активируйте ключи для конкретных ботов. Один ключ — один бот.</p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-8">
            <section className="bg-[#121212] border border-zinc-800 rounded-[2.5rem] p-8 shadow-2xl">
                <h3 className="text-xl font-bold text-white mb-6 flex items-center gap-2">
                    <BotIcon className="w-5 h-5 text-blue-500" />
                    Ваши инстансы
                </h3>
                <div className="space-y-3">
                    {bots.map(bot => {
                        const days = Math.max(0, Math.ceil((bot.licenseExpiresAt - Date.now()) / (1000 * 3600 * 24)));
                        const expired = days === 0;
                        return (
                            <div key={bot.id} className="flex items-center justify-between p-4 bg-black border border-zinc-800 rounded-2xl">
                                <div>
                                    <p className="text-sm font-bold text-white">{bot.name}</p>
                                    <p className="text-[10px] text-zinc-500 font-mono">{bot.id}</p>
                                </div>
                                <div className="text-right">
                                    <p className={`text-xs font-black uppercase tracking-widest ${expired ? 'text-red-500' : 'text-green-500'}`}>
                                        {expired ? 'Истекла' : `${days} дн.`}
                                    </p>
                                    <p className="text-[9px] text-zinc-600">До {new Date(bot.licenseExpiresAt).toLocaleDateString()}</p>
                                </div>
                            </div>
                        );
                    })}
                    {bots.length === 0 && <p className="text-center text-zinc-600 py-10 uppercase text-[10px] font-bold">Нет созданных ботов</p>}
                </div>
            </section>

            <section className="bg-[#111] border border-zinc-800 rounded-[2rem] p-8 space-y-6">
                <h3 className="text-xl font-bold flex items-center gap-2 text-white">
                    <Key className="w-5 h-5 text-blue-500" />
                    Активация ключа
                </h3>
                <div className="space-y-4">
                    <label className="block">
                        <span className="text-[10px] font-bold text-zinc-500 uppercase mb-2 block">Выберите бота для продления</span>
                        <select 
                            className="w-full bg-black border border-zinc-800 rounded-xl p-4 text-sm text-white outline-none focus:border-blue-500"
                            value={selectedBotId}
                            onChange={e => setSelectedBotId(e.target.value)}
                        >
                            <option value="">-- Выбрать из списка --</option>
                            {bots.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                        </select>
                    </label>
                    
                    <div className="flex flex-col md:flex-row gap-4">
                        <input 
                            className="flex-1 bg-black border border-zinc-800 rounded-xl p-4 text-sm font-mono text-white outline-none focus:border-blue-500 transition-colors"
                            placeholder="BOT-1-XXXX-XXXX"
                            value={activationKey}
                            onChange={e => setActivationKey(e.target.value)}
                        />
                        <button 
                            onClick={handleActivate}
                            disabled={isActivating || !activationKey || !selectedBotId}
                            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-black px-8 py-4 rounded-xl transition-all uppercase tracking-widest text-xs whitespace-nowrap"
                        >
                            {isActivating ? 'Активация...' : 'Активировать'}
                        </button>
                    </div>
                </div>
                <p className="text-[10px] text-zinc-600 font-bold uppercase tracking-widest text-center">
                    Ключ привязывается только к выбранному боту и не может быть перенесен
                </p>
            </section>
        </div>

        <div className="space-y-6">
            <div className="bg-blue-600/10 border border-blue-500/20 rounded-3xl p-8 flex flex-col items-center text-center">
                <ShoppingCart className="w-12 h-12 text-blue-500 mb-4" />
                <h3 className="text-lg font-bold text-white mb-2">Ценообразование</h3>
                <p className="text-xs text-zinc-400 mb-6 leading-relaxed">
                    Каждый бот требует отдельной подписки.
                    <br/><br/>
                    1 бот / 1 мес — 50 звезд ⭐<br/>
                    1 бот / 3 мес — 120 звезд ⭐<br/>
                </p>
                <a href="https://t.me/dialogengine_bot" target="_blank" className="w-full bg-white text-black font-black py-4 rounded-xl uppercase tracking-widest text-xs hover:bg-zinc-200 transition-all shadow-xl text-center">Купить через Telegram</a>
            </div>
        </div>
      </div>
    </div>
  );
};

export default Profile;
