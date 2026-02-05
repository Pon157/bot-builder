
import React, { useState, useMemo } from 'react';
import { BotConfig, TelegramUser } from '../types';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts';
import { Users, UserMinus, Ban, UserCheck, Activity, AlertTriangle, Loader2, TrendingUp, ShieldCheck, Undo2, Search, RefreshCcw, Fingerprint } from 'lucide-react';
import { api } from '../services/apiService';

interface BotStatsViewProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
}

const BotStatsView: React.FC<BotStatsViewProps> = ({ bot, onUpdate }) => {
  const [isSyncing, setIsSyncing] = useState<number | null>(null);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<'all' | 'active' | 'banned' | 'unsubscribed'>('all');

  const stats = bot?.stats || { 
    totalMessages: 0, 
    incomingToday: 0, 
    outgoingToday: 0, 
    history: [] 
  };
  
  const safeHistory = useMemo(() => {
    if (Array.isArray(stats.history) && stats.history.length > 0) {
        return stats.history.map(pt => ({
            ...pt,
            incoming: pt.incoming || 0,
            outgoing: pt.outgoing || 0,
            totalUsers: pt.totalUsers || 0,
            activeUsers: pt.activeUsers || 0,
            date: pt.date || '??'
        }));
    }
    const today = new Date().toLocaleDateString('ru-RU', {day:'2-digit', month:'2-digit'});
    return [{ date: today, incoming: 0, outgoing: 0, totalUsers: 0, activeUsers: 0 }];
  }, [stats.history]);

  const connectedUsers = Array.isArray(bot?.connectedUsers) ? bot.connectedUsers : [];
  
  const filteredUsers = useMemo(() => {
    return connectedUsers.filter(u => {
        if (!u) return false;
        const anonId = u.id?.toString().slice(-6).toUpperCase() || '????';
        const matchesSearch = search === '' || 
            u.first_name?.toLowerCase().includes(search.toLowerCase()) || 
            u.username?.toLowerCase().includes(search.toLowerCase()) || 
            u.id?.toString().includes(search) || anonId.includes(search.toUpperCase());
        
        const matchesFilter = 
            filter === 'all' ? true :
            filter === 'active' ? (u.is_active && !u.is_banned) :
            filter === 'banned' ? u.is_banned :
            filter === 'unsubscribed' ? !u.is_active : true;
            
        return matchesSearch && matchesFilter;
    });
  }, [connectedUsers, search, filter]);

  const totalCount = connectedUsers.length;
  const bannedCount = connectedUsers.filter(u => u?.is_banned).length;
  const leavesCount = connectedUsers.filter(u => u && !u.is_active).length;
  const netActiveCount = connectedUsers.filter(u => u && u.is_active && !u.is_banned).length;

  const handleModeration = async (userId: number, action: 'unban' | 'warn' | 'unwarn' | 'ban') => {
    setIsSyncing(userId);
    try {
        const result = await api.moderateUser(bot.id, userId, action);
        if (result && result.status === 'ok') {
            const updatedUsers = connectedUsers.map(u => u.id === userId ? { ...u, ...result.user } : u);
            onUpdate({ ...bot, connectedUsers: updatedUsers });
        }
    } catch (e) { 
        alert("Ошибка модерации"); 
    } finally { 
        setIsSyncing(null); 
    }
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-12">
      {/* Статистические карточки */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Аудитория', value: totalCount, color: 'text-white', icon: Users, sub: 'Всего вступило', active: filter === 'all', onClick: () => setFilter('all') },
          { label: 'Живые', value: netActiveCount, color: 'text-emerald-400', icon: UserCheck, sub: 'Не в бане + Активны', active: filter === 'active', onClick: () => setFilter('active') },
          { label: 'Ливы', value: leavesCount, color: 'text-rose-500', icon: UserMinus, sub: 'Удалили бота', active: filter === 'unsubscribed', onClick: () => setFilter('unsubscribed') },
          { label: 'Бан-лист', value: bannedCount, color: 'text-amber-500', icon: Ban, sub: 'Заблокированы вами', active: filter === 'banned', onClick: () => setFilter('banned') },
        ].map((stat, i) => (
          <div 
            key={i} 
            className={`bg-[#111] border p-6 rounded-3xl relative overflow-hidden group cursor-pointer transition-all ${stat.active ? 'border-blue-500/50 shadow-[0_0_20px_rgba(59,130,246,0.1)]' : 'border-zinc-800'}`} 
            onClick={stat.onClick}
          >
            <stat.icon className={`absolute -right-4 -bottom-4 w-20 h-20 transition-colors ${stat.active ? 'text-blue-500/10' : 'text-white/5 group-hover:text-white/10'}`} />
            <div className="relative z-10">
              <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-1">{stat.label}</p>
              <p className={`text-4xl font-black ${stat.color}`}>{stat.value.toLocaleString()}</p>
              <p className="text-[9px] text-zinc-600 mt-2 font-medium">{stat.sub}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Графики */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] shadow-2xl">
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-sm font-bold text-white uppercase tracking-widest flex items-center gap-2">
              <Activity className="w-4 h-4 text-blue-500" /> Трафик сообщений
            </h3>
          </div>
          <div className="h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={safeHistory}>
                <CartesianGrid strokeDasharray="3 3" stroke="#222" vertical={false} />
                <XAxis dataKey="date" stroke="#444" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis stroke="#444" fontSize={10} tickLine={false} axisLine={false} />
                <Tooltip 
                    contentStyle={{ backgroundColor: '#111', border: '1px solid #333', borderRadius: '12px', fontSize: '12px' }}
                    itemStyle={{ fontSize: '10px', fontWeight: 'bold' }}
                />
                <Area type="monotone" dataKey="incoming" stroke="#3b82f6" fill="#3b82f633" strokeWidth={3} name="Входящие" />
                <Area type="monotone" dataKey="outgoing" stroke="#a855f7" fill="transparent" strokeWidth={2} name="Исходящие" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] shadow-2xl">
           <div className="flex items-center justify-between mb-8">
            <h3 className="text-sm font-bold text-white uppercase tracking-widest flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-emerald-500" /> Динамика аудитории
            </h3>
          </div>
          <div className="h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={safeHistory}>
                <CartesianGrid strokeDasharray="3 3" stroke="#222" vertical={false} />
                <XAxis dataKey="date" stroke="#444" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis stroke="#444" fontSize={10} tickLine={false} axisLine={false} />
                <Tooltip 
                    contentStyle={{ backgroundColor: '#111', border: '1px solid #333', borderRadius: '12px', fontSize: '12px' }}
                    itemStyle={{ fontSize: '10px', fontWeight: 'bold' }}
                />
                <Line type="monotone" dataKey="totalUsers" stroke="#10b981" strokeWidth={3} dot={false} name="Всего" />
                <Line type="monotone" dataKey="activeUsers" stroke="#52525b" strokeWidth={2} dot={false} strokeDasharray="5 5" name="Живых" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
      
      {/* Список пользователей и Модерация */}
      <div className="bg-[#111] border border-zinc-800 rounded-[2.5rem] overflow-hidden shadow-2xl">
        <div className="p-6 border-b border-zinc-800 space-y-4 bg-zinc-900/20">
          <div className="flex justify-between items-center">
            <h3 className="text-xs font-bold text-white uppercase flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-blue-500" /> Модерация пользователей
            </h3>
            <span className="text-[10px] text-zinc-600 font-bold uppercase tracking-tighter">
                <RefreshCcw className="w-3 h-3 inline mr-1" /> Auto-Sync Active
            </span>
          </div>
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1">
                <Search className="absolute left-4 top-3.5 w-4 h-4 text-zinc-600" />
                <input 
                    placeholder="Имя, ID или Anon ID (#XXXX)..." 
                    className="w-full bg-black border border-zinc-800 rounded-2xl py-3.5 pl-11 pr-4 text-xs text-white focus:border-blue-500 outline-none transition-all" 
                    value={search} 
                    onChange={e => setSearch(e.target.value)} 
                />
            </div>
            <div className="flex bg-black border border-zinc-800 rounded-2xl p-1">
                {(['all', 'active', 'banned', 'unsubscribed'] as const).map(f => (
                    <button 
                        key={f} 
                        onClick={() => setFilter(f)} 
                        className={`px-4 py-2 rounded-xl text-[10px] font-black uppercase transition-all ${filter === f ? 'bg-zinc-800 text-white' : 'text-zinc-600 hover:text-zinc-400'}`}
                    >
                        {f === 'all' ? 'Все' : f === 'active' ? 'Живые' : f === 'banned' ? 'Бан' : 'Лив'}
                    </button>
                ))}
            </div>
          </div>
        </div>
        <div className="max-h-[600px] overflow-y-auto no-scrollbar bg-black/40">
          {filteredUsers.length === 0 ? (
            <div className="p-20 text-center space-y-3 opacity-30">
                <Users className="w-12 h-12 mx-auto mb-2" />
                <p className="text-xs font-bold uppercase">Пользователей не найдено</p>
            </div>
          ) : (
            filteredUsers.map(u => (
              <div key={u.id} className="p-5 flex items-center justify-between border-b border-zinc-900 last:border-0 hover:bg-white/[0.02] transition-colors">
                <div className="flex items-center gap-4">
                  <div className={`w-12 h-12 rounded-2xl flex items-center justify-center text-sm font-black transition-all border ${!u.is_active ? 'bg-zinc-900 border-zinc-800 text-zinc-700' : u.is_banned ? 'bg-amber-500/10 border-amber-500/20 text-amber-500' : 'bg-blue-600/10 border-blue-600/20 text-blue-500'}`}>
                    {u.first_name?.charAt(0) || "U"}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                        <p className="text-sm font-bold text-white">{u.first_name || "Без имени"}</p>
                        {!u.is_active && <span className="text-[7px] bg-rose-500/10 text-rose-500 px-1.5 py-0.5 rounded font-black uppercase tracking-widest">Bot Blocked</span>}
                        {u.is_banned && <span className="text-[7px] bg-amber-500/10 text-amber-500 px-1.5 py-0.5 rounded font-black uppercase tracking-widest">Banned</span>}
                    </div>
                    <div className="text-[10px] text-zinc-500 font-mono mt-0.5 flex flex-wrap items-center gap-x-4 gap-y-1">
                        <span className="flex items-center gap-1"><Fingerprint className="w-3 h-3 opacity-40" /> #{u.id?.toString().slice(-6).toUpperCase() || '????'}</span>
                        <span>ID: <code>{u.id}</code></span>
                        {(u.warns || 0) > 0 && <span className="text-amber-500 font-black">[{u.warns} WARNS]</span>}
                    </div>
                  </div>
                </div>
                <div className="flex gap-2">
                    {isSyncing === u.id ? (
                        <div className="p-2.5"><Loader2 className="w-4 h-4 text-blue-500 animate-spin" /></div>
                    ) : u.is_banned ? (
                        <button 
                            onClick={() => handleModeration(u.id, 'unban')} 
                            className="text-[9px] font-black uppercase text-emerald-500 bg-emerald-500/10 px-5 py-2.5 rounded-xl border border-emerald-500/20 hover:bg-emerald-500/20 transition-all"
                        >
                            Разбанить
                        </button>
                    ) : (
                        <>
                            {(u.warns || 0) > 0 && (
                                <button 
                                    onClick={() => handleModeration(u.id, 'unwarn')} 
                                    className="p-3 bg-zinc-800 text-zinc-400 hover:text-white rounded-xl border border-zinc-700 transition-all"
                                    title="Снять варн"
                                >
                                    <Undo2 className="w-4 h-4" />
                                </button>
                            )}
                            <button 
                                onClick={() => handleModeration(u.id, 'warn')} 
                                className="p-3 bg-amber-500/10 text-amber-500 hover:bg-amber-500/20 rounded-xl border border-amber-500/20 transition-all"
                                title="Выдать варн"
                            >
                                <AlertTriangle className="w-4 h-4" />
                            </button>
                            <button 
                                onClick={() => handleModeration(u.id, 'ban')} 
                                className="p-3 bg-rose-500/10 text-rose-500 hover:bg-rose-500/20 rounded-xl border border-rose-500/20 transition-all"
                                title="Забанить"
                            >
                                <Ban className="w-4 h-4" />
                            </button>
                        </>
                    )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

export default BotStatsView;
