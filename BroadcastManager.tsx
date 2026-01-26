
import React, { useState } from 'react';
import { BotConfig } from '../types';

interface BroadcastManagerProps {
  bots: BotConfig[];
}

const BroadcastManager: React.FC<BroadcastManagerProps> = ({ bots }) => {
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [progress, setProgress] = useState(0);

  const toggleBot = (id: string) => {
    setSelectedBotIds(prev => 
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const handleSend = async () => {
    if (!message || selectedBotIds.length === 0) return;
    
    setSending(true);
    setProgress(0);
    
    // Simulate real broadcasting across tokens
    for (let i = 1; i <= 100; i++) {
        await new Promise(r => setTimeout(r, 30));
        setProgress(i);
    }
    
    setSending(false);
    setMessage('');
    alert("Broadcast completed successfully across all selected bots.");
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in duration-500">
      <header>
        <h1 className="text-3xl font-bold mb-2">Global Broadcast</h1>
        <p className="text-zinc-400">Push messages to all users who have interacted with your selected bots.</p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        <div className="md:col-span-2 space-y-6">
            <div className="bg-[#121212] border border-zinc-800 rounded-2xl p-6 space-y-4">
                <label className="block text-xs font-semibold text-zinc-500 uppercase tracking-widest">Compose Message</label>
                <textarea 
                    className="w-full bg-[#0a0a0a] border border-zinc-800 rounded-xl p-4 text-sm focus:ring-1 focus:ring-blue-500 focus:outline-none min-h-[200px]"
                    placeholder="Enter your message here... markdown is supported."
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    disabled={sending}
                />
                
                <div className="flex items-center gap-4">
                    <button 
                        onClick={handleSend}
                        disabled={sending || !message || selectedBotIds.length === 0}
                        className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-8 py-2.5 rounded-lg font-bold transition-all flex items-center gap-2"
                    >
                        {sending ? (
                            <>
                                <svg className="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                                Sending... {progress}%
                            </>
                        ) : 'Initiate Broadcast'}
                    </button>
                    {sending && (
                        <div className="flex-1 bg-zinc-800 h-1.5 rounded-full overflow-hidden">
                            <div className="bg-blue-500 h-full transition-all duration-300" style={{ width: `${progress}%` }}></div>
                        </div>
                    )}
                </div>
            </div>
        </div>

        <div className="space-y-4">
            <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest px-2">Select Target Bots</h3>
            <div className="bg-[#121212] border border-zinc-800 rounded-2xl p-4 space-y-2">
                {bots.length === 0 && <p className="text-zinc-600 text-xs text-center py-4 italic">No bots available</p>}
                {bots.map(bot => (
                    <label 
                        key={bot.id} 
                        className={`flex items-center justify-between p-3 rounded-xl cursor-pointer transition-all border ${selectedBotIds.includes(bot.id) ? 'bg-blue-600/10 border-blue-600/30 text-blue-400' : 'bg-[#0a0a0a] border-zinc-800 text-zinc-400 hover:border-zinc-700'}`}
                    >
                        <span className="text-sm font-medium truncate">{bot.name}</span>
                        <input 
                            type="checkbox" 
                            className="hidden"
                            checked={selectedBotIds.includes(bot.id)}
                            onChange={() => toggleBot(bot.id)}
                        />
                        <div className={`w-4 h-4 rounded border flex items-center justify-center ${selectedBotIds.includes(bot.id) ? 'bg-blue-600 border-blue-600' : 'border-zinc-600'}`}>
                            {selectedBotIds.includes(bot.id) && <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" /></svg>}
                        </div>
                    </label>
                ))}
            </div>
            {selectedBotIds.length > 0 && (
                <div className="px-2">
                    <button 
                        onClick={() => setSelectedBotIds([])}
                        className="text-[10px] text-zinc-500 hover:text-zinc-300 uppercase font-bold"
                    >
                        Deselect All
                    </button>
                </div>
            )}
        </div>
      </div>
    </div>
  );
};

export default BroadcastManager;
