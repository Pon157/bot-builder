import React, { useState } from 'react';
import { User, BotConfig } from '../types';
import { api } from '../services/apiService';
import { 
  Key, 
  ShoppingCart, 
  Bot as BotIcon, 
  RefreshCw, 
  FileText, 
  ExternalLink, 
  Megaphone, 
  MessageCircle, 
  LifeBuoy 
} from 'lucide-react';

interface ProfileProps {
  user: User;
  bots: BotConfig[];
  onUpdateBots: (bots: BotConfig[]) => void;
}

const Profile: React.FC<ProfileProps> = ({ user, bots, onUpdateBots }) => {
  const [activationKey, setActivationKey] = useState('');
  const [selectedBotId, setSelectedBotId] = useState('');
  const [isActivating, setIsActivating] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);

  // Ссылки на файлы в GitHub
  const GITHUB_RAW_URL = "https://raw.githubusercontent.com/Pon157/bot-builder/main";

  const refreshData = async () => {
    setIsSyncing(true);
    try {
      const serverBots = await api.getBots(user.id);
      onUpdateBots(serverBots);
    } catch (e) {
      console.error("Refresh failed", e);
    } finally {
      setIsSyncing(false);
    }
  };

  const handleActivate = async () => {
    if (!activationKey || !selectedBotId) return;
    setIsActivating(true);
    try {
      const res = await api.activateLicense(selectedBotId, activationKey);
      if (res && res.status === 'ok') {
        await refreshData();
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
      <header className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold mb-2 text-white">Управление лицензиями</h1>
          <p className="text-sm text-zinc-500">Активируйте ключи для конкретных ботов. Срок суммируется.</p>
        </div>
        <button 
          onClick={refreshData} 
          disabled={isSyncing}
          className="flex items-center gap-2 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-xl text-xs font-bold transition-all border border-zinc-700"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? 'animate-spin' : ''}`} />
          Обновить статус
        </button>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 md:gap-8">
        {/* Левая колонка */}
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
                  <div key={bot.id} className="flex flex-col sm:flex-row sm:items-center justify-between p-4 bg-black border border-zinc-800 rounded-2xl gap-3 hover:border-zinc-700 transition-colors">
                    <div>
                      <p className="text-sm font-bold text-white truncate max-w-[200px]">{bot.name}</p>
                      <p className="text-[10px] text-zinc-500 font-mono uppercase tracking-tighter opacity-50">{bot.id}</p>
                    </div>
                    <div className="text-left sm:text-right">
                      <p className={`text-xs font-black uppercase tracking-widest ${expired ? 'text-red-500' : 'text-emerald-500'}`}>
                        {expired ? 'Истекла' : `${days} дн. доступа`}
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
                <span className="text-[10px] font-bold text-zinc-500 uppercase mb-2 block ml-2">Выберите бота</span>
                <select 
                  className="w-full bg-black border border-zinc-800 rounded-xl p-4 text-sm text-white outline-none focus:border-blue-500 appearance-none cursor-pointer"
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
                  placeholder="Введите ключ (напр. PRO-30-DAYS-XXXX)"
                  value={activationKey}
                  onChange={e => setActivationKey(e.target.value)}
                />
                <button 
                  onClick={handleActivate}
                  disabled={isActivating || !activationKey || !selectedBotId}
                  className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-black px-8 py-4 rounded-xl transition-all uppercase tracking-widest text-xs shadow-lg shadow-blue-600/20"
                >
                  {isActivating ? 'Активация...' : 'Активировать лицензию'}
                </button>
              </div>
            </div>
          </section>
        </div>

        {/* Правая колонка */}
        <div className="space-y-6">
          {/* Маркетплейс */}
          <div className="bg-blue-600/10 border border-blue-500/20 rounded-3xl p-6 md:p-8 flex flex-col items-center text-center shadow-xl shadow-blue-900/5">
            <ShoppingCart className="w-10 h-10 md:w-12 md:h-12 text-blue-500 mb-4" />
            <h3 className="text-lg font-bold text-white mb-2">Маркетплейс</h3>
            <div className="text-xs text-zinc-400 mb-6 space-y-2">
              <p>При покупке ключа срок добавляется к текущему.</p>
              <div className="py-3 bg-black/40 rounded-xl border border-blue-500/10 mt-2">
                <p className="text-white font-bold text-sm">⭐ 50 | 0,7 $ — 30 дней</p>
                <p className="text-white font-bold text-sm">⭐ 120 | 1,5 $ — 90 дней</p>
              </div>
            </div>
            <a href="https://t.me/dialogengine_bot" target="_blank" rel="noreferrer" className="w-full bg-white text-black font-black py-4 rounded-xl uppercase tracking-widest text-xs hover:bg-zinc-200 transition-all shadow-xl text-center">Купить ключ в TG</a>
          </div>

          {/* ТЕХНИЧЕСКАЯ ПОДДЕРЖКА */}
          <a 
            href="https://t.me/DialogeEngineSupportBot" 
            target="_blank" 
            rel="noreferrer" 
            className="flex items-center gap-4 p-5 bg-emerald-500/10 border border-emerald-500/20 rounded-3xl hover:bg-emerald-500/20 transition-all group"
          >
            <div className="w-10 h-10 bg-emerald-500 rounded-2xl flex items-center justify-center shadow-lg shadow-emerald-500/20">
              <LifeBuoy className="w-5 h-5 text-white animate-pulse" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-white group-hover:text-emerald-400 transition-colors">Тех. поддержка</h4>
              <p className="text-[10px] text-zinc-500">Поможем с настройкой 24/7</p>
            </div>
          </a>

          {/* НАШ ТГК */}
          <div className="bg-[#121212] border border-zinc-800 rounded-3xl p-6 flex flex-col items-center text-center">
            <div className="w-10 h-10 bg-zinc-800 rounded-full flex items-center justify-center mb-4">
               <MessageCircle className="w-5 h-5 text-sky-400" />
            </div>
            <h4 className="text-sm font-bold text-white mb-1 uppercase tracking-tight">Наше сообщество</h4>
            <p className="text-[11px] text-zinc-500 mb-4">Новости, обновления, промокоды и важные анонсы.</p>
            <a 
              href="https://t.me/dialogeengine" 
              target="_blank" 
              rel="noreferrer"
              className="w-full py-3 bg-zinc-800 hover:bg-zinc-700 text-sky-400 text-[11px] font-bold rounded-xl transition-colors flex items-center justify-center gap-2"
            >
              Перейти в канал
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>

          {/* РЕКЛАМА (ОДИН СЛОТ) */}
          <div className="bg-zinc-900/30 border border-zinc-800/50 rounded-3xl p-6">
            <div className="flex items-center gap-2 mb-4 opacity-50">
               <Megaphone className="w-3 h-3 text-zinc-400" />
               <span className="text-[9px] font-black uppercase tracking-[0.2em] text-zinc-400">Реклама</span>
            </div>
            <a href="https://t.me/NOVA_creators" target="_blank" rel="noreferrer" className="block group">
              <p className="text-xs font-bold text-zinc-200 group-hover:text-blue-400 transition-colors mb-1">NOVA CREATIVE STUDIO</p>
              <p className="text-[10px] text-zinc-500 leading-relaxed mb-3">NOVA — твоя креативная студия в Telegram:
Крутые аватарки, баннеры, тексты и оформление для твоего канала.
Хочешь стильный контент — просто напиши.</p>
              <span className="text-[10px] text-blue-500 font-bold flex items-center gap-1 group-hover:underline">
                Подробнее <ExternalLink className="w-2.5 h-2.5" />
              </span>
            </a>
          </div>

          {/* ИНФОРМАЦИЯ */}
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-3xl p-6">
            <h4 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-4 flex items-center gap-2">
              <FileText className="w-3 h-3" />
              Документация
            </h4>
            <div className="space-y-2">
              <a 
                href={`${GITHUB_RAW_URL}/user_agreement.pdf`} 
                target="_blank" 
                rel="noreferrer"
                className="flex items-center justify-between p-3 bg-black/30 border border-zinc-800 rounded-xl text-[10px] text-zinc-400 hover:text-white hover:border-zinc-600 transition-all"
              >
                Соглашение
                <ExternalLink className="w-3 h-3 opacity-30" />
              </a>
              <a 
                href={`${GITHUB_RAW_URL}/privacy_policy.pdf`} 
                target="_blank" 
                rel="noreferrer"
                className="flex items-center justify-between p-3 bg-black/30 border border-zinc-800 rounded-xl text-[10px] text-zinc-400 hover:text-white hover:border-zinc-600 transition-all"
              >
                Конфиденциальность
                <ExternalLink className="w-3 h-3 opacity-30" />
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Profile;
