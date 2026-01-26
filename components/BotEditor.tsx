
import React, { useState } from 'react';
import { BotConfig, BotStatus } from '../types';
import { api } from '../services/apiService';
import BotConsole from './BotConsole';

interface BotEditorProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
  onDelete: () => void;
}

const BotEditor: React.FC<BotEditorProps> = ({ bot, onUpdate, onDelete }) => {
  const [activeTab, setActiveTab] = useState<'settings' | 'logic' | 'interface' | 'logs'>('settings');
  const [isDeploying, setIsDeploying] = useState(false);

  const handleToggleServer = async () => {
    if (bot.status === BotStatus.RUNNING) {
      await api.stopBotOnServer(bot.id);
      onUpdate({ ...bot, status: BotStatus.IDLE });
    } else {
      setIsDeploying(true);
      const success = await api.startBotOnServer(bot);
      if (success) {
        onUpdate({ ...bot, status: BotStatus.RUNNING });
      }
      setIsDeploying(false);
    }
  };

  const save = () => api.saveBot(bot.ownerId, bot);

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <header className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] flex flex-col md:flex-row justify-between items-center gap-6 shadow-xl">
        <div className="flex items-center gap-6">
          <div className={`w-16 h-16 rounded-2xl flex items-center justify-center border-2 transition-all duration-500 ${bot.status === BotStatus.RUNNING ? 'bg-green-500/10 border-green-500/30 text-green-500' : 'bg-zinc-900 border-zinc-800 text-zinc-600'}`}>
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </div>
          <div>
            <h1 className="text-3xl font-black text-white">{bot.name}</h1>
            <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{bot.status}</span>
          </div>
        </div>
        <div className="flex gap-4">
           <button onClick={save} className="px-6 py-4 bg-zinc-800 text-white rounded-2xl text-[10px] font-bold uppercase tracking-widest hover:bg-zinc-700">Сохранить</button>
           <button onClick={handleToggleServer} className={`px-10 py-4 rounded-2xl font-black text-xs uppercase tracking-widest transition-all ${bot.status === BotStatus.RUNNING ? 'bg-red-500/10 text-red-500' : 'bg-blue-600 text-white'}`}>
             {bot.status === BotStatus.RUNNING ? 'Остановить' : 'Запустить'}
           </button>
        </div>
      </header>

      <div className="flex gap-2 border-b border-zinc-800 overflow-x-auto no-scrollbar">
        {['settings', 'logic', 'interface', 'logs'].map((t) => (
          <button 
            key={t}
            onClick={() => setActiveTab(t as any)}
            className={`px-6 py-4 text-[10px] font-black uppercase tracking-widest border-b-2 transition-all whitespace-nowrap ${activeTab === t ? 'border-blue-500 text-blue-500' : 'border-transparent text-zinc-500'}`}
          >
            {t === 'settings' ? 'Конфиг' : t === 'logic' ? 'Триггеры' : t === 'interface' ? 'Клавиатура' : 'Консоль'}
          </button>
        ))}
      </div>

      <div className="min-h-[400px]">
        {activeTab === 'settings' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
              <h2 className="text-xl font-black text-white">Параметры доступа</h2>
              <div className="space-y-4">
                <input type="password" className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-sm font-mono text-white" placeholder="Token" value={bot.token} onChange={e => onUpdate({...bot, token: e.target.value})} />
                <input type="text" className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-sm text-white" placeholder="Admin Chat ID" value={bot.adminChatId} onChange={e => onUpdate({...bot, adminChatId: e.target.value})} />
              </div>
            </div>
            <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
              <h2 className="text-xl font-black text-white">Старт-сообщение</h2>
              <textarea className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-sm min-h-[150px] resize-none text-white" value={bot.welcomeMessage} onChange={e => onUpdate({...bot, welcomeMessage: e.target.value})} />
            </div>
          </div>
        )}

        {activeTab === 'logic' && (
          <div className="space-y-4">
             <div className="flex justify-between items-center">
               <h2 className="text-xl font-black text-white">Триггеры на текст</h2>
               <button onClick={() => onUpdate({...bot, triggers: [...bot.triggers, {keyword: '', response: ''}]})} className="bg-blue-600 px-4 py-2 rounded-lg text-[10px] font-black text-white">Добавить</button>
             </div>
             {bot.triggers.map((trig, i) => (
               <div key={i} className="bg-[#111] border border-zinc-800 p-6 rounded-2xl flex gap-4">
                  <input className="flex-1 bg-black border border-zinc-800 p-3 rounded-lg text-sm text-white" placeholder="Слово-ключ" value={trig.keyword} onChange={e => {
                    const nt = [...bot.triggers]; nt[i].keyword = e.target.value; onUpdate({...bot, triggers: nt});
                  }} />
                  <input className="flex-1 bg-black border border-zinc-800 p-3 rounded-lg text-sm text-white" placeholder="Ответ бота" value={trig.response} onChange={e => {
                    const nt = [...bot.triggers]; nt[i].response = e.target.value; onUpdate({...bot, triggers: nt});
                  }} />
                  <button onClick={() => { const nt = bot.triggers.filter((_, idx) => idx !== i); onUpdate({...bot, triggers: nt}); }} className="text-red-500 font-bold">×</button>
               </div>
             ))}
          </div>
        )}

        {activeTab === 'interface' && (
          <div className="space-y-4">
             <div className="flex justify-between items-center">
               <h2 className="text-xl font-black text-white">Кнопки меню</h2>
               <button onClick={() => onUpdate({...bot, buttons: [...bot.buttons, {text: '', response: ''}]})} className="bg-blue-600 px-4 py-2 rounded-lg text-[10px] font-black text-white">Добавить</button>
             </div>
             {bot.buttons.map((btn, i) => (
               <div key={i} className="bg-[#111] border border-zinc-800 p-6 rounded-2xl flex gap-4">
                  <input className="flex-1 bg-black border border-zinc-800 p-3 rounded-lg text-sm text-white" placeholder="Текст кнопки" value={btn.text} onChange={e => {
                    const nb = [...bot.buttons]; nb[i].text = e.target.value; onUpdate({...bot, buttons: nb});
                  }} />
                  <input className="flex-1 bg-black border border-zinc-800 p-3 rounded-lg text-sm text-white" placeholder="Ответ бота" value={btn.response} onChange={e => {
                    const nb = [...bot.buttons]; nb[i].response = e.target.value; onUpdate({...bot, buttons: nb});
                  }} />
                  <button onClick={() => { const nb = bot.buttons.filter((_, idx) => idx !== i); onUpdate({...bot, buttons: nb}); }} className="text-red-500 font-bold">×</button>
               </div>
             ))}
          </div>
        )}

        {activeTab === 'logs' && <BotConsole logs={bot.logs || []} />}
      </div>
    </div>
  );
};

export default BotEditor;
