
import React, { useState } from 'react';
import { BotConfig, BotStatus } from '../types';
import { api } from '../services/apiService';
import BotConsole from './BotConsole';
import BotStatsView from './BotStatsView';
import { Settings, Cpu, MousePointer2, BarChart3, Terminal, X, Save, Power, Download, MessageSquare, Ticket } from 'lucide-react';
import CodeViewer from './CodeViewer';

interface BotEditorProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
  onDelete: () => void;
}

const BotEditor: React.FC<BotEditorProps> = ({ bot, onUpdate, onDelete }) => {
  const [activeTab, setActiveTab] = useState<'settings' | 'logic' | 'interface' | 'logs' | 'stats' | 'code'>('settings');
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
      alert("Конфигурация сохранена!");
    } catch (e) {
      alert("Ошибка сохранения");
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-20">
      <header className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] flex flex-col md:flex-row justify-between items-center gap-6 shadow-xl relative overflow-hidden">
        <div className="flex items-center gap-6 relative z-10">
          <div className={`w-16 h-16 rounded-2xl flex items-center justify-center border-2 transition-all duration-500 ${bot.status === BotStatus.RUNNING ? 'bg-green-500/10 border-green-500/30 text-green-500' : 'bg-zinc-900 border-zinc-800 text-zinc-600'}`}>
            <Cpu className="w-8 h-8" />
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
           <button onClick={save} disabled={isProcessing} className="px-6 py-4 bg-zinc-800 text-white rounded-2xl text-[10px] font-bold uppercase tracking-widest hover:bg-zinc-700 flex items-center gap-2 transition-all">
             <Save className="w-4 h-4" /> {isProcessing ? '...' : 'Сохранить'}
           </button>
           <button onClick={handleToggleServer} disabled={isProcessing} className={`px-10 py-4 rounded-2xl font-black text-xs uppercase tracking-widest transition-all flex items-center gap-2 shadow-lg ${bot.status === BotStatus.RUNNING ? 'bg-red-500/10 text-red-500 shadow-red-500/5' : 'bg-blue-600 text-white shadow-blue-600/20'}`}>
             <Power className="w-4 h-4" /> {isProcessing ? 'Ждите...' : (bot.status === BotStatus.RUNNING ? 'Стоп' : 'Старт')}
           </button>
        </div>
      </header>

      <div className="flex gap-2 border-b border-zinc-800 overflow-x-auto no-scrollbar">
        {[
          {id: 'settings', label: 'Настройки', icon: Settings},
          {id: 'logic', label: 'Триггеры', icon: MousePointer2},
          {id: 'interface', label: 'Меню', icon: Ticket},
          {id: 'stats', label: 'Аналитика', icon: BarChart3},
          {id: 'logs', label: 'Консоль', icon: Terminal},
          {id: 'code', label: 'Код/Deploy', icon: Download}
        ].map((t) => (
          <button 
            key={t.id}
            onClick={() => setActiveTab(t.id as any)}
            className={`px-6 py-4 text-[10px] font-black uppercase tracking-widest border-b-2 transition-all flex items-center gap-2 ${activeTab === t.id ? 'border-blue-500 text-blue-500' : 'border-transparent text-zinc-500'}`}
          >
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
                  <span className="text-[10px] font-bold text-zinc-500 uppercase">Admin ID (для Feedback)</span>
                  <input type="text" className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-white" value={bot.adminChatId} onChange={e => onUpdate({...bot, adminChatId: e.target.value})} />
                </label>
              </div>
            </div>
            <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] space-y-6">
              <h2 className="text-xl font-black text-white">Контент</h2>
              <label className="block">
                <span className="text-[10px] font-bold text-zinc-500 uppercase">Приветствие (/start)</span>
                <textarea className="w-full mt-1 bg-black border border-zinc-800 p-4 rounded-xl text-white min-h-[120px]" value={bot.welcomeMessage} onChange={e => onUpdate({...bot, welcomeMessage: e.target.value})} />
              </label>
            </div>
          </div>
        )}

        {activeTab === 'logic' && (
          <div className="space-y-4">
             <div className="flex justify-between items-center mb-6">
               <h2 className="text-xl font-black text-white">Авто-ответчики</h2>
               <button onClick={() => onUpdate({...bot, triggers: [...bot.triggers, {keyword: '', response: ''}]})} className="bg-blue-600 px-6 py-2 rounded-xl text-[10px] font-black text-white uppercase">Добавить</button>
             </div>
             {bot.triggers.map((trig, i) => (
               <div key={i} className="bg-[#111] border border-zinc-800 p-6 rounded-2xl flex gap-4">
                  <input placeholder="Ключевое слово" className="flex-1 bg-black border border-zinc-800 p-3 rounded-lg text-white" value={trig.keyword} onChange={e => {
                    const nt = [...bot.triggers]; nt[i].keyword = e.target.value; onUpdate({...bot, triggers: nt});
                  }} />
                  <input placeholder="Ответ" className="flex-1 bg-black border border-zinc-800 p-3 rounded-lg text-white" value={trig.response} onChange={e => {
                    const nt = [...bot.triggers]; nt[i].response = e.target.value; onUpdate({...bot, triggers: nt});
                  }} />
                  <button onClick={() => onUpdate({...bot, triggers: bot.triggers.filter((_, idx) => idx !== i)})} className="text-red-500 p-3"><X /></button>
               </div>
             ))}
          </div>
        )}

        {activeTab === 'interface' && (
          <div className="space-y-4">
             <div className="flex justify-between items-center mb-6">
               <div>
                <h2 className="text-xl font-black text-white">Главное меню (Reply)</h2>
                <p className="text-xs text-zinc-500 mt-1 italic">Кнопки "Обращение" уведомляют администратора.</p>
               </div>
               <button onClick={() => onUpdate({...bot, buttons: [...bot.buttons, {text: '', response: '', type: 'message'}]})} className="bg-blue-600 px-6 py-2 rounded-xl text-[10px] font-black text-white uppercase">Добавить кнопку</button>
             </div>
             <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
               {bot.buttons.map((btn, i) => (
                 <div key={i} className={`bg-[#111] border rounded-2xl p-6 space-y-4 relative transition-colors ${btn.type === 'request' ? 'border-blue-500/50 bg-blue-500/5' : 'border-zinc-800'}`}>
                    <button onClick={() => onUpdate({...bot, buttons: bot.buttons.filter((_, idx) => idx !== i)})} className="absolute top-4 right-4 text-zinc-600 hover:text-red-500"><X className="w-4 h-4" /></button>
                    
                    <div className="flex gap-2 mb-2">
                        <button 
                            onClick={() => { const nb = [...bot.buttons]; nb[i].type = 'message'; onUpdate({...bot, buttons: nb}); }}
                            className={`flex-1 py-2 text-[9px] font-bold uppercase rounded-lg border transition-all flex items-center justify-center gap-1 ${btn.type !== 'request' ? 'bg-zinc-800 border-zinc-700 text-white' : 'border-zinc-900 text-zinc-600'}`}
                        >
                            <MessageSquare className="w-3 h-3" /> Сообщение
                        </button>
                        <button 
                            onClick={() => { const nb = [...bot.buttons]; nb[i].type = 'request'; onUpdate({...bot, buttons: nb}); }}
                            className={`flex-1 py-2 text-[9px] font-bold uppercase rounded-lg border transition-all flex items-center justify-center gap-1 ${btn.type === 'request' ? 'bg-blue-600 border-blue-500 text-white' : 'border-zinc-900 text-zinc-600'}`}
                        >
                            <Ticket className="w-3 h-3" /> Обращение
                        </button>
                    </div>

                    <input placeholder="Текст кнопки" className="w-full bg-black border border-zinc-800 p-3 rounded-lg text-white text-sm" value={btn.text} onChange={e => {
                      const nb = [...bot.buttons]; nb[i].text = e.target.value; onUpdate({...bot, buttons: nb});
                    }} />
                    <textarea placeholder="Ответ бота" className="w-full bg-black border border-zinc-800 p-3 rounded-lg text-white text-sm min-h-[80px]" value={btn.response} onChange={e => {
                      const nb = [...bot.buttons]; nb[i].response = e.target.value; onUpdate({...bot, buttons: nb});
                    }} />
                 </div>
               ))}
             </div>
          </div>
        )}

        {activeTab === 'stats' && <BotStatsView bot={bot} onUpdate={onUpdate} />}
        {activeTab === 'logs' && <BotConsole logs={bot.logs || []} />}
        {activeTab === 'code' && <CodeViewer bot={bot} onBack={() => setActiveTab('settings')} />}
      </div>
    </div>
  );
};

export default BotEditor;
