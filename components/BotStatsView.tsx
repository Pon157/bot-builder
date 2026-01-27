
import React from 'react';
import { BotConfig } from '../types';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Users, MessageSquare, Ban, Activity, ShieldAlert } from 'lucide-react';

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
  const inactiveUsers = bot.connectedUsers.filter(u => !u.is_active && !u.is_banned); // Those who blocked the bot

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Всего пользователей', value: bot.usersCount, color: 'text-white', icon: Users },
          { label: 'Активно (24ч)', value: stats.activeUsers24h, color: 'text-green-500', icon: Activity },
          { label: 'Забанено (Админ)', value: stats.bannedCount, color: 'text-red-500', icon: Ban },
          { label: 'Заблокировали бота', value: inactiveUsers.length, color: 'text-orange-500', icon: ShieldAlert },
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
        <div className="flex items-center justify-between mb-8">
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-widest">Активность сообщений</h3>
            <p className="text-[10px] text-zinc-500 font-medium">Статистика за последние 7 дней</p>
          </div>
          <div className="flex gap-4">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-blue-500"></div>
              <span className="text-[9px] font-bold text-zinc-400 uppercase">Входящие</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-purple-500"></div>
              <span className="text-[9px] font-bold text-zinc-400 uppercase">Исходящие</span>
            </div>
          </div>
        </div>
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
              <Tooltip 
                contentStyle={{ backgroundColor: '#111', border: '1px solid #333', borderRadius: '12px', fontSize: '12px' }}
                itemStyle={{ fontWeight: 'bold' }}
              />
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
              Последние активные
            </h3>
          </div>
          <div className="flex-1 max-h-[400px] overflow-y-auto no-scrollbar">
            {bot.connectedUsers.filter(u => u.is_active && !u.is_banned).length === 0 ? (
              <div className="p-20 text-center text-[10px] font-bold text-zinc-700 uppercase">Нет активных пользователей</div>
            ) : (
              bot.connectedUsers
                .filter(u => u.is_active && !u.is_banned)
                .sort((a, b) => (b.last_seen || 0) - (a.last_seen || 0))
                .slice(0, 50)
                .map(u => (
                <div key={u.id} className="p-4 flex items-center justify-between hover:bg-zinc-800/30 border-b border-zinc-900/50 last:border-0 transition-colors">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-blue-600/10 text-blue-500 flex items-center justify-center text-xs font-bold">
                      {u.first_name[0]}
                    </div>
                    <div>
                      <p className="text-sm font-bold text-white">{u.first_name}</p>
                      <p className="text-[10px] text-zinc-500">ID: {u.id} • @{u.username || 'n/a'}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-[10px] text-green-500 font-bold block">Online</span>
                    <span className="text-[9px] text-zinc-600">{u.last_seen ? new Date(u.last_seen * 1000).toLocaleTimeString() : 'n/a'}</span>
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
              Ограничения доступа
            </h3>
          </div>
          <div className="flex-1 max-h-[400px] overflow-y-auto no-scrollbar">
            {bannedUsers.length === 0 && inactiveUsers.length === 0 ? (
              <div className="p-20 text-center text-[10px] font-bold text-zinc-700 uppercase">Черный список пуст</div>
            ) : (
              <>
                {bannedUsers.map(u => (
                  <div key={u.id} className="p-4 flex items-center justify-between bg-red-500/5 border-b border-red-500/10">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-red-500/10 text-red-500 flex items-center justify-center text-xs font-bold">
                        {u.first_name[0]}
                      </div>
                      <div>
                        <p className="text-sm font-bold text-white">{u.first_name}</p>
                        <p className="text-[10px] text-zinc-500">ID: {u.id}</p>
                      </div>
                    </div>
                    <span className="px-2 py-1 bg-red-500 text-white text-[8px] font-black uppercase rounded">BANNED</span>
                  </div>
                ))}
                {inactiveUsers.map(u => (
                  <div key={u.id} className="p-4 flex items-center justify-between bg-orange-500/5 border-b border-orange-500/10">
                    <div className="flex items-center gap-3 opacity-60">
                      <div className="w-8 h-8 rounded-full bg-zinc-800 text-zinc-500 flex items-center justify-center text-xs font-bold">
                        {u.first_name[0]}
                      </div>
                      <div>
                        <p className="text-sm font-bold text-white">{u.first_name}</p>
                        <p className="text-[10px] text-zinc-500">ID: {u.id}</p>
                      </div>
                    </div>
                    <span className="px-2 py-1 bg-zinc-800 text-zinc-500 text-[8px] font-black uppercase rounded">BLOCKED BOT</span>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default BotStatsView;
