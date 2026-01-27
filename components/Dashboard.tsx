
import React from 'react';
import { BotConfig } from '../types';

interface DashboardProps {
  bots: BotConfig[];
  onSelectBot: (id: string) => void;
  onAddBot: () => void;
}

const Dashboard: React.FC<DashboardProps> = ({ bots, onSelectBot, onAddBot }) => {
  const totalUsers = bots.reduce((acc, b) => acc + (b.connectedUsers?.length || 0), 0);
  const totalMessages = bots.reduce((acc, b) => acc + (b.stats?.totalMessages || 0), 0);
  const activeBots = bots.filter(b => b.status === 'RUNNING').length;

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <header>
        <h1 className="text-4xl font-black mb-2 text-white">Управление узлами</h1>
        <p className="text-zinc-500 text-sm font-medium">Централизованный контроль вашей сети Telegram-ботов.</p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-[#111] p-8 rounded-[2.5rem] border border-zinc-800">
            <p className="text-zinc-500 text-[10px] font-bold uppercase tracking-widest mb-4">Активные инстансы</p>
            <div className="flex items-end gap-2">
                <p className="text-5xl font-black text-white">{activeBots}</p>
                <p className="text-zinc-700 font-bold mb-1">/ {bots.length}</p>
            </div>
        </div>
        <div className="bg-[#111] p-8 rounded-[2.5rem] border border-zinc-800">
            <p className="text-zinc-500 text-[10px] font-bold uppercase tracking-widest mb-4">Общий охват (Users)</p>
            <p className="text-5xl font-black text-blue-500">{totalUsers.toLocaleString()}</p>
        </div>
        <div className="bg-[#111] p-8 rounded-[2.5rem] border border-zinc-800">
            <p className="text-zinc-500 text-[10px] font-bold uppercase tracking-widest mb-4">Всего транзакций</p>
            <p className="text-5xl font-black text-white">{totalMessages.toLocaleString()}</p>
        </div>
      </div>

      <section className="space-y-6">
        <div className="flex items-center justify-between">
            <h2 className="text-xl font-black text-white">Ваши боты</h2>
            <button onClick={onAddBot} className="text-blue-500 text-xs font-bold uppercase tracking-widest hover:underline">+ Создать новый</button>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {bots.map(bot => (
                <div 
                    key={bot.id}
                    className="bg-[#111] border border-zinc-800 rounded-[2.5rem] p-8 hover:border-blue-500/50 transition-all cursor-pointer group"
                    onClick={() => onSelectBot(bot.id)}
                >
                    <div className="flex justify-between items-start mb-6">
                        <div className={`w-12 h-12 rounded-2xl flex items-center justify-center ${bot.status === 'RUNNING' ? 'bg-green-500/10 text-green-500' : 'bg-zinc-900 text-zinc-600'}`}>
                            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                        </div>
                        <span className={`text-[9px] px-3 py-1 rounded-full font-black uppercase ${bot.status === 'RUNNING' ? 'bg-green-500/10 text-green-500' : 'bg-zinc-800 text-zinc-500'}`}>
                            {bot.status}
                        </span>
                    </div>
                    <h3 className="text-xl font-black text-white mb-2 group-hover:text-blue-500 transition-colors">{bot.name}</h3>
                    <div className="flex items-center gap-6 mt-6 pt-6 border-t border-zinc-800/50">
                        <div className="text-center">
                            <p className="text-lg font-black text-white">{bot.connectedUsers?.length || 0}</p>
                            <p className="text-[8px] text-zinc-600 uppercase font-bold">Users</p>
                        </div>
                        <div className="text-center">
                            <p className="text-lg font-black text-white">{bot.stats?.totalMessages || 0}</p>
                            <p className="text-[8px] text-zinc-600 uppercase font-bold">Msgs</p>
                        </div>
                    </div>
                </div>
            ))}
        </div>
      </section>
    </div>
  );
};

export default Dashboard;
