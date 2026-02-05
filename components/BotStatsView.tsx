
import React, { useState, useMemo } from 'react';
import { BotConfig, TelegramUser } from '../types';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts';
import { 
  Users, UserMinus, Ban, UserCheck, Activity, AlertTriangle, 
  Loader2, TrendingUp, ShieldCheck, Undo2, Search, Filter,
  ExternalLink, Mail, UserX, UserPlus
} from 'lucide-react';
import { api } from '../services/apiService';

interface BotStatsViewProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
}

const BotStatsView: React.FC<BotStatsViewProps> = ({ bot, onUpdate }) => {
  const [isSyncing, setIsSyncing] = useState<number | null>(null);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<'all' | 'active' | 'banned' | 'unsubscribed'>('all');

  const stats = bot.stats || { 
    totalMessages: 0, incomingToday: 0, outgoingToday: 0, 
    bannedCount: 0, history: [], activeUsers24h: 0 
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
    return [{ date: '01.01', incoming: 0, outgoing: 0, totalUsers: 0, activeUsers: 0 }];
  }, [stats.history]);

  const connectedUsers = Array.isArray(bot.connectedUsers) ? bot.connectedUsers : [];
  
  const filteredUsers = useMemo(() => {
    return connectedUsers.filter(u => {
      if (!u) return false;
      const searchLower = search.toLowerCase();
      const matchesSearch = 
        u.first_name?.toLowerCase().includes(searchLower) || 
        u.username?.toLowerCase().includes(searchLower) || 
        u.id.toString().includes(searchLower);
      
      const matchesFilter = 
        filter === 'all' ? true :
        filter === 'active' ? (u.is_active && !u.is_banned) :
        filter === 'banned' ? u.is_banned :
        filter === 'unsubscribed' ? !u.is_active : true;
      
      return matchesSearch && matchesFilter;
    });
  }, [connectedUsers, search, filter]);

  const counts = useMemo(() => ({
    total: connectedUsers.length,
    active: connectedUsers.filter(u => u.is_active && !u.is_banned).length,
    banned: connectedUsers.filter(u => u.is_banned).length,
    leaves: connectedUsers.filter(u => !u.is_active).length
  }), [connectedUsers]);

  const handleModeration = async (userId: number, action: 'unban' | 'warn' | 'unwarn' | 'ban') => {
    setIsSyncing(userId);
    try {
        const result = await api.moderateUser(bot.id, userId, action);
        if (result && result.status === 'ok') {
            const updatedUsers = connectedUsers.map(u => u.id === userId ? { ...u, ...result.user } : u);
            onUpdate({ ...bot, connectedUsers: updatedUsers });
        } else {
          // Fallback if API not fully ready
          const updatedUsers = connectedUsers.map(u => {
            if (u.id === userId) {
              if (action === 'ban') return { ...u, is_banned: true };
              if (action === 'unban') return { ...u, is_banned: false };
              if (action === 'warn') return { ...u, warns: (u.warns || 0) + 1 };
              if (action === 'unwarn') return { ...u, warns: Math.max(0, (u.warns || 0) - 1) };
            }
            return u;
          });
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
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Аудитория', value: counts.total, color: 'text-white', icon: Users, sub: 'Всего участников', f: 'all' },
          { label: 'Лояльные', value: counts.active, color: 'text-emerald-500', icon: UserCheck, sub: 'Активны + Без бана', f: 'active' },
          { label: 'Отписки', value: counts.leaves, color: 'text-rose-500', icon: UserMinus, sub: 'Заблокировали бота', f: 'unsubscribed' },
          { label: 'Черный список', value: counts.banned, color: 'text-amber-500', icon: Ban, sub: 'В бане навсегда', f: 'banned' },
        ].map((stat, i) => (
          <button 
            key={i} 
            onClick={() => setFilter(stat.f as any)}
            className={`bg-[#111] border p-6 rounded-3xl relative overflow-hidden group text-left transition-all ${filter === stat.f ? 'border-blue-500/50 ring-1 ring-blue-500/20' : 'border-zinc-800'}`}
          >
            <stat.icon className={`absolute -right-4 -bottom-4 w-20 h-20 transition-colors ${filter === stat.f ? 'text-blue-500/10' : 'text-white/5 group-hover:text-white/10'}`} />
            <div className="relative z-10">
              <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-1">{stat.label}</p>
              <p className={`text-4xl font-black ${stat.color}`}>{stat.value.toLocaleString()}</p>
              <p className="text-[9px] text-zinc-600 mt-2 font-medium">{stat.sub}</p>
            </div>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] shadow-2xl">
          <h3 className="text-sm font-bold text-white uppercase tracking-widest flex items-center gap-2 mb-8">
            <Activity className="w-4 h-4 text-blue-500" /> Активность узла
          </h3>
          <div className="h-[250px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={safeHistory}>
                <CartesianGrid strokeDasharray="3 3" stroke="#222" vertical={false} />
                <XAxis dataKey="date" stroke="#444" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis stroke="#444" fontSize={10} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={{ backgroundColor: '#111', border: '1px solid #333', borderRadius: '12px', fontSize: '12px' }} />
                <Area type="monotone" dataKey="incoming" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.1} strokeWidth={3} name="Входящие" />
                <Area type="monotone" dataKey="outgoing" stroke="#a855f7" fillOpacity={0} strokeWidth={2} name="Исходящие" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] shadow-2xl">
          <h3 className="text-sm font-bold text-white uppercase tracking-widest flex items-center gap-2 mb-8">
            <TrendingUp className="w-4 h-4 text-emerald-500" /> График роста
          </h3>
          <div className="h-[250px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={safeHistory}>
                <CartesianGrid strokeDasharray="3 3" stroke="#222" vertical={false} />
                <XAxis dataKey="date" stroke="#444" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis stroke="#444" fontSize={10} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={{ backgroundColor: '#111', border: '1px solid #333', borderRadius: '12px', fontSize: '12px' }} />
                <Line type="monotone" dataKey="totalUsers" stroke="#10b981" strokeWidth={3} dot={false} name="Всего" />
                <Line type="monotone" dataKey="activeUsers" stroke="#3b82f6" strokeWidth={2} dot={false} strokeDasharray="5 5" name="Актив" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
      
      <div className="bg-[#111] border border-zinc-800 rounded-[2.5rem] overflow-hidden shadow-2xl">
        <div className="p-8 border-b border-zinc-800 bg-zinc-900/20 space-y-6">
          <div className="flex justify-between items-center">
            <h3 className="text-sm font-black text-white uppercase flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-blue-500" /> Модерация и CRM
            </h3>
            <div className="flex bg-black p-1 rounded-xl border border-zinc-800">
              <button onClick={() => setFilter('all')} className={`px-4 py-1.5 rounded-lg text-[9px] font-black uppercase transition-all ${filter === 'all' ? 'bg-zinc-800 text-white' : 'text-zinc-600'}`}>Все</button>
              <button onClick={() => setFilter('active')} className={`px-4 py-1.5 rounded-lg text-[9px] font-black uppercase transition-all ${filter === 'active' ? 'bg-zinc-800 text-white' : 'text-zinc-600'}`}>Активные</button>
              <button onClick={() => setFilter('unsubscribed')} className={`px-4 py-1.5 rounded-lg text-[9px] font-black uppercase transition-all ${filter === 'unsubscribed' ? 'bg-zinc-800 text-white' : 'text-zinc-600'}`}>Ливы</button>
              <button onClick={() => setFilter('banned')} className={`px-4 py-1.5 rounded-lg text-[9px] font-black uppercase transition-all ${filter === 'banned' ? 'bg-zinc-800 text-white' : 'text-zinc-600'}`}>Бан</button>
            </div>
          </div>
          <div className="relative">
            <Search className="absolute left-5 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-600" />
            <input 
              placeholder="Поиск по имени, @username или ID..." 
              className="w-full bg-black border border-zinc-800 rounded-2xl py-4 pl-12 pr-6 text-sm text-white focus:border-blue-500 outline-none transition-all shadow-inner"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
        </div>

        <div className="max-h-[600px] overflow-y-auto no-scrollbar bg-black/40">
          {filteredUsers.length === 0 ? (
            <div className="p-24 text-center space-y-4 opacity-30">
              <Filter className="w-12 h-12 mx-auto" />
              <p className="text-[10px] font-black uppercase tracking-widest">Никого не найдено</p>
            </div>
          ) : (
            filteredUsers.map(u => (
              <div key={u.id} className="p-6 flex items-center justify-between border-b border-zinc-900/50 last:border-0 hover:bg-white/[0.01] transition-colors">
                <div className="flex items-center gap-5">
                  <div className={`w-14 h-14 rounded-2xl flex items-center justify-center text-lg font-black border-2 transition-all ${!u.is_active ? 'bg-zinc-900 border-zinc-800 text-zinc-700' : u.is_banned ? 'bg-rose-500/10 border-rose-500/30 text-rose-500' : 'bg-blue-600/10 border-blue-600/30 text-blue-500'}`}>
                    {u.first_name?.charAt(0) || "U"}
                  </div>
                  <div className="space-y-1">
                    <div className="flex items-center gap-3">
                        <p className="text-sm font-black text-white">{u.first_name || "Без имени"}</p>
                        {!u.is_active && <span className="text-[7px] bg-rose-500/10 text-rose-500 px-2 py-0.5 rounded-md font-black uppercase tracking-tighter">Left Bot</span>}
                        {u.is_banned && <span className="text-[7px] bg-amber-500/10 text-amber-500 px-2 py-0.5 rounded-md font-black uppercase tracking-tighter">Banned</span>}
                    </div>
                    <div className="flex items-center gap-4">
                      <p className="text-[10px] text-zinc-500 font-mono">ID: {u.id} {u.username && <span className="text-blue-500/60 ml-1">@{u.username}</span>}</p>
                      {(u.warns || 0) > 0 && <span className="text-[9px] text-amber-500 bg-amber-500/5 px-2 rounded font-black border border-amber-500/10">{u.warns} WARNS</span>}
                    </div>
                  </div>
                </div>
                <div className="flex gap-2">
                    {isSyncing === u.id ? <Loader2 className="w-5 h-5 text-blue-500 animate-spin m-2" /> : (
                        u.is_banned ? (
                            <button onClick={() => handleModeration(u.id, 'unban')} className="text-[10px] font-black uppercase text-emerald-500 bg-emerald-500/10 px-6 py-3 rounded-xl border border-emerald-500/20 hover:bg-emerald-500/20 transition-all">Разбанить</button>
                        ) : (
                            <div className="flex gap-2">
                                {(u.warns || 0) > 0 && (
                                    <button onClick={() => handleModeration(u.id, 'unwarn')} className="p-3 bg-zinc-800 text-zinc-400 hover:text-white rounded-xl border border-zinc-700" title="Снять 1 варн"><Undo2 className="w-5 h-5" /></button>
                                )}
                                <button onClick={() => handleModeration(u.id, 'warn')} className="p-3 bg-amber-500/10 text-amber-500 hover:bg-amber-500/20 rounded-xl border border-amber-500/30" title="Выдать варн"><AlertTriangle className="w-5 h-5" /></button>
                                <button onClick={() => handleModeration(u.id, 'ban')} className="p-3 bg-rose-500/10 text-rose-500 hover:bg-rose-500/20 rounded-xl border border-rose-500/30" title="Заблокировать навсегда"><Ban className="w-5 h-5" /></button>
                            </div>
                        )
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
