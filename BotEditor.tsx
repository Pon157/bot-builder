
import React, { useState, useEffect, useRef } from 'react';
import { BotConfig, BotStatus, MessageLog, TelegramUser, BotTrigger, BotButton } from '../types';
import BotConsole from './BotConsole';

interface BotEditorProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
  onDelete: () => void;
  onGenerateCode: () => void;
}

const BotEditor: React.FC<BotEditorProps> = ({ bot, onUpdate, onDelete, onGenerateCode }) => {
  const [activeTab, setActiveTab] = useState<'settings' | 'logic' | 'interface' | 'chats' | 'logs'>('settings');
  const [selectedChatUser, setSelectedChatUser] = useState<number | null>(null);
  const [replyText, setReplyText] = useState('');
  const [lastUpdateId, setLastUpdateId] = useState(0);
  
  const pollingRef = useRef<number | null>(null);

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

  const pollTelegram = async () => {
    try {
      const response = await fetch(`https://api.telegram.org/bot${bot.token}/getUpdates?offset=${lastUpdateId + 1}&timeout=30`);
      const data = await response.json();
      if (data.ok && data.result.length > 0) {
        let maxId = lastUpdateId;
        const newUsers = [...bot.connectedUsers];
        data.result.forEach((update: any) => {
          maxId = Math.max(maxId, update.update_id);
          if (update.message) {
            const from = update.message.from;
            if (!newUsers.find(u => u.id === from.id)) {
              newUsers.push({ id: from.id, first_name: from.first_name, username: from.username, last_seen: Date.now() });
            }
            addLog(`Message from ${from.id}: ${update.message.text || '[Media]'}`, 'incoming');
          }
        });
        setLastUpdateId(maxId);
        onUpdate({ ...bot, connectedUsers: newUsers, usersCount: newUsers.length });
      }
    } catch (err) {}
  };

  useEffect(() => {
    if (bot.status === BotStatus.RUNNING) {
      pollingRef.current = window.setInterval(pollTelegram, 3000);
    } else {
      if (pollingRef.current) clearInterval(pollingRef.current);
    }
    return () => { if (pollingRef.current) clearInterval(pollingRef.current); };
  }, [bot.status, lastUpdateId]);

  const handleLaunch = () => {
    onUpdate({ ...bot, status: bot.status === BotStatus.RUNNING ? BotStatus.IDLE : BotStatus.RUNNING });
    addLog(bot.status === BotStatus.RUNNING ? "Engine stopping..." : "Engine starting...", "info");
  };

  const handleAddTrigger = () => {
    onUpdate({ ...bot, triggers: [...(bot.triggers || []), { keyword: '', response: '' }] });
  };

  const handleAddButton = () => {
    onUpdate({ ...bot, buttons: [...(bot.buttons || []), { text: '', response: '' }] });
  };

  const handleSendReply = async () => {
    if (!selectedChatUser || !replyText) return;
    try {
      const res = await fetch(`https://api.telegram.org/bot${bot.token}/sendMessage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: selectedChatUser, text: replyText })
      });
      if (res.ok) {
        addLog(`Reply sent to ${selectedChatUser}: ${replyText}`, 'outgoing');
        setReplyText('');
      }
    } catch (e) {}
  };

  return (
    <div className="space-y-6 md:space-y-8 pb-20">
      <header className="flex flex-col md:flex-row md:items-center justify-between bg-[#121212] p-6 rounded-3xl border border-zinc-800 gap-4">
        <div className="flex items-center gap-4">
          <div className={`w-12 h-12 md:w-14 md:h-14 rounded-2xl flex items-center justify-center border transition-all ${bot.status === BotStatus.RUNNING ? 'bg-green-500/10 border-green-500/30 text-green-500' : 'bg-zinc-900 border-zinc-800 text-zinc-500'}`}>
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </div>
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-white tracking-tight truncate max-w-[200px]">{bot.name}</h1>
            <div className="flex items-center gap-2 mt-1">
              <span className={`w-2 h-2 rounded-full ${bot.status === BotStatus.RUNNING ? 'bg-green-500 shadow-[0_0_8px_#22c55e]' : 'bg-zinc-600'}`}></span>
              <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{bot.status}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button 
            onClick={handleLaunch}
            className={`flex-1 md:flex-none px-6 py-3 rounded-xl font-bold transition-all border ${bot.status === BotStatus.RUNNING ? 'bg-red-500/10 text-red-500 border-red-500/20 hover:bg-red-500/20' : 'bg-blue-600 text-white hover:bg-blue-700 shadow-lg shadow-blue-600/20 border-transparent'}`}
          >
            {bot.status === BotStatus.RUNNING ? 'Stop' : 'Start'}
          </button>
          <button onClick={onGenerateCode} className="bg-zinc-800 hover:bg-zinc-700 text-white px-6 py-3 rounded-xl font-bold border border-zinc-700 transition-all">
            Deploy
          </button>
        </div>
      </header>

      <div className="flex overflow-x-auto gap-1 border-b border-zinc-800 pb-px no-scrollbar">
        {(['settings', 'logic', 'interface', 'chats', 'logs'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 md:px-6 py-3 text-[10px] md:text-xs font-bold uppercase tracking-widest transition-all border-b-2 whitespace-nowrap ${activeTab === tab ? 'border-blue-500 text-blue-500' : 'border-transparent text-zinc-500 hover:text-zinc-300'}`}
          >
            {tab}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-8">
        {activeTab === 'settings' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 animate-in slide-in-from-left-4">
            <section className="bg-[#121212] border border-zinc-800 rounded-3xl p-6 md:p-8 space-y-6">
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                <svg className="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                Core Config
              </h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-2">Admin/Operator ID</label>
                  <input 
                    type="text" className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-xl p-4 text-sm text-white focus:ring-1 focus:ring-blue-500 focus:outline-none"
                    value={bot.adminChatId} onChange={(e) => onUpdate({ ...bot, adminChatId: e.target.value })} placeholder="Your Telegram ID"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-2">Welcome Message</label>
                  <textarea 
                    className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-xl p-4 text-sm text-white focus:ring-1 focus:ring-blue-500 focus:outline-none min-h-[120px]"
                    value={bot.welcomeMessage} onChange={(e) => onUpdate({ ...bot, welcomeMessage: e.target.value })}
                  />
                </div>
              </div>
            </section>
            
            <section className="bg-[#121212] border border-zinc-800 rounded-3xl p-6 md:p-8 space-y-6">
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                 <svg className="w-5 h-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                 Security & Anti-Spam
              </h2>
              <div className="p-4 bg-zinc-900/50 rounded-2xl border border-zinc-800 space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-zinc-300">Enabled Rate Limiting</span>
                  <input 
                    type="checkbox" className="w-5 h-5 rounded border-zinc-800 bg-black text-blue-500"
                    checked={bot.antiSpam.enabled} onChange={(e) => onUpdate({...bot, antiSpam: {...bot.antiSpam, enabled: e.target.checked}})}
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-zinc-500 uppercase mb-2">Messages per minute</label>
                  <input 
                    type="number" className="w-full bg-black border border-zinc-800 rounded-xl p-3 text-sm"
                    value={bot.antiSpam.rateLimit} onChange={(e) => onUpdate({...bot, antiSpam: {...bot.antiSpam, rateLimit: parseInt(e.target.value)}})}
                  />
                </div>
              </div>
            </section>
          </div>
        )}

        {activeTab === 'logic' && (
          <div className="animate-in fade-in zoom-in-95 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-bold">Autoreply Triggers</h2>
              <button onClick={handleAddTrigger} className="bg-blue-600/10 text-blue-500 px-4 py-2 rounded-xl text-xs font-bold border border-blue-500/20 hover:bg-blue-600/20">Add Trigger</button>
            </div>
            <div className="grid grid-cols-1 gap-4">
              {(bot.triggers || []).map((t, idx) => (
                <div key={idx} className="bg-[#121212] border border-zinc-800 p-6 rounded-2xl grid grid-cols-1 md:grid-cols-2 gap-4">
                   <input 
                     className="bg-[#0a0a0a] border border-zinc-800 p-3 rounded-lg text-sm" placeholder="If message contains..." 
                     value={t.keyword} onChange={(e) => {
                       const nt = [...bot.triggers]; nt[idx].keyword = e.target.value; onUpdate({...bot, triggers: nt});
                     }}
                   />
                   <input 
                     className="bg-[#0a0a0a] border border-zinc-800 p-3 rounded-lg text-sm" placeholder="Bot will reply..." 
                     value={t.response} onChange={(e) => {
                       const nt = [...bot.triggers]; nt[idx].response = e.target.value; onUpdate({...bot, triggers: nt});
                     }}
                   />
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'interface' && (
          <div className="animate-in fade-in zoom-in-95 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-bold">Main Menu Buttons</h2>
              <button onClick={handleAddButton} className="bg-blue-600/10 text-blue-500 px-4 py-2 rounded-xl text-xs font-bold border border-blue-500/20 hover:bg-blue-600/20">Add Button</button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {(bot.buttons || []).map((b, idx) => (
                <div key={idx} className="bg-[#121212] border border-zinc-800 p-6 rounded-2xl space-y-3">
                   <input 
                     className="w-full bg-[#0a0a0a] border border-zinc-800 p-3 rounded-lg text-sm font-bold" placeholder="Button Label" 
                     value={b.text} onChange={(e) => {
                       const nb = [...bot.buttons]; nb[idx].text = e.target.value; onUpdate({...bot, buttons: nb});
                     }}
                   />
                   <textarea 
                     className="w-full bg-[#0a0a0a] border border-zinc-800 p-3 rounded-lg text-sm" placeholder="On click, reply..." 
                     value={b.response} onChange={(e) => {
                       const nb = [...bot.buttons]; nb[idx].response = e.target.value; onUpdate({...bot, buttons: nb});
                     }}
                   />
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'chats' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 h-[500px] md:h-[600px] animate-in zoom-in-95">
            <div className="bg-[#121212] border border-zinc-800 rounded-3xl overflow-hidden flex flex-col">
              <div className="p-4 border-b border-zinc-800 bg-zinc-900/50 font-bold text-[10px] uppercase text-zinc-500 tracking-widest">Active Users</div>
              <div className="flex-1 overflow-y-auto">
                {bot.connectedUsers.length === 0 ? (
                  <div className="p-10 text-center text-zinc-600 text-sm italic">Database empty...</div>
                ) : (
                  bot.connectedUsers.map(user => (
                    <div 
                      key={user.id} onClick={() => setSelectedChatUser(user.id)}
                      className={`p-4 border-b border-zinc-800/50 cursor-pointer transition-colors ${selectedChatUser === user.id ? 'bg-blue-600/10 border-l-2 border-l-blue-500' : 'hover:bg-zinc-800/50'}`}
                    >
                      <p className="text-sm font-bold text-white">{user.first_name || 'Anonymous'}</p>
                      <p className="text-[10px] text-zinc-500 font-mono">UID: {user.id}</p>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="lg:col-span-2 bg-[#121212] border border-zinc-800 rounded-3xl flex flex-col overflow-hidden relative">
              {selectedChatUser ? (
                <>
                  <div className="p-4 border-b border-zinc-800 bg-zinc-900/50 flex justify-between items-center">
                    <span className="text-sm font-bold text-white">Live Link: {selectedChatUser}</span>
                    <span className="text-[10px] text-green-500 uppercase font-bold tracking-widest animate-pulse">Socket Active</span>
                  </div>
                  <div className="flex-1 p-6 overflow-y-auto space-y-4 bg-[#0a0a0a]/50">
                    <div className="bg-zinc-900/80 p-4 rounded-2xl border border-zinc-800 max-w-[90%] text-xs leading-relaxed text-zinc-400">
                      Operator interface active. Messages received via web-polling will appear in Logs. Direct replies from here use the standard Telegram API.
                    </div>
                  </div>
                  <div className="p-6 border-t border-zinc-800 bg-zinc-900/30">
                    <div className="flex gap-3">
                      <input 
                        type="text" className="flex-1 bg-black border border-zinc-800 rounded-xl p-4 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
                        placeholder="Push message to user..." value={replyText} onChange={(e) => setReplyText(e.target.value)}
                        onKeyPress={(e) => e.key === 'Enter' && handleSendReply()}
                      />
                      <button onClick={handleSendReply} className="bg-blue-600 hover:bg-blue-700 text-white px-8 rounded-xl font-bold transition-all">Send</button>
                    </div>
                  </div>
                </>
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center text-zinc-700 space-y-4">
                  <svg className="w-12 h-12 opacity-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  <p className="text-sm font-medium">Select a user to engage</p>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'logs' && (
          <div className="animate-in slide-in-from-right-4">
            <BotConsole logs={bot.logs} />
          </div>
        )}
      </div>

      <footer className="pt-8 border-t border-zinc-800 flex justify-end">
        <button 
          onClick={() => { if(confirm("Permanently destroy this instance data?")) onDelete(); }}
          className="text-[10px] text-zinc-600 hover:text-red-500 uppercase tracking-widest font-bold transition-colors"
        >
          Terminate Instance
        </button>
      </footer>
    </div>
  );
};

export default BotEditor;
