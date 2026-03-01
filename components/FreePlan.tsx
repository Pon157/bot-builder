import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bot, Zap, BarChart2, MessageSquare, ShieldCheck,
  Settings, Play, Square, Loader2, AlertTriangle,
  Crown, Plus, Trash2, Save, ArrowLeft,
  Info, Wifi, WifiOff, User, Image, Send, ShieldAlert,
  CheckSquare, Square as SquareIcon, Lock, ToggleLeft, ToggleRight,
  Users, Hash, Eye, EyeOff, Upload, RefreshCw
} from 'lucide-react';

const FREE_API  = (path: string) => `/api/free${path}`;
const BOTS_API  = (path: string) => `/api${path}`;

// ─── types ────────────────────────────────────────────────────────────────────
interface FreeBot {
  id: string;
  name: string;
  status: string;
  token?: string;
  config?: any;
  is_free_plan: boolean;
  memory_limit_mb: number;
  ad_enabled: boolean;
}

interface AccountInfo {
  id: string; email: string; username: string; plan: string;
  linked_pro_user_id?: string;
  pro_account?: { id: string; email: string; username: string; balance: number; license_expires_at?: number; };
}

// ─── Account Badge ────────────────────────────────────────────────────────────
const AccountBadge: React.FC<{ userId: string }> = ({ userId }) => {
  const [info, setInfo] = useState<AccountInfo | null>(null);
  useEffect(() => {
    fetch(FREE_API(`/user-info/${userId}`)).then(r => r.ok ? r.json() : null).then(d => d && setInfo(d)).catch(() => {});
  }, [userId]);
  if (!info) return null;
  const isPro = !!info.pro_account;
  return (
    <div className="fixed top-4 right-4 z-50 group">
      <div className={`flex items-center gap-2 px-3 py-2 rounded-xl border text-xs font-bold transition-all cursor-default ${isPro ? 'bg-amber-500/10 border-amber-500/30 text-amber-400' : 'bg-zinc-900 border-zinc-700 text-zinc-400'}`}>
        <div className={`w-1.5 h-1.5 rounded-full ${isPro ? 'bg-amber-400' : 'bg-zinc-500'}`} />
        <User size={11} />
        <span className="uppercase tracking-wider">{isPro ? '⭐ PRO' : 'FREE'}</span>
        <span className="text-zinc-600 hidden group-hover:inline">· {info.email?.split('@')[0]}</span>
      </div>
      <div className="absolute top-full right-0 mt-1 w-56 bg-zinc-900 border border-zinc-800 rounded-xl p-3 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity shadow-xl">
        <div className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2">Аккаунт</div>
        <div className="text-white text-xs font-bold truncate">{info.email}</div>
        {info.pro_account && (<>
          <div className="mt-1 text-[10px] text-zinc-500">Привязан к Pro:</div>
          <div className="text-amber-400 text-xs font-bold truncate">{info.pro_account.email}</div>
          <div className="text-zinc-500 text-[10px] mt-1">Баланс: {info.pro_account.balance?.toFixed(2)} ₽</div>
        </>)}
        <div className={`mt-2 text-[10px] font-bold uppercase px-2 py-1 rounded-lg inline-block ${isPro ? 'bg-amber-500/20 text-amber-400' : 'bg-zinc-800 text-zinc-500'}`}>
          {isPro ? 'Pro Plan' : 'Free Plan'}
        </div>
      </div>
    </div>
  );
};

// ─── Toggle ────────────────────────────────────────────────────────────────────
const Toggle: React.FC<{ value: boolean; onChange: (v: boolean) => void; label: string; sub?: string; color?: string }> = ({ value, onChange, label, sub, color = 'blue' }) => {
  const colors: Record<string, string> = {
    blue:    'bg-blue-500/10 border-blue-500/30 text-blue-400',
    emerald: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
    amber:   'bg-amber-500/10 border-amber-500/30 text-amber-400',
    zinc:    'bg-zinc-800 border-zinc-700 text-white',
  };
  return (
    <button type="button" onClick={() => onChange(!value)}
      className={`w-full flex items-center justify-between p-4 rounded-xl border transition-all text-left ${value ? (colors[color] || colors.blue) : 'bg-black border-zinc-800 text-zinc-600'}`}>
      <div>
        <p className="text-xs font-bold">{label}</p>
        {sub && <p className="text-[9px] uppercase opacity-60 mt-0.5">{sub}</p>}
      </div>
      {value ? <ToggleRight className="w-5 h-5 flex-shrink-0" /> : <ToggleLeft className="w-5 h-5 flex-shrink-0" />}
    </button>
  );
};

// ─── LimitBadge ────────────────────────────────────────────────────────────────
const LimitBadge: React.FC<{ current: number; max: number; label: string }> = ({ current, max, label }) => (
  <div className="flex items-center justify-between text-xs mb-1">
    <span className="text-zinc-500 uppercase tracking-widest text-[10px]">{label}</span>
    <span className={`font-bold font-mono ${current >= max ? 'text-red-400' : 'text-zinc-300'}`}>{current}/{max}</span>
  </div>
);

// ─── Section ────────────────────────────────────────────────────────────────────
const Section: React.FC<{ title: string; icon: React.ReactNode; children: React.ReactNode }> = ({ title, icon, children }) => (
  <section className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-5 space-y-4">
    <h2 className="text-xs font-black text-zinc-300 uppercase tracking-widest flex items-center gap-2">{icon}{title}</h2>
    {children}
  </section>
);

// ════════════════════════════════════════════════════════════════════════════════
// FREE BOT EDITOR — полные настройки как в BotEditor
// ════════════════════════════════════════════════════════════════════════════════
const FreeBotEditor: React.FC<{
  bot: FreeBot; userId: string;
  onSave: (updated: FreeBot) => void; onBack: () => void;
}> = ({ bot, userId, onSave, onBack }) => {
  const cfg       = bot.config || {};
  const rawSettings = cfg.settings || {};

  const defaultSettings = {
    useTopics: false, topicPerRequest: false, anonymousTopics: false,
    forwardAll: false, rateLimit: 1, autoBanThreshold: 3,
    showHeaderId: true, showHeaderName: true, showHeaderUsername: true,
    firstMessageHeader: '🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>',
    ticketMessageHeader: '🆘 <b>ЗАЯВКА [{btn}]:</b>',
    commonMessageHeader: '📩 <b>СООБЩЕНИЕ:</b>',
  };
  const settings = { ...defaultSettings, ...rawSettings };

  // ── state ───────────────────────────────────────────────────────────────────
  const [name,         setName]         = useState(bot.name);
  const [token,        setToken]        = useState(bot.token || cfg.token || '');
  const [welcome,      setWelcome]      = useState(cfg.welcomeMessage || '');
  const [welcomePhoto, setWelcomePhoto] = useState(cfg.welcomePhoto   || '');
  const [adminId,      setAdminId]      = useState(cfg.adminChatId    || '');
  const [buttons,      setButtons]      = useState<any[]>(cfg.buttons  || []);
  const [triggers,     setTriggers]     = useState<any[]>(cfg.triggers || []);
  const [stg,          setStg]          = useState(settings);
  const [showToken,    setShowToken]    = useState(false);
  const [saving,       setSaving]       = useState(false);
  const [error,        setError]        = useState('');
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const MAX_BUTTONS  = 2;
  const MAX_TRIGGERS = 2;

  const updateStg = (key: string, val: any) => setStg(prev => ({ ...prev, [key]: val }));

  // ── Photo upload ─────────────────────────────────────────────────────────────
  const handlePhotoUpload = async (file: File) => {
    setUploadingPhoto(true);
    try {
      const fd = new FormData(); fd.append('file', file);
      const r  = await fetch('/api/upload', { method: 'POST', body: fd });
      if (!r.ok) throw new Error('Ошибка загрузки');
      const d  = await r.json();
      setWelcomePhoto(d.url || d.path || '');
    } catch { alert('Ошибка загрузки фото'); }
    finally   { setUploadingPhoto(false); }
  };

  // ── Save ─────────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    setSaving(true); setError('');
    try {
      // Если токен изменился — обновляем его отдельно
      if (token && token !== (bot.token || cfg.token || '')) {
        const tr = await fetch(`/api/bots/${bot.id}/token`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token })
        });
        if (!tr.ok) console.warn('Token update failed');
      }

      const res = await fetch(FREE_API(`/bots/${bot.id}/config`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId, name,
          config: {
            welcomeMessage: welcome,
            welcomePhoto,
            adminChatId:  adminId,
            settings:     stg,
          },
          buttons, triggers
        })
      });
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail || 'Ошибка сохранения'); }
      const updated = await res.json();
      onSave({
        ...bot, name, token,
        config: { ...cfg, welcomeMessage: welcome, welcomePhoto, adminChatId: adminId, settings: stg, buttons, triggers }
      });
    } catch (e: any) { setError(e.message); }
    finally { setSaving(false); }
  };

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      <div className="max-w-2xl mx-auto p-6 md:p-10 space-y-5 pb-24">
        {/* Header */}
        <div className="flex items-center gap-4 mb-2">
          <button onClick={onBack} className="p-2 rounded-xl bg-zinc-900 hover:bg-zinc-800 transition-colors"><ArrowLeft size={16} /></button>
          <div>
            <h1 className="text-lg font-black text-white">{bot.name}</h1>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="px-2 py-0.5 bg-zinc-800 rounded-full text-[10px] text-zinc-400 font-bold uppercase tracking-widest">Free Plan</span>
              {bot.ad_enabled && <span className="px-2 py-0.5 bg-amber-500/10 rounded-full text-[10px] text-amber-400 font-bold uppercase tracking-widest">📢 Реклама</span>}
            </div>
          </div>
        </div>

        {/* Limits strip */}
        <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-4">
          <div className="flex items-center gap-2 mb-3"><Info size={13} className="text-blue-400" /><span className="text-[11px] text-zinc-400 font-bold uppercase tracking-widest">Лимиты Free-плана</span></div>
          <LimitBadge current={buttons.length}  max={MAX_BUTTONS}  label="Кнопки" />
          <LimitBadge current={triggers.length} max={MAX_TRIGGERS} label="Триггеры" />
          <div className="flex items-center justify-between text-xs mt-1">
            <span className="text-zinc-500 uppercase tracking-widest text-[10px]">Память</span>
            <span className="font-bold text-zinc-300 font-mono">{bot.memory_limit_mb} МБ</span>
          </div>
        </div>

        {/* ── Основные настройки ─────────────────────────────────────────────── */}
        <Section title="Основные настройки" icon={<Settings size={13} className="text-blue-400" />}>
          {/* Название */}
          <label className="block">
            <span className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5">Название бота</span>
            <input value={name} onChange={e => setName(e.target.value)}
              className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500 transition-colors"
              placeholder="Мой бот" />
          </label>

          {/* Токен */}
          <label className="block">
            <span className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5">Telegram Bot Token</span>
            <div className="relative">
              <input type={showToken ? 'text' : 'password'} value={token} onChange={e => setToken(e.target.value)}
                className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-2.5 pr-10 text-sm text-white font-mono focus:outline-none focus:border-blue-500 transition-colors"
                placeholder="Токен от @BotFather" />
              <button type="button" onClick={() => setShowToken(!showToken)} className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-600 hover:text-zinc-400 transition-colors">
                {showToken ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </label>

          {/* Admin Chat ID */}
          <label className="block">
            <span className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5 flex items-center gap-1.5"><Users size={10} className="text-amber-400" />ID группы / форума администраторов</span>
            <input value={adminId} onChange={e => setAdminId(e.target.value)}
              className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-amber-500 transition-colors"
              placeholder="-100123456789" />
          </label>
        </Section>

        {/* ── Приветствие ───────────────────────────────────────────────────── */}
        <Section title="Приветствие (/start)" icon={<MessageSquare size={13} className="text-emerald-400" />}>
          <label className="block">
            <span className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5">Текст приветствия</span>
            <textarea value={welcome} onChange={e => setWelcome(e.target.value)} rows={3}
              className="w-full bg-black border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-emerald-500 transition-colors resize-none"
              placeholder="Добро пожаловать!" />
            <p className="text-[10px] text-amber-500/70 mt-1.5">ℹ️ На free-плане после приветствия автоматически показывается реклама</p>
          </label>

          {/* Фото к /start */}
          <div>
            <span className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5 flex items-center gap-1.5"><Image size={10} className="text-blue-400" />Фото к /start (опционально)</span>
            <div className="flex gap-2">
              <input value={welcomePhoto} onChange={e => setWelcomePhoto(e.target.value)}
                className="flex-1 bg-black border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500 transition-colors"
                placeholder="https://... или загрузите файл" />
              <button type="button" onClick={() => fileRef.current?.click()} disabled={uploadingPhoto}
                className="px-3 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-xl text-zinc-400 hover:text-white transition-all disabled:opacity-50">
                {uploadingPhoto ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              </button>
              <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) handlePhotoUpload(f); }} />
            </div>
            {welcomePhoto && (
              <div className="mt-3 relative inline-block">
                <img src={welcomePhoto} alt="preview"
                  className="h-28 rounded-xl object-cover border border-zinc-800"
                  onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }} />
                <button type="button" onClick={() => setWelcomePhoto('')}
                  className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 rounded-full text-white text-xs flex items-center justify-center hover:bg-red-400 transition-colors">✕</button>
                <div className="absolute bottom-2 left-2 bg-black/60 px-2 py-0.5 rounded text-[8px] text-white uppercase font-bold backdrop-blur-sm">Превью</div>
              </div>
            )}

            {/* Live preview */}
            {(welcome || welcomePhoto) && (
              <div className="mt-3 bg-black/50 border border-zinc-800 rounded-xl p-3">
                <p className="text-[8px] text-zinc-600 uppercase font-black mb-2 flex items-center gap-1.5"><Bot size={9} />Превью в Telegram</p>
                <div className="bg-zinc-900 rounded-2xl rounded-bl-sm p-3 max-w-[85%]">
                  {welcomePhoto && <div className="w-full h-16 bg-zinc-800 rounded-xl mb-2 overflow-hidden"><img src={welcomePhoto} className="w-full h-full object-cover" alt="" onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }} /></div>}
                  <p className="text-[10px] text-zinc-300 leading-relaxed whitespace-pre-wrap">{(welcome || 'Привет!').slice(0, 100)}{welcome.length > 100 ? '…' : ''}</p>
                </div>
                <p className="text-[7px] text-zinc-700 uppercase mt-2">↑ Далее будет показана реклама (free)</p>
              </div>
            )}
          </div>
        </Section>

        {/* ── Режим пересылки ──────────────────────────────────────────────── */}
        <Section title="Режим пересылки" icon={<Send size={13} className="text-blue-400" />}>
          <Toggle value={!!stg.forwardAll} onChange={v => updateStg('forwardAll', v)}
            label="Пересылать все сообщения в чат"
            sub="Без создания тикета — всё идёт в админ-чат"
            color="blue" />
          {stg.forwardAll && (
            <p className="text-[10px] text-blue-300/60 bg-blue-500/5 border border-blue-500/10 rounded-xl p-3 leading-relaxed">
              💡 В этом режиме все сообщения пользователей сразу пересылаются в админ-чат. Тикетные кнопки можно не добавлять.
            </p>
          )}
        </Section>

        {/* ── Форум / Темы ─────────────────────────────────────────────────── */}
        <Section title="Форум (Темы)" icon={<ShieldAlert size={13} className="text-emerald-400" />}>
          <div className="space-y-2">
            {[
              { k: 'useTopics',       label: 'Использовать Темы (Forum)', sub: 'Для супергрупп с включёнными темами', color: 'emerald' },
              { k: 'topicPerRequest', label: 'Новая ветка на каждый тикет', sub: 'Ticket System Mode', color: 'blue' },
              { k: 'anonymousTopics', label: 'Анонимные ID (Anon ID)', sub: 'Хешировать данные пользователей', color: 'zinc' },
            ].map(f => (
              <Toggle key={f.k} value={!!(stg as any)[f.k]} onChange={v => updateStg(f.k, v)}
                label={f.label} sub={f.sub} color={f.color} />
            ))}
          </div>
          {stg.useTopics && (
            <p className="text-[10px] text-emerald-300/60 bg-emerald-500/5 border border-emerald-500/10 rounded-xl p-3 leading-relaxed">
              💡 Убедитесь, что бот является администратором форум-группы с правами управления темами.
            </p>
          )}
        </Section>

        {/* ── Заголовки сообщений ─────────────────────────────────────────── */}
        <Section title="Заголовки сообщений" icon={<Hash size={13} className="text-zinc-400" />}>
          <div className="space-y-3">
            {[
              { k: 'firstMessageHeader',  ph: '🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>', label: 'Первое сообщение' },
              { k: 'ticketMessageHeader', ph: '🆘 <b>ЗАЯВКА [{btn}]:</b>',    label: 'Тикет / заявка' },
              { k: 'commonMessageHeader', ph: '📩 <b>СООБЩЕНИЕ:</b>',          label: 'Обычное сообщение' },
            ].map(f => (
              <label key={f.k} className="block">
                <span className="text-[9px] text-zinc-500 uppercase tracking-widest block mb-1">{f.label}</span>
                <input value={(stg as any)[f.k] || ''} onChange={e => updateStg(f.k, e.target.value)}
                  className="w-full bg-black border border-zinc-800 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-zinc-600 transition-colors"
                  placeholder={f.ph} />
              </label>
            ))}
          </div>
          <div className="grid grid-cols-3 gap-2 pt-1">
            {[{ k: 'showHeaderName', l: 'Имя' }, { k: 'showHeaderUsername', l: 'Юзер' }, { k: 'showHeaderId', l: 'ID' }].map(f => (
              <button key={f.k} type="button" onClick={() => updateStg(f.k, !(stg as any)[f.k])}
                className={`flex items-center justify-between p-3 rounded-xl border text-[9px] font-bold uppercase transition-all ${(stg as any)[f.k] ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-black border-zinc-800 text-zinc-600'}`}>
                {f.l} {(stg as any)[f.k] ? <CheckSquare className="w-3 h-3" /> : <SquareIcon className="w-3 h-3" />}
              </button>
            ))}
          </div>
        </Section>

        {/* ── Безопасность ─────────────────────────────────────────────────── */}
        <Section title="Безопасность и Анти-Флуд" icon={<Lock size={13} className="text-rose-400" />}>
          <div className="flex items-center justify-between p-4 rounded-xl bg-black border border-zinc-800">
            <div><p className="text-xs font-bold text-white">Интервал анти-спама</p><p className="text-[9px] text-zinc-500 uppercase">Сек. между сообщениями</p></div>
            <input type="number" step="0.5" min="0"
              className="w-16 bg-zinc-900 border border-zinc-700 rounded-lg p-2 text-center text-xs text-white focus:outline-none"
              value={stg.rateLimit} onChange={e => updateStg('rateLimit', parseFloat(e.target.value) || 0)} />
          </div>
          <div className="flex items-center justify-between p-4 rounded-xl bg-black border border-zinc-800">
            <div><p className="text-xs font-bold text-white">Лимит предупреждений</p><p className="text-[9px] text-zinc-500 uppercase">Варнов до авто-бана</p></div>
            <input type="number" min="0"
              className="w-16 bg-zinc-900 border border-zinc-700 rounded-lg p-2 text-center text-xs text-white focus:outline-none"
              value={stg.autoBanThreshold} onChange={e => updateStg('autoBanThreshold', parseInt(e.target.value) || 0)} />
          </div>
        </Section>

        {/* ── Кнопки ───────────────────────────────────────────────────────── */}
        <Section title={`Кнопки (${buttons.length}/${MAX_BUTTONS})`} icon={<Zap size={13} className="text-blue-400" />}>
          {buttons.length === 0 && <p className="text-center text-zinc-600 text-xs py-2">Нет кнопок</p>}
          <div className="space-y-3">
            {buttons.map((btn, i) => (
              <div key={btn.id || i} className="bg-black/60 border border-zinc-800 rounded-xl p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <input value={btn.text || ''} onChange={e => setButtons(prev => prev.map((b, idx) => idx === i ? { ...b, text: e.target.value } : b))}
                    className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none" placeholder="Текст кнопки" />
                  <select value={btn.type || 'default'} onChange={e => setButtons(prev => prev.map((b, idx) => idx === i ? { ...b, type: e.target.value } : b))}
                    className="bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-2 text-xs text-white focus:outline-none">
                    <option value="default">Обычная</option>
                    <option value="ticket">Тикетная</option>
                  </select>
                  <button type="button" onClick={() => setButtons(prev => prev.filter((_, idx) => idx !== i))} className="p-1.5 text-zinc-600 hover:text-red-400 transition-colors"><Trash2 size={13} /></button>
                </div>
                <textarea value={btn.response || ''} onChange={e => setButtons(prev => prev.map((b, idx) => idx === i ? { ...b, response: e.target.value } : b))} rows={2}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none resize-none" placeholder="Ответ на кнопку..." />
              </div>
            ))}
          </div>
          <button type="button" onClick={() => { if (buttons.length >= MAX_BUTTONS) return; setButtons(prev => [...prev, { id: `btn_${Date.now()}`, text: '', type: 'default', response: '' }]); }}
            disabled={buttons.length >= MAX_BUTTONS}
            className="w-full py-2.5 rounded-xl border border-dashed border-blue-500/30 text-blue-400 text-[11px] font-bold uppercase tracking-wider hover:bg-blue-500/5 disabled:opacity-30 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-1.5">
            <Plus size={12} /> Добавить кнопку
          </button>
        </Section>

        {/* ── Триггеры ─────────────────────────────────────────────────────── */}
        <Section title={`Триггеры (${triggers.length}/${MAX_TRIGGERS})`} icon={<MessageSquare size={13} className="text-purple-400" />}>
          {triggers.length === 0 && <p className="text-center text-zinc-600 text-xs py-2">Нет триггеров</p>}
          <div className="space-y-3">
            {triggers.map((trg, i) => (
              <div key={trg.id || i} className="bg-black/60 border border-zinc-800 rounded-xl p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <input value={trg.keyword || ''} onChange={e => setTriggers(prev => prev.map((t, idx) => idx === i ? { ...t, keyword: e.target.value } : t))}
                    className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none" placeholder="Ключевое слово" />
                  <button type="button" onClick={() => setTriggers(prev => prev.filter((_, idx) => idx !== i))} className="p-1.5 text-zinc-600 hover:text-red-400 transition-colors"><Trash2 size={13} /></button>
                </div>
                <textarea value={trg.response || ''} onChange={e => setTriggers(prev => prev.map((t, idx) => idx === i ? { ...t, response: e.target.value } : t))} rows={2}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none resize-none" placeholder="Ответ на триггер..." />
              </div>
            ))}
          </div>
          <button type="button" onClick={() => { if (triggers.length >= MAX_TRIGGERS) return; setTriggers(prev => [...prev, { id: `trg_${Date.now()}`, keyword: '', response: '' }]); }}
            disabled={triggers.length >= MAX_TRIGGERS}
            className="w-full py-2.5 rounded-xl border border-dashed border-purple-500/30 text-purple-400 text-[11px] font-bold uppercase tracking-wider hover:bg-purple-500/5 disabled:opacity-30 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-1.5">
            <Plus size={12} /> Добавить триггер
          </button>
        </Section>

        {/* Pro CTA */}
        <div className="bg-gradient-to-r from-amber-500/10 to-orange-500/10 border border-amber-500/20 rounded-2xl p-4">
          <div className="flex items-center gap-3">
            <Crown size={20} className="text-amber-400 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-xs font-black text-amber-300 uppercase tracking-widest mb-0.5">Разблокировать Pro</div>
              <div className="text-[11px] text-zinc-400">Неограниченные кнопки, триггеры, ИИ, рассылки, без рекламы</div>
            </div>
            <a href="/auth" className="px-3 py-2 bg-amber-500 hover:bg-amber-400 rounded-xl text-[11px] font-black text-black uppercase tracking-widest transition-colors shrink-0">Pro →</a>
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-xs">
            <AlertTriangle size={14} /> {error}
          </div>
        )}

        {/* Fixed save button */}
        <div className="fixed bottom-0 left-0 right-0 p-4 bg-[#0a0a0a]/95 backdrop-blur-sm border-t border-zinc-800 flex justify-center">
          <button onClick={handleSave} disabled={saving}
            className="px-8 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-zinc-800 rounded-2xl text-sm font-black uppercase tracking-widest transition-colors flex items-center gap-2 min-w-[200px] justify-center">
            {saving ? <><Loader2 size={16} className="animate-spin" /> Сохранение...</> : <><Save size={16} /> Сохранить</>}
          </button>
        </div>
      </div>
    </div>
  );
};

// ─── Analytics Panel ──────────────────────────────────────────────────────────
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
          <button onClick={onBack} className="p-2 rounded-xl bg-zinc-900 hover:bg-zinc-800 transition-colors"><ArrowLeft size={16} /></button>
          <div><h1 className="text-lg font-black text-white">Аналитика</h1><div className="text-xs text-zinc-500">{bot.name}</div></div>
        </div>
        {loading ? (
          <div className="flex justify-center py-16"><Loader2 size={24} className="animate-spin text-zinc-600" /></div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {statCards.map(c => (
              <div key={c.label} className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-4">
                <div className={`text-2xl font-black mb-1 ${c.color}`}>{c.value}</div>
                <div className="text-[10px] text-zinc-500 uppercase tracking-widest">{c.label}</div>
              </div>
            ))}
          </div>
        )}
        {/* History chart placeholder */}
        {stats?.stats?.history?.length > 0 && (
          <div className="mt-6 bg-zinc-900/60 border border-zinc-800 rounded-2xl p-5">
            <h3 className="text-xs font-black text-zinc-400 uppercase tracking-widest mb-4">История (14 дней)</h3>
            <div className="flex items-end gap-1 h-24">
              {stats.stats.history.map((d: any, i: number) => {
                const maxVal = Math.max(...stats.stats.history.map((h: any) => (h.incoming || 0) + (h.outgoing || 0)), 1);
                const h = Math.max(4, Math.round(((d.incoming + d.outgoing) / maxVal) * 88));
                return (
                  <div key={i} className="flex-1 flex flex-col items-center gap-1 group">
                    <div className="w-full bg-blue-500/30 hover:bg-blue-500/50 transition-colors rounded-sm" style={{ height: `${h}px` }} />
                    <span className="text-[7px] text-zinc-700 group-hover:text-zinc-500">{d.date}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// ════════════════════════════════════════════════════════════════════════════════
// MAIN FREE PLAN PAGE
// ════════════════════════════════════════════════════════════════════════════════
type View = 'list' | 'editor' | 'analytics';

const FreePlan: React.FC = () => {
  const navigate = useNavigate();
  const userId   = localStorage.getItem('user_id') || '';

  const [view,      setView]      = useState<View>('list');
  const [activeBot, setActiveBot] = useState<FreeBot | null>(null);
  const [bots,      setBots]      = useState<FreeBot[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [creating,  setCreating]  = useState(false);

  // Create form
  const [newName,  setNewName]  = useState('');
  const [newToken, setNewToken] = useState('');
  const [showCreateForm, setShowCreateForm] = useState(false);

  // Bot status polling
  const [statusMap, setStatusMap] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!userId) { navigate('/auth'); return; }
    loadBots();
  }, [userId]);

  // Poll statuses every 5s
  useEffect(() => {
    const t = setInterval(() => {
      bots.forEach(b => {
        fetch(`/api/bots/status/${b.id}`)
          .then(r => r.ok ? r.json() : null)
          .then(d => { if (d?.status) setStatusMap(prev => ({ ...prev, [b.id]: d.status })); })
          .catch(() => {});
      });
    }, 5000);
    return () => clearInterval(t);
  }, [bots]);

  const loadBots = async () => {
    setLoading(true);
    try {
      const r = await fetch(FREE_API(`/bots/${userId}`));
      const d = r.ok ? await r.json() : [];
      setBots(d);
      const sm: Record<string, string> = {};
      d.forEach((b: FreeBot) => { sm[b.id] = b.status; });
      setStatusMap(sm);
    } catch { setBots([]); }
    finally { setLoading(false); }
  };

  const createBot = async () => {
    if (!newName.trim() || !newToken.trim()) return;
    setCreating(true);
    try {
      const r = await fetch(FREE_API('/bots/create'), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, name: newName.trim(), token: newToken.trim() })
      });
      if (!r.ok) { const e = await r.json(); throw new Error(e.detail); }
      const bot = await r.json();
      setBots(prev => [...prev, bot]);
      setStatusMap(prev => ({ ...prev, [bot.id]: 'IDLE' }));
      setNewName(''); setNewToken(''); setShowCreateForm(false);
    } catch (e: any) { alert(e.message); }
    finally { setCreating(false); }
  };

  const toggleBot = async (bot: FreeBot) => {
    const status = statusMap[bot.id] || bot.status;
    const isRunning = status === 'RUNNING';
    setStatusMap(prev => ({ ...prev, [bot.id]: 'LOADING' }));
    try {
      if (isRunning) {
        await fetch(BOTS_API(`/bots/stop/${bot.id}`), { method: 'POST' });
        setStatusMap(prev => ({ ...prev, [bot.id]: 'IDLE' }));
      } else {
        // Сначала сохраняем конфиг, потом стартуем
        const r = await fetch(BOTS_API('/bots/start'), {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: bot.id })
        });
        if (!r.ok) {
          const e = await r.json().catch(() => ({}));
          throw new Error(e.detail || 'Ошибка запуска');
        }
        setStatusMap(prev => ({ ...prev, [bot.id]: 'RUNNING' }));
      }
    } catch (e: any) {
      alert(e.message);
      setStatusMap(prev => ({ ...prev, [bot.id]: status }));
    }
  };

  const deleteBot = async (bot: FreeBot) => {
    if (!window.confirm(`Удалить бот «${bot.name}»?`)) return;
    try {
      await fetch(BOTS_API(`/bots/delete/${userId}/${bot.id}`), { method: 'DELETE' });
      setBots(prev => prev.filter(b => b.id !== bot.id));
    } catch { alert('Ошибка удаления'); }
  };

  // ─── Sub-views ───────────────────────────────────────────────────────────────
  if (view === 'editor' && activeBot) {
    return <FreeBotEditor bot={activeBot} userId={userId}
      onSave={updated => { setBots(prev => prev.map(b => b.id === updated.id ? updated : b)); setActiveBot(updated); }}
      onBack={() => { setView('list'); setActiveBot(null); }} />;
  }
  if (view === 'analytics' && activeBot) {
    return <FreeBotAnalytics bot={activeBot} userId={userId} onBack={() => { setView('list'); setActiveBot(null); }} />;
  }

  // ─── Main list view ──────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      {userId && <AccountBadge userId={userId} />}

      <div className="max-w-2xl mx-auto p-6 md:p-10">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-black text-white">Free Plan</h1>
            <p className="text-zinc-500 text-sm mt-1">Бесплатные боты с рекламой</p>
          </div>
          <button onClick={() => navigate('/')} className="p-2 rounded-xl bg-zinc-900 hover:bg-zinc-800 transition-colors text-zinc-400 hover:text-white">
            <ArrowLeft size={16} />
          </button>
        </div>

        {/* Features grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-8">
          {[
            { icon: '✅', label: 'Аналитика' }, { icon: '✅', label: 'Тикеты' },
            { icon: '✅', label: 'Модерация' }, { icon: '✅', label: 'Рассылки' },
            { icon: '✅', label: 'Топики',    }, { icon: '✅', label: '2 кнопки' },
            { icon: '❌', label: 'ИИ-ассистент' }, { icon: '❌', label: 'Мини-приложения' },
          ].map(f => (
            <div key={f.label} className="bg-zinc-900/40 border border-zinc-800 rounded-xl p-2.5 text-center">
              <div className="text-base mb-0.5">{f.icon}</div>
              <div className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest">{f.label}</div>
            </div>
          ))}
        </div>

        {/* Bots */}
        {loading ? (
          <div className="flex justify-center py-16"><Loader2 size={24} className="animate-spin text-zinc-600" /></div>
        ) : (
          <div className="space-y-3 mb-6">
            {bots.map(bot => {
              const status = statusMap[bot.id] || bot.status;
              const isRunning = status === 'RUNNING';
              const isLoading = status === 'LOADING';
              return (
                <div key={bot.id} className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-4">
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full flex-shrink-0 ${isRunning ? 'bg-green-400' : isLoading ? 'bg-amber-400 animate-pulse' : 'bg-zinc-600'}`} />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-bold text-white truncate">{bot.name}</div>
                      <div className="text-[10px] text-zinc-500 uppercase font-bold">{isLoading ? 'Загрузка...' : isRunning ? 'Работает' : 'Остановлен'}</div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <button onClick={() => toggleBot(bot)} disabled={isLoading}
                        className={`p-2 rounded-xl transition-all ${isLoading ? 'opacity-50 cursor-not-allowed' : isRunning ? 'bg-red-500/10 hover:bg-red-500/20 text-red-400' : 'bg-green-500/10 hover:bg-green-500/20 text-green-400'}`}>
                        {isLoading ? <Loader2 size={14} className="animate-spin" /> : isRunning ? <Square size={14} /> : <Play size={14} />}
                      </button>
                      <button onClick={() => { setActiveBot(bot); setView('editor'); }}
                        className="p-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white transition-all"><Settings size={14} /></button>
                      <button onClick={() => { setActiveBot(bot); setView('analytics'); }}
                        className="p-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white transition-all"><BarChart2 size={14} /></button>
                      <button onClick={() => deleteBot(bot)}
                        className="p-2 rounded-xl bg-zinc-800 hover:bg-red-500/10 text-zinc-600 hover:text-red-400 transition-all"><Trash2 size={14} /></button>
                    </div>
                  </div>
                </div>
              );
            })}

            {/* Create form / button */}
            {bots.length === 0 && !showCreateForm && (
              <div className="text-center py-10 text-zinc-600">
                <Bot size={32} className="mx-auto mb-3 opacity-30" />
                <p className="text-sm font-bold">Нет ботов</p>
                <p className="text-xs mt-1">Создайте бесплатного бота</p>
              </div>
            )}

            {bots.length === 0 && !showCreateForm && (
              <button onClick={() => setShowCreateForm(true)}
                className="w-full py-3 rounded-2xl border border-dashed border-blue-500/30 text-blue-400 text-sm font-bold uppercase tracking-widest hover:bg-blue-500/5 transition-all flex items-center justify-center gap-2">
                <Plus size={16} /> Создать бота
              </button>
            )}

            {bots.length > 0 && !showCreateForm && (
              <div className="bg-zinc-900/40 border border-zinc-800/50 rounded-2xl p-4 text-center">
                <p className="text-[11px] text-zinc-600 uppercase font-bold tracking-widest">Free: 1 бот</p>
                <p className="text-[10px] text-zinc-700 mt-1">Для дополнительных ботов перейдите на Pro</p>
              </div>
            )}

            {showCreateForm && (
              <div className="bg-zinc-900/60 border border-zinc-700 rounded-2xl p-4 space-y-3">
                <h3 className="text-xs font-black text-zinc-300 uppercase tracking-widest">Новый бот</h3>
                <input value={newName} onChange={e => setNewName(e.target.value)}
                  className="w-full bg-black border border-zinc-800 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500"
                  placeholder="Название бота" />
                <input value={newToken} onChange={e => setNewToken(e.target.value)}
                  className="w-full bg-black border border-zinc-800 rounded-xl px-3 py-2.5 text-sm text-white font-mono focus:outline-none focus:border-blue-500"
                  placeholder="Токен от @BotFather" type="password" />
                <div className="flex gap-2">
                  <button onClick={createBot} disabled={creating || !newName.trim() || !newToken.trim()}
                    className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-zinc-800 disabled:text-zinc-600 rounded-xl text-sm font-bold transition-colors flex items-center justify-center gap-2">
                    {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} Создать
                  </button>
                  <button onClick={() => setShowCreateForm(false)} className="px-4 py-2.5 bg-zinc-800 hover:bg-zinc-700 rounded-xl text-sm font-bold text-zinc-400 transition-colors">Отмена</button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Pro upgrade */}
        <div className="bg-gradient-to-r from-amber-500/10 to-orange-500/10 border border-amber-500/20 rounded-2xl p-4">
          <div className="flex items-center gap-3">
            <Crown size={20} className="text-amber-400 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-xs font-black text-amber-300 uppercase tracking-widest mb-0.5">Перейти на Pro</div>
              <div className="text-[11px] text-zinc-400">Без ограничений, без рекламы, ИИ, мини-приложения</div>
            </div>
            <a href="/auth" className="px-3 py-2 bg-amber-500 hover:bg-amber-400 rounded-xl text-[11px] font-black text-black uppercase tracking-widest transition-colors shrink-0">Pro →</a>
          </div>
        </div>
      </div>
    </div>
  );
};

export default FreePlan;
