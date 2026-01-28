
import React, { useState } from 'react';
import { BotConfig, TelegramUser } from '../types';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Users, MessageSquare, Ban, Activity, ShieldAlert, ShieldCheck, AlertTriangle, Loader2 } from 'lucide-react';
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
  
  const chartData = stats.history.length > 0 ? stats.history : [
    { date: new Date().toLocaleDateString(), incoming: 0, outgoing: 0 }
  ];

  const bannedUsers = bot.connectedUsers.filter(u => u.is_banned);

  const handleModeration = async (userId: number, action: 'unban' | 'warn' | 'unwarn' | 'ban') => {
    setIsSyncing(userId);
    const threshold = bot.settings.autoBanThreshold || 0;
    
    const updatedUsers = bot.connectedUsers.map(u => {
      if (u.id === userId) {
        if (action === 'unban') {
          // Если мы разблокируем, нужно сбросить варны хотя бы на 1 ниже порога, иначе автобан сработает снова при сохранении
          const newWarns = (threshold > 0 && u.warns >= threshold) ? threshold - 1 : u.warns;
          return { ...u, is_banned: false, warns: newWarns };
        }
        if (action === 'ban') return { ...u, is_banned: true };
        if (action === 'warn') return { ...u, warns: (u.warns || 0) + 1 };
        if (action === 'unwarn') return { ...u, warns: Math.max(0, (u.warns || 0) - 1) };
      }
      return u;
    });
    
    // Проверка порога автобана (только для действия warn)
    const finalizedUsers = updatedUsers.map(u => {
        if (u.id === userId && action === 'warn' && threshold > 0 && u.warns >= threshold) {
            return { ...u, is_banned: true };
        }
        return u;
    });

    const updatedBot = { ...bot, connectedUsers: finalizedUsers };
    
    try {
        // Сохраняем и дожидаемся ответа
        await api.saveBot(bot.ownerId, updatedBot);
        // Только после успешного сохранения обновляем локальный стейт
        onUpdate(updatedBot);
    } catch (e) {
        console.error(e);
        alert("Ошибка синхронизации с сервером");
    } finally {
        setIsSyncing(null);
    }
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Всего пользователей', value: bot.connectedUsers.length, color: 'text-white', icon: Users },
          { label: 'Активно (24ч)', value: stats.activeUsers24h, color: 'text-green-500', icon: Activity },
          { label: 'Забанено', value: bannedUsers.length, color: 'text-red-500', icon: Ban },
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
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-blue-600/20 text-blue-500 flex items-center justify-center text-xs font-black">
                        {u.first_name?.charAt(0) || "U"}
                    </div>
                    <div>
                        <p className="text-sm font-bold text-white">{u.first_name}</p>
                        <p className="text-[10px] text-zinc-500">ID: {u.id} {u.warns > 0 && <span className="text-yellow-500 ml-2 font-bold uppercase">Варны: {u.warns}</span>}</p>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    {isSyncing === u.id ? (
                        <div className="p-2"><Loader2 className="w-4 h-4 text-zinc-500 animate-spin" /></div>
                    ) : (
                        <>
                            <button onClick={() => handleModeration(u.id, 'warn')} title="Выдать варн" className="p-2 bg-yellow-500/10 text-yellow-500 rounded-lg hover:bg-yellow-500/20 transition-all"><AlertTriangle className="w-3.5 h-3.5" /></button>
                            <button onClick={() => handleModeration(u.id, 'unwarn')} title="Снять варн" className="p-2 bg-blue-500/10 text-blue-500 rounded-lg hover:bg-blue-500/20 transition-all"><ShieldCheck className="w-3.5 h-3.5" /></button>
                            <button onClick={() => handleModeration(u.id, 'ban')} title="Забанить" className="p-2 bg-red-500/10 text-red-500 rounded-lg hover:bg-red-500/20 transition-all"><Ban className="w-3.5 h-3.5" /></button>
                        </>
                    )}
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
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-red-500/20 text-red-500 flex items-center justify-center text-xs font-black">
                        {u.first_name?.charAt(0) || "U"}
                    </div>
                    <div>
                        <p className="text-sm font-bold text-white">{u.first_name}</p>
                        <p className="text-[10px] text-zinc-500">ID: {u.id} {u.warns > 0 && <span className="text-yellow-500/70 ml-2">Варны: {u.warns}</span>}</p>
                    </div>
                  </div>
                  {isSyncing === u.id ? (
                      <Loader2 className="w-4 h-4 text-zinc-500 animate-spin mr-4" />
                  ) : (
                      <button onClick={() => handleModeration(u.id, 'unban')} className="text-[10px] font-black uppercase text-red-500 hover:text-white bg-red-500/10 hover:bg-red-500 px-4 py-2 rounded-xl transition-all">Разблокировать</button>
                  )}
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
