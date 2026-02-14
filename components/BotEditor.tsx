import React, { useState, useEffect } from 'react';
import { BotConfig, BotStatus } from '../types';
import { api } from '../services/apiService';
import BotConsole from './BotConsole';
import BotStatsView from './BotStatsView';
import {
  Settings, BarChart3, Terminal, Save, Power,
  Plus, MessageSquare, CheckSquare, Square, Zap,
  Layout, Lock, Trash2, AlertCircle, Globe,
  Send, Shuffle, Hash, Users, Link, X, ChevronRight
} from 'lucide-react';

interface BotEditorProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
  onDelete: () => void;
  isAdminMode?: boolean;
}

// ══════════════════════════════════════════════════════════════
// Маленькие хелперы
// ══════════════════════════════════════════════════════════════

const Field: React.FC<{
  label: string;
  hint?: string;
  accent?: string;
  children: React.ReactNode;
}> = ({ label, hint, accent = 'focus:border-blue-500', children }) => (
  <div>
    <span className="block text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-2 ml-1">
      {label}
    </span>
    {children}
    {hint && <p className="mt-1.5 text-[9px] text-zinc-600 ml-1 uppercase font-bold">{hint}</p>}
  </div>
);

const inputCls = (accent = 'focus:border-blue-500', extra = '') =>
  `w-full bg-black border border-zinc-800 p-4 rounded-2xl text-white outline-none transition-all text-sm ${accent} ${extra}`;

const Toggle: React.FC<{
  on: boolean;
  onClick: () => void;
  label: string;
  sub?: string;
  color?: string;
}> = ({ on, onClick, label, sub, color = 'blue' }) => {
  const cls = on
    ? color === 'emerald' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
    : color === 'purple'  ? 'bg-purple-500/10 border-purple-500/30 text-purple-400'
    : 'bg-blue-500/10 border-blue-500/30 text-blue-400'
    : 'bg-black border-zinc-800 text-zinc-600';
  return (
    <button onClick={onClick}
      className={`w-full flex items-center justify-between p-4 rounded-2xl border transition-all ${cls}`}>
      <div className="text-left">
        <p className="text-xs font-bold">{label}</p>
        {sub && <p className="text-[9px] uppercase opacity-50">{sub}</p>}
      </div>
      {on ? <CheckSquare className="w-4 h-4 shrink-0" /> : <Square className="w-4 h-4 shrink-0" />}
    </button>
  );
};

// ══════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ══════════════════════════════════════════════════════════════

const BotEditor: React.FC<BotEditorProps> = ({ bot, onUpdate, onDelete, isAdminMode }) => {
  const [activeTab, setActiveTab] = useState('settings');
  const [isProcessing, setIsProcessing] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [messages, setMessages] = useState<any[]>([]);

  const isPoster     = bot.platform === 'poster';
  const isRandomizer = bot.platform === 'randomizer';
  const isVK         = bot.platform === 'vk';
  const isSupportBot = !isPoster && !isRandomizer;

  // Сброс вкладки если она недоступна для типа
  useEffect(() => {
    const allowed = isSupportBot
      ? ['settings', 'interface', 'logic', 'stats', 'logs', 'chat']
      : isRandomizer
      ? ['settings', 'stats', 'logs']
      : ['settings', 'stats', 'logs'];
    if (!allowed.includes(activeTab)) setActiveTab('settings');
  }, [bot.platform]);

  useEffect(() => {
    if (activeTab === 'chat') {
      api.getBotMessages(bot.id).then(setMessages).catch(() => setMessages([]));
    }
  }, [activeTab, bot.id]);

  // helpers
  const upd = (patch: Partial<BotConfig>) => { setDirty(true); onUpdate({ ...bot, ...patch }); };
  const updSet = (key: string, val: any) => {
    setDirty(true);
    onUpdate({ ...bot, settings: { ...(bot.settings || {} as any), [key]: val } });
  };
  const adminIdsStr = (bot.adminIds || []).join(', ');
  const parseAdminIds = (str: string) =>
    str.split(',').map(s => s.trim()).filter(s => /^\d+$/.test(s)).map(Number);

  const save = async () => {
    setIsProcessing(true);
    try {
      const r = await api.saveBot(bot.owner_id, bot);
      if (r) { onUpdate(r); setDirty(false); }
    } catch { alert('Ошибка сохранения'); }
    finally { setIsProcessing(false); }
  };

  const toggleServer = async () => {
    setIsProcessing(true);
    try {
      if (bot.status === BotStatus.RUNNING) {
        await api.stopBotOnServer(bot.id);
        onUpdate({ ...bot, status: BotStatus.IDLE });
      } else {
        const r = await api.saveBot(bot.owner_id, bot);
        if (r) { onUpdate(r); setDirty(false); }
        const res = await api.startBotOnServer(bot);
        if (res === true) onUpdate({ ...bot, status: BotStatus.RUNNING });
        else alert(`Ошибка запуска: ${res}`);
      }
    } finally { setIsProcessing(false); }
  };

  // — Цвета / иконки по типу ———————————————————————————
  const [accent, accentBg, accentBorder] = isPoster
    ? ['text-emerald-400', 'bg-emerald-500/10', 'border-emerald-500/30']
    : isRandomizer
    ? ['text-purple-400', 'bg-purple-500/10', 'border-purple-500/30']
    : isVK
    ? ['text-sky-400', 'bg-sky-500/10', 'border-sky-500/30']
    : ['text-blue-400', 'bg-blue-500/10', 'border-blue-500/30'];

  const inputAccent = isPoster ? 'focus:border-emerald-500'
    : isRandomizer ? 'focus:border-purple-500'
    : 'focus:border-blue-500';

  const badgeLabel = isPoster ? 'TG Постинг' : isRandomizer ? 'Рандомайзер' : isVK ? 'VK' : 'Telegram';
  const PlatIcon = isPoster ? Send : isRandomizer ? Shuffle : isVK ? Globe : Settings;

  const tabs = [
    { id: 'settings',  label: 'Настройки', icon: Settings },
    ...(isSupportBot ? [
      { id: 'interface', label: 'Кнопки',    icon: MessageSquare },
      { id: 'logic',     label: 'Триггеры',  icon: Zap },
      { id: 'chat',      label: 'CRM',       icon: MessageSquare },
    ] : []),
    { id: 'stats',     label: 'Аналитика', icon: BarChart3 },
    { id: 'logs',      label: 'Терминал',  icon: Terminal },
  ];

  const safeSettings: any = { ...(bot.settings || {}) };

  // ─────────────────────────────────────────────────────────────
  return (
    <div className="space-y-6 pb-24 animate-in fade-in duration-300">

      {/* ── Несохранённые изменения ── */}
      {dirty && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-[200] flex items-center gap-4 bg-zinc-900 border border-zinc-700 px-6 py-3 rounded-2xl shadow-2xl shadow-black/60 animate-in slide-in-from-bottom-4 duration-300">
          <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
          <span className="text-xs font-black uppercase tracking-widest text-white">Несохранённые изменения</span>
          <button onClick={save} disabled={isProcessing}
            className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-xl text-[10px] font-black uppercase transition-all">
            Сохранить
          </button>
        </div>
      )}

      {/* ── ШАПКА ── */}
      <header className={`bg-[#111] border border-zinc-800 p-6 rounded-3xl flex flex-col sm:flex-row justify-between items-center gap-5 shadow-2xl`}>
        <div className="flex items-center gap-5">
          <div className={`w-14 h-14 rounded-2xl flex items-center justify-center border-2 transition-all ${
            bot.status === BotStatus.RUNNING
              ? `${accentBg} ${accentBorder} ${accent}`
              : 'bg-zinc-900 border-zinc-800 text-zinc-600'
          }`}>
            <PlatIcon className="w-7 h-7" />
          </div>
          <div>
            <div className="flex items-center flex-wrap gap-2">
              <h1 className="text-2xl font-black text-white">{bot.name}</h1>
              <span className={`px-2 py-0.5 rounded-lg text-[8px] font-black uppercase tracking-widest border ${accentBg} ${accentBorder} ${accent}`}>
                {badgeLabel}
              </span>
              {isAdminMode && (
                <span className="px-2 py-0.5 bg-orange-500/10 border border-orange-500/20 rounded-lg text-orange-400 text-[8px] font-black uppercase">
                  Support Mode
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 mt-1">
              <span className={`w-2 h-2 rounded-full ${bot.status === BotStatus.RUNNING ? 'bg-emerald-500 animate-pulse' : 'bg-zinc-600'}`} />
              <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{bot.status}</span>
              {bot.id && <span className="text-[9px] text-zinc-700 font-mono ml-1">{bot.id}</span>}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={save} disabled={isProcessing}
            className={`px-5 py-3 rounded-2xl text-[10px] font-black uppercase tracking-widest flex items-center gap-2 transition-all border ${
              dirty ? 'bg-blue-600 text-white border-blue-600 shadow-lg shadow-blue-600/20' : 'bg-transparent text-zinc-500 border-zinc-800 hover:border-zinc-700'
            }`}>
            <Save className="w-4 h-4" />Сохранить
          </button>
          <button onClick={toggleServer} disabled={isProcessing}
            className={`px-8 py-3 rounded-2xl font-black text-xs uppercase flex items-center gap-2 transition-all ${
              bot.status === BotStatus.RUNNING
                ? 'bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20'
                : 'bg-blue-600 text-white shadow-lg shadow-blue-600/20 hover:bg-blue-500'
            }`}>
            <Power className="w-4 h-4" />
            {isProcessing ? '...' : bot.status === BotStatus.RUNNING ? 'Стоп' : 'Запустить'}
          </button>
        </div>
      </header>

      {/* ── ВКЛАДКИ ── */}
      <div className="flex gap-1 border-b border-zinc-800/60 overflow-x-auto no-scrollbar">
        {tabs.map(t => (
          <button key={t.id} onClick={() => setActiveTab(t.id)}
            className={`flex items-center gap-1.5 px-5 py-3.5 text-[10px] font-black uppercase tracking-widest border-b-2 transition-all whitespace-nowrap ${
              activeTab === t.id
                ? `border-current ${accent}`
                : 'border-transparent text-zinc-600 hover:text-zinc-400'
            }`}>
            <t.icon className="w-3 h-3" />{t.label}
          </button>
        ))}
      </div>

      {/* ════════════════════════════════════════════
          НАСТРОЙКИ — ПОСТЕР
      ════════════════════════════════════════════ */}
      {activeTab === 'settings' && isPoster && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 animate-in fade-in duration-300">

          {/* Основные */}
          <div className="bg-[#111] border border-zinc-800 p-7 rounded-3xl space-y-5">
            <h2 className="text-xs font-black text-zinc-300 uppercase flex items-center gap-2">
              <Send className="w-4 h-4 text-emerald-500" />Настройки постинга
            </h2>

            <Field label="Bot Token (BotFather)">
              <input type="password" className={inputCls('focus:border-emerald-500', 'font-mono')}
                placeholder="123456789:AAF..." value={bot.token}
                onChange={e => upd({ token: e.target.value })} />
            </Field>

            <Field label="Канал для публикации" hint="Бот должен быть администратором канала">
              <div className="flex items-center gap-2">
                <Hash className="w-4 h-4 text-emerald-500 shrink-0" />
                <input className={inputCls('focus:border-emerald-500')}
                  placeholder="@mychannel или -1001234567890"
                  value={bot.channelId || ''}
                  onChange={e => upd({ channelId: e.target.value })} />
              </div>
            </Field>

            <Field label="ID администраторов" hint="Кто может создавать и публиковать посты (через запятую)">
              <div className="flex items-center gap-2">
                <Users className="w-4 h-4 text-amber-500 shrink-0" />
                <input className={inputCls('focus:border-amber-500')}
                  placeholder="123456789, 987654321"
                  value={adminIdsStr}
                  onChange={e => upd({ adminIds: parseAdminIds(e.target.value) })} />
              </div>
            </Field>
          </div>

          {/* Инфо-карточка */}
          <div className="space-y-5">
            <div className="bg-emerald-500/5 border border-emerald-500/15 p-7 rounded-3xl space-y-4">
              <h3 className="text-xs font-black text-emerald-400 uppercase flex items-center gap-2">
                <Send className="w-4 h-4" />Что умеет этот бот
              </h3>
              <div className="space-y-2 text-[11px] text-zinc-400 leading-relaxed">
                {[
                  '📝 Текст с HTML-форматированием',
                  '🖼 Фото, Видео, GIF, Аудио, Документ, Стикер',
                  '🔘 Инлайн-кнопки: <code>Текст | https://url</code>',
                  '⏰ Отложенная публикация (через N мин или в дату)',
                  '👁 Предпросмотр перед публикацией',
                  '✅ Подтверждение: Опубликовать / Редактировать / Отмена',
                ].map((t, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <ChevronRight className="w-3 h-3 text-emerald-500 shrink-0 mt-0.5" />
                    <span dangerouslySetInnerHTML={{ __html: t }} />
                  </div>
                ))}
              </div>
              <div className="pt-3 border-t border-emerald-500/10 text-[9px] text-emerald-500/60 uppercase font-black tracking-widest">
                Запустить бота → /start → Создать пост
              </div>
            </div>

            {/* /broadcast инфо */}
            <div className="bg-amber-500/5 border border-amber-500/15 p-5 rounded-2xl">
              <h4 className="text-[10px] font-black text-amber-400 uppercase mb-2 flex items-center gap-1.5">
                <Users className="w-3 h-3" />Команда /broadcast
              </h4>
              <p className="text-[10px] text-zinc-500 leading-relaxed">
                Администраторы из списка выше могут отправить <code className="text-amber-400">/broadcast</code> прямо боту — бот запросит сообщение, покажет превью и разошлёт по всем пользователям.
              </p>
            </div>

            {/* Удаление */}
            {!isAdminMode && (
              <button onClick={() => window.confirm('Удалить этот инстанс?') && onDelete()}
                className="w-full p-4 text-[10px] font-black uppercase text-rose-500 bg-rose-500/5 rounded-2xl border border-rose-500/10 hover:bg-rose-500/15 transition-all flex items-center justify-center gap-2">
                <Trash2 className="w-4 h-4" />Удалить навсегда
              </button>
            )}
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════
          НАСТРОЙКИ — РАНДОМАЙЗЕР
      ════════════════════════════════════════════ */}
      {activeTab === 'settings' && isRandomizer && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 animate-in fade-in duration-300">

          {/* Основные */}
          <div className="bg-[#111] border border-zinc-800 p-7 rounded-3xl space-y-5">
            <h2 className="text-xs font-black text-zinc-300 uppercase flex items-center gap-2">
              <Shuffle className="w-4 h-4 text-purple-500" />Настройки рандомайзера
            </h2>

            <Field label="Bot Token (BotFather)">
              <input type="password" className={inputCls('focus:border-purple-500', 'font-mono')}
                placeholder="123456789:AAF..." value={bot.token}
                onChange={e => upd({ token: e.target.value })} />
            </Field>

            <Field label="Канал розыгрышей" hint="Бот — администратор этого канала">
              <div className="flex items-center gap-2">
                <Hash className="w-4 h-4 text-purple-500 shrink-0" />
                <input className={inputCls('focus:border-purple-500')}
                  placeholder="@lotchannel или -1001234567890"
                  value={bot.lotChannel || ''}
                  onChange={e => upd({ lotChannel: e.target.value })} />
              </div>
            </Field>

            <Field label="ID администраторов" hint="Могут управлять ботом, создавать розыгрыши (через запятую)">
              <div className="flex items-center gap-2">
                <Users className="w-4 h-4 text-amber-500 shrink-0" />
                <input className={inputCls('focus:border-amber-500')}
                  placeholder="123456789, 987654321"
                  value={adminIdsStr}
                  onChange={e => upd({ adminIds: parseAdminIds(e.target.value) })} />
              </div>
            </Field>

            <Field label="Username бота" hint="Для deep-link ссылок участия в розыгрышах">
              <div className="flex items-center gap-2">
                <Link className="w-4 h-4 text-purple-400 shrink-0" />
                <input className={inputCls('focus:border-purple-500')}
                  placeholder="@MyLotteryBot"
                  value={bot.botLink || ''}
                  onChange={e => upd({ botLink: e.target.value })} />
              </div>
            </Field>

            <Field label="Приветственное сообщение (/start)">
              <textarea className={inputCls('focus:border-purple-500', 'min-h-[80px] resize-none')}
                placeholder="👋 Привет! Я бот для розыгрышей."
                value={bot.welcomeMessage || ''}
                onChange={e => upd({ welcomeMessage: e.target.value })} />
            </Field>
          </div>

          {/* Инфо + удаление */}
          <div className="space-y-5">
            <div className="bg-purple-500/5 border border-purple-500/15 p-7 rounded-3xl space-y-4">
              <h3 className="text-xs font-black text-purple-400 uppercase flex items-center gap-2">
                <Shuffle className="w-4 h-4" />Что умеет этот бот
              </h3>
              <div className="space-y-2 text-[11px] text-zinc-400 leading-relaxed">
                {[
                  '🎲 Создание розыгрышей из панели администратора',
                  '📢 Публикация в канал с кнопкой «Участвовать»',
                  '🔍 Проверка подписки на каналы перед участием',
                  '⏱ Финиш по времени или по числу участников',
                  '🏆 Автоматический выбор победителей',
                  '📊 Аналитика: пользователи, блоки, розыгрыши',
                  '📣 /broadcast — рассылка по всем участникам',
                ].map((t, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <ChevronRight className="w-3 h-3 text-purple-500 shrink-0 mt-0.5" />
                    <span>{t}</span>
                  </div>
                ))}
              </div>
              <div className="pt-3 border-t border-purple-500/10 text-[9px] text-purple-500/60 uppercase font-black tracking-widest">
                Запустить бота → /start → 🛠 Панель → Создать розыгрыш
              </div>
            </div>

            <div className="bg-amber-500/5 border border-amber-500/15 p-5 rounded-2xl">
              <h4 className="text-[10px] font-black text-amber-400 uppercase mb-2 flex items-center gap-1.5">
                <Users className="w-3 h-3" />/broadcast через бота
              </h4>
              <p className="text-[10px] text-zinc-500 leading-relaxed">
                Администраторы из списка выше могут прямо в боте нажать <code className="text-amber-400">/broadcast</code> и разослать сообщение всем зарегистрированным пользователям.
              </p>
            </div>

            {!isAdminMode && (
              <button onClick={() => window.confirm('Удалить этот инстанс?') && onDelete()}
                className="w-full p-4 text-[10px] font-black uppercase text-rose-500 bg-rose-500/5 rounded-2xl border border-rose-500/10 hover:bg-rose-500/15 transition-all flex items-center justify-center gap-2">
                <Trash2 className="w-4 h-4" />Удалить навсегда
              </button>
            )}
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════
          НАСТРОЙКИ — SUPPORT BOT (TG + VK)
      ════════════════════════════════════════════ */}
      {activeTab === 'settings' && isSupportBot && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 animate-in fade-in duration-300">

          <div className="space-y-6">
            {/* Основные */}
            <div className="bg-[#111] border border-zinc-800 p-7 rounded-3xl space-y-5">
              <h2 className="text-xs font-black text-zinc-300 uppercase flex items-center gap-2">
                <Settings className="w-4 h-4 text-blue-500" />Основные
              </h2>

              {/* Переключатель TG / VK */}
              <div className="flex bg-black p-1 rounded-2xl border border-zinc-800">
                {(['telegram', 'vk'] as const).map(p => (
                  <button key={p} type="button"
                    onClick={() => upd({ platform: p })}
                    className={`flex-1 py-3 rounded-xl text-[10px] font-black uppercase transition-all ${
                      bot.platform === p ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20' : 'text-zinc-500 hover:text-zinc-300'
                    }`}>
                    {p === 'telegram' ? 'Telegram Bot' : 'VK Community'}
                  </button>
                ))}
              </div>

              <Field label={isVK ? 'ВКонтакте Access Token' : 'Telegram Bot Token'}>
                <input type="password" className={inputCls('focus:border-blue-500', 'font-mono')}
                  placeholder={isVK ? 'vk1.a.xxxx...' : '123456789:AAF...'}
                  value={bot.token}
                  onChange={e => upd({ token: e.target.value })} />
              </Field>

              <Field
                label={isVK ? 'ID беседы (peer_id)' : 'ID группы-форума'}
                hint={isVK ? 'peer_id беседы ВКонтакте, напр. 2000000010' : 'ID Telegram-группы с включёнными темами'}>
                <input className={inputCls('focus:border-blue-500')}
                  placeholder={isVK ? '2000000010' : '-100...'}
                  value={isVK ? (bot.vkGroupId ?? '') : (bot.adminChatId ?? '')}
                  onChange={e => isVK
                    ? upd({ vkGroupId: e.target.value, vk_group_id: e.target.value })
                    : upd({ adminChatId: e.target.value })} />
              </Field>

              <Field label="ID администраторов бота" hint="Могут делать /broadcast прямо в боте">
                <div className="flex items-center gap-2">
                  <Users className="w-4 h-4 text-amber-500 shrink-0" />
                  <input className={inputCls('focus:border-amber-500')}
                    placeholder="123456789, 987654321"
                    value={adminIdsStr}
                    onChange={e => upd({ adminIds: parseAdminIds(e.target.value) })} />
                </div>
              </Field>

              <Field label="Приветствие (/start)">
                <textarea className={inputCls('focus:border-blue-500', 'min-h-[90px] resize-none')}
                  placeholder="Привет! Чем могу помочь?"
                  value={bot.welcomeMessage || ''}
                  onChange={e => upd({ welcomeMessage: e.target.value })} />
              </Field>
            </div>

            {/* Конструктор шапки */}
            {!isVK && (
              <div className="bg-[#111] border border-zinc-800 p-7 rounded-3xl space-y-4">
                <h3 className="text-xs font-black text-zinc-300 uppercase flex items-center gap-2">
                  <Layout className="w-4 h-4 text-emerald-500" />Шапки сообщений
                </h3>
                {[
                  { k: 'firstMessageHeader',  l: 'Первое обращение',  ph: '🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>' },
                  { k: 'ticketMessageHeader',  l: 'Заявка (кнопки)',   ph: '🆘 <b>ЗАЯВКА [{btn}]:</b>'  },
                  { k: 'commonMessageHeader',  l: 'Обычное сообщение', ph: '📩 <b>СООБЩЕНИЕ:</b>'        },
                ].map(f => (
                  <div key={f.k}>
                    <span className="text-[9px] text-zinc-600 uppercase font-bold ml-1">{f.l}</span>
                    <input className="w-full mt-1 bg-black border border-zinc-800 p-3.5 rounded-xl text-xs text-white outline-none focus:border-emerald-500 transition-all"
                      value={safeSettings[f.k] || ''} placeholder={f.ph}
                      onChange={e => updSet(f.k, e.target.value)} />
                  </div>
                ))}
                <div className="grid grid-cols-3 gap-2 pt-1">
                  {[{k:'showHeaderName',l:'Имя'},{k:'showHeaderUsername',l:'@Юзер'},{k:'showHeaderId',l:'ID'}].map(f => (
                    <Toggle key={f.k} on={!!safeSettings[f.k]} onClick={() => updSet(f.k, !safeSettings[f.k])} label={f.l} color="emerald" />
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="space-y-6">
            {/* Безопасность */}
            <div className="bg-[#111] border border-zinc-800 p-7 rounded-3xl space-y-4">
              <h3 className="text-xs font-black text-zinc-300 uppercase flex items-center gap-2">
                <Lock className="w-4 h-4 text-rose-500" />Безопасность и анти-флуд
              </h3>
              <div className="space-y-3">
                <div className="flex items-center justify-between p-4 rounded-2xl bg-black border border-zinc-800">
                  <div>
                    <p className="text-xs font-bold text-white">Интервал анти-спама</p>
                    <p className="text-[9px] text-zinc-500 uppercase">Сек. между сообщениями</p>
                  </div>
                  <input type="number" step="0.5" min="0"
                    className="w-16 bg-zinc-900 border border-zinc-700 p-2 rounded-xl text-center text-xs text-white"
                    value={safeSettings.rateLimit ?? 1}
                    onChange={e => updSet('rateLimit', parseFloat(e.target.value))} />
                </div>
                <div className="flex items-center justify-between p-4 rounded-2xl bg-black border border-zinc-800">
                  <div>
                    <p className="text-xs font-bold text-white">Лимит предупреждений</p>
                    <p className="text-[9px] text-zinc-500 uppercase">Варнов до авто-бана</p>
                  </div>
                  <input type="number" min="1"
                    className="w-16 bg-zinc-900 border border-zinc-700 p-2 rounded-xl text-center text-xs text-white"
                    value={safeSettings.autoBanThreshold ?? 3}
                    onChange={e => updSet('autoBanThreshold', parseInt(e.target.value))} />
                </div>
                <Toggle on={!!safeSettings.antiSpam} onClick={() => updSet('antiSpam', !safeSettings.antiSpam)}
                  label="Включить антиспам" sub="Ограничение частоты сообщений" />
                <Toggle on={!!safeSettings.forwardToAdmin} onClick={() => updSet('forwardToAdmin', !safeSettings.forwardToAdmin)}
                  label="Пересылать в группу" sub="Основной режим работы" color="emerald" />
                <Toggle on={!!safeSettings.notifyOnStart} onClick={() => updSet('notifyOnStart', !safeSettings.notifyOnStart)}
                  label="Уведомление при старте" sub="Когда новый пользователь /start" />
                <Toggle on={!!safeSettings.notifyOnBlock} onClick={() => updSet('notifyOnBlock', !safeSettings.notifyOnBlock)}
                  label="Уведомление о блоке" sub="Когда пользователь заблокировал" />
              </div>
            </div>

            {/* Темы (только TG) */}
            {!isVK && (
              <div className="bg-[#111] border border-zinc-800 p-7 rounded-3xl space-y-3">
                <h3 className="text-xs font-black text-zinc-300 uppercase flex items-center gap-2">
                  <MessageSquare className="w-4 h-4 text-blue-500" />Форум (Темы)
                </h3>
                <Toggle on={!!safeSettings.useTopics} onClick={() => updSet('useTopics', !safeSettings.useTopics)}
                  label="Использовать темы" sub="Для супергрупп с форумом" color="emerald" />
                <Toggle on={!!safeSettings.topicPerRequest} onClick={() => updSet('topicPerRequest', !safeSettings.topicPerRequest)}
                  label="Ветка на каждый тикет" sub="Ticket System Mode" />
                <Toggle on={!!safeSettings.anonymousTopics} onClick={() => updSet('anonymousTopics', !safeSettings.anonymousTopics)}
                  label="Анонимные ID" sub="Хешировать данные пользователей" />
              </div>
            )}

            {/* Удаление */}
            {isAdminMode ? (
              <div className="p-5 border border-zinc-800 bg-zinc-900/30 rounded-2xl flex items-center gap-3 opacity-40">
                <Lock className="w-5 h-5 text-zinc-500" />
                <div>
                  <p className="text-[10px] font-black uppercase text-zinc-400">Admin Protection</p>
                  <p className="text-[9px] text-zinc-600 uppercase">Deletion disabled in Support Mode</p>
                </div>
              </div>
            ) : (
              <button onClick={() => window.confirm('Удалить этот инстанс?') && onDelete()}
                className="w-full p-4 text-[10px] font-black uppercase text-rose-500 bg-rose-500/5 rounded-2xl border border-rose-500/10 hover:bg-rose-500/15 transition-all flex items-center justify-center gap-2">
                <Trash2 className="w-4 h-4" />Удалить навсегда
              </button>
            )}
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════
          КНОПКИ (только support)
      ════════════════════════════════════════════ */}
      {activeTab === 'interface' && isSupportBot && (
        <div className="space-y-6 animate-in fade-in duration-300">
          <div className="flex justify-between items-center">
            <h2 className="text-xl font-black text-white uppercase">Кнопки меню</h2>
            <button onClick={() => upd({ buttons: [...(bot.buttons||[]), {text:'',response:'',type:'message'}] })}
              className="bg-blue-600 hover:bg-blue-500 px-6 py-3 rounded-2xl text-[10px] font-black text-white uppercase flex items-center gap-2 transition-all">
              <Plus className="w-4 h-4" />Добавить
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {(bot.buttons||[]).map((btn, i) => (
              <div key={i} className="bg-[#111] border border-zinc-800 rounded-3xl p-7 space-y-4 relative border-t-4 border-t-blue-500/20">
                <button onClick={() => upd({buttons: bot.buttons!.filter((_,j)=>j!==i)})}
                  className="absolute top-5 right-5 text-zinc-600 hover:text-rose-400 transition-colors">
                  <X className="w-5 h-5" />
                </button>
                <Field label="Текст кнопки">
                  <input className={inputCls('focus:border-blue-500', 'font-bold')}
                    value={btn.text}
                    onChange={e => { const nb=[...bot.buttons!]; nb[i]={...nb[i],text:e.target.value}; upd({buttons:nb}); }} />
                </Field>
                <Field label="Ответ системы">
                  <textarea className={inputCls('focus:border-blue-500','min-h-[100px] resize-none')}
                    value={btn.response}
                    onChange={e => { const nb=[...bot.buttons!]; nb[i]={...nb[i],response:e.target.value}; upd({buttons:nb}); }} />
                </Field>
                <div className="flex bg-black p-1 rounded-xl border border-zinc-800">
                  {(['message','request'] as const).map(t => (
                    <button key={t} onClick={() => { const nb=[...bot.buttons!]; nb[i]={...nb[i],type:t}; upd({buttons:nb}); }}
                      className={`flex-1 py-2.5 rounded-lg text-[9px] font-black uppercase transition-all ${btn.type===t?'bg-blue-600 text-white':'text-zinc-600 hover:text-zinc-400'}`}>
                      {t==='message'?'Обычный ответ':'🆘 Заявка (Тикет)'}
                    </button>
                  ))}
                </div>
              </div>
            ))}
            {(bot.buttons||[]).length === 0 && (
              <div className="col-span-2 py-20 text-center text-zinc-700 text-xs uppercase font-black tracking-widest opacity-40">
                Кнопки не добавлены
              </div>
            )}
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════
          ТРИГГЕРЫ (только support)
      ════════════════════════════════════════════ */}
      {activeTab === 'logic' && isSupportBot && (
        <div className="space-y-6 animate-in fade-in duration-300">
          <div className="flex justify-between items-center">
            <h2 className="text-xl font-black text-white uppercase">Триггеры авто-ответа</h2>
            <button onClick={() => upd({triggers:[...(bot.triggers||[]),{keyword:'',response:''}]})}
              className="bg-emerald-600 hover:bg-emerald-500 px-6 py-3 rounded-2xl text-[10px] font-black text-white uppercase flex items-center gap-2 transition-all">
              <Plus className="w-4 h-4" />Добавить
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {(bot.triggers||[]).map((trig,i) => (
              <div key={i} className="bg-[#111] border border-zinc-800 rounded-3xl p-7 space-y-4 relative border-t-4 border-t-emerald-500/20">
                <button onClick={() => upd({triggers: bot.triggers!.filter((_,j)=>j!==i)})}
                  className="absolute top-5 right-5 text-zinc-600 hover:text-rose-400 transition-colors">
                  <X className="w-5 h-5" />
                </button>
                <Field label="Ключевое слово">
                  <input className={inputCls('focus:border-emerald-500', 'font-bold')}
                    placeholder="ping, привет, помощь..."
                    value={trig.keyword}
                    onChange={e => { const nt=[...bot.triggers!]; nt[i]={...nt[i],keyword:e.target.value}; upd({triggers:nt}); }} />
                </Field>
                <Field label="Ответ бота">
                  <textarea className={inputCls('focus:border-emerald-500','min-h-[100px] resize-none')}
                    placeholder="Что бот ответит на это слово..."
                    value={trig.response}
                    onChange={e => { const nt=[...bot.triggers!]; nt[i]={...nt[i],response:e.target.value}; upd({triggers:nt}); }} />
                </Field>
              </div>
            ))}
            {(bot.triggers||[]).length === 0 && (
              <div className="col-span-2 py-20 text-center text-zinc-700 text-xs uppercase font-black tracking-widest opacity-40">
                Триггеры не добавлены
              </div>
            )}
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════
          CRM — история сообщений (только support)
      ════════════════════════════════════════════ */}
      {activeTab === 'chat' && isSupportBot && (
        <div className="bg-[#111] border border-zinc-800 rounded-3xl h-[680px] flex flex-col p-6 animate-in fade-in duration-300">
          <h2 className="text-xs font-black text-zinc-300 uppercase flex items-center gap-2 mb-5">
            <MessageSquare className="w-4 h-4 text-blue-500" />История сообщений CRM
          </h2>
          <div className="flex-1 overflow-y-auto space-y-4 pr-2">
            {messages.length === 0 ? (
              <p className="text-center text-zinc-700 py-32 text-[10px] uppercase font-black tracking-widest opacity-30">
                История пуста
              </p>
            ) : messages.map((m, i) => (
              <div key={i} className={`flex gap-3 items-end ${m.is_admin ? 'flex-row-reverse' : ''}`}>
                <div className={`p-4 rounded-2xl max-w-[75%] text-sm shadow-lg ${
                  m.is_admin
                    ? 'bg-blue-600 text-white rounded-br-sm'
                    : 'bg-zinc-900 border border-zinc-800 text-zinc-300 rounded-bl-sm'
                }`}>
                  <p className="text-[9px] font-black opacity-40 mb-1 uppercase">
                    {m.user?.name} · {new Date(m.timestamp).toLocaleTimeString()}
                  </p>
                  <div className="whitespace-pre-wrap leading-relaxed">{m.text}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════
          АНАЛИТИКА (все типы — адаптивный компонент)
      ════════════════════════════════════════════ */}
      {activeTab === 'stats' && (
        <BotStatsView bot={bot} onUpdate={onUpdate} />
      )}

      {/* ════════════════════════════════════════════
          ТЕРМИНАЛ (все типы)
      ════════════════════════════════════════════ */}
      {activeTab === 'logs' && (
        <BotConsole botId={bot.id} />
      )}

    </div>
  );
};

export default BotEditor;
