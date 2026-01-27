
import React from 'react';
import { BotConfig } from '../types';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';

interface BotStatsViewProps {
  bot: BotConfig;
}

const BotStatsView: React.FC<BotStatsViewProps> = ({ bot }) => {
  const stats = bot.stats || { totalMessages: 0, incomingToday: 0, outgoingToday: 0, bannedCount: 0, history: [] };
  
  // Если истории нет, показываем пустой график, а не имитацию
  const chartData = stats.history.length > 0 ? stats.history : [
    { date: 'No Data', incoming: 0, outgoing: 0 }
  ];

  const bannedUsers = bot.connectedUsers.filter(u => u.is_banned);

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          { label: 'Всего пользователей', value: bot.usersCount, color: 'text-white' },
          { label: 'Сообщений сегодня', value: stats.incomingToday + stats.outgoingToday, color: 'text-blue-500' },
          { label: 'Заблокировано (бан)', value: stats.bannedCount, color: 'text-red-500' },
          { label: 'Всего за все время', value: stats.totalMessages, color: 'text-zinc-500' },
        ].map((stat, i) => (
          <div key={i} className="bg-[#111] border border-zinc-800 p-6 rounded-3xl">
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-1">{stat.label}</p>
            <p className={`text-3xl font-black ${stat.color}`}>{stat.value}</p>
          </div>
        ))}
      </div>

      <div className="bg-[#111] border border-zinc-800 p-8 rounded-[2.5rem]">
        <h3 className="text-sm font-bold text-white uppercase tracking-widest mb-8">Активность сообщений (7 дней)</h3>
        <div className="h-[300px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="colorIn" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
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
              <Area type="monotone" dataKey="outgoing" stroke="#a855f7" fillOpacity={0} strokeWidth={2} strokeDasharray="5 5" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="bg-[#111] border border-zinc-800 rounded-[2.5rem] overflow-hidden">
          <div className="p-6 border-b border-zinc-800 flex justify-between">
            <h3 className="text-xs font-bold text-white uppercase">Последние активные</h3>
          </div>
          <div className="max-h-[300px] overflow-y-auto no-scrollbar">
            {bot.connectedUsers.filter(u => !u.is_banned).slice(-10).reverse().map(u => (
              <div key={u.id} className="p-4 flex items-center justify-between hover:bg-zinc-800/30">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-blue-600/20 text-blue-500 flex items-center justify-center text-xs font-bold">
                    {u.first_name[0]}
                  </div>
                  <div>
                    <p className="text-sm font-bold text-white">{u.first_name}</p>
                    <p className="text-[10px] text-zinc-500">ID: {u.id}</p>
                  </div>
                </div>
                <span className="text-[10px] text-zinc-600">{new Date(u.joined_at * 1000).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-[#111] border border-zinc-800 rounded-[2.5rem] overflow-hidden">
          <div className="p-6 border-b border-zinc-800">
            <h3 className="text-xs font-bold text-red-500 uppercase">Черный список (Banned)</h3>
          </div>
          <div className="max-h-[300px] overflow-y-auto no-scrollbar">
            {bannedUsers.length === 0 ? (
              <div className="p-20 text-center text-[10px] font-bold text-zinc-700 uppercase">Список пуст</div>
            ) : (
              bannedUsers.map(u => (
                <div key={u.id} className="p-4 flex items-center justify-between bg-red-500/5">
                  <div className="flex items-center gap-3 opacity-50">
                    <div className="w-8 h-8 rounded-full bg-zinc-800 text-zinc-500 flex items-center justify-center text-xs font-bold">
                      {u.first_name[0]}
                    </div>
                    <div>
                      <p className="text-sm font-bold text-white">{u.first_name}</p>
                      <p className="text-[10px] text-zinc-500">ID: {u.id}</p>
                    </div>
                  </div>
                  <span className="px-2 py-1 bg-red-500/10 text-red-500 text-[9px] font-black uppercase rounded">BANNED</span>
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
