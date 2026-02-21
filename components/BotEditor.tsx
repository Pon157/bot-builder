import React, { useState, useEffect } from 'react';
import { BotConfig, BotStatus } from '../types';
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
  MoveVertical, Check, ChevronUp, Copy, Eye, EyeOff
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
    commonMessageHeader: "📩 <b>СООБЩЕНИЕ:</b>"
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
        if (res === true) onUpdate({ ...bot, status: BotStatus.RUNNING });
        else alert(`Ошибка запуска: ${res}`);
      }
    } finally { setIsProcessing(false); }
  };

  // ── adminIds helper ──
  const adminIdsStr = (bot.adminIds || []).join(', ');
  const updateAdminIds = (str: string) => {
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
        <div className="fixed bottom-10 left-1/2 -translate-x-1/2 z-[100] bg-blue-600 text-white px-8 py-4 rounded-2xl shadow-2xl flex items-center gap-4 animate-bounce">
          <AlertCircle className="w-5 h-5" />
          <span className="text-xs font-black uppercase tracking-widest">Несохранённые изменения!</span>
          <button onClick={syncState} disabled={isProcessing} className="bg-white text-blue-600 px-4 py-1.5 rounded-xl font-black text-[10px] uppercase">
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
<div className="flex gap-2 border-b border-zinc-800 overflow-x-auto no-scrollbar">
  {tabs.map(t => (
      <button 
        key={t.id} 
        onClick={() => setActiveTab(t.id as any)}
        className={`px-6 py-4 text-[10px] font-black uppercase tracking-widest border-b-2 transition-all flex items-center gap-2 whitespace-nowrap ${
          activeTab === t.id ? 'border-blue-500 text-blue-500' : 'border-transparent text-zinc-500'
        }`}
      >
        <t.icon className="w-3.5 h-3.5" />
        {t.label}
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
                    value={adminIdsStr}
                    onChange={e => updateAdminIds(e.target.value)} />
                  <p className="text-[8px] text-zinc-600 mt-1.5 ml-2 uppercase font-bold tracking-wider">
                    {isPoster || isRandomizer ? 'Только эти пользователи могут управлять ботом' : 'Могут делать /broadcast прямо в боте'}
                  </p>
                </label>

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
                </h2>
                <div className="space-y-4">
                  {[
                    { key: 'firstMessageHeader',  label: 'Заголовок первого обращения', ph: '🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>' },
                    { key: 'ticketMessageHeader',  label: 'Заголовок заявки (кнопки)',  ph: '🆘 <b>ЗАЯВКА [{btn}]:</b>'  },
                    { key: 'commonMessageHeader',  label: 'Обычное сообщение',          ph: '📩 <b>СООБЩЕНИЕ:</b>'        },
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

                  {/* ── Инлайн URL-кнопки к ответу кнопки ── */}
                  <div className="border-t border-zinc-800 pt-4">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-[9px] font-black text-zinc-500 uppercase flex items-center gap-1.5">
                        <ExternalLink className="w-3 h-3 text-indigo-400" />
                        {isVK ? 'URL-кнопки к ответу (OpenLink)' : 'Инлайн URL-кнопки к ответу'}
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

                    {isVK && (
                      <p className="text-[8px] text-sky-400/60 mb-2 bg-sky-500/5 border border-sky-500/10 rounded-xl p-2 leading-relaxed">
                        💡 В VK отправляются как инлайн OpenLink-кнопки под сообщением ответа.
                      </p>
                    )}

                    <p className="text-[8px] text-zinc-600 mb-2">
                      {isVK
                        ? 'URL-кнопки появятся под ответом бота в VK:'
                        : 'Инлайн-кнопки появятся под ответом бота (только TG):'}
                    </p>

                    {(btn.inline || []).map((ib: any, ii: number) => (
                      <div key={ii} className="flex gap-2 mb-2">
                        <input
                          placeholder="Текст кнопки"
                          className={`flex-1 bg-black border border-zinc-800 p-3 rounded-xl text-xs text-white outline-none transition-all ${isVK ? 'focus:border-sky-500' : 'focus:border-indigo-500'}`}
                          value={ib.text}
                          onChange={e => {
                            const nb = [...bot.buttons];
                            nb[i].inline[ii] = { ...nb[i].inline[ii], text: e.target.value };
                            handleLocalUpdate({ ...bot, buttons: nb });
                          }}
                        />
                        <input
                          placeholder="https://..."
                          className={`flex-1 bg-black border border-zinc-800 p-3 rounded-xl text-xs text-white outline-none transition-all ${isVK ? 'focus:border-sky-500' : 'focus:border-indigo-500'}`}
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

                    {/* Мини-превью инлайн-кнопок */}
                    {(btn.inline || []).filter((b: any) => b.text).length > 0 && (
                      <div className="mt-2 bg-black/40 border border-zinc-800/60 rounded-xl p-3 space-y-1">
                        <p className="text-[7px] text-zinc-700 uppercase font-bold mb-2 flex items-center gap-1">
                          <Smartphone className="w-2 h-2" />Превью
                        </p>
                        <div className="bg-zinc-900/70 rounded-xl p-2.5 max-w-[80%] mb-1.5">
                          <p className="text-[9px] text-zinc-400">{btn.response ? btn.response.slice(0, 60) + (btn.response.length > 60 ? '…' : '') : 'Ответ кнопки...'}</p>
                        </div>
                        {(btn.inline || []).filter((b: any) => b.text).map((b: any, pi: number) => (
                          <div key={pi} className={`rounded-lg py-1.5 px-3 text-center flex items-center justify-center gap-1 ${
                            isVK ? 'bg-sky-500/10 border border-sky-500/20' : 'bg-indigo-500/10 border border-indigo-500/20'
                          }`}>
                            <ExternalLink className={`w-2 h-2 shrink-0 ${isVK ? 'text-sky-400/60' : 'text-indigo-400/60'}`} />
                            <span className={`text-[9px] font-semibold ${isVK ? 'text-sky-300' : 'text-indigo-300'}`}>{b.text}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  {/* Конец блока Инлайн URL-кнопок */}

                </div>
              </div>
            ))}
          </div>
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
      {activeTab === 'ai' && isSupportBot && (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
          {/* Баланс токенов */}
          <div className="bg-[#111] border border-zinc-800 p-6 rounded-[2.5rem] flex flex-col md:flex-row items-center gap-6">
            <div className="flex-1">
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
                <p className="text-xs text-zinc-500 mt-2">Загрузка баланса...</p>
              )}
            </div>
            <div className="w-full md:w-auto space-y-2">
              <p className="text-[9px] text-zinc-500 font-bold uppercase ml-1">Активировать ключ AI</p>
              <div className="flex gap-2">
                <input
                  className="flex-1 bg-black border border-zinc-800 rounded-xl p-3 text-xs text-white font-mono outline-none focus:border-amber-500 transition-all min-w-[180px]"
                  placeholder="AITOK-XXXXXX-NNN"
                  value={aiKeyInput}
                  onChange={e => setAiKeyInput(e.target.value)}
                />
                <button
                  onClick={async () => {
                    if (!aiKeyInput.trim()) return;
                    setAiKeyStatus('⏳ Активация...');
                    try {
                      const r = await fetch('/api/ai/activate-tokens', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ key: aiKeyInput.trim().toUpperCase(), botId: bot.id })
                      });
                      const res = await r.json();
                      if (res.status === 'ok') {
                        setAiKeyStatus(`✅ +${res.tokens_added?.toLocaleString()} токенов!`);
                        setAiKeyInput('');
                        fetch(`/api/ai/balance/${bot.id}`).then(r => r.json()).then(setAiBalance);
                      } else {
                        setAiKeyStatus(`❌ ${res.message}`);
                      }
                    } catch { setAiKeyStatus('❌ Ошибка сети'); }
                  }}
                  className="px-4 py-3 bg-amber-500/10 text-amber-500 border border-amber-500/20 rounded-xl text-xs font-black hover:bg-amber-500/20 transition-all"
                >
                  Активировать
                </button>
              </div>
              {aiKeyStatus && <p className="text-[10px] text-zinc-400 ml-1">{aiKeyStatus}</p>}
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

interface MiniApp {
  id: string; title: string; theme: MiniTheme; components: MiniComp[]; 
  formWebhook?: string; 
  submitTarget?: 'bot' | 'webhook'; // ДОБАВИТЬ ЭТО
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
  { label: '🌑 Ночь',  theme: { bg: '#0a0a0f', surface: '#13131c', primary: '#6366f1', textPrimary: '#f8fafc', textSecondary: '#94a3b8', gradient: 'radial-gradient(ellipse at 30% 0%, #312e8155 0%, transparent 60%)' } },
  { label: '❄️ Лёд',   theme: { bg: '#f0f9ff', surface: '#ffffff',  primary: '#0ea5e9', textPrimary: '#0f172a', textSecondary: '#64748b', gradient: '' } },
  { label: '🔥 Закат', theme: { bg: '#1c0d2b', surface: '#251238',  primary: '#f97316', textPrimary: '#fff7ed', textSecondary: '#d1a27c', gradient: 'radial-gradient(ellipse at 80% 0%, #7c2d8840 0%, transparent 60%)' } },
  { label: '🌿 Лес',   theme: { bg: '#0d1f12', surface: '#142419',  primary: '#22c55e', textPrimary: '#f0fdf4', textSecondary: '#86efac', gradient: '' } },
  { label: '🌸 Роза',  theme: { bg: '#fff1f2', surface: '#ffffff',  primary: '#f43f5e', textPrimary: '#1c1917', textSecondary: '#78716c', gradient: '' } },
];

const DEFAULT_MINI_THEME: MiniTheme = {
  bg: '#0a0a0f', surface: '#13131c', primary: '#6366f1',
  textPrimary: '#f8fafc', textSecondary: '#94a3b8',
  radius: 12, font: "'Manrope', sans-serif",
  gradient: "radial-gradient(ellipse at 30% 0%, #312e8155 0%, transparent 60%)",
};

const mkMiniId = () => Math.random().toString(36).slice(2, 9);

const newMiniComp = (type: MiniCompType): MiniComp => {
  const id = mkMiniId();
  switch (type) {
    case 'heading':    return { id, type, props: { text: 'Заголовок', level: 'h2', fontSize: 28, fontWeight: '800', color: '', align: 'left' } };
    case 'text':       return { id, type, props: { text: 'Опишите здесь что угодно — информацию, оффер, инструкции.', fontSize: 15, color: '', align: 'left' } };
    case 'button':     return { id, type, props: { text: 'Нажать', bgColor: '', textColor: '#fff', action: 'none' } };
    case 'linkButton': return { id, type, props: { text: 'Перейти →', bgColor: '', textColor: '#fff', url: 'https://', action: 'link' } };
    case 'input':      return { id, type, props: { label: 'Ваше имя', placeholder: 'Имя...', inputType: 'text', name: 'name', required: true } };
    case 'textarea':   return { id, type, props: { label: 'Сообщение', placeholder: 'Текст...', name: 'message', required: false } };
    case 'image':      return { id, type, props: { src: 'https://picsum.photos/seed/app/800/300', alt: '', width: '100%' } };
    case 'divider':    return { id, type, props: { dividerColor: '' } };
    case 'spacer':     return { id, type, props: { height: 24 } };
    default:           return { id, type, props: {} };
  }
};

// ── Превью компонента ─────────────────────────────────────────────────────────
const MiniPreviewComp: React.FC<{ comp: MiniComp; theme: MiniTheme; selected?: boolean; onClick?: () => void }> = ({ comp, theme, selected, onClick }) => {
  const { type, props: p } = comp;
  const wrap = (el: React.ReactNode) => (
    <div
      onClick={onClick}
      style={{
        outline: selected ? `2px solid ${theme.primary}` : 'none',
        outlineOffset: 2, borderRadius: 4, cursor: onClick ? 'pointer' : 'default',
      }}
    >{el}</div>
  );

  if (type === 'heading') {
    const Tag = (p.level || 'h2') as 'h1' | 'h2' | 'h3';
    return wrap(<Tag style={{ fontSize: p.fontSize || 28, fontWeight: p.fontWeight || '800', color: p.color || theme.textPrimary, textAlign: p.align || 'left', margin: 0, lineHeight: 1.2, fontFamily: theme.font }}>{p.text || 'Заголовок'}</Tag>);
  }
  if (type === 'text') {
    return wrap(<p style={{ fontSize: p.fontSize || 15, color: p.color || theme.textSecondary, textAlign: p.align || 'left', margin: 0, lineHeight: 1.65, fontFamily: theme.font }}>{p.text || 'Текст'}</p>);
  }
  if (type === 'button' || type === 'linkButton') {
    return wrap(<div style={{ textAlign: 'center' }}><span style={{ display: 'inline-block', background: p.bgColor || theme.primary, color: p.textColor || '#fff', borderRadius: theme.radius, fontWeight: '700', fontSize: 14, padding: '10px 24px', fontFamily: theme.font }}>{p.text || 'Кнопка'}</span></div>);
  }
  if (type === 'input') {
    return wrap(<div>
      {p.label && <span style={{ display: 'block', fontSize: 11, fontWeight: '700', color: theme.textSecondary, marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.08em', fontFamily: theme.font }}>{p.label}{p.required ? ' *' : ''}</span>}
      <div style={{ background: theme.surface, border: `1px solid ${theme.textSecondary}30`, borderRadius: theme.radius * 0.6, padding: '9px 13px', fontSize: 13, color: theme.textSecondary + '80', fontFamily: theme.font }}>{p.placeholder || 'Введите...'}</div>
    </div>);
  }
  if (type === 'textarea') {
    return wrap(<div>
      {p.label && <span style={{ display: 'block', fontSize: 11, fontWeight: '700', color: theme.textSecondary, marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.08em', fontFamily: theme.font }}>{p.label}{p.required ? ' *' : ''}</span>}
      <div style={{ background: theme.surface, border: `1px solid ${theme.textSecondary}30`, borderRadius: theme.radius * 0.6, padding: '9px 13px', fontSize: 13, color: theme.textSecondary + '80', fontFamily: theme.font, minHeight: 64 }}>{p.placeholder || 'Введите...'}</div>
    </div>);
  }
  if (type === 'image') {
    return wrap(<img src={p.src} alt={p.alt || ''} style={{ width: p.width || '100%', borderRadius: theme.radius, display: 'block', maxWidth: '100%' }} onError={e => { (e.currentTarget as HTMLImageElement).style.opacity = '0.3'; }} />);
  }
  if (type === 'divider') return wrap(<hr style={{ border: 'none', borderTop: `1px solid ${p.dividerColor || theme.textSecondary + '30'}`, margin: '2px 0' }} />);
  if (type === 'spacer') return wrap(<div style={{ height: p.height || 24 }} />);
  return wrap(<div />);
};

// ── Панель свойств (компактная) ───────────────────────────────────────────────
const MiniPropsPanel: React.FC<{ comp: MiniComp | null; theme: MiniTheme; onChange: (id: string, p: Partial<MiniCompProps>) => void }> = ({ comp, theme, onChange }) => {
  if (!comp) return (
    <div className="flex flex-col items-center justify-center py-12 gap-2 opacity-20">
      <Layers className="w-8 h-8 text-zinc-500" />
      <p className="text-[9px] text-zinc-500 font-black uppercase tracking-widest">Выберите блок</p>
    </div>
  );
  const p = comp.props;
  const up = (patch: Partial<MiniCompProps>) => onChange(comp.id, patch);
  const inp = (className = '') => `w-full bg-black border border-zinc-800 focus:border-indigo-500 text-white text-xs p-2.5 rounded-xl outline-none transition-all ${className}`;

  return (
    <div className="p-4 space-y-3">
      <p className="text-[8px] font-black text-indigo-400 uppercase tracking-[0.2em] mb-3">{comp.type}</p>

      {(comp.type === 'heading' || comp.type === 'text') && (<>
        <label className="block">
          <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Текст</span>
          <textarea value={p.text || ''} rows={3} onChange={e => up({ text: e.target.value })} className={inp('resize-none')} />
        </label>
        {comp.type === 'heading' && (
          <label className="block">
            <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Уровень</span>
            <select value={p.level || 'h2'} onChange={e => up({ level: e.target.value as any })} className={inp('cursor-pointer')}>
              <option value="h1">H1 — Главный</option><option value="h2">H2 — Средний</option><option value="h3">H3 — Малый</option>
            </select>
          </label>
        )}
        <label className="block">
          <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Размер (px)</span>
          <input type="number" min={10} max={80} value={p.fontSize || 16} onChange={e => up({ fontSize: Number(e.target.value) })} className={inp()} />
        </label>
        <label className="block">
          <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Выравнивание</span>
          <div className="flex gap-1">
            {(['left','center','right'] as const).map(a => (
              <button key={a} onClick={() => up({ align: a })}
                className={`flex-1 py-2 rounded-lg border text-[9px] font-black uppercase transition-all ${p.align===a ? 'bg-indigo-500/20 border-indigo-500/40 text-indigo-400' : 'border-zinc-800 text-zinc-600 hover:border-zinc-700'}`}>{a[0].toUpperCase()}{a.slice(1)}</button>
            ))}
          </div>
        </label>
        <label className="block">
          <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Цвет текста</span>
          <div className="flex gap-2">
            <input type="color" value={p.color || theme.textPrimary} onChange={e => up({ color: e.target.value })} className="w-9 h-9 rounded-lg border border-zinc-800 bg-black cursor-pointer p-0.5" />
            <input value={p.color || ''} placeholder="авто" onChange={e => up({ color: e.target.value })} className={inp()} />
          </div>
        </label>
      </>)}

      {(comp.type === 'button' || comp.type === 'linkButton') && (<>
        <label className="block">
          <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Текст</span>
          <input value={p.text || ''} onChange={e => up({ text: e.target.value })} className={inp()} />
        </label>
        <label className="block">
          <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Цвет фона</span>
          <div className="flex gap-2">
            <input type="color" value={p.bgColor || theme.primary} onChange={e => up({ bgColor: e.target.value })} className="w-9 h-9 rounded-lg border border-zinc-800 bg-black cursor-pointer p-0.5" />
            <input value={p.bgColor || ''} placeholder="авто (акцент)" onChange={e => up({ bgColor: e.target.value })} className={inp()} />
          </div>
        </label>
        {comp.type === 'linkButton' && (
          <label className="block">
            <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">URL</span>
            <input type="url" value={p.url || ''} placeholder="https://" onChange={e => up({ url: e.target.value })} className={inp()} />
          </label>
        )}
        {comp.type === 'button' && (
          <label className="block">
            <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Действие</span>
            <select value={p.action || 'none'} onChange={e => up({ action: e.target.value as any })} className={inp('cursor-pointer')}>
              <option value="none">Нет</option><option value="submit">Отправить форму</option><option value="link">Открыть ссылку</option>
            </select>
          </label>
        )}
        {comp.type === 'button' && p.action === 'link' && (
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
          <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">name (для формы)</span>
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
          <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Высота (px)</span>
          <input type="number" min={4} max={300} value={p.height || 24} onChange={e => up({ height: Number(e.target.value) })} className={inp()} />
        </label>
      )}
    </div>
  );
};

// ── Главный компонент вкладки ─────────────────────────────────────────────────
const MiniAppsTab: React.FC<{ bot: BotConfig; onUpdate: (b: BotConfig) => void; isVK: boolean }> = ({ bot, onUpdate, isVK }) => {
  const [apps, setApps] = React.useState<MiniApp[]>(() => {
    try { return JSON.parse(localStorage.getItem(`miniapps_${bot.id}`) || '[]'); } catch { return []; }
  });
  const [editingId, setEditingId]   = React.useState<string | null>(null);
  const [selectedComp, setSelComp]  = React.useState<string | null>(null);
  const [rightTab, setRightTab]     = React.useState<'props' | 'theme'>('props');
  const [saving, setSaving]         = React.useState(false);
  const [saved, setSaved]           = React.useState(false);
  const [copiedId, setCopiedId]     = React.useState<string | null>(null);
  const [previewMode, setPreviewMode] = React.useState(false);

  const editing = apps.find(a => a.id === editingId) || null;
  const selComp = editing?.components.find(c => c.id === selectedComp) || null;

  const persist = (next: MiniApp[]) => {
    setApps(next);
    localStorage.setItem(`miniapps_${bot.id}`, JSON.stringify(next));
  };

  const saveToServer = async (app: MiniApp) => {
    setSaving(true);
    try {
      // Используем apiService, чтобы URL формировался правильно
      const res = await api.saveMiniApp({ ...app, owner_id: bot.owner_id });
      
      if (!res) throw new Error("Сервер вернул ошибку");
      
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) { 
      console.error("Ошибка при сохранении в БД:", err);
      alert("Не удалось сохранить в базу. Проверьте консоль.");
    } finally { 
      setSaving(false); 
    }
  };

  const createApp = () => {
    const app: MiniApp = {
      id: mkMiniId(),
      title: 'Новое приложение',
      theme: { ...DEFAULT_MINI_THEME },
      components: [newMiniComp('heading'), newMiniComp('text'), newMiniComp('button')],
      formWebhook: '',
    };
    const next = [...apps, app];
    persist(next);
    setEditingId(app.id);
    setSelComp(null);
    setPreviewMode(false);
  };

  const deleteApp = (id: string) => {
    if (!window.confirm('Удалить это мини-приложение?')) return;
    const next = apps.filter(a => a.id !== id);
    persist(next);
    if (editingId === id) setEditingId(null);
  };

  const updateApp = (patch: Partial<MiniApp>) => {
    if (!editingId) return;
    const next = apps.map(a => a.id === editingId ? { ...a, ...patch } : a);
    persist(next);
  };

  const addComp = (type: MiniCompType) => {
    if (!editing) return;
    const c = newMiniComp(type);
    updateApp({ components: [...editing.components, c] });
    setSelComp(c.id);
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
    const url = `${window.location.origin}/app/${id}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    });
  };

  const theme = editing?.theme || DEFAULT_MINI_THEME;

// ── Главный компонент вкладки ─────────────────────────────────────────────────
const MiniAppsTab: React.FC<{ bot: BotConfig; onUpdate: (b: BotConfig) => void; isVK: boolean }> = ({ bot, onUpdate, isVK }) => {
  const [apps, setApps] = React.useState<MiniApp[]>(() => {
    try { return JSON.parse(localStorage.getItem(`miniapps_${bot.id}`) || '[]'); } catch { return []; }
  });
  const [editingId, setEditingId]   = React.useState<string | null>(null);
  const [selectedComp, setSelComp]  = React.useState<string | null>(null);
  const [rightTab, setRightTab]     = React.useState<'props' | 'theme'>('props');
  const [saving, setSaving]         = React.useState(false);
  const [saved, setSaved]           = React.useState(false);
  const [copiedId, setCopiedId]     = React.useState<string | null>(null);
  const [previewMode, setPreviewMode] = React.useState(false);

  const editing = apps.find(a => a.id === editingId) || null;
  const selComp = editing?.components.find(c => c.id === selectedComp) || null;

  const persist = (next: MiniApp[]) => {
    setApps(next);
    localStorage.setItem(`miniapps_${bot.id}`, JSON.stringify(next));
  };

  const saveToServer = async (app: MiniApp) => {
    setSaving(true);
    try {
      // Используем apiService, чтобы URL формировался правильно
      const res = await api.saveMiniApp({ ...app, owner_id: bot.owner_id });
      
      if (!res) throw new Error("Сервер вернул ошибку");
      
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) { 
      console.error("Ошибка при сохранении в БД:", err);
      alert("Не удалось сохранить в базу. Проверьте консоль.");
    } finally { 
      setSaving(false); 
    }
  };

  const createApp = () => {
    const app: MiniApp = {
      id: mkMiniId(),
      title: 'Новое приложение',
      theme: { ...DEFAULT_MINI_THEME },
      components: [newMiniComp('heading'), newMiniComp('text'), newMiniComp('button')],
      formWebhook: '',
    };
    const next = [...apps, app];
    persist(next);
    setEditingId(app.id);
    setSelComp(null);
    setPreviewMode(false);
  };

  const deleteApp = (id: string) => {
    if (!window.confirm('Удалить это мини-приложение?')) return;
    const next = apps.filter(a => a.id !== id);
    persist(next);
    if (editingId === id) setEditingId(null);
  };

  const updateApp = (patch: Partial<MiniApp>) => {
    if (!editingId) return;
    const next = apps.map(a => a.id === editingId ? { ...a, ...patch } : a);
    persist(next);
  };

  const addComp = (type: MiniCompType) => {
    if (!editing) return;
    const c = newMiniComp(type);
    updateApp({ components: [...editing.components, c] });
    setSelComp(c.id);
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
    const url = `${window.location.origin}/app/${id}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    });
  };

  const theme = editing?.theme || DEFAULT_MINI_THEME;

  // ── Рендер списка приложений ─────────────────────────────────────────
  if (!editingId) return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-black text-white uppercase">Мини-приложения</h2>
          <p className="text-[10px] text-zinc-500 mt-1 uppercase tracking-widest">Веб-страницы с формами и кнопками, доступные по ссылке</p>
        </div>
        <button onClick={createApp}
          className="bg-indigo-600 hover:bg-indigo-500 px-6 py-4 rounded-2xl text-[11px] font-black text-white uppercase flex items-center gap-2 shadow-lg shadow-indigo-600/20 transition-all">
          <Plus className="w-4 h-4" /> Создать
        </button>
      </div>

      <div className="bg-indigo-500/5 border border-indigo-500/20 rounded-2xl p-5 flex gap-4 items-start">
        <div className="w-9 h-9 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center shrink-0 mt-0.5">
          <AppWindow className="w-4 h-4 text-indigo-400" />
        </div>
        <div>
          <p className="text-xs font-black text-indigo-300 mb-1">Что такое мини-приложение?</p>
          <p className="text-[10px] text-zinc-500 leading-relaxed">
            Создайте красивую веб-страницу с кнопками, формами, текстом и изображениями. Поделитесь ссылкой с пользователями бота — они смогут открыть её прямо в браузере. Отправки форм приходят на ваш webhook.
            {isVK && ' Для VK: ссылку можно прикрепить как OpenLink-кнопку к любому ответу.'}
          </p>
        </div>
      </div>

      {apps.length === 0 ? (
        <div className="border-2 border-dashed border-zinc-800 rounded-[2.5rem] p-16 text-center">
          <AppWindow className="w-12 h-12 text-zinc-800 mx-auto mb-4" />
          <p className="text-zinc-600 font-black text-sm uppercase tracking-widest">Нет мини-приложений</p>
          <p className="text-zinc-700 text-[10px] mt-2">Нажмите «Создать» — будет готово за пару минут</p>
          <button onClick={createApp}
            className="mt-6 bg-indigo-600 hover:bg-indigo-500 px-8 py-3.5 rounded-2xl text-[11px] font-black text-white uppercase inline-flex items-center gap-2 transition-all">
            <Plus className="w-4 h-4" /> Создать первое
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {apps.map(app => (
            <div key={app.id}
              style={{ borderColor: app.theme.primary + '30', background: app.theme.bg + '20' }}
              className="border rounded-[2rem] overflow-hidden group hover:scale-[1.01] transition-all">
              <div style={{ background: app.theme.bg, minHeight: 90, position: 'relative', overflow: 'hidden' }}>
                {app.theme.gradient && <div style={{ position: 'absolute', inset: 0, background: app.theme.gradient }} />}
                <div className="relative z-10 p-5 flex items-end h-full">
                  <div>
                    <p style={{ color: app.theme.textSecondary, fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 4 }}>
                      {app.components.length} блоков
                    </p>
                    <p style={{ color: app.theme.textPrimary, fontWeight: 800, fontSize: 16, fontFamily: app.theme.font }}>
                      {app.title}
                    </p>
                  </div>
                  <div className="ml-auto">
                    <span style={{ background: app.theme.primary, color: '#fff', fontSize: 9, fontWeight: 800, padding: '4px 10px', borderRadius: app.theme.radius * 0.5, textTransform: 'uppercase' }}>
                      {app.components.filter(c => c.type === 'button' || c.type === 'linkButton').length} кнопок
                    </span>
                  </div>
                </div>
              </div>

              <div className="p-4 flex items-center gap-2 bg-zinc-900/50 border-t border-zinc-800/50">
                <button onClick={() => { setEditingId(app.id); setSelComp(null); setPreviewMode(false); }}
                  className="flex-1 text-[9px] font-black uppercase text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 py-2.5 rounded-xl transition-all flex items-center justify-center gap-1.5">
                  <Palette className="w-3 h-3" /> Редактировать
                </button>
                <button onClick={() => copyUrl(app.id)}
                  className={`flex items-center gap-1.5 text-[9px] font-black uppercase py-2.5 px-3 rounded-xl transition-all ${copiedId === app.id ? 'bg-emerald-500/20 text-emerald-400' : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white'}`}>
                  {copiedId === app.id ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                  {copiedId === app.id ? 'Скопировано' : 'Ссылка'}
                </button>
                <a href={`/app/${app.id}`} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-[9px] font-black uppercase py-2.5 px-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white transition-all">
                  <ExternalLink className="w-3 h-3" />
                </a>
                <button onClick={() => deleteApp(app.id)}
                  className="text-[9px] py-2.5 px-3 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-500 transition-all">
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  // ── Рендер редактора ───────────────────────────────────────────────
  return (
    <div className="fixed inset-0 z-[60] bg-zinc-950 flex flex-col animate-in fade-in duration-300">
      {/* Header */}
      <div className="h-16 border-b border-zinc-900 flex items-center px-4 gap-4 bg-zinc-950/50 backdrop-blur-xl">
        <button onClick={() => setEditingId(null)} className="p-2 hover:bg-zinc-900 rounded-xl text-zinc-400 transition-colors">
          <X className="w-5 h-5" />
        </button>
        <div className="h-8 w-px bg-zinc-900 mx-1" />
        <input 
          value={editing.title} 
          onChange={e => updateApp({ title: e.target.value })}
          className="bg-transparent border-none focus:ring-0 text-white font-black uppercase text-sm w-64"
          placeholder="Название приложения..."
        />
        
        <div className="ml-auto flex items-center gap-2">
          <button onClick={() => setPreviewMode(!previewMode)}
            className={`px-4 py-2 rounded-xl text-[10px] font-bold uppercase transition-all flex items-center gap-2 ${previewMode ? 'bg-indigo-500 text-white' : 'bg-zinc-900 text-zinc-400 hover:text-white'}`}>
            {previewMode ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            {previewMode ? 'Редактор' : 'Предпросмотр'}
          </button>
          <button 
            onClick={() => saveToServer(editing)}
            disabled={saving}
            className={`px-6 py-2 rounded-xl text-[10px] font-bold uppercase transition-all flex items-center gap-2 ${saved ? 'bg-emerald-500 text-white' : 'bg-indigo-600 hover:bg-indigo-500 text-white'} disabled:opacity-50`}>
            {saving ? <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : (saved ? <Check className="w-3.5 h-3.5" /> : <Save className="w-3.5 h-3.5" />)}
            {saved ? 'Сохранено' : (saving ? 'Сохранение...' : 'Сохранить в облако')}
          </button>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* Палитра компонентов */}
        {!previewMode && (
          <div className="w-64 border-r border-zinc-900 p-4 overflow-y-auto space-y-6">
            <p className="text-[10px] font-black text-zinc-600 uppercase tracking-widest">Палитра блоков</p>
            <div className="grid grid-cols-1 gap-2">
              {MINI_PALETTE.map(item => (
                <button key={item.type} onClick={() => addComp(item.type)}
                  className="w-full flex items-center gap-3 p-3 rounded-2xl bg-zinc-900/50 border border-zinc-800/50 hover:border-indigo-500/50 hover:bg-indigo-500/5 transition-all text-left group">
                  <div className="w-8 h-8 rounded-lg bg-zinc-800 flex items-center justify-center text-zinc-400 group-hover:text-indigo-400 transition-colors">
                    <item.icon className="w-4 h-4" />
                  </div>
                  <div>
                    <p className="text-[10px] font-bold text-zinc-300">{item.label}</p>
                    <p className="text-[8px] text-zinc-600">{item.desc}</p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Рабочая область (Canvas) */}
        <div className="flex-1 bg-zinc-900/30 overflow-y-auto p-12 flex justify-center">
          <div className={`w-full max-w-md transition-all duration-500 ${previewMode ? 'scale-100' : 'scale-[0.98]'}`}>
            <div 
              style={{ 
                background: theme.bg, 
                minHeight: '80vh',
                borderRadius: previewMode ? theme.radius * 2 : 32,
                boxShadow: '0 25px 50px -12px rgba(0,0,0,0.5)',
                position: 'relative',
                overflow: 'hidden'
              }}
              className="border border-zinc-800/50"
            >
              {theme.gradient && <div style={{ position: 'absolute', inset: 0, background: theme.gradient, pointerEvents: 'none' }} />}
              
              <div className="relative z-10 p-6 space-y-4">
                {editing.components.map((c) => (
                  <div key={c.id} 
                    onClick={() => !previewMode && setSelComp(c.id)}
                    className={`relative group ${!previewMode ? 'cursor-pointer' : ''}`}>
                    
                    {!previewMode && selectedComp === c.id && (
                      <div className="absolute -inset-2 border-2 border-indigo-500 rounded-xl z-20 pointer-events-none animate-in fade-in zoom-in-95 duration-200" />
                    )}

                    <div className={!previewMode && selectedComp === c.id ? 'opacity-100' : ''}>
                      <MiniCompRenderer comp={c} theme={theme} />
                    </div>

                    {!previewMode && selectedComp === c.id && (
                      <div className="absolute -right-12 top-0 flex flex-col gap-1 z-30">
                        <button onClick={(e) => { e.stopPropagation(); moveComp(c.id, -1); }} className="p-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-400 rounded-lg"><ChevronUp className="w-3 h-3" /></button>
                        <button onClick={(e) => { e.stopPropagation(); moveComp(c.id, 1); }} className="p-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-400 rounded-lg"><ChevronDown className="w-3 h-3" /></button>
                        <button onClick={(e) => { e.stopPropagation(); removeComp(c.id); }} className="p-2 bg-rose-500/10 hover:bg-rose-500/20 text-rose-500 rounded-lg"><Trash2 className="w-3 h-3" /></button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Правая панель свойств */}
        {!previewMode && (
          <div className="w-80 border-l border-zinc-900 bg-zinc-950/50 flex flex-col">
            <div className="flex border-b border-zinc-900">
              <button onClick={() => setRightTab('props')} className={`flex-1 py-4 text-[10px] font-black uppercase tracking-widest transition-all ${rightTab === 'props' ? 'text-indigo-400 border-b-2 border-indigo-500' : 'text-zinc-600 hover:text-zinc-400'}`}>Свойства</button>
              <button onClick={() => setRightTab('theme')} className={`flex-1 py-4 text-[10px] font-black uppercase tracking-widest transition-all ${rightTab === 'theme' ? 'text-indigo-400 border-b-2 border-indigo-500' : 'text-zinc-600 hover:text-zinc-400'}`}>Дизайн</button>
            </div>

            <div className="flex-1 overflow-y-auto p-5">
              {rightTab === 'props' ? (
                selComp ? (
                  <div className="space-y-6">
                    <div className="flex items-center gap-2 mb-4">
                      <div className="p-2 bg-indigo-500/10 rounded-lg text-indigo-400">
                        {React.createElement(MINI_PALETTE.find(p => p.type === selComp.type)?.icon || Square, { className: 'w-4 h-4' })}
                      </div>
                      <p className="text-xs font-black text-white uppercase">{MINI_PALETTE.find(p => p.type === selComp.type)?.label}</p>
                    </div>
                    <MiniPropEditor comp={selComp} update={(p) => updateCompProps(selComp.id, p)} />
                  </div>
                ) : (
                  <div className="h-full flex flex-col items-center justify-center text-center p-6">
                    <MousePointerClick className="w-8 h-8 text-zinc-800 mb-3" />
                    <p className="text-zinc-600 text-[10px] font-bold uppercase tracking-wider">Выберите блок на холсте,<br/>чтобы изменить его</p>
                  </div>
                )
              ) : (
                <div className="space-y-6">
                  <p className="text-[10px] font-black text-zinc-600 uppercase tracking-widest mb-4">Глобальная тема</p>
                  <MiniThemeEditor theme={theme} onChange={t => updateApp({ theme: t })} />
                  <div className="pt-6 border-t border-zinc-900">
                    <label className="block mb-4">
                      <span className="text-[9px] font-black text-zinc-500 uppercase tracking-widest block mb-2">Webhook для форм</span>
                      <input 
                        value={editing.formWebhook || ''}
                        onChange={e => updateApp({ formWebhook: e.target.value })}
                        className="w-full bg-zinc-900 border-zinc-800 rounded-xl text-xs text-white p-3 focus:border-indigo-500 transition-all"
                        placeholder="https://your-api.com/webhook"
                      />
                    </label>
                  </div>
                </div>
              )}
            </div>

            {/* Слои (Список компонентов) */}
            {rightTab === 'props' && editing.components.length > 0 && (
              <div className="border-t border-zinc-800/80 p-3 shrink-0">
                <p className="text-[9px] font-black text-zinc-600 uppercase tracking-widest mb-2 flex items-center gap-1.5">
                  <Layers className="w-3 h-3" /> Слои ({editing.components.length})
                </p>
                <div className="space-y-0.5 max-h-32 overflow-y-auto">
                  {editing.components.map((c, i) => {
                    const item = MINI_PALETTE.find(p => p.type === c.type);
                    const Icon = item?.icon || Square;
                    return (
                      <button key={c.id} onClick={() => setSelComp(c.id)}
                        className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left text-[10px] transition-all ${selectedComp === c.id ? 'bg-indigo-500/15 text-indigo-300' : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40'}`}>
                        <Icon className="w-3 h-3 shrink-0" />
                        <span className="truncate font-bold">{item?.label || c.type}</span>
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

  // ── Редактор ──────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-0 animate-in fade-in duration-300 -mx-0" style={{ minHeight: 700 }}>

      {/* Топ-бар редактора */}
      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <button onClick={() => { setEditingId(null); setSelComp(null); }}
          className="flex items-center gap-1.5 text-zinc-500 hover:text-white text-[10px] font-black uppercase tracking-widest transition-colors group">
          <ArrowRight className="w-3 h-3 rotate-180 group-hover:-translate-x-1 transition-transform" /> Все приложения
        </button>
        <div className="h-4 w-px bg-zinc-800" />
        <input
          value={editing!.title}
          onChange={e => updateApp({ title: e.target.value })}
          className="text-white font-black text-sm bg-transparent outline-none border-b border-transparent focus:border-indigo-500 transition-all flex-1 min-w-0"
          placeholder="Название"
        />
        <button onClick={() => setPreviewMode(p => !p)}
          className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-[9px] font-black uppercase tracking-wider transition-all ${previewMode ? 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30' : 'bg-zinc-800 text-zinc-400 border border-zinc-700'}`}>
          {previewMode ? <ChevronUp className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
          {previewMode ? 'Редактор' : 'Превью'}
        </button>
        <button onClick={() => saveToServer(editing!)} disabled={saving}
          className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-[9px] font-black uppercase tracking-wider transition-all shadow-lg ${saved ? 'bg-emerald-600 text-white' : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-600/20'}`}>
          {saved ? <Check className="w-3 h-3" /> : <Save className="w-3 h-3" />}
          {saved ? 'Готово!' : saving ? '...' : 'Сохранить'}
        </button>
        <button onClick={() => copyUrl(editing!.id)}
          className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-[9px] font-black uppercase tracking-wider transition-all border ${copiedId === editing!.id ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-zinc-800 text-zinc-400 border-zinc-700 hover:text-white'}`}>
          {copiedId === editing!.id ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
          {copiedId === editing!.id ? 'Скопировано!' : 'Скопировать ссылку'}
        </button>
      </div>

      <div className="flex gap-5 min-h-0" style={{ minHeight: 640 }}>

        {/* ── Левая: палитра ── */}
        {!previewMode && (
          <div className="w-36 shrink-0 space-y-1">
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
            <div className="pt-3 border-t border-zinc-800/50 mt-3">
              <p className="text-[8px] font-black text-zinc-600 uppercase tracking-[0.2em] mb-2 px-1">Webhook</p>
              <input
                value={editing!.formWebhook || ''}
                onChange={e => updateApp({ formWebhook: e.target.value })}
                placeholder="https://..."
                className="w-full bg-black border border-zinc-800 focus:border-indigo-500 text-white text-[9px] p-2 rounded-lg outline-none transition-all"
              />
              <p className="text-[7px] text-zinc-700 mt-1 leading-relaxed px-1">POST-запрос при отправке формы</p>
            </div>
          </div>
        )}

        {/* ── Центр: канвас ── */}
        <div className="flex-1 min-w-0 overflow-y-auto rounded-[1.5rem] border border-zinc-800" onClick={() => !previewMode && setSelComp(null)}>
          <div style={{ background: theme.bg, minHeight: '100%', position: 'relative' }}>
            {theme.gradient && <div style={{ position: 'absolute', inset: 0, background: theme.gradient, pointerEvents: 'none', zIndex: 0 }} />}
            <div style={{ position: 'relative', zIndex: 1, padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
              {editing!.components.length === 0 && (
                <div style={{ textAlign: 'center', padding: '40px 0', opacity: 0.3 }}>
                  <p style={{ color: theme.textSecondary, fontSize: 12, fontFamily: theme.font }}>Добавьте блоки слева</p>
                </div>
              )}
              {editing!.components.map((comp, idx) => (
                <div key={comp.id} style={{ position: 'relative' }} onClick={e => { if (!previewMode) { e.stopPropagation(); setSelComp(comp.id); }}}>
                  <MiniPreviewComp comp={comp} theme={theme} selected={!previewMode && selectedComp === comp.id} />
                  {!previewMode && selectedComp === comp.id && (
                    <div className="absolute -top-2 -right-2 flex gap-0.5 z-10">
                      <button onClick={e => { e.stopPropagation(); moveComp(comp.id, -1); }} disabled={idx === 0}
                        className="w-5 h-5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 flex items-center justify-center disabled:opacity-30 shadow text-[8px]">
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

        {/* ── Правая: свойства/тема ── */}
        {!previewMode && (
          <div className="w-52 shrink-0 bg-[#0d0d0d] border border-zinc-800 rounded-[1.5rem] overflow-hidden flex flex-col">
            <div className="flex border-b border-zinc-800">
              {[{ id: 'props', icon: Settings, label: 'Свойства' }, { id: 'theme', icon: Palette, label: 'Тема' }].map(tab => (
                <button key={tab.id} onClick={() => setRightTab(tab.id as any)}
                  className={`flex-1 flex items-center justify-center gap-1 py-3 text-[8px] font-black uppercase tracking-widest border-b-2 transition-all ${rightTab === tab.id ? 'border-indigo-500 text-indigo-400' : 'border-transparent text-zinc-600 hover:text-zinc-400'}`}>
                  <tab.icon className="w-3 h-3" /> {tab.label}
                </button>
              ))}
            </div>
            <div className="flex-1 overflow-y-auto">
              {rightTab === 'props' ? (
                <MiniPropsPanel comp={selComp} theme={theme} onChange={updateCompProps} />
              ) : (
                <div className="p-3 space-y-3">
                  <p className="text-[8px] font-black text-indigo-400 uppercase tracking-[0.2em] mb-3">Тема</p>
                  {/* Пресеты */}
                  <p className="text-[8px] font-black text-zinc-600 uppercase tracking-widest mb-1">Пресеты</p>
                  <div className="grid grid-cols-2 gap-1.5">
                    {MINI_PRESETS.map(pt => (
                      <button key={pt.label} onClick={() => updateApp({ theme: { ...theme, ...pt.theme } })}
                        style={{ background: pt.theme.bg, borderColor: pt.theme.primary + '50' }}
                        className="border rounded-xl p-1.5 text-[8px] font-black transition-all hover:scale-105">
                        <span style={{ color: pt.theme.textPrimary }}>{pt.label}</span>
                      </button>
                    ))}
                  </div>
                  <div className="h-px bg-zinc-800 my-2" />
                  {/* Цвета */}
                  {[
                    { label: 'Фон',         key: 'bg' as keyof MiniTheme },
                    { label: 'Акцент',      key: 'primary' as keyof MiniTheme },
                    { label: 'Текст (осн)', key: 'textPrimary' as keyof MiniTheme },
                    { label: 'Текст (доп)', key: 'textSecondary' as keyof MiniTheme },
                  ].map(({ label, key }) => (
                    <label key={key} className="block">
                      <span className="text-[8px] font-black text-zinc-600 uppercase tracking-widest block mb-1">{label}</span>
                      <div className="flex gap-1.5">
                        <input type="color" value={(theme as any)[key] || '#000000'} onChange={e => updateApp({ theme: { ...theme, [key]: e.target.value } })}
                          className="w-7 h-7 rounded-lg border border-zinc-800 bg-black cursor-pointer p-0.5" />
                        <input value={(theme as any)[key] || ''} onChange={e => updateApp({ theme: { ...theme, [key]: e.target.value } })}
                          className="flex-1 bg-black border border-zinc-800 text-white text-[9px] p-2 rounded-lg outline-none focus:border-indigo-500 transition-all min-w-0" />
                      </div>
                    </label>
                  ))}
                  <label className="block">
                    <span className="text-[8px] font-black text-zinc-600 uppercase tracking-widest block mb-1">Скругление {theme.radius}px</span>
                    <input type="range" min={0} max={32} value={theme.radius} onChange={e => updateApp({ theme: { ...theme, radius: Number(e.target.value) } })}
                      className="w-full accent-indigo-500" />
                  </label>
                </div>
              )}
            </div>
            {/* Слои */}
            {rightTab === 'props' && editing!.components.length > 0 && (
              <div className="border-t border-zinc-800 p-2 shrink-0">
                <p className="text-[7px] font-black text-zinc-700 uppercase tracking-widest mb-1.5 px-1">Слои</p>
                <div className="space-y-0.5 max-h-24 overflow-y-auto">
                  {editing!.components.map((c, i) => {
                    const itm = MINI_PALETTE.find(p => p.type === c.type);
                    const Ic = itm?.icon || Square;
                    return (
                      <button key={c.id} onClick={() => setSelComp(c.id)}
                        className={`w-full flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-[9px] font-bold transition-all ${selectedComp === c.id ? 'bg-indigo-500/15 text-indigo-300' : 'text-zinc-600 hover:text-zinc-300 hover:bg-zinc-800/40'}`}>
                        <Ic className="w-2.5 h-2.5 shrink-0" />
                        <span className="truncate">{itm?.label || c.type}</span>
                        <span className="ml-auto text-zinc-700">{i+1}</span>
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


export default BotEditor;
