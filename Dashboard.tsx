
import React from 'react';
import { BotConfig } from '../types';

interface DashboardProps {
  bots: BotConfig[];
  onSelectBot: (id: string) => void;
  onAddBot: () => void;
}

const Dashboard: React.FC<DashboardProps> = ({ bots, onSelectBot, onAddBot }) => {
  const totalUsers = bots.reduce((acc, b) => acc + b.usersCount, 0);
  const activeBots = bots.filter(b => b.status === 'RUNNING').length;

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <header>
        <h1 className="text-3xl font-bold mb-2">System Overview</h1>
        <p className="text-zinc-400">Manage your autonomous bot network and traffic analytics.</p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-[#121212] p-6 rounded-2xl border border-zinc-800">
            <p className="text-zinc-500 text-sm font-medium uppercase tracking-wider mb-2">Total Bots</p>
            <p className="text-4xl font-bold text-white">{bots.length}</p>
        </div>
        <div className="bg-[#121212] p-6 rounded-2xl border border-zinc-800">
            <p className="text-zinc-500 text-sm font-medium uppercase tracking-wider mb-2">Total Users Reach</p>
            <p className="text-4xl font-bold text-white">{totalUsers.toLocaleString()}</p>
        </div>
        <div className="bg-[#121212] p-6 rounded-2xl border border-zinc-800 border-b-blue-500/50">
            <p className="text-zinc-500 text-sm font-medium uppercase tracking-wider mb-2">Active Instances</p>
            <p className="text-4xl font-bold text-blue-500">{activeBots}</p>
        </div>
      </div>

      <section>
        <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-bold">Recent Instances</h2>
        </div>
        
        {bots.length === 0 ? (
            <div className="bg-[#121212] border-2 border-dashed border-zinc-800 rounded-3xl p-20 text-center">
                <div className="mx-auto w-16 h-16 bg-blue-600/10 rounded-2xl flex items-center justify-center mb-6 text-blue-500">
                  <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </div>
                <h3 className="text-xl font-bold text-white mb-2">No active bots found</h3>
                <p className="text-zinc-500 mb-8 max-w-xs mx-auto text-sm">Create your first autonomous instance to start managing interactions and automated flows.</p>
                <button 
                  onClick={onAddBot}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-3 rounded-xl font-bold transition-all shadow-lg shadow-blue-600/20"
                >
                    Create Your First Bot
                </button>
            </div>
        ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {bots.map(bot => (
                    <div 
                        key={bot.id}
                        className="group bg-[#121212] border border-zinc-800 rounded-2xl p-6 hover:border-zinc-700 transition-all cursor-pointer"
                        onClick={() => onSelectBot(bot.id)}
                    >
                        <div className="flex justify-between items-start mb-4">
                            <div className={`p-2 rounded-lg ${bot.status === 'RUNNING' ? 'bg-green-500/10 text-green-500' : 'bg-zinc-800 text-zinc-400'}`}>
                                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                            </div>
                            <span className={`text-[10px] px-2 py-0.5 rounded-full uppercase font-bold ${bot.status === 'RUNNING' ? 'bg-green-500/20 text-green-400' : 'bg-zinc-800 text-zinc-500'}`}>
                                {bot.status}
                            </span>
                        </div>
                        <h3 className="text-lg font-bold mb-1 group-hover:text-blue-400 transition-colors text-white">{bot.name}</h3>
                        <p className="text-zinc-500 text-sm mb-4 line-clamp-1">{bot.description}</p>
                        <div className="flex items-center gap-4 text-xs text-zinc-400">
                            <span className="flex items-center gap-1">
                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                                {bot.usersCount} users
                            </span>
                            <span className="flex items-center gap-1">
                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                                {/* Use optional chaining to safely access actions array length */}
                                {bot.actions?.length || 0} flows
                            </span>
                        </div>
                    </div>
                ))}
            </div>
        )}
      </section>
    </div>
  );
};

export default Dashboard;
