import React from 'react';
import { BotConfig, User } from '../types';
import { api } from '../services/apiService';
import { 
  LayoutDashboard, 
  Send, 
  UserCircle, 
  Plus, 
  LogOut, 
  ShieldCheck, 
  Bot,
  Terminal
} from 'lucide-react';

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

const Sidebar: React.FC<SidebarProps> = ({ 
  activeTab, 
  setActiveTab, 
  bots, 
  selectedBotId, 
  setSelectedBotId, 
  onAddBot, 
  user, 
  onLogout, 
  isOpen 
}) => {
  const expiry = Number(user.license_expires_at) || 0;
  const daysRemaining = Math.max(0, Math.ceil((expiry - Date.now()) / (1000 * 60 * 60 * 24)));

  // Функция для создания временного ключа доступа администратору
  const createSupportKey = async () => {
    if (!selectedBotId) return;
    
    // Генерируем случайный короткий ключ
    const key = Math.random().toString(36).substring(2, 8).toUpperCase();
    
    try {
      await api.createTempAccess(selectedBotId, key);
      alert(`Ключ доступа создан: ${key}\n\nПередайте этот ключ администратору. Доступ к редактору этого бота будет открыт в течение 20 минут.`);
    } catch (e) {
      console.error("Support key error:", e);
      alert("Не удалось создать ключ доступа. Попробуйте позже.");
    }
  };

  return (
    <aside className={`
      fixed inset-y-0 left-0 z-50 w-72 bg-[#121212] border-r border-zinc-800 flex flex-col h-full transition-transform duration-300 ease-in-out
      md:relative md:translate-x-0
      ${isOpen ? 'translate-x-0' : '-translate-x-full'}
    `}>
      {/* Логотип */}
      <div className="p-6 border-b border-zinc-800 flex items-center gap-3">
        <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center shadow-lg shadow-blue-600/20">
            <Terminal size={18} className="text-white" />
        </div>
        <h1 className="text-xl font-bold tracking-tight text-white italic">
            Dialoge<span className="text-blue-500 not-italic">Engine</span>
        </h1>
      </div>

      <nav className="flex-1 overflow-y-auto p-4 space-y-8 no-scrollbar">
        {/* Главное меню */}
        <div>
            <h2 className="text-[10px] font-black text-zinc-600 uppercase tracking-[0.2em] mb-4 px-2">Консоль</h2>
            <ul className="space-y-1">
                <li 
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-xl cursor-pointer transition-all font-medium text-sm ${activeTab === 'dashboard' ? 'bg-zinc-800 text-white shadow-inner' : 'text-zinc-400 hover:bg-zinc-900'}`}
                    onClick={() => setActiveTab('dashboard')}
                >
                    <LayoutDashboard size={18} />
                    Дашборд
                </li>
                <li 
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-xl cursor-pointer transition-all font-medium text-sm ${activeTab === 'broadcast' ? 'bg-zinc-800 text-white shadow-inner' : 'text-zinc-400 hover:bg-zinc-900'}`}
                    onClick={() => setActiveTab('broadcast')}
                >
                    <Send size={18} />
                    Рассылка
                </li>
                <li 
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-xl cursor-pointer transition-all font-medium text-sm ${activeTab === 'profile' ? 'bg-zinc-800 text-white shadow-inner' : 'text-zinc-400 hover:bg-zinc-900'}`}
                    onClick={() => setActiveTab('profile')}
                >
                    <UserCircle size={18} />
                    Профиль и Лицензия
                </li>
            </ul>
        </div>

        {/* Секция ботов */}
        <div>
            <div className="flex items-center justify-between mb-4 px-2">
                <h2 className="text-[10px] font-black text-zinc-600 uppercase tracking-[0.2em]">Ваши проекты</h2>
                <button 
                    onClick={onAddBot}
                    className="p-1 hover:bg-blue-600/10 rounded-md transition-colors text-blue-500"
                    title="Создать бота"
                >
                    <Plus size={18} />
                </button>
            </div>
            <ul className="space-y-1">
                {bots.length === 0 ? (
                  <p className="px-2 py-4 text-[10px] text-zinc-700 font-bold uppercase tracking-widest text-center border border-dashed border-zinc-800 rounded-xl">
                    Нет активных ботов
                  </p>
                ) : bots.map(bot => (
                    <li 
                        key={bot.id}
                        className={`flex items-center gap-3 px-3 py-2.5 rounded-xl cursor-pointer transition-all border ${selectedBotId === bot.id && activeTab === 'editor' ? 'bg-blue-600/10 text-blue-400 border-blue-600/20 shadow-lg shadow-blue-900/5' : 'text-zinc-400 hover:bg-zinc-900 border-transparent'}`}
                        onClick={() => { setSelectedBotId(bot.id); setActiveTab('editor'); }}
                    >
                        <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${bot.status === 'RUNNING' ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]' : 'bg-zinc-700'}`}></div>
                        <span className="truncate flex-1 text-sm font-medium">{bot.name}</span>
                        {selectedBotId === bot.id && <Bot size={14} className="opacity-40" />}
                    </li>
                ))}
            </ul>
        </div>

        {/* Кнопка доступа для поддержки */}
        {selectedBotId && activeTab === 'editor' && (
            <div className="px-2 pt-4">
                <button 
                    onClick={createSupportKey}
                    className="w-full flex items-center justify-center gap-2 py-3 bg-orange-500/5 border border-orange-500/10 rounded-xl text-orange-500/70 hover:text-orange-500 hover:bg-orange-500/10 hover:border-orange-500/30 transition-all group"
                >
                    <ShieldCheck size={16} className="group-hover:scale-110 transition-transform" />
                    <span className="text-[10px] font-black uppercase tracking-tighter">Доступ поддержке</span>
                </button>
            </div>
        )}
      </nav>

      {/* Футер пользователя */}
      <div className="p-4 border-t border-zinc-800 shrink-0 bg-[#121212]">
        <div className="flex items-center justify-between p-3 rounded-2xl bg-zinc-900/50 border border-zinc-800/50 backdrop-blur-md">
            <div className="flex items-center gap-2 overflow-hidden">
                <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-700 text-white flex items-center justify-center text-sm font-black shrink-0 shadow-lg">
                    {user.username.charAt(0).toUpperCase()}
                </div>
                <div className="truncate">
                    <p className="text-xs font-bold text-white truncate leading-none mb-1">{user.username}</p>
                    <div className="flex items-center gap-1.5">
                        <div className={`w-1 h-1 rounded-full ${daysRemaining < 3 ? 'bg-red-500 animate-pulse' : 'bg-blue-500'}`}></div>
                        <p className={`text-[9px] truncate font-black uppercase tracking-tighter ${daysRemaining < 3 ? 'text-red-500' : 'text-zinc-500'}`}>
                            {daysRemaining} дн. доступа
                        </p>
                    </div>
                </div>
            </div>
            <button 
                onClick={onLogout}
                className="p-2 hover:bg-red-500/10 text-zinc-600 hover:text-red-500 rounded-lg transition-all active:scale-90"
                title="Выйти"
            >
                <LogOut size={18} />
            </button>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
