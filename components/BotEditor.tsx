import React, { useState, useEffect, useRef } from 'react';
import { BotConfig, BotStatus } from '../types';
import { api } from '../services/apiService';
import BotConsole from './BotConsole';
import BotStatsView from './BotStatsView';
import { 
  Settings, Cpu, BarChart3, Terminal, X, Save, Power, 
  Ticket, Plus, MessageSquare, User, CheckSquare, 
  Square, Zap, Bell, Shield, Sliders, Layout, ShieldAlert, Lock, Trash2, ShieldCheck, AlertCircle, Type as TypeIcon,
  ChevronRight, Activity
} from 'lucide-react';

interface BotEditorProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
  onDelete: () => void;
  isAdminMode?: boolean; 
}

const BotEditor: React.FC<BotEditorProps> = ({ bot, onUpdate, onDelete, isAdminMode }) => {
  // --- [ ЛОКАЛЬНЫЙ СТЕЙТ ДЛЯ ЗАЩИТЫ ДАННЫХ ] ---
  const [localBot, setLocalBot] = useState<BotConfig>(() => ({
    ...bot,
    buttons: bot.buttons || [],
    triggers: bot.triggers || [],
    settings: bot.settings || {}
  }));
  
  const [activeTab, setActiveTab] = useState<'settings' | 'logic' | 'interface' | 'logs' | 'stats' | 'chat'>('settings');
  const [isProcessing, setIsProcessing] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [messages, setMessages] = useState<any[]>([]);

  // Реф для смены бота (если переключаемся между ботами в списке)
  const lastBotId = useRef(bot.id);
  useEffect(() => {
    if (lastBotId.current !== bot.id) {
      setLocalBot({
        ...bot,
        buttons: bot.buttons || [],
        triggers: bot.triggers || [],
        settings: bot.settings || {}
      });
      lastBotId.current = bot.id;
      setHasUnsavedChanges(false);
    }
  }, [bot]);

  // Дефолтные настройки для предотвращения undefined
  const safeSettings = {
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
    firstMessageHeader: "🆕 <b>ПЕРВОЕ ОБРАЩЕНИЕ:</b>",
    ticketMessageHeader: "🆘 <b>ЗАЯВКА [{btn}]:</b>",
    commonMessageHeader: "📩 <b>СООБЩЕНИЕ:</b>",
    ...(localBot.settings || {})
  };

  // --- [ ФУНКЦИИ ИЗМЕНЕНИЯ ] ---

  const handleFieldChange = (updates: Partial<BotConfig>) => {
    setLocalBot(prev => ({ ...prev, ...updates }));
    setHasUnsavedChanges(true);
  };

  const updateSetting = (key: string, val: any) => {
    handleFieldChange({
      settings: { ...safeSettings, [key]: val }
    });
  };

  const syncWithDatabase = async () => {
    if (isProcessing) return;
    setIsProcessing(true);
    try {
      // Отправляем локальное состояние в базу
      const updated = await api.saveBot(localBot.owner_id, localBot);
      if (updated) {
        const sanitized = {
          ...updated,
          buttons: updated.buttons || [],
          triggers: updated.triggers || [],
          settings: updated.settings || {}
        };
        setLocalBot(sanitized);
        onUpdate(sanitized); // Синхронизируем App.tsx
        setHasUnsavedChanges(false);
        alert("✅ Данные успешно синхронизированы с базой");
      }
    } catch (e) {
      console.error(e);
      alert("❌ Ошибка при обращении к API");
    } finally {
      setIsProcessing(false);
    }
  };

  const toggleBotStatus = async () => {
    const action = localBot.status === BotStatus.RUNNING ? 'stop' : 'start';
    setIsProcessing(true);
    try {
      // Пытаемся запустить/остановить процесс на сервере
      const success = await api.adminBotAction(localStorage.getItem('admin_token') || '', localBot.id, action);
      if (success) {
        handleFieldChange({ status: action === 'start' ? BotStatus.RUNNING : BotStatus.IDLE });
      }
    } catch (e) {
      alert("Не удалось изменить состояние процесса");
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="space-y-8 pb-24 animate-in fade-in duration-500">
      {/* ПЛАШКА ПРЕДУПРЕЖДЕНИЯ */}
      {hasUnsavedChanges && (
        <div className="fixed bottom-10 left-1/2 -translate-x-1/2 z-[100] bg-blue-600 text-white px-8 py-4 rounded-2xl shadow-2xl flex items-center gap-6 border border-blue-400 animate-bounce">
          <div className="flex flex-col">
            <span className="text-[10px] font-black uppercase tracking-widest opacity-70">Unsaved Data</span>
            <span className="text-xs font-bold whitespace-nowrap">Изменения еще не в БД</span>
          </div>
          <button onClick={syncWithDatabase} className="bg-white text-blue-600 px-6 py-2 rounded-xl font-black text-[10px] uppercase hover:scale-105 transition-all">Сохранить</button>
        </div>
      )}

      {/* HEADER КАРТОЧКА */}
      <header className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] flex flex-col md:flex-row justify-between items-center gap-6 shadow-2xl relative overflow-hidden group">
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-blue-500/20 to-transparent" />
        <div className="flex items-center gap-6">
          <div className={`w-20 h-20 rounded-[1.8rem] flex items-center justify-center border-2 transition-all duration-500 ${localBot.status === BotStatus.RUNNING ? 'bg-blue-500/10 border-blue-500/30 text-blue-500 shadow-[0_0_30px_rgba(59,130,246,0.2)]' : 'bg-zinc-900 border-zinc-800 text-zinc-600'}`}>
            <Cpu className={`w-10 h-10 ${localBot.status === BotStatus.RUNNING ? 'animate-pulse' : ''}`} />
          </div>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-4xl font-black text-white tracking-tighter">{localBot.name}</h1>
              <div className={`px-3 py-1 rounded-full text-[8px] font-black uppercase tracking-widest border ${localBot.status === BotStatus.RUNNING ? 'bg-blue-500/10 border-blue-500/20 text-blue-500' : 'bg-zinc-900 border-zinc-800 text-zinc-500'}`}>
                {localBot.status}
              </div>
            </div>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-500 mt-2 flex items-center gap-2">
              <ShieldCheck className="w-3 h-3 text-blue-500" /> Instance ID: {localBot.id}
            </p>
          </div>
        </div>
        <div className="flex gap-3">
          <button onClick={toggleBotStatus} disabled={isProcessing} className={`p-5 rounded-2xl border transition-all ${localBot.status === BotStatus.RUNNING ? 'bg-red-500/10 border-red-500/20 text-red-500 hover:bg-red-500/20' : 'bg-blue-600 border-blue-500 text-white hover:bg-blue-700 shadow-lg shadow-blue-600/20'}`}>
            <Power className="w-6 h-6" />
          </button>
          <button onClick={syncWithDatabase} disabled={isProcessing} className="px-8 py-5 bg-zinc-800 hover:bg-zinc-700 text-white rounded-2xl text-[10px] font-black uppercase tracking-widest border border-zinc-700 flex items-center gap-3 transition-all">
            <Save className="w-4 h-4" /> {isProcessing ? 'Saving...' : 'Сохранить'}
          </button>
          {!isAdminMode && (
            <button onClick={onDelete} className="p-5 bg-zinc-900/50 border border-zinc-800 text-zinc-600 hover:text-red-500 hover:border-red-500/30 rounded-2xl transition-all">
              <Trash2 className="w-6 h-6" />
            </button>
          )}
        </div>
      </header>

      {/* НАВИГАЦИЯ */}
      <nav className="flex gap-2 border-b border-zinc-800/50 overflow-x-auto no-scrollbar">
        {[
          { id: 'settings', label: 'Система', icon: Settings },
          { id: 'interface', label: 'Интерфейс', icon: Layout },
          { id: 'logic', label: 'Логика', icon: Zap },
          { id: 'logs', label: 'Консоль', icon: Terminal },
          { id: 'chat', label: 'Чат', icon: MessageSquare },
          { id: 'stats', label: 'Статистика', icon: BarChart3 }
        ].map((tab) => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id as any)} className={`px-8 py-5 text-[10px] font-black uppercase tracking-[0.15em] border-b-2 transition-all flex items-center gap-3 whitespace-nowrap ${activeTab === tab.id ? 'border-blue-500 text-blue-500 bg-blue-500/5' : 'border-transparent text-zinc-500 hover:text-zinc-300'}`}>
            <tab.icon className="w-4 h-4" /> {tab.label}
          </button>
        ))}
      </nav>

      {/* КОНТЕНТ */}
      <div className="min-h-[600px] animate-in slide-in-from-bottom-4 duration-500">
        
        {activeTab === 'settings' && (
          <div className="space-y-8">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              {/* Token & IDs */}
              <section className="bg-[#111] border border-zinc-800 p-10 rounded-[3rem] space-y-8 shadow-xl">
                <h2 className="text-sm font-black text-white uppercase tracking-widest flex items-center gap-3 mb-2"><Lock className="w-4 h-4 text-blue-500" /> API Connection</h2>
                <div className="space-y-6">
                  <div>
                    <label className="text-[9px] font-black text-zinc-500 uppercase ml-2 tracking-widest">Bot Token</label>
                    <input type="password" placeholder="5000000000:AA..." className="w-full mt-3 bg-black border border-zinc-800 p-5 rounded-2xl text-white outline-none focus:border-blue-500 transition-all font-mono text-xs" value={localBot.token || ''} onChange={e => handleFieldChange({ token: e.target.value })} />
                  </div>
                  <div>
                    <label className="text-[9px] font-black text-zinc-500 uppercase ml-2 tracking-widest">Admin Chat ID</label>
                    <input type="text" placeholder="123456789" className="w-full mt-3 bg-black border border-zinc-800 p-5 rounded-2xl text-white outline-none focus:border-blue-500 transition-all font-mono text-xs" value={localBot.adminChatId || ''} onChange={e => handleFieldChange({ adminChatId: e.target.value })} />
                  </div>
                </div>
              </section>

              {/* Security Toggles */}
              <section className="bg-[#111] border border-zinc-800 p-10 rounded-[3rem] space-y-8 shadow-xl">
                <h2 className="text-sm font-black text-white uppercase tracking-widest flex items-center gap-3 mb-2"><Shield className="w-4 h-4 text-blue-500" /> Security & Flows</h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {[
                    { key: 'antiSpam', label: 'Анти-спам', icon: ShieldAlert },
                    { key: 'forwardToAdmin', label: 'Пересыл админу', icon: Bell },
                    { key: 'autoApproveJoin', label: 'Авто-прием заявок', icon: CheckSquare },
                    { key: 'showUserInfo', label: 'Показывать данные', icon: User }
                  ].map((s) => (
                    <button key={s.key} onClick={() => updateSetting(s.key, !safeSettings[s.key as keyof typeof safeSettings])} className={`p-5 rounded-2xl border flex items-center gap-4 transition-all ${safeSettings[s.key as keyof typeof safeSettings] ? 'bg-blue-600/10 border-blue-500/30 text-white' : 'bg-black border-zinc-800 text-zinc-600'}`}>
                      <s.icon className={`w-5 h-5 ${safeSettings[s.key as keyof typeof safeSettings] ? 'text-blue-500' : ''}`} />
                      <span className="text-[10px] font-black uppercase tracking-widest">{s.label}</span>
                    </button>
                  ))}
                </div>
              </section>
            </div>

            {/* Сообщения / Хедеры */}
            <section className="bg-[#111] border border-zinc-800 p-10 rounded-[3rem] space-y-8 shadow-xl">
              <h2 className="text-sm font-black text-white uppercase tracking-widest flex items-center gap-3"><TypeIcon className="w-4 h-4 text-blue-500" /> Настройка заголовков сообщений</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div>
                  <label className="text-[9px] font-black text-zinc-500 uppercase ml-2">Приветственное сообщение</label>
                  <textarea className="w-full mt-3 bg-black border border-zinc-800 p-5 rounded-2xl text-zinc-300 text-xs min-h-[100px] outline-none focus:border-blue-500" value={localBot.welcomeMessage || ''} onChange={e => handleFieldChange({ welcomeMessage: e.target.value })} />
                </div>
                <div className="space-y-6">
                  <div>
                    <label className="text-[9px] font-black text-zinc-500 uppercase ml-2">Заголовок 1-го сообщения</label>
                    <input className="w-full mt-3 bg-black border border-zinc-800 p-4 rounded-xl text-zinc-300 text-xs outline-none focus:border-blue-500" value={safeSettings.firstMessageHeader} onChange={e => updateSetting('firstMessageHeader', e.target.value)} />
                  </div>
                  <div>
                    <label className="text-[9px] font-black text-zinc-500 uppercase ml-2">Заголовок заявки</label>
                    <input className="w-full mt-3 bg-black border border-zinc-800 p-4 rounded-xl text-zinc-300 text-xs outline-none focus:border-blue-500" value={safeSettings.ticketMessageHeader} onChange={e => updateSetting('ticketMessageHeader', e.target.value)} />
                  </div>
                </div>
              </div>
            </section>
          </div>
        )}

        {activeTab === 'interface' && (
          <div className="space-y-8">
            <div className="flex justify-between items-center bg-zinc-900/30 p-8 rounded-[2rem] border border-zinc-800/50">
              <div>
                <h2 className="text-2xl font-black text-white uppercase tracking-tighter">Кнопки меню</h2>
                <p className="text-[10px] font-bold text-zinc-500 uppercase mt-1">Нижнее меню бота (Reply Keyboard)</p>
              </div>
              <button onClick={() => handleFieldChange({ buttons: [...localBot.buttons, { text: 'Новая кнопка', response: 'Ответ...', type: 'message' }] })} className="px-8 py-4 bg-blue-600 hover:bg-blue-500 text-white rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all shadow-lg shadow-blue-600/20 flex items-center gap-3">
                <Plus size={16} /> Добавить кнопку
              </button>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
              {localBot.buttons.map((btn, i) => (
                <div key={i} className="bg-[#111] border border-zinc-800 rounded-[2.5rem] p-8 space-y-6 relative group hover:border-blue-500/40 transition-all">
                  <button onClick={() => handleFieldChange({ buttons: localBot.buttons.filter((_, idx) => idx !== i) })} className="absolute top-6 right-6 text-zinc-600 hover:text-red-500 transition-colors p-2 bg-black rounded-xl border border-zinc-800"><X size={14} /></button>
                  <div>
                    <label className="text-[8px] font-black text-zinc-600 uppercase tracking-widest ml-1">Текст на кнопке</label>
                    <input className="w-full mt-2 bg-black border border-zinc-800 p-4 rounded-xl text-white font-bold text-xs outline-none focus:border-blue-500" value={btn.text} onChange={e => {
                      const nb = [...localBot.buttons]; nb[i] = { ...nb[i], text: e.target.value };
                      handleFieldChange({ buttons: nb });
                    }} />
                  </div>
                  <div>
                    <label className="text-[8px] font-black text-zinc-600 uppercase tracking-widest ml-1">Тип действия</label>
                    <select className="w-full mt-2 bg-black border border-zinc-800 p-4 rounded-xl text-white font-bold text-[10px] uppercase outline-none" value={btn.type || 'message'} onChange={e => {
                      const nb = [...localBot.buttons]; nb[i] = { ...nb[i], type: e.target.value as any };
                      handleFieldChange({ buttons: nb });
                    }}>
                      <option value="message">💬 Текст</option>
                      <option value="ticket">🆘 Тикет (Заявка)</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-[8px] font-black text-zinc-600 uppercase tracking-widest ml-1">Ответ</label>
                    <textarea className="w-full mt-2 bg-black border border-zinc-800 p-4 rounded-xl text-zinc-400 text-[11px] font-medium min-h-[100px] resize-none outline-none" value={btn.response} onChange={e => {
                      const nb = [...localBot.buttons]; nb[i] = { ...nb[i], response: e.target.value };
                      handleFieldChange({ buttons: nb });
                    }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'logic' && (
          <div className="space-y-8">
            <div className="bg-[#111] p-10 rounded-[3rem] border border-zinc-800 flex flex-col md:flex-row justify-between items-center gap-6 shadow-xl">
              <div className="flex gap-6 items-center">
                <div className="w-16 h-16 bg-blue-600/10 rounded-2xl flex items-center justify-center text-blue-500 border border-blue-500/20"><Zap size={32} /></div>
                <div>
                  <h2 className="text-2xl font-black text-white uppercase tracking-tighter">Авто-ответы</h2>
                  <p className="text-[10px] font-bold text-zinc-500 uppercase mt-1">Триггеры на входящие ключевые слова</p>
                </div>
              </div>
              <button onClick={() => handleFieldChange({ triggers: [...localBot.triggers, { keyword: 'цена', response: 'Наши тарифы...', mode: 'contains' }] })} className="px-10 py-5 bg-white text-black rounded-2xl text-[10px] font-black uppercase tracking-widest hover:bg-zinc-200 transition-all shadow-2xl">+ Новый триггер</button>
            </div>
            
            <div className="grid grid-cols-1 gap-4">
              {localBot.triggers.map((trig, i) => (
                <div key={i} className="bg-[#111] border border-zinc-800 rounded-3xl p-6 flex flex-col lg:flex-row gap-6 items-center hover:border-zinc-700 transition-all">
                   <div className="w-full lg:w-1/4">
                      <label className="text-[8px] font-black text-zinc-600 uppercase tracking-widest mb-2 block ml-1">Ключевое слово</label>
                      <input className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-blue-500 font-bold text-xs outline-none" value={trig.keyword} onChange={e => {
                        const nt = [...localBot.triggers]; nt[i] = { ...nt[i], keyword: e.target.value };
                        handleFieldChange({ triggers: nt });
                      }} />
                   </div>
                   <div className="w-full lg:flex-1">
                      <label className="text-[8px] font-black text-zinc-600 uppercase tracking-widest mb-2 block ml-1">Текст авто-ответа</label>
                      <input className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-zinc-300 text-xs outline-none" value={trig.response} onChange={e => {
                        const nt = [...localBot.triggers]; nt[i] = { ...nt[i], response: e.target.value };
                        handleFieldChange({ triggers: nt });
                      }} />
                   </div>
                   <button onClick={() => handleFieldChange({ triggers: localBot.triggers.filter((_, idx) => idx !== i) })} className="p-4 bg-red-500/10 text-red-500 rounded-xl hover:bg-red-500/20 transition-all"><X size={20} /></button>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'logs' && <BotConsole botId={localBot.id} />}
        {activeTab === 'stats' && <BotStatsView stats={localBot.stats} />}
        
        {activeTab === 'chat' && (
          <div className="bg-[#111] border border-zinc-800 rounded-[2.5rem] h-[700px] flex flex-col p-8 shadow-2xl relative overflow-hidden">
            <h2 className="text-sm font-black text-white uppercase mb-6 flex items-center gap-2"><MessageSquare className="w-4 h-4 text-blue-500" /> CRM Chat Log</h2>
            <div className="flex-1 overflow-y-auto no-scrollbar space-y-6 pr-4">
              {messages.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-32 opacity-20">
                   <MessageSquare size={64} className="mb-4" />
                   <p className="uppercase text-[10px] font-black tracking-widest">История пуста</p>
                </div>
              ) : messages.map((m, i) => (
                <div key={i} className={`flex gap-4 items-start ${m.is_admin ? 'flex-row-reverse text-right' : ''}`}>
                   <div className={`p-5 rounded-3xl max-w-[75%] text-sm shadow-lg ${m.is_admin ? 'bg-blue-600 text-white rounded-tr-none' : 'bg-black/60 border border-zinc-800 text-zinc-300 rounded-tl-none'}`}>
                      <p className="text-[9px] font-black uppercase opacity-40 mb-2">{m.user?.name || 'User'} | {new Date(m.timestamp).toLocaleTimeString()}</p>
                      <div className="leading-relaxed whitespace-pre-wrap font-medium">{m.text}</div>
                   </div>
                </div>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  );
};

export default BotEditor;
