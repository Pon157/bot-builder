
import React, { useState } from 'react';
import { BotConfig, BotStatus } from '../types';
import { api } from '../services/apiService';
import BotConsole from './BotConsole';
import BotStatsView from './BotStatsView';

interface BotEditorProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
  onDelete: () => void;
}

const BotEditor: React.FC<BotEditorProps> = ({ bot, onUpdate, onDelete }) => {
  const [activeTab, setActiveTab] = useState<'settings' | 'logic' | 'interface' | 'logs' | 'stats'>('settings');
  const [isProcessing, setIsProcessing] = useState(false);

  const handleToggleServer = async () => {
    setIsProcessing(true);
    try {
      if (bot.status === BotStatus.RUNNING) {
        await api.stopBotOnServer(bot.id);
        onUpdate({ ...bot, status: BotStatus.IDLE });
      } else {
        const result = await api.startBotOnServer(bot);
        if (result === true) {
          onUpdate({ ...bot, status: BotStatus.RUNNING });
        } else {
          alert(`Ошибка: ${result}`);
        }
      }
    } catch (e) {
      alert("Ошибка связи с сервером");
    } finally {
      setIsProcessing(false);
    }
  };

  const save = async () => {
    setIsProcessing(true);
    try {
      await api.saveBot(bot.ownerId, bot);
      alert("Конфигурация сохранена. Бот будет перезапущен.");
    } catch (e) {
      alert("Ошибка сохранения");
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-20">
      <header className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] flex flex-col md:flex-row justify-between items-center gap-6 shadow-xl relative overflow-hidden">
        <div className="absolute top-0 right-0 p-4 opacity-5">
            <svg className="w-32 h-32" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5-10-5-10 5z"/></svg>
        </div>
        <div className="flex items-center gap-6 relative z-10">
          <div className={`w-16 h-16 rounded-2xl flex items-center justify-center border-2 transition-all duration-500 ${bot.status === BotStatus.RUNNING ? 'bg-green-500/10 border-green-500/30 text-green-500 shadow-[0_0_20px_rgba(34,197,94,0.1)]' : 'bg-zinc-900 border-zinc-800 text-zinc-600'}`}>
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </div>
          <div>
            <h1 className="text-3xl font-black text-white">{bot.name}</h1>
            <div className="flex items-center gap-2">
               <span className={`w-2 h-2 rounded-full ${bot.status === BotStatus.RUNNING ? 'bg-green-500 animate-pulse' : 'bg-zinc-600'}`}></span>
               <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{bot.status}</span>
            </div>
          </div>
        </div>
        <div className="flex gap-4 relative z-10">
           <button 
             onClick={save} 
             disabled={isProcessing}
             className="px-6 py-4 bg-zinc-800 text-white rounded-2xl text-[10px] font-bold uppercase tracking-widest hover:bg-zinc-700 transition-all active:scale-95 disabled:opacity-50"
           >
             {isProcessing ? '...' : 'Обновить'}
           </button>
           <button 
             onClick={handleToggleServer} 
             disabled={isProcessing}
             className={`px-10 py-4 rounded-2xl font-black text-xs uppercase tracking-widest transition-all active:scale-95 ${bot.status === BotStatus.RUNNING ? 'bg-red-500/10 text-red-500 hover:bg-red-500/20' : 'bg-blue-600 text-white shadow-lg shadow-blue-600/20 hover:bg-blue-500'} ${isProcessing ? 'opacity-50 cursor-wait' : ''}`}
           >
             {isProcessing ? 'Загрузка...' : (bot.status === BotStatus.RUNNING ? 'Выключить' : 'Включить')}
           </button>
        </div>
      </header>

      <div className="flex gap-2 border-b border-zinc-800 overflow-x-auto no-scrollbar">
        {[
          {id: 'settings', label: 'Конфиг'},
          {id: 'logic', label: 'Триггеры'},
          {id: 'interface', label: 'Кнопки'},
          {id: 'stats', label: 'Статистика'},
          {id: 'logs', label: 'Консоль'}
        ].map((t) => (
          <button 
            key={t.id}
            onClick={() => setActiveTab(t.id as any)}
            className={`px-6 py-4 text-[10px] font-black uppercase tracking-widest border-b-2 transition-all whitespace-nowrap ${activeTab === t.id ? 'border-blue-500 text-blue-500' : 'border-transparent text-zinc-500 hover:text-zinc-300'}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="min-h-[400px]">
        {activeTab === 'settings' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
              <h2 className="text-xl font-black text-white flex items-center gap-2">
                <svg className="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                Доступ и Связь
              </h2>
              <div className="space-y-4">
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase ml-1">HTTP API Token (@BotFather)</span>
                  <input type="password" className="w-full mt-1 bg-black border border-zinc-800 p-4 rounded-xl text-sm font-mono text-white outline-none focus:border-blue-500 transition-colors" placeholder="123456789:ABC..." value={bot.token} onChange={e => onUpdate({...bot, token: e.target.value})} />
                </label>
                <label className="block">
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase ml-1">Admin Chat/Group ID</span>
                    <span className="text-[9px] text-blue-500 font-bold uppercase cursor-help" title="ID чата куда будут падать сообщения. Можно узнать командой /id у бота">Где взять?</span>
                  </div>
                  <input type="text" className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-sm text-white outline-none focus:border-blue-500 transition-colors" placeholder="-100..." value={bot.adminChatId} onChange={e => onUpdate({...bot, adminChatId: e.target.value})} />
                </label>
              </div>
              <div className="pt-4 space-y-3">
                 <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Опции обратной связи</h3>
                 <div className="grid grid-cols-1 gap-2">
                    <label className="flex items-center justify-between p-3 bg-black border border-zinc-800 rounded-xl cursor-pointer hover:border-zinc-700 transition-all">
                       <span className="text-xs text-zinc-300">Поддержка топиков (Topics)</span>
                       <input type="checkbox" className="w-4 h-4 accent-blue-600" checked={bot.settings.useTopics} onChange={e => onUpdate({...bot, settings: {...bot.settings, useTopics: e.target.checked}})} />
                    </label>
                    <label className="flex items-center justify-between p-3 bg-black border border-zinc-800 rounded-xl cursor-pointer hover:border-zinc-700 transition-all">
                       <span className="text-xs text-zinc-300">Показывать инфо юзера админу</span>
                       <input type="checkbox" className="w-4 h-4 accent-blue-600" checked={bot.settings.showUserInfo} onChange={e => onUpdate({...bot, settings: {...bot.settings, showUserInfo: e.target.checked}})} />
                    </label>
                 </div>
              </div>
            </div>
            <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
              <h2 className="text-xl font-black text-white flex items-center gap-2">
                 <svg className="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                 Контент бота
              </h2>
              <div className="space-y-4">
                <label className="block">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase ml-1">Приветствие (/start)</span>
                  <textarea className="w-full mt-1 bg-black border border-zinc-800 p-4 rounded-xl text-sm min-h-[150px] resize-none text-white outline-none focus:border-blue-500 transition-colors" value={bot.welcomeMessage} onChange={e => onUpdate({...bot, welcomeMessage: e.target.value})} />
                </label>
                <div className="p-4 bg-blue-600/5 border border-blue-600/20 rounded-xl">
                   <p className="text-[10px] text-blue-400 leading-relaxed font-medium">
                     <b>Совет:</b> Используйте HTML-теги для оформления: &lt;b&gt;жирный&lt;/b&gt;, &lt;i&gt;курсив&lt;/i&gt;, &lt;code&gt;код&lt;/code&gt;.
                   </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'logic' && (
          <div className="space-y-4">
             <div className="flex justify-between items-center mb-6">
               <h2 className="text-xl font-black text-white">Авто-ответчики</h2>
               <button onClick={() => onUpdate({...bot, triggers: [...bot.triggers, {keyword: '', response: ''}]})} className="bg-blue-600 hover:bg-blue-700 transition-all active:scale-95 px-6 py-2 rounded-xl text-[10px] font-black text-white uppercase tracking-widest">Добавить триггер</button>
             </div>
             <div className="grid grid-cols-1 gap-3">
               {bot.triggers.map((trig, i) => (
                 <div key={i} className="bg-[#111] border border-zinc-800 p-6 rounded-2xl flex flex-col md:flex-row gap-4 animate-in slide-in-from-left-2 duration-300 group">
                    <div className="flex-1 space-y-1">
                       <span className="text-[9px] font-bold text-zinc-600 uppercase ml-1">Если юзер написал:</span>
                       <input className="w-full bg-black border border-zinc-800 p-3 rounded-lg text-sm text-white outline-none focus:border-blue-500" placeholder="Напр: 'Цены' или 'Купить'" value={trig.keyword} onChange={e => {
                        const nt = [...bot.triggers]; nt[i].keyword = e.target.value; onUpdate({...bot, triggers: nt});
                      }} />
                    </div>
                    <div className="flex-1 space-y-1">
                       <span className="text-[9px] font-bold text-zinc-600 uppercase ml-1">Бот ответит:</span>
                       <input className="w-full bg-black border border-zinc-800 p-3 rounded-lg text-sm text-white outline-none focus:border-blue-500" placeholder="Текст ответа..." value={trig.response} onChange={e => {
                        const nt = [...bot.triggers]; nt[i].response = e.target.value; onUpdate({...bot, triggers: nt});
                      }} />
                    </div>
                    <button onClick={() => { const nt = bot.triggers.filter((_, idx) => idx !== i); onUpdate({...bot, triggers: nt}); }} className="md:self-end mb-1 p-3 text-red-500 hover:bg-red-500/10 rounded-lg transition-all">
                       <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    </button>
                 </div>
               ))}
               {bot.triggers.length === 0 && (
                 <div className="text-center py-12 bg-zinc-900/30 rounded-[2rem] border border-dashed border-zinc-800">
                    <p className="text-zinc-600 text-xs font-bold uppercase tracking-widest">Нет активных триггеров</p>
                 </div>
               )}
             </div>
          </div>
        )}

        {activeTab === 'interface' && (
          <div className="space-y-4">
             <div className="flex justify-between items-center mb-6">
               <h2 className="text-xl font-black text-white">Кнопки главного меню</h2>
               <button onClick={() => onUpdate({...bot, buttons: [...bot.buttons, {text: '', response: ''}]})} className="bg-blue-600 hover:bg-blue-700 transition-all active:scale-95 px-6 py-2 rounded-xl text-[10px] font-black text-white uppercase tracking-widest">Добавить кнопку</button>
             </div>
             <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
               {bot.buttons.map((btn, i) => (
                 <div key={i} className="bg-[#111] border border-zinc-800 p-6 rounded-2xl space-y-4 animate-in zoom-in-95 duration-300 relative">
                    <button onClick={() => { const nb = bot.buttons.filter((_, idx) => idx !== i); onUpdate({...bot, buttons: nb}); }} className="absolute top-4 right-4 text-zinc-600 hover:text-red-500 transition-colors">
                       <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    </button>
                    <div className="space-y-1">
                       <span className="text-[9px] font-bold text-zinc-600 uppercase ml-1">Текст на кнопке</span>
                       <input className="w-full bg-black border border-zinc-800 p-3 rounded-lg text-sm text-white outline-none focus:border-blue-500" placeholder="Напр: 🚀 Тарифы" value={btn.text} onChange={e => {
                        const nb = [...bot.buttons]; nb[i].text = e.target.value; onUpdate({...bot, buttons: nb});
                      }} />
                    </div>
                    <div className="space-y-1">
                       <span className="text-[9px] font-bold text-zinc-600 uppercase ml-1">Действие бота</span>
                       <textarea className="w-full bg-black border border-zinc-800 p-3 rounded-lg text-sm text-white outline-none focus:border-blue-500 min-h-[80px] resize-none" placeholder="Сообщение которое бот отправит в ответ..." value={btn.response} onChange={e => {
                        const nb = [...bot.buttons]; nb[i].response = e.target.value; onUpdate({...bot, buttons: nb});
                      }} />
                    </div>
                 </div>
               ))}
             </div>
          </div>
        )}

        {activeTab === 'stats' && <BotStatsView bot={bot} />}
        {activeTab === 'logs' && <BotConsole logs={bot.logs || []} />}
      </div>
    </div>
  );
};

export default BotEditor;
