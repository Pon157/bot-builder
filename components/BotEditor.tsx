
import React, { useState, useEffect, useCallback } from 'react';
import { BotConfig, BotStatus } from '../types';
import { api } from '../services/apiService';
import BotConsole from './BotConsole';
import BotStatsView from './BotStatsView';
import { Settings, Cpu, MousePointer2, BarChart3, Terminal, X, Save, Power, Ticket, Info, Plus, MessageSquare, User, EyeOff, CheckSquare, Square, ShieldAlert, RefreshCw } from 'lucide-react';

interface BotEditorProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
  onDelete: () => void;
}

const BotEditor: React.FC<BotEditorProps> = ({ bot, onUpdate, onDelete }) => {
  const [activeTab, setActiveTab] = useState<'settings' | 'logic' | 'interface' | 'logs' | 'stats' | 'chat'>('settings');
  const [isProcessing, setIsProcessing] = useState(false);
  const [messages, setMessages] = useState<any[]>([]);
  const [lastRefresh, setLastRefresh] = useState(Date.now());

  const refreshBotData = useCallback(async () => {
    try {
        const serverBots = await api.getBots(bot.owner_id);
        const current = serverBots.find(b => b.id === bot.id);
        if (current) {
            // Важно: Не сбрасываем состояние компонента, а просто обновляем данные
            onUpdate(current);
            if (activeTab === 'chat') {
                const msgs = await api.getBotMessages(bot.id);
                setMessages(msgs);
            }
        }
    } catch(e) {}
  }, [bot.id, bot.owner_id, onUpdate, activeTab]);

  useEffect(() => {
    if (activeTab === 'stats' || activeTab === 'chat') {
        const interval = setInterval(refreshBotData, 10000);
        refreshBotData();
        return () => clearInterval(interval);
    }
  }, [activeTab, refreshBotData]);

  const handleToggleServer = async () => {
    if (isProcessing) return;
    setIsProcessing(true);
    try {
      if (bot.status === BotStatus.RUNNING) {
        await api.stopBotOnServer(bot.id);
        onUpdate({ ...bot, status: BotStatus.IDLE });
      } else {
        await api.saveBot(bot.owner_id, bot);
        const res = await api.startBotOnServer(bot);
        if (res === true) onUpdate({ ...bot, status: BotStatus.RUNNING });
        else alert("Ошибка запуска: " + res);
      }
    } catch (e: any) { alert("Ошибка сервера: " + e.message); }
    finally { setIsProcessing(false); }
  };

  const save = async () => {
    setIsProcessing(true);
    try {
      await api.saveBot(bot.owner_id, bot);
      alert("Конфигурация успешно синхронизирована!");
    } catch (e: any) { alert("Ошибка сохранения!"); }
    finally { setIsProcessing(false); }
  };

  const toggleSetting = (key: keyof BotConfig['settings']) => {
    onUpdate({
      ...bot,
      settings: { ...bot.settings, [key]: !bot.settings[key] }
    });
  };

  // Список табов вынесен в константу для надежности рендера
  const tabs = [
    {id: 'settings', label: 'Настройки', icon: Settings},
    {id: 'interface', label: 'Меню', icon: Ticket},
    {id: 'logic', label: 'Триггеры', icon: MousePointer2},
    {id: 'chat', label: 'Сообщения', icon: MessageSquare},
    {id: 'stats', label: 'Аналитика', icon: BarChart3},
    {id: 'logs', label: 'Консоль', icon: Terminal}
  ] as const;

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-20">
      <header className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] flex flex-col md:flex-row justify-between items-center gap-6 shadow-2xl relative overflow-hidden">
        <div className="flex items-center gap-6 relative z-10">
          <div className={`w-16 h-16 rounded-2xl flex items-center justify-center border-2 transition-all ${bot.status === BotStatus.RUNNING ? 'bg-green-500/10 border-green-500/30 text-green-500 shadow-[0_0_20px_rgba(34,197,94,0.1)]' : 'bg-zinc-900 border-zinc-800 text-zinc-600'}`}>
            <Cpu className={`w-8 h-8 ${bot.status === BotStatus.RUNNING ? 'animate-pulse' : ''}`} />
          </div>
          <div>
            <h1 className="text-3xl font-black text-white tracking-tight">{bot.name}</h1>
            <div className="flex items-center gap-2 mt-1">
              <span className={`w-2 h-2 rounded-full ${bot.status === BotStatus.RUNNING ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.8)]' : 'bg-zinc-600'}`}></span>
              <span className="text-[10px] font-black uppercase tracking-widest text-zinc-500">{bot.status}</span>
            </div>
          </div>
        </div>
        <div className="flex gap-4 relative z-10">
           <button onClick={save} disabled={isProcessing} className="px-6 py-4 bg-zinc-800 text-white rounded-2xl text-[10px] font-black uppercase tracking-widest hover:bg-zinc-700 flex items-center gap-2 transition-all border border-zinc-700">
             <Save className="w-4 h-4" /> Сохранить
           </button>
           <button onClick={handleToggleServer} disabled={isProcessing} className={`px-10 py-4 rounded-2xl font-black text-xs uppercase tracking-widest transition-all flex items-center gap-2 shadow-xl ${bot.status === BotStatus.RUNNING ? 'bg-red-500/10 text-red-500 border border-red-500/20' : 'bg-blue-600 text-white shadow-blue-600/30'}`}>
             <Power className="w-4 h-4" /> {bot.status === BotStatus.RUNNING ? 'Остановить' : 'Запустить'}
           </button>
        </div>
      </header>

      <div className="flex gap-1 bg-zinc-900/50 p-1 rounded-2xl border border-zinc-800 overflow-x-auto no-scrollbar scroll-smooth">
        {tabs.map((t) => (
          <button 
            key={t.id} 
            onClick={() => setActiveTab(t.id)} 
            className={`px-6 py-3.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all flex items-center gap-2 whitespace-nowrap ${activeTab === t.id ? 'bg-blue-600 text-white shadow-lg' : 'text-zinc-500 hover:text-zinc-300 hover:bg-white/5'}`}
          >
            <t.icon className="w-3.5 h-3.5" /> {t.label}
          </button>
        ))}
      </div>

      <div className="min-h-[500px]">
        {activeTab === 'settings' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6 shadow-xl">
              <h2 className="text-sm font-black text-white uppercase tracking-widest flex items-center gap-2">
                <Info className="w-4 h-4 text-blue-500" /> Основные данные
              </h2>
              <div className="space-y-5">
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">Telegram Bot Token</span>
                  <input type="password" className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white font-mono focus:border-blue-500 outline-none transition-all" value={bot.token} onChange={e => onUpdate({...bot, token: e.target.value})} />
                </label>
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">ID Администратора</span>
                  <input type="text" className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white focus:border-blue-500 outline-none transition-all" value={bot.adminChatId} onChange={e => onUpdate({...bot, adminChatId: e.target.value})} />
                </label>
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">Приветствие (/start)</span>
                  <textarea className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white min-h-[100px] focus:border-blue-500 outline-none transition-all resize-none text-xs" value={bot.welcomeMessage || ""} onChange={e => onUpdate({...bot, welcomeMessage: e.target.value})} />
                </label>
              </div>
            </div>
            
            <div className="space-y-6">
                <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-4 shadow-xl">
                    <h3 className="text-xs font-black text-white uppercase tracking-widest mb-2 flex items-center gap-2">
                        <ShieldAlert className="w-4 h-4 text-amber-500" /> Функционал
                    </h3>
                    <div className="space-y-3">
                        <div className="p-4 bg-black rounded-2xl border border-zinc-800 space-y-3">
                            <div className="flex items-center justify-between">
                                <span className="text-xs font-bold text-zinc-400">Авто-бан (варны)</span>
                                <input 
                                    type="number" 
                                    className="w-16 bg-zinc-900 border border-zinc-800 rounded-lg p-2 text-xs text-center text-white outline-none focus:border-blue-500"
                                    value={bot.settings?.autoBanThreshold || 0}
                                    onChange={e => onUpdate({...bot, settings: {...bot.settings, autoBanThreshold: parseInt(e.target.value) || 0}})}
                                />
                            </div>
                        </div>
                        {[
                            { key: 'useTopics', label: 'Поддержка топиков' },
                            { key: 'anonymousTopics', label: 'Анонимные топики' },
                            { key: 'topicPerRequest', label: 'Топик на заявку' }
                        ].map(s => (
                            <label key={s.key} className="flex items-center justify-between p-4 bg-black rounded-2xl border border-zinc-800 cursor-pointer hover:border-zinc-600 transition-colors">
                                <span className="text-xs font-bold text-zinc-400">{s.label}</span>
                                <input type="checkbox" className="w-4 h-4 rounded bg-black border-zinc-700 text-blue-600" checked={bot.settings[s.key as keyof BotConfig['settings']] as boolean} onChange={() => toggleSetting(s.key as any)} />
                            </label>
                        ))}
                    </div>
                </div>
                <div className="p-6 text-center">
                    <button onClick={onDelete} className="text-[10px] font-black uppercase text-zinc-600 hover:text-red-500 transition-colors">Удалить этот инстанс</button>
                </div>
            </div>
          </div>
        )}
        {activeTab === 'chat' && (
            <div className="bg-[#111] border border-zinc-800 rounded-[2.5rem] overflow-hidden flex flex-col h-[600px] shadow-2xl">
                <div className="p-6 border-b border-zinc-800 flex justify-between items-center bg-zinc-900/20">
                    <h2 className="text-xs font-black text-white uppercase flex items-center gap-2">
                        <MessageSquare className="w-4 h-4 text-blue-500" /> Живая лента сообщений
                    </h2>
                    <button onClick={refreshBotData} className="p-2 text-zinc-500 hover:text-white transition-colors">
                        <RefreshCw className="w-4 h-4" />
                    </button>
                </div>
                <div className="flex-1 overflow-y-auto p-6 space-y-4 no-scrollbar">
                    {messages.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-full opacity-10">
                            <MessageSquare className="w-16 h-16 mb-4" />
                            <p className="text-sm font-black uppercase">Нет данных</p>
                        </div>
                    ) : messages.map((m, i) => (
                        <div key={i} className={`flex gap-4 items-start p-5 rounded-3xl border transition-all ${m.is_from_admin ? 'bg-blue-600/5 border-blue-500/10 ml-12' : 'bg-black/40 border-zinc-800/50 mr-12 hover:border-zinc-700'}`}>
                            <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${m.is_from_admin ? 'bg-blue-600 text-white shadow-lg' : 'bg-zinc-800 text-zinc-400'}`}>
                                {m.is_from_admin ? <Cpu className="w-5 h-5" /> : <User className="w-5 h-5" />}
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-1">
                                    <span className="text-xs font-bold text-white truncate">{m.first_name}</span>
                                    <span className="text-[9px] text-zinc-600 font-mono">{new Date(m.created_at).toLocaleTimeString()}</span>
                                </div>
                                <p className="text-sm text-zinc-300 leading-relaxed break-words">{m.message_text}</p>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        )}
        {activeTab === 'interface' && (
            <div className="space-y-6 animate-in slide-in-from-bottom-4">
                <div className="flex justify-between items-center">
                    <h2 className="text-sm font-black text-white uppercase tracking-widest">Кнопки главного меню</h2>
                    <button onClick={() => onUpdate({...bot, buttons: [...(bot.buttons || []), {text: '', response: '', type: 'message'}]})} className="bg-blue-600 hover:bg-blue-700 px-6 py-3.5 rounded-2xl text-[10px] font-black text-white uppercase flex items-center gap-2 transition-all shadow-xl shadow-blue-600/20">
                        <Plus className="w-4 h-4" /> Добавить
                    </button>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {(bot.buttons || []).map((btn, i) => (
                        <div key={i} className="bg-[#111] border border-zinc-800 rounded-[2.5rem] p-8 space-y-4 relative group hover:border-zinc-600 transition-all shadow-lg">
                            <button onClick={() => onUpdate({...bot, buttons: bot.buttons.filter((_, idx) => idx !== i)})} className="absolute top-6 right-6 text-zinc-700 hover:text-red-500 transition-colors"><X className="w-5 h-5" /></button>
                            <input placeholder="Текст кнопки" className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-white text-sm font-bold outline-none focus:border-blue-500" value={btn.text} onChange={e => { const nb = [...bot.buttons]; nb[i].text = e.target.value; onUpdate({...bot, buttons: nb}); }} />
                            <textarea placeholder="Ответ бота..." className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-white text-xs min-h-[100px] outline-none focus:border-blue-500 resize-none" value={btn.response} onChange={e => { const nb = [...bot.buttons]; nb[i].response = e.target.value; onUpdate({...bot, buttons: nb}); }} />
                            <select className="w-full bg-zinc-900 border border-zinc-800 p-3 rounded-xl text-[10px] font-bold text-white uppercase outline-none" value={btn.type || 'message'} onChange={e => { const nb = [...bot.buttons]; nb[i].type = e.target.value as any; onUpdate({...bot, buttons: nb}); }}>
                                <option value="message">Обычное сообщение</option>
                                <option value="request">Тикет админу</option>
                            </select>
                        </div>
                    ))}
                </div>
            </div>
        )}
        {activeTab === 'logic' && (
            <div className="space-y-6 animate-in slide-in-from-bottom-4">
                <div className="flex justify-between items-center">
                    <h2 className="text-sm font-black text-white uppercase tracking-widest">Авто-ответы (триггеры)</h2>
                    <button onClick={() => onUpdate({...bot, triggers: [...(bot.triggers || []), {keyword: '', response: ''}]})} className="bg-blue-600 px-6 py-3.5 rounded-2xl text-[10px] font-black text-white uppercase flex items-center gap-2 shadow-xl shadow-blue-600/20">
                        <Plus className="w-4 h-4" /> Добавить
                    </button>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {(bot.triggers || []).map((trig, i) => (
                        <div key={i} className="bg-[#111] border border-zinc-800 rounded-[2.5rem] p-8 space-y-4 relative group hover:border-zinc-600 transition-all">
                            <button onClick={() => onUpdate({...bot, triggers: bot.triggers.filter((_, idx) => idx !== i)})} className="absolute top-6 right-6 text-zinc-700 hover:text-red-500 transition-colors"><X className="w-5 h-5" /></button>
                            <input placeholder="Ключевое слово (или часть)" className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-white text-sm font-bold outline-none focus:border-blue-500" value={trig.keyword} onChange={e => { const nt = [...bot.triggers]; nt[i].keyword = e.target.value; onUpdate({...bot, triggers: nt}); }} />
                            <textarea placeholder="Ответ..." className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-white text-xs outline-none focus:border-blue-500 resize-none min-h-[80px]" value={trig.response} onChange={e => { const nt = [...bot.triggers]; nt[i].response = e.target.value; onUpdate({...bot, triggers: nt}); }} />
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
