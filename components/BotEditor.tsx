
import React, { useState } from 'react';
import { BotConfig, BotStatus } from '../types';
import { api } from '../services/apiService';
import BotConsole from './BotConsole';
import BotStatsView from './BotStatsView';
import { Settings, Cpu, MousePointer2, BarChart3, Terminal, X, Save, Power, Ticket } from 'lucide-react';

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
      alert("Сохранено!");
    } catch (e) { alert("Ошибка сохранения"); }
    finally { setIsProcessing(false); }
  };

  // Безопасный доступ к настройкам
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
           <button onClick={save} disabled={isProcessing} className="px-6 py-4 bg-zinc-800 text-white rounded-2xl text-[10px] font-bold uppercase tracking-widest hover:bg-zinc-700 flex items-center gap-2 transition-all">
             <Save className="w-4 h-4" /> Сохранить
           </button>
           <button onClick={handleToggleServer} disabled={isProcessing} className={`px-10 py-4 rounded-2xl font-black text-xs uppercase tracking-widest transition-all flex items-center gap-2 shadow-lg ${bot.status === BotStatus.RUNNING ? 'bg-red-500/10 text-red-500' : 'bg-blue-600 text-white'}`}>
             <Power className="w-4 h-4" /> {bot.status === BotStatus.RUNNING ? 'Стоп' : 'Старт'}
           </button>
        </div>
      </header>

      <div className="flex gap-2 border-b border-zinc-800 overflow-x-auto no-scrollbar">
        {[
          {id: 'settings', label: 'Настройки', icon: Settings},
          {id: 'logic', label: 'Триггеры', icon: MousePointer2},
          {id: 'interface', label: 'Меню', icon: Ticket},
          {id: 'stats', label: 'Аналитика', icon: BarChart3},
          {id: 'logs', label: 'Консоль', icon: Terminal}
        ].map((t) => (
          <button key={t.id} onClick={() => setActiveTab(t.id as any)} className={`px-6 py-4 text-[10px] font-black uppercase tracking-widest border-b-2 transition-all flex items-center gap-2 ${activeTab === t.id ? 'border-blue-500 text-blue-500' : 'border-transparent text-zinc-500'}`}>
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
                  <span className="text-[10px] font-bold text-zinc-500 uppercase">Bot Token</span>
                  <input type="password" className="w-full mt-1 bg-black border border-zinc-800 p-4 rounded-xl text-white font-mono" value={bot.token} onChange={e => onUpdate({...bot, token: e.target.value})} />
                </label>
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase">Admin ID</span>
                  <input type="text" className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-white" value={bot.adminChatId} onChange={e => onUpdate({...bot, adminChatId: e.target.value})} />
                </label>
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase">Приветствие</span>
                  <textarea className="w-full mt-1 bg-black border border-zinc-800 p-4 rounded-xl text-white min-h-[100px]" value={bot.welcomeMessage} onChange={e => onUpdate({...bot, welcomeMessage: e.target.value})} />
                </label>
              </div>
            </div>
            <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
              <h2 className="text-xl font-black text-white">Опции</h2>
              <div className="space-y-4">
                <label className="flex items-center gap-4 p-4 bg-black rounded-2xl border border-zinc-800 cursor-pointer">
                  <input type="checkbox" className="w-5 h-5" checked={botSettings.useTopics} onChange={e => onUpdate({...bot, settings: {...botSettings, useTopics: e.target.checked}})} />
                  <div>
                    <p className="text-xs font-bold text-white uppercase tracking-widest">Топики</p>
                    <p className="text-[10px] text-zinc-500">Отдельный чат на юзера.</p>
                  </div>
                </label>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'logic' && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
               <h2 className="text-xl font-black text-white">Триггеры</h2>
               <button onClick={() => onUpdate({...bot, triggers: [...bot.triggers, {keyword: '', response: ''}]})} className="bg-blue-600 px-6 py-2 rounded-xl text-[10px] font-black text-white uppercase">Добавить</button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
               {bot.triggers.map((trig, i) => (
                 <div key={i} className="bg-[#111] border border-zinc-800 rounded-2xl p-6 space-y-4 relative">
                    <button onClick={() => onUpdate({...bot, triggers: bot.triggers.filter((_, idx) => idx !== i)})} className="absolute top-4 right-4 text-zinc-600 hover:text-red-500"><X className="w-4 h-4" /></button>
                    <input placeholder="Слово" className="w-full bg-black border border-zinc-800 p-3 rounded-lg text-white text-sm" value={trig.keyword} onChange={e => { const nt = [...bot.triggers]; nt[i].keyword = e.target.value; onUpdate({...bot, triggers: nt}); }} />
                    <textarea placeholder="Ответ" className="w-full bg-black border border-zinc-800 p-3 rounded-lg text-white text-sm" value={trig.response} onChange={e => { const nt = [...bot.triggers]; nt[i].response = e.target.value; onUpdate({...bot, triggers: nt}); }} />
                 </div>
               ))}
            </div>
          </div>
        )}

        {activeTab === 'interface' && (
          <div className="space-y-4">
             <div className="flex justify-between items-center mb-6">
               <h2 className="text-xl font-black text-white">Меню</h2>
               <button onClick={() => onUpdate({...bot, buttons: [...bot.buttons, {text: '', response: '', type: 'message'}]})} className="bg-blue-600 px-6 py-2 rounded-xl text-[10px] font-black text-white uppercase">Добавить кнопку</button>
             </div>
             <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
               {bot.buttons.map((btn, i) => (
                 <div key={i} className={`bg-[#111] border rounded-2xl p-6 space-y-4 relative ${btn.type === 'request' ? 'border-blue-500/50' : 'border-zinc-800'}`}>
                    <button onClick={() => onUpdate({...bot, buttons: bot.buttons.filter((_, idx) => idx !== i)})} className="absolute top-4 right-4 text-zinc-600 hover:text-red-500"><X className="w-4 h-4" /></button>
                    <div className="flex gap-2">
                        <button onClick={() => { const nb = [...bot.buttons]; nb[i].type = 'message'; onUpdate({...bot, buttons: nb}); }} className={`flex-1 py-2 text-[9px] font-bold uppercase rounded-lg border ${btn.type !== 'request' ? 'bg-zinc-800 text-white' : 'text-zinc-600'}`}>Сообщение</button>
                        <button onClick={() => { const nb = [...bot.buttons]; nb[i].type = 'request'; onUpdate({...bot, buttons: nb}); }} className={`flex-1 py-2 text-[9px] font-bold uppercase rounded-lg border ${btn.type === 'request' ? 'bg-blue-600 text-white' : 'text-zinc-600'}`}>Обращение</button>
                    </div>
                    <input placeholder="Текст кнопки" className="w-full bg-black border border-zinc-800 p-3 rounded-lg text-white text-sm" value={btn.text} onChange={e => { const nb = [...bot.buttons]; nb[i].text = e.target.value; onUpdate({...bot, buttons: nb}); }} />
                    <textarea placeholder="Ответ" className="w-full bg-black border border-zinc-800 p-3 rounded-lg text-white text-sm" value={btn.response} onChange={e => { const nb = [...bot.buttons]; nb[i].response = e.target.value; onUpdate({...bot, buttons: nb}); }} />
                 </div>
               ))}
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
