import React, { useState, useEffect, useRef } from 'react';
import { BotConfig, BotStatus } from '../types';
import { api } from '../services/apiService';
import BotConsole from './BotConsole';
import BotStatsView from './BotStatsView';
import { 
  Settings, Cpu, BarChart3, Terminal, X, Save, Power, 
  Ticket, Plus, MessageSquare, User, CheckSquare, 
  Square, Zap, Shield, Sliders, Layout, ShieldAlert, Lock, Trash2, 
  AlertCircle, Search, ChevronRight, Send, Clock
} from 'lucide-react';

interface BotEditorProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
  onDelete: () => void;
}

const BotEditor: React.FC<BotEditorProps> = ({ bot, onUpdate, onDelete }) => {
  const [activeTab, setActiveTab] = useState<'settings' | 'logic' | 'interface' | 'logs' | 'stats' | 'chat'>('settings');
  const [isProcessing, setIsProcessing] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  
  // --- CRM STATE ---
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<any[]>([]);
  const [replyText, setReplyText] = useState('');
  const [searchUser, setSearchUser] = useState('');
  const [isSending, setIsSending] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Скролл чата
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  const defaultSettings: BotConfig['settings'] = {
    useTopics: false,
    topicPerRequest: false,
    anonymousTopics: false,
    forwardToAdmin: true,
    antiSpam: true,
    showUserInfo: true,
    showUsername: true,
    autoApproveJoin: false,
    rateLimit: 1,
    autoBanThreshold: 3,
    showHeaderId: true,
    showHeaderName: true,
    showHeaderUsername: true,
    notifyOnStart: true,
    notifyOnBlock: true,
    firstMessageHeader: "🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>",
    ticketMessageHeader: "🆘 <b>ЗАЯВКА [{btn}]:</b>",
    commonMessageHeader: "📩 <b>СООБЩЕНИЕ:</b>"
  };

  const safeSettings = { ...defaultSettings, ...(bot.settings || {}) };

  // --- CRM FUNCTIONS ---
  const loadChatHistory = async (userId: string) => {
    setSelectedUserId(userId);
    try {
      const history = await api.getChatHistory(bot.id, userId);
      setChatMessages(Array.isArray(history) ? history : []);
    } catch (e) {
      console.error("CRM Load Error:", e);
      setChatMessages([]);
    }
  };

  const handleSendMessage = async () => {
    if (!replyText.trim() || !selectedUserId) return;
    setIsSending(true);
    try {
      await api.sendChatMessage(bot.id, selectedUserId, replyText);
      setChatMessages(prev => [...prev, {
        t: Math.floor(Date.now() / 1000),
        role: 'admin',
        msg: replyText
      }]);
      setReplyText('');
    } catch (e) {
      alert("Ошибка отправки сообщения");
    } finally {
      setIsSending(false);
    }
  };

  // --- EDITOR FUNCTIONS ---
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
        if (res === true) {
            onUpdate({ ...bot, status: BotStatus.RUNNING });
        } else {
            alert(`Ошибка запуска: ${res}`);
        }
      }
    } finally { setIsProcessing(false); }
  };

  const syncState = async () => {
    setIsProcessing(true);
    try {
        const updated = await api.saveBot(bot.owner_id, bot);
        if (updated) onUpdate(updated);
        setHasUnsavedChanges(false);
        alert("Конфигурация успешно сохранена и синхронизирована!");
    } catch {
        alert("Ошибка сети при сохранении");
    } finally {
        setIsProcessing(false);
    }
  };

  const updateSetting = (key: keyof typeof defaultSettings, val: any) => {
    setHasUnsavedChanges(true);
    onUpdate({ ...bot, settings: { ...safeSettings, [key]: val } });
  };

  const handleLocalUpdate = (updatedBot: BotConfig) => {
    setHasUnsavedChanges(true);
    onUpdate(updatedBot);
  };

  // Фильтр пользователей для CRM
  const connectedUsers = (bot.config?.connectedUsers || []) as any[];
  const filteredUsers = connectedUsers.filter(u => 
    u.first_name?.toLowerCase().includes(searchUser.toLowerCase()) || 
    u.id.toString().includes(searchUser)
  );

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-20">
      {hasUnsavedChanges && (
        <div className="fixed bottom-10 left-1/2 -translate-x-1/2 z-[100] bg-blue-600 text-white px-8 py-4 rounded-2xl shadow-2xl flex items-center gap-4 animate-bounce">
            <AlertCircle className="w-5 h-5" />
            <span className="text-xs font-black uppercase tracking-widest">Несохраненные изменения!</span>
            <button onClick={syncState} disabled={isProcessing} className="bg-white text-blue-600 px-4 py-1.5 rounded-xl font-black text-[10px] uppercase">Сохранить</button>
        </div>
      )}

      {/* HEADER */}
      <header className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] flex flex-col md:flex-row justify-between items-center gap-6 shadow-2xl relative overflow-hidden">
        <div className="flex items-center gap-6 relative z-10">
          <div className={`w-16 h-16 rounded-2xl flex items-center justify-center border-2 ${bot.status === BotStatus.RUNNING ? 'bg-blue-500/10 border-blue-500/30 text-blue-500' : 'bg-zinc-900 border-zinc-800 text-zinc-600'}`}>
            <Cpu className="w-8 h-8" />
          </div>
          <div>
            <h1 className="text-3xl font-black text-white">{bot.name}</h1>
            <div className="flex items-center gap-2 mt-1">
              <span className={`w-2 h-2 rounded-full ${bot.status === BotStatus.RUNNING ? 'bg-blue-500 animate-pulse' : 'bg-zinc-600'}`}></span>
              <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{bot.status}</span>
            </div>
          </div>
        </div>
        <div className="flex gap-4 relative z-10">
           <button onClick={syncState} disabled={isProcessing} className={`px-6 py-4 rounded-2xl text-[10px] font-black uppercase tracking-widest flex items-center gap-2 transition-all ${hasUnsavedChanges ? 'bg-blue-600 text-white animate-pulse' : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}`}>
             <Save className="w-4 h-4" /> Сохранить
           </button>
           <button onClick={handleToggleServer} disabled={isProcessing} className={`px-10 py-4 rounded-2xl font-black text-xs uppercase transition-all flex items-center gap-2 shadow-xl ${bot.status === BotStatus.RUNNING ? 'bg-red-500/10 text-red-500 border border-red-500/20' : 'bg-blue-600 text-white'}`}>
             <Power className="w-4 h-4" /> {bot.status === BotStatus.RUNNING ? 'Остановить' : 'Запустить'}
           </button>
        </div>
      </header>

      {/* TABS */}
      <div className="flex gap-2 border-b border-zinc-800 overflow-x-auto no-scrollbar">
        {[
          {id: 'settings', label: 'Основные', icon: Settings},
          {id: 'interface', label: 'Меню (Кнопки)', icon: Ticket},
          {id: 'logic', label: 'Триггеры', icon: Zap},
          {id: 'chat', label: 'CRM Чат', icon: MessageSquare},
          {id: 'stats', label: 'Аналитика', icon: BarChart3},
          {id: 'logs', label: 'Терминал', icon: Terminal}
        ].map((t) => (
          <button key={t.id} onClick={() => setActiveTab(t.id as any)} className={`px-6 py-4 text-[10px] font-black uppercase tracking-widest border-b-2 transition-all flex items-center gap-2 whitespace-nowrap ${activeTab === t.id ? 'border-blue-500 text-blue-500' : 'border-transparent text-zinc-500'}`}>
            <t.icon className="w-3.5 h-3.5" /> {t.label}
          </button>
        ))}
      </div>

      <div className="min-h-[400px]">
        {/* === CRM CHAT === */}
        {activeTab === 'chat' && (
           <div className="flex h-[700px] bg-[#0a0a0a] border border-zinc-800 rounded-[2.5rem] overflow-hidden shadow-2xl relative">
              {/* Sidebar: User List */}
              <div className="w-80 border-r border-zinc-800 flex flex-col bg-zinc-900/10">
                  <div className="p-5 border-b border-zinc-800">
                      <div className="relative">
                          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-500" />
                          <input 
                              type="text" 
                              placeholder="Поиск клиента..."
                              className="w-full bg-black border border-zinc-800 rounded-xl py-2.5 pl-9 pr-4 text-xs text-white outline-none focus:border-blue-500 transition-all"
                              value={searchUser}
                              onChange={e => setSearchUser(e.target.value)}
                          />
                      </div>
                  </div>
                  <div className="flex-1 overflow-y-auto custom-scrollbar">
                      {filteredUsers.length === 0 ? (
                          <div className="p-10 text-center opacity-30">
                              <User className="w-8 h-8 mx-auto mb-2" />
                              <p className="text-[10px] font-bold uppercase">Нет пользователей</p>
                          </div>
                      ) : (
                          filteredUsers.map(u => (
                              <button 
                                  key={u.id}
                                  onClick={() => loadChatHistory(u.id)}
                                  className={`w-full p-4 flex items-center gap-3 border-b border-zinc-900/50 hover:bg-white/[0.02] transition-all text-left group ${selectedUserId === u.id ? 'bg-blue-600/10 border-r-2 border-r-blue-500' : ''}`}
                              >
                                  <div className={`w-10 h-10 rounded-2xl flex items-center justify-center font-bold text-sm transition-colors ${selectedUserId === u.id ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400 group-hover:bg-zinc-700'}`}>
                                      {u.first_name?.[0] || '?'}
                                  </div>
                                  <div className="flex-1 min-w-0">
                                      <div className="flex justify-between items-center mb-0.5">
                                          <p className={`text-xs font-bold truncate ${selectedUserId === u.id ? 'text-white' : 'text-zinc-300'}`}>{u.first_name || 'Без имени'}</p>
                                      </div>
                                      <p className="text-[10px] text-zinc-600 font-mono truncate">ID: {u.id}</p>
                                  </div>
                                  <ChevronRight className={`w-3 h-3 ${selectedUserId === u.id ? 'text-blue-500' : 'text-zinc-700 opacity-0 group-hover:opacity-100'}`} />
                              </button>
                          ))
                      )}
                  </div>
              </div>

              {/* Chat Area */}
              <div className="flex-1 flex flex-col bg-[#050505]">
                  {selectedUserId ? (
                      <>
                          {/* Chat Header */}
                          <div className="px-6 py-4 border-b border-zinc-800 bg-zinc-900/20 flex justify-between items-center">
                              <div className="flex items-center gap-3">
                                  <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
                                  <span className="text-xs font-black text-white uppercase tracking-widest">
                                      Чат с {filteredUsers.find(u => u.id === selectedUserId)?.first_name}
                                  </span>
                              </div>
                              <span className="text-[10px] font-mono text-zinc-600">HISTORY MODE</span>
                          </div>

                          {/* Messages List */}
                          <div className="flex-1 overflow-y-auto p-6 space-y-4 custom-scrollbar bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-zinc-900/20 via-black to-black">
                              {chatMessages.length === 0 && (
                                  <div className="h-full flex flex-col items-center justify-center opacity-20">
                                      <MessageSquare className="w-12 h-12 mb-3" />
                                      <p className="text-[10px] font-black uppercase tracking-widest">История сообщений пуста</p>
                                  </div>
                              )}
                              {chatMessages.map((msg, i) => (
                                  <div key={i} className={`flex ${msg.role === 'admin' ? 'justify-end' : 'justify-start'} animate-in slide-in-from-bottom-2`}>
                                      <div className={`max-w-[70%] p-4 rounded-2xl text-xs leading-relaxed shadow-lg backdrop-blur-sm ${
                                          msg.role === 'admin' 
                                          ? 'bg-blue-600 text-white rounded-tr-sm' 
                                          : 'bg-zinc-900 border border-zinc-800 text-zinc-300 rounded-tl-sm'
                                      }`}>
                                          {msg.msg}
                                          <div className={`flex items-center gap-1 mt-2 text-[9px] font-bold uppercase ${msg.role === 'admin' ? 'text-blue-200' : 'text-zinc-600'}`}>
                                              <Clock className="w-2.5 h-2.5" />
                                              {new Date(msg.t * 1000).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                                          </div>
                                      </div>
                                  </div>
                              ))}
                              <div ref={chatEndRef} />
                          </div>

                          {/* Input Area */}
                          <div className="p-5 border-t border-zinc-800 bg-zinc-900/10">
                              <div className="flex gap-3 relative">
                                  <input 
                                      className="flex-1 bg-zinc-950 border border-zinc-800 rounded-xl px-5 py-4 text-xs text-white outline-none focus:border-blue-500/50 transition-all placeholder:text-zinc-700"
                                      placeholder="Напишите сообщение..."
                                      value={replyText}
                                      onChange={e => setReplyText(e.target.value)}
                                      onKeyDown={e => e.key === 'Enter' && handleSendMessage()}
                                  />
                                  <button 
                                      onClick={handleSendMessage}
                                      disabled={isSending || !replyText.trim()}
                                      className="w-14 bg-blue-600 hover:bg-blue-500 text-white rounded-xl flex items-center justify-center disabled:opacity-50 disabled:grayscale transition-all shadow-lg shadow-blue-600/10"
                                  >
                                      <Send className="w-5 h-5" />
                                  </button>
                              </div>
                          </div>
                      </>
                  ) : (
                      <div className="flex-1 flex flex-col items-center justify-center text-zinc-700">
                          <div className="w-20 h-20 bg-zinc-900/50 rounded-full flex items-center justify-center mb-6 border border-zinc-800">
                              <MessageSquare className="w-8 h-8 opacity-50" />
                          </div>
                          <p className="text-xs font-black uppercase tracking-[0.2em] mb-2">CRM Система</p>
                          <p className="text-[10px] font-medium uppercase opacity-50">Выберите диалог слева</p>
                      </div>
                  )}
              </div>
           </div>
        )}

        {/* === SETTINGS === */}
        {activeTab === 'settings' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-8">
              <section>
                <h2 className="text-sm font-black text-white uppercase flex items-center gap-2 mb-6">
                  <Sliders className="w-4 h-4 text-blue-500" /> Системная конфигурация
                </h2>
                <div className="space-y-5">
                  <label className="block">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">Telegram Bot Token</span>
                    <input type="password" placeholder="Токен от @BotFather" className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white font-mono outline-none focus:border-blue-500 transition-all" value={bot.token} onChange={e => handleLocalUpdate({...bot, token: e.target.value})} />
                  </label>
                  <label className="block">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">ID Группы Админов (Forum)</span>
                    <input type="text" placeholder="-100..." className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white outline-none focus:border-blue-500 transition-all" value={bot.adminChatId} onChange={e => handleLocalUpdate({...bot, adminChatId: e.target.value})} />
                  </label>
                  <label className="block">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">Приветствие (/start)</span>
                    <textarea className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white min-h-[100px] outline-none text-xs focus:border-blue-500 transition-all resize-none" value={bot.welcomeMessage || ""} onChange={e => handleLocalUpdate({...bot, welcomeMessage: e.target.value})} />
                  </label>
                </div>
              </section>
              {/* Other settings sections... */}
               <section className="space-y-6">
                <h2 className="text-sm font-black text-white uppercase flex items-center gap-2 mb-6">
                  <Layout className="w-4 h-4 text-emerald-500" /> Конструктор шапки сообщений
                </h2>
                
                <div className="space-y-4">
                  <div>
                    <span className="text-[9px] font-bold text-zinc-500 uppercase ml-2">Заголовок первого обращения</span>
                    <input 
                      className="w-full mt-1.5 bg-black border border-zinc-800 p-4 rounded-xl text-xs text-white outline-none focus:border-emerald-500 transition-all" 
                      value={safeSettings.firstMessageHeader || ""} 
                      onChange={e => updateSetting('firstMessageHeader', e.target.value)}
                      placeholder="🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>"
                    />
                  </div>
                  <div>
                    <span className="text-[9px] font-bold text-zinc-500 uppercase ml-2">Заголовок заявки (кнопки)</span>
                    <input 
                      className="w-full mt-1.5 bg-black border border-zinc-800 p-4 rounded-xl text-xs text-white outline-none focus:border-emerald-500 transition-all" 
                      value={safeSettings.ticketMessageHeader || ""} 
                      onChange={e => updateSetting('ticketMessageHeader', e.target.value)}
                      placeholder="🆘 <b>ЗАЯВКА [{btn}]:</b>"
                    />
                    <p className="text-[8px] text-zinc-600 mt-1 px-2 uppercase font-bold tracking-tighter">* Используйте {'{btn}'} для подстановки названия кнопки</p>
                  </div>
                  <div>
                    <span className="text-[9px] font-bold text-zinc-500 uppercase ml-2">Обычное сообщение</span>
                    <input 
                      className="w-full mt-1.5 bg-black border border-zinc-800 p-4 rounded-xl text-xs text-white outline-none focus:border-emerald-500 transition-all" 
                      value={safeSettings.commonMessageHeader || ""} 
                      onChange={e => updateSetting('commonMessageHeader', e.target.value)}
                      placeholder="📩 <b>СООБЩЕНИЕ:</b>"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2">
                  {[
                    {k: 'showHeaderName', l: 'Имя'}, {k: 'showHeaderUsername', l: 'Юзер'}, {k: 'showHeaderId', l: 'ID'}
                  ].map(field => (
                    <button key={field.k} onClick={() => updateSetting(field.k as any, !safeSettings[field.k as keyof typeof safeSettings])} className={`flex items-center justify-between p-4 rounded-xl border text-[9px] font-bold uppercase transition-all ${safeSettings[field.k as keyof typeof safeSettings] ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-black border-zinc-800 text-zinc-600'}`}>
                      {field.l} {safeSettings[field.k as keyof typeof safeSettings] ? <CheckSquare className="w-3 h-3" /> : <Square className="w-3 h-3" />}
                    </button>
                  ))}
                </div>
              </section>
            </div>
            
            <div className="space-y-8">
                <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
                  <h3 className="text-sm font-black text-white uppercase flex items-center gap-2">
                    <Lock className="w-4 h-4 text-rose-500" /> Безопасность и Анти-Флуд
                  </h3>
                  <div className="space-y-4">
                    <div className="flex items-center justify-between p-5 rounded-2xl bg-black border border-zinc-800">
                      <div><p className="text-xs font-bold text-white">Интервал анти-спама</p><p className="text-[9px] text-zinc-500 uppercase">Сек. между сообщениями</p></div>
                      <input type="number" step="0.5" className="w-16 bg-zinc-900 border border-zinc-800 p-2 rounded-lg text-center text-xs text-white" value={safeSettings.rateLimit} onChange={e => updateSetting('rateLimit', parseFloat(e.target.value))} />
                    </div>
                    <div className="flex items-center justify-between p-5 rounded-2xl bg-black border border-zinc-800">
                      <div><p className="text-xs font-bold text-white">Лимит Предупреждений</p><p className="text-[9px] text-zinc-500 uppercase">Варнов до авто-бана</p></div>
                      <input type="number" className="w-16 bg-zinc-900 border border-zinc-800 p-2 rounded-lg text-center text-xs text-white" value={safeSettings.autoBanThreshold} onChange={e => updateSetting('autoBanThreshold', parseInt(e.target.value))} />
                    </div>
                  </div>
                </div>

                <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
                    <h3 className="text-sm font-black text-white uppercase flex items-center gap-2">
                      <ShieldAlert className="w-4 h-4 text-emerald-500" /> Форум (Темы) и Анонимность
                    </h3>
                    <div className="space-y-3">
                      <button onClick={() => updateSetting('useTopics', !safeSettings.useTopics)} className={`w-full flex items-center justify-between p-5 rounded-2xl border transition-all ${safeSettings.useTopics ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-black border-zinc-800 text-zinc-600'}`}>
                        <div className="text-left"><p className="text-xs font-bold">Использовать Темы (Forum)</p><p className="text-[9px] uppercase opacity-50">Для супергрупп</p></div>
                        {safeSettings.useTopics ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                      </button>
                      <button onClick={() => updateSetting('topicPerRequest', !safeSettings.topicPerRequest)} className={`w-full flex items-center justify-between p-5 rounded-2xl border transition-all ${safeSettings.topicPerRequest ? 'bg-blue-500/10 border-blue-500/30 text-blue-400' : 'bg-black border-zinc-800 text-zinc-600'}`}>
                        <div className="text-left"><p className="text-xs font-bold">Новая ветка на каждый тикет</p><p className="text-[9px] uppercase opacity-50">Ticket System Mode</p></div>
                        {safeSettings.topicPerRequest ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                      </button>
                      <button onClick={() => updateSetting('anonymousTopics', !safeSettings.anonymousTopics)} className={`w-full flex items-center justify-between p-5 rounded-2xl border transition-all ${safeSettings.anonymousTopics ? 'bg-zinc-800 text-white' : 'bg-black border-zinc-800 text-zinc-600'}`}>
                        <div className="text-left"><p className="text-xs font-bold">Анонимные ID (Anon ID)</p><p className="text-[9px] uppercase opacity-50">Хешировать данные в группе</p></div>
                        {safeSettings.anonymousTopics ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                      </button>
                    </div>
                </div>
                <button onClick={() => window.confirm("Вы точно хотите удалить этот инстанс?") && onDelete()} className="w-full p-5 text-[10px] font-black uppercase text-rose-500 bg-rose-500/5 rounded-3xl border border-rose-500/10 hover:bg-rose-500/10 transition-all flex items-center justify-center gap-2">
                    <Trash2 className="w-4 h-4" /> Удалить навсегда
                </button>
            </div>
          </div>
        )}
        
        {activeTab === 'interface' && (
          <div className="space-y-6">
             <div className="flex justify-between items-center mb-6">
                <h2 className="text-2xl font-black text-white uppercase tracking-tight">Конструктор Кнопок</h2>
                <button onClick={() => handleLocalUpdate({...bot, buttons: [...(bot.buttons || []), {text: '', response: '', type: 'message'}]})} className="bg-blue-600 px-8 py-4 rounded-2xl text-[11px] font-black text-white uppercase flex items-center gap-2 shadow-lg shadow-blue-600/20">
                    <Plus className="w-4 h-4" /> Новая кнопка
                </button>
             </div>
             <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
               {(bot.buttons || []).map((btn, i) => (
                 <div key={i} className="bg-[#0d0d0d] border border-zinc-800 rounded-[2.5rem] p-8 space-y-6 relative group border-t-4 border-t-blue-500/20 shadow-xl">
                    <button onClick={() => handleLocalUpdate({...bot, buttons: bot.buttons.filter((_, idx) => idx !== i)})} className="absolute top-6 right-6 text-zinc-600 hover:text-rose-500 transition-colors"><X className="w-5 h-5" /></button>
                    <div className="space-y-5">
                        <label className="block"><span className="text-[9px] font-bold text-zinc-600 uppercase ml-2">Текст на кнопке</span><input className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white text-sm font-bold outline-none focus:border-blue-500" value={btn.text} onChange={e => { const nb = [...bot.buttons]; nb[i].text = e.target.value; handleLocalUpdate({...bot, buttons: nb}); }} /></label>
                        <label className="block"><span className="text-[9px] font-bold text-zinc-600 uppercase ml-2">Ответ системы</span><textarea className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white text-sm min-h-[120px] outline-none focus:border-blue-500 resize-none" value={btn.response} onChange={e => { const nb = [...bot.buttons]; nb[i].response = e.target.value; handleLocalUpdate({...bot, buttons: nb}); }} /></label>
                        <div className="flex bg-black p-1 rounded-xl border border-zinc-800">
                          {['message', 'request'].map(type => (
                            <button key={type} onClick={() => { const nb = [...bot.buttons]; nb[i].type = type as any; handleLocalUpdate({...bot, buttons: nb}); }} className={`flex-1 py-2.5 rounded-lg text-[9px] font-black uppercase transition-all ${btn.type === type ? 'bg-blue-600 text-white' : 'text-zinc-600'}`}>{type === 'message' ? 'Обычный ответ' : '🆘 Заявка (Тикет)'}</button>
                          ))}
                        </div>
                    </div>
                 </div>
               ))}
             </div>
          </div>
        )}

        {activeTab === 'logic' && (
          <div className="space-y-6">
            <div className="flex justify-between items-end mb-6"><h2 className="text-2xl font-black text-white uppercase">Триггеры авто-ответа</h2><button onClick={() => handleLocalUpdate({...bot, triggers: [...(bot.triggers || []), {keyword: '', response: ''}]})} className="bg-emerald-600 px-8 py-4 rounded-2xl text-[10px] font-black text-white uppercase flex items-center gap-2 transition-all"><Plus className="w-4 h-4" /> Новый триггер</button></div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
               {(bot.triggers || []).map((trig, i) => (
                 <div key={i} className="bg-[#0d0d0d] border border-zinc-800 rounded-[2.5rem] p-8 space-y-5 relative border-t-4 border-t-emerald-500/20 shadow-xl">
                    <button onClick={() => handleLocalUpdate({...bot, triggers: bot.triggers.filter((_, idx) => idx !== i)})} className="absolute top-6 right-6 text-zinc-600 hover:text-rose-500"><X className="w-5 h-5" /></button>
                    <input placeholder="Ключевое слово (например: цена)" className="w-full bg-black border border-zinc-800 p-5 rounded-2xl text-white text-sm font-bold outline-none focus:border-emerald-500" value={trig.keyword} onChange={e => { const nt = [...bot.triggers]; nt[i].keyword = e.target.value; handleLocalUpdate({...bot, triggers: nt}); }} />
                    <textarea placeholder="Что бот должен ответить..." className="w-full bg-black border border-zinc-800 p-5 rounded-2xl text-white text-sm outline-none min-h-[120px] focus:border-emerald-500" value={trig.response} onChange={e => { const nt = [...bot.triggers]; nt[i].response = e.target.value; handleLocalUpdate({...bot, triggers: nt}); }} />
                 </div>
               ))}
            </div>
          </div>
        )}

        {activeTab === 'stats' && <BotStatsView bot={bot} onUpdate={onUpdate} />}
        {activeTab === 'logs' && <BotConsole botId={bot.id} />}
      </div>
    </div>
  );
};

export default BotEditor;
