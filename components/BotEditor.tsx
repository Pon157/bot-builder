import React, { useState, useEffect } from 'react';
import { BotConfig, BotStatus, BotStaffAdmin, StaffSettings } from '../types';
import { api } from '../services/apiService';
import BotConsole from './BotConsole';
import BotStatsView from './BotStatsView';
import {
  Settings, Cpu, BarChart3, Terminal, X, Save, Power,
  Ticket, Plus, MessageSquare, User, CheckSquare,
  Square, Zap, Layout, ShieldAlert, Lock, Trash2, AlertCircle, Globe,
  Send, Shuffle, Hash, Users, Link, Smartphone, ChevronDown,
  Brain, Image, ExternalLink, ArrowRight, Layers, Coins, Upload,
  AppWindow, Palette, AlignLeft, AlignCenter, AlignRight,
  Type, MousePointerClick, Link2, TextCursorInput, Minus,
  MoveVertical, Check, ChevronUp, Copy, Eye, EyeOff,
  Calendar, AlertTriangle, RefreshCw, ToggleLeft, ToggleRight,
  UserPlus, Shield, ArrowLeftRight, Clock, TrendingUp, Award
} from 'lucide-react';

interface BotEditorProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
  onDelete: () => void;
  isAdminMode?: boolean;
}

const BotEditor: React.FC<BotEditorProps> = ({ bot, onUpdate, onDelete, isAdminMode }) => {
  const [activeTab, setActiveTab] = useState<'settings' | 'logic' | 'interface' | 'ai' | 'logs' | 'stats' | 'miniapps'>('settings');
  const [isProcessing, setIsProcessing] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [messages, setMessages] = useState<any[]>([]);
  const [aiBalance, setAiBalance] = useState<{tokens_balance: number, tokens_total: number, tokens_used: number} | null>(null);
  const [aiKeyInput, setAiKeyInput] = useState('');
  const [aiKeyStatus, setAiKeyStatus] = useState<string>('');
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  // ── AI preview chat panel ──
  const [aiChatOpen, setAiChatOpen]       = useState(false);
  const [aiChatInput, setAiChatInput]     = useState('');
  const [aiChatLoading, setAiChatLoading] = useState(false);
  const [aiChatMsgs, setAiChatMsgs]       = useState<{role:'user'|'ai', text:string}[]>([]);

  // ── Типы платформ ──
  const isVK         = bot.platform === 'vk';
  const isPoster     = bot.platform === 'poster';
  const isRandomizer = bot.platform === 'randomizer';
  const isSupportBot = !isPoster && !isRandomizer;

  // Сбрасываем вкладку сразу при маунте и при смене бота/платформы
  useEffect(() => {
    const supportOnlyTabs = ['logic', 'interface', 'chat'];
    if ((isPoster || isRandomizer) && supportOnlyTabs.includes(activeTab)) {
      setActiveTab('settings');
    }
  }, [bot.id, bot.platform, isPoster, isRandomizer]);

  useEffect(() => {
    if (activeTab === 'chat') {
      api.getBotMessages(bot.id).then(setMessages).catch(() => setMessages([]));
    }
    if (activeTab === 'ai') {
      fetch(`/api/ai/balance/${bot.id}`)
        .then(r => r.json()).then(setAiBalance).catch(() => {});
    }
  }, [activeTab, bot.id]);

  const defaultSettings: BotConfig['settings'] = {
    useTopics: false, topicPerRequest: false, anonymousTopics: false,
    forwardToAdmin: true, antiSpam: true, showUserInfo: true, showUsername: true,
    autoApproveJoin: false, rateLimit: 1, autoBanThreshold: 3,
    showHeaderId: true, showHeaderName: true, showHeaderUsername: true,
    notifyOnStart: true, notifyOnBlock: true,
    firstMessageHeader: "🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>",
    ticketMessageHeader: "🆘 <b>ЗАЯВКА [{btn}]:</b>",
    commonMessageHeader: "📩 <b>СООБЩЕНИЕ:</b>",
    memoryBaseEnabled: false,
    memoryBaseBlockReasons: [] as string[],
    dvrEnabled: false,
  };
  const safeSettings = { ...defaultSettings, ...(bot.settings || {}) };

  // ── Helpers ──
  const handleLocalUpdate = (upd: BotConfig) => { setHasUnsavedChanges(true); onUpdate(upd); };
  const updateSetting = (key: keyof typeof defaultSettings, val: any) => {
    setHasUnsavedChanges(true);
    onUpdate({ ...bot, settings: { ...safeSettings, [key]: val } });
  };
  const syncState = async () => {
    setIsProcessing(true);
    try {
      const updated = await api.saveBot(bot.owner_id, bot);
      if (updated) onUpdate(updated);
      setHasUnsavedChanges(false);
      alert('Конфигурация сохранена!');
    } catch { alert('Ошибка при сохранении'); }
    finally { setIsProcessing(false); }
  };
  const handleToggleServer = async () => {
    setIsProcessing(true);
    try {
      if (bot.status === BotStatus.RUNNING) {
        await api.stopBotOnServer(bot.id);
        onUpdate({ ...bot, status: BotStatus.IDLE });
      } else {
        const updated = await api.saveBot(bot.owner_id, bot);
        if (updated) onUpdate(updated);
        setHasUnsavedChanges(false);
        const res = await api.startBotOnServer(bot);
        if (res === true) onUpdate({ ...(updated ?? bot), status: BotStatus.RUNNING });
        else alert(`Ошибка запуска: ${res}`);
      }
    } finally { setIsProcessing(false); }
  };

  // ── adminIds helper ──
  const [adminIdsRaw, setAdminIdsRaw] = React.useState(() => (bot.adminIds || []).join(', '));
  // Синхронизируем если бот сменился (смена вкладки)
  const prevBotId = React.useRef(bot.id);
  if (prevBotId.current !== bot.id) {
    prevBotId.current = bot.id;
    // В render нельзя вызывать setState — используем useEffect ниже
  }
  React.useEffect(() => {
    setAdminIdsRaw((bot.adminIds || []).join(', '));
  }, [bot.id]); // только при смене бота, не при каждом изменении
  const updateAdminIds = (str: string) => {
    setAdminIdsRaw(str); // сохраняем сырую строку — не теряем незаконченный ввод
    const ids = str.split(',').map(s => s.trim()).filter(s => /^\d+$/.test(s)).map(Number);
    handleLocalUpdate({ ...bot, adminIds: ids });
  };

  // ── Вкладки по типу бота ──
  // isSupportBot = все боты поддержки (TG + VK), isTgSupport = только TG
  const isTgSupport = isSupportBot && !isVK;
  const tabs = [
    { id: 'settings',   label: 'Основные',     icon: Settings,  show: true          },
    { id: 'interface',  label: 'Интерфейс',    icon: Ticket,    show: isSupportBot  },
    { id: 'logic',      label: 'Логика',       icon: Zap,       show: isSupportBot  },
    { id: 'staff',      label: 'Персонал',           icon: Users,     show: isSupportBot  },
    { id: 'ai',         label: 'ИИ-Ассистент', icon: Brain,     show: isSupportBot  },
    { id: 'miniapps',   label: 'Мини-апп',     icon: AppWindow, show: isSupportBot  },
    { id: 'stats',      label: 'Аналитика',    icon: BarChart3, show: true          },
    { id: 'logs',       label: 'Терминал',     icon: Terminal,  show: true          },
  ].filter((t: any) => t.show);
  
  // ── Иконка заголовка ──
  const HeaderIcon = isPoster ? Send : isRandomizer ? Shuffle : (isVK ? Globe : Cpu);
  const platformColor = isPoster ? 'text-emerald-500' : isRandomizer ? 'text-purple-500' : isVK ? 'text-sky-500' : 'text-blue-500';
  const platformBadge = isPoster ? 'Постинг' : isRandomizer ? 'Рандомайзер' : isVK ? 'VK' : 'Telegram';
  const badgeStyle    = isPoster ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' :
                        isRandomizer ? 'bg-purple-500/10 border-purple-500/20 text-purple-400' :
                        isVK ? 'bg-sky-500/10 border-sky-500/20 text-sky-400' :
                        'bg-blue-500/10 border-blue-500/20 text-blue-400';

  const globalPointerStyle = (
  <style>{`
    .bot-editor-container button,
    .bot-editor-container select,
    .bot-editor-container a,
    .bot-editor-container [role="button"] { cursor: pointer !important; }
    .bot-editor-container input[type="text"],
    .bot-editor-container input[type="password"],
    .bot-editor-container textarea { cursor: text !important; }
    .bot-editor-container input[type="number"] { cursor: ns-resize !important; }
    .bot-editor-container button:disabled,
    .bot-editor-container input:disabled,
    .bot-editor-container select:disabled { cursor: not-allowed !important; opacity: 0.5; }
    .bot-editor-container button:hover:not(:disabled) { opacity: 0.88; }
    .no-scrollbar::-webkit-scrollbar { display: none; }
    .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
  `}</style>
);

  // ── Превью-чат с ИИ ──
  const sendAiChat = async () => {
    const text = aiChatInput.trim();
    if (!text || aiChatLoading) return;
    setAiChatInput('');
    setAiChatMsgs(prev => [...prev, { role: 'user', text }]);
    setAiChatLoading(true);
    try {
      const r = await fetch('/api/ai/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          botId: bot.id,
          message: text,
          systemPrompt: bot.ai?.systemPrompt || 'Ты полезный ИИ-ассистент.',
          model: bot.ai?.model || 'turbo',
          maxTokens: bot.ai?.maxTokensPerReply || 800,
        })
      });
      const data = await r.json();
      setAiChatMsgs(prev => [...prev, { role: 'ai', text: data.reply || '⚠️ Нет ответа' }]);
      fetch(`/api/ai/balance/${bot.id}`).then(r => r.json()).then(setAiBalance).catch(() => {});
    } catch {
      setAiChatMsgs(prev => [...prev, { role: 'ai', text: '❌ Ошибка соединения' }]);
    } finally {
      setAiChatLoading(false);
    }
  };

  return (
    <div className="bot-editor-container space-y-8 animate-in fade-in duration-500 pb-20">
      {globalPointerStyle}

      {/* ══════════════════════════════════════════
          AI CHAT PANEL — fullscreen overlay
      ══════════════════════════════════════════ */}
      {aiChatOpen && (
        <div
          className="fixed inset-0 z-[200] bg-black/75 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={e => { if (e.target === e.currentTarget) setAiChatOpen(false); }}
        >
          <div className="w-full max-w-2xl h-[85vh] bg-[#0d0d0d] border border-zinc-700 rounded-[2.5rem] flex flex-col shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
            {/* Шапка */}
            <div className="flex items-center justify-between px-8 py-5 border-b border-zinc-800 bg-[#111] shrink-0">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
                  <Brain className="w-4 h-4 text-purple-400" />
                </div>
                <div>
                  <p className="text-sm font-black text-white">ИИ-ассистент · превью</p>
                  <p className="text-[9px] text-zinc-500 font-bold">{bot.ai?.model || 'turbo'} · {bot.ai?.systemPrompt ? 'кастомный промпт' : 'дефолтный промпт'}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                {aiBalance && (
                  <span className="text-[9px] text-amber-400 font-bold bg-amber-500/10 px-3 py-1.5 rounded-lg border border-amber-500/20">
                    {aiBalance.tokens_balance.toLocaleString()} токенов
                  </span>
                )}
                <button
                  onClick={() => { setAiChatOpen(false); setAiChatMsgs([]); }}
                  className="w-9 h-9 rounded-xl bg-zinc-800 hover:bg-rose-500/20 text-zinc-400 hover:text-rose-400 transition-all flex items-center justify-center"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Лента сообщений */}
            <div className="flex-1 overflow-y-auto p-6 space-y-3">
              {aiChatMsgs.length === 0 && (
                <div className="flex flex-col items-center justify-center h-full gap-3 opacity-25 select-none">
                  <Brain className="w-14 h-14 text-purple-400" />
                  <p className="text-xs text-zinc-500 font-bold uppercase tracking-widest">Задайте вопрос ИИ</p>
                  {bot.ai?.systemPrompt && (
                    <p className="text-[9px] text-zinc-600 text-center max-w-xs">
                      «{bot.ai.systemPrompt.slice(0, 90)}{bot.ai.systemPrompt.length > 90 ? '…' : ''}»
                    </p>
                  )}
                </div>
              )}
              {aiChatMsgs.map((msg, idx) => (
                <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[78%] px-5 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap break-words ${
                    msg.role === 'user'
                      ? 'bg-blue-600 text-white rounded-br-sm'
                      : 'bg-zinc-800/80 text-zinc-100 rounded-bl-sm border border-zinc-700'
                  }`}>
                    {msg.role === 'ai' && <span className="block text-[8px] text-purple-400 font-black uppercase mb-1 tracking-widest">ИИ</span>}
                    {msg.text}
                  </div>
                </div>
              ))}
              {aiChatLoading && (
                <div className="flex justify-start">
                  <div className="bg-zinc-800/80 border border-zinc-700 px-5 py-4 rounded-2xl rounded-bl-sm flex items-center gap-1.5">
                    {[0, 150, 300].map(d => (
                      <span key={d} className="w-1.5 h-1.5 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: `${d}ms` }} />
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Ввод */}
            <div className="p-4 border-t border-zinc-800 bg-[#111] shrink-0">
              <div className="flex gap-3">
                <input
                  className="flex-1 bg-black border border-zinc-700 rounded-2xl px-5 py-4 text-sm text-white outline-none focus:border-purple-500 transition-all"
                  placeholder="Введите сообщение..."
                  value={aiChatInput}
                  onChange={e => setAiChatInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendAiChat(); } }}
                  autoFocus
                />
                <button
                  onClick={sendAiChat}
                  disabled={aiChatLoading || !aiChatInput.trim()}
                  className="w-14 h-14 rounded-2xl bg-purple-600 hover:bg-purple-500 disabled:opacity-30 text-white flex items-center justify-center transition-all shadow-lg shadow-purple-600/20 shrink-0"
                >
                  <Send className="w-5 h-5" />
                </button>
              </div>
              <p className="text-[8px] text-zinc-600 mt-2 ml-2">Enter — отправить · Shift+Enter — новая строка</p>
            </div>
          </div>
        </div>
      )}

      {/* Баннер несохранённых изменений */}
      {hasUnsavedChanges && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[100] bg-blue-600 text-white px-4 md:px-8 py-3 md:py-4 rounded-2xl shadow-2xl flex items-center gap-3 md:gap-4 max-w-[90vw]">
          <AlertCircle className="w-4 h-4 md:w-5 md:h-5 shrink-0" />
          <span className="text-[10px] md:text-xs font-black uppercase tracking-widest">Несохранённые изменения!</span>
          <button onClick={syncState} disabled={isProcessing} className="bg-white text-blue-600 px-3 md:px-4 py-1.5 rounded-xl font-black text-[10px] uppercase shrink-0">
            Сохранить
          </button>
        </div>
      )}

      {/* Шапка */}
      <header className="bg-[#111] border border-zinc-800 p-6 md:p-8 rounded-[2.5rem] flex flex-col md:flex-row justify-between items-start md:items-center gap-4 shadow-2xl">
        <div className="flex items-center gap-4 md:gap-6">
          <div className={`w-14 h-14 md:w-16 md:h-16 rounded-2xl flex items-center justify-center border-2 ${bot.status === BotStatus.RUNNING ? `border-current/30 bg-current/5 ${platformColor}` : 'bg-zinc-900 border-zinc-800 text-zinc-600'}`}>
            <HeaderIcon className="w-7 h-7 md:w-8 md:h-8" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl md:text-3xl font-black text-white">{bot.name}</h1>
              <span className={`px-2 py-1 rounded-lg text-[8px] font-black uppercase tracking-widest border ${badgeStyle}`}>{platformBadge}</span>
              {isAdminMode && <span className="px-2 py-1 bg-orange-500/10 border border-orange-500/20 rounded-lg text-orange-500 text-[8px] font-black uppercase tracking-widest">Support</span>}
            </div>
            <div className="flex items-center gap-2 mt-1">
              <span className={`w-2 h-2 rounded-full ${bot.status === BotStatus.RUNNING ? 'bg-blue-500 animate-pulse' : 'bg-zinc-600'}`}></span>
              <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{bot.status}</span>
            </div>
          </div>
        </div>
        <div className="flex gap-3 w-full md:w-auto">
          <button onClick={syncState} disabled={isProcessing} className={`flex-1 md:flex-none px-4 md:px-6 py-3 md:py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest flex items-center justify-center gap-2 transition-all ${hasUnsavedChanges ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}`}>
            <Save className="w-4 h-4" /> Сохранить
          </button>
          <button onClick={handleToggleServer} disabled={isProcessing} className={`flex-1 md:flex-none px-6 md:px-10 py-3 md:py-4 rounded-2xl font-black text-xs uppercase flex items-center justify-center gap-2 shadow-xl transition-all ${bot.status === BotStatus.RUNNING ? 'bg-red-500/10 text-red-500 border border-red-500/20' : 'bg-blue-600 text-white'}`}>
            <Power className="w-4 h-4" /> {bot.status === BotStatus.RUNNING ? 'Стоп' : 'Запустить'}
          </button>
        </div>
      </header>

      {/* Вкладки */}
<div className="flex gap-1 border-b border-zinc-800 overflow-x-auto no-scrollbar -mx-1 px-1">
  {tabs.map(t => (
      <button 
        key={t.id} 
        onClick={() => setActiveTab(t.id as any)}
        className={`px-3 md:px-6 py-3 md:py-4 text-[9px] md:text-[10px] font-black uppercase tracking-widest border-b-2 transition-all flex items-center gap-1.5 whitespace-nowrap ${
          activeTab === t.id ? 'border-blue-500 text-blue-500' : 'border-transparent text-zinc-500'
        }`}
      >
        <t.icon className="w-3 h-3 md:w-3.5 md:h-3.5" />
        <span className="hidden sm:inline">{t.label}</span>
        <span className="sm:hidden">{t.label.slice(0, 3)}</span>
      </button>
  ))}
</div>

      {/* ════════════════════════════════════════════
          ВКЛАДКА: НАСТРОЙКИ
      ════════════════════════════════════════════ */}
      {activeTab === 'settings' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 animate-in fade-in slide-in-from-bottom-4 duration-500">

          {/* ══ ТИП БОТА — всегда col-span-2 ══ */}
          <div className="lg:col-span-2">
            <div className="bg-[#111] border border-zinc-800 p-6 rounded-[2.5rem]">
              <h2 className="text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                <ChevronDown className="w-3 h-3" /> Тип бота
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {([
                  { id: 'telegram',   label: 'TG Поддержка', sub: 'Чат с пользователями',  Icon: Smartphone, active: 'bg-blue-600/10 border-blue-500 text-blue-400'    },
                  { id: 'vk',         label: 'VK Поддержка', sub: 'Беседа ВКонтакте',       Icon: Globe,      active: 'bg-sky-600/10 border-sky-500 text-sky-400'        },
                  { id: 'poster',     label: 'TG Постинг',   sub: 'Публикация в канал',     Icon: Send,       active: 'bg-emerald-600/10 border-emerald-500 text-emerald-400' },
                  { id: 'randomizer', label: 'Рандомайзер',  sub: 'Розыгрыши и конкурсы',  Icon: Shuffle,    active: 'bg-purple-600/10 border-purple-500 text-purple-400' },
                ] as const).map(({ id, label, sub, Icon, active }) => (
                  <button key={id} type="button"
                    onClick={() => handleLocalUpdate({ ...bot, platform: id as any })}
                    className={`flex items-center gap-3 p-4 rounded-2xl border text-left transition-all ${
                      bot.platform === id ? active : 'bg-black border-zinc-800 text-zinc-500 hover:border-zinc-700'
                    }`}>
                    <Icon className="w-4 h-4 shrink-0" />
                    <div>
                      <div className="text-[10px] font-black uppercase">{label}</div>
                      <div className="text-[8px] opacity-60 font-medium">{sub}</div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Левая колонка */}
          <div className="space-y-8">
            <section className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
              <h2 className="text-sm font-black text-white uppercase flex items-center gap-2">
                <Settings className="w-4 h-4 text-blue-500" /> Основные настройки
              </h2>
              <div className="space-y-5">

                {/* Токен */}
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">
                    {isVK ? 'ВКонтакте Access Token' : 'Telegram Bot Token'}
                  </span>
                  <input type="password"
                    placeholder={isVK ? 'Введите токен доступа группы' : 'Токен от @BotFather'}
                    className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white font-mono outline-none focus:border-blue-500 transition-all"
                    value={bot.token}
                    onChange={e => handleLocalUpdate({ ...bot, token: e.target.value })} />
                </label>

                {/* Группа/Форум — для support-ботов */}
                {isSupportBot && (
                  <label className="block">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">
                      {isVK ? 'ID беседы (peer_id)' : 'ID Группы Админов (Forum)'}
                    </span>
                    <input type="text"
                      placeholder={isVK ? '2000000010' : '-100...'}
                      className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white outline-none focus:border-blue-500 transition-all"
                      value={isVK ? (bot.vkGroupId ?? bot.vk_group_id ?? '') : (bot.adminChatId ?? '')}
                      onChange={e => isVK
                        ? handleLocalUpdate({ ...bot, vkGroupId: e.target.value, vk_group_id: e.target.value })
                        : handleLocalUpdate({ ...bot, adminChatId: e.target.value })} />
                    {isVK && <p className="text-[8px] text-zinc-600 mt-1.5 ml-2 uppercase font-bold tracking-wider">peer_id беседы ВКонтакте: напр. 2000000010</p>}
                  </label>
                )}

                {/* Каналы — для постера (список) */}
                {isPoster && (
                  <div className="space-y-3">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2 flex items-center gap-1.5">
                      <Hash className="w-3 h-3 text-emerald-500" />Каналы для публикации
                    </span>
                    {(bot.channels || (bot.channelId ? [bot.channelId] : [])).map((ch: string, i: number) => (
                      <div key={i} className="flex gap-2">
                        <input type="text"
                          className="flex-1 bg-black border border-zinc-800 p-4 rounded-2xl text-white text-sm outline-none focus:border-emerald-500 transition-all"
                          value={ch}
                          placeholder="@mychannel или -1001234567890"
                          onChange={e => {
                            const chs = [...(bot.channels || [bot.channelId || ''])];
                            chs[i] = e.target.value;
                            handleLocalUpdate({ ...bot, channels: chs, channelId: chs[0] || '' });
                          }} />
                        <button type="button"
                          onClick={() => {
                            const chs = (bot.channels || [bot.channelId || '']).filter((_: string, idx: number) => idx !== i);
                            handleLocalUpdate({ ...bot, channels: chs, channelId: chs[0] || '' });
                          }}
                          className="px-3 py-2 rounded-xl bg-rose-500/10 text-rose-500 hover:bg-rose-500/20 transition-all text-xs font-bold">
                          ✕
                        </button>
                      </div>
                    ))}
                    <button type="button"
                      onClick={() => {
                        const chs = [...(bot.channels || (bot.channelId ? [bot.channelId] : []))];
                        chs.push('');
                        handleLocalUpdate({ ...bot, channels: chs });
                      }}
                      className="w-full py-3 rounded-2xl border border-dashed border-emerald-500/30 text-emerald-500 text-[10px] font-black uppercase tracking-wider hover:bg-emerald-500/5 transition-all">
                      + Добавить канал
                    </button>
                    <p className="text-[8px] text-zinc-600 ml-2 uppercase font-bold">Бот должен быть администратором каждого канала</p>
                  </div>
                )}

                {/* Канал + ссылка — для рандомайзера */}
                {isRandomizer && (<>
                  <label className="block">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2 flex items-center gap-1.5">
                      <Hash className="w-3 h-3 text-purple-500" />Канал розыгрышей
                    </span>
                    <input type="text"
                      placeholder="@lotchannel или -1001234567890"
                      className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white outline-none focus:border-purple-500 transition-all"
                      value={bot.lotChannel || ''}
                      onChange={e => handleLocalUpdate({ ...bot, lotChannel: e.target.value })} />
                    <p className="text-[8px] text-zinc-600 mt-1.5 ml-2 uppercase font-bold">Бот — администратор этого канала</p>
                  </label>
                  <label className="block">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2 flex items-center gap-1.5">
                      <Link className="w-3 h-3 text-purple-400" />Username бота
                    </span>
                    <input type="text"
                      placeholder="@MyLotteryBot"
                      className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white outline-none focus:border-purple-500 transition-all"
                      value={bot.botLink || ''}
                      onChange={e => handleLocalUpdate({ ...bot, botLink: e.target.value })} />
                    <p className="text-[8px] text-zinc-600 mt-1.5 ml-2 uppercase font-bold">Для генерации deep-link ссылок участия</p>
                  </label>
                </>)}

                {/* ID администраторов — для всех типов */}
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2 flex items-center gap-1.5">
                    <Users className="w-3 h-3 text-amber-500" />ID администраторов бота
                  </span>
                  <input type="text"
                    placeholder="123456789, 987654321"
                    className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white outline-none focus:border-amber-500 transition-all"
                    value={adminIdsRaw}
                    onChange={e => updateAdminIds(e.target.value)} />
                  <p className="text-[8px] text-zinc-600 mt-1.5 ml-2 uppercase font-bold tracking-wider">
                    {isPoster || isRandomizer ? 'Только эти пользователи могут управлять ботом' : 'Могут делать /broadcast прямо в боте'}
                  </p>
                </label>

                {/* Username бота — только для TG, для DVR защиты */}
                {!isVK && (
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2 flex items-center gap-1.5">
                    <span className="text-amber-500 font-black">@</span>Username бота
                  </span>
                  <input type="text"
                    placeholder="mybot (без @)"
                    className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white outline-none focus:border-amber-500 transition-all"
                    value={(bot.botUsername || '').replace('@', '')}
                    onChange={e => handleLocalUpdate({ ...bot, botUsername: e.target.value.replace('@', '').toLowerCase().trim() })} />
                  <p className="text-[8px] text-zinc-600 mt-1.5 ml-2 uppercase font-bold tracking-wider">
                    Система защиты DVR использует username для остановки бота при рейде
                  </p>
                </label>
                )}

                {/* Приветствие — не для постера */}
                {!isPoster && (
                  <div className="space-y-4">
                    <label className="block">
                      <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">
                        {isVK ? 'Текст приветствия' : 'Приветствие (/start)'}
                      </span>
                      <textarea
                        placeholder="Текст для команды /start"
                        className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white min-h-[100px] outline-none text-xs focus:border-blue-500 transition-all resize-none"
                        value={bot.welcomeMessage || ''}
                        onChange={e => handleLocalUpdate({ ...bot, welcomeMessage: e.target.value })} />
                    </label>

                    {/* Стартовое фото — для всех support-ботов */}
                    {isSupportBot && (
                      <label className="block">
                        <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2 flex items-center gap-1.5">
                          <Image className="w-3 h-3 text-blue-400" />
                          {isVK ? 'Фото к приветствию (опционально)' : 'Фото к /start (опционально)'}
                        </span>
                        <div className="mt-2">
                          <input
                            placeholder="Вставьте прямую ссылку на фото (https://...)"
                            className="w-full bg-black border border-zinc-800 p-4 rounded-2xl text-white text-xs outline-none focus:border-blue-500 transition-all"
                            value={bot.welcomePhoto || ''}
                            onChange={e => handleLocalUpdate({ ...bot, welcomePhoto: e.target.value })}
                          />
                        </div>
                        {bot.welcomePhoto && (
                          <div className="mt-3 relative inline-block">
                            <img
                              src={bot.welcomePhoto}
                              alt="preview"
                              className="h-32 rounded-2xl object-cover border border-zinc-800 shadow-lg"
                              onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
                            />
                            <div className="absolute top-2 left-2 bg-black/50 px-2 py-1 rounded text-[8px] text-white uppercase font-bold backdrop-blur-sm">
                              Превью
                            </div>
                          </div>
                        )}
                        <p className="text-[8px] text-zinc-600 mt-1.5 ml-2 uppercase font-bold">
                          {isVK ? 'Бот прикрепит фото к первому сообщению пользователя' : 'Бот отправит это фото первым сообщением вместе с текстом приветствия'}
                        </p>
                      </label>
                    )}

                    {/* Инлайн-кнопки к /start (TG + VK) */}
                    {isSupportBot && (
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2 flex items-center gap-1.5">
                            <ExternalLink className="w-3 h-3 text-indigo-400" />
                            {isVK ? 'URL-кнопки к приветствию (VK OpenLink)' : 'Инлайн-кнопки к /start'}
                          </span>
                          <button type="button"
                            onClick={() => handleLocalUpdate({ ...bot, welcomeInline: [...(bot.welcomeInline || []), { text: '', url: '' }] })}
                            className="text-[9px] text-indigo-400 font-bold hover:text-indigo-300 uppercase tracking-wider">
                            + Добавить
                          </button>
                        </div>

                        {isVK && (
                          <p className="text-[8px] text-sky-400/60 ml-2 bg-sky-500/5 border border-sky-500/10 rounded-xl p-2.5 leading-relaxed">
                            💡 В VK кнопки-ссылки отправляются как инлайн-кнопка (OpenLink) вместе с приветствием. 
                          </p>
                        )}

                        {(bot.welcomeInline || []).map((btn: any, wi: number) => (
                          <div key={wi} className="flex gap-2">
                            <input placeholder="Текст кнопки"
                              className={`flex-1 bg-black border border-zinc-800 p-3 rounded-xl text-xs text-white outline-none transition-all ${isVK ? 'focus:border-sky-500' : 'focus:border-indigo-500'}`}
                              value={btn.text}
                              onChange={e => {
                                const wb = [...(bot.welcomeInline || [])];
                                wb[wi] = { ...wb[wi], text: e.target.value };
                                handleLocalUpdate({ ...bot, welcomeInline: wb });
                              }} />
                            <input placeholder="https://..."
                              className={`flex-1 bg-black border border-zinc-800 p-3 rounded-xl text-xs text-white outline-none transition-all ${isVK ? 'focus:border-sky-500' : 'focus:border-indigo-500'}`}
                              value={btn.url}
                              onChange={e => {
                                const wb = [...(bot.welcomeInline || [])];
                                wb[wi] = { ...wb[wi], url: e.target.value };
                                handleLocalUpdate({ ...bot, welcomeInline: wb });
                              }} />
                            <button type="button"
                              onClick={() => handleLocalUpdate({ ...bot, welcomeInline: (bot.welcomeInline || []).filter((_: any, ii: number) => ii !== wi) })}
                              className="px-2 text-zinc-600 hover:text-rose-500 transition-colors">
                              <X className="w-4 h-4" />
                            </button>
                          </div>
                        ))}

                        {/* Превью стартового сообщения */}
                        {(bot.welcomeMessage || (bot.welcomeInline || []).length > 0) && (
                          <div className="mt-1 bg-black/50 border border-zinc-800 rounded-2xl p-4">
                            <p className="text-[8px] text-zinc-600 uppercase font-black mb-3 flex items-center gap-1.5">
                              <Smartphone className="w-2.5 h-2.5" />Превью {isVK ? 'в VK' : 'в Telegram'}
                            </p>
                            <div className={`rounded-2xl rounded-bl-sm p-3.5 max-w-[85%] mb-2 ${isVK ? 'bg-sky-950/40 border border-sky-900/30' : 'bg-zinc-900'}`}>
                              {bot.welcomePhoto && (
                                <div className="w-full h-20 bg-zinc-800 rounded-xl mb-2 overflow-hidden">
                                  <img src={bot.welcomePhoto} className="w-full h-full object-cover"
                                    onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }} alt="" />
                                </div>
                              )}
                              <p className="text-[10px] text-zinc-300 leading-relaxed whitespace-pre-wrap break-words">
                                {(bot.welcomeMessage || 'Привет!').slice(0, 120)}{(bot.welcomeMessage || '').length > 120 ? '…' : ''}
                              </p>
                            </div>
                            {(bot.welcomeInline || []).filter((b: any) => b.text).map((b: any, pi: number) => (
                              <div key={pi} className={`rounded-xl py-2 px-4 mb-1.5 text-center flex items-center justify-center gap-1.5 ${
                                isVK
                                  ? 'bg-sky-500/10 border border-sky-500/20'
                                  : 'bg-indigo-500/10 border border-indigo-500/20'
                              }`}>
                                {isVK && <ExternalLink className="w-2.5 h-2.5 text-sky-400/60 shrink-0" />}
                                <span className={`text-[10px] font-semibold ${isVK ? 'text-sky-300' : 'text-indigo-300'}`}>{b.text}</span>
                                {b.url && <span className="text-[8px] text-zinc-600 ml-1">{b.url.replace('https://', '').slice(0, 25)}</span>}
                              </div>
                            ))}
                            <p className="text-[7px] text-zinc-700 uppercase mt-1.5">
                              {isVK ? '↑ OpenLink-кнопки в VK (инлайн под сообщением)' : '↑ Кнопки прикреплены к сообщению в TG'}
                            </p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )} {/* <=== ВОТ ОНА, ТА САМАЯ ПОТЕРЯННАЯ СКОБКА (Закрывает !isPoster) */}

                <p className="text-[8px] text-zinc-600 uppercase font-black tracking-widest opacity-50 ml-2 mt-4">
                  * Данные синхронизируются (из файла .env)
                </p>
              </div>
            </section>

            {/* Инфо-плашки для постера/рандомайзера */}
            {isPoster && (
              <div className="bg-emerald-500/5 border border-emerald-500/20 p-8 rounded-[2.5rem] space-y-3">
                <h3 className="text-sm font-black text-emerald-400 uppercase flex items-center gap-2">
                  <Send className="w-4 h-4" />Бот постинга — возможности
                </h3>
                <div className="text-[10px] text-zinc-400 leading-relaxed space-y-1.5">
                  <p>✅ <b>Контент:</b> текст, фото, видео, GIF, аудио, документ, стикер</p>
                  <p>✅ <b>Форматирование:</b> выделяй текст прямо в Telegram — жирный, курсив, код</p>
                  <p>✅ <b>Несколько каналов:</b> публикация в один или все сразу</p>
                  <p>✅ <b>Кнопки:</b> <code className="text-emerald-400">Текст | https://url</code> · столбцом или строчкой</p>
                  <p>✅ <b>Расписание:</b> через N минут / часов или точная дата</p>
                  <p>✅ <b>Очередь постов:</b> список запланированных + отмена</p>
                  <p className="text-zinc-600 mt-2">Управление: /start → wizard</p>
                </div>
              </div>
            )}

            {isRandomizer && (
              <div className="bg-purple-500/5 border border-purple-500/20 p-8 rounded-[2.5rem] space-y-3">
                <h3 className="text-sm font-black text-purple-400 uppercase flex items-center gap-2">
                  <Shuffle className="w-4 h-4" />Рандомайзер — возможности
                </h3>
                <div className="text-[10px] text-zinc-400 leading-relaxed space-y-1.5">
                  <p>✅ <b>Розыгрыши</b> с публикацией в канал + кнопкой «Участвовать»</p>
                  <p>✅ <b>Проверка подписки</b> на канал перед участием</p>
                  <p>✅ <b>Финиш</b>: по времени или по числу участников</p>
                  <p>✅ <b>Авто-выбор победителей</b> и уведомление</p>
                  <p>✅ <b>/broadcast</b> — рассылка по всем участникам</p>
                  <p className="text-zinc-600 mt-2">Управление: /start → 🛠 Панель → Создать розыгрыш</p>
                </div>
              </div>
            )}

            {/* Конструктор шапки — только для support-ботов */}
            {isSupportBot && (
              <section className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
                <h2 className="text-sm font-black text-white uppercase flex items-center gap-2">
                  <Layout className="w-4 h-4 text-emerald-500" />Конструктор шапки сообщений
                  {isVK && <span className="text-[9px] bg-sky-500/20 text-sky-400 px-2 py-0.5 rounded-md ml-auto font-normal normal-case">VK: plain text, HTML не поддерживается</span>}
                </h2>
                <div className="space-y-4">
                  {[
                    { key: 'firstMessageHeader',  label: 'Заголовок первого обращения', ph: isVK ? '🆕 ПЕРВОЕ ОБРАЩЕНИЕ:' : '🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>' },
                    { key: 'ticketMessageHeader',  label: 'Заголовок заявки (кнопки)',  ph: isVK ? '🆘 ЗАЯВКА [{btn}]:'   : '🆘 <b>ЗАЯВКА [{btn}]:</b>'  },
                    { key: 'commonMessageHeader',  label: 'Обычное сообщение',          ph: isVK ? '📩 СООБЩЕНИЕ:'        : '📩 <b>СООБЩЕНИЕ:</b>'        },
                  ].map(f => (
                    <div key={f.key}>
                      <span className="text-[9px] font-bold text-zinc-500 uppercase ml-2">{f.label}</span>
                      <input
                        className="w-full mt-1.5 bg-black border border-zinc-800 p-4 rounded-xl text-xs text-white outline-none focus:border-emerald-500 transition-all"
                        value={safeSettings[f.key as keyof typeof safeSettings] as string || ''}
                        onChange={e => updateSetting(f.key as any, e.target.value)}
                        placeholder={f.ph} />
                    </div>
                  ))}
                </div>
                <div className="grid grid-cols-3 gap-3 pt-2">
                  {[{k:'showHeaderName',l:'Имя'},{k:'showHeaderUsername',l:'Юзер'},{k:'showHeaderId',l:'ID'}].map(f => (
                    <button key={f.k} onClick={() => updateSetting(f.k as any, !safeSettings[f.k as keyof typeof safeSettings])}
                      className={`flex items-center justify-between p-4 rounded-xl border text-[9px] font-bold uppercase transition-all ${safeSettings[f.k as keyof typeof safeSettings] ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-black border-zinc-800 text-zinc-600'}`}>
                      {f.l} {safeSettings[f.k as keyof typeof safeSettings] ? <CheckSquare className="w-3 h-3" /> : <Square className="w-3 h-3" />}
                    </button>
                  ))}
                </div>
              </section>
            )}
          </div>

          {/* Правая колонка — только для support-ботов */}
          {isSupportBot && (
            <div className="space-y-8">
              <section className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
                <h3 className="text-sm font-black text-white uppercase flex items-center gap-2">
                  <Lock className="w-4 h-4 text-rose-500" />Безопасность и Анти-Флуд
                </h3>
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-5 rounded-2xl bg-black border border-zinc-800">
                    <div><p className="text-xs font-bold text-white">Интервал анти-спама</p><p className="text-[9px] text-zinc-500 uppercase">Сек. между сообщениями</p></div>
                    <input type="number" step="0.5" className="w-16 bg-zinc-900 border border-zinc-800 p-2 rounded-lg text-center text-xs text-white"
                      value={safeSettings.rateLimit} onChange={e => updateSetting('rateLimit', parseFloat(e.target.value))} />
                  </div>
                  <div className="flex items-center justify-between p-5 rounded-2xl bg-black border border-zinc-800">
                    <div><p className="text-xs font-bold text-white">Лимит Предупреждений</p><p className="text-[9px] text-zinc-500 uppercase">Варнов до авто-бана</p></div>
                    <input type="number" className="w-16 bg-zinc-900 border border-zinc-800 p-2 rounded-lg text-center text-xs text-white"
                      value={safeSettings.autoBanThreshold} onChange={e => updateSetting('autoBanThreshold', parseInt(e.target.value))} />
                  </div>
                </div>
              </section>

              {/* ══ MEMORY BASE ══ */}
              {!isVK && (
                <section className="bg-[#111] border border-red-900/30 p-8 rounded-[2.5rem] space-y-5">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-black text-white uppercase flex items-center gap-2">
                      <ShieldAlert className="w-4 h-4 text-red-400" />MemoryBase Антиспам
                    </h3>
                    <button
                      onClick={() => updateSetting('memoryBaseEnabled' as any, !(safeSettings as any).memoryBaseEnabled)}
                      className={`flex items-center gap-2 px-4 py-2 rounded-xl text-[9px] font-black uppercase border transition-all ${
                        (safeSettings as any).memoryBaseEnabled
                          ? 'bg-red-500/15 border-red-500/30 text-red-300'
                          : 'bg-black border-zinc-800 text-zinc-500'
                      }`}
                    >
                      {(safeSettings as any).memoryBaseEnabled ? <ToggleRight className="w-4 h-4" /> : <ToggleLeft className="w-4 h-4" />}
                      {(safeSettings as any).memoryBaseEnabled ? 'Включено' : 'Выключено'}
                    </button>
                  </div>

                  {(safeSettings as any).memoryBaseEnabled && (
                    <div className="space-y-4 animate-in fade-in duration-200">
                      <p className="text-[10px] text-zinc-400 leading-relaxed bg-red-500/5 border border-red-500/10 rounded-xl p-3">
                        🛡️ Бот проверяет каждого нового пользователя по антиспам-базе{' '}
                        <a href="https://t.me/MemoryBaseBot" target="_blank" rel="noreferrer" className="text-red-300 underline">@MemoryBaseBot</a>.
                        При совпадении — ограничивает доступ и уведомляет администраторов.
                      </p>

                      <div>
                        <p className="text-[10px] font-bold text-zinc-400 uppercase mb-3">
                          Блокировать при причинах:
                        </p>
                        <p className="text-[9px] text-zinc-600 mb-3">Если ничего не выбрано — блокировать при любой причине</p>
                        {[
                          { id: 'scammer',      label: 'Мошенник ⛔️',            color: 'rose'   },
                          { id: 'bad_admin',    label: 'Плохой администратор ❌', color: 'orange' },
                          { id: 'bad_owner',    label: 'Плохой владелец ❌',      color: 'amber'  },
                          { id: 'bad_behavior', label: 'Петушара / Нарушитель 🐔', color: 'yellow' },
                          { id: 'spammer',      label: 'Спамер 🚫',              color: 'red'    },
                          { id: 'raider',       label: 'Рейдер 💥',              color: 'purple' },
                        ].map(({ id, label, color }) => {
                          const reasons: string[] = (safeSettings as any).memoryBaseBlockReasons || [];
                          const active = reasons.includes(id);
                          const toggleReason = () => {
                            const newReasons = active
                              ? reasons.filter((r: string) => r !== id)
                              : [...reasons, id];
                            updateSetting('memoryBaseBlockReasons' as any, newReasons);
                          };
                          return (
                            <button key={id} onClick={toggleReason}
                              className={`w-full flex items-center justify-between p-4 rounded-xl border text-left transition-all mb-2 ${
                                active
                                  ? `bg-${color}-500/10 border-${color}-500/30 text-${color}-300`
                                  : 'bg-black border-zinc-800 text-zinc-500'
                              }`}>
                              <span className="text-xs font-bold">{label}</span>
                              {active ? <CheckSquare className="w-4 h-4 shrink-0" /> : <Square className="w-4 h-4 shrink-0" />}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </section>
              )}

              {/* ══ DVR МОНИТОРИНГ ══ */}
              {!isVK && (
                <section className="bg-[#111] border border-purple-900/30 p-8 rounded-[2.5rem] space-y-5">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-black text-white uppercase flex items-center gap-2">
                      <ShieldAlert className="w-4 h-4 text-purple-400" />DVR Анти-Рейд
                    </h3>
                    <button
                      onClick={() => updateSetting('dvrEnabled' as any, !(safeSettings as any).dvrEnabled)}
                      className={`flex items-center gap-2 px-4 py-2 rounded-xl text-[9px] font-black uppercase border transition-all ${
                        (safeSettings as any).dvrEnabled
                          ? 'bg-purple-500/15 border-purple-500/30 text-purple-300'
                          : 'bg-black border-zinc-800 text-zinc-500'
                      }`}
                    >
                      {(safeSettings as any).dvrEnabled ? <ToggleRight className="w-4 h-4" /> : <ToggleLeft className="w-4 h-4" />}
                      {(safeSettings as any).dvrEnabled ? 'Включено' : 'Выключено'}
                    </button>
                  </div>
                  {(safeSettings as any).dvrEnabled ? (
                    <p className="text-[10px] text-purple-300/70 bg-purple-500/5 border border-purple-500/10 rounded-xl p-3 leading-relaxed">
                      💜 Мониторинг DVR рейд-канала активен. При обнаружении поста с упоминанием вашего бота — он будет автоматически остановлен, а вы получите уведомление в чат администраторов.
                    </p>
                  ) : (
                    <p className="text-[10px] text-zinc-600 leading-relaxed">
                      Автоматическая защита от рейдов DVR-проекта. Бот мониторит рейд-канал и экстренно останавливается при угрозе.
                    </p>
                  )}
                </section>
              )}

              <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-4">
                <h3 className="text-sm font-black text-white uppercase flex items-center gap-2">
                  <Send className="w-4 h-4 text-blue-400" />Режим пересылки
                </h3>
                <button
                  onClick={() => updateSetting('forwardAll' as any, !safeSettings['forwardAll' as keyof typeof safeSettings])}
                  className={`w-full flex items-center justify-between p-5 rounded-2xl border transition-all ${
                    safeSettings['forwardAll' as keyof typeof safeSettings]
                      ? 'bg-blue-500/10 border-blue-500/30 text-blue-400'
                      : 'bg-black border-zinc-800 text-zinc-600'
                  }`}>
                  <div className="text-left">
                    <p className="text-xs font-bold">Пересылать все сообщения в чат</p>
                    <p className="text-[9px] uppercase opacity-60">Без создания тикета — всё идёт в админ</p>
                  </div>
                  {safeSettings['forwardAll' as keyof typeof safeSettings]
                    ? <ToggleRight className="w-5 h-5 flex-shrink-0" />
                    : <ToggleLeft className="w-5 h-5 flex-shrink-0" />}
                </button>
                {safeSettings['forwardAll' as keyof typeof safeSettings] && (
                  <p className="text-[9px] text-blue-300/60 bg-blue-500/5 border border-blue-500/10 rounded-xl p-3 leading-relaxed">
                    💡 В этом режиме все сообщения пользователей после /start сразу пересылаются в админ-чат. Тикетные кнопки можно не добавлять.
                  </p>
                )}
              </div>

              <div className={`bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6 transition-all ${isVK ? 'opacity-40 select-none' : ''}`}>
                <h3 className="text-sm font-black text-white uppercase flex items-center gap-2">
                  <ShieldAlert className={`w-4 h-4 ${isVK ? 'text-zinc-500' : 'text-emerald-500'}`} />Форум (Темы)
                  {isVK && <span className="text-[9px] bg-rose-500/20 text-rose-500 px-2 py-0.5 rounded-md ml-auto">Только Telegram</span>}
                </h3>
                <div className="space-y-3">
                  {[
                    {k:'useTopics',       l:'Использовать Темы (Forum)', sub:'Для супергрупп',        c:'emerald'},
                    {k:'topicPerRequest', l:'Новая ветка на каждый тикет', sub:'Ticket System Mode', c:'blue'},
                    {k:'anonymousTopics', l:'Анонимные ID (Anon ID)', sub:'Хешировать данные',       c:'zinc'},
                  ].map(f => (
                    <button key={f.k} disabled={isVK}
                      onClick={() => updateSetting(f.k as any, !safeSettings[f.k as keyof typeof safeSettings])}
                      className={`w-full flex items-center justify-between p-5 rounded-2xl border transition-all ${
                        !isVK && safeSettings[f.k as keyof typeof safeSettings]
                          ? f.c === 'emerald' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                          : f.c === 'blue' ? 'bg-blue-500/10 border-blue-500/30 text-blue-400'
                          : 'bg-zinc-800 text-white'
                          : 'bg-black border-zinc-800 text-zinc-600'
                      }`}>
                      <div className="text-left">
                        <p className="text-xs font-bold">{f.l}</p>
                        <p className="text-[9px] uppercase opacity-50">{f.sub}</p>
                      </div>
                      {isVK ? <Lock className="w-4 h-4" /> : (safeSettings[f.k as keyof typeof safeSettings] ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />)}
                    </button>
                  ))}
                </div>
              </div>
              {/* ── ОБЯЗАТЕЛЬНАЯ ПОДПИСКА ── */}
              {!isVK && (
                <section className="bg-[#111] border border-violet-500/20 p-8 rounded-[2.5rem] space-y-5">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-black text-white uppercase flex items-center gap-2">
                      <Lock className="w-4 h-4 text-violet-400" />Обязательная подписка
                    </h3>
                    <button
                      onClick={() => {
                        const enabled = !(bot.requiredSubEnabled ?? false);
                        handleLocalUpdate({ ...bot, requiredSubEnabled: enabled });
                      }}
                      className={`flex items-center gap-2 px-4 py-2 rounded-xl text-[9px] font-black uppercase border transition-all ${
                        bot.requiredSubEnabled
                          ? 'bg-violet-500/15 border-violet-500/30 text-violet-300'
                          : 'bg-black border-zinc-800 text-zinc-500'
                      }`}
                    >
                      {bot.requiredSubEnabled
                        ? <ToggleRight className="w-4 h-4" />
                        : <ToggleLeft className="w-4 h-4" />}
                      {bot.requiredSubEnabled ? 'Включено' : 'Выключено'}
                    </button>
                  </div>

                  {/* Уведомление */}
                  <div className="bg-amber-500/8 border border-amber-500/20 rounded-2xl p-4 flex gap-3">
                    <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                    <div className="space-y-1">
                      <p className="text-[10px] font-black text-amber-300 uppercase tracking-wide">Перед добавлением канала/чата</p>
                      <p className="text-[9px] text-amber-400/70 leading-relaxed">
                        Бот <b>должен быть добавлен в канал/чат как администратор</b> (или хотя бы участник для публичных каналов), чтобы иметь возможность проверять подписку пользователей через <code className="text-amber-300">get_chat_member</code>.
                      </p>
                    </div>
                  </div>

                  {bot.requiredSubEnabled && (
                    <div className="space-y-4 animate-in fade-in duration-200">
                      <div className="space-y-3">
                        {((bot.requiredChannels || []) as any[]).map((ch: any, idx: number) => (
                          <div key={idx} className="bg-black border border-zinc-800 rounded-2xl p-4 space-y-3">
                            <div className="flex items-center justify-between">
                              <span className="text-[9px] font-black text-zinc-500 uppercase tracking-wider flex items-center gap-1.5">
                                <Hash className="w-2.5 h-2.5 text-violet-400" />Канал / Чат #{idx + 1}
                              </span>
                              <button
                                onClick={() => {
                                  const chs = (bot.requiredChannels || []).filter((_: any, i: number) => i !== idx);
                                  handleLocalUpdate({ ...bot, requiredChannels: chs });
                                }}
                                className="w-7 h-7 flex items-center justify-center rounded-lg bg-rose-500/10 text-rose-500 hover:bg-rose-500/20 transition-all"
                              >
                                <X className="w-3.5 h-3.5" />
                              </button>
                            </div>
                            <div className="grid grid-cols-1 gap-2">
                              <div>
                                <span className="text-[8px] text-zinc-600 uppercase font-bold ml-1">ID канала / чата</span>
                                <input
                                  type="text"
                                  placeholder="@mychannel или -1001234567890"
                                  className="w-full mt-1.5 bg-zinc-900 border border-zinc-800 p-3 rounded-xl text-xs text-white outline-none focus:border-violet-500 transition-all font-mono"
                                  value={ch.id || ''}
                                  onChange={e => {
                                    const chs = [...(bot.requiredChannels || [])];
                                    chs[idx] = { ...chs[idx], id: e.target.value };
                                    handleLocalUpdate({ ...bot, requiredChannels: chs });
                                  }}
                                />
                              </div>
                              <div className="grid grid-cols-2 gap-2">
                                <div>
                                  <span className="text-[8px] text-zinc-600 uppercase font-bold ml-1">Название (для юзера)</span>
                                  <input
                                    type="text"
                                    placeholder="Наш канал"
                                    className="w-full mt-1.5 bg-zinc-900 border border-zinc-800 p-3 rounded-xl text-xs text-white outline-none focus:border-violet-500 transition-all"
                                    value={ch.title || ''}
                                    onChange={e => {
                                      const chs = [...(bot.requiredChannels || [])];
                                      chs[idx] = { ...chs[idx], title: e.target.value };
                                      handleLocalUpdate({ ...bot, requiredChannels: chs });
                                    }}
                                  />
                                </div>
                                <div>
                                  <span className="text-[8px] text-zinc-600 uppercase font-bold ml-1">Ссылка (кнопка)</span>
                                  <input
                                    type="text"
                                    placeholder="https://t.me/mychannel"
                                    className="w-full mt-1.5 bg-zinc-900 border border-zinc-800 p-3 rounded-xl text-xs text-white outline-none focus:border-violet-500 transition-all"
                                    value={ch.url || ''}
                                    onChange={e => {
                                      const chs = [...(bot.requiredChannels || [])];
                                      chs[idx] = { ...chs[idx], url: e.target.value };
                                      handleLocalUpdate({ ...bot, requiredChannels: chs });
                                    }}
                                  />
                                </div>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>

                      <button
                        onClick={() => {
                          const chs = [...(bot.requiredChannels || []), { id: '', title: '', url: '' }];
                          handleLocalUpdate({ ...bot, requiredChannels: chs });
                        }}
                        className="w-full py-3.5 rounded-2xl border border-dashed border-violet-500/30 text-violet-400 text-[10px] font-black uppercase tracking-wider hover:bg-violet-500/5 transition-all flex items-center justify-center gap-2"
                      >
                        <Plus className="w-3.5 h-3.5" /> Добавить канал / чат
                      </button>

                      {(bot.requiredChannels || []).length > 0 && (
                        <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-4">
                          <p className="text-[8px] text-zinc-500 uppercase font-black mb-2 flex items-center gap-1.5">
                            <Smartphone className="w-2.5 h-2.5" />Превью сообщения для пользователя
                          </p>
                          <div className="bg-black rounded-xl p-3 space-y-2">
                            <p className="text-[10px] text-white leading-relaxed">
                              🔒 <b>Для использования бота необходимо подписаться на наши каналы:</b>
                            </p>
                            {((bot.requiredChannels || []) as any[]).filter((c: any) => c.id || c.title).map((c: any, i: number) => (
                              <p key={i} className="text-[10px] text-zinc-400">• {c.title || c.id}</p>
                            ))}
                            <div className="mt-2 space-y-1.5">
                              {((bot.requiredChannels || []) as any[]).filter((c: any) => c.title || c.id).map((c: any, i: number) => (
                                <div key={i} className="bg-violet-500/10 border border-violet-500/20 rounded-lg py-2 px-3 text-center text-[10px] text-violet-300 font-semibold">
                                  📢 {c.title || c.id}
                                </div>
                              ))}
                              <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg py-2 px-3 text-center text-[10px] text-emerald-300 font-semibold">
                                ✅ Я подписался — проверить
                              </div>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </section>
              )}
            </div>
          )}

          {/* Зона опасных действий */}
          <div className="lg:col-span-2 mt-4">
            {isAdminMode ? (
              <div className="p-6 border border-zinc-800 bg-zinc-900/40 rounded-[2rem] flex items-center gap-4 opacity-50 pointer-events-none">
                <div className="p-3 bg-zinc-800 rounded-xl"><Lock size={20} className="text-zinc-500" /></div>
                <div>
                  <h4 className="text-[10px] font-black uppercase text-zinc-400 tracking-widest">Admin Protection</h4>
                  <p className="text-[9px] text-zinc-600 uppercase">Deletion disabled in Support Mode</p>
                </div>
              </div>
            ) : (
              <button onClick={() => window.confirm('Вы точно хотите удалить этот инстанс?') && onDelete()}
                className="w-full p-5 text-[10px] font-black uppercase text-rose-500 bg-rose-500/5 rounded-3xl border border-rose-500/10 hover:bg-rose-500/20 transition-all flex items-center justify-center gap-2">
                <Trash2 className="w-4 h-4" />Удалить навсегда
              </button>
            )}
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════
          ВКЛАДКА: КНОПКИ (Интерфейс)
      ════════════════════════════════════════════ */}
      {activeTab === 'interface' && isSupportBot && (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
          
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-2xl font-black text-white uppercase">Конструктор Кнопок</h2>
            <button 
              onClick={() => handleLocalUpdate({ ...bot, buttons: [...(bot.buttons||[]), {text:'', response:'', type:'message'}] })}
              className="bg-blue-600 px-8 py-4 rounded-2xl text-[11px] font-black text-white uppercase flex items-center gap-2 shadow-lg shadow-blue-600/20 hover:bg-blue-500 transition-all"
            >
              <Plus className="w-4 h-4" />Новая кнопка
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {(bot.buttons||[]).map((btn, i) => (
              <div key={i} className="bg-[#0d0d0d] border border-zinc-800 rounded-[2.5rem] p-8 space-y-6 relative border-t-4 border-t-blue-500/20 shadow-xl">
                
                {/* Кнопка удаления */}
                <button 
                  onClick={() => handleLocalUpdate({...bot, buttons: bot.buttons.filter((_, idx) => idx !== i)})}
                  className="absolute top-6 right-6 text-zinc-600 hover:text-rose-500 transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>

                <div className="space-y-5">
                  {/* Текст кнопки */}
                  <label className="block">
                    <span className="text-[9px] font-bold text-zinc-600 uppercase ml-2">Текст на кнопке</span>
                    <input 
                      className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white text-sm font-bold outline-none focus:border-blue-500"
                      value={btn.text} 
                      onChange={e => { const nb=[...bot.buttons]; nb[i].text=e.target.value; handleLocalUpdate({...bot, buttons:nb}); }} 
                    />
                  </label>

                  {/* Ответ системы */}
                  <label className="block">
                    <span className="text-[9px] font-bold text-zinc-600 uppercase ml-2">Ответ системы</span>
                    <textarea 
                      className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white text-sm min-h-[120px] outline-none focus:border-blue-500 resize-none"
                      value={btn.response} 
                      onChange={e => { const nb=[...bot.buttons]; nb[i].response=e.target.value; handleLocalUpdate({...bot, buttons:nb}); }} 
                    />
                  </label>

                  {/* Переключатель типа сообщения */}
                  <div className="flex bg-black p-1 rounded-xl border border-zinc-800">
                    {['message', 'request'].map(type => (
                      <button 
                        key={type} 
                        onClick={() => { const nb=[...bot.buttons]; nb[i].type=type as any; handleLocalUpdate({...bot, buttons:nb}); }}
                        className={`flex-1 py-2.5 rounded-lg text-[9px] font-black uppercase transition-all ${btn.type===type ? 'bg-blue-600 text-white shadow-lg' : 'text-zinc-600 hover:text-zinc-400'}`}
                      >
                        {type==='message' ? 'Обычный ответ' : '🆘 Заявка (Тикет)'}
                      </button>
                    ))}
                  </div>

                  {/* ── Sub-кнопки (If/Else) ── */}
                  {(
                    <div className="border-t border-zinc-800 pt-4">
                      <div className="flex items-center justify-between mb-3">
                        <span className="text-[9px] font-black text-zinc-500 uppercase flex items-center gap-1.5">
                          <Layers className="w-3 h-3 text-blue-400" /> Sub-кнопки
                        </span>
                        <button 
                          type="button"
                          onClick={() => { const nb=[...bot.buttons]; nb[i].children=[...(nb[i].children||[]), {text:'', response:''}]; handleLocalUpdate({...bot, buttons:nb}); }}
                          className="text-[9px] text-blue-400 font-bold hover:text-blue-300"
                        >
                          + Под-кнопка
                        </button>
                      </div>
                      
                      <p className="text-[8px] text-zinc-600 mb-2">При нажатии — показать эти кнопки вместо ответа:</p>
                      
                      {(btn.children||[]).map((child: any, ci: number) => (
                        <div key={ci} className="flex gap-2 mb-2">
                          <input 
                            placeholder="Кнопка"
                            className="flex-1 bg-black border border-zinc-800 p-3 rounded-xl text-xs text-white outline-none focus:border-blue-500"
                            value={child.text}
                            onChange={e => { const nb=[...bot.buttons]; nb[i].children[ci].text=e.target.value; handleLocalUpdate({...bot, buttons:nb}); }} 
                          />
                          <input 
                            placeholder="Ответ"
                            className="flex-1 bg-black border border-zinc-800 p-3 rounded-xl text-xs text-white outline-none focus:border-blue-500"
                            value={child.response}
                            onChange={e => { const nb=[...bot.buttons]; nb[i].children[ci].response=e.target.value; handleLocalUpdate({...bot, buttons:nb}); }} 
                          />
                          <button 
                            type="button"
                            onClick={() => { const nb=[...bot.buttons]; nb[i].children=nb[i].children.filter((_:any, idx:number) => idx !== ci); handleLocalUpdate({...bot, buttons:nb}); }}
                            className="px-2 text-zinc-600 hover:text-rose-500"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                  {/* Конец блока Sub-кнопок */}

                  {/* Инлайн URL-кнопки к ответу — только Telegram */}
                  {!isVK && (
                  <div className="border-t border-zinc-800 pt-4">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-[9px] font-black text-zinc-500 uppercase flex items-center gap-1.5">
                        <ExternalLink className="w-3 h-3 text-indigo-400" />
                        Инлайн URL-кнопки к ответу
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          const nb = [...bot.buttons];
                          nb[i].inline = [...(nb[i].inline || []), { text: '', url: '' }];
                          handleLocalUpdate({ ...bot, buttons: nb });
                        }}
                        className="text-[9px] text-indigo-400 font-bold hover:text-indigo-300"
                      >
                        + Ссылка
                      </button>
                    </div>

                    <p className="text-[8px] text-zinc-600 mb-2">
                      Кнопки-ссылки появятся под ответом бота в Telegram:
                    </p>

                    {(btn.inline || []).map((ib: any, ii: number) => (
                      <div key={ii} className="flex gap-2 mb-2">
                        <input
                          placeholder="Текст кнопки"
                          className="flex-1 bg-black border border-zinc-800 p-3 rounded-xl text-xs text-white outline-none transition-all focus:border-indigo-500"
                          value={ib.text}
                          onChange={e => {
                            const nb = [...bot.buttons];
                            nb[i].inline[ii] = { ...nb[i].inline[ii], text: e.target.value };
                            handleLocalUpdate({ ...bot, buttons: nb });
                          }}
                        />
                        <input
                          placeholder="https://..."
                          className="flex-1 bg-black border border-zinc-800 p-3 rounded-xl text-xs text-white outline-none transition-all focus:border-indigo-500"
                          value={ib.url}
                          onChange={e => {
                            const nb = [...bot.buttons];
                            nb[i].inline[ii] = { ...nb[i].inline[ii], url: e.target.value };
                            handleLocalUpdate({ ...bot, buttons: nb });
                          }}
                        />
                        <button
                          type="button"
                          onClick={() => {
                            const nb = [...bot.buttons];
                            nb[i].inline = (nb[i].inline || []).filter((_: any, idx: number) => idx !== ii);
                            handleLocalUpdate({ ...bot, buttons: nb });
                          }}
                          className="px-2 text-zinc-600 hover:text-rose-500"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    ))}

                    {/* Превью инлайн-кнопок */}
                    {(btn.inline || []).filter((b: any) => b.text).length > 0 && (
                      <div className="mt-2 bg-black/40 border border-zinc-800/60 rounded-xl p-3 space-y-1">
                        <p className="text-[7px] text-zinc-700 uppercase font-bold mb-2 flex items-center gap-1">
                          <Smartphone className="w-2 h-2" />Превью
                        </p>
                        <div className="bg-zinc-900/70 rounded-xl p-2.5 max-w-[80%] mb-1.5">
                          <p className="text-[9px] text-zinc-400">{btn.response ? btn.response.slice(0, 60) + (btn.response.length > 60 ? '…' : '') : 'Ответ кнопки...'}</p>
                        </div>
                        {(btn.inline || []).filter((b: any) => b.text).map((b: any, pi: number) => (
                          <div key={pi} className="rounded-lg py-1.5 px-3 text-center flex items-center justify-center gap-1 bg-indigo-500/10 border border-indigo-500/20">
                            <ExternalLink className="w-2 h-2 shrink-0 text-indigo-400/60" />
                            <span className="text-[9px] font-semibold text-indigo-300">{b.text}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  )}
                  {/* Конец блока Инлайн URL-кнопок */}

                </div>
              </div>
            ))}
          </div>

          {/* ════════════════════════════════════════════
              БЛОК: РАСШИРЕННАЯ ЛОГИКА (Flow-редактор)
          ════════════════════════════════════════════ */}
          <ButtonFlowEditor bot={bot} onUpdate={handleLocalUpdate} />
        </div>
      )}

      {/* ════════════════════════════════════════════
          ВКЛАДКА: ТРИГГЕРЫ (только для support-ботов)
      ════════════════════════════════════════════ */}
      {activeTab === 'logic' && isSupportBot && (
        <div className="space-y-6 animate-in fade-in duration-500">
          <div className="flex justify-between items-end mb-6">
            <h2 className="text-2xl font-black text-white uppercase">Триггеры авто-ответа</h2>
            <button onClick={() => handleLocalUpdate({...bot,triggers:[...(bot.triggers||[]),{keyword:'',response:''}]})}
              className="bg-emerald-600 px-8 py-4 rounded-2xl text-[10px] font-black text-white uppercase flex items-center gap-2 transition-all">
              <Plus className="w-4 h-4" />Новый триггер
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {(bot.triggers||[]).map((trig,i) => (
              <div key={i} className="bg-[#0d0d0d] border border-zinc-800 rounded-[2.5rem] p-8 space-y-5 relative border-t-4 border-t-emerald-500/20 shadow-xl">
                <button onClick={() => handleLocalUpdate({...bot,triggers:bot.triggers.filter((_,idx)=>idx!==i)})} className="absolute top-6 right-6 text-zinc-600 hover:text-rose-500"><X className="w-5 h-5" /></button>
                <input placeholder="Ключевое слово" className="w-full bg-black border border-zinc-800 p-5 rounded-2xl text-white text-sm font-bold outline-none focus:border-emerald-500"
                  value={trig.keyword} onChange={e => { const nt=[...bot.triggers]; nt[i].keyword=e.target.value; handleLocalUpdate({...bot,triggers:nt}); }} />
                <textarea placeholder="Что бот должен ответить..." className="w-full bg-black border border-zinc-800 p-5 rounded-2xl text-white text-sm outline-none min-h-[120px] focus:border-emerald-500"
                  value={trig.response} onChange={e => { const nt=[...bot.triggers]; nt[i].response=e.target.value; handleLocalUpdate({...bot,triggers:nt}); }} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* CRM */}
      {activeTab === 'chat' && isSupportBot && (
        <div className="bg-[#111] border border-zinc-800 rounded-[2.5rem] h-[700px] overflow-hidden flex flex-col p-8 shadow-2xl animate-in fade-in duration-500">
          <h2 className="text-sm font-black text-white uppercase mb-6 flex items-center gap-2">
            <MessageSquare className="w-4 h-4 text-blue-500" />CRM История сообщений
          </h2>
          <div className="flex-1 overflow-y-auto no-scrollbar space-y-6 pr-4">
            {messages.length === 0 ? (
              <p className="text-center text-zinc-700 py-32 uppercase text-[10px] font-black tracking-widest opacity-20">История пуста</p>
            ) : messages.map((m,i) => (
              <div key={i} className={`flex gap-4 items-start ${m.is_admin?'flex-row-reverse text-right':''} animate-in slide-in-from-bottom-2 duration-300`}>
                <div className={`p-5 rounded-3xl max-w-[75%] text-sm shadow-lg ${m.is_admin?'bg-blue-600 text-white rounded-tr-none':'bg-black/60 border border-zinc-800 text-zinc-300 rounded-tl-none'}`}>
                  <p className="text-[9px] font-black uppercase opacity-40 mb-2">{m.user?.name} | {new Date(m.timestamp).toLocaleTimeString()}</p>
                  <div className="leading-relaxed whitespace-pre-wrap">{m.text}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════
          ВКЛАДКА: ИИ-АССИСТЕНТ
      ════════════════════════════════════════════ */}
      {activeTab === 'staff' && isSupportBot && (
        <StaffTab bot={bot} onUpdate={handleLocalUpdate} isVK={isVK} />
      )}
      {activeTab === 'ai' && isSupportBot && (
  <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
    {/* Баланс токенов */}
    <div className="bg-[#111] border border-zinc-800 p-6 rounded-[2.5rem] flex flex-col lg:flex-row items-center gap-8">
      <div className="flex-1 w-full">
        <h3 className="text-sm font-black text-white flex items-center gap-2 mb-1">
          <Coins className="w-4 h-4 text-amber-500" /> AI-токены
        </h3>
        {aiBalance ? (
          <div className="grid grid-cols-3 gap-4 mt-3">
            {[
              { label: 'Остаток', val: aiBalance.tokens_balance, color: 'text-emerald-400' },
              { label: 'Всего',   val: aiBalance.tokens_total,   color: 'text-blue-400' },
              { label: 'Потрачено',val: aiBalance.tokens_used,   color: 'text-rose-400' },
            ].map(({ label, val, color }) => (
              <div key={label} className="bg-black border border-zinc-800 p-3 rounded-2xl text-center">
                <p className={`text-lg font-black ${color}`}>{val.toLocaleString()}</p>
                <p className="text-[8px] text-zinc-600 uppercase font-bold">{label}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-zinc-500 mt-2 italic">Загрузка баланса...</p>
        )}
      </div>

      {/* Кнопки быстрой покупки */}
      <div className="w-full lg:w-auto flex flex-col gap-2">
        <p className="text-[9px] text-zinc-500 font-bold uppercase ml-1 tracking-widest text-center lg:text-left">Пополнить пакет токенов</p>
        <div className="flex flex-wrap lg:flex-nowrap gap-2">
          {[
            { id: 'ai_500k',  label: '500K',  price: 90 },
            { id: 'ai_1500k', label: '1.5M',  price: 250 },
            { id: 'ai_5000k', label: '5M',    price: 700 }
          ].map((pkg) => (
            <button
              key={pkg.id}
              onClick={async () => {
                if (!window.confirm(`Списать ${pkg.price} ₽ за ${pkg.label} токенов?`)) return;
                setIsProcessing(true);
                try {
                  const res = await api.buyService(bot.owner_id, pkg.id, bot.id);
                  if (res && res.status === 'ok') {
                    // Обновляем баланс AI после покупки
                    const newBal = await fetch(`/api/ai/balance/${bot.id}`).then(r => r.json());
                    setAiBalance(newBal);
                    alert(`✅ Пакет ${pkg.label} успешно активирован!`);
                  } else {
                    alert(res?.detail || 'Недостаточно средств на балансе');
                  }
                } catch (e) {
                  alert('Ошибка соединения с сервером');
                } finally {
                  setIsProcessing(false);
                }
              }}
              disabled={isProcessing}
              className="flex-1 lg:flex-none px-4 py-3 bg-zinc-900 border border-zinc-800 hover:border-amber-500/50 rounded-xl transition-all group text-center"
            >
              <div className="text-amber-500 font-black text-xs group-hover:scale-110 transition-transform">{pkg.label}</div>
              <div className="text-[9px] text-zinc-500 font-bold italic">{pkg.price} ₽</div>
            </button>
          ))}
        </div>
        <p className="text-[8px] text-zinc-700 text-center lg:text-left italic">Средства спишутся с вашего личного счета</p>
      </div>
    </div>
    
          {/* Настройки AI — блокируются если нет токенов */}
          {(!aiBalance || aiBalance.tokens_balance <= 0) ? (
            <div className="bg-amber-500/5 border border-amber-500/20 p-8 rounded-[2.5rem] text-center">
              <Brain className="w-10 h-10 text-amber-500/40 mx-auto mb-3" />
              <p className="text-sm font-black text-amber-400/60">Нет AI-токенов</p>
              <p className="text-[10px] text-zinc-600 mt-1">Активируйте ключ выше или купите пакет в магазине</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              {/* Режим работы */}
              <section className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
                <h3 className="text-sm font-black text-white flex items-center gap-2">
                  <Brain className="w-4 h-4 text-purple-500" /> Режим ИИ-ассистента
                </h3>
                <div className="space-y-2">
                  {([
                    { id: 'off',     label: 'Отключён',          sub: 'ИИ не используется' },
                    { id: 'all',     label: 'На все сообщения',   sub: 'ИИ отвечает на каждый текст (если нет триггеров/кнопок)' },
                    { id: 'button',  label: 'По кнопке',          sub: 'Кнопка «ИИ-ассистент» в клавиатуре' },
                    { id: 'command', label: 'По команде /ai',      sub: 'Пользователь пишет /ai' },
                  ] as const).map(({ id, label, sub }) => (
                    <button key={id} type="button"
                      onClick={() => handleLocalUpdate({ ...bot, ai: { ...(bot.ai || {}), mode: id, enabled: id !== 'off' } })}
                      className={`w-full flex items-center justify-between p-4 rounded-2xl border text-left transition-all ${
                        (bot.ai?.mode || 'off') === id
                          ? 'bg-purple-500/10 border-purple-500/30 text-purple-400'
                          : 'bg-black border-zinc-800 text-zinc-500 hover:border-zinc-700'
                      }`}>
                      <div>
                        <p className="text-xs font-bold">{label}</p>
                        <p className="text-[9px] opacity-60">{sub}</p>
                      </div>
                      {(bot.ai?.mode || 'off') === id && <CheckSquare className="w-4 h-4 shrink-0" />}
                    </button>
                  ))}
                </div>
                {bot.ai?.mode === 'button' && (
                  <label className="block">
                    <span className="text-[9px] text-zinc-500 font-bold uppercase ml-2">Название кнопки</span>
                    <input
                      className="w-full mt-2 bg-black border border-zinc-800 p-4 rounded-2xl text-sm text-white outline-none focus:border-purple-500 transition-all"
                      value={bot.ai?.buttonName || 'ИИ-ассистент'}
                      onChange={e => handleLocalUpdate({ ...bot, ai: { ...(bot.ai || {}), buttonName: e.target.value } })}
                    />
                  </label>
                )}
                {/* Кнопка теста ИИ */}
                {(bot.ai?.mode ?? 'off') !== 'off' && (
                  <button
                    type="button"
                    onClick={() => { setAiChatMsgs([]); setAiChatOpen(true); }}
                    className="w-full py-4 rounded-2xl bg-purple-600/10 border border-purple-500/30 text-purple-400 text-xs font-black uppercase tracking-widest hover:bg-purple-600/20 transition-all flex items-center justify-center gap-2 mt-2"
                  >
                    <Brain className="w-4 h-4" />Протестировать ИИ-ассистента (в разработке)
                  </button>
                )}
              </section>

{/* Параметры модели */}
              <section className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-5">
                <h3 className="text-sm font-black text-white flex items-center gap-2">
                  <Settings className="w-4 h-4 text-blue-500" /> Параметры
                </h3>
                
                <label className="block">
                  <span className="text-[9px] text-zinc-500 font-bold uppercase ml-2">Модель</span>
                  <select
                    className="w-full mt-2 bg-black border border-zinc-800 p-4 rounded-2xl text-sm text-white outline-none focus:border-blue-500 transition-all cursor-pointer"
                    value={bot.ai?.model || 'qturbo'}
                    onChange={e => handleLocalUpdate({ ...bot, ai: { ...(bot.ai || {}), model: e.target.value } })}>
                    <option value="turbo">turbo (быстрый, дешёвый)</option>
                    <option value="plus">plus (умнее)</option>
                    <option value="max">max (самый умный)</option>
                  </select>
                </label>

                <div className="grid grid-cols-2 gap-4">
                  <label className="block">
                    <span className="text-[9px] text-zinc-500 font-bold uppercase ml-2">Макс. токенов/ответ</span>
                    <input 
                      type="number" 
                      min="100" 
                      max="4000" 
                      step="100"
                      className="w-full mt-2 bg-black border border-zinc-800 p-4 rounded-2xl text-sm text-white outline-none focus:border-blue-500 transition-all"
                      // Используем ?? '', чтобы при удалении цифр поле оставалось пустым, а не сбрасывалось на 800
                      value={bot.ai?.maxTokensPerReply ?? ''} 
                      onChange={e => {
                        const val = e.target.value === '' ? undefined : parseInt(e.target.value);
                        handleLocalUpdate({ 
                          ...bot, 
                          ai: { ...(bot.ai || {}), maxTokensPerReply: val } 
                        });
                      }} 
                    />
                  </label>

                  <label className="block">
                    <span className="text-[9px] text-zinc-500 font-bold uppercase ml-2">Глубина контекста</span>
                    <input 
                      type="number" 
                      min="1" 
                      max="20"
                      className="w-full mt-2 bg-black border border-zinc-800 p-4 rounded-2xl text-sm text-white outline-none focus:border-blue-500 transition-all"
                      // Используем ?? '', чтобы при удалении цифр поле не возвращало 6
                      value={bot.ai?.contextMessages ?? ''} 
                      onChange={e => {
                        const val = e.target.value === '' ? undefined : parseInt(e.target.value);
                        handleLocalUpdate({ 
                          ...bot, 
                          ai: { ...(bot.ai || {}), contextMessages: val } 
                        });
                      }} 
                    />
                  </label>
                </div>

                <label className="block">
                  <span className="text-[9px] text-zinc-500 font-bold uppercase ml-2">Системный промпт</span>
                  <textarea
                    className="w-full mt-2 bg-black border border-zinc-800 p-4 rounded-2xl text-xs text-white outline-none focus:border-blue-500 transition-all resize-none min-h-[120px]"
                    placeholder="Ты помощник поддержки компании. Отвечай вежливо и по делу."
                    value={bot.ai?.systemPrompt || ''}
                    onChange={e => handleLocalUpdate({ ...bot, ai: { ...(bot.ai || {}), systemPrompt: e.target.value } })} 
                  />
                </label>
              </section>
            </div>
          )}
        </div>
      )}

      {/* ════════════════════════════════════════════
          ВКЛАДКА: МИНИ-ПРИЛОЖЕНИЯ
      ════════════════════════════════════════════ */}
      {activeTab === 'miniapps' && isSupportBot && (
        <MiniAppsTab bot={bot} onUpdate={handleLocalUpdate} isVK={isVK} />
      )}


      {/* Аналитика и логи */}
      {activeTab === 'stats' && <BotStatsView bot={bot} onUpdate={onUpdate} />}
      {activeTab === 'logs'  && <BotConsole botId={bot.id} />}

    </div>
  );
};


// ══════════════════════════════════════════════════════════════════════════════
//  МИНИ-ПРИЛОЖЕНИЯ — встроенный конструктор в BotEditor
// ══════════════════════════════════════════════════════════════════════════════

type MiniCompType = 'heading' | 'text' | 'button' | 'linkButton' | 'input' | 'textarea' | 'divider' | 'spacer' | 'image';

interface MiniCompProps {
  text?: string; level?: 'h1' | 'h2' | 'h3'; fontSize?: number; fontWeight?: string;
  color?: string; align?: 'left' | 'center' | 'right'; italic?: boolean;
  bgColor?: string; textColor?: string; action?: 'link' | 'submit' | 'none'; url?: string;
  placeholder?: string; label?: string; required?: boolean; inputType?: string; name?: string;
  src?: string; alt?: string; width?: string; height?: number; dividerColor?: string;
}

interface MiniComp { id: string; type: MiniCompType; props: MiniCompProps; }

interface MiniTheme {
  bg: string; surface: string; primary: string;
  textPrimary: string; textSecondary: string; radius: number; font: string; gradient?: string;
}

// formbot = через выделенный бот форм (рекомендуется)
// sheets  = Google Apps Script
// webhook = внешний URL (n8n, Make, Zapier)
type MiniWebhookType = 'formbot' | 'sheets' | 'webhook';

interface MiniApp {
  id: string;
  title: string;
  theme: MiniTheme;
  components: MiniComp[];
  webhookType: MiniWebhookType;
  notifyChatId?: string;
  sheetsUrl?: string;
  formWebhook?: string;
  bot_id?: string;
  owner_id?: string;
}

const MINI_PALETTE: { type: MiniCompType; label: string; icon: React.ElementType }[] = [
  { type: 'heading',    label: 'Заголовок', icon: Type },
  { type: 'text',       label: 'Текст',     icon: AlignLeft },
  { type: 'button',     label: 'Кнопка',    icon: MousePointerClick },
  { type: 'linkButton', label: 'Ссылка',    icon: Link2 },
  { type: 'input',      label: 'Поле',      icon: TextCursorInput },
  { type: 'textarea',   label: 'Textarea',  icon: Square },
  { type: 'image',      label: 'Фото',      icon: Image },
  { type: 'divider',    label: 'Линия',     icon: Minus },
  { type: 'spacer',     label: 'Отступ',    icon: MoveVertical },
];

const MINI_PRESETS: { label: string; theme: Partial<MiniTheme> }[] = [
  { label: 'Ночь',   theme: { bg: '#0a0a0f', surface: '#13131c', primary: '#6366f1', textPrimary: '#f8fafc', textSecondary: '#94a3b8', gradient: 'radial-gradient(ellipse at 30% 0%, #312e8155 0%, transparent 60%)' } },
  { label: 'Лёд',    theme: { bg: '#f0f9ff', surface: '#ffffff',  primary: '#0ea5e9', textPrimary: '#0f172a', textSecondary: '#64748b', gradient: '' } },
  { label: 'Закат',  theme: { bg: '#1c0d2b', surface: '#251238',  primary: '#f97316', textPrimary: '#fff7ed', textSecondary: '#d1a27c', gradient: 'radial-gradient(ellipse at 80% 0%, #7c2d8840 0%, transparent 60%)' } },
  { label: 'Лес',    theme: { bg: '#0d1f12', surface: '#142419',  primary: '#22c55e', textPrimary: '#f0fdf4', textSecondary: '#86efac', gradient: '' } },
  { label: 'Роза',   theme: { bg: '#fff1f2', surface: '#ffffff',  primary: '#f43f5e', textPrimary: '#1c1917', textSecondary: '#78716c', gradient: '' } },
  { label: 'Уголь',  theme: { bg: '#111111', surface: '#1c1c1e',  primary: '#f59e0b', textPrimary: '#fafaf9', textSecondary: '#78716c', gradient: '' } },
];

const DEFAULT_MINI_THEME: MiniTheme = {
  bg: '#0a0a0f', surface: '#13131c', primary: '#6366f1',
  textPrimary: '#f8fafc', textSecondary: '#94a3b8',
  radius: 12, font: "'Manrope', sans-serif",
  gradient: 'radial-gradient(ellipse at 30% 0%, #312e8155 0%, transparent 60%)',
};

const mkMiniId = () => Math.random().toString(36).slice(2, 9);

const newMiniComp = (type: MiniCompType): MiniComp => {
  const id = mkMiniId();
  switch (type) {
    case 'heading':    return { id, type, props: { text: 'Заголовок', level: 'h2', fontSize: 28, fontWeight: '800', color: '', align: 'left' } };
    case 'text':       return { id, type, props: { text: 'Опишите здесь что угодно.', fontSize: 15, color: '', align: 'left' } };
    case 'button':     return { id, type, props: { text: 'Отправить', bgColor: '', textColor: '#ffffff', action: 'submit' } };
    case 'linkButton': return { id, type, props: { text: 'Перейти', url: 'https://', bgColor: '', textColor: '#ffffff' } };
    case 'input':      return { id, type, props: { label: 'Поле', placeholder: 'Введите...', name: `field_${id}`, inputType: 'text', required: false } };
    case 'textarea':   return { id, type, props: { label: 'Сообщение', placeholder: 'Ваш текст...', name: `msg_${id}`, required: false } };
    case 'image':      return { id, type, props: { src: '', alt: '', width: '100%' } };
    case 'divider':    return { id, type, props: { dividerColor: '' } };
    case 'spacer':     return { id, type, props: { height: 24 } };
    default:           return { id, type, props: {} };
  }
};

// ── Превью блока в редакторе ──────────────────────────────────────────────────

const MiniPreviewComp: React.FC<{
  comp: MiniComp; theme: MiniTheme; selected?: boolean;
}> = ({ comp, theme, selected }) => {
  const { type, props: p } = comp;
  const wrap = (el: React.ReactNode) => (
    <div style={{ outline: selected ? `2px solid ${theme.primary}` : 'none', outlineOffset: 2, borderRadius: 4 }}>{el}</div>
  );
  if (type === 'heading') {
    const Tag = (p.level || 'h2') as 'h1' | 'h2' | 'h3';
    return wrap(<Tag style={{ fontSize: p.fontSize || 28, fontWeight: p.fontWeight || '800', color: p.color || theme.textPrimary, textAlign: p.align || 'left', margin: 0, lineHeight: 1.2, fontFamily: theme.font }}>{p.text || 'Заголовок'}</Tag>);
  }
  if (type === 'text') return wrap(<p style={{ fontSize: p.fontSize || 15, color: p.color || theme.textSecondary, textAlign: p.align || 'left', margin: 0, lineHeight: 1.65, fontFamily: theme.font }}>{p.text || 'Текст'}</p>);
  if (type === 'button' || type === 'linkButton') return wrap(<div style={{ textAlign: 'center' }}><span style={{ display: 'inline-block', background: p.bgColor || theme.primary, color: p.textColor || '#fff', borderRadius: theme.radius, fontWeight: '700', fontSize: 14, padding: '10px 24px', fontFamily: theme.font }}>{p.text || 'Кнопка'}</span></div>);
  if (type === 'input') return wrap(<div>
    {p.label && <span style={{ display: 'block', fontSize: 11, fontWeight: '700', color: theme.textSecondary, marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.08em', fontFamily: theme.font }}>{p.label}{p.required ? ' *' : ''}</span>}
    <div style={{ background: theme.surface, border: `1px solid ${theme.textSecondary}30`, borderRadius: theme.radius * 0.6, padding: '9px 13px', fontSize: 13, color: theme.textSecondary + '80', fontFamily: theme.font }}>{p.placeholder || 'Введите...'}</div>
  </div>);
  if (type === 'textarea') return wrap(<div>
    {p.label && <span style={{ display: 'block', fontSize: 11, fontWeight: '700', color: theme.textSecondary, marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.08em', fontFamily: theme.font }}>{p.label}{p.required ? ' *' : ''}</span>}
    <div style={{ background: theme.surface, border: `1px solid ${theme.textSecondary}30`, borderRadius: theme.radius * 0.6, padding: '9px 13px', fontSize: 13, color: theme.textSecondary + '80', fontFamily: theme.font, minHeight: 64 }}>{p.placeholder || 'Введите...'}</div>
  </div>);
  if (type === 'image') return wrap(<img src={p.src} alt={p.alt || ''} style={{ width: p.width || '100%', borderRadius: theme.radius, display: 'block', maxWidth: '100%' }} onError={e => { (e.currentTarget as HTMLImageElement).style.opacity = '0.3'; }} />);
  if (type === 'divider') return wrap(<hr style={{ border: 'none', borderTop: `1px solid ${p.dividerColor || theme.textSecondary + '30'}`, margin: '2px 0' }} />);
  if (type === 'spacer') return wrap(<div style={{ height: p.height || 24 }} />);
  return wrap(<div />);
};

// ── Панель свойств блока ──────────────────────────────────────────────────────

const MiniPropsPanel: React.FC<{
  comp: MiniComp | null; theme: MiniTheme; onChange: (id: string, p: Partial<MiniCompProps>) => void;
}> = ({ comp, theme, onChange }) => {
  if (!comp) return (
    <div className="flex flex-col items-center justify-center py-12 gap-2 opacity-20">
      <Layers className="w-8 h-8 text-zinc-500" />
      <p className="text-[9px] text-zinc-500 font-black uppercase tracking-widest">Выберите блок</p>
    </div>
  );
  const p = comp.props;
  const up = (patch: Partial<MiniCompProps>) => onChange(comp.id, patch);
  const inp = (cls = '') => `w-full bg-black border border-zinc-800 focus:border-indigo-500 text-white text-xs p-2.5 rounded-xl outline-none transition-all ${cls}`;

  return (
    <div className="p-3 space-y-3 overflow-y-auto h-full">
      <p className="text-[8px] font-black text-indigo-400 uppercase tracking-[0.2em]">{comp.type}</p>

      {(comp.type === 'heading' || comp.type === 'text') && (<>
        <label className="block">
          <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Текст</span>
          <textarea value={p.text || ''} rows={3} onChange={e => up({ text: e.target.value })} className={inp('resize-none')} />
        </label>
        {comp.type === 'heading' && (
          <label className="block">
            <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Уровень</span>
            <select value={p.level || 'h2'} onChange={e => up({ level: e.target.value as 'h1'|'h2'|'h3' })} className={inp('cursor-pointer')}>
              <option value="h1">H1</option><option value="h2">H2</option><option value="h3">H3</option>
            </select>
          </label>
        )}
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Размер px</span>
            <input type="number" min={10} max={80} value={p.fontSize || (comp.type === 'heading' ? 28 : 15)} onChange={e => up({ fontSize: Number(e.target.value) })} className={inp()} />
          </label>
          <label className="block">
            <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Жирность</span>
            <div className="flex gap-1">
              {([
                { v: '400', l: 'Обычный' },
                { v: '600', l: 'Средний' },
                { v: '700', l: 'Жирный' },
                { v: '800', l: 'Очень' },
              ] as const).map(({ v, l }) => {
                const def = comp.type === 'heading' ? '800' : '400';
                const active = p.fontWeight === v || (!p.fontWeight && v === def);
                return (
                  <button key={v} onClick={() => up({ fontWeight: v })} style={{ fontWeight: v }}
                    className={`flex-1 py-1.5 rounded-lg border text-[8px] transition-all truncate px-0.5 ${active ? 'bg-indigo-500/20 border-indigo-500/40 text-indigo-300' : 'border-zinc-800 text-zinc-600 hover:border-zinc-700 hover:text-white'}`}>
                    {l}
                  </button>
                );
              })}
            </div>
          </label>
        </div>
        <div className="flex gap-1">
          {(['left','center','right'] as const).map(a => (
            <button key={a} onClick={() => up({ align: a })}
              className={`flex-1 py-2 rounded-lg border text-[9px] font-black uppercase transition-all ${p.align===a ? 'bg-indigo-500/20 border-indigo-500/40 text-indigo-400' : 'border-zinc-800 text-zinc-600 hover:border-zinc-700'}`}>
              {a === 'left' ? 'Лево' : a === 'center' ? 'Центр' : 'Право'}
            </button>
          ))}
        </div>
        <label className="block">
          <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Цвет</span>
          <div className="flex gap-2 items-center">
            <input type="color"
              value={p.color && p.color !== '' ? p.color : (comp.type === 'heading' ? theme.textPrimary : theme.textSecondary)}
              onChange={e => up({ color: e.target.value })}
              className="w-8 h-8 rounded-lg border border-zinc-800 bg-black cursor-pointer p-0.5 shrink-0" />
            <input value={p.color || ''} placeholder="авто (по теме)" onChange={e => up({ color: e.target.value })} className={inp('flex-1')} />
            {p.color && <button onClick={() => up({ color: '' })} className="text-zinc-700 hover:text-rose-500 shrink-0 text-xs px-1">x</button>}
          </div>
        </label>
      </>)}

      {(comp.type === 'button' || comp.type === 'linkButton') && (<>
        <label className="block">
          <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Текст</span>
          <input value={p.text || ''} onChange={e => up({ text: e.target.value })} className={inp()} />
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Фон</span>
            <div className="flex gap-1.5">
              <input type="color" value={p.bgColor || theme.primary} onChange={e => up({ bgColor: e.target.value })} className="w-8 h-8 rounded-lg border border-zinc-800 bg-black cursor-pointer p-0.5 shrink-0" />
              <input value={p.bgColor || ''} placeholder="авто" onChange={e => up({ bgColor: e.target.value })} className={inp('flex-1 min-w-0')} />
            </div>
          </label>
          <label className="block">
            <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Текст</span>
            <div className="flex gap-1.5">
              <input type="color" value={p.textColor || '#ffffff'} onChange={e => up({ textColor: e.target.value })} className="w-8 h-8 rounded-lg border border-zinc-800 bg-black cursor-pointer p-0.5 shrink-0" />
              <input value={p.textColor || '#ffffff'} onChange={e => up({ textColor: e.target.value })} className={inp('flex-1 min-w-0')} />
            </div>
          </label>
        </div>
        {comp.type === 'button' && (
          <label className="block">
            <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Действие</span>
            <select value={p.action || 'none'} onChange={e => up({ action: e.target.value as 'link'|'submit'|'none' })} className={inp('cursor-pointer')}>
              <option value="none">Нет</option><option value="submit">Отправить форму</option><option value="link">Открыть ссылку</option>
            </select>
          </label>
        )}
        {(comp.type === 'linkButton' || (comp.type === 'button' && p.action === 'link')) && (
          <label className="block">
            <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">URL</span>
            <input type="url" value={p.url || ''} placeholder="https://" onChange={e => up({ url: e.target.value })} className={inp()} />
          </label>
        )}
      </>)}

      {(comp.type === 'input' || comp.type === 'textarea') && (<>
        <label className="block">
          <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Подпись</span>
          <input value={p.label || ''} onChange={e => up({ label: e.target.value })} className={inp()} />
        </label>
        <label className="block">
          <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Placeholder</span>
          <input value={p.placeholder || ''} onChange={e => up({ placeholder: e.target.value })} className={inp()} />
        </label>
        <label className="block">
          <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Поле name</span>
          <input value={p.name || ''} onChange={e => up({ name: e.target.value })} className={inp()} />
        </label>
        {comp.type === 'input' && (
          <label className="block">
            <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Тип</span>
            <select value={p.inputType || 'text'} onChange={e => up({ inputType: e.target.value })} className={inp('cursor-pointer')}>
              <option value="text">Текст</option><option value="email">Email</option><option value="tel">Телефон</option><option value="number">Число</option>
            </select>
          </label>
        )}
        <div className="flex items-center justify-between p-2.5 rounded-xl bg-zinc-900/50 border border-zinc-800">
          <span className="text-[9px] font-black text-zinc-400">Обязательное</span>
          <button onClick={() => up({ required: !p.required })} className={`w-9 h-5 rounded-full relative transition-all ${p.required ? 'bg-indigo-500' : 'bg-zinc-700'}`}>
            <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-all ${p.required ? 'left-4' : 'left-0.5'}`} />
          </button>
        </div>
      </>)}

      {comp.type === 'image' && (<>
        <label className="block">
          <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">URL фото</span>
          <input value={p.src || ''} onChange={e => up({ src: e.target.value })} placeholder="https://..." className={inp()} />
        </label>
        <label className="block">
          <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Ширина</span>
          <select value={p.width || '100%'} onChange={e => up({ width: e.target.value })} className={inp('cursor-pointer')}>
            <option value="100%">100%</option><option value="75%">75%</option><option value="50%">50%</option><option value="auto">Авто</option>
          </select>
        </label>
      </>)}

      {comp.type === 'spacer' && (
        <label className="block">
          <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Высота px</span>
          <input type="number" min={4} max={300} value={p.height || 24} onChange={e => up({ height: Number(e.target.value) })} className={inp()} />
        </label>
      )}
    </div>
  );
};

// ── Панель темы ───────────────────────────────────────────────────────────────

const MiniThemePanel: React.FC<{
  theme: MiniTheme; onChange: (t: MiniTheme) => void;
}> = ({ theme, onChange }) => (
  <div className="p-3 space-y-3 overflow-y-auto h-full">
    <p className="text-[8px] font-black text-indigo-400 uppercase tracking-[0.2em]">Тема</p>
    <p className="text-[8px] font-black text-zinc-600 uppercase tracking-widest">Пресеты</p>
    <div className="grid grid-cols-2 gap-1.5">
      {MINI_PRESETS.map(pt => (
        <button key={pt.label} onClick={() => onChange({ ...theme, ...pt.theme } as MiniTheme)}
          style={{ background: pt.theme.bg, borderColor: (pt.theme.primary || '#fff') + '50' }}
          className="border rounded-xl p-2 text-[9px] font-black transition-all hover:scale-105">
          <span style={{ color: pt.theme.textPrimary }}>{pt.label}</span>
        </button>
      ))}
    </div>
    <div className="h-px bg-zinc-800" />
    {([
      { label: 'Фон',         key: 'bg' },
      { label: 'Поверхность', key: 'surface' },
      { label: 'Акцент',      key: 'primary' },
      { label: 'Текст осн.',  key: 'textPrimary' },
      { label: 'Текст доп.',  key: 'textSecondary' },
    ] as { label: string; key: keyof MiniTheme }[]).map(({ label, key }) => (
      <label key={key} className="block">
        <span className="text-[8px] font-black text-zinc-600 uppercase tracking-widest block mb-1">{label}</span>
        <div className="flex gap-1.5">
          <input type="color" value={(theme as any)[key] || '#000000'}
            onChange={e => onChange({ ...theme, [key]: e.target.value })}
            className="w-7 h-7 rounded-lg border border-zinc-800 bg-black cursor-pointer p-0.5 shrink-0" />
          <input value={(theme as any)[key] || ''}
            onChange={e => onChange({ ...theme, [key]: e.target.value })}
            className="flex-1 bg-black border border-zinc-800 text-white text-[9px] p-2 rounded-lg outline-none focus:border-indigo-500 transition-all min-w-0" />
        </div>
      </label>
    ))}
    <label className="block">
      <span className="text-[8px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Скругление {theme.radius}px</span>
      <input type="range" min={0} max={32} value={theme.radius}
        onChange={e => onChange({ ...theme, radius: Number(e.target.value) })}
        className="w-full accent-indigo-500" />
    </label>
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[8px] font-black text-zinc-600 uppercase tracking-widest">Градиент</span>
        <button onClick={() => onChange({ ...theme, gradient: theme.gradient ? '' : MINI_PRESETS[0].theme.gradient || '' })}
          className={`w-8 h-4 rounded-full relative transition-all ${theme.gradient ? 'bg-indigo-500' : 'bg-zinc-700'}`}>
          <div className={`absolute top-0.5 w-3 h-3 bg-white rounded-full shadow transition-all ${theme.gradient ? 'left-4' : 'left-0.5'}`} />
        </button>
      </div>
      {theme.gradient && (
        <input value={theme.gradient}
          onChange={e => onChange({ ...theme, gradient: e.target.value })}
          placeholder="radial-gradient(...)"
          className="w-full bg-black border border-zinc-800 text-white text-[9px] p-2 rounded-lg outline-none focus:border-indigo-500 transition-all" />
      )}
    </div>
  </div>
);

// ── Настройки доставки формы ──────────────────────────────────────────────────

const FORM_BOT_USERNAME = '@formsdialoge_bot'; // заменить на актуальный username

const MiniFormSettings: React.FC<{
  app: MiniApp; onChange: (patch: Partial<MiniApp>) => void;
}> = ({ app, onChange }) => (
  <div className="p-3 space-y-3 overflow-y-auto h-full">
    <p className="text-[8px] font-black text-indigo-400 uppercase tracking-[0.2em]">Доставка заявок</p>

    <div className="space-y-1">
      {([
        { val: 'formbot' as MiniWebhookType, label: 'Бот форм',      desc: 'Рекомендуется. Добавьте бота в чат — заявки придут туда.' },
        { val: 'sheets'  as MiniWebhookType, label: 'Google Sheets',  desc: 'Данные записываются в таблицу через Apps Script.' },
        { val: 'webhook' as MiniWebhookType, label: 'Вебхук',         desc: 'POST на ваш URL (n8n, Make, Zapier и др.).' },
      ]).map(({ val, label, desc }) => (
        <button key={val} onClick={() => onChange({ webhookType: val })}
          className={`w-full text-left px-3 py-2.5 rounded-xl border text-[9px] transition-all ${
            app.webhookType === val
              ? 'bg-indigo-500/15 border-indigo-500/40 text-indigo-300'
              : 'border-zinc-800 text-zinc-500 hover:border-zinc-700 hover:text-zinc-300'
          }`}>
          <div className="font-black mb-0.5">{label}</div>
          <div className={`text-[8px] leading-relaxed ${app.webhookType === val ? 'text-indigo-400/70' : 'text-zinc-700'}`}>{desc}</div>
        </button>
      ))}
    </div>

    {app.webhookType === 'formbot' && (
      <div className="space-y-2">
        <label className="block">
          <span className="text-[8px] font-black text-zinc-600 uppercase tracking-widest block mb-1">ID чата</span>
          <input
            value={app.notifyChatId || ''}
            onChange={e => onChange({ notifyChatId: e.target.value })}
            placeholder="-100123456789"
            className="w-full bg-black border border-zinc-800 focus:border-indigo-500 text-white text-xs p-2.5 rounded-xl outline-none transition-all font-mono"
          />
        </label>
        <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-3 space-y-1.5">
          <p className="text-[8px] font-black text-zinc-500 uppercase tracking-widest">Как получить ID</p>
          <p className="text-[8px] text-zinc-600 leading-relaxed">
            1. Добавьте {FORM_BOT_USERNAME} в нужный чат.<br />
            2. Бот пришлёт ID этого чата — скопируйте его.<br />
            3. Вставьте ID в поле выше.<br />
            Для личных сообщений напишите боту /start.
          </p>
        </div>
      </div>
    )}

    {app.webhookType === 'sheets' && (
      <div className="space-y-2">
        <label className="block">
          <span className="text-[8px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Apps Script URL</span>
          <input
            value={app.sheetsUrl || ''}
            onChange={e => onChange({ sheetsUrl: e.target.value })}
            placeholder="https://script.google.com/macros/s/..."
            className="w-full bg-black border border-zinc-800 focus:border-emerald-500 text-white text-[9px] p-2.5 rounded-xl outline-none transition-all"
          />
        </label>
        <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-3 space-y-1.5">
          <p className="text-[8px] font-black text-zinc-500 uppercase tracking-widest">Подключение таблицы</p>
          <p className="text-[8px] text-zinc-600 leading-relaxed">
            1. Откройте Google Таблицу.<br />
            2. Расширения &rarr; Apps Script.<br />
            3. Создайте функцию doPost (пример ниже).<br />
            4. Опубликуйте: Развернуть &rarr; Веб-приложение, доступ — для всех.<br />
            5. Скопируйте URL публикации.
          </p>
          <pre className="text-[7px] text-zinc-500 bg-black/60 rounded-lg p-2 overflow-x-auto leading-relaxed whitespace-pre">{`function doPost(e) {
  var d = JSON.parse(e.postData.contents);
  var s = SpreadsheetApp
    .getActiveSpreadsheet()
    .getActiveSheet();
  var row = [new Date()];
  for (var k in d) {
    if (k[0] !== '_') row.push(k+': '+d[k]);
  }
  s.appendRow(row);
  return ContentService
    .createTextOutput('ok');
}`}</pre>
        </div>
      </div>
    )}

    {app.webhookType === 'webhook' && (
      <div className="space-y-2">
        <label className="block">
          <span className="text-[8px] font-black text-zinc-600 uppercase tracking-widest block mb-1">URL вебхука</span>
          <input
            value={app.formWebhook || ''}
            onChange={e => onChange({ formWebhook: e.target.value })}
            placeholder="https://..."
            className="w-full bg-black border border-zinc-800 focus:border-indigo-500 text-white text-[9px] p-2.5 rounded-xl outline-none transition-all"
          />
        </label>
        <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-3">
          <p className="text-[8px] text-zinc-600 leading-relaxed">
            Сервер отправит POST с JSON данных формы и полем _appId.<br />
            Совместимо с n8n, Make.com, Zapier и любым HTTP-эндпоинтом.
          </p>
        </div>
      </div>
    )}
  </div>
);

// ── Главный компонент вкладки ─────────────────────────────────────────────────
const MiniAppsTab: React.FC<{ bot: BotConfig; onUpdate: (b: BotConfig) => void; isVK: boolean }> = ({ bot, onUpdate, isVK }) => {
  const [apps, setApps]                   = React.useState<MiniApp[]>([]);
  const [loading, setLoading]             = React.useState(true);
  const [isProcessing, setIsProcessing]   = React.useState(false);
  const isLicenseValid = bot.license_expires_at ? new Date(bot.license_expires_at) > new Date() : false;
  const expiryDateStr = bot.license_expires_at ? new Date(bot.license_expires_at).toLocaleDateString() : '—';
  // Эти две переменные раньше не были объявлены — отсюда ReferenceError при покупке
  const [licenseActive, setLicenseActive] = React.useState<boolean>(isLicenseValid);
  const [licenseExpiry, setLicenseExpiry] = React.useState<number>(bot.license_expires_at || 0);
  const [licenseKey, setLicenseKey]       = React.useState('');
  const [activatingKey, setActivatingKey] = React.useState(false);
  const [keyStatus, setKeyStatus]         = React.useState('');
  const [editingId, setEditingId]         = React.useState<string | null>(null);
  const [selectedComp, setSelComp]        = React.useState<string | null>(null);
  const [rightTab, setRightTab]           = React.useState<'props' | 'theme' | 'form'>('form');
  const [saving, setSaving]               = React.useState(false);
  const [saved, setSaved]                 = React.useState(false);
  const [copiedId, setCopiedId]           = React.useState<string | null>(null);
  const [previewMode, setPreviewMode]     = React.useState(false);
  // Мобильный таб редактора
  const [mobileTab, setMobileTab]         = React.useState<'blocks' | 'canvas' | 'panel'>('canvas');

  const editing = apps.find(a => a.id === editingId) || null;
  const selComp = editing?.components.find(c => c.id === selectedComp) || null;
  const theme   = editing?.theme || DEFAULT_MINI_THEME;

  React.useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [licRes, appsRes] = await Promise.all([
          fetch(`/api/miniapps/license/${bot.id}`),
          fetch(`/api/miniapps/list-by-bot/${bot.id}`),
        ]);
        if (licRes.ok) {
          const lic = await licRes.json();
          setLicenseActive(lic.active || false);
          setLicenseExpiry(lic.expires_at || 0);
        }
        if (appsRes.ok) {
          const rows = await appsRes.json();
          setApps(rows.map((a: any) => ({
            ...a,
            webhookType:  a.webhookType  || a.webhook_type   || 'formbot',
            formWebhook:  a.formWebhook  || a.form_webhook   || '',
            sheetsUrl:    a.sheetsUrl    || a.sheets_url     || '',
            notifyChatId: a.notifyChatId || a.notify_chat_id || '',
          })));
        }
      } catch {
        try {
          const local = JSON.parse(localStorage.getItem(`miniapps_${bot.id}`) || '[]');
          setApps(local);
        } catch { /* ignore */ }
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [bot.id]);

  const activateKey = async () => {
    if (!licenseKey.trim()) return;
    setActivatingKey(true);
    setKeyStatus('Активация...');
    try {
      const r = await fetch('/api/miniapps/activate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: licenseKey.trim().toUpperCase(), botId: bot.id }),
      });
      const res = await r.json();
      if (res.status === 'ok') {
        setKeyStatus(`Активировано до ${new Date(res.expires_at).toLocaleDateString()}`);
        setLicenseActive(true);
        setLicenseExpiry(res.expires_at);
        setLicenseKey('');
      } else {
        setKeyStatus(res.message || 'Ошибка активации');
      }
    } catch {
      setKeyStatus('Ошибка сети');
    } finally {
      setActivatingKey(false);
    }
  };

  const persist = (next: MiniApp[]) => {
    setApps(next);
    localStorage.setItem(`miniapps_${bot.id}`, JSON.stringify(next));
  };

  const saveToServer = async (app: MiniApp) => {
    setSaving(true);
    try {
      const res = await fetch('/api/miniapps/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id:             app.id,
          owner_id:       bot.owner_id,
          bot_id:         bot.id,
          title:          app.title,
          theme:          app.theme,
          components:     app.components,
          webhook_type:   app.webhookType  || 'formbot',
          form_webhook:   app.formWebhook  || '',
          sheets_url:     app.sheetsUrl    || '',
          notify_chat_id: app.notifyChatId || '',
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      persist(apps.map(a => a.id === app.id ? app : a));
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      console.error('Ошибка сохранения:', err);
      alert('Не удалось сохранить. Проверьте консоль.');
    } finally {
      setSaving(false);
    }
  };

  const createApp = () => {
    const app: MiniApp = {
      id: mkMiniId(), title: 'Новое приложение',
      theme: { ...DEFAULT_MINI_THEME },
      components: [newMiniComp('heading'), newMiniComp('text'), newMiniComp('button')],
      webhookType: 'formbot', notifyChatId: '', formWebhook: '', sheetsUrl: '',
      bot_id: bot.id, owner_id: bot.owner_id,
    };
    persist([...apps, app]);
    setEditingId(app.id); setSelComp(null); setPreviewMode(false);
    setRightTab('form'); setMobileTab('canvas');
  };

  const deleteApp = async (id: string) => {
    if (!window.confirm('Удалить это мини-приложение?')) return;
    persist(apps.filter(a => a.id !== id));
    if (editingId === id) setEditingId(null);
    try {
      await fetch(`/api/miniapps/${id}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ owner_id: bot.owner_id }),
      });
    } catch { /* already removed from UI */ }
  };

  const updateApp = (patch: Partial<MiniApp>) => {
    if (!editing) return;
    const next = apps.map(a => a.id === editingId ? { ...a, ...patch } : a);
    setApps(next);
    localStorage.setItem(`miniapps_${bot.id}`, JSON.stringify(next));
  };

  const addComp = (type: MiniCompType) => {
    if (!editing) return;
    const newC = newMiniComp(type);
    updateApp({ components: [...editing.components, newC] });
    setSelComp(newC.id);
    setRightTab('props');
    setMobileTab('canvas');
  };

  const removeComp = (id: string) => {
    if (!editing) return;
    updateApp({ components: editing.components.filter(c => c.id !== id) });
    if (selectedComp === id) setSelComp(null);
  };

  const moveComp = (id: string, dir: -1 | 1) => {
    if (!editing) return;
    const comps = [...editing.components];
    const idx = comps.findIndex(c => c.id === id);
    const to = idx + dir;
    if (to < 0 || to >= comps.length) return;
    [comps[idx], comps[to]] = [comps[to], comps[idx]];
    updateApp({ components: comps });
  };

  const updateCompProps = (id: string, props: Partial<MiniCompProps>) => {
    if (!editing) return;
    updateApp({ components: editing.components.map(c => c.id === id ? { ...c, props: { ...c.props, ...props } } : c) });
  };

  const copyUrl = (id: string) => {
    navigator.clipboard.writeText(`${window.location.origin}/app/${id}`).then(() => {
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    });
  };

  if (loading) return (
    <div className="flex items-center justify-center py-24 gap-3">
      <div className="w-5 h-5 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin" />
      <span className="text-xs text-zinc-500 font-bold uppercase tracking-widest">Загрузка...</span>
    </div>
  );

  if (!licenseActive) return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <h2 className="text-2xl font-black text-white uppercase">Мини-приложения</h2>
      <div className="bg-indigo-500/5 border border-indigo-500/20 rounded-[2rem] p-6 md:p-8 text-center space-y-5">
        <div className="w-14 h-14 bg-indigo-500/10 border border-indigo-500/20 rounded-2xl flex items-center justify-center mx-auto">
          <AppWindow className="w-7 h-7 text-indigo-400" />
        </div>
        
        <div>
          <p className="text-white font-black text-lg mb-2">Подписка не активна</p>
          <p className="text-zinc-500 text-sm leading-relaxed max-w-sm mx-auto">
            Публичные веб-страницы с формами и контентом для вашего бота.<br />
            Стоимость: <strong className="text-indigo-400">90 ₽ / 30 дней</strong>.
          </p>
        </div>

        <div className="max-w-sm mx-auto pt-4">
          <button 
            onClick={async () => {
              if (!window.confirm('Списать 90 ₽ с баланса для активации Мини-приложений?')) return;
              setActivatingKey(true);
              try {
                // 1. Вызываем API покупки
                const res = await api.buyService(bot.owner_id, 'miniapp_30d', bot.id);
                
                if (res && res.status === 'ok') {
                  // Берём expires_at из ответа сервера, или считаем локально как fallback
                  const addMs = 30 * 86400000;
                  const currentExp = bot.license_expires_at || Date.now();
                  const newExp = res.expires_at || (Math.max(currentExp, Date.now()) + addMs);

                  // Обновляем родительский компонент чтобы данные сохранились
                  onUpdate({ ...bot, license_expires_at: newExp });
                  setLicenseActive(true);
                  setLicenseExpiry(newExp);
                  alert('Мини-приложения успешно активированы!');
                } else {
                  alert(res?.detail || 'Недостаточно средств на балансе. Пополните его в профиле.');
                }
              } catch (e) {
                console.error('Ошибка активации:', e);
                alert('Ошибка при связи с сервером. Попробуйте позже.');
              } finally {
                setActivatingKey(false);
              }
            }}
            disabled={activatingKey}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white font-black py-4 rounded-2xl text-xs uppercase tracking-[0.2em] transition-all flex items-center justify-center gap-3 shadow-lg shadow-indigo-600/20"
          >
            {activatingKey ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <>
                <Zap className="w-4 h-4 fill-current" />
                Оплатить с баланса
              </>
            )}
          </button>
          
          <p className="mt-4 text-[10px] text-zinc-600 font-bold uppercase tracking-wider">
            Средства будут списаны с вашего личного счета
          </p>
        </div>
      </div>
    </div>
  );

  if (!editingId) return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* ПАНЕЛЬ ЗАГОЛОВКА */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-black text-white uppercase tracking-tight">Мини-приложения</h2>
          <p className="text-[10px] text-emerald-400 mt-0.5 font-bold flex items-center gap-1.5">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            Активно до {bot.license_expires_at ? new Date(bot.license_expires_at).toLocaleDateString() : '—'}
          </p>
        </div>
        <button 
          onClick={createApp}
          className="bg-indigo-600 hover:bg-indigo-500 px-6 py-3 rounded-2xl text-[11px] font-black text-white uppercase flex items-center gap-2 shadow-lg shadow-indigo-600/20 transition-all active:scale-95"
        >
          <Plus className="w-4 h-4" /> Создать
        </button>
      </div>

      {/* КАРТОЧКА ЛИЦЕНЗИИ И ПРОДЛЕНИЯ */}
      <div className="bg-[#111] border border-zinc-800 p-6 md:p-8 rounded-[2.5rem] flex flex-col lg:flex-row items-stretch lg:items-center gap-8">
        {/* Левая часть: Статус */}
        <div className="flex-1">
          <h3 className="text-[11px] font-black text-white uppercase tracking-[0.2em] flex items-center gap-2 mb-4 opacity-80">
            <AppWindow className="w-4 h-4 text-indigo-400" /> 
            Статус подписки
          </h3>
          
          <div className="grid grid-cols-2 gap-3 md:gap-4">
            <div className="bg-black/50 border border-zinc-800/50 p-4 rounded-2xl flex flex-col items-center justify-center text-center">
              <p className={`text-base md:text-lg font-black leading-none mb-1.5 ${licenseActive ? 'text-emerald-400' : 'text-rose-400'}`}>
                {licenseActive ? 'АКТИВНА' : 'ИСТЕКЛА'}
              </p>
              <p className="text-[8px] text-zinc-600 uppercase font-black tracking-widest">Лицензия</p>
            </div>
            
            <div className="bg-black/50 border border-zinc-800/50 p-4 rounded-2xl flex flex-col items-center justify-center text-center">
              <p className="text-base md:text-lg font-black text-blue-400 leading-none mb-1.5">
                {bot.license_expires_at ? new Date(bot.license_expires_at).toLocaleDateString() : '—'}
              </p>
              <p className="text-[8px] text-zinc-600 uppercase font-black tracking-widest">До даты</p>
            </div>
          </div>
        </div>

        {/* Разделитель */}
        <div className="hidden lg:block w-px h-16 bg-zinc-800/50" />

        {/* Правая часть: Кнопки покупки */}
        <div className="w-full lg:w-72 flex flex-col gap-3">
          <p className="text-[9px] text-zinc-500 font-black uppercase tracking-widest ml-1">Быстрое продление</p>
          <div className="flex gap-2">
            {[
              { id: 'miniapp_30d', label: '30 ДНЕЙ', price: 90 },
              { id: 'miniapp_90d', label: '90 ДНЕЙ', price: 250 }
            ].map((pkg) => (
              <button
                key={pkg.id}
                disabled={isProcessing}
                onClick={async () => {
                  if (!window.confirm(`Списать ${pkg.price}₽ с баланса?`)) return;
                  setIsProcessing(true);
                  try {
                    const res = await api.buyService(bot.owner_id, pkg.id, bot.id);
                    if (res?.status === 'ok') {
                      const days = pkg.id === 'miniapp_30d' ? 30 : 90;
                      const currentExp = bot.license_expires_at || Date.now();
                      const newExp = res.expires_at || (Math.max(currentExp, Date.now()) + (days * 86400000));
                      onUpdate({ ...bot, license_expires_at: newExp });
                      setLicenseActive(true);
                      setLicenseExpiry(newExp);
                      alert('Подписка продлена!');
                    } else {
                      alert(res?.detail || 'Недостаточно средств');
                    }
                  } catch (e) {
                    alert('Ошибка сервера');
                  } finally {
                    setIsProcessing(false);
                  }
                }}
                className="flex-1 flex flex-col items-center justify-center px-2 py-3.5 bg-zinc-900 border border-zinc-800 rounded-2xl hover:border-indigo-500/50 hover:bg-indigo-500/5 transition-all active:scale-95 disabled:opacity-50"
              >
                <div className="text-indigo-400 font-black text-[10px] mb-0.5">{pkg.label}</div>
                <div className="text-[10px] text-white font-bold">{pkg.price}₽</div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* СПИСОК ПРИЛОЖЕНИЙ */}
      {apps.length === 0 ? (
        <div className="border-2 border-dashed border-zinc-800 rounded-[2rem] p-14 text-center">
          <AppWindow className="w-12 h-12 text-zinc-800 mx-auto mb-4 opacity-20" />
          <p className="text-zinc-600 font-black text-sm uppercase tracking-widest">Нет мини-приложений</p>
          <button onClick={createApp}
            className="mt-6 bg-indigo-600 hover:bg-indigo-500 px-8 py-3.5 rounded-2xl text-[11px] font-black text-white uppercase inline-flex items-center gap-2 transition-all">
            <Plus className="w-4 h-4" /> Создать первое
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {apps.map(app => {
            const deliveryLabel = app.webhookType === 'formbot' ? 'бот форм' : app.webhookType === 'sheets' ? 'таблица' : 'вебхук';
            return (
              <div key={app.id} 
                style={{ 
                  borderColor: (app.theme?.primary || '#6366f1') + '30', 
                  background: (app.theme?.bg || '#0a0a0f') + '20' 
                }}
                className="border rounded-[2rem] overflow-hidden hover:scale-[1.01] transition-all group"
              >
                <div style={{ background: app.theme?.bg || '#0a0a0f', minHeight: 100, position: 'relative', overflow: 'hidden' }}>
                  {app.theme?.gradient && <div style={{ position: 'absolute', inset: 0, background: app.theme.gradient, opacity: 0.4 }} />}
                  <div className="relative z-10 p-6">
                    <p style={{ color: app.theme?.textSecondary || '#71717a', fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 4 }}>
                      {app.components?.length || 0} блоков · {deliveryLabel}
                    </p>
                    <p style={{ color: app.theme?.textPrimary || '#ffffff', fontWeight: 800, fontSize: 18, fontFamily: app.theme?.font }}>
                      {app.title}
                    </p>
                  </div>
                </div>

                <div className="p-4 flex items-center gap-2 bg-zinc-900/50 border-t border-zinc-800/50">
                  <button onClick={() => { setEditingId(app.id); setSelComp(null); setPreviewMode(false); setMobileTab('canvas'); }}
                    className="flex-1 text-[9px] font-black uppercase text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 py-3 rounded-xl transition-all flex items-center justify-center gap-1.5">
                    <Palette className="w-3 h-3" /> Настроить
                  </button>
                  
                  <button onClick={() => copyUrl(app.id)}
                    className={`flex items-center gap-1.5 text-[9px] font-black uppercase py-3 px-4 rounded-xl transition-all ${copiedId === app.id ? 'bg-emerald-500/20 text-emerald-400' : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white'}`}>
                    {copiedId === app.id ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                    {copiedId === app.id ? 'OK' : 'URL'}
                  </button>

                  <button onClick={() => deleteApp(app.id)}
                    className="py-3 px-4 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-500 transition-all">
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );

  // ── Редактор ─────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-0 animate-in fade-in duration-300">
      {/* Топ-бар */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <button onClick={() => { setEditingId(null); setSelComp(null); }}
          className="flex items-center gap-1.5 text-zinc-500 hover:text-white text-[10px] font-black uppercase tracking-widest transition-colors shrink-0">
          <ArrowRight className="w-3 h-3 rotate-180" /> Все
        </button>
        <div className="h-4 w-px bg-zinc-800 shrink-0" />
        <input value={editing!.title} onChange={e => updateApp({ title: e.target.value })}
          className="text-white font-black text-sm bg-transparent outline-none border-b border-transparent focus:border-indigo-500 transition-all flex-1 min-w-0" placeholder="Название" />
        <button onClick={() => setPreviewMode(v => !v)}
          className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-[9px] font-black uppercase transition-all shrink-0 ${previewMode ? 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30' : 'bg-zinc-800 text-zinc-400 border border-zinc-700'}`}>
          {previewMode ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
          <span className="hidden sm:inline">{previewMode ? 'Редактор' : 'Превью'}</span>
        </button>
        <button onClick={() => saveToServer(editing!)} disabled={saving}
          className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-[9px] font-black uppercase tracking-wider transition-all shrink-0 ${saved ? 'bg-emerald-600 text-white' : 'bg-indigo-600 hover:bg-indigo-500 text-white'}`}>
          {saved ? <Check className="w-3 h-3" /> : <Save className="w-3 h-3" />}
          {saved ? 'Сохранено' : saving ? '...' : 'Сохранить'}
        </button>
        <button onClick={() => copyUrl(editing!.id)}
          className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-[9px] font-black uppercase transition-all border shrink-0 ${copiedId === editing!.id ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-zinc-800 text-zinc-400 border-zinc-700 hover:text-white'}`}>
          {copiedId === editing!.id ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
          <span className="hidden sm:inline">{copiedId === editing!.id ? 'Скопировано' : 'Ссылка'}</span>
        </button>
      </div>

      {/* Мобильные табы (только на маленьких экранах) */}
      {!previewMode && (
        <div className="flex md:hidden gap-1 mb-3 bg-zinc-900 border border-zinc-800 rounded-xl p-1">
          {([
            { id: 'blocks' as const, label: 'Блоки' },
            { id: 'canvas' as const, label: 'Холст' },
            { id: 'panel'  as const, label: rightTab === 'form' ? 'Форма' : rightTab === 'theme' ? 'Тема' : 'Свойства' },
          ]).map(({ id, label }) => (
            <button key={id} onClick={() => setMobileTab(id)}
              className={`flex-1 py-2 rounded-lg text-[10px] font-black uppercase tracking-wider transition-all ${mobileTab === id ? 'bg-indigo-600 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}>
              {label}
            </button>
          ))}
        </div>
      )}

      <div className="flex gap-3" style={{ minHeight: 'min(560px, 70vh)' }}>
        {/* Левая: блоки */}
        {!previewMode && (
          <div className={`w-36 shrink-0 flex-col gap-0.5 ${mobileTab !== 'blocks' ? 'hidden md:flex' : 'flex'}`}>
            <p className="text-[8px] font-black text-zinc-600 uppercase tracking-[0.2em] mb-2 px-1">Блоки</p>
            {MINI_PALETTE.map(item => {
              const Icon = item.icon;
              return (
                <button key={item.type} onClick={() => addComp(item.type)}
                  className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl text-zinc-500 hover:text-white hover:bg-zinc-800/60 transition-all text-left group">
                  <div className="w-6 h-6 rounded-lg bg-indigo-500/10 flex items-center justify-center shrink-0 group-hover:bg-indigo-500/20 transition-all">
                    <Icon className="w-3 h-3 text-indigo-400" />
                  </div>
                  <span className="text-[10px] font-bold">{item.label}</span>
                </button>
              );
            })}
          </div>
        )}

        {/* Холст */}
        <div className={`flex-1 min-w-0 rounded-[1.5rem] border border-zinc-800 overflow-y-auto ${(!previewMode && mobileTab !== 'canvas') ? 'hidden md:block' : 'block'}`}
          onClick={() => !previewMode && setSelComp(null)}>
          <div style={{ background: theme.bg, minHeight: '100%', position: 'relative' }}>
            {theme.gradient && <div style={{ position: 'absolute', inset: 0, background: theme.gradient, pointerEvents: 'none', zIndex: 0 }} />}
            <div style={{ position: 'relative', zIndex: 1, padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
              {editing!.components.length === 0 && (
                <div style={{ textAlign: 'center', padding: '40px 0', opacity: 0.3 }}>
                  <p style={{ color: theme.textSecondary, fontSize: 12, fontFamily: theme.font }}>Добавьте блоки</p>
                </div>
              )}
              {editing!.components.map((comp, idx) => (
                <div key={comp.id} style={{ position: 'relative' }}
                  onClick={e => { if (!previewMode) { e.stopPropagation(); setSelComp(comp.id); setRightTab('props'); setMobileTab('panel'); } }}>
                  <MiniPreviewComp comp={comp} theme={theme} selected={!previewMode && selectedComp === comp.id} />
                  {!previewMode && selectedComp === comp.id && (
                    <div className="absolute -top-2 -right-2 flex gap-0.5 z-10">
                      <button onClick={e => { e.stopPropagation(); moveComp(comp.id, -1); }} disabled={idx === 0}
                        className="w-5 h-5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 flex items-center justify-center disabled:opacity-30 shadow">
                        <ChevronUp className="w-2.5 h-2.5" />
                      </button>
                      <button onClick={e => { e.stopPropagation(); moveComp(comp.id, 1); }} disabled={idx === editing!.components.length - 1}
                        className="w-5 h-5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 flex items-center justify-center disabled:opacity-30 shadow">
                        <ChevronDown className="w-2.5 h-2.5" />
                      </button>
                      <button onClick={e => { e.stopPropagation(); removeComp(comp.id); }}
                        className="w-5 h-5 rounded bg-rose-600 hover:bg-rose-500 text-white flex items-center justify-center shadow">
                        <X className="w-2.5 h-2.5" />
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Правая: свойства / тема / форма */}
        {!previewMode && (
          <div className={`w-52 shrink-0 bg-[#0d0d0d] border border-zinc-800 rounded-[1.5rem] overflow-hidden flex-col ${mobileTab !== 'panel' ? 'hidden md:flex' : 'flex'}`}>
            <div className="flex border-b border-zinc-800 shrink-0">
              {([
                { id: 'props' as const, label: 'Блок',  icon: Settings },
                { id: 'theme' as const, label: 'Тема',  icon: Palette },
                { id: 'form'  as const, label: 'Форма', icon: Link2 },
              ]).map(({ id, label, icon: Icon }) => (
                <button key={id} onClick={() => setRightTab(id)}
                  className={`flex-1 flex items-center justify-center gap-1 py-2.5 text-[8px] font-black uppercase tracking-widest border-b-2 transition-all ${rightTab === id ? 'border-indigo-500 text-indigo-400' : 'border-transparent text-zinc-600 hover:text-zinc-400'}`}>
                  <Icon className="w-3 h-3" /> {label}
                </button>
              ))}
            </div>
            <div className="flex-1 overflow-hidden">
              {rightTab === 'props' && <MiniPropsPanel comp={selComp} theme={theme} onChange={updateCompProps} />}
              {rightTab === 'theme' && editing && <MiniThemePanel theme={editing.theme} onChange={t => updateApp({ theme: t })} />}
              {rightTab === 'form'  && editing && <MiniFormSettings app={editing} onChange={updateApp} />}
            </div>
            {rightTab === 'props' && editing!.components.length > 0 && (
              <div className="border-t border-zinc-800 p-2 shrink-0">
                <p className="text-[7px] font-black text-zinc-700 uppercase tracking-widest mb-1.5 px-1">Слои</p>
                <div className="space-y-0.5 max-h-36 overflow-y-auto">
                  {editing!.components.map((c, i) => {
                    const itm = MINI_PALETTE.find(pl => pl.type === c.type);
                    const Ic = itm?.icon || Square;
                    return (
                      <button key={c.id} onClick={() => { setSelComp(c.id); setRightTab('props'); setMobileTab('panel'); }}
                        className={`w-full flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-[9px] font-bold transition-all ${selectedComp === c.id ? 'bg-indigo-500/15 text-indigo-300' : 'text-zinc-600 hover:text-zinc-300 hover:bg-zinc-800/40'}`}>
                        <Ic className="w-2.5 h-2.5 shrink-0" />
                        <span className="truncate">{itm?.label || c.type}</span>
                        <span className="ml-auto text-zinc-700">{i + 1}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};


// ══════════════════════════════════════════════════════════════════════════════
//  РАСШИРЕННАЯ ЛОГИКА КНОПОК — Flow-редактор (только Telegram)
// ══════════════════════════════════════════════════════════════════════════════

type FlowActionType = 'message' | 'admin_notify' | 'code' | 'buttons' | 'create_ticket';

interface FlowAction {
  id: string;
  type: FlowActionType;
  text?: string;
  code?: string;
  buttons?: FlowNode[];
  // create_ticket fields
  ticketUserText?: string;
  ticketAdminText?: string;
  ticketBtnLabel?: string;
}

interface FlowNode {
  id: string;
  label: string;
  actions: FlowAction[];
}

const mkFlowId = () => Math.random().toString(36).slice(2, 8);

const ACTION_META: Record<FlowActionType, { label: string; color: string; desc: string }> = {
  message:       { label: 'Сообщение пользователю', color: 'bg-blue-500/15 text-blue-400 border-blue-500/25',    desc: 'Бот отправит текст пользователю' },
  admin_notify:  { label: 'Уведомить админов',       color: 'bg-amber-500/15 text-amber-400 border-amber-500/25', desc: 'Сообщение придёт в чат администраторов' },
  code:          { label: 'Выполнить код',            color: 'bg-violet-500/15 text-violet-400 border-violet-500/25', desc: 'Python-код на сервере' },
  buttons:       { label: 'Показать под-кнопки',      color: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/25', desc: 'Разветвление на новые кнопки' },
  create_ticket: { label: 'Создать тикет',            color: 'bg-rose-500/15 text-rose-400 border-rose-500/25',   desc: 'Открывает обращение в поддержку' },
};

const CODE_SNIPPETS: { label: string; code: string }[] = [
  {
    label: 'Погода (OpenWeatherMap)',
    code: `# requests уже доступен — import не нужен
api_key = 'ВАШ_КЛЮЧ'  # бесплатно на openweathermap.org
city = 'Moscow'

r = requests.get(
    'https://api.openweathermap.org/data/2.5/weather',
    params={'q': city, 'appid': api_key, 'units': 'metric', 'lang': 'ru'}
)
data = r.json()
temp = data['main']['temp']
desc = data['weather'][0]['description']
reply_text = f"Погода в {city}: {temp}°C, {desc}"`,
  },
  {
    label: 'Курс валют (ЦБ РФ)',
    code: `# ET (xml.etree.ElementTree) и requests уже доступны
r = requests.get('https://www.cbr.ru/scripts/XML_daily.asp')
root = ET.fromstring(r.content)
rates = {}
for v in root.findall('Valute'):
    code_v = v.find('CharCode').text
    val    = v.find('Value').text.replace(',', '.')
    nom    = int(v.find('Nominal').text)
    rates[code_v] = float(val) / nom

usd = rates.get('USD', 0)
eur = rates.get('EUR', 0)
reply_text = f"USD: {usd:.2f} руб\\nEUR: {eur:.2f} руб"`,
  },
  {
    label: 'GET-запрос к API',
    code: `url = 'https://api.example.com/endpoint'
r = requests.get(
    url,
    headers={'Authorization': 'Bearer ВАШ_ТОКЕН'},
    params={'user_id': user_id, 'query': text}
)
if r.status_code == 200:
    data = r.json()
    reply_text = str(data.get('result', ''))
else:
    reply_text = f"Ошибка: {r.status_code}"`,
  },
  {
    label: 'POST с JSON',
    code: `payload = {
    'user_id':  user_id,
    'username': username,
    'message':  text,
}
r = requests.post('https://api.example.com/data', json=payload)
result = r.json()
reply_text = result.get('message', 'Отправлено')`,
  },
  {
    label: 'Курс крипты (CoinGecko)',
    code: `r = requests.get(
    'https://api.coingecko.com/api/v3/simple/price',
    params={'ids': 'bitcoin,ethereum', 'vs_currencies': 'usd,rub'}
)
data = r.json()
btc_usd = data['bitcoin']['usd']
btc_rub = data['bitcoin']['rub']
eth_usd = data['ethereum']['usd']
reply_text = (
    f"Bitcoin:  \${btc_usd:,} / {btc_rub:,} руб\\n"
    f"Ethereum: \${eth_usd:,}"
)`,
  },
  {
    label: 'Случайная цитата',
    code: `r = requests.get('http://api.quotable.io/random')
if r.status_code == 200:
    q = r.json()
    reply_text = f'"{q["content"]}"\\n— {q["author"]}'
else:
    reply_text = 'Не удалось получить цитату'`,
  },
  {
    label: 'Webhook (Zapier / n8n / Make)',
    code: `webhook_url = 'https://hooks.zapier.com/...'
requests.post(webhook_url, json={
    'bot_id':   bot_id,
    'user_id':  user_id,
    'username': username,
    'text':     text,
})
reply_text = 'Данные отправлены'`,
  },
];


// Минималистичный code-редактор с номерами строк и Tab-indent
const CodeEditor: React.FC<{
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}> = ({ value, onChange, placeholder }) => {
  const taRef = React.useRef<HTMLTextAreaElement>(null);
  const linesRef = React.useRef<HTMLDivElement>(null);

  const lineCount = (value || '').split('\n').length;
  const lineNums = Array.from({ length: Math.max(lineCount, 8) }, (_, i) => i + 1);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const ta = e.currentTarget;
    if (e.key === 'Tab') {
      e.preventDefault();
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const newVal = value.substring(0, start) + '    ' + value.substring(end);
      onChange(newVal);
      requestAnimationFrame(() => {
        ta.selectionStart = ta.selectionEnd = start + 4;
      });
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      const start = ta.selectionStart;
      const lines = value.substring(0, start).split('\n');
      const curLine = lines[lines.length - 1];
      const indent = curLine.match(/^(\s*)/)?.[1] || '';
      // Автоотступ после двоеточия
      const extraIndent = curLine.trimEnd().endsWith(':') ? '    ' : '';
      const ins = '\n' + indent + extraIndent;
      const newVal = value.substring(0, start) + ins + value.substring(ta.selectionEnd);
      onChange(newVal);
      requestAnimationFrame(() => {
        ta.selectionStart = ta.selectionEnd = start + ins.length;
      });
    }
  };

  const syncScroll = () => {
    if (linesRef.current && taRef.current) {
      linesRef.current.scrollTop = taRef.current.scrollTop;
    }
  };

  return (
    <div className="rounded-xl border border-zinc-800 overflow-hidden font-mono text-[11px] leading-5 bg-[#0a0a14]">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-zinc-800 bg-zinc-900/60 flex-wrap">
        <span className="text-[8px] font-black text-violet-400 uppercase tracking-widest">Python</span>
        <span className="text-[8px] text-zinc-700">{lineCount} стр.</span>
        <div className="flex-1" />
        <span className="text-[8px] text-zinc-700">Tab = 4 пробела · Enter = автоотступ</span>
      </div>
      {/* Editor area */}
      <div className="flex overflow-hidden" style={{ maxHeight: 320 }}>
        {/* Line numbers */}
        <div
          ref={linesRef}
          className="shrink-0 overflow-hidden select-none bg-zinc-900/40 border-r border-zinc-800/60 py-2"
          style={{ width: 38 }}
        >
          {lineNums.map(n => (
            <div key={n} className="text-right pr-2.5 text-zinc-700 leading-5" style={{ fontSize: 10 }}>{n}</div>
          ))}
        </div>
        {/* Textarea */}
        <textarea
          ref={taRef}
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onScroll={syncScroll}
          placeholder={placeholder}
          spellCheck={false}
          className="flex-1 bg-transparent text-violet-200 py-2 px-3 outline-none resize-none overflow-auto leading-5 placeholder:text-zinc-700"
          style={{ fontSize: 11, minHeight: 180, maxHeight: 320, tabSize: 4 }}
        />
      </div>
    </div>
  );
};

const FlowBadge: React.FC<{ type: FlowActionType }> = ({ type }) => (
  <span className={`inline-flex items-center border rounded-lg px-2.5 py-1 text-[9px] font-black uppercase tracking-wide ${ACTION_META[type].color}`}>
    {ACTION_META[type].label}
  </span>
);

// Редактор одного действия
const FlowActionEditor: React.FC<{
  action: FlowAction;
  depth: number;
  onChange: (a: FlowAction) => void;
  onDelete: () => void;
  bot: BotConfig;
  onUpdate: (b: BotConfig) => void;
}> = ({ action, depth, onChange, onDelete, bot, onUpdate }) => {
  const [collapsed, setCollapsed] = React.useState(false);
  const [snippetOpen, setSnippetOpen] = React.useState(false);

  const addChildNode = () => {
    const node: FlowNode = { id: mkFlowId(), label: 'Новая кнопка', actions: [] };
    onChange({ ...action, buttons: [...(action.buttons || []), node] });
  };
  const updateChildNode = (idx: number, node: FlowNode) => {
    const nb = [...(action.buttons || [])]; nb[idx] = node;
    onChange({ ...action, buttons: nb });
  };
  const deleteChildNode = (idx: number) => {
    onChange({ ...action, buttons: (action.buttons || []).filter((_, i) => i !== idx) });
  };

  // Нормализуем существующие под-ноды — добавляем id если отсутствует
  const normalizedButtons: FlowNode[] = (action.buttons || []).map((n: any) => ({
    ...n,
    id: n.id || mkFlowId(),
    label: n.label || '',
    actions: n.actions || [],
  }));

  return (
    <div className={`rounded-2xl border overflow-hidden ${depth % 2 === 0 ? 'bg-zinc-900/50 border-zinc-800' : 'bg-black/40 border-zinc-800/60'}`}>
      <div className="flex items-center gap-3 px-4 py-3">
        <button onClick={() => setCollapsed(v => !v)} className="text-zinc-600 hover:text-zinc-300 transition-colors shrink-0">
          {collapsed ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronUp className="w-3.5 h-3.5" />}
        </button>
        <FlowBadge type={action.type} />
        {collapsed && action.text && (
          <span className="text-[10px] text-zinc-600 truncate flex-1">{action.text.slice(0, 60)}</span>
        )}
        <div className="flex-1" />
        <button onClick={onDelete} className="text-zinc-700 hover:text-rose-500 transition-colors">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {!collapsed && (
        <div className="px-4 pb-4 space-y-3">
          {(action.type === 'message' || action.type === 'admin_notify') && (
            <div>
              <span className="text-[8px] font-black text-zinc-600 uppercase tracking-widest block mb-1.5">
                {action.type === 'admin_notify'
                  ? 'Текст для чата админов — переменные: {username}, {first_name}, {user_id}, {text}'
                  : `Текст для пользователя${bot.platform !== 'vk' ? ' — поддерживается HTML' : ' (VK: plain text, без HTML)'}`}
              </span>
              <textarea
                rows={3}
                className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white text-xs p-3 rounded-xl outline-none resize-none transition-all"
                placeholder={action.type === 'admin_notify'
                  ? 'Обращение от {username}:\n{text}'
                  : 'Ваша заявка принята. Ожидайте ответа.'}
                value={action.text || ''}
                onChange={e => onChange({ ...action, text: e.target.value })}
              />
            </div>
          )}

          {action.type === 'code' && (
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <span className="text-[8px] font-black text-violet-400 uppercase tracking-widest">Python-код</span>
                <span className="text-[8px] text-zinc-600">переменные: user_id, username, first_name, text, bot_id</span>
                <div className="flex-1" />
                <div className="relative">
                  <button
                    onClick={() => setSnippetOpen(v => !v)}
                    className="text-[8px] font-black text-zinc-500 hover:text-zinc-300 border border-zinc-800 hover:border-zinc-600 rounded-lg px-2.5 py-1.5 transition-all flex items-center gap-1.5"
                  >
                    <Hash className="w-2.5 h-2.5" /> Шаблоны
                  </button>
                  {snippetOpen && (
                    <div className="absolute right-0 top-8 z-50 bg-[#111] border border-zinc-700 rounded-2xl shadow-2xl w-64 overflow-hidden">
                      {CODE_SNIPPETS.map((s, si) => (
                        <button
                          key={si}
                          onClick={() => { onChange({ ...action, code: s.code }); setSnippetOpen(false); }}
                          className="w-full text-left px-4 py-3 text-[10px] text-zinc-400 hover:bg-zinc-800 hover:text-white transition-all border-b border-zinc-800/60 last:border-0"
                        >
                          {s.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              <CodeEditor
                value={action.code || ''}
                onChange={code => onChange({ ...action, code })}
                placeholder={"# Напишите Python-код\n# или выберите шаблон выше"}
              />
              <p className="text-[8px] text-zinc-600">
                Код выполняется в изолированном окружении. Можно использовать requests, json, datetime, xml.etree.
              </p>
            </div>
          )}

          {action.type === 'buttons' && (
            <div className="space-y-3">
              <p className="text-[8px] font-black text-zinc-600 uppercase tracking-widest">
                Под-кнопки — пользователь увидит их как меню
              </p>
              {normalizedButtons.map((node, idx) => (
                <FlowNodeEditor
                  key={node.id}
                  node={node}
                  depth={depth + 1}
                  onChange={n => updateChildNode(idx, n)}
                  onDelete={() => deleteChildNode(idx)}
                  bot={bot}
                  onUpdate={onUpdate}
                />
              ))}
              <button
                onClick={addChildNode}
                className="w-full py-3 rounded-xl border border-dashed border-emerald-500/30 text-emerald-500 text-[9px] font-black uppercase hover:border-emerald-500/50 hover:bg-emerald-500/5 transition-all flex items-center justify-center gap-1.5"
              >
                <Plus className="w-3 h-3" /> Добавить под-кнопку
              </button>
            </div>
          )}

          {action.type === 'create_ticket' && (
            <div className="space-y-4">
              {/* Дефолтные значения из настроек бота */}
              <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-3 text-[9px] text-zinc-500 leading-relaxed">
                <p className="font-black text-zinc-400 mb-1">Как работает тикет</p>
                <p>При срабатывании — пользователь переводится в режим обращения. Его следующие сообщения пересылаются в чат администраторов до закрытия тикета.</p>
              </div>

              <div>
                <span className="text-[8px] font-black text-zinc-600 uppercase tracking-widest block mb-1.5">
                  Текст кнопки закрытия тикета у пользователя
                </span>
                <input
                  className="w-full bg-black border border-zinc-800 focus:border-rose-500 text-white text-xs p-3 rounded-xl outline-none transition-all"
                  placeholder="Закрыть обращение (по умолчанию)"
                  value={action.ticketBtnLabel || ''}
                  onChange={e => onChange({ ...action, ticketBtnLabel: e.target.value })}
                />
              </div>

              <div>
                <span className="text-[8px] font-black text-zinc-600 uppercase tracking-widest block mb-1.5">
                  Сообщение пользователю при открытии тикета
                </span>
                <textarea
                  rows={3}
                  className="w-full bg-black border border-zinc-800 focus:border-rose-500 text-white text-xs p-3 rounded-xl outline-none resize-none transition-all"
                  placeholder={bot.settings?.ticketMessageHeader
                    ? `По умолчанию из настроек: "${(bot.settings as any).ticketMessageHeader}"`
                    : 'Ваше обращение принято. Ожидайте ответа оператора.'}
                  value={action.ticketUserText || ''}
                  onChange={e => onChange({ ...action, ticketUserText: e.target.value })}
                />
                <p className="text-[8px] text-zinc-700 mt-1">Оставьте пустым — будет использован текст из поля «Ответ системы» кнопки.</p>
              </div>

              <div>
                <span className="text-[8px] font-black text-zinc-600 uppercase tracking-widest block mb-1.5">
                  Заголовок уведомления в чат администраторов
                </span>
                <textarea
                  rows={2}
                  className="w-full bg-black border border-zinc-800 focus:border-rose-500 text-white text-xs p-3 rounded-xl outline-none resize-none transition-all"
                  placeholder="Переменные: {username}, {first_name}, {user_id}, {btn}"
                  value={action.ticketAdminText || ''}
                  onChange={e => onChange({ ...action, ticketAdminText: e.target.value })}
                />
                <p className="text-[8px] text-zinc-700 mt-1">Оставьте пустым — будет использован стандартный заголовок из основных настроек.</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// Редактор одной ноды (кнопка + цепочка действий)
const FlowNodeEditor: React.FC<{
  node: FlowNode;
  depth: number;
  onChange: (n: FlowNode) => void;
  onDelete: () => void;
  bot: BotConfig;
  onUpdate: (b: BotConfig) => void;
}> = ({ node, depth, onChange, onDelete, bot, onUpdate }) => {
  const depthColors = ['border-l-blue-500', 'border-l-emerald-500', 'border-l-amber-500', 'border-l-violet-500', 'border-l-rose-400'];
  const lineColor = depthColors[depth % depthColors.length];

  const addAction = (type: FlowActionType) => {
    const action: FlowAction = { id: mkFlowId(), type, text: '', code: '', buttons: [] };
    onChange({ ...node, actions: [...node.actions, action] });
  };
  const updateAction = (idx: number, a: FlowAction) => {
    const na = [...node.actions]; na[idx] = a;
    onChange({ ...node, actions: na });
  };
  const deleteAction = (idx: number) => {
    onChange({ ...node, actions: node.actions.filter((_, i) => i !== idx) });
  };

  return (
    <div className={`border-l-2 ${lineColor} pl-4 space-y-3`}>
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-2 flex-1 bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-2.5 focus-within:border-zinc-600 transition-colors">
          <MousePointerClick className="w-3 h-3 text-zinc-500 shrink-0" />
          <input
            className="flex-1 bg-transparent text-white text-xs font-bold outline-none placeholder:text-zinc-600"
            placeholder="Текст кнопки..."
            value={node.label}
            onChange={e => onChange({ ...node, label: e.target.value })}
          />
        </div>
        <button onClick={onDelete} className="text-zinc-700 hover:text-rose-500 transition-colors p-1 shrink-0">
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {node.actions.length > 0 && (
        <div className="flex items-center gap-2 ml-1">
          <ArrowRight className="w-3 h-3 text-zinc-700 shrink-0" />
          <span className="text-[8px] text-zinc-700 font-bold uppercase tracking-widest">Тогда:</span>
        </div>
      )}

      {node.actions.length > 0 && (
        <div className="space-y-2">
          {node.actions.map((action, idx) => (
            <FlowActionEditor
              key={action.id}
              action={action}
              depth={depth}
              onChange={a => updateAction(idx, a)}
              onDelete={() => deleteAction(idx)}
              bot={bot}
              onUpdate={onUpdate}
            />
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-1.5 pt-1">
        {(Object.keys(ACTION_META) as FlowActionType[]).map(type => (
          <button
            key={type}
            onClick={() => addAction(type)}
            title={ACTION_META[type].desc}
            className="text-[8px] font-black uppercase tracking-wide border border-zinc-800 text-zinc-500 hover:text-white hover:border-zinc-600 rounded-lg px-2.5 py-1.5 transition-all"
          >
            + {ACTION_META[type].label}
          </button>
        ))}
      </div>
    </div>
  );
};

// Редактор прямых действий кнопки (без под-кнопок — на уровне корня)
const FlowDirectActions: React.FC<{
  actions: FlowAction[];
  onChange: (actions: FlowAction[]) => void;
  bot: BotConfig;
  onUpdate: (b: BotConfig) => void;
}> = ({ actions, onChange, bot, onUpdate }) => {
  const addAction = (type: FlowActionType) => {
    onChange([...actions, { id: mkFlowId(), type, text: '', code: '', buttons: [] }]);
  };
  const updateAction = (idx: number, a: FlowAction) => {
    const na = [...actions]; na[idx] = a;
    onChange(na);
  };
  const deleteAction = (idx: number) => {
    onChange(actions.filter((_, i) => i !== idx));
  };

  return (
    <div className="space-y-3">
      {actions.length > 0 && (
        <div className="flex items-center gap-2">
          <ArrowRight className="w-3 h-3 text-zinc-700 shrink-0" />
          <span className="text-[8px] text-zinc-700 font-bold uppercase tracking-widest">При нажатии кнопки — выполнить:</span>
        </div>
      )}
      <div className="space-y-2">
        {actions.map((action, idx) => (
          <FlowActionEditor
            key={action.id}
            action={action}
            depth={0}
            onChange={a => updateAction(idx, a)}
            onDelete={() => deleteAction(idx)}
            bot={bot}
            onUpdate={onUpdate}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {(Object.keys(ACTION_META) as FlowActionType[]).map(type => (
          <button
            key={type}
            onClick={() => addAction(type)}
            title={ACTION_META[type].desc}
            className="text-[8px] font-black uppercase tracking-wide border border-zinc-800 text-zinc-500 hover:text-white hover:border-zinc-600 rounded-lg px-2.5 py-1.5 transition-all"
          >
            + {ACTION_META[type].label}
          </button>
        ))}
      </div>
    </div>
  );
};

const ButtonFlowEditor: React.FC<{ bot: BotConfig; onUpdate: (b: BotConfig) => void }> = ({ bot, onUpdate }) => {
  const [open, setOpen] = React.useState(false);
  const [selectedBtnIdx, setSelectedBtnIdx] = React.useState<number | null>(null);
  const [tab, setTab] = React.useState<'direct' | 'nodes'>('direct');
  const isVKBot = bot.platform === 'vk';

  // Сбрасываем вкладку при смене выбранной кнопки
  React.useEffect(() => {
    setTab('direct');
  }, [selectedBtnIdx]);

  const buttons = bot.buttons || [];

  const getFlow = (i: number): FlowNode[] => buttons[i]?.flow || [];
  const getDirectActions = (i: number): FlowAction[] => buttons[i]?.directActions || [];

  const updateFlow = (btnIdx: number, flow: FlowNode[]) => {
    const nb = [...buttons];
    nb[btnIdx] = { ...nb[btnIdx], flow };
    onUpdate({ ...bot, buttons: nb });
  };

  const updateDirectActions = (btnIdx: number, directActions: FlowAction[]) => {
    const nb = [...buttons];
    nb[btnIdx] = { ...nb[btnIdx], directActions };
    onUpdate({ ...bot, buttons: nb });
  };

  const addRootNode = (btnIdx: number) => {
    updateFlow(btnIdx, [...getFlow(btnIdx), { id: mkFlowId(), label: 'Новая кнопка', actions: [] }]);
  };
  const updateNode = (btnIdx: number, idx: number, node: FlowNode) => {
    const flow = [...getFlow(btnIdx)]; flow[idx] = node;
    updateFlow(btnIdx, flow);
  };
  const deleteNode = (btnIdx: number, idx: number) => {
    updateFlow(btnIdx, getFlow(btnIdx).filter((_, i) => i !== idx));
  };

  if (buttons.length === 0) return null;

  return (
    <div className="mt-10">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between bg-[#0d0d0d] border border-zinc-800 rounded-[2rem] px-8 py-5 hover:border-zinc-700 transition-all group"
      >
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center shrink-0">
            <Zap className="w-5 h-5 text-white" />
          </div>
          <div className="text-left">
            <p className="text-white font-black text-sm">Расширенная логика кнопок</p>
            <p className="text-[9px] text-zinc-500 mt-0.5">
              Действия при нажатии, под-кнопки, код, уведомления{isVKBot ? ' (VK)' : ' (Telegram)'}.
            </p>
          </div>
        </div>
        <ChevronDown className={`w-5 h-5 text-zinc-500 group-hover:text-zinc-300 transition-all duration-200 ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="mt-4 bg-[#0d0d0d] border border-zinc-800 rounded-[2rem] p-6 md:p-8 space-y-6 animate-in fade-in duration-200">
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 text-[10px] text-zinc-500 leading-relaxed space-y-1">
            <p>Выберите кнопку слева. Вкладка <b className="text-zinc-400">Действия</b> — что происходит сразу при нажатии (отправить текст, код, уведомление).</p>
            <p>Вкладка <b className="text-zinc-400">Под-кнопки</b> — показать пользователю вложенное меню, каждая ветка может иметь свои действия.</p>
            <p className="text-zinc-700">Вложенность не ограничена.</p>
          </div>

          <div className="flex flex-col md:flex-row gap-6" style={{ minHeight: 320 }}>
            {/* Список кнопок */}
            <div className="w-full md:w-56 shrink-0 space-y-1.5">
              <p className="text-[8px] font-black text-zinc-600 uppercase tracking-widest px-1 mb-2">Кнопки бота</p>
              {buttons.map((btn: any, i: number) => {
                const flowLen = (btn.flow || []).length;
                const directLen = (btn.directActions || []).length;
                const isSelected = selectedBtnIdx === i;
                return (
                  <button
                    key={i}
                    onClick={() => setSelectedBtnIdx(i)}
                    className={`w-full text-left px-4 py-3 rounded-2xl border transition-all flex items-start gap-3 ${
                      isSelected
                        ? 'bg-blue-500/10 border-blue-500/25 text-white'
                        : 'bg-black/30 border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200'
                    }`}
                  >
                    <MousePointerClick className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${isSelected ? 'text-blue-400' : 'text-zinc-600'}`} />
                    <div className="min-w-0">
                      <p className="text-xs font-bold truncate">{btn.text || `Кнопка ${i + 1}`}</p>
                      <p className={`text-[8px] mt-0.5 ${isSelected ? 'text-blue-400/60' : 'text-zinc-700'}`}>
                        {directLen > 0 && `${directLen} действ. `}
                        {flowLen > 0 && `${flowLen} под-кнопок`}
                        {directLen === 0 && flowLen === 0 && 'без логики'}
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Редактор */}
            <div className="flex-1 min-w-0">
              {selectedBtnIdx === null ? (
                <div className="h-full flex flex-col items-center justify-center gap-3 text-zinc-700 py-12">
                  <MousePointerClick className="w-8 h-8" />
                  <p className="text-[10px] font-black uppercase tracking-widest">Выберите кнопку</p>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center justify-between flex-wrap gap-3">
                    <p className="text-white font-black">
                      Кнопка: «{buttons[selectedBtnIdx]?.text || `Кнопка ${selectedBtnIdx + 1}`}»
                    </p>
                    {tab === 'nodes' && (
                      <button
                        onClick={() => addRootNode(selectedBtnIdx)}
                        className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 px-4 py-2.5 rounded-xl text-[10px] font-black text-white uppercase transition-all shrink-0"
                      >
                        <Plus className="w-3.5 h-3.5" /> Под-кнопка
                      </button>
                    )}
                  </div>

                  {/* Вкладки */}
                  <div className="flex bg-black border border-zinc-800 rounded-2xl p-1 gap-1">
                    <button
                      onClick={() => setTab('direct')}
                      className={`flex-1 py-2.5 rounded-xl text-[9px] font-black uppercase tracking-wide transition-all ${tab === 'direct' ? 'bg-blue-600 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}
                    >
                      Действия при нажатии
                    </button>
                    <button
                      onClick={() => setTab('nodes')}
                      className={`flex-1 py-2.5 rounded-xl text-[9px] font-black uppercase tracking-wide transition-all ${tab === 'nodes' ? 'bg-blue-600 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}
                    >
                      Под-кнопки и ветки
                    </button>
                  </div>

                  {/* Содержимое вкладки */}
                  {tab === 'direct' && (
                    <FlowDirectActions
                      actions={getDirectActions(selectedBtnIdx)}
                      onChange={a => updateDirectActions(selectedBtnIdx, a)}
                      bot={bot}
                      onUpdate={onUpdate}
                    />
                  )}

                  {tab === 'nodes' && (
                    getFlow(selectedBtnIdx).length === 0 ? (
                      <div className="border-2 border-dashed border-zinc-800 rounded-2xl p-12 text-center">
                        <Layers className="w-8 h-8 text-zinc-800 mx-auto mb-3" />
                        <p className="text-zinc-700 text-xs font-black uppercase">Нет под-кнопок</p>
                        <p className="text-[9px] text-zinc-800 mt-1">Нажмите «Под-кнопка» чтобы добавить ветку</p>
                      </div>
                    ) : (
                      <div className="space-y-4">
                        {getFlow(selectedBtnIdx).map((node, idx) => (
                          <FlowNodeEditor
                            key={node.id}
                            node={node}
                            depth={0}
                            onChange={n => updateNode(selectedBtnIdx, idx, n)}
                            onDelete={() => deleteNode(selectedBtnIdx, idx)}
                            bot={bot}
                            onUpdate={onUpdate}
                          />
                        ))}
                      </div>
                    )
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ══════════════════════════════════════════════════════════════════════
// STAFF TAB — Система администраторов поддержки
// ══════════════════════════════════════════════════════════════════════
const DEFAULT_STAFF_SETTINGS: StaffSettings = {
  enabled: false,
  notifyOnAssign: true,
  showStaffList: false,
  staffListButtonName: 'Список администрации',
  allowUserSwitch: true,
  assignMode: 'random',
};

function genStaffId() {
  return Math.random().toString(36).slice(2, 10);
}

const StaffTab: React.FC<{ bot: BotConfig; onUpdate: (b: BotConfig) => void; isVK: boolean }> = ({ bot, onUpdate, isVK }) => {
  const staffSettings: StaffSettings = { ...DEFAULT_STAFF_SETTINGS, ...(bot.staffSettings || {}) };
  const staffAdmins: BotStaffAdmin[] = bot.staffAdmins || [];

  // Форма добавления нового стафф-админа
  const [newAlias, setNewAlias]   = React.useState('');
  const [newName, setNewName]     = React.useState('');
  const [newTgId, setNewTgId]     = React.useState('');
  const [addError, setAddError]   = React.useState('');

  // Редактируемый ID (inline)
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [editBuf, setEditBuf]     = React.useState<Partial<BotStaffAdmin>>({});

  // Стата — развёрнутый айди
  const [expandedStat, setExpandedStat] = React.useState<string | null>(null);

  // Загрузка кнопки отдыха
  const [restLoading, setRestLoading] = React.useState<string | null>(null);

  const upd = (patch: Partial<BotConfig>) => onUpdate({ ...bot, ...patch });
  const updSettings = (patch: Partial<StaffSettings>) =>
    upd({ staffSettings: { ...staffSettings, ...patch } });
  const updAdmins = (list: BotStaffAdmin[]) => upd({ staffAdmins: list });

  const addAdmin = () => {
    setAddError('');
    const alias = newAlias.trim();
    const name  = newName.trim();
    const rawId = newTgId.trim();

    if (!alias) { setAddError('Укажите псевдоним'); return; }
    if (!name)  { setAddError('Укажите внутреннее имя'); return; }
    if (!rawId || isNaN(Number(rawId))) { setAddError(`Укажите корректный ${isVK ? 'VK ID' : 'Telegram ID'}`); return; }

    const numId = Number(rawId);
    const alreadyExists = staffAdmins.some(a => isVK ? a.vk_id === numId : a.tg_id === numId);
    if (alreadyExists) { setAddError('Этот ID уже добавлен'); return; }

    const newAdmin: BotStaffAdmin = {
      id: genStaffId(),
      alias,
      name,
      active: true,
      is_on_rest: false,
      ...(isVK ? { vk_id: numId } : { tg_id: numId }),
      stats: { ticketsAccepted: 0, ticketsClosed: 0, messagesSent: 0, avgResponseMs: 0 },
    };
    updAdmins([...staffAdmins, newAdmin]);
    setNewAlias(''); setNewName(''); setNewTgId('');
  };

  const removeAdmin = (id: string) => updAdmins(staffAdmins.filter(a => a.id !== id));

  const toggleActive = (id: string) =>
    updAdmins(staffAdmins.map(a => a.id === id ? { ...a, active: !a.active } : a));

  // Кнопка «На отдых / Вернуть» — сохраняет в БД мгновенно (не ждёт общего Save)
  const toggleRest = async (adminId: string, currentRest: boolean) => {
    setRestLoading(adminId);
    // Оптимистичное обновление локально
    updAdmins(staffAdmins.map(a => a.id === adminId ? { ...a, is_on_rest: !currentRest } : a));
    try {
      await api.toggleStaffRest(bot.id, adminId, !currentRest);
    } catch {
      // Откатываем при ошибке
      updAdmins(staffAdmins.map(a => a.id === adminId ? { ...a, is_on_rest: currentRest } : a));
    } finally {
      setRestLoading(null);
    }
  };

  const startEdit = (a: BotStaffAdmin) => { setEditingId(a.id); setEditBuf({ alias: a.alias, name: a.name, tg_id: a.tg_id, vk_id: a.vk_id }); };
  const saveEdit = (id: string) => {
    updAdmins(staffAdmins.map(a => a.id === id ? { ...a, ...editBuf } : a));
    setEditingId(null); setEditBuf({});
  };

  const fmtMs = (ms: number) => {
    if (!ms) return '—';
    if (ms < 60000) return `${Math.round(ms / 1000)}с`;
    return `${Math.round(ms / 60000)}м`;
  };

  const Toggle: React.FC<{ value: boolean; onChange: (v: boolean) => void; label: string; sub?: string }> = ({ value, onChange, label, sub }) => (
    <div className="flex items-start justify-between gap-4">
      <div>
        <p className="text-sm font-semibold text-white">{label}</p>
        {sub && <p className="text-xs text-zinc-500 mt-0.5">{sub}</p>}
      </div>
      <button onClick={() => onChange(!value)} className="shrink-0 mt-0.5">
        {value
          ? <ToggleRight className="w-7 h-7 text-blue-500" />
          : <ToggleLeft  className="w-7 h-7 text-zinc-600" />}
      </button>
    </div>
  );

  const inputCls = "w-full bg-[#0d0d0d] border border-zinc-700 rounded-xl px-3 py-2 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-blue-500 transition-colors";

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">

      {/* ── Главный тумблер ── */}
      <section className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
        <div className="flex items-center gap-3 mb-2">
          <Shield className="w-5 h-5 text-indigo-400" />
          <h2 className="text-base font-black text-white">Система администраторов</h2>
          {staffSettings.enabled && (
            <span className="ml-auto text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-400 border border-indigo-500/20">
              Активна
            </span>
          )}
        </div>
        <p className="text-xs text-zinc-500 leading-relaxed -mt-2">
          Когда функция включена — каждое новое обращение автоматически закрепляется за одним из активных администраторов.
          Если она выключена, бот работает как раньше.
        </p>

        <Toggle
          value={staffSettings.enabled}
          onChange={v => updSettings({ enabled: v })}
          label="Включить систему администраторов"
          sub="Тикеты будут распределяться между добавленными администраторами"
        />

        {staffSettings.enabled && (
          <>
            <div className="border-t border-zinc-800 pt-6 space-y-5">

              <Toggle
                value={staffSettings.notifyOnAssign}
                onChange={v => updSettings({ notifyOnAssign: v })}
                label='Уведомлять пользователя об ответственном'
                sub='Пользователь получит сообщение: "Вас принял: [псевдоним]"'
              />

              <Toggle
                value={staffSettings.allowUserSwitch}
                onChange={v => updSettings({ allowUserSwitch: v })}
                label="Кнопка «Сменить админа»"
                sub="Пользователь может попросить другого администратора (случайный выбор)"
              />

              <Toggle
                value={staffSettings.showStaffList}
                onChange={v => updSettings({ showStaffList: v })}
                label="Показывать список администрации"
                sub="Добавит кнопку в меню пользователя для выбора конкретного администратора"
              />

              {staffSettings.showStaffList && (
                <div className="pl-4 border-l-2 border-indigo-500/30 space-y-2">
                  <label className="text-xs font-semibold text-zinc-400">Название кнопки</label>
                  <input
                    className={inputCls}
                    value={staffSettings.staffListButtonName}
                    onChange={e => updSettings({ staffListButtonName: e.target.value })}
                    placeholder="Список администрации"
                  />
                </div>
              )}

              <div className="space-y-2">
                <label className="text-xs font-semibold text-zinc-400 flex items-center gap-1.5">
                  <ArrowLeftRight className="w-3.5 h-3.5" /> Режим назначения
                </label>
                <div className="flex gap-2">
                  {([
                    ['random', 'Случайный',   'Рандомный свободный администратор'],
                    ['least',  'По нагрузке', 'Первым в списке — с наименьшим числом тикетов'],
                  ] as const).map(([val, label, hint]) => (
                    <button
                      key={val}
                      onClick={() => updSettings({ assignMode: val })}
                      className={`flex-1 py-2.5 px-3 rounded-xl border text-xs font-bold transition-all ${
                        staffSettings.assignMode === val
                          ? 'border-indigo-500 bg-indigo-500/10 text-indigo-300'
                          : 'border-zinc-700 text-zinc-500 hover:border-zinc-600'
                      }`}
                    >
                      <div>{label}</div>
                      <div className="text-[10px] font-normal opacity-70 mt-0.5">{hint}</div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </>
        )}
      </section>

      {/* ── Список администраторов ── */}
      <section className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-5">
        <div className="flex items-center gap-3">
          <Users className="w-5 h-5 text-indigo-400" />
          <h2 className="text-base font-black text-white">Администраторы</h2>
          <span className="ml-auto text-xs font-bold text-zinc-500">{staffAdmins.length} чел.</span>
        </div>

        {!staffSettings.enabled && (
          <div className="flex items-center gap-2 text-xs text-amber-400/80 bg-amber-500/5 border border-amber-500/10 rounded-xl px-4 py-3">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
            Включите систему администраторов выше, чтобы они начали получать тикеты
          </div>
        )}

        {/* Форма добавления */}
        <div className="bg-[#0d0d0d] border border-zinc-800 rounded-2xl p-5 space-y-3">
          <p className="text-xs font-black uppercase tracking-widest text-zinc-500 flex items-center gap-1.5">
            <UserPlus className="w-3.5 h-3.5" /> Добавить администратора
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <input
              className={inputCls}
              placeholder="Имя в панели (Иван)"
              value={newName}
              onChange={e => setNewName(e.target.value)}
            />
            <input
              className={inputCls}
              placeholder="Псевдоним для юзеров (Иван П.)"
              value={newAlias}
              onChange={e => setNewAlias(e.target.value)}
            />
            <input
              className={inputCls}
              placeholder={isVK ? 'VK ID (123456)' : 'Telegram ID (123456)'}
              value={newTgId}
              onChange={e => setNewTgId(e.target.value.replace(/\D/g, ''))}
            />
          </div>
          {addError && <p className="text-xs text-red-400">{addError}</p>}
          <button
            onClick={addAdmin}
            className="w-full py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-black transition-colors flex items-center justify-center gap-2"
          >
            <Plus className="w-3.5 h-3.5" /> Добавить
          </button>
        </div>

        {/* Список */}
        {staffAdmins.length === 0 ? (
          <div className="text-center py-10 text-zinc-600 text-sm">
            Нет администраторов. Добавьте первого выше.
          </div>
        ) : (
          <div className="space-y-3">
            {staffAdmins.map(admin => (
              <div key={admin.id} className={`border rounded-2xl transition-all ${
                admin.is_on_rest
                  ? 'border-yellow-500/30 bg-[#0d0d0d] opacity-75'
                  : admin.active
                    ? 'border-zinc-700 bg-[#0d0d0d]'
                    : 'border-zinc-800 bg-[#0a0a0a] opacity-60'
              }`}>

                {/* Основная строка */}
                <div className="flex items-center gap-3 p-4">
                  {/* Аватар-заглушка */}
                  <div className={`w-9 h-9 rounded-xl flex items-center justify-center font-black text-sm shrink-0 ${
                    admin.is_on_rest
                      ? 'bg-yellow-500/15 text-yellow-400'
                      : admin.active
                        ? 'bg-indigo-500/20 text-indigo-400'
                        : 'bg-zinc-800 text-zinc-600'
                  }`}>
                    {admin.alias.charAt(0).toUpperCase()}
                  </div>

                  {editingId === admin.id ? (
                    /* ── Режим редактирования ── */
                    <div className="flex-1 grid grid-cols-1 sm:grid-cols-3 gap-2">
                      <input className={inputCls} value={editBuf.name || ''} onChange={e => setEditBuf(b => ({ ...b, name: e.target.value }))} placeholder="Имя в панели" />
                      <input className={inputCls} value={editBuf.alias || ''} onChange={e => setEditBuf(b => ({ ...b, alias: e.target.value }))} placeholder="Псевдоним" />
                      <input className={inputCls}
                        value={String(isVK ? (editBuf.vk_id ?? '') : (editBuf.tg_id ?? ''))}
                        onChange={e => {
                          const n = Number(e.target.value);
                          setEditBuf(b => isVK ? { ...b, vk_id: n } : { ...b, tg_id: n });
                        }}
                        placeholder={isVK ? 'VK ID' : 'Telegram ID'}
                      />
                    </div>
                  ) : (
                    /* ── Отображение ── */
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-bold text-white truncate">{admin.name}</span>
                        <span className="text-xs text-zinc-500">·</span>
                        <span className="text-xs text-indigo-400 truncate">@{admin.alias}</span>
                        {admin.is_on_rest && (
                          <span className="text-[10px] font-black uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-yellow-500/15 text-yellow-400 border border-yellow-500/20">
                            🌙 Отдыхает
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] text-zinc-600 mt-0.5">
                        {isVK ? `VK: ${admin.vk_id}` : `TG: ${admin.tg_id}`}
                      </div>
                    </div>
                  )}

                  {/* Кнопки действий */}
                  <div className="flex items-center gap-1 shrink-0">
                    {editingId === admin.id ? (
                      <>
                        <button onClick={() => saveEdit(admin.id)} className="p-1.5 rounded-lg bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors"><Check className="w-3.5 h-3.5" /></button>
                        <button onClick={() => setEditingId(null)} className="p-1.5 rounded-lg bg-zinc-800 text-zinc-400 hover:bg-zinc-700 transition-colors"><X className="w-3.5 h-3.5" /></button>
                      </>
                    ) : (
                      <>
                        <button
                          onClick={() => setExpandedStat(expandedStat === admin.id ? null : admin.id)}
                          className="p-1.5 rounded-lg bg-zinc-800 text-zinc-400 hover:text-indigo-400 transition-colors"
                          title="Статистика"
                        >
                          <TrendingUp className="w-3.5 h-3.5" />
                        </button>
                        <button onClick={() => startEdit(admin)} className="p-1.5 rounded-lg bg-zinc-800 text-zinc-400 hover:text-blue-400 transition-colors" title="Редактировать">
                          <Settings className="w-3.5 h-3.5" />
                        </button>
                        {/* Кнопка «На отдых / Вернуть» */}
                        <button
                          onClick={() => toggleRest(admin.id, !!admin.is_on_rest)}
                          disabled={restLoading === admin.id}
                          className={`p-1.5 rounded-lg transition-colors text-sm ${
                            admin.is_on_rest
                              ? 'bg-yellow-500/20 text-yellow-400 hover:bg-yellow-500/30'
                              : 'bg-zinc-800 text-zinc-500 hover:bg-yellow-500/10 hover:text-yellow-400'
                          } ${restLoading === admin.id ? 'opacity-50 cursor-not-allowed' : ''}`}
                          title={admin.is_on_rest ? 'Вернуть из отдыха' : 'Отправить на отдых'}
                        >
                          {restLoading === admin.id ? '…' : '🌙'}
                        </button>
                        <button
                          onClick={() => toggleActive(admin.id)}
                          className={`p-1.5 rounded-lg transition-colors ${admin.active ? 'bg-green-500/10 text-green-400 hover:bg-red-500/10 hover:text-red-400' : 'bg-zinc-800 text-zinc-600 hover:bg-green-500/10 hover:text-green-400'}`}
                          title={admin.active ? 'Деактивировать' : 'Активировать'}
                        >
                          {admin.active ? <Check className="w-3.5 h-3.5" /> : <X className="w-3.5 h-3.5" />}
                        </button>
                        <button onClick={() => removeAdmin(admin.id)} className="p-1.5 rounded-lg bg-zinc-800 text-zinc-500 hover:bg-red-500/10 hover:text-red-400 transition-colors" title="Удалить">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {/* Блок статистики (раскрывается) */}
                {expandedStat === admin.id && admin.stats && (
                  <div className="border-t border-zinc-800 px-4 pb-4 pt-3 grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {/* Бейдж «На отдыхе» */}
                    {admin.is_on_rest && (
                      <div className="col-span-full flex items-center gap-2 bg-yellow-500/10 border border-yellow-500/20 rounded-xl px-4 py-2">
                        <span className="text-base">🌙</span>
                        <span className="text-xs font-semibold text-yellow-400">Администратор на отдыхе — новые тикеты не назначаются</span>
                      </div>
                    )}
                    {[
                      { icon: Ticket,       label: 'Принято',        value: admin.stats.ticketsAccepted },
                      { icon: Check,        label: 'Закрыто',        value: admin.stats.ticketsClosed   },
                      { icon: MessageSquare, label: 'Сообщений',     value: admin.stats.messagesSent    },
                      { icon: Clock,        label: 'Сред. ответ',    value: fmtMs(admin.stats.avgResponseMs) },
                    ].map(({ icon: Icon, label, value }) => (
                      <div key={label} className="bg-[#111] border border-zinc-800 rounded-xl px-3 py-2.5 text-center">
                        <Icon className="w-3.5 h-3.5 text-indigo-400 mx-auto mb-1" />
                        <div className="text-sm font-black text-white">{value}</div>
                        <div className="text-[10px] text-zinc-600 mt-0.5">{label}</div>
                      </div>
                    ))}
                    <p className="col-span-full text-[10px] text-zinc-600 text-center">
                      Статистика обновляется в реальном времени через бота. Команда: <code className="text-zinc-500">/stat {isVK ? admin.vk_id : admin.tg_id}</code>
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ── Справка по командам ── */}
      {staffSettings.enabled && (
        <section className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-4">
          <div className="flex items-center gap-3 mb-1">
            <Award className="w-5 h-5 text-indigo-400" />
            <h2 className="text-base font-black text-white">Команды для администраторов</h2>
          </div>
          <div className="space-y-2">
            {[
              ['/give <id или псевдоним>', 'Передать текущий тикет другому администратору (в топике/реплае)'],
              ['/stat <id или псевдоним>', 'Посмотреть статистику конкретного администратора'],
              ['/stat', 'Посмотреть свою статистику (если пишет сам администратор)'],
              [isVK ? '«Сменить админа»' : '«Сменить админа»', 'Кнопка у пользователя — переназначает случайного активного администратора'],
            ].map(([cmd, desc]) => (
              <div key={cmd} className="flex items-start gap-3 bg-[#0d0d0d] rounded-xl px-4 py-3">
                <code className="text-xs font-mono text-indigo-300 shrink-0 mt-0.5">{cmd}</code>
                <span className="text-xs text-zinc-500">{desc}</span>
              </div>
            ))}
          </div>
        </section>
      )}

    </div>
  );
};

export default BotEditor;
