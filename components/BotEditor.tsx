
import React, { useState, useEffect, useRef } from 'react';
import { BotConfig, BotStatus, MessageLog } from '../types';
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
  const [deployStep, setDeployStep] = useState(0);

  const deployMessages = [
    "Инициализация Cloud инстанса...",
    "Проверка Python зависимостей...",
    "Синхронизация базы данных триггеров...",
    "Запуск процесса aiogram-worker...",
    "Бот успешно запущен в фоновом режиме сервера."
  ];

  const handleToggleServer = async () => {
    if (bot.status === BotStatus.RUNNING) {
      await api.stopBotOnServer(bot.id);
      onUpdate({ ...bot, status: BotStatus.IDLE });
    } else {
      setIsDeploying(true);
      setDeployStep(0);
      
      // Анимация серверного деплоя
      for (let i = 0; i < deployMessages.length; i++) {
        setDeployStep(i);
        await new Promise(r => setTimeout(r, 600));
      }

      const success = await api.startBotOnServer(bot);
      if (success) {
        onUpdate({ ...bot, status: BotStatus.RUNNING });
      }
      setIsDeploying(false);
    }
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {isDeploying && (
        <div className="fixed inset-0 z-[200] bg-black/95 backdrop-blur-md flex items-center justify-center p-6">
          <div className="max-w-md w-full">
            <div className="bg-[#111] border border-zinc-800 rounded-[2.5rem] p-8 shadow-2xl space-y-6">
              <div className="flex justify-center">
                <div className="w-12 h-12 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
              </div>
              <div className="font-mono text-[11px] space-y-2">
                {deployMessages.slice(0, deployStep + 1).map((msg, i) => (
                  <div key={i} className="flex gap-3 items-start animate-in slide-in-from-left-2">
                    <span className="text-zinc-600">[{new Date().toLocaleTimeString()}]</span>
                    <span className={i === deployStep ? "text-blue-400" : "text-green-500"}>
                      {i < deployStep ? "DONE" : "PROC"}: {msg}
                    </span>
                  </div>
                ))}
              </div>
              <p className="text-center text-zinc-500 text-[9px] uppercase font-bold tracking-[0.2em]">Deploying to Server Node #01</p>
            </div>
          </div>
        </div>
      )}

      <header className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] flex flex-col md:flex-row justify-between items-center gap-6 shadow-xl">
        <div className="flex items-center gap-6">
          <div className={`w-16 h-16 rounded-2xl flex items-center justify-center border-2 transition-all duration-500 ${bot.status === BotStatus.RUNNING ? 'bg-green-500/10 border-green-500/30 text-green-500' : 'bg-zinc-900 border-zinc-800 text-zinc-600'}`}>
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </div>
          <div>
            <h1 className="text-3xl font-black text-white">{bot.name}</h1>
            <div className="flex items-center gap-2 mt-1">
              <div className={`w-2 h-2 rounded-full ${bot.status === BotStatus.RUNNING ? 'bg-green-500 animate-pulse' : 'bg-zinc-700'}`}></div>
              <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                {bot.status === BotStatus.RUNNING ? 'Работает на сервере (24/7)' : 'Остановлен'}
              </span>
            </div>
          </div>
        </div>

        <button 
          onClick={handleToggleServer}
          className={`px-10 py-4 rounded-2xl font-black text-xs uppercase tracking-widest transition-all ${bot.status === BotStatus.RUNNING ? 'bg-red-500/10 text-red-500 border border-red-500/20 hover:bg-red-500/20' : 'bg-blue-600 text-white shadow-lg shadow-blue-600/20 hover:bg-blue-700'}`}
        >
          {bot.status === BotStatus.RUNNING ? 'Остановить сервер' : 'Запустить на сервере'}
        </button>
      </header>

      <div className="flex gap-2 border-b border-zinc-800">
        {['settings', 'logic', 'interface', 'logs'].map((t) => (
          <button 
            key={t}
            onClick={() => setActiveTab(t as any)}
            className={`px-6 py-4 text-[10px] font-black uppercase tracking-widest border-b-2 transition-all ${activeTab === t ? 'border-blue-500 text-blue-500' : 'border-transparent text-zinc-500 hover:text-zinc-300'}`}
          >
            {t === 'settings' ? 'Конфиг' : t === 'logic' ? 'Триггеры' : t === 'interface' ? 'Кнопки' : 'Логи'}
          </button>
        ))}
      </div>

      <div className="min-h-[400px]">
        {activeTab === 'settings' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2rem] space-y-6">
              <h2 className="text-xl font-black text-white">Cloud API</h2>
              <div className="space-y-4">
                <div>
                  <label className="text-[10px] font-black text-zinc-500 uppercase block mb-2">Telegram Token</label>
                  <input type="password" className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-sm font-mono" value={bot.token} onChange={e => onUpdate({...bot, token: e.target.value})} />
                </div>
                <div>
                  <label className="text-[10px] font-black text-zinc-500 uppercase block mb-2">ID Администратора</label>
                  <input type="text" className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-sm" value={bot.adminChatId} onChange={e => onUpdate({...bot, adminChatId: e.target.value})} />
                </div>
              </div>
            </div>
            <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2rem] space-y-6">
              <h2 className="text-xl font-black text-white">Старт-текст</h2>
              <textarea className="w-full bg-black border border-zinc-800 p-4 rounded-xl text-sm min-h-[150px] resize-none" value={bot.welcomeMessage} onChange={e => onUpdate({...bot, welcomeMessage: e.target.value})} />
            </div>
          </div>
        )}

        {activeTab === 'logic' && (
          <div className="space-y-4">
             <div className="flex justify-between items-center mb-4">
               <h2 className="text-xl font-black text-white">Авто-ответы</h2>
               <button onClick={() => onUpdate({...bot, triggers: [...bot.triggers, {keyword: '', response: ''}]})} className="bg-blue-600 px-4 py-2 rounded-lg text-[10px] font-black text-white uppercase tracking-widest">Добавить</button>
             </div>
             {bot.triggers.map((trig, i) => (
               <div key={i} className="bg-[#111] border border-zinc-800 p-6 rounded-2xl flex gap-4 items-center">
                  <input className="flex-1 bg-black border border-zinc-800 p-3 rounded-lg text-sm" placeholder="Ключевое слово" value={trig.keyword} onChange={e => {
                    const nt = [...bot.triggers]; nt[i].keyword = e.target.value; onUpdate({...bot, triggers: nt});
                  }} />
                  <input className="flex-1 bg-black border border-zinc-800 p-3 rounded-lg text-sm" placeholder="Ответ" value={trig.response} onChange={e => {
                    const nt = [...bot.triggers]; nt[i].response = e.target.value; onUpdate({...bot, triggers: nt});
                  }} />
               </div>
             ))}
          </div>
        )}

        {activeTab === 'logs' && <BotConsole logs={bot.logs || []} />}
      </div>

      <footer className="pt-8 border-t border-zinc-800 flex justify-end">
        <button onClick={() => confirm("Удалить бота с сервера?") && onDelete()} className="text-[10px] font-black text-zinc-700 hover:text-red-500 uppercase tracking-widest transition-colors">Удалить конфигурацию</button>
      </footer>
    </div>
  );
};

export default BotEditor;
