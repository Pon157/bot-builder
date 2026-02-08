
import React, { useState, useEffect } from 'react';
import { BotConfig, BotStatus } from '../types';
import { api } from '../services/apiService';
import BotConsole from './BotConsole';
import BotStatsView from './BotStatsView';
import { 
  Settings, Cpu, BarChart3, Terminal, X, Save, Power, 
  Ticket, Plus, MessageSquare, User, CheckSquare, 
  Square, Zap, Bell, Shield, Sliders, Layout, ShieldAlert, Lock, Trash2, ShieldCheck, AlertCircle, Type as TypeIcon
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
  const [messages, setMessages] = useState<any[]>([]);

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

  useEffect(() => {
    if (activeTab === 'chat') {
        api.getBotMessages(bot.id).then(setMessages).catch(() => setMessages([]));
    }
  }, [activeTab, bot.id]);

  const handleToggleServer = async () => {
    setIsProcessing(true);
    try {
      if (bot.status === BotStatus.RUNNING) {
        await api.stopBotOnServer(bot.id);
        onUpdate({ ...bot, status: BotStatus.IDLE });
      } else {
        // При запуске всегда сначала сохраняем конфиг
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

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-20">
      {hasUnsavedChanges && (
        <div className="fixed bottom-10 left-1/2 -translate-x-1/2 z-[100] bg-blue-600 text-white px-8 py-4 rounded-2xl shadow-2xl flex items-center gap-4 animate-bounce">
            <AlertCircle className="w-5 h-5" />
            <span className="text-xs font-black uppercase tracking-widest">Несохраненные изменения!</span>
            <button onClick={syncState} disabled={isProcessing} className="bg-white text-blue-600 px-4 py-1.5 rounded-xl font-black text-[10px] uppercase">Сохранить</button>
        </div>
      )}

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

      <div className="flex gap-2 border-b border-zinc-800 overflow-x-auto no-scrollbar">
        {[
          {id: 'settings', label: 'Основные', icon: Settings},
          {id: 'interface', label: 'Меню (Кнопки)', icon: Ticket},
          {id: 'logic', label: 'Триггеры', icon: Zap},
          {id: 'stats', label: 'Аналитика', icon: BarChart3},
          {id: 'logs', label: 'Терминал', icon: Terminal}
        ].map((t) => (
          <button key={t.id} onClick={() => setActiveTab(t.id as any)} className={`px-6 py-4 text-[10px] font-black uppercase tracking-widest border-b-2 transition-all flex items-center gap-2 whitespace-nowrap ${activeTab === t.id ? 'border-blue-500 text-blue-500' : 'border-transparent text-zinc-500'}`}>
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

        {activeTab === 'chat' && (
          <div className="bg-[#111] border border-zinc-800 rounded-[2.5rem] h-[700px] overflow-hidden flex flex-col p-8 shadow-2xl relative">
            <h2 className="text-sm font-black text-white uppercase mb-6 flex items-center gap-2"><MessageSquare className="w-4 h-4 text-blue-500" /> CRM История сообщений</h2>
            <div className="flex-1 overflow-y-auto no-scrollbar space-y-6 pr-4">
              {messages.length === 0 ? <p className="text-center text-zinc-700 py-32 uppercase text-[10px] font-black tracking-widest opacity-20">История пуста</p> : messages.map((m, i) => (
                <div key={i} className={`flex gap-4 items-start ${m.is_admin ? 'flex-row-reverse text-right' : ''} animate-in slide-in-from-bottom-2 duration-300`}>
                   <div className={`p-5 rounded-3xl max-w-[75%] text-sm shadow-lg ${m.is_admin ? 'bg-blue-600 text-white rounded-tr-none' : 'bg-black/60 border border-zinc-800 text-zinc-300 rounded-tl-none'}`}>
                      <p className="text-[9px] font-black uppercase opacity-40 mb-2">{m.user?.name} | {new Date(m.timestamp).toLocaleTimeString()}</p>
                      <div className="leading-relaxed whitespace-pre-wrap">{m.text}</div>
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
