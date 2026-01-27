
import React from 'react';
import { BotConfig, TelegramUser } from '../types';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Users, MessageSquare, Ban, Activity, ShieldAlert, ShieldCheck, AlertTriangle } from 'lucide-react';
import { api } from '../services/apiService';

interface BotStatsViewProps {
  bot: BotConfig;
}

const BotStatsView: React.FC<BotStatsViewProps> = ({ bot }) => {
  const stats = bot.stats || { 
    totalMessages: 0, 
    incomingToday: 0, 
    outgoingToday: 0, 
    bannedCount: 0, 
    history: [], 
    activeUsers24h: 0 
  };
  
  const chartData = stats.history.length > 0 ? stats.history : [
    { date: new Date().toLocaleDateString(), incoming: 0, outgoing: 0 }
  ];

  const bannedUsers = bot.connectedUsers.filter(u => u.is_banned);

  const handleModeration = async (userId: number, action: 'unban' | 'warn' | 'unwarn') => {
    const updatedUsers = bot.connectedUsers.map(u => {
      if (u.id === userId) {
        if (action === 'unban') return { ...u, is_banned: false };
        if (action === 'warn') return { ...u, warns: (u.warns || 0) + 1 };
        if (action === 'unwarn') return { ...u, warns: Math.max(0, (u.warns || 0) - 1) };
      }
      return u;
    });
    
    // Explicitly update the bot configuration on the server
    const updatedBot = { ...bot, connectedUsers: updatedUsers };
    await api.saveBot(bot.ownerId, updatedBot);
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Всего пользователей', value: bot.usersCount, color: 'text-white', icon: Users },
          { label: 'Активно (24ч)', value: stats.activeUsers24h, color: 'text-green-500', icon: Activity },
          { label: 'Забанено', value: bot.connectedUsers.filter(u => u.is_banned).length, color: 'text-red-500', icon: Ban },
          { label: 'Предупреждения', value: bot.connectedUsers.reduce((a,b) => a + (b.warns || 0), 0), color: 'text-yellow-500', icon: AlertTriangle },
        ].map((stat, i) => (
          <div key={i} className="bg-[#111] border border-zinc-800 p-6 rounded-3xl relative overflow-hidden group">
            <stat.icon className="absolute -right-4 -bottom-4 w-24 h-24 text-zinc-900 group-hover:text-zinc-800 transition-colors" />
            <div className="relative z-10">
              <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-1">{stat.label}</p>
              <p className={`text-3xl font-black ${stat.color}`}>{stat.value}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem]">
        <h3 className="text-sm font-bold text-white uppercase tracking-widest mb-8">Активность сообщений</h3>
        <div className="h-[300px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="colorIn" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="colorOut" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#a855f7" stopOpacity={0.1}/>
                  <stop offset="95%" stopColor="#a855f7" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#222" vertical={false} />
              <XAxis dataKey="date" stroke="#444" fontSize={10} tickLine={false} axisLine={false} />
              <YAxis stroke="#444" fontSize={10} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ backgroundColor: '#111', border: '1px solid #333', borderRadius: '12px', fontSize: '12px' }} />
              <Area type="monotone" dataKey="incoming" stroke="#3b82f6" fillOpacity={1} fill="url(#colorIn)" strokeWidth={3} />
              <Area type="monotone" dataKey="outgoing" stroke="#a855f7" fillOpacity={1} fill="url(#colorOut)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="bg-[#111] border border-zinc-800 rounded-[2.5rem] overflow-hidden flex flex-col">
          <div className="p-6 border-b border-zinc-800 flex justify-between items-center bg-zinc-900/20">
            <h3 className="text-xs font-bold text-white uppercase flex items-center gap-2">
              <Users className="w-4 h-4 text-blue-500" />
              Активные пользователи
            </h3>
          </div>
          <div className="flex-1 max-h-[400px] overflow-y-auto no-scrollbar">
            {bot.connectedUsers.filter(u => !u.is_banned).length === 0 ? (
              <div className="p-20 text-center text-[10px] font-bold text-zinc-700 uppercase">Нет данных</div>
            ) : (
              bot.connectedUsers.filter(u => !u.is_banned).map(u => (
                <div key={u.id} className="p-4 flex items-center justify-between hover:bg-zinc-800/30 border-b border-zinc-900/50 last:border-0 transition-colors">
                  <div>
                    <p className="text-sm font-bold text-white">{u.first_name}</p>
                    <p className="text-[10px] text-zinc-500">ID: {u.id} {u.warns > 0 && <span className="text-yellow-500 ml-2">Warns: {u.warns}</span>}</p>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => handleModeration(u.id, 'warn')} className="p-2 bg-yellow-500/10 text-yellow-500 rounded-lg hover:bg-yellow-500/20"><AlertTriangle className="w-3.5 h-3.5" /></button>
                    <button onClick={() => handleModeration(u.id, 'unwarn')} className="p-2 bg-blue-500/10 text-blue-500 rounded-lg hover:bg-blue-500/20"><ShieldCheck className="w-3.5 h-3.5" /></button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="bg-[#111] border border-zinc-800 rounded-[2.5rem] overflow-hidden flex flex-col">
          <div className="p-6 border-b border-zinc-800 bg-red-950/10">
            <h3 className="text-xs font-bold text-red-500 uppercase flex items-center gap-2">
              <Ban className="w-4 h-4" />
              Черный список
            </h3>
          </div>
          <div className="flex-1 max-h-[400px] overflow-y-auto no-scrollbar">
            {bannedUsers.length === 0 ? (
              <div className="p-20 text-center text-[10px] font-bold text-zinc-700 uppercase">Пусто</div>
            ) : (
              bannedUsers.map(u => (
                <div key={u.id} className="p-4 flex items-center justify-between bg-red-500/5 border-b border-red-500/10">
                  <div>
                    <p className="text-sm font-bold text-white">{u.first_name}</p>
                    <p className="text-[10px] text-zinc-500">ID: {u.id}</p>
                  </div>
                  <button onClick={() => handleModeration(u.id, 'unban')} className="text-[8px] font-black uppercase text-red-500 hover:underline">Разблокировать</button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default BotStatsView;
