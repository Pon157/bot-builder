
import React, { useState, useEffect } from 'react';
import { BotConfig, BotStatus } from '../types';
import { api } from '../services/apiService';
import BotConsole from './BotConsole';
import BotStatsView from './BotStatsView';
import { Settings, Cpu, MousePointer2, BarChart3, Terminal, X, Save, Power, Ticket, Info, Plus, MessageSquare, User } from 'lucide-react';

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
    if (activeTab === 'chat') {
        api.getBotMessages(bot.id).then(setMessages);
    }
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
        const result = await api.startBotOnServer(bot);
        if (result === true) {
            onUpdate({ ...bot, status: BotStatus.RUNNING });
        } else {
            alert(`Ошибка запуска: ${result}`);
        }
      }
    } catch (e: any) { alert("Ошибка сервера: " + (e.message || "Неизвестно")); }
    finally { setIsProcessing(false); }
  };

  const save = async () => {
    setIsProcessing(true);
    try {
      await api.saveBot(bot.owner_id, bot);
      alert("Конфигурация успешно сохранена в облаке!");
    } catch (e: any) { 
      alert("Ошибка при сохранении: " + (e.message || "Проверьте подключение")); 
    }
    finally { setIsProcessing(false); }
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
           <button onClick={save} disabled={isProcessing} className="px-6 py-4 bg-zinc-800 text-white rounded-2xl text-[10px] font-bold uppercase tracking-widest hover:bg-zinc-700 flex items-center gap-2 transition-all border border-transparent hover:border-zinc-600 shadow-lg">
             <Save className="w-4 h-4" /> Сохранить в БД
           </button>
           <button onClick={handleToggleServer} disabled={isProcessing} className={`px-10 py-4 rounded-2xl font-black text-xs uppercase tracking-widest transition-all flex items-center gap-2 shadow-lg ${bot.status === BotStatus.RUNNING ? 'bg-red-500/10 text-red-500 border border-red-500/20' : 'bg-blue-600 text-white shadow-blue-600/20'}`}>
             <Power className="w-4 h-4" /> {bot.status === BotStatus.RUNNING ? 'Остановить' : 'Запустить'}
           </button>
        </div>
      </header>

      <div className="flex gap-2 border-b border-zinc-800 overflow-x-auto no-scrollbar">
        {[
          {id: 'settings', label: 'Конфигурация', icon: Settings},
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
        {activeTab === 'chat' && (
            <div className="bg-[#111] border border-zinc-800 rounded-[2.5rem] overflow-hidden flex flex-col h-[600px]">
                <div className="p-6 border-b border-zinc-800 flex justify-between items-center bg-zinc-900/20">
                    <h2 className="text-sm font-black text-white uppercase flex items-center gap-2">
                        <MessageSquare className="w-4 h-4 text-blue-500" /> Активные диалоги (Livegram Mode)
                    </h2>
                </div>
                <div className="flex-1 overflow-y-auto p-6 space-y-4 no-scrollbar">
                    {messages.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-full opacity-20">
                            <MessageSquare className="w-12 h-12 mb-2" />
                            <p className="text-[10px] font-black uppercase">Нет сообщений</p>
                        </div>
                    ) : messages.map((m, i) => (
                        <div key={i} className={`flex gap-4 items-start p-5 rounded-3xl border ${m.is_admin ? 'bg-blue-600/5 border-blue-500/20 ml-10' : 'bg-black/40 border-zinc-800/50 mr-10'}`}>
                            <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${m.is_admin ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400'}`}>
                                {m.is_admin ? <Cpu className="w-5 h-5" /> : <User className="w-5 h-5" />}
                            </div>
                            <div>
                                <div className="flex items-center gap-2 mb-1">
                                    <span className="text-xs font-bold text-white">{m.user.name}</span>
                                    {!m.is_admin && <span className="text-[10px] text-zinc-600 font-mono">ID: {m.user.id}</span>}
                                    <span className="text-[9px] text-zinc-500">{new Date(m.timestamp).toLocaleTimeString()}</span>
                                </div>
                                <p className="text-sm text-zinc-300 leading-relaxed">{m.text}</p>
                            </div>
                        </div>
                    ))}
                </div>
                <div className="p-6 bg-zinc-900/10 border-t border-zinc-800 text-center">
                    <p className="text-[10px] text-zinc-500 font-bold uppercase">Отвечайте в Telegram пересылкой сообщения юзеру</p>
                </div>
            </div>
        )}

        {activeTab === 'interface' && (
          <div className="space-y-6">
             <div className="flex justify-between items-center mb-4">
                <h2 className="text-xl font-black text-white uppercase tracking-tight">Редактор меню</h2>
                <button onClick={() => onUpdate({...bot, buttons: [...(bot.buttons || []), {text: '', response: '', type: 'message'}]})} className="bg-blue-600 hover:bg-blue-700 px-8 py-3.5 rounded-2xl text-[11px] font-black text-white uppercase tracking-widest flex items-center gap-2 transition-all shadow-xl shadow-blue-600/20">
                    <Plus className="w-4 h-4" /> Добавить кнопку
                </button>
             </div>

             <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
               {(bot.buttons || []).map((btn, i) => (
                 <div key={i} className="bg-[#0d0d0d] border border-zinc-800 rounded-[2.5rem] p-8 space-y-6 relative transition-all group hover:border-zinc-700">
                    <button onClick={() => onUpdate({...bot, buttons: bot.buttons.filter((_, idx) => idx !== i)})} className="absolute top-6 right-6 text-zinc-600 hover:text-red-500 transition-colors">
                      <X className="w-5 h-5" />
                    </button>
                    
                    <div className="space-y-4">
                        <input 
                          placeholder="Текст кнопки" 
                          className="w-full bg-black border border-zinc-800 p-5 rounded-2xl text-white text-sm font-black focus:border-blue-500/40 outline-none transition-all" 
                          value={btn.text} 
                          onChange={e => { const nb = [...bot.buttons]; nb[i].text = e.target.value; onUpdate({...bot, buttons: nb}); }} 
                        />
                        <textarea 
                          placeholder="Текст ответа при нажатии..."
                          className="w-full bg-black border border-zinc-800 p-5 rounded-2xl text-white text-sm min-h-[120px] focus:border-blue-500/40 outline-none transition-all resize-none" 
                          value={btn.response} 
                          onChange={e => { const nb = [...bot.buttons]; nb[i].response = e.target.value; onUpdate({...bot, buttons: nb}); }} 
                        />
                        <div className="flex items-center gap-2">
                             <span className="text-[9px] font-bold text-zinc-500 uppercase">Тип:</span>
                             <select 
                                className="bg-zinc-900 border border-zinc-800 rounded px-2 py-1 text-[10px] text-white"
                                value={btn.type || 'message'}
                                onChange={e => { const nb = [...bot.buttons]; nb[i].type = e.target.value as any; onUpdate({...bot, buttons: nb}); }}
                             >
                                 <option value="message">Обычное сообщение</option>
                                 <option value="request">Заявка админу (Ticket)</option>
                             </select>
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
               <div>
                  <h2 className="text-xl font-black text-white uppercase">Триггеры (Автоответы)</h2>
                  <p className="text-zinc-500 text-[10px] font-bold uppercase tracking-widest mt-1">Ответы на ключевые слова в сообщениях</p>
               </div>
               <button onClick={() => onUpdate({...bot, triggers: [...(bot.triggers || []), {keyword: '', response: ''}]})} className="bg-blue-600 hover:bg-blue-700 px-6 py-3.5 rounded-2xl text-[10px] font-black text-white uppercase tracking-widest flex items-center gap-2 transition-all shadow-lg">
                  <Plus className="w-4 h-4" /> Новый триггер
               </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
               {(bot.triggers || []).map((trig, i) => (
                 <div key={i} className="bg-[#0d0d0d] border border-zinc-800 rounded-[2.5rem] p-8 space-y-5 relative group hover:border-zinc-700 transition-all">
                    <button onClick={() => onUpdate({...bot, triggers: bot.triggers.filter((_, idx) => idx !== i)})} className="absolute top-6 right-6 text-zinc-600 hover:text-red-500 transition-colors">
                      <X className="w-5 h-5" />
                    </button>
                    <div>
                        <span className="text-[10px] font-black text-zinc-500 uppercase tracking-widest ml-1">Ключевое слово (или часть слова)</span>
                        <input placeholder="Напр: тарифы" className="w-full mt-2 bg-black border border-zinc-800 p-4 rounded-xl text-white text-sm font-bold focus:border-blue-500/40 outline-none transition-all" value={trig.keyword} onChange={e => { const nt = [...bot.triggers]; nt[i].keyword = e.target.value; onUpdate({...bot, triggers: nt}); }} />
                    </div>
                    <div>
                        <span className="text-[10px] font-black text-zinc-500 uppercase tracking-widest ml-1">Ответ бота</span>
                        <textarea placeholder="Бот ответит этим текстом..." className="w-full mt-2 bg-black border border-zinc-800 p-4 rounded-xl text-white text-sm focus:border-blue-500/40 outline-none transition-all min-h-[100px] resize-none" value={trig.response} onChange={e => { const nt = [...bot.triggers]; nt[i].response = e.target.value; onUpdate({...bot, triggers: nt}); }} />
                    </div>
                 </div>
               ))}
            </div>
          </div>
        )}

        {activeTab === 'settings' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
              <h2 className="text-xl font-black text-white uppercase">Основные данные</h2>
              <div className="space-y-5">
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">Telegram Bot Token</span>
                  <input type="password" className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white font-mono focus:border-blue-500/50 outline-none transition-all shadow-inner" value={bot.token} onChange={e => onUpdate({...bot, token: e.target.value})} />
                </label>
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">ID Администратора (для Livegram)</span>
                  <input type="text" className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white focus:border-blue-500/50 outline-none transition-all shadow-inner" value={bot.adminChatId} onChange={e => onUpdate({...bot, adminChatId: e.target.value})} placeholder="Получите через @userinfobot" />
                </label>
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">Приветствие (/start)</span>
                  <textarea className="w-full mt-2 bg-black border border-zinc-800 p-5 rounded-2xl text-white min-h-[140px] focus:border-blue-500/50 outline-none transition-all resize-none shadow-inner" value={bot.welcomeMessage} onChange={e => onUpdate({...bot, welcomeMessage: e.target.value})} />
                </label>
              </div>
            </div>
            <div className="space-y-6">
                <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-4">
                    <h3 className="text-xs font-black text-white uppercase mb-2">Настройки безопасности</h3>
                    <div className="space-y-3">
                        <label className="flex items-center justify-between p-4 bg-black rounded-2xl border border-zinc-800 cursor-pointer">
                            <span className="text-xs font-bold text-zinc-400">Автобан при варнах (0 = откл)</span>
                            <div className="flex items-center gap-3">
                                <input type="number" className="w-16 bg-zinc-900 border border-zinc-800 rounded p-1 text-center text-xs text-white" value={bot.settings?.autoBanThreshold || 0} onChange={e => onUpdate({...bot, settings: {...bot.settings, autoBanThreshold: parseInt(e.target.value) || 0}})} />
                            </div>
                        </label>
                        <label className="flex items-center justify-between p-4 bg-black rounded-2xl border border-zinc-800 cursor-pointer">
                            <span className="text-xs font-bold text-zinc-400">Поддержка топиков (Forum)</span>
                            <input type="checkbox" className="w-4 h-4 rounded border-zinc-800 bg-black text-blue-600" checked={bot.settings?.useTopics} onChange={e => onUpdate({...bot, settings: {...bot.settings, useTopics: e.target.checked}})} />
                        </label>
                        <label className="flex items-center justify-between p-4 bg-black rounded-2xl border border-zinc-800 cursor-pointer">
                            <span className="text-xs font-bold text-zinc-400">Топик на каждую заявку</span>
                            <input type="checkbox" className="w-4 h-4 rounded border-zinc-800 bg-black text-blue-600" checked={bot.settings?.topicPerRequest} onChange={e => onUpdate({...bot, settings: {...bot.settings, topicPerRequest: e.target.checked}})} />
                        </label>
                    </div>
                </div>
                <div className="bg-blue-600/5 border border-blue-500/20 p-8 rounded-[2.5rem] flex flex-col items-center text-center space-y-4">
                    <div className="w-16 h-16 bg-blue-600/10 rounded-2xl flex items-center justify-center text-blue-500">
                        <Info className="w-8 h-8" />
                    </div>
                    <p className="text-xs text-zinc-400 leading-relaxed font-medium">После нажатия <b>"Сохранить в БД"</b>, настройки применяются в облаке. Для активации изменений в запущенном боте нажмите <b>"Остановить"</b> и снова <b>"Запустить"</b>.</p>
                </div>
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
