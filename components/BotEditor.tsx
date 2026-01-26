
import React, { useState, useEffect, useRef } from 'react';
import { BotConfig, BotStatus, MessageLog, TelegramUser, BotTrigger, BotButton } from '../types';
import BotConsole from './BotConsole';

interface BotEditorProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
  onDelete: () => void;
}

const BotEditor: React.FC<BotEditorProps> = ({ bot, onUpdate, onDelete }) => {
  const [activeTab, setActiveTab] = useState<'settings' | 'advanced' | 'logic' | 'interface' | 'chats' | 'logs'>('settings');
  const [selectedChatUser, setSelectedChatUser] = useState<number | null>(null);
  const [replyText, setReplyText] = useState('');
  const [lastUpdateId, setLastUpdateId] = useState(0);
  
  const pollingRef = useRef<number | null>(null);
  const isProcessingRef = useRef(false);

  const safeSettings = bot.settings || {
    useTopics: false,
    autoApproveJoin: false,
    forwardToAdmin: true,
    antiSpam: true,
    rateLimit: 15
  };

  const addLog = (text: string, type: MessageLog['type'] = 'info') => {
    const newLog: MessageLog = {
      id: Math.random().toString(36).substr(2, 9),
      timestamp: Date.now(),
      type,
      text
    };
    onUpdate({
      ...bot,
      logs: [newLog, ...bot.logs].slice(0, 50)
    });
  };

  // ОСНОВНОЙ ДВИЖОК БОТА (RUNNING MODE)
  const runBotEngine = async () => {
    if (isProcessingRef.current || bot.status !== BotStatus.RUNNING) return;
    isProcessingRef.current = true;

    try {
      const response = await fetch(`https://api.telegram.org/bot${bot.token}/getUpdates?offset=${lastUpdateId + 1}&timeout=20`);
      const data = await response.json();

      if (data.ok && data.result.length > 0) {
        let maxId = lastUpdateId;
        const newUsers = [...bot.connectedUsers];
        
        for (const update of data.result) {
          maxId = Math.max(maxId, update.update_id);
          const msg = update.message;
          if (!msg) continue;

          const from = msg.from;
          const text = (msg.text || "").trim();

          // Регистрация пользователя
          if (!newUsers.find(u => u.id === from.id)) {
            newUsers.push({ id: from.id, first_name: from.first_name, username: from.username, last_seen: Date.now() });
          }
          
          addLog(`Входящее от ${from.id}: ${text || '[Медиа]'}`, 'incoming');

          // ЛОГИКА АВТООТВЕТА
          let handled = false;

          // 1. Команда /start
          if (text.startsWith('/start')) {
            await sendTelegramMessage(from.id, bot.welcomeMessage);
            handled = true;
          }

          // 2. Кнопки меню
          if (!handled) {
            for (const btn of (bot.buttons || [])) {
              if (btn.text.toLowerCase() === text.toLowerCase()) {
                await sendTelegramMessage(from.id, btn.response);
                handled = true;
                break;
              }
            }
          }

          // 3. Триггеры (ключевые слова)
          if (!handled) {
            for (const trig of (bot.triggers || [])) {
              if (text.toLowerCase().includes(trig.keyword.toLowerCase())) {
                await sendTelegramMessage(from.id, trig.response);
                handled = true;
                break;
              }
            }
          }

          // 4. Пересылка админу (если ничего не подошло)
          if (!handled && safeSettings.forwardToAdmin && bot.adminChatId) {
             addLog(`Сообщение от ${from.id} требует внимания оператора`, 'info');
          }
        }
        
        setLastUpdateId(maxId);
        onUpdate({ ...bot, connectedUsers: newUsers, usersCount: newUsers.length });
      }
    } catch (err) {
      console.error("Engine Error:", err);
    } finally {
      isProcessingRef.current = false;
    }
  };

  const sendTelegramMessage = async (chatId: number | string, text: string) => {
    try {
      const kbRows = [];
      if (bot.buttons && bot.buttons.length > 0) {
        let currentRow = [];
        bot.buttons.forEach((btn, i) => {
          currentRow.push({ text: btn.text });
          if ((i + 1) % 2 === 0) { kbRows.push(currentRow); currentRow = []; }
        });
        if (currentRow.length > 0) kbRows.push(currentRow);
      }

      const res = await fetch(`https://api.telegram.org/bot${bot.token}/sendMessage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chat_id: chatId,
          text: text,
          reply_markup: kbRows.length > 0 ? { keyboard: kbRows, resize_keyboard: true } : undefined
        })
      });
      if (res.ok) addLog(`Ответ отправлен пользователю ${chatId}`, 'outgoing');
    } catch (e) {
      addLog(`Ошибка отправки: ${e}`, 'error');
    }
  };

  useEffect(() => {
    if (bot.status === BotStatus.RUNNING) {
      pollingRef.current = window.setInterval(runBotEngine, 3000);
    } else {
      if (pollingRef.current) clearInterval(pollingRef.current);
    }
    return () => { if (pollingRef.current) clearInterval(pollingRef.current); };
  }, [bot.status, lastUpdateId, bot.token]);

  const handleToggle = () => {
    if (bot.status === BotStatus.RUNNING) {
      onUpdate({ ...bot, status: BotStatus.IDLE });
      addLog("Инстанс выключен пользователем", "system");
    } else {
      if (!bot.token) return alert("Введите токен бота!");
      onUpdate({ ...bot, status: BotStatus.RUNNING });
      addLog("Запуск движка хостинга...", "system");
    }
  };

  const handleManualReply = () => {
    if (!selectedChatUser || !replyText) return;
    sendTelegramMessage(selectedChatUser, replyText);
    setReplyText('');
  };

  return (
    <div className="space-y-6 md:space-y-8 pb-20 animate-in fade-in duration-500">
      <header className="flex flex-col md:flex-row md:items-center justify-between bg-[#121212] p-6 rounded-3xl border border-zinc-800 gap-4 shadow-xl">
        <div className="flex items-center gap-4">
          <div className={`w-14 h-14 rounded-2xl flex items-center justify-center border transition-all duration-300 ${bot.status === BotStatus.RUNNING ? 'bg-green-500/10 border-green-500/30 text-green-500 shadow-[0_0_20px_rgba(34,197,94,0.2)]' : 'bg-zinc-900 border-zinc-800 text-zinc-500'}`}>
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">{bot.name}</h1>
            <div className="flex items-center gap-2 mt-1">
              <span className={`w-2 h-2 rounded-full ${bot.status === BotStatus.RUNNING ? 'bg-green-500 shadow-[0_0_8px_#22c55e]' : 'bg-zinc-600'}`}></span>
              <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{bot.status}</span>
            </div>
          </div>
        </div>

        <button 
          onClick={handleToggle}
          className={`px-10 py-3 rounded-xl font-bold transition-all border ${bot.status === BotStatus.RUNNING ? 'bg-red-500/10 text-red-500 border-red-500/20 hover:bg-red-500/20' : 'bg-blue-600 text-white hover:bg-blue-700 shadow-lg shadow-blue-600/20 border-transparent'}`}
        >
          {bot.status === BotStatus.RUNNING ? 'Выключить Хостинг' : 'Запустить на Сервере'}
        </button>
      </header>

      <div className="flex overflow-x-auto gap-1 border-b border-zinc-800 pb-px sticky top-0 bg-[#0a0a0a] z-10 pt-2">
        {[
          { id: 'settings', label: 'Конфиг' },
          { id: 'advanced', label: 'Настройки' },
          { id: 'logic', label: 'Триггеры' },
          { id: 'interface', label: 'Меню' },
          { id: 'chats', label: 'Диалоги' },
          { id: 'logs', label: 'Логи' }
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`px-6 py-3 text-xs font-bold uppercase tracking-widest transition-all border-b-2 ${activeTab === tab.id ? 'border-blue-500 text-blue-500' : 'border-transparent text-zinc-500 hover:text-zinc-300'}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="min-h-[450px]">
        {activeTab === 'settings' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 animate-in slide-in-from-bottom-4 duration-300">
            <section className="bg-[#121212] border border-zinc-800 rounded-3xl p-8 space-y-6">
              <h2 className="text-xl font-bold text-white">API & Личность</h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-[10px] font-bold text-zinc-500 uppercase mb-2">Telegram Bot Token</label>
                  <input type="password" className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-xl p-4 text-sm text-white font-mono" value={bot.token} onChange={(e) => onUpdate({ ...bot, token: e.target.value })} />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-zinc-500 uppercase mb-2">ID Администратора</label>
                  <input type="text" className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-xl p-4 text-sm text-white" value={bot.adminChatId} onChange={(e) => onUpdate({ ...bot, adminChatId: e.target.value })} />
                </div>
              </div>
            </section>
            <section className="bg-[#121212] border border-zinc-800 rounded-3xl p-8 space-y-6">
              <h2 className="text-xl font-bold text-white">Старт-сообщение (/start)</h2>
              <textarea className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-xl p-4 text-sm text-white min-h-[150px]" value={bot.welcomeMessage} onChange={(e) => onUpdate({ ...bot, welcomeMessage: e.target.value })} />
            </section>
          </div>
        )}

        {activeTab === 'advanced' && (
          <div className="bg-[#121212] border border-zinc-800 rounded-3xl p-8 space-y-8">
            <h2 className="text-xl font-bold text-white">Дополнительные модули</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {[
                { key: 'useTopics', label: 'Темы (Topics)', desc: 'Работа в группах с топиками.' },
                { key: 'autoApproveJoin', label: 'Авто-прием', desc: 'Прием заявок в каналы.' },
                { key: 'forwardToAdmin', label: 'Обратная связь', desc: 'Пересылка сообщений вам.' },
                { key: 'antiSpam', label: 'Защита от спама', desc: 'Лимит запросов в секунду.' }
              ].map(item => (
                <div key={item.key} className="flex items-center justify-between p-5 bg-zinc-900/50 rounded-2xl border border-zinc-800">
                  <div className="pr-4">
                    <span className="text-sm font-bold text-white block mb-1">{item.label}</span>
                    <span className="text-xs text-zinc-500">{item.desc}</span>
                  </div>
                  <input type="checkbox" className="w-6 h-6 rounded-lg bg-black border-zinc-700 text-blue-600" checked={(safeSettings as any)[item.key]} onChange={(e) => onUpdate({ ...bot, settings: { ...safeSettings, [item.key]: e.target.checked } })} />
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'logic' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-bold text-white">Умные авто-ответы</h2>
              <button onClick={() => onUpdate({ ...bot, triggers: [...(bot.triggers || []), { keyword: '', response: '' }] })} className="bg-blue-600 px-4 py-2 rounded-xl text-xs font-bold text-white">Добавить правило</button>
            </div>
            <div className="grid grid-cols-1 gap-4">
              {(bot.triggers || []).map((t, idx) => (
                <div key={idx} className="bg-[#121212] border border-zinc-800 p-6 rounded-2xl flex flex-col md:flex-row gap-4">
                   <input className="flex-1 bg-black border border-zinc-800 p-3 rounded-lg text-sm" placeholder="Если содержит..." value={t.keyword} onChange={(e) => {
                     const nt = [...bot.triggers]; nt[idx].keyword = e.target.value; onUpdate({...bot, triggers: nt});
                   }} />
                   <input className="flex-1 bg-black border border-zinc-800 p-3 rounded-lg text-sm" placeholder="Ответить..." value={t.response} onChange={(e) => {
                     const nt = [...bot.triggers]; nt[idx].response = e.target.value; onUpdate({...bot, triggers: nt});
                   }} />
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'interface' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-bold text-white">Главное меню (Клавиатура)</h2>
              <button onClick={() => onUpdate({ ...bot, buttons: [...(bot.buttons || []), { text: '', response: '' }] })} className="bg-blue-600 px-4 py-2 rounded-xl text-xs font-bold text-white">Новая кнопка</button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
               {(bot.buttons || []).map((b, idx) => (
                <div key={idx} className="bg-[#121212] border border-zinc-800 p-5 rounded-2xl space-y-4">
                   <input className="w-full bg-black border border-zinc-800 p-3 rounded-xl text-sm font-bold" placeholder="Текст кнопки" value={b.text} onChange={(e) => {
                     const nb = [...bot.buttons]; nb[idx].text = e.target.value; onUpdate({...bot, buttons: nb});
                   }} />
                   <textarea className="w-full bg-black border border-zinc-800 p-3 rounded-xl text-sm min-h-[80px]" placeholder="Ответ" value={b.response} onChange={(e) => {
                     const nb = [...bot.buttons]; nb[idx].response = e.target.value; onUpdate({...bot, buttons: nb});
                   }} />
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'chats' && (
           <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 h-[550px]">
             <div className="bg-[#121212] border border-zinc-800 rounded-3xl overflow-hidden flex flex-col">
               <div className="p-4 border-b border-zinc-800 text-[10px] font-bold uppercase text-zinc-500">Клиенты</div>
               <div className="flex-1 overflow-y-auto">
                 {bot.connectedUsers.length === 0 ? <div className="p-8 text-center text-zinc-700 italic">Нет активных юзеров</div> : bot.connectedUsers.map(user => (
                    <div key={user.id} onClick={() => setSelectedChatUser(user.id)} className={`p-4 border-b border-zinc-800/50 cursor-pointer transition-colors ${selectedChatUser === user.id ? 'bg-blue-600/10 border-l-2 border-l-blue-500' : 'hover:bg-zinc-800/50'}`}>
                      <p className="text-sm font-bold text-white">{user.first_name || 'Клиент'}</p>
                      <p className="text-[10px] text-zinc-500 font-mono">ID: {user.id}</p>
                    </div>
                 ))}
               </div>
             </div>
             <div className="lg:col-span-2 bg-[#121212] border border-zinc-800 rounded-3xl flex flex-col overflow-hidden">
                {selectedChatUser ? (
                  <div className="flex-1 flex flex-col p-6">
                    <div className="mb-4 text-sm font-bold text-blue-500">ДИАЛОГ: {selectedChatUser}</div>
                    <div className="flex-1 bg-black/40 rounded-2xl p-6 mb-4 text-xs italic text-zinc-600">Все сообщения от этого пользователя будут дублироваться здесь, когда бот активен.</div>
                    <div className="flex gap-3">
                       <input className="flex-1 bg-black border border-zinc-800 p-4 rounded-xl text-sm" placeholder="Написать клиенту..." value={replyText} onChange={e => setReplyText(e.target.value)} onKeyPress={e => e.key === 'Enter' && handleManualReply()} />
                       <button onClick={handleManualReply} className="bg-blue-600 text-white px-8 rounded-xl font-bold">ОТВЕТИТЬ</button>
                    </div>
                  </div>
                ) : <div className="flex-1 flex items-center justify-center text-zinc-600 italic">Выберите клиента для переписки</div>}
             </div>
           </div>
        )}

        {activeTab === 'logs' && <BotConsole logs={bot.logs} />}
      </div>

      <footer className="pt-8 border-t border-zinc-800 flex justify-end">
        <button onClick={() => confirm("Удалить безвозвратно?") && onDelete()} className="text-[10px] font-bold text-zinc-600 hover:text-red-500 uppercase tracking-widest">Удалить инстанс</button>
      </footer>
    </div>
  );
};

export default BotEditor;
