import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { User, BotConfig } from '../types';
import { api } from '../services/apiService';
import {
  Key, ShoppingCart, Bot as BotIcon, RefreshCw, FileText,
  ExternalLink, Megaphone, MessageCircle, LifeBuoy, Brain, Coins, Zap, AppWindow
} from 'lucide-react';

interface ProfileProps {
  user: User;
  bots: BotConfig[];
  onUpdateBots: (bots: BotConfig[]) => void;
}

const Profile: React.FC<ProfileProps> = ({ user, bots, onUpdateBots }) => {
  const [activationKey, setActivationKey]   = useState('');
  const [selectedBotId, setSelectedBotId]   = useState('');
  const [isActivating, setIsActivating]     = useState(false);
  const [isSyncing, setIsSyncing]           = useState(false);
  const [activeSection, setActiveSection]   = useState<'license' | 'ai' | 'miniapps'>('license');
  const [miniappKey, setMiniappKey]         = useState('');
  const [miniappBotId, setMiniappBotId]     = useState('');
  const [activatingMiniapp, setActivatingMiniapp] = useState(false);
  const [miniappLicenses, setMiniappLicenses] = useState<Record<string, {active: boolean, expires_at: number}>>({});

  // AI-токены
  const [aiKey, setAiKey]               = useState('');
  const [aiKeyBotId, setAiKeyBotId]     = useState('');
  const [isActivatingAi, setActivatingAi] = useState(false);
  const [aiBalances, setAiBalances]     = useState<Record<string, number>>({});

  const GITHUB_RAW_URL = "https://raw.githubusercontent.com/Pon157/bot-builder/main";

  // Загружаем AI-балансы и мини-апп лицензии при маунте
  useEffect(() => {
    bots.forEach(bot => {
      fetch(`/api/ai/balance/${bot.id}`)
        .then(r => r.json())
        .then(d => setAiBalances(prev => ({ ...prev, [bot.id]: d.tokens_balance || 0 })))
        .catch(() => {});
      fetch(`/api/miniapps/license/${bot.id}`)
        .then(r => r.json())
        .then(d => setMiniappLicenses(prev => ({ ...prev, [bot.id]: d })))
        .catch(() => {});
    });
  }, [bots]);

  const handleActivateMiniapp = async () => {
    if (!miniappKey || !miniappBotId) return;
    setActivatingMiniapp(true);
    try {
      const r = await fetch('/api/miniapps/activate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: miniappKey.trim().toUpperCase(), botId: miniappBotId })
      });
      const res = await r.json();
      if (res.status === 'ok') {
        setMiniappLicenses(prev => ({ ...prev, [miniappBotId]: { active: true, expires_at: res.expires_at } }));
        alert(`✅ Мини-апп активированы! До ${new Date(res.expires_at).toLocaleDateString()}`);
        setMiniappKey('');
      } else {
        alert('Ошибка: ' + (res.message || 'Неизвестная ошибка'));
      }
    } catch { alert('Ошибка сети'); }
    finally { setActivatingMiniapp(false); }
  };

  const refreshData = async () => {
    setIsSyncing(true);
    try {
      const serverBots = await api.getBots(user.id);
      onUpdateBots(serverBots);
    } catch (e) { console.error('Refresh failed', e); }
    finally { setIsSyncing(false); }
  };

  const handleActivate = async () => {
    if (!activationKey || !selectedBotId) return;
    setIsActivating(true);
    try {
      const res = await api.activateLicense(selectedBotId, activationKey);
      if (res && res.status === 'ok') {
        await refreshData();
        alert('Лицензия бота успешно продлена!');
        setActivationKey('');
      } else {
        alert('Ошибка активации: ' + (res.message || 'Неверный ключ'));
      }
    } catch { alert('Ошибка сервера при активации'); }
    finally { setIsActivating(false); }
  };

  const handleActivateAi = async () => {
    if (!aiKey || !aiKeyBotId) return;
    setActivatingAi(true);
    try {
      const r = await fetch('/api/ai/activate-tokens', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: aiKey.trim().toUpperCase(), botId: aiKeyBotId })
      });
      const res = await r.json();
      if (res.status === 'ok') {
        alert(`✅ Начислено ${res.tokens_added?.toLocaleString()} AI-токенов!`);
        setAiKey('');
        // Обновляем баланс
        fetch(`/api/ai/balance/${aiKeyBotId}`)
          .then(r => r.json())
          .then(d => setAiBalances(prev => ({ ...prev, [aiKeyBotId]: d.tokens_balance || 0 })));
      } else {
        alert('Ошибка: ' + (res.message || 'Неизвестная ошибка'));
      }
    } catch { alert('Ошибка сети'); }
    finally { setActivatingAi(false); }
  };

  return (
    <div className="space-y-8 md:space-y-12 animate-in fade-in duration-500 pb-10">
      {/* Шапка */}
      <header className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold mb-2 text-white">Управление ботами</h1>
          <p className="text-sm text-zinc-500">Лицензии, AI-токены и настройки</p>
        </div>
        <button onClick={refreshData} disabled={isSyncing}
          className="flex items-center gap-2 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-xl text-xs font-bold transition-all border border-zinc-700">
          <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? 'animate-spin' : ''}`} />
          Обновить
        </button>
      </header>

      {/* Переключатель раздела */}
      <div className="flex bg-black border border-zinc-800 rounded-2xl p-1 w-fit gap-1 flex-wrap">
        {([
          { id: 'license',  label: '🔑 Лицензии'    },
          { id: 'ai',       label: '🤖 AI-токены'   },
          { id: 'miniapps', label: '📱 Мини-апп'    },
        ] as const).map(({ id, label }) => (
          <button key={id} onClick={() => setActiveSection(id)}
            className={`px-5 py-3 rounded-xl text-[11px] font-black uppercase tracking-wider transition-all ${
              activeSection === id ? 'bg-indigo-600 text-white shadow-lg' : 'text-zinc-500 hover:text-zinc-300'
            }`}>{label}</button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 md:gap-8">
        {/* Левая колонка */}
        <div className="lg:col-span-2 space-y-6 md:space-y-8">

          {/* ── ЛИЦЕНЗИИ ── */}
          {activeSection === 'license' && (<>
            {/* Список ботов + статус */}
            <section className="bg-[#121212] border border-zinc-800 rounded-[1.5rem] md:rounded-[2.5rem] p-5 md:p-8 shadow-2xl">
              <h3 className="text-lg md:text-xl font-bold text-white mb-6 flex items-center gap-2">
                <BotIcon className="w-5 h-5 text-blue-500" />Ваши инстансы
              </h3>
              <div className="space-y-3">
                {bots.map(bot => {
                  const expiry = Number(bot.license_expires_at) || 0;
                  const days   = Math.max(0, Math.ceil((expiry - Date.now()) / (1000 * 3600 * 24)));
                  const expired = days === 0;
                  return (
                    <div key={bot.id} className="flex flex-col sm:flex-row sm:items-center justify-between p-4 bg-black border border-zinc-800 rounded-2xl gap-3 hover:border-zinc-700 transition-colors">
                      <div>
                        <p className="text-sm font-bold text-white truncate max-w-[200px]">{bot.name}</p>
                        <p className="text-[10px] text-zinc-500 font-mono uppercase tracking-tighter opacity-50">{bot.id}</p>
                      </div>
                      <div className="text-left sm:text-right space-y-0.5">
                        <p className={`text-xs font-black uppercase tracking-widest ${expired ? 'text-red-500' : 'text-emerald-500'}`}>
                          {expired ? 'Истекла' : `${days} дн. доступа`}
                        </p>
                        {(aiBalances[bot.id] ?? 0) > 0 && (
                          <p className="text-[9px] text-purple-400 font-bold">
                            🤖 {aiBalances[bot.id].toLocaleString()} AI-токенов
                          </p>
                        )}
                        <p className="text-[9px] text-zinc-600">До {expiry > 0 ? new Date(expiry).toLocaleDateString() : '---'}</p>
                      </div>
                    </div>
                  );
                })}
                {bots.length === 0 && <p className="text-center text-zinc-600 py-10 uppercase text-[10px] font-bold">Нет созданных ботов</p>}
              </div>
            </section>

            {/* Активация лицензионного ключа */}
            <section className="bg-[#111] border border-zinc-800 rounded-[1.5rem] md:rounded-[2.5rem] p-5 md:p-8 space-y-6">
              <h3 className="text-lg md:text-xl font-bold flex items-center gap-2 text-white">
                <Key className="w-5 h-5 text-blue-500" />Активация лицензии
              </h3>
              <div className="space-y-4">
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase mb-2 block ml-2">Выберите бота</span>
                  <select className="w-full bg-black border border-zinc-800 rounded-xl p-4 text-sm text-white outline-none focus:border-blue-500 appearance-none cursor-pointer"
                    value={selectedBotId} onChange={e => setSelectedBotId(e.target.value)}>
                    <option value="">-- Выбрать из списка --</option>
                    {bots.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                </label>
                <div className="flex flex-col gap-4">
                  <input className="w-full bg-black border border-zinc-800 rounded-xl p-4 text-sm font-mono text-white outline-none focus:border-blue-500 transition-colors"
                    placeholder="DE-XXXXXX-NNN"
                    value={activationKey}
                    onChange={e => setActivationKey(e.target.value)} />
                  <button onClick={handleActivate}
                    disabled={isActivating || !activationKey || !selectedBotId}
                    className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-black px-8 py-4 rounded-xl transition-all uppercase tracking-widest text-xs shadow-lg shadow-blue-600/20">
                    {isActivating ? 'Активация...' : 'Активировать лицензию'}
                  </button>
                </div>
              </div>
            </section>
          </>)}

          {/* ── AI-ТОКЕНЫ ── */}
          {activeSection === 'ai' && (<>
            {/* Балансы */}
            <section className="bg-[#121212] border border-zinc-800 rounded-[1.5rem] md:rounded-[2.5rem] p-5 md:p-8 shadow-2xl">
              <h3 className="text-lg md:text-xl font-bold text-white mb-6 flex items-center gap-2">
                <Coins className="w-5 h-5 text-amber-500" />AI-токены по ботам
              </h3>
              <div className="space-y-3">
                {bots.map(bot => {
                  const bal = aiBalances[bot.id] ?? 0;
                  return (
                    <div key={bot.id} className="flex flex-col sm:flex-row sm:items-center justify-between p-4 bg-black border border-zinc-800 rounded-2xl gap-3 hover:border-zinc-700 transition-colors">
                      <div>
                        <p className="text-sm font-bold text-white">{bot.name}</p>
                        <p className="text-[10px] text-zinc-500 font-mono">{bot.id}</p>
                      </div>
                      <div className="text-right">
                        <p className={`text-xs font-black ${bal > 0 ? 'text-purple-400' : 'text-zinc-600'}`}>
                          {bal > 0 ? `${bal.toLocaleString()} токенов` : 'Нет токенов'}
                        </p>
                        <p className="text-[9px] text-zinc-600">AI-баланс</p>
                      </div>
                    </div>
                  );
                })}
                {bots.length === 0 && <p className="text-center text-zinc-600 py-10 uppercase text-[10px] font-bold">Нет созданных ботов</p>}
              </div>
            </section>

            {/* Активация AI-ключа */}
            <section className="bg-[#111] border border-zinc-800 rounded-[1.5rem] md:rounded-[2.5rem] p-5 md:p-8 space-y-6">
              <h3 className="text-lg md:text-xl font-bold flex items-center gap-2 text-white">
                <Brain className="w-5 h-5 text-purple-500" />Активация AI-ключа
              </h3>
              <div className="space-y-4">
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase mb-2 block ml-2">Выберите бота</span>
                  <select className="w-full bg-black border border-zinc-800 rounded-xl p-4 text-sm text-white outline-none focus:border-purple-500 appearance-none cursor-pointer"
                    value={aiKeyBotId} onChange={e => setAiKeyBotId(e.target.value)}>
                    <option value="">-- Выбрать из списка --</option>
                    {bots.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                </label>
                <input className="w-full bg-black border border-zinc-800 rounded-xl p-4 text-sm font-mono text-white outline-none focus:border-purple-500 transition-colors"
                  placeholder="AITOK-XXXXXX-NNN"
                  value={aiKey}
                  onChange={e => setAiKey(e.target.value)} />
                <button onClick={handleActivateAi}
                  disabled={isActivatingAi || !aiKey || !aiKeyBotId}
                  className="w-full bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white font-black px-8 py-4 rounded-xl transition-all uppercase tracking-widest text-xs shadow-lg shadow-purple-600/20">
                  {isActivatingAi ? 'Активация...' : 'Активировать AI-токены'}
                </button>
              </div>
            </section>
          </>)}

          {/* ── МИНИ-АПП ── */}
          {activeSection === 'miniapps' && (<>
            {/* Статус по ботам */}
            <section className="bg-[#121212] border border-zinc-800 rounded-[1.5rem] md:rounded-[2.5rem] p-5 md:p-8 shadow-2xl">
              <h3 className="text-lg md:text-xl font-bold text-white mb-6 flex items-center gap-2">
                <AppWindow className="w-5 h-5 text-indigo-500" />Мини-апп по ботам
              </h3>
              <div className="space-y-3">
                {bots.map(bot => {
                  const lic = miniappLicenses[bot.id];
                  const active = lic?.active || false;
                  const expiry = lic?.expires_at || 0;
                  const days = Math.max(0, Math.ceil((expiry - Date.now()) / (1000 * 3600 * 24)));
                  return (
                    <div key={bot.id} className="flex flex-col sm:flex-row sm:items-center justify-between p-4 bg-black border border-zinc-800 rounded-2xl gap-3 hover:border-zinc-700 transition-colors">
                      <div>
                        <p className="text-sm font-bold text-white truncate max-w-[200px]">{bot.name}</p>
                        <p className="text-[10px] text-zinc-500 font-mono">{bot.id}</p>
                      </div>
                      <div className="text-right">
                        <p className={`text-xs font-black uppercase tracking-widest ${active ? 'text-indigo-400' : 'text-zinc-600'}`}>
                          {active ? `✅ ${days} дн. доступа` : '— Не активно'}
                        </p>
                        {expiry > 0 && <p className="text-[9px] text-zinc-600">До {new Date(expiry).toLocaleDateString()}</p>}
                      </div>
                    </div>
                  );
                })}
                {bots.length === 0 && <p className="text-center text-zinc-600 py-10 uppercase text-[10px] font-bold">Нет ботов</p>}
              </div>
            </section>

            {/* Активация ключа */}
            <section className="bg-[#111] border border-zinc-800 rounded-[1.5rem] md:rounded-[2.5rem] p-5 md:p-8 space-y-6">
              <h3 className="text-lg md:text-xl font-bold flex items-center gap-2 text-white">
                <Key className="w-5 h-5 text-indigo-500" />Активация мини-апп ключа
              </h3>
              <div className="space-y-4">
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase mb-2 block ml-2">Выберите бота</span>
                  <select className="w-full bg-black border border-zinc-800 rounded-xl p-4 text-sm text-white outline-none focus:border-indigo-500 appearance-none cursor-pointer"
                    value={miniappBotId} onChange={e => setMiniappBotId(e.target.value)}>
                    <option value="">-- Выбрать из списка --</option>
                    {bots.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                </label>
                <input className="w-full bg-black border border-zinc-800 rounded-xl p-4 text-sm font-mono text-white outline-none focus:border-indigo-500 transition-colors"
                  placeholder="MAPP-XXXXXX-NNN"
                  value={miniappKey}
                  onChange={e => setMiniappKey(e.target.value)} />
                <button onClick={handleActivateMiniapp}
                  disabled={activatingMiniapp || !miniappKey || !miniappBotId}
                  className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-black px-8 py-4 rounded-xl transition-all uppercase tracking-widest text-xs shadow-lg shadow-indigo-600/20">
                  {activatingMiniapp ? 'Активация...' : 'Активировать мини-апп'}
                </button>
              </div>
            </section>
          </>)}
        </div>

        {/* Правая колонка */}
        <div className="space-y-6">
          {/* Магазин лицензий */}
          {activeSection === 'license' && (
            <div className="bg-blue-600/10 border border-blue-500/20 rounded-3xl p-6 md:p-8 flex flex-col items-center text-center shadow-xl shadow-blue-900/5">
              <ShoppingCart className="w-10 h-10 md:w-12 md:h-12 text-blue-500 mb-4" />
              <h3 className="text-lg font-bold text-white mb-2">Купить лицензию</h3>
              <div className="text-xs text-zinc-400 mb-6 space-y-2">
                <p>При покупке срок добавляется к текущему.</p>
                <div className="py-3 bg-black/40 rounded-xl border border-blue-500/10 mt-2">
                  <p className="text-white font-bold text-sm">⭐ 50 | 0,7 $ — 30 дней</p>
                  <p className="text-white font-bold text-sm">⭐ 120 | 1,5 $ — 90 дней</p>
                </div>
              </div>
              <a href="https://t.me/dialogengine_bot" target="_blank" rel="noreferrer"
                className="w-full bg-white text-black font-black py-4 rounded-xl uppercase tracking-widest text-xs hover:bg-zinc-200 transition-all shadow-xl text-center">
                Купить ключ в TG
              </a>
            </div>
          )}

          {/* Магазин мини-апп */}
          {activeSection === 'miniapps' && (
            <div className="bg-indigo-600/10 border border-indigo-500/20 rounded-3xl p-6 md:p-8 flex flex-col items-center text-center shadow-xl">
              <AppWindow className="w-10 h-10 md:w-12 md:h-12 text-indigo-400 mb-4" />
              <h3 className="text-lg font-bold text-white mb-2">Мини-приложения</h3>
              <div className="text-xs text-zinc-400 mb-6 space-y-2">
                <p>Публичные веб-страницы с формами, кнопками и контентом.</p>
                <div className="py-3 bg-black/40 rounded-xl border border-indigo-500/10 mt-2 space-y-1">
                  <p className="text-white font-bold text-sm">📱 1 месяц — 90 ₽</p>
                  <p className="text-zinc-500 text-xs">за бота · неограниченно приложений</p>
                </div>
                <div className="text-left py-2 space-y-1">
                  <p className="text-zinc-500">✅ Формы через бота / Sheets / вебхук</p>
                  <p className="text-zinc-500">✅ Кастомные темы и градиенты</p>
                  <p className="text-zinc-500">✅ Публичная ссылка /app/...</p>
                </div>
              </div>
              <a href="https://t.me/dialogengine_bot" target="_blank" rel="noreferrer"
                className="w-full bg-indigo-600 text-white font-black py-4 rounded-xl uppercase tracking-widest text-xs hover:bg-indigo-500 transition-all shadow-xl text-center">
                Купить ключ в TG — 90 ₽
              </a>
            </div>
          )}

          {/* Магазин AI-токенов */}
          {activeSection === 'ai' && (
            <div className="bg-purple-600/10 border border-purple-500/20 rounded-3xl p-6 md:p-8 flex flex-col items-center text-center shadow-xl">
              <Brain className="w-10 h-10 md:w-12 md:h-12 text-purple-500 mb-4" />
              <h3 className="text-lg font-bold text-white mb-2">Купить AI-токены</h3>
              <div className="text-xs text-zinc-400 mb-6 space-y-2">
                <p>Токены расходуются при ответах ИИ-ассистента.</p>
                <div className="py-3 bg-black/40 rounded-xl border border-purple-500/10 mt-2 space-y-1">
                  <p className="text-white font-bold text-sm">500 000 токенов — 30 ₽</p>
                  <p className="text-white font-bold text-sm">1 500 000 токенов — 80 ₽</p>
                  <p className="text-white font-bold text-sm">5 000 000 токенов — 230 ₽</p>
                </div>
              </div>
              <a href="https://t.me/dialogengine_bot" target="_blank" rel="noreferrer"
                className="w-full bg-purple-600 text-white font-black py-4 rounded-xl uppercase tracking-widest text-xs hover:bg-purple-500 transition-all shadow-xl text-center">
                Купить AI-токены в TG
              </a>
            </div>
          )}

          {/* Тех. поддержка */}
          <a href="https://t.me/DialogeEngineSupportBot" target="_blank" rel="noreferrer"
            className="flex items-center gap-4 p-5 bg-emerald-500/10 border border-emerald-500/20 rounded-3xl hover:bg-emerald-500/20 transition-all group">
            <div className="w-10 h-10 bg-emerald-500 rounded-2xl flex items-center justify-center shadow-lg shadow-emerald-500/20">
              <LifeBuoy className="w-5 h-5 text-white animate-pulse" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-white group-hover:text-emerald-400 transition-colors">Тех. поддержка</h4>
              <p className="text-[10px] text-zinc-500">Поможем с настройкой 24/7</p>
            </div>
          </a>

          {/* Канал */}
          <div className="bg-[#121212] border border-zinc-800 rounded-3xl p-6 flex flex-col items-center text-center">
            <div className="w-10 h-10 bg-zinc-800 rounded-full flex items-center justify-center mb-4">
              <MessageCircle className="w-5 h-5 text-sky-400" />
            </div>
            <h4 className="text-sm font-bold text-white mb-1 uppercase tracking-tight">Наше сообщество</h4>
            <p className="text-[11px] text-zinc-500 mb-4">Новости, обновления, промокоды.</p>
            <a href="https://t.me/dialogeengine" target="_blank" rel="noreferrer"
              className="w-full py-3 bg-zinc-800 hover:bg-zinc-700 text-sky-400 text-[11px] font-bold rounded-xl transition-colors flex items-center justify-center gap-2">
              Перейти в канал <ExternalLink className="w-3 h-3" />
            </a>
          </div>

          {/* Реклама */}
          <div className="bg-zinc-900/30 border border-zinc-800/50 rounded-3xl p-6">
            <div className="flex items-center gap-2 mb-4 opacity-50">
              <Megaphone className="w-3 h-3 text-zinc-400" />
              <span className="text-[9px] font-black uppercase tracking-[0.2em] text-zinc-400">Реклама</span>
            </div>
            <a href="https://t.me/NOVA_creators" target="_blank" rel="noreferrer" className="block group">
              <p className="text-xs font-bold text-zinc-200 group-hover:text-blue-400 transition-colors mb-1">NOVA CREATIVE STUDIO</p>
              <p className="text-[10px] text-zinc-500 leading-relaxed mb-3">Крутые аватарки, баннеры, тексты и оформление для твоего канала.</p>
              <span className="text-[10px] text-blue-500 font-bold flex items-center gap-1 group-hover:underline">
                Подробнее <ExternalLink className="w-2.5 h-2.5" />
              </span>
            </a>
          </div>

          {/* Документация */}
<div className="bg-zinc-900/50 border border-zinc-800 rounded-3xl p-6">
  <h4 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-4 flex items-center gap-2">
    <FileText className="w-3 h-3" />Документация
  </h4>
  <div className="space-y-2">
    {/* Внутренние страницы (Обязательно для ЮKassa) */}
    <Link to="/refund" 
      className="flex items-center justify-between p-3 bg-black/30 border border-zinc-800 rounded-xl text-[10px] text-zinc-400 hover:text-white hover:border-zinc-600 transition-all">
      Правила возврата <ExternalLink className="w-3 h-3 opacity-30" />
    </Link>
    
    <Link to="/contacts" 
      className="flex items-center justify-between p-3 bg-black/30 border border-zinc-800 rounded-xl text-[10px] text-zinc-400 hover:text-white hover:border-zinc-600 transition-all">
      Контакты и реквизиты <ExternalLink className="w-3 h-3 opacity-30" />
    </Link>

    {/* Ссылки на GitHub */}
    {[
      { label: 'Соглашение',       file: 'user_agreement.pdf' },
      { label: 'Конфиденциальность', file: 'privacy_policy.pdf' },
    ].map(({ label, file }) => (
      <a key={file} href={`${GITHUB_RAW_URL}/${file}`} target="_blank" rel="noreferrer"
        className="flex items-center justify-between p-3 bg-black/30 border border-zinc-800 rounded-xl text-[10px] text-zinc-400 hover:text-white hover:border-zinc-600 transition-all">
        {label} <ExternalLink className="w-3 h-3 opacity-30" />
      </a>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Profile;
