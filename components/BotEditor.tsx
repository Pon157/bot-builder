
import React, { useState, useEffect } from 'react';
import { BotConfig, BotStatus } from '../types';
import { api } from '../services/apiService';
import BotConsole from './BotConsole';
import BotStatsView from './BotStatsView';
import { 
  Settings, Cpu, BarChart3, Terminal, X, Save, Power, 
  Ticket, Plus, MessageSquare, User, CheckSquare, 
  Square, Zap, Bell, Shield, Sliders, Layout, ShieldAlert
} from 'lucide-react';

interface BotEditorProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
  onDelete: () => void;
}

const BotEditor: React.FC<BotEditorProps> = ({ bot, onUpdate, onDelete }) => {
  const [activeTab, setActiveTab] = useState<'settings' | 'logic' | 'interface' | 'logs' | 'stats' | 'chat'>('settings');
  const [isProcessing, setIsProcessing] = useState(false);
  const [messages, setMessages] = useState<any[]>([]);

  const defaultSettings = {
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
    notifyOnBlock: true
  };

  const safeSettings = { ...defaultSettings, ...(bot.settings || {}) };

  useEffect(() => {
    if (activeTab === 'chat') api.getBotMessages(bot.id).then(setMessages);
  }, [activeTab, bot.id]);

  const handleToggleServer = async () => {
    if (isProcessing) return;
    setIsProcessing(true);
    try {
      if (bot.status === BotStatus.RUNNING) {
        await api.stopBotOnServer(bot.id);
        onUpdate({ ...bot, status: BotStatus.IDLE });
      } else {
        await api.saveBot(bot.owner_id, bot);
        if (await api.startBotOnServer(bot) === true) onUpdate({ ...bot, status: BotStatus.RUNNING });
      }
    } catch (e: any) { alert("Ошибка сервера: " + e.message); }
    finally { setIsProcessing(false); }
  };

  const save = async () => {
    setIsProcessing(true);
    try {
      await api.saveBot(bot.owner_id, bot);
      alert("Сохранено!");
    } catch (e: any) { alert("Ошибка!"); }
    finally { setIsProcessing(false); }
  };

  const handleDelete = () => {
    if (window.confirm(`Вы действительно хотите удалить инстанс "${bot.name}"? Это действие необратимо.`)) {
      onDelete();
    }
  };

  const toggleSetting = (key: keyof typeof defaultSettings) => {
    onUpdate({
      ...bot,
      settings: {
        ...safeSettings,
        [key]: !safeSettings[key]
      }
    });
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-20">
      <header className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] flex flex-col md:flex-row justify-between items-center gap-6 shadow-xl relative overflow-hidden">
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
           <button onClick={save} disabled={isProcessing} className="px-6 py-4 bg-zinc-800 text-white rounded-2xl text-[10px] font-bold uppercase tracking-widest hover:bg-zinc-700 flex items-center gap-2 transition-all shadow-lg">
             <Save className="w-4 h-4" /> Сохранить изменения
           </button>
           <button onClick={handleToggleServer} disabled={isProcessing} className={`px-10 py-4 rounded-2xl font-black text-xs uppercase tracking-widest transition-all flex items-center gap-2 shadow-lg ${bot.status === BotStatus.RUNNING ? 'bg-red-500/10 text-red-500 border border-red-500/20' : 'bg-blue-600 text-white shadow-blue-600/20'}`}>
             <Power className="w-4 h-4" /> {bot.status === BotStatus.RUNNING ? 'Остановить' : 'Запустить'}
           </button>
        </div>
      </header>

      <div className="flex gap-2 border-b border-zinc-800 overflow-x-auto no-scrollbar">
        {[
          {id: 'settings', label: 'Система', icon: Settings},
          {id: 'interface', label: 'Конструктор Меню', icon: Ticket},
          {id: 'logic', label: 'Авто-ответы', icon: Zap},
          {id: 'chat', label: 'История диалогов', icon: MessageSquare},
          {id: 'stats', label: 'CRM & Аналитика', icon: BarChart3},
          {id: 'logs', label: 'Лог событий', icon: Terminal}
        ].map((t) => (
          <button key={t.id} onClick={() => setActiveTab(t.id as any)} className={`px-6 py-4 text-[10px] font-black uppercase tracking-widest border-b-2 transition-all flex items-center gap-2 whitespace-nowrap ${activeTab === t.id ? 'border-blue-500 text-blue-500' : 'border-transparent text-zinc-500 hover:text-zinc-300'}`}>
            <t.icon className="w-3.5 h-3.5" /> {t.label}
          </button>
        ))}
      </div>

      <div className="min-h-[400px]">
        {activeTab === 'settings' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-8">
              <section>
                <h2 className="text-sm font-black text-white uppercase flex items-center gap-2 mb-6">
                  <Sliders className="w-4 h-4 text-blue-500" /> Основная конфигурация
                </h2>
                <div className="space-y-5">
                  <label className="block">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">Telegram Bot Token</span>
                    <input type="password" placeholder="Токен из @BotFather" className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white font-mono focus:border-blue-500 outline-none transition-all" value={bot.token} onChange={e => onUpdate({...bot, token: e.target.value})} />
                  </label>
                  <label className="block">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">ID Администратора / Группы</span>
                    <input type="text" placeholder="ID или @username группы" className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white focus:border-blue-500 outline-none transition-all" value={bot.adminChatId} onChange={e => onUpdate({...bot, adminChatId: e.target.value})} />
                  </label>
                  <label className="block">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">Приветствие (/start)</span>
                    <textarea className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white min-h-[100px] focus:border-blue-500 outline-none transition-all resize-none text-xs" value={bot.welcomeMessage || ""} onChange={e => onUpdate({...bot, welcomeMessage: e.target.value})} />
                  </label>
                </div>
              </section>

              <section>
                <h2 className="text-sm font-black text-white uppercase flex items-center gap-2 mb-6">
                  <Layout className="w-4 h-4 text-emerald-500" /> Настройка заголовка сообщений
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <button onClick={() => toggleSetting('showHeaderName')} className={`flex items-center justify-between p-4 rounded-xl border text-[9px] font-bold uppercase transition-all ${safeSettings.showHeaderName ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-black border-zinc-800 text-zinc-600'}`}>
                    Имя {safeSettings.showHeaderName ? <CheckSquare className="w-3 h-3" /> : <Square className="w-3 h-3" />}
                  </button>
                  <button onClick={() => toggleSetting('showHeaderUsername')} className={`flex items-center justify-between p-4 rounded-xl border text-[9px] font-bold uppercase transition-all ${safeSettings.showHeaderUsername ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-black border-zinc-800 text-zinc-600'}`}>
                    Юзер {safeSettings.showHeaderUsername ? <CheckSquare className="w-3 h-3" /> : <Square className="w-3 h-3" />}
                  </button>
                  <button onClick={() => toggleSetting('showHeaderId')} className={`flex items-center justify-between p-4 rounded-xl border text-[9px] font-bold uppercase transition-all ${safeSettings.showHeaderId ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-black border-zinc-800 text-zinc-600'}`}>
                    ID {safeSettings.showHeaderId ? <CheckSquare className="w-3 h-3" /> : <Square className="w-3 h-3" />}
                  </button>
                </div>
              </section>
            </div>
            
            <div className="space-y-8">
                <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
                    <h3 className="text-sm font-black text-white uppercase flex items-center gap-2">
                      <ShieldAlert className="w-4 h-4 text-emerald-500" /> Темы и Управление топиками
                    </h3>
                    <div className="space-y-4">
                        <button onClick={() => toggleSetting('useTopics')} className={`w-full flex items-center justify-between p-5 rounded-2xl border transition-all ${safeSettings.useTopics ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-black border-zinc-800 text-zinc-600'}`}>
                            <div className="text-left">
                                <p className="text-xs font-bold">Использовать топики</p>
                                <p className="text-[9px] font-bold uppercase opacity-50">Для групп с Forum Enable</p>
                            </div>
                            {safeSettings.useTopics ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                        </button>
                        <button onClick={() => toggleSetting('topicPerRequest')} className={`w-full flex items-center justify-between p-5 rounded-2xl border transition-all ${safeSettings.topicPerRequest ? 'bg-blue-500/10 border-blue-500/30 text-blue-400' : 'bg-black border-zinc-800 text-zinc-600'}`}>
                            <div className="text-left">
                                <p className="text-xs font-bold">Новый топик на каждое обращение</p>
                                <p className="text-[9px] font-bold uppercase opacity-50">Создавать новый чат при /start или кнопке</p>
                            </div>
                            {safeSettings.topicPerRequest ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                        </button>
                    </div>
                </div>

                <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
                    <h3 className="text-sm font-black text-white uppercase flex items-center gap-2">
                      <Bell className="w-4 h-4 text-amber-500" /> Системные уведомления
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <button onClick={() => toggleSetting('notifyOnStart')} className={`flex items-center justify-between p-4 rounded-xl border text-[9px] font-bold uppercase transition-all ${safeSettings.notifyOnStart ? 'bg-amber-500/10 border-amber-500/30 text-amber-400' : 'bg-black border-zinc-800 text-zinc-600'}`}>
                           Новый юзер {safeSettings.notifyOnStart ? <CheckSquare className="w-3 h-3" /> : <Square className="w-3 h-3" />}
                        </button>
                        <button onClick={() => toggleSetting('notifyOnBlock')} className={`flex items-center justify-between p-4 rounded-xl border text-[9px] font-bold uppercase transition-all ${safeSettings.notifyOnBlock ? 'bg-amber-500/10 border-amber-500/30 text-amber-400' : 'bg-black border-zinc-800 text-zinc-600'}`}>
                           Блокировка {safeSettings.notifyOnBlock ? <CheckSquare className="w-3 h-3" /> : <Square className="w-3 h-3" />}
                        </button>
                    </div>
                </div>

                <div className="p-8 bg-red-500/5 border border-red-500/10 rounded-[2.5rem] flex flex-col items-center">
                    <button onClick={handleDelete} className="text-[10px] font-black uppercase text-red-500 hover:underline">Удалить инстанс безвозвратно</button>
                </div>
            </div>
          </div>
        )}
        
        {activeTab === 'interface' && (
          <div className="space-y-6">
             <div className="flex justify-between items-center mb-4">
                <h2 className="text-xl font-black text-white uppercase tracking-tight">Нижнее меню бота</h2>
                <button onClick={() => onUpdate({...bot, buttons: [...(bot.buttons || []), {text: '', response: '', type: 'message'}]})} className="bg-blue-600 hover:bg-blue-700 px-8 py-4 rounded-2xl text-[11px] font-black text-white uppercase flex items-center gap-2 transition-all shadow-lg shadow-blue-600/20">
                    <Plus className="w-4 h-4" /> Добавить кнопку
                </button>
             </div>
             <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
               {(bot.buttons || []).map((btn, i) => (
                 <div key={i} className="bg-[#0d0d0d] border border-zinc-800 rounded-[2.5rem] p-8 space-y-6 relative group hover:border-zinc-700 transition-all">
                    <button onClick={() => onUpdate({...bot, buttons: bot.buttons.filter((_, idx) => idx !== i)})} className="absolute top-6 right-6 text-zinc-600 hover:text-red-500 transition-colors">
                      <X className="w-5 h-5" />
                    </button>
                    <div className="space-y-4">
                        <div className="space-y-2">
                          <span className="text-[9px] font-bold text-zinc-600 uppercase ml-2">Текст на кнопке</span>
                          <input placeholder="Напр: 🆘 Поддержка" className="w-full bg-black border border-zinc-800 p-5 rounded-2xl text-white text-sm font-black outline-none focus:border-blue-500" value={btn.text} onChange={e => { const nb = [...bot.buttons]; nb[i].text = e.target.value; onUpdate({...bot, buttons: nb}); }} />
                        </div>
                        <div className="space-y-2">
                          <span className="text-[9px] font-bold text-zinc-600 uppercase ml-2">Действие / Ответ бота</span>
                          <textarea placeholder="Текст, который увидит пользователь..." className="w-full bg-black border border-zinc-800 p-5 rounded-2xl text-white text-sm min-h-[120px] outline-none resize-none focus:border-blue-500" value={btn.response} onChange={e => { const nb = [...bot.buttons]; nb[i].response = e.target.value; onUpdate({...bot, buttons: nb}); }} />
                        </div>
                        <div className="flex items-center gap-4 bg-zinc-900/50 p-4 rounded-2xl border border-zinc-800">
                             <span className="text-[9px] font-bold text-zinc-500 uppercase">Режим:</span>
                             <div className="flex gap-2">
                               {['message', 'request'].map(type => (
                                 <button 
                                  key={type}
                                  onClick={() => { const nb = [...bot.buttons]; nb[i].type = type as any; onUpdate({...bot, buttons: nb}); }}
                                  className={`px-3 py-1.5 rounded-lg text-[9px] font-black uppercase transition-all ${btn.type === type ? 'bg-blue-600 text-white' : 'bg-black text-zinc-500'}`}
                                 >
                                   {type === 'message' ? 'Просто ответ' : 'Создать тикет'}
                                 </button>
                               ))}
                             </div>
                        </div>
                    </div>
                 </div>
               ))}
             </div>
          </div>
        )}

        {activeTab === 'logic' && (
          <div className="space-y-6">
            <div className="flex justify-between items-end mb-4">
               <h2 className="text-xl font-black text-white uppercase">Ключевые слова</h2>
               <button onClick={() => onUpdate({...bot, triggers: [...(bot.triggers || []), {keyword: '', response: ''}]})} className="bg-blue-600 px-6 py-4 rounded-2xl text-[10px] font-black text-white uppercase tracking-widest flex items-center gap-2">
                  <Plus className="w-4 h-4" /> Новый триггер
               </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
               {(bot.triggers || []).map((trig, i) => (
                 <div key={i} className="bg-[#0d0d0d] border border-zinc-800 rounded-[2.5rem] p-8 space-y-5 relative group hover:border-zinc-700 transition-all">
                    <button onClick={() => onUpdate({...bot, triggers: bot.triggers.filter((_, idx) => idx !== i)})} className="absolute top-6 right-6 text-zinc-600 hover:text-red-500">
                      <X className="w-5 h-5" />
                    </button>
                    <div className="space-y-2">
                      <span className="text-[9px] font-bold text-zinc-600 uppercase ml-2">Слово-активатор</span>
                      <input placeholder="Напр: тарифы" className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-white text-sm font-bold outline-none focus:border-blue-500" value={trig.keyword} onChange={e => { const nt = [...bot.triggers]; nt[i].keyword = e.target.value; onUpdate({...bot, triggers: nt}); }} />
                    </div>
                    <div className="space-y-2">
                      <span className="text-[9px] font-bold text-zinc-600 uppercase ml-2">Ответ системы</span>
                      <textarea placeholder="Текст ответа..." className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-white text-sm outline-none min-h-[100px] resize-none focus:border-blue-500" value={trig.response} onChange={e => { const nt = [...bot.triggers]; nt[i].response = e.target.value; onUpdate({...bot, triggers: nt}); }} />
                    </div>
                 </div>
               ))}
            </div>
          </div>
        )}

        {activeTab === 'chat' && (
            <div className="bg-[#111] border border-zinc-800 rounded-[2.5rem] overflow-hidden flex flex-col h-[650px] shadow-2xl">
                <div className="p-6 border-b border-zinc-800 flex justify-between items-center bg-zinc-900/40">
                    <h2 className="text-sm font-black text-white uppercase flex items-center gap-2">
                        <MessageSquare className="w-4 h-4 text-blue-500" /> Последние события в чате
                    </h2>
                </div>
                <div className="flex-1 overflow-y-auto p-8 space-y-6 no-scrollbar bg-[radial-gradient(circle_at_bottom_left,_var(--tw-gradient-stops))] from-blue-500/5 via-transparent to-transparent">
                    {messages.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-full opacity-20">
                            <MessageSquare className="w-16 h-16 mb-4" />
                            <p className="text-xs font-black uppercase tracking-widest">История пуста</p>
                        </div>
                    ) : messages.map((m, i) => (
                        <div key={i} className={`flex gap-5 items-start animate-in slide-in-from-bottom-2 ${m.is_admin ? 'flex-row-reverse' : ''}`}>
                            <div className={`w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 border-2 ${m.is_admin ? 'bg-blue-600 border-blue-400 text-white' : 'bg-zinc-900 border-zinc-800 text-zinc-400'}`}>
                                {m.is_admin ? <Shield className="w-6 h-6" /> : <User className="w-6 h-6" />}
                            </div>
                            <div className={`flex-1 max-w-[80%] space-y-2 ${m.is_admin ? 'text-right' : ''}`}>
                                <div className={`flex items-center gap-3 ${m.is_admin ? 'flex-row-reverse' : ''}`}>
                                    <span className="text-xs font-black text-white">{m.user?.name || "Пользователь"}</span>
                                    <span className="text-[9px] text-zinc-600 font-bold uppercase">{new Date(m.timestamp).toLocaleTimeString()}</span>
                                </div>
                                <div className={`p-5 rounded-3xl text-sm leading-relaxed shadow-lg ${m.is_admin ? 'bg-blue-600 text-white rounded-tr-none' : 'bg-black/60 border border-zinc-800 text-zinc-300 rounded-tl-none'}`}>
                                    {m.text}
                                </div>
                            </div>
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
