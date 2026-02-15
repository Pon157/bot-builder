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
  Brain, Image, ExternalLink, ArrowRight, Layers, Coins, Upload
} from 'lucide-react';

interface BotEditorProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
  onDelete: () => void;
  isAdminMode?: boolean;
}

const BotEditor: React.FC<BotEditorProps> = ({ bot, onUpdate, onDelete, isAdminMode }) => {
  const [activeTab, setActiveTab] = useState<'settings' | 'logic' | 'interface' | 'ai' | 'logs' | 'stats'>('settings');
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
  // tgSupport = только TG support-боты (не VK, не poster, не randomizer)
  const isTgSupport = isSupportBot && !isVK;
  const tabs = [
    { id: 'settings',   label: 'Основные',     icon: Settings,  show: true          },
    { id: 'interface',  label: 'Интерфейс',    icon: Ticket,    show: isTgSupport   },
    { id: 'logic',      label: 'Логика',       icon: Zap,       show: isTgSupport   },
    { id: 'ai',         label: 'ИИ-Ассистент', icon: Brain,     show: isTgSupport   },
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
          model: bot.ai?.model || 'qwen-turbo',
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
                  <p className="text-[9px] text-zinc-500 font-bold">{bot.ai?.model || 'qwen-turbo'} · {bot.ai?.systemPrompt ? 'кастомный промпт' : 'дефолтный промпт'}</p>
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
      <header className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] flex flex-col md:flex-row justify-between items-center gap-6 shadow-2xl">
        <div className="flex items-center gap-6">
          <div className={`w-16 h-16 rounded-2xl flex items-center justify-center border-2 ${bot.status === BotStatus.RUNNING ? `border-current/30 bg-current/5 ${platformColor}` : 'bg-zinc-900 border-zinc-800 text-zinc-600'}`}>
            <HeaderIcon className="w-8 h-8" />
          </div>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-black text-white">{bot.name}</h1>
              <span className={`px-2 py-1 rounded-lg text-[8px] font-black uppercase tracking-widest border ${badgeStyle}`}>{platformBadge}</span>
              {isAdminMode && <span className="px-2 py-1 bg-orange-500/10 border border-orange-500/20 rounded-lg text-orange-500 text-[8px] font-black uppercase tracking-widest">Support</span>}
            </div>
            <div className="flex items-center gap-2 mt-1">
              <span className={`w-2 h-2 rounded-full ${bot.status === BotStatus.RUNNING ? 'bg-blue-500 animate-pulse' : 'bg-zinc-600'}`}></span>
              <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{bot.status}</span>
            </div>
          </div>
        </div>
        <div className="flex gap-4">
          <button onClick={syncState} disabled={isProcessing} className={`px-6 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest flex items-center gap-2 transition-all ${hasUnsavedChanges ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}`}>
            <Save className="w-4 h-4" /> Сохранить
          </button>
          <button onClick={handleToggleServer} disabled={isProcessing} className={`px-10 py-4 rounded-2xl font-black text-xs uppercase flex items-center gap-2 shadow-xl transition-all ${bot.status === BotStatus.RUNNING ? 'bg-red-500/10 text-red-500 border border-red-500/20' : 'bg-blue-600 text-white'}`}>
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

                {/* Платформа — показываем только для support-ботов */}
                {isSupportBot && (
                  <div className="flex bg-black p-1 rounded-2xl border border-zinc-800">
                    {['telegram', 'vk'].map(p => (
                      <button key={p} type="button"
                        onClick={() => handleLocalUpdate({ ...bot, platform: p as any })}
                        className={`flex-1 py-3 rounded-xl text-[10px] font-black uppercase transition-all ${bot.platform === p ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20' : 'text-zinc-500 hover:text-zinc-300'}`}>
                        {p === 'telegram' ? 'Telegram Bot' : 'VK Community'}
                      </button>
                    ))}
                  </div>
                )}

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

{/* Стартовое фото — скрываем для ВК, даже если это SupportBot */}
{isSupportBot && !isVK && (
  <label className="block">
    <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2 flex items-center gap-1.5">
      <Image className="w-3 h-3 text-blue-400" />Фото к /start (опционально)
    </span>
    <div className="mt-2">
      <input
        placeholder="Вставьте прямую ссылку на фото (https://...)"
        className="w-full bg-black border border-zinc-800 p-4 rounded-2xl text-white text-xs outline-none focus:border-blue-500 transition-all"
        value={bot.welcomePhoto || ''}
        onChange={e => handleLocalUpdate({ ...bot, welcomePhoto: e.target.value })} 
      />
    </div>
    
    {/* Блок превью: покажет картинку, если ссылка вставлена */}
    {bot.welcomePhoto && (
      <div className="mt-3 relative inline-block">
        <img 
          src={bot.welcomePhoto} 
          alt="preview"
          className="h-32 rounded-2xl object-cover border border-zinc-800 shadow-lg"
          onError={e => (e.currentTarget.style.display = 'none')} 
        />
        <div className="absolute top-2 left-2 bg-black/50 px-2 py-1 rounded text-[8px] text-white uppercase font-bold backdrop-blur-sm">
          Превью
        </div>
      </div>
    )}
    
    <p className="text-[8px] text-zinc-600 mt-1.5 ml-2 uppercase font-bold">
      Бот отправит это фото первым сообщением вместе с текстом приветствия
    </p>
  </label>
)}

                    {/* Инлайн-кнопки к /start (только TG) */}
                    {isTgSupport && (
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2 flex items-center gap-1.5">
                            <ExternalLink className="w-3 h-3 text-indigo-400" />Инлайн-кнопки к /start
                          </span>
                          <button type="button"
                            onClick={() => handleLocalUpdate({ ...bot, welcomeInline: [...(bot.welcomeInline || []), { text: '', url: '' }] })}
                            className="text-[9px] text-indigo-400 font-bold hover:text-indigo-300 uppercase tracking-wider">
                            + Добавить
                          </button>
                        </div>

                        {(bot.welcomeInline || []).map((btn: any, wi: number) => (
                          <div key={wi} className="flex gap-2">
                            <input placeholder="Текст кнопки"
                              className="flex-1 bg-black border border-zinc-800 p-3 rounded-xl text-xs text-white outline-none focus:border-indigo-500 transition-all"
                              value={btn.text}
                              onChange={e => {
                                const wb = [...(bot.welcomeInline || [])];
                                wb[wi] = { ...wb[wi], text: e.target.value };
                                handleLocalUpdate({ ...bot, welcomeInline: wb });
                              }} />
                            <input placeholder="https://..."
                              className="flex-1 bg-black border border-zinc-800 p-3 rounded-xl text-xs text-white outline-none focus:border-indigo-500 transition-all"
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

                        {/* Превью стартового сообщения с привязанными инлайн-кнопками */}
                        {(bot.welcomeMessage || (bot.welcomeInline || []).length > 0) && (
                          <div className="mt-1 bg-black/50 border border-zinc-800 rounded-2xl p-4">
                            <p className="text-[8px] text-zinc-600 uppercase font-black mb-3 flex items-center gap-1.5">
                              <Smartphone className="w-2.5 h-2.5" />Превью в Telegram
                            </p>
                            {/* Пузырь сообщения */}
                            <div className="bg-zinc-900 rounded-2xl rounded-bl-sm p-3.5 max-w-[85%] mb-2">
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
                            {/* Инлайн-кнопки прикреплены прямо под сообщением */}
                            {(bot.welcomeInline || []).filter((b: any) => b.text).map((b: any, pi: number) => (
                              <div key={pi} className="bg-indigo-500/10 border border-indigo-500/20 rounded-xl py-2 px-4 mb-1.5 text-center">
                                <span className="text-[10px] text-indigo-300 font-semibold">{b.text}</span>
                                {b.url && <span className="text-[8px] text-zinc-600 ml-2">{b.url.replace('https://', '')}</span>}
                              </div>
                            ))}
                            <p className="text-[7px] text-zinc-700 uppercase mt-1.5">↑ Кнопки прикреплены к сообщению в TG</p>
                          </div>
                        )}
                      </div>
                    )}
)}

                <p className="text-[8px] text-zinc-600 uppercase font-black tracking-widest opacity-50 ml-2">* Данные синхронизируются (согласно .env)</p>
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
      {activeTab === 'interface' && isTgSupport && (
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

                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════
          ВКЛАДКА: ТРИГГЕРЫ (только для support-ботов)
      ════════════════════════════════════════════ */}
      {activeTab === 'logic' && isTgSupport && (
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
                    <Brain className="w-4 h-4" />Протестировать ИИ-ассистента
                  </button>
                )}
              </section>

              {/* Параметры модели */}
              <section className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-5">
                <h3 className="text-sm font-black text-white flex items-center gap-2">
                  <Settings className="w-4 h-4 text-blue-500" /> Параметры AI
                </h3>
                <label className="block">
                  <span className="text-[9px] text-zinc-500 font-bold uppercase ml-2">Модель</span>
                  <select
                    className="w-full mt-2 bg-black border border-zinc-800 p-4 rounded-2xl text-sm text-white outline-none focus:border-blue-500 transition-all cursor-pointer"
                    value={bot.ai?.model || 'qwen-turbo'}
                    onChange={e => handleLocalUpdate({ ...bot, ai: { ...(bot.ai || {}), model: e.target.value } })}>
                    <option value="qwen-turbo">turbo (быстрый, дешёвый)</option>
                    <option value="qwen-plus">plus (умнее)</option>
                    <option value="qwen-max">max (самый умный)</option>
                  </select>
                </label>
                <div className="grid grid-cols-2 gap-4">
                  <label className="block">
                    <span className="text-[9px] text-zinc-500 font-bold uppercase ml-2">Макс. токенов/ответ</span>
                    <input type="number" min="100" max="4000" step="100"
                      className="w-full mt-2 bg-black border border-zinc-800 p-4 rounded-2xl text-sm text-white outline-none focus:border-blue-500 transition-all"
                      value={bot.ai?.maxTokensPerReply || 800}
                      onChange={e => handleLocalUpdate({ ...bot, ai: { ...(bot.ai || {}), maxTokensPerReply: parseInt(e.target.value) } })} />
                  </label>
                  <label className="block">
                    <span className="text-[9px] text-zinc-500 font-bold uppercase ml-2">Глубина контекста</span>
                    <input type="number" min="1" max="20"
                      className="w-full mt-2 bg-black border border-zinc-800 p-4 rounded-2xl text-sm text-white outline-none focus:border-blue-500 transition-all"
                      value={bot.ai?.contextMessages || 6}
                      onChange={e => handleLocalUpdate({ ...bot, ai: { ...(bot.ai || {}), contextMessages: parseInt(e.target.value) } })} />
                  </label>
                </div>
                <label className="block">
                  <span className="text-[9px] text-zinc-500 font-bold uppercase ml-2">Системный промпт</span>
                  <textarea
                    className="w-full mt-2 bg-black border border-zinc-800 p-4 rounded-2xl text-xs text-white outline-none focus:border-blue-500 transition-all resize-none min-h-[120px]"
                    placeholder="Ты помощник поддержки компании. Отвечай вежливо и по делу."
                    value={bot.ai?.systemPrompt || ''}
                    onChange={e => handleLocalUpdate({ ...bot, ai: { ...(bot.ai || {}), systemPrompt: e.target.value } })} />
                </label>
              </section>
            </div>
          )}
        </div>
      )}

      {/* Аналитика и логи */}
      {activeTab === 'stats' && <BotStatsView bot={bot} onUpdate={onUpdate} />}
      {activeTab === 'logs'  && <BotConsole botId={bot.id} />}

    </div>
  );
};

export default BotEditor;
