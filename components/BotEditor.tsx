
import React, { useState } from 'react';
import { BotConfig, BotStatus } from '../types';
import { api } from '../services/apiService';
import BotConsole from './BotConsole';
import BotStatsView from './BotStatsView';
import { Settings, Cpu, MousePointer2, BarChart3, Terminal, X, Save, Power, Ticket, Info, Plus } from 'lucide-react';

interface BotEditorProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
  onDelete: () => void;
}

const BotEditor: React.FC<BotEditorProps> = ({ bot, onUpdate, onDelete }) => {
  const [activeTab, setActiveTab] = useState<'settings' | 'logic' | 'interface' | 'logs' | 'stats'>('settings');
  const [isProcessing, setIsProcessing] = useState(false);

  const handleToggleServer = async () => {
    if (isProcessing) return;
    setIsProcessing(true);
    try {
      if (bot.status === BotStatus.RUNNING) {
        await api.stopBotOnServer(bot.id);
        onUpdate({ ...bot, status: BotStatus.IDLE });
      } else {
        const result = await api.startBotOnServer(bot);
        if (result === true) onUpdate({ ...bot, status: BotStatus.RUNNING });
        else alert(`Ошибка: ${result}`);
      }
    } catch (e) { alert("Ошибка связи с сервером"); }
    finally { setIsProcessing(false); }
  };

  const save = async () => {
    setIsProcessing(true);
    try {
      await api.saveBot(bot.ownerId, bot);
      alert("Конфигурация сохранена!");
    } catch (e) { alert("Ошибка сохранения"); }
    finally { setIsProcessing(false); }
  };

  const botSettings = bot.settings || {
    useTopics: false,
    topicPerRequest: false,
    forwardToAdmin: true,
    antiSpam: true,
    showUserInfo: true,
    showUsername: true,
    autoApproveJoin: false,
    rateLimit: 15,
    autoBanThreshold: 0
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
           <button onClick={save} disabled={isProcessing} className="px-6 py-4 bg-zinc-800 text-white rounded-2xl text-[10px] font-bold uppercase tracking-widest hover:bg-zinc-700 flex items-center gap-2 transition-all border border-transparent hover:border-zinc-600">
             <Save className="w-4 h-4" /> Сохранить
           </button>
           <button onClick={handleToggleServer} disabled={isProcessing} className={`px-10 py-4 rounded-2xl font-black text-xs uppercase tracking-widest transition-all flex items-center gap-2 shadow-lg ${bot.status === BotStatus.RUNNING ? 'bg-red-500/10 text-red-500 border border-red-500/20' : 'bg-blue-600 text-white shadow-blue-600/20'}`}>
             <Power className="w-4 h-4" /> {bot.status === BotStatus.RUNNING ? 'Стоп' : 'Старт'}
           </button>
        </div>
      </header>

      <div className="flex gap-2 border-b border-zinc-800 overflow-x-auto no-scrollbar">
        {[
          {id: 'settings', label: 'Настройки', icon: Settings},
          {id: 'interface', label: 'Главное меню', icon: Ticket},
          {id: 'logic', label: 'Триггеры', icon: MousePointer2},
          {id: 'stats', label: 'Аналитика', icon: BarChart3},
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
              <h2 className="text-xl font-black text-white">Основное</h2>
              <div className="space-y-4">
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">Bot Token (из @BotFather)</span>
                  <input type="password" className="w-full mt-1 bg-black border border-zinc-800 p-4 rounded-xl text-white font-mono focus:border-blue-500/50 outline-none transition-all" value={bot.token} onChange={e => onUpdate({...bot, token: e.target.value})} />
                </label>
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">ID Администратора / Чат ID</span>
                  <input type="text" className="w-full mt-1 bg-black border border-zinc-800 p-4 rounded-xl text-white focus:border-blue-500/50 outline-none transition-all" value={bot.adminChatId} onChange={e => onUpdate({...bot, adminChatId: e.target.value})} placeholder="Напр: 123456789 или -100..." />
                </label>
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase ml-2">Текст приветствия (/start)</span>
                  <textarea className="w-full mt-1 bg-black border border-zinc-800 p-4 rounded-xl text-white min-h-[100px] focus:border-blue-500/50 outline-none transition-all" value={bot.welcomeMessage} onChange={e => onUpdate({...bot, welcomeMessage: e.target.value})} />
                </label>
              </div>
            </div>
            <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
              <h2 className="text-xl font-black text-white">Расширенные опции</h2>
              <div className="space-y-4">
                <label className="flex items-center gap-4 p-4 bg-black rounded-2xl border border-zinc-800 cursor-pointer hover:border-zinc-700 transition-all">
                  <input type="checkbox" className="w-5 h-5 accent-blue-600" checked={botSettings.useTopics} onChange={e => onUpdate({...bot, settings: {...botSettings, useTopics: e.target.checked}})} />
                  <div>
                    <p className="text-xs font-bold text-white uppercase tracking-widest">Использовать топики</p>
                    <p className="text-[10px] text-zinc-500">Создает отдельную ветку чата для каждого пользователя (для супергрупп).</p>
                  </div>
                </label>
                <label className="flex items-center gap-4 p-4 bg-black rounded-2xl border border-zinc-800 cursor-pointer hover:border-zinc-700 transition-all">
                  <input type="checkbox" className="w-5 h-5 accent-blue-600" checked={botSettings.forwardToAdmin} onChange={e => onUpdate({...bot, settings: {...botSettings, forwardToAdmin: e.target.checked}})} />
                  <div>
                    <p className="text-xs font-bold text-white uppercase tracking-widest">Пересылка сообщений</p>
                    <p className="text-[10px] text-zinc-500">Дублировать все входящие сообщения в чат администратора.</p>
                  </div>
                </label>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'logic' && (
          <div className="space-y-6">
            <div className="flex justify-between items-end mb-4">
               <div>
                  <h2 className="text-xl font-black text-white">Триггеры</h2>
                  <p className="text-zinc-500 text-[10px] font-bold uppercase tracking-widest mt-1">Автоматические ответы на ключевые слова</p>
               </div>
               <button onClick={() => onUpdate({...bot, triggers: [...(bot.triggers || []), {keyword: '', response: ''}]})} className="bg-blue-600 hover:bg-blue-700 px-6 py-3 rounded-xl text-[10px] font-black text-white uppercase tracking-widest flex items-center gap-2 transition-all">
                  <Plus className="w-4 h-4" /> Добавить триггер
               </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
               {(bot.triggers || []).map((trig, i) => (
                 <div key={i} className="bg-[#0d0d0d] border border-zinc-800 rounded-3xl p-6 space-y-4 relative group hover:border-zinc-700 transition-all">
                    <button onClick={() => onUpdate({...bot, triggers: bot.triggers.filter((_, idx) => idx !== i)})} className="absolute top-4 right-4 text-zinc-600 hover:text-red-500 transition-colors">
                      <X className="w-5 h-5" />
                    </button>
                    <div>
                        <span className="text-[8px] font-black text-zinc-500 uppercase tracking-widest ml-1">Ключевое слово (или часть текста)</span>
                        <input placeholder="Напр: привет" className="w-full mt-1 bg-black border border-zinc-800 p-3 rounded-xl text-white text-sm focus:border-blue-500/50 outline-none transition-all" value={trig.keyword} onChange={e => { const nt = [...bot.triggers]; nt[i].keyword = e.target.value; onUpdate({...bot, triggers: nt}); }} />
                    </div>
                    <div>
                        <span className="text-[8px] font-black text-zinc-500 uppercase tracking-widest ml-1">Ответ бота</span>
                        <textarea placeholder="Текст ответа..." className="w-full mt-1 bg-black border border-zinc-800 p-3 rounded-xl text-white text-sm focus:border-blue-500/50 outline-none transition-all min-h-[80px]" value={trig.response} onChange={e => { const nt = [...bot.triggers]; nt[i].response = e.target.value; onUpdate({...bot, triggers: nt}); }} />
                    </div>
                 </div>
               ))}
               {(bot.triggers || []).length === 0 && (
                 <div className="col-span-full py-20 border-2 border-dashed border-zinc-800 rounded-[2.5rem] flex flex-col items-center justify-center text-zinc-700">
                    <MousePointer2 className="w-12 h-12 mb-4 opacity-20" />
                    <p className="text-xs font-black uppercase tracking-widest opacity-30">Нет активных триггеров</p>
                 </div>
               )}
            </div>
          </div>
        )}

        {activeTab === 'interface' && (
          <div className="space-y-6">
             <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-2">
               <div className="flex-1">
                  <h2 className="text-xl font-black text-white">Главное меню</h2>
                  <div className="mt-4 bg-blue-600/5 border border-blue-600/20 p-4 rounded-2xl inline-block max-w-full">
                    <div className="flex items-center gap-2 mb-2">
                        <Info className="w-3 h-3 text-blue-500" />
                        <span className="text-[9px] font-black text-blue-500 uppercase tracking-widest">Доступные теги для админ-шаблона:</span>
                    </div>
                    <div className="flex flex-wrap gap-x-4 gap-y-1">
                        <span className="text-[10px] text-zinc-400 font-mono"><span className="text-zinc-600">{"{{id}}"}</span> - ID юзера</span>
                        <span className="text-[10px] text-zinc-400 font-mono"><span className="text-zinc-600">{"{{name}}"}</span> - Имя</span>
                        <span className="text-[10px] text-zinc-400 font-mono"><span className="text-zinc-600">{"{{username}}"}</span> - Логин</span>
                        <span className="text-[10px] text-zinc-400 font-mono"><span className="text-zinc-600">{"{{button}}"}</span> - Название кнопки</span>
                    </div>
                  </div>
               </div>
               <button onClick={() => onUpdate({...bot, buttons: [...(bot.buttons || []), {text: '', response: '', type: 'message', adminTemplate: '⚡️ Сообщение от {{name}} (ID: {{id}})'}]})} className="bg-blue-600 hover:bg-blue-700 px-8 py-3 rounded-xl text-[10px] font-black text-white uppercase tracking-widest flex items-center gap-2 transition-all self-end md:self-start">
                  ДОБАВИТЬ КНОПКУ
               </button>
             </div>

             <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
               {(bot.buttons || []).map((btn, i) => (
                 <div key={i} className={`bg-[#0d0d0d] border rounded-[2rem] p-8 space-y-5 relative transition-all ${btn.type === 'request' ? 'border-blue-600/40 shadow-[0_0_20px_rgba(37,99,235,0.05)]' : 'border-zinc-800'}`}>
                    <button onClick={() => onUpdate({...bot, buttons: bot.buttons.filter((_, idx) => idx !== i)})} className="absolute top-6 right-6 text-zinc-600 hover:text-red-500 transition-colors">
                      <X className="w-5 h-5" />
                    </button>
                    
                    <div className="bg-black border border-zinc-800 rounded-xl p-1 flex gap-1">
                        <button 
                          onClick={() => { const nb = [...bot.buttons]; nb[i].type = 'message'; onUpdate({...bot, buttons: nb}); }} 
                          className={`flex-1 flex items-center justify-center gap-2 py-2 text-[9px] font-black uppercase rounded-lg transition-all ${btn.type !== 'request' ? 'bg-zinc-800 text-white' : 'text-zinc-600 hover:text-zinc-400'}`}
                        >
                          <Ticket className="w-3 h-3" /> Сообщение
                        </button>
                        <button 
                          onClick={() => { const nb = [...bot.buttons]; nb[i].type = 'request'; onUpdate({...bot, buttons: nb}); }} 
                          className={`flex-1 flex items-center justify-center gap-2 py-2 text-[9px] font-black uppercase rounded-lg transition-all ${btn.type === 'request' ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20' : 'text-zinc-600 hover:text-zinc-400'}`}
                        >
                          <MousePointer2 className="w-3 h-3" /> Обращение
                        </button>
                    </div>

                    <div className="space-y-4">
                        <input 
                          placeholder="Текст на кнопке..." 
                          className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-white text-sm font-bold focus:border-blue-500/30 outline-none transition-all" 
                          value={btn.text} 
                          onChange={e => { const nb = [...bot.buttons]; nb[i].text = e.target.value; onUpdate({...bot, buttons: nb}); }} 
                        />
                        <textarea 
                          placeholder="Что ответит бот пользователю при нажатии?" 
                          className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-white text-sm min-h-[100px] focus:border-blue-500/30 outline-none transition-all resize-none" 
                          value={btn.response} 
                          onChange={e => { const nb = [...bot.buttons]; nb[i].response = e.target.value; onUpdate({...bot, buttons: nb}); }} 
                        />
                    </div>

                    {btn.type === 'request' && (
                      <div className="pt-2 animate-in slide-in-from-top-2 duration-300">
                         <span className="text-[9px] font-black text-blue-500 uppercase tracking-widest ml-1">Шаблон для админа</span>
                         <textarea 
                          placeholder="Текст, который придет админу..." 
                          className="w-full mt-2 bg-black border border-blue-500/20 p-4 rounded-xl text-[12px] text-zinc-300 min-h-[100px] focus:border-blue-500/50 outline-none transition-all resize-none font-mono" 
                          value={btn.adminTemplate} 
                          onChange={e => { const nb = [...bot.buttons]; nb[i].adminTemplate = e.target.value; onUpdate({...bot, buttons: nb}); }} 
                        />
                      </div>
                    )}
                 </div>
               ))}
               {(bot.buttons || []).length === 0 && (
                 <div className="col-span-full py-20 border-2 border-dashed border-zinc-800 rounded-[2.5rem] flex flex-col items-center justify-center text-zinc-700">
                    <Ticket className="w-12 h-12 mb-4 opacity-20" />
                    <p className="text-xs font-black uppercase tracking-widest opacity-30">Меню пусто</p>
                 </div>
               )}
             </div>
          </div>
        )}

        {activeTab === 'stats' && <BotStatsView bot={bot} onUpdate={onUpdate} />}
        {activeTab === 'logs' && <BotConsole logs={bot.logs || []} />}
      </div>
    </div>
  );
};

export default BotEditor;
