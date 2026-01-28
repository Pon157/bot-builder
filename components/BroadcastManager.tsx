
import React, { useState } from 'react';
import { BotConfig } from '../types';
import { api } from '../services/apiService';

interface BroadcastManagerProps {
  bots: BotConfig[];
}

const BroadcastManager: React.FC<BroadcastManagerProps> = ({ bots }) => {
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);

  const toggleBot = (id: string) => {
    setSelectedBotIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const handleSend = async () => {
    if (!message || selectedBotIds.length === 0) return;
    setSending(true);
    try {
      const result = await api.sendBroadcast(selectedBotIds, message);
      if (result) {
        alert(`Рассылка завершена!\nУспешно: ${result.success}\nОшибок: ${result.failed}`);
        setMessage('');
        setSelectedBotIds([]);
      }
    } catch (e) {
      alert("Ошибка при выполнении рассылки");
    } finally {
      setSending(false);
    }
  };

  const activeBots = bots.filter(b => b.status === 'RUNNING');

  return (
    <div className="max-w-4xl mx-auto space-y-6 md:space-y-8 animate-in fade-in duration-500 pb-10">
      <header>
        <h1 className="text-2xl md:text-3xl font-black text-white">Глобальная рассылка</h1>
        <p className="text-zinc-500 text-sm">Отправка сообщений всем пользователям выбранных инстансов.</p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8">
        <div className="md:col-span-2 bg-[#111] border border-zinc-800 p-5 md:p-8 rounded-[1.5rem] md:rounded-[2rem] space-y-6">
          <label className="text-[10px] font-black text-zinc-500 uppercase tracking-widest block">Текст сообщения</label>
          <textarea 
            className="w-full bg-black border border-zinc-800 rounded-2xl p-4 md:p-6 text-sm focus:ring-1 focus:ring-blue-500 min-h-[200px] md:min-h-[250px] resize-none outline-none"
            placeholder="Ваше сообщение..."
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            disabled={sending}
          />
          <button 
            onClick={handleSend}
            disabled={sending || !message || selectedBotIds.length === 0}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white py-4 rounded-2xl font-black uppercase tracking-widest text-xs transition-all shadow-lg shadow-blue-600/20"
          >
            {sending ? 'Отправка...' : 'Запустить рассылку'}
          </button>
        </div>

        <div className="space-y-4">
          <h3 className="text-[10px] font-black text-zinc-500 uppercase tracking-widest px-2">Выберите ботов</h3>
          <div className="bg-[#111] border border-zinc-800 rounded-[1.5rem] md:rounded-[2rem] p-4 space-y-2 max-h-[300px] md:max-h-none overflow-y-auto no-scrollbar">
            {activeBots.map(bot => (
              <label 
                key={bot.id} 
                className={`flex items-center justify-between p-4 rounded-2xl cursor-pointer transition-all border ${selectedBotIds.includes(bot.id) ? 'bg-blue-600/10 border-blue-600/30' : 'bg-black border-zinc-900 hover:border-zinc-800'}`}
              >
                <span className="text-xs font-bold text-zinc-300 truncate pr-2">{bot.name}</span>
                <input type="checkbox" className="hidden" checked={selectedBotIds.includes(bot.id)} onChange={() => toggleBot(bot.id)} />
                <div className={`w-5 h-5 rounded-lg border flex items-center justify-center shrink-0 ${selectedBotIds.includes(bot.id) ? 'bg-blue-600 border-blue-600' : 'border-zinc-800'}`}>
                  {selectedBotIds.includes(bot.id) && <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" strokeWidth="3" /></svg>}
                </div>
              </label>
            ))}
            {activeBots.length === 0 && (
              <p className="text-[10px] text-zinc-600 text-center py-6 uppercase font-bold">Нет активных ботов</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default BroadcastManager;
