
import React from 'react';
import { BotConfig, User } from '../types';
import { ShieldCheck, LayoutDashboard, Radio, UserCircle, LogOut, Plus } from 'lucide-react';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: any) => void;
  bots: BotConfig[];
  selectedBotId: string | null;
  setSelectedBotId: (id: string) => void;
  onAddBot: () => void;
  user: User;
  onLogout: () => void;
  isOpen?: boolean;
}

const Sidebar: React.FC<SidebarProps> = ({ activeTab, setActiveTab, bots, selectedBotId, setSelectedBotId, onAddBot, user, onLogout, isOpen }) => {
  const expiry = Number(user.license_expires_at || 0);
  const daysRemaining = Math.max(0, Math.ceil((expiry - Date.now()) / (1000 * 60 * 60 * 24)));

  return (
    <aside className={`
      fixed inset-y-0 left-0 z-50 w-72 bg-[#121212] border-r border-zinc-800 flex flex-col h-full transition-transform duration-300 ease-in-out
      md:relative md:translate-x-0
      ${isOpen ? 'translate-x-0' : '-translate-x-full'}
    `}>
      <div className="p-6 border-b border-zinc-800 flex items-center gap-3">
        <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
            <span className="font-bold text-white text-xs">BE</span>
        </div>
        <h1 className="text-xl font-bold tracking-tight text-white">BotEngine<span className="text-blue-500 text-sm ml-1 uppercase">Pro</span></h1>
      </div>

      <nav className="flex-1 overflow-y-auto p-4 space-y-8 no-scrollbar">
        <div>
            <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-4 px-2">Главное</h2>
            <ul className="space-y-1">
                <li 
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-xl cursor-pointer transition-colors ${activeTab === 'dashboard' ? 'bg-zinc-800 text-white' : 'text-zinc-400 hover:bg-zinc-900'}`}
                    onClick={() => setActiveTab('dashboard')}
                >
                    <LayoutDashboard size={18} />
                    Дашборд
                </li>
                <li 
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-xl cursor-pointer transition-colors ${activeTab === 'broadcast' ? 'bg-zinc-800 text-white' : 'text-zinc-400 hover:bg-zinc-900'}`}
                    onClick={() => setActiveTab('broadcast')}
                >
                    <Radio size={18} />
                    Рассылка
                </li>
                <li 
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-xl cursor-pointer transition-colors ${activeTab === 'profile' ? 'bg-zinc-800 text-white' : 'text-zinc-400 hover:bg-zinc-900'}`}
                    onClick={() => setActiveTab('profile')}
                >
                    <UserCircle size={18} />
                    Профиль и Ключ
                </li>
            </ul>
        </div>

        <div>
            <div className="flex items-center justify-between mb-4 px-2">
                <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">Ваши боты</h2>
                <button 
                    onClick={onAddBot}
                    className="p-1 hover:bg-zinc-800 rounded-md transition-colors text-blue-500"
                >
                    <Plus size={16} />
                </button>
            </div>
            <ul className="space-y-1">
                {bots.map(bot => (
                    <li 
                        key={bot.id}
                        className={`flex items-center gap-3 px-3 py-2.5 rounded-xl cursor-pointer transition-all ${selectedBotId === bot.id && activeTab === 'editor' ? 'bg-blue-600/10 text-blue-400 border border-blue-600/20' : 'text-zinc-400 hover:bg-zinc-900 border border-transparent'}`}
                        onClick={() => { setSelectedBotId(bot.id); setActiveTab('editor'); }}
                    >
                        <div className={`w-2 h-2 rounded-full shrink-0 ${bot.status === 'RUNNING' ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.5)]' : 'bg-zinc-600'}`}></div>
                        <span className="truncate flex-1 text-sm">{bot.name}</span>
                    </li>
                ))}
            </ul>
        </div>
      </nav>

      <div className="p-4 border-t border-zinc-800 shrink-0 space-y-4">
        <div className="flex items-center justify-center gap-2 bg-emerald-500/5 py-2 rounded-xl border border-emerald-500/10">
          <ShieldCheck className="w-3 h-3 text-emerald-500" />
          <span className="text-[9px] font-black uppercase text-emerald-500 tracking-wider">Secured by RLS</span>
        </div>
        
        <div className="flex items-center justify-between p-3 rounded-2xl bg-zinc-900/50 border border-zinc-800/50">
            <div className="flex items-center gap-2 overflow-hidden">
                <div className="w-9 h-9 rounded-xl bg-blue-600/20 text-blue-500 flex items-center justify-center text-sm font-bold shrink-0">
                    {user.username.charAt(0).toUpperCase()}
                </div>
                <div className="truncate">
                    <p className="text-xs font-bold text-white truncate">{user.username}</p>
                    <p className={`text-[10px] truncate font-bold ${daysRemaining < 3 ? 'text-red-500' : 'text-zinc-500'}`}>
                        {daysRemaining} дн. доступа
                    </p>
                </div>
            </div>
            <button 
                onClick={onLogout}
                className="p-2 hover:bg-red-500/10 text-zinc-500 hover:text-red-500 rounded-lg transition-all"
            >
                <LogOut size={16} />
            </button>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
