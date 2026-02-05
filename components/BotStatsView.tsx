
import React, { useState } from 'react';
import { BotConfig, TelegramUser } from '../types';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts';
import { Users, UserMinus, Ban, UserCheck, Activity, AlertTriangle, Loader2, TrendingUp, ShieldCheck, Undo2 } from 'lucide-react';
import { api } from '../services/apiService';

interface BotStatsViewProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
}

const BotStatsView: React.FC<BotStatsViewProps> = ({ bot, onUpdate }) => {
  const [isSyncing, setIsSyncing] = useState<number | null>(null);

  const stats = bot.stats || { 
    totalMessages: 0, 
    incomingToday: 0, 
    outgoingToday: 0, 
    bannedCount: 0, 
    history: [], 
    activeUsers24h: 0 
  };
  
  const safeHistory = Array.isArray(stats.history) && stats.history.length > 0 
    ? stats.history.map(pt => ({
        ...pt,
        incoming: pt.incoming || 0,
        outgoing: pt.outgoing || 0,
        totalUsers: pt.totalUsers || 0,
        date: pt.date || '??'
      }))
    : [{ date: new Date().toLocaleDateString('ru-RU', {day:'2-digit', month:'2-digit'}), incoming: 0, outgoing: 0, totalUsers: 0 }];

  const connectedUsers = Array.isArray(bot.connectedUsers) ? bot.connectedUsers : [];
  const totalCount = connectedUsers.length;
  const bannedCount = connectedUsers.filter(u => u && u.is_banned).length;
  const blockedByMeCount = connectedUsers.filter(u => u && !u.is_active).length;
  const netActiveCount = connectedUsers.filter(u => u && u.is_active && !u.is_banned).length;

  const handleModeration = async (userId: number, action: 'unban' | 'warn' | 'unwarn' | 'ban') => {
    setIsSyncing(userId);
    const updatedUsers = connectedUsers.map(u => {
      if (u && u.id === userId) {
        if (action === 'unban') return { ...u, is_banned: false };
        if (action === 'ban') return { ...u, is_banned: true };
        if (action === 'warn') return { ...u, warns: (u.warns || 0) + 1 };
        if (action === 'unwarn') return { ...u, warns: Math.max(0, (u.warns || 0) - 1) };
      }
      return u;
    });
    
    const updatedBot = { ...bot, connectedUsers: updatedUsers };
    try {
        await api.saveBot(bot.owner_id, updatedBot);
        onUpdate(updatedBot);
    } catch (e) { alert("Ошибка сохранения данных"); }
    finally { setIsSyncing(null); }
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-12">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Всего вступило', value: totalCount, color: 'text-white', icon: Users, sub: 'За все время' },
          { label: 'Чистая база', value: netActiveCount, color: 'text-emerald-500', icon: UserCheck, sub: 'Живые + Не в бане' },
          { label: 'Отписались', value: blockedByMeCount, color: 'text-rose-500', icon: UserMinus, sub: 'Заблокировали бота' },
          { label: 'В черном списке', value: bannedCount, color: 'text-amber-500', icon: Ban, sub: 'Забанены вами' },
        ].map((stat, i) => (
          <div key={i} className="bg-[#111] border border-zinc-800 p-6 rounded-3xl relative overflow-hidden group">
            <stat.icon className="absolute -right-4 -bottom-4 w-20 h-20 text-white/5 group-hover:text-white/10 transition-colors" />
            <div className="relative z-10">
              <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-1">{stat.label}</p>
              <p className={`text-4xl font-black ${stat.color}`}>{stat.value.toLocaleString()}</p>
              <p className="text-[9px] text-zinc-600 mt-2 font-medium">{stat.sub}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem] shadow-2xl">
          <h3 className="text-sm font-bold text-white uppercase tracking-widest flex items-center gap-2 mb-8">
            <Activity className="w-4 h-4 text-blue-500" /> Активность (сообщения)
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
            <TrendingUp className="w-4 h-4 text-emerald-500" /> Рост аудитории
          </h3>
          <div className="h-[250px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={safeHistory}>
                <CartesianGrid strokeDasharray="3 3" stroke="#222" vertical={false} />
                <XAxis dataKey="date" stroke="#444" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis stroke="#444" fontSize={10} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={{ backgroundColor: '#111', border: '1px solid #333', borderRadius: '12px', fontSize: '12px' }} />
                <Line type="monotone" dataKey="totalUsers" stroke="#10b981" strokeWidth={3} dot={false} name="Пользователи" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
      
      <div className="bg-[#111] border border-zinc-800 rounded-[2.5rem] overflow-hidden">
        <div className="p-6 border-b border-zinc-800 flex justify-between items-center bg-zinc-900/20">
          <h3 className="text-xs font-bold text-white uppercase flex items-center gap-2">
            <Users className="w-4 h-4 text-blue-500" /> Управление пользователями
          </h3>
          <span className="text-[10px] text-zinc-500 font-mono">SYNCED WITH BOT</span>
        </div>
        <div className="max-h-[500px] overflow-y-auto no-scrollbar">
          {connectedUsers.length === 0 ? (
            <div className="p-20 text-center text-[10px] font-bold text-zinc-700 uppercase">Пользователей пока нет</div>
          ) : (
            connectedUsers.map(u => (
              <div key={u.id} className={`p-5 flex items-center justify-between border-b border-zinc-900/50 last:border-0 hover:bg-white/[0.02] transition-colors ${u.is_banned ? 'bg-red-500/[0.03]' : ''}`}>
                <div className="flex items-center gap-4">
                  <div className={`w-10 h-10 rounded-2xl flex items-center justify-center text-sm font-black transition-all ${!u.is_active ? 'bg-zinc-800 text-zinc-600' : u.is_banned ? 'bg-amber-500/10 text-amber-500' : 'bg-blue-600/10 text-blue-500'}`}>
                    {u.first_name?.charAt(0) || "U"}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                        <p className="text-sm font-bold text-white">{u.first_name || "Без имени"}</p>
                        {u.is_banned && <span className="text-[8px] bg-rose-500/10 text-rose-500 px-1.5 py-0.5 rounded font-black uppercase tracking-widest">Banned</span>}
                    </div>
                    <p className="text-[10px] text-zinc-500 font-mono mt-0.5">ID: {u.id} {u.username && `@${u.username}`} {(u.warns || 0) > 0 && <span className="text-amber-500 ml-2 font-black">[{u.warns} WARNS]</span>}</p>
                  </div>
                </div>
                <div className="flex gap-2">
                    {isSyncing === u.id ? <Loader2 className="w-4 h-4 text-zinc-500 animate-spin" /> : (
                        u.is_banned ? (
                            <button onClick={() => handleModeration(u.id, 'unban')} className="text-[9px] font-black uppercase text-emerald-500 bg-emerald-500/10 px-4 py-2 rounded-xl border border-emerald-500/20">Разбанить</button>
                        ) : (
                            <>
                                {(u.warns || 0) > 0 && (
                                    <button onClick={() => handleModeration(u.id, 'unwarn')} className="p-2.5 bg-zinc-800 text-zinc-400 hover:text-white rounded-xl border border-zinc-700" title="Снять 1 варн"><Undo2 className="w-4 h-4" /></button>
                                )}
                                <button onClick={() => handleModeration(u.id, 'warn')} className="p-2.5 bg-amber-500/10 text-amber-500 rounded-xl border border-amber-500/20" title="Выдать варн"><AlertTriangle className="w-4 h-4" /></button>
                                <button onClick={() => handleModeration(u.id, 'ban')} className="p-2.5 bg-rose-500/10 text-rose-500 rounded-xl border border-rose-500/20" title="Забанить"><Ban className="w-4 h-4" /></button>
                            </>
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
