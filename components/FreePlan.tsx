import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bot, Zap, BarChart2, MessageSquare, ShieldCheck,
  Settings, Play, Square, Loader2, AlertTriangle,
  Crown, ChevronRight, Plus, Trash2, Save, ArrowLeft,
  Info, Star, Lock, Wifi, WifiOff, User
} from 'lucide-react';

const FREE_API = (path: string) => `/api/free${path}`;
const BOTS_API = (path: string) => `/api${path}`;

// ─── types ─────────────────────────────────────────────────────────────────
interface FreeBot {
  id: string;
  name: string;
  status: string;
  config?: any;
  is_free_plan: boolean;
  memory_limit_mb: number;
  ad_enabled: boolean;
}

interface AccountInfo {
  id: string;
  email: string;
  username: string;
  plan: string;
  linked_pro_user_id?: string;
  pro_account?: {
    id: string; email: string; username: string;
    balance: number; license_expires_at?: number;
  };
}

// ─── Account Badge ──────────────────────────────────────────────────────────
const AccountBadge: React.FC<{ userId: string }> = ({ userId }) => {
  const [info, setInfo] = useState<AccountInfo | null>(null);

  useEffect(() => {
    fetch(FREE_API(`/user-info/${userId}`))
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setInfo(d))
      .catch(() => {});
  }, [userId]);

  if (!info) return null;

  const displayAccount = info.pro_account || info;
  const isPro = !!info.pro_account;

  return (
    <div className="fixed top-4 right-4 z-50 group">
      <div className={`flex items-center gap-2 px-3 py-2 rounded-xl border text-xs font-bold transition-all cursor-default
        ${isPro
          ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
          : 'bg-zinc-900 border-zinc-700 text-zinc-400'}`}>
        <div className={`w-1.5 h-1.5 rounded-full ${isPro ? 'bg-amber-400' : 'bg-zinc-500'}`} />
        <User size={11} />
        <span className="uppercase tracking-wider">
          {isPro ? '⭐ PRO' : 'FREE'}
        </span>
        <span className="text-zinc-600 hidden group-hover:inline">
          · {(displayAccount as any).email?.split('@')[0]}
        </span>
      </div>

      {/* Tooltip */}
      <div className="absolute top-full right-0 mt-1 w-56 bg-zinc-900 border border-zinc-800 rounded-xl p-3 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity shadow-xl">
        <div className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2">Аккаунт</div>
        <div className="text-white text-xs font-bold truncate">{info.email}</div>
        {info.pro_account && (
          <>
            <div className="mt-1 text-[10px] text-zinc-500">Привязан к Pro:</div>
            <div className="text-amber-400 text-xs font-bold truncate">{info.pro_account.email}</div>
            <div className="text-zinc-500 text-[10px] mt-1">
              Баланс: {info.pro_account.balance?.toFixed(2)} ₽
            </div>
          </>
        )}
        <div className={`mt-2 text-[10px] font-bold uppercase px-2 py-1 rounded-lg inline-block
          ${isPro ? 'bg-amber-500/20 text-amber-400' : 'bg-zinc-800 text-zinc-500'}`}>
          {isPro ? 'Pro Plan' : 'Free Plan'}
        </div>
      </div>
    </div>
  );
};

// ─── Limit Badge ────────────────────────────────────────────────────────────
const LimitBadge: React.FC<{ current: number; max: number; label: string }> = ({ current, max, label }) => (
  <div className="flex items-center justify-between text-xs mb-1">
    <span className="text-zinc-500 uppercase tracking-widest text-[10px]">{label}</span>
    <span className={`font-bold font-mono ${current >= max ? 'text-red-400' : 'text-zinc-300'}`}>
      {current}/{max}
    </span>
  </div>
);

// ─── Free Bot Editor ─────────────────────────────────────────────────────────
const FreeBotEditor: React.FC<{
  bot: FreeBot;
  userId: string;
  onSave: (updated: FreeBot) => void;
  onBack: () => void;
}> = ({ bot, userId, onSave, onBack }) => {
  const cfg = bot.config || {};
  const [name, setName]         = useState(bot.name);
  const [welcome, setWelcome]   = useState(cfg.welcomeMessage || '');
  const [adminId, setAdminId]   = useState(cfg.adminChatId || '');
  const [buttons, setButtons]   = useState<any[]>(cfg.buttons || []);
  const [triggers, setTriggers] = useState<any[]>(cfg.triggers || []);
  const [saving, setSaving]     = useState(false);
  const [error, setError]       = useState('');

  const maxButtons  = 2;
  const maxTriggers = 2;

  const addButton = () => {
    if (buttons.length >= maxButtons) return;
    setButtons(prev => [...prev, { id: `btn_${Date.now()}`, text: '', type: 'default', response: '' }]);
  };

  const addTrigger = () => {
    if (triggers.length >= maxTriggers) return;
    setTriggers(prev => [...prev, { id: `trg_${Date.now()}`, keyword: '', response: '' }]);
  };

  const removeButton  = (i: number) => setButtons(prev => prev.filter((_, idx) => idx !== i));
  const removeTrigger = (i: number) => setTriggers(prev => prev.filter((_, idx) => idx !== i));

  const updateButton  = (i: number, key: string, val: string) =>
    setButtons(prev => prev.map((b, idx) => idx === i ? { ...b, [key]: val } : b));
  const updateTrigger = (i: number, key: string, val: string) =>
    setTriggers(prev => prev.map((t, idx) => idx === i ? { ...t, [key]: val } : t));

  const handleSave = async () => {
    setSaving(true); setError('');
    try {
      const res = await fetch(FREE_API(`/bots/${bot.id}/config`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId, name,
          config: { welcomeMessage: welcome, adminChatId: adminId },
          buttons, triggers
        })
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Ошибка сохранения');
      }
      onSave({ ...bot, name, config: { ...cfg, welcomeMessage: welcome, adminChatId: adminId, buttons, triggers } });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white p-6 md:p-10">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-4 mb-8">
          <button onClick={onBack} className="p-2 rounded-xl bg-zinc-900 hover:bg-zinc-800 transition-colors">
            <ArrowLeft size={16} />
          </button>
          <div>
            <h1 className="text-lg font-black text-white">{bot.name}</h1>
            <div className="flex items-center gap-2 mt-0.5">
              <div className="px-2 py-0.5 bg-zinc-800 rounded-full text-[10px] text-zinc-400 font-bold uppercase tracking-widest">
                Free Plan
              </div>
              {bot.ad_enabled && (
                <div className="px-2 py-0.5 bg-amber-500/10 rounded-full text-[10px] text-amber-400 font-bold uppercase tracking-widest">
                  📢 Реклама
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Limits info */}
        <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-4 mb-6">
          <div className="flex items-center gap-2 mb-3">
            <Info size={14} className="text-blue-400" />
            <span className="text-[11px] text-zinc-400 font-bold uppercase tracking-widest">Лимиты Free-плана</span>
          </div>
          <LimitBadge current={buttons.length}  max={maxButtons}  label="Кнопки" />
          <LimitBadge current={triggers.length} max={maxTriggers} label="Триггеры" />
          <div className="flex items-center justify-between text-xs mt-1">
            <span className="text-zinc-500 uppercase tracking-widest text-[10px]">Память</span>
            <span className="font-bold text-zinc-300 font-mono">{bot.memory_limit_mb} МБ</span>
          </div>
        </div>

        {/* Main Settings */}
        <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-5 mb-4">
          <h2 className="text-xs font-black text-zinc-300 uppercase tracking-widest mb-4 flex items-center gap-2">
            <Settings size={13} /> Основные настройки
          </h2>
          <div className="space-y-3">
            <div>
              <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1">Название бота</label>
              <input
                value={name} onChange={e => setName(e.target.value)}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                placeholder="Мой бот"
              />
            </div>
            <div>
              <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1">Приветствие (/start)</label>
              <textarea
                value={welcome} onChange={e => setWelcome(e.target.value)}
                rows={3}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 resize-none"
                placeholder="Добро пожаловать!"
              />
              <p className="text-[10px] text-zinc-600 mt-1">
                ℹ️ На free-плане после приветствия показывается реклама
              </p>
            </div>
            <div>
              <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1">Admin Chat ID</label>
              <input
                value={adminId} onChange={e => setAdminId(e.target.value)}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                placeholder="-100123456789"
              />
            </div>
          </div>
        </div>

        {/* Buttons */}
        <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-5 mb-4">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xs font-black text-zinc-300 uppercase tracking-widest flex items-center gap-2">
              <Zap size={13} /> Кнопки ({buttons.length}/{maxButtons})
            </h2>
            <button
              onClick={addButton}
              disabled={buttons.length >= maxButtons}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:bg-zinc-800 disabled:text-zinc-600 rounded-xl text-[11px] font-bold transition-colors"
            >
              <Plus size={12} /> Добавить
            </button>
          </div>
          {buttons.length === 0 && (
            <div className="text-center text-zinc-600 text-xs py-4">Нет кнопок</div>
          )}
          <div className="space-y-3">
            {buttons.map((btn, i) => (
              <div key={btn.id} className="bg-zinc-800/50 border border-zinc-700/50 rounded-xl p-3">
                <div className="flex items-center gap-2 mb-2">
                  <input
                    value={btn.text}
                    onChange={e => updateButton(i, 'text', e.target.value)}
                    className="flex-1 bg-zinc-700 border border-zinc-600 rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none"
                    placeholder="Текст кнопки"
                  />
                  <select
                    value={btn.type || 'default'}
                    onChange={e => updateButton(i, 'type', e.target.value)}
                    className="bg-zinc-700 border border-zinc-600 rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none"
                  >
                    <option value="default">Обычная</option>
                    <option value="ticket">Тикетная</option>
                  </select>
                  <button onClick={() => removeButton(i)} className="p-1.5 text-zinc-500 hover:text-red-400 transition-colors">
                    <Trash2 size={13} />
                  </button>
                </div>
                <textarea
                  value={btn.response || ''}
                  onChange={e => updateButton(i, 'response', e.target.value)}
                  rows={2}
                  className="w-full bg-zinc-700 border border-zinc-600 rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none resize-none"
                  placeholder="Ответ на кнопку..."
                />
              </div>
            ))}
          </div>
        </div>

        {/* Triggers */}
        <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-5 mb-4">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xs font-black text-zinc-300 uppercase tracking-widest flex items-center gap-2">
              <MessageSquare size={13} /> Триггеры ({triggers.length}/{maxTriggers})
            </h2>
            <button
              onClick={addTrigger}
              disabled={triggers.length >= maxTriggers}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:bg-zinc-800 disabled:text-zinc-600 rounded-xl text-[11px] font-bold transition-colors"
            >
              <Plus size={12} /> Добавить
            </button>
          </div>
          {triggers.length === 0 && (
            <div className="text-center text-zinc-600 text-xs py-4">Нет триггеров</div>
          )}
          <div className="space-y-3">
            {triggers.map((trg, i) => (
              <div key={trg.id} className="bg-zinc-800/50 border border-zinc-700/50 rounded-xl p-3">
                <div className="flex items-center gap-2 mb-2">
                  <input
                    value={trg.keyword}
                    onChange={e => updateTrigger(i, 'keyword', e.target.value)}
                    className="flex-1 bg-zinc-700 border border-zinc-600 rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none"
                    placeholder="Ключевое слово"
                  />
                  <button onClick={() => removeTrigger(i)} className="p-1.5 text-zinc-500 hover:text-red-400 transition-colors">
                    <Trash2 size={13} />
                  </button>
                </div>
                <textarea
                  value={trg.response || ''}
                  onChange={e => updateTrigger(i, 'response', e.target.value)}
                  rows={2}
                  className="w-full bg-zinc-700 border border-zinc-600 rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none resize-none"
                  placeholder="Ответ..."
                />
              </div>
            ))}
          </div>
        </div>

        {/* Pro Upgrade Banner */}
        <div className="bg-gradient-to-r from-amber-500/10 to-orange-500/10 border border-amber-500/20 rounded-2xl p-4 mb-6">
          <div className="flex items-center gap-3">
            <Crown size={20} className="text-amber-400 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-xs font-black text-amber-300 uppercase tracking-widest mb-1">
                Разблокировать Pro
              </div>
              <div className="text-[11px] text-zinc-400">
                Неограниченные кнопки, триггеры, ИИ, мини-приложения, рассылки, без рекламы
              </div>
            </div>
            <a href="/auth" className="px-3 py-2 bg-amber-500 hover:bg-amber-400 rounded-xl text-[11px] font-black text-black uppercase tracking-widest transition-colors shrink-0">
              Pro →
            </a>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-xl mb-4 text-red-400 text-xs">
            <AlertTriangle size={14} /> {error}
          </div>
        )}

        {/* Save */}
        <button
          onClick={handleSave}
          disabled={saving}
          className="w-full py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-zinc-800 rounded-2xl text-sm font-black uppercase tracking-widest transition-colors flex items-center justify-center gap-2"
        >
          {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
          {saving ? 'Сохранение...' : 'Сохранить'}
        </button>
      </div>
    </div>
  );
};

// ─── Analytics Panel ─────────────────────────────────────────────────────────
const FreeBotAnalytics: React.FC<{ bot: FreeBot; userId: string; onBack: () => void }> = ({ bot, userId, onBack }) => {
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(FREE_API(`/bots/${bot.id}/stats?user_id=${userId}`))
      .then(r => r.ok ? r.json() : null)
      .then(d => { setStats(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [bot.id, userId]);

  const s = stats?.stats || {};
  const statCards = [
    { label: 'Всего сообщений', value: s.totalMessages || 0, color: 'text-blue-400' },
    { label: 'Входящих сегодня', value: s.incomingToday || 0, color: 'text-green-400' },
    { label: 'Исходящих сегодня', value: s.outgoingToday || 0, color: 'text-amber-400' },
    { label: 'Активных 24ч', value: s.activeUsers24h || 0, color: 'text-purple-400' },
    { label: 'Пользователей', value: stats?.users_count || 0, color: 'text-cyan-400' },
    { label: 'Заблокировано', value: s.bannedCount || 0, color: 'text-red-400' },
  ];

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white p-6 md:p-10">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center gap-4 mb-8">
          <button onClick={onBack} className="p-2 rounded-xl bg-zinc-900 hover:bg-zinc-800 transition-colors">
            <ArrowLeft size={16} />
          </button>
          <div>
            <h1 className="text-lg font-black text-white">Аналитика</h1>
            <div className="text-xs text-zinc-500">{bot.name}</div>
          </div>
        </div>

        {loading ? (
          <div className="flex justify-center py-20"><Loader2 size={24} className="animate-spin text-zinc-600" /></div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {statCards.map(card => (
              <div key={card.label} className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-4">
                <div className={`text-2xl font-black font-mono ${card.color}`}>{card.value}</div>
                <div className="text-[11px] text-zinc-500 mt-1">{card.label}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

// ─── Main FreePlan Page ───────────────────────────────────────────────────────
const FreePlan: React.FC = () => {
  const navigate = useNavigate();

  const [userId, setUserId]     = useState<string | null>(null);
  const [bots, setBots]         = useState<FreeBot[]>([]);
  const [loading, setLoading]   = useState(true);
  const [creating, setCreating] = useState(false);
  const [newBotName, setNewBotName]   = useState('');
  const [newBotToken, setNewBotToken] = useState('');
  const [showCreate, setShowCreate]   = useState(false);
  const [createError, setCreateError] = useState('');

  const [view, setView] = useState<'list' | 'editor' | 'analytics'>('list');
  const [selectedBot, setSelectedBot] = useState<FreeBot | null>(null);

  // Attempt to get userId from localStorage (shared session)
  useEffect(() => {
    const raw = localStorage.getItem('active_session_user');
    if (raw) {
      try {
        const u = JSON.parse(raw);
        if (u?.id) {
          setUserId(u.id);
          loadBots(u.id);
          return;
        }
      } catch {}
    }
    setLoading(false);
  }, []);

  const loadBots = async (uid: string) => {
    setLoading(true);
    try {
      const r = await fetch(FREE_API(`/bots/${uid}`));
      if (r.ok) setBots(await r.json());
    } catch {}
    setLoading(false);
  };

  const handleCreate = async () => {
    if (!userId || !newBotName.trim() || !newBotToken.trim()) return;
    setCreating(true); setCreateError('');
    try {
      const r = await fetch(FREE_API('/bots/create'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, name: newBotName.trim(), token: newBotToken.trim() })
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || 'Ошибка создания');
      setBots(prev => [...prev, data]);
      setShowCreate(false); setNewBotName(''); setNewBotToken('');
    } catch (e: any) {
      setCreateError(e.message);
    } finally {
      setCreating(false);
    }
  };

  const startBot = async (botId: string) => {
    await fetch(BOTS_API(`/bots/${botId}/start`), { method: 'POST' });
    setBots(prev => prev.map(b => b.id === botId ? { ...b, status: 'RUNNING' } : b));
  };

  const stopBot = async (botId: string) => {
    await fetch(BOTS_API(`/bots/${botId}/stop`), { method: 'POST' });
    setBots(prev => prev.map(b => b.id === botId ? { ...b, status: 'IDLE' } : b));
  };

  // Sub-views
  if (view === 'editor' && selectedBot && userId) {
    return <FreeBotEditor
      bot={selectedBot} userId={userId}
      onSave={updated => { setBots(prev => prev.map(b => b.id === updated.id ? updated : b)); setView('list'); }}
      onBack={() => setView('list')}
    />;
  }
  if (view === 'analytics' && selectedBot && userId) {
    return <FreeBotAnalytics bot={selectedBot} userId={userId} onBack={() => setView('list')} />;
  }

  if (!userId) {
    return (
      <div className="min-h-screen bg-[#0a0a0a] flex flex-col items-center justify-center p-6 text-center">
        <Bot size={48} className="text-zinc-700 mb-6" />
        <h1 className="text-2xl font-black text-white mb-2">Войдите в аккаунт</h1>
        <p className="text-zinc-500 text-sm mb-8">Для доступа к бесплатному плану необходима авторизация</p>
        <button onClick={() => navigate('/auth')}
          className="px-8 py-3 bg-blue-600 hover:bg-blue-700 rounded-2xl font-black text-sm uppercase tracking-widest transition-colors">
          Войти
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      {userId && <AccountBadge userId={userId} />}

      <div className="max-w-2xl mx-auto px-4 py-10">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-1">
            <button onClick={() => navigate('/')} className="text-zinc-600 hover:text-zinc-400 transition-colors">
              <ArrowLeft size={16} />
            </button>
            <div className="px-2 py-0.5 bg-zinc-800 rounded-full text-[10px] text-zinc-400 font-bold uppercase tracking-widest">
              BotEngine Free
            </div>
          </div>
          <h1 className="text-3xl font-black text-white mt-3">Бесплатный план</h1>
          <p className="text-zinc-500 text-sm mt-1">Создавайте ботов бесплатно с базовым функционалом</p>
        </div>

        {/* Features Grid */}
        <div className="grid grid-cols-2 gap-3 mb-8">
          {[
            { icon: <MessageSquare size={15} />, label: '2 кнопки', sub: 'Обычная или тикетная', ok: true },
            { icon: <Zap size={15} />, label: '2 триггера', sub: 'По ключевым словам', ok: true },
            { icon: <BarChart2 size={15} />, label: 'Аналитика', sub: 'Полная статистика', ok: true },
            { icon: <ShieldCheck size={15} />, label: 'Поддержка', sub: 'Ping-pong, тикеты', ok: true },
            { icon: <Lock size={15} />, label: 'ИИ-ответы', sub: 'Только Pro', ok: false },
            { icon: <Lock size={15} />, label: 'Мини-приложения', sub: 'Только Pro', ok: false },
          ].map((f, i) => (
            <div key={i} className={`p-4 rounded-2xl border transition-all
              ${f.ok
                ? 'bg-zinc-900/60 border-zinc-800'
                : 'bg-zinc-900/20 border-zinc-800/40 opacity-50'}`}>
              <div className={`mb-2 ${f.ok ? 'text-blue-400' : 'text-zinc-600'}`}>{f.icon}</div>
              <div className={`text-xs font-bold ${f.ok ? 'text-white' : 'text-zinc-600'}`}>{f.label}</div>
              <div className="text-[10px] text-zinc-600 mt-0.5">{f.sub}</div>
            </div>
          ))}
        </div>

        {/* Bots List */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-black text-zinc-300 uppercase tracking-widest">Мои боты</h2>
            {bots.length === 0 && (
              <button
                onClick={() => setShowCreate(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded-xl text-[11px] font-bold transition-colors"
              >
                <Plus size={12} /> Создать
              </button>
            )}
          </div>

          {loading && <div className="flex justify-center py-10"><Loader2 size={20} className="animate-spin text-zinc-600" /></div>}

          {!loading && bots.length === 0 && !showCreate && (
            <div className="text-center py-12 bg-zinc-900/40 border border-zinc-800 rounded-2xl">
              <Bot size={32} className="text-zinc-700 mx-auto mb-3" />
              <p className="text-zinc-500 text-sm mb-4">Ботов нет. Создайте первый!</p>
              <button
                onClick={() => setShowCreate(true)}
                className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 rounded-xl text-sm font-bold transition-colors"
              >
                Создать бота
              </button>
            </div>
          )}

          {/* Create form */}
          {showCreate && (
            <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-5 mb-4">
              <h3 className="text-xs font-black text-zinc-300 uppercase tracking-widest mb-4">Новый бот</h3>
              <div className="space-y-3">
                <div>
                  <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1">Название</label>
                  <input
                    value={newBotName} onChange={e => setNewBotName(e.target.value)}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                    placeholder="Мой бот"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1">
                    Токен (@BotFather)
                  </label>
                  <input
                    value={newBotToken} onChange={e => setNewBotToken(e.target.value)}
                    type="password"
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 font-mono"
                    placeholder="123456:ABC..."
                  />
                </div>
                {createError && (
                  <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-xs">
                    <AlertTriangle size={13} /> {createError}
                  </div>
                )}
                <div className="flex gap-2">
                  <button onClick={() => { setShowCreate(false); setCreateError(''); }}
                    className="flex-1 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-xl text-xs font-bold transition-colors">
                    Отмена
                  </button>
                  <button onClick={handleCreate} disabled={creating}
                    className="flex-1 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-zinc-800 rounded-xl text-xs font-bold transition-colors flex items-center justify-center gap-2">
                    {creating ? <Loader2 size={13} className="animate-spin" /> : null}
                    {creating ? 'Создание...' : 'Создать'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Bots */}
          <div className="space-y-3">
            {bots.map(bot => (
              <div key={bot.id} className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-xl flex items-center justify-center
                      ${bot.status === 'RUNNING' ? 'bg-green-500/20' : 'bg-zinc-800'}`}>
                      <Bot size={15} className={bot.status === 'RUNNING' ? 'text-green-400' : 'text-zinc-500'} />
                    </div>
                    <div>
                      <div className="text-sm font-bold text-white">{bot.name}</div>
                      <div className={`text-[10px] font-bold uppercase tracking-widest
                        ${bot.status === 'RUNNING' ? 'text-green-400' : 'text-zinc-600'}`}>
                        {bot.status === 'RUNNING' ? '● Активен' : '○ Остановлен'}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => bot.status === 'RUNNING' ? stopBot(bot.id) : startBot(bot.id)}
                      className={`p-2 rounded-xl transition-colors
                        ${bot.status === 'RUNNING'
                          ? 'bg-red-500/10 text-red-400 hover:bg-red-500/20'
                          : 'bg-green-500/10 text-green-400 hover:bg-green-500/20'}`}
                    >
                      {bot.status === 'RUNNING' ? <Square size={14} /> : <Play size={14} />}
                    </button>
                  </div>
                </div>

                <div className="flex gap-2">
                  <button
                    onClick={() => { setSelectedBot(bot); setView('editor'); }}
                    className="flex-1 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-xl text-[11px] font-bold transition-colors flex items-center justify-center gap-1.5"
                  >
                    <Settings size={12} /> Редактор
                  </button>
                  <button
                    onClick={() => { setSelectedBot(bot); setView('analytics'); }}
                    className="flex-1 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-xl text-[11px] font-bold transition-colors flex items-center justify-center gap-1.5"
                  >
                    <BarChart2 size={12} /> Аналитика
                  </button>
                </div>

                {bot.ad_enabled && (
                  <div className="mt-2 flex items-center gap-1.5 text-[10px] text-amber-500/70">
                    <AlertTriangle size={11} />
                    <span>Реклама показывается при каждом /start</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Upgrade CTA */}
        <div className="bg-gradient-to-br from-zinc-900 to-zinc-900/60 border border-zinc-700 rounded-2xl p-6 text-center">
          <Star size={24} className="text-amber-400 mx-auto mb-3" />
          <h3 className="font-black text-white mb-1">Нужно больше?</h3>
          <p className="text-zinc-500 text-xs mb-4">
            Неограниченные боты, ИИ, рассылки, мини-приложения, без рекламы
          </p>
          <button onClick={() => navigate('/auth')}
            className="px-6 py-2.5 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 rounded-xl text-sm font-black text-black transition-all">
            Перейти на Pro →
          </button>
        </div>
      </div>
    </div>
  );
};

export default FreePlan;
