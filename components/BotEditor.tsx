
import React, { useState, useEffect } from 'react';
import { BotConfig, BotStatus } from '../types';
import { api } from '../services/apiService';
import BotConsole from './BotConsole';
import BotStatsView from './BotStatsView';
import { Settings, Cpu, MousePointer2, BarChart3, Terminal, X, Save, Power, Ticket, Plus, MessageSquare, User, CheckSquare, Square } from 'lucide-react';

interface BotEditorProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
  onDelete: () => void;
}

const BotEditor: React.FC<BotEditorProps> = ({ bot, onUpdate, onDelete }) => {
  const [activeTab, setActiveTab] = useState<'settings' | 'logic' | 'interface' | 'logs' | 'stats' | 'chat'>('settings');
  const [isProcessing, setIsProcessing] = useState(false);
  const [messages, setMessages] = useState<any[]>([]);

  useEffect(() => {
    if (activeTab === 'chat') api.getBotMessages(bot.id).then(setMessages);
  }, [activeTab, bot.id]);

  // Fix: Provide a complete default object for settings to satisfy BotConfig type requirements
  const safeSettings = bot.settings || {
    useTopics: false,
    topicPerRequest: false,
    anonymousTopics: false,
    forwardToAdmin: true,
    antiSpam: true,
    showUserInfo: true,
    showUsername: true,
    autoApproveJoin: false,
    rateLimit: 15,
    autoBanThreshold: 0,
    adminMessageTemplate: "",
    showHeaderId: true,
    showHeaderName: true,
    showHeaderUsername: true
  };

  const handleToggleServer = async () => {
    if (isProcessing) return;
    setIsProcessing(true);
    try {
      if (bot.status === BotStatus.RUNNING) {
        await api.stopBotOnServer(bot.id);
        onUpdate({ ...bot, status: BotStatus.IDLE });
      } else {
        await api.saveBot(bot.owner_id, bot);
        const result = await api.startBotOnServer(bot);
        if (result === true) onUpdate({ ...bot, status: BotStatus.RUNNING });
        else alert("Ошибка: " + result);
      }
    } catch (e: any) { alert("Ошибка сервера: " + e.message); }
    finally { setIsProcessing(false); }
  };

  const save = async () => {
    setIsProcessing(true);
    try {
      await api.saveBot(bot.owner_id, bot);
      alert("Конфигурация сохранена!");
    } catch (e: any) { alert("Ошибка при сохранении!"); }
    finally { setIsProcessing(false); }
  };

  const toggleSetting = (key: string) => {
    onUpdate({
      ...bot,
      settings: { ...safeSettings, [key]: !(safeSettings as any)[key] }
    });
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-20">
      <header className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] flex flex-col md:flex-row justify-between items-center gap-6 shadow-xl relative overflow-hidden">
        <div className="flex items-center gap-6 relative z-10">
          <div className={`w-16 h-16 rounded-2xl flex items-center justify-center border-2 ${bot.status === BotStatus.RUNNING ? 'bg-green-500/10 border-green-500/30 text-green-500' : 'bg-zinc-900 border-zinc-800 text-zinc-600'}`}>
            <Cpu className="w-8 h-8" />
          </div>
          <div>
            <h1 className="text-3xl font-black text-white">{bot.name}</h1>
            <div className="flex items-center gap-2 mt-1">
              <span className={`w-2 h-2 rounded-full ${bot.status === BotStatus.RUNNING ? 'bg-green-500 animate-pulse' : 'bg-zinc-600'}`}></span>
              <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{bot.status}</span>
            </div>
          </div>
        </div>
        <div className="flex gap-4 relative z-10">
           <button onClick={save} disabled={isProcessing} className="px-6 py-4 bg-zinc-800 text-white rounded-2xl text-[10px] font-bold uppercase tracking-widest hover:bg-zinc-700 flex items-center gap-2 transition-all shadow-lg">
             <Save className="w-4 h-4" /> Сохранить
           </button>
           <button onClick={handleToggleServer} disabled={isProcessing} className={`px-10 py-4 rounded-2xl font-black text-xs uppercase tracking-widest transition-all flex items-center gap-2 shadow-lg ${bot.status === BotStatus.RUNNING ? 'bg-red-500/10 text-red-500 border border-red-500/20' : 'bg-blue-600 text-white shadow-blue-600/20'}`}>
             <Power className="w-4 h-4" /> {bot.status === BotStatus.RUNNING ? 'Остановить' : 'Запустить'}
           </button>
        </div>
      </header>

      <div className="flex gap-2 border-b border-zinc-800 overflow-x-auto no-scrollbar">
        {[
          {id: 'settings', label: 'Настройки', icon: Settings},
          {id: 'interface', label: 'Меню', icon: Ticket},
          {id: 'logic', label: 'Триггеры', icon: MousePointer2},
          {id: 'chat', label: 'Диалоги', icon: MessageSquare},
          {id: 'stats', label: 'Статистика', icon: BarChart3},
          {id: 'logs', label: 'Консоль', icon: Terminal}
        ].map((t) => (
          <button key={t.id} onClick={() => setActiveTab(t.id as any)} className={`px-6 py-4 text-[10px] font-black uppercase tracking-widest border-b-2 transition-all flex items-center gap-2 whitespace-nowrap ${activeTab === t.id ? 'border-blue-500 text-blue-500' : 'border-transparent text-zinc-500 hover:text-zinc-300'}`}>
            <t.icon className="w-3.5 h-3.5" /> {t.label}
          </button>
        ))}
      </div>

      <div className="min-h-[400px]">
        {activeTab === 'settings' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
              <h2 className="text-xl font-black text-white uppercase tracking-tighter">Конфигурация API</h2>
              <div className="space-y-5">
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">Telegram Bot Token</span>
                  <input type="password" className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white font-mono focus:border-blue-500/50 outline-none transition-all" value={bot.token} onChange={e => onUpdate({...bot, token: e.target.value})} />
                </label>
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">ID Администратора</span>
                  <input type="text" className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white focus:border-blue-500/50 outline-none transition-all" value={bot.adminChatId} onChange={e => onUpdate({...bot, adminChatId: e.target.value})} />
                </label>
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">Шаблон уведомления</span>
                  <textarea className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white min-h-[100px] outline-none text-xs" value={safeSettings.adminMessageTemplate} onChange={e => onUpdate({...bot, settings: {...safeSettings, adminMessageTemplate: e.target.value}})} placeholder="👤 {{name}}\n🆔 {{id}}\n💬 {{text}}" />
                </label>
              </div>

              <div className="pt-6 border-t border-zinc-800 grid grid-cols-3 gap-3">
                  {[
                    { key: 'showHeaderId', label: 'ID' },
                    { key: 'showHeaderName', label: 'Имя' },
                    { key: 'showHeaderUsername', label: 'Login' }
                  ].map(item => (
                    <button key={item.key} onClick={() => toggleSetting(item.key)} className={`flex items-center gap-2 p-3 rounded-xl border transition-all ${(safeSettings as any)[item.key] ? 'bg-blue-600/10 border-blue-500/30 text-blue-500' : 'bg-black border-zinc-800 text-zinc-600'}`}>
                        {(safeSettings as any)[item.key] ? <CheckSquare className="w-3.5 h-3.5" /> : <Square className="w-3.5 h-3.5" />}
                        <span className="text-[9px] font-bold uppercase">{item.label}</span>
                    </button>
                  ))}
              </div>
            </div>
            
            <div className="space-y-6">
                <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-4">
                    <h3 className="text-xs font-black text-white uppercase">Функции модерации</h3>
                    <label className="flex items-center justify-between p-4 bg-black rounded-2xl border border-zinc-800 cursor-pointer">
                        <span className="text-xs font-bold text-zinc-400 uppercase">Режим Форума (Топики)</span>
                        <input type="checkbox" checked={safeSettings.useTopics} onChange={e => onUpdate({...bot, settings: {...safeSettings, useTopics: e.target.checked}})} />
                    </label>
                    <label className="flex items-center justify-between p-4 bg-black rounded-2xl border border-zinc-800 cursor-pointer">
                        <span className="text-xs font-bold text-zinc-400 uppercase tracking-widest">Анонимные топики</span>
                        <input type="checkbox" checked={safeSettings.anonymousTopics} onChange={e => onUpdate({...bot, settings: {...safeSettings, anonymousTopics: e.target.checked}})} />
                    </label>
                </div>
                <button onClick={() => { if(confirm("Удалить?")) { api.deleteBot(bot.owner_id, bot.id).then(onDelete); }}} className="w-full py-5 bg-red-500 hover:bg-red-600 text-white text-[10px] font-black uppercase rounded-2xl transition-all shadow-lg shadow-red-500/20">Удалить бота навсегда</button>
            </div>
          </div>
        )}

        {activeTab === 'interface' && (
          <div className="space-y-6">
             <div className="flex justify-between items-center mb-6">
                <h2 className="text-xl font-black text-white uppercase tracking-tight">Редактор кнопок меню</h2>
                <button onClick={() => onUpdate({...bot, buttons: [...(bot.buttons || []), {text: '', response: '', type: 'message'}]})} className="bg-blue-600 hover:bg-blue-700 px-8 py-3.5 rounded-2xl text-[11px] font-black text-white uppercase flex items-center gap-2 shadow-lg shadow-blue-600/20">
                    <Plus className="w-4 h-4" /> Добавить кнопку
                </button>
             </div>
             <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
               {(bot.buttons || []).map((btn, i) => (
                 <div key={i} className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6 space-y-4 relative group hover:border-zinc-700 transition-all">
                    <button onClick={() => onUpdate({...bot, buttons: bot.buttons.filter((_, idx) => idx !== i)})} className="absolute top-4 right-4 text-zinc-600 hover:text-red-500">
                      <X className="w-4 h-4" />
                    </button>
                    <input placeholder="Название на кнопке" className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-white text-sm font-bold outline-none focus:border-blue-500" value={btn.text} onChange={e => { const nb = [...bot.buttons]; nb[i].text = e.target.value; onUpdate({...bot, buttons: nb}); }} />
                    <textarea placeholder="Ответ бота..." className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-white text-sm min-h-[100px] outline-none resize-none focus:border-blue-500" value={btn.response} onChange={e => { const nb = [...bot.buttons]; nb[i].response = e.target.value; onUpdate({...bot, buttons: nb}); }} />
                 </div>
               ))}
             </div>
          </div>
        )}

        {activeTab === 'logic' && (
          <div className="space-y-6">
            <div className="flex justify-between items-end mb-6">
               <h2 className="text-xl font-black text-white uppercase">Триггеры (Автоответ)</h2>
               <button onClick={() => onUpdate({...bot, triggers: [...(bot.triggers || []), {keyword: '', response: ''}]})} className="bg-blue-600 px-6 py-3.5 rounded-2xl text-[10px] font-black text-white uppercase tracking-widest flex items-center gap-2">
                  <Plus className="w-4 h-4" /> Новый триггер
               </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
               {(bot.triggers || []).map((trig, i) => (
                 <div key={i} className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6 space-y-4 relative group hover:border-zinc-700 transition-all">
                    <button onClick={() => onUpdate({...bot, triggers: bot.triggers.filter((_, idx) => idx !== i)})} className="absolute top-4 right-4 text-zinc-600 hover:text-red-500">
                      <X className="w-4 h-4" />
                    </button>
                    <input placeholder="Слово-ключ" className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-white text-sm font-bold outline-none focus:border-blue-500" value={trig.keyword} onChange={e => { const nt = [...bot.triggers]; nt[i].keyword = e.target.value; onUpdate({...bot, triggers: nt}); }} />
                    <textarea placeholder="Текст автоответа..." className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-white text-sm outline-none min-h-[100px] resize-none focus:border-blue-500" value={trig.response} onChange={e => { const nt = [...bot.triggers]; nt[i].response = e.target.value; onUpdate({...bot, triggers: nt}); }} />
                 </div>
               ))}
            </div>
          </div>
        )}

        {activeTab === 'chat' && (
            <div className="bg-[#111] border border-zinc-800 rounded-[2.5rem] overflow-hidden flex flex-col h-[600px] shadow-2xl">
                <div className="p-6 border-b border-zinc-800 flex justify-between items-center bg-zinc-900/20">
                    <h2 className="text-sm font-black text-white uppercase flex items-center gap-2">
                        <MessageSquare className="w-4 h-4 text-blue-500" /> История диалогов
                    </h2>
                </div>
                <div className="flex-1 overflow-y-auto p-6 space-y-4 no-scrollbar">
                    {messages.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-full opacity-20"><p className="text-[10px] font-black uppercase">Нет данных</p></div>
                    ) : messages.map((m, i) => (
                        <div key={i} className={`flex gap-4 items-start p-5 rounded-3xl border ${m.is_from_admin ? 'bg-blue-600/5 border-blue-500/20 ml-10' : 'bg-black/40 border-zinc-800/50 mr-10'}`}>
                            <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${m.is_from_admin ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400'}`}>
                                {m.is_from_admin ? <Cpu className="w-5 h-5" /> : <User className="w-5 h-5" />}
                            </div>
                            <div className="flex-1 min-w-0">
                                <p className="text-xs font-bold text-white mb-1 truncate">{m.first_name || "User"} <span className="text-[9px] text-zinc-600 ml-2 font-normal">{new Date(m.created_at).toLocaleTimeString()}</span></p>
                                <p className="text-sm text-zinc-300 leading-relaxed break-words">{m.message_text}</p>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        )}
