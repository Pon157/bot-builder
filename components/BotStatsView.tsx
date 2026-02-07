import React, { useState, useMemo, useEffect } from 'react';
import { BotConfig, TelegramUser } from '../types';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts';
import { 
  Users, UserMinus, Ban, UserCheck, Activity, AlertTriangle, 
  TrendingUp, ShieldCheck, Search, Filter, ShieldAlert, RefreshCw
} from 'lucide-react';
// Импортируем API сервис для получения свежих данных
import { api } from '../services/apiService';

interface BotStatsViewProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
}

const BotStatsView: React.FC<BotStatsViewProps> = ({ bot, onUpdate }) => {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<'all' | 'active' | 'banned' | 'unsubscribed'>('all');
  const [isAutoUpdating, setIsAutoUpdating] = useState(false);

  // --- МЕХАНИЗМ МОМЕНТАЛЬНОГО ОБНОВЛЕНИЯ ---
  useEffect(() => {
    const updateStats = async () => {
      setIsAutoUpdating(true);
      try {
        // Используем метод getBotById из apiService
        const updatedBot = await api.getBotById(bot.id);
        if (updatedBot) {
          onUpdate(updatedBot);
        }
      } catch (e) {
        console.error("Ошибка автообновления статистики:", e);
      } finally {
        setIsAutoUpdating(false);
      }
    };

    // Запускаем цикл обновления каждые 5 секунд
    const interval = setInterval(updateStats, 5000);
    return () => clearInterval(interval);
  }, [bot.id, onUpdate]);

  const stats = bot.stats || { 
    totalMessages: 0, incomingToday: 0, outgoingToday: 0, 
    bannedCount: 0, history: [], activeUsers24h: 0 
  };
  
  // Безопасная подготовка данных для графиков
  const safeHistory = useMemo(() => {
    if (Array.isArray(stats.history) && stats.history.length > 0) {
      return stats.history.map(pt => ({
        ...pt,
        incoming: Number(pt.incoming || 0),
        outgoing: Number(pt.outgoing || 0),
        totalUsers: Number(pt.totalUsers || 0),
        activeUsers: Number(pt.activeUsers || 0),
        date: pt.date || '??'
      }));
    }
    // Если истории нет, создаем пустую точку, чтобы график не исчезал
    return [{ date: 'Нет данных', incoming: 0, outgoing: 0, totalUsers: 0, activeUsers: 0 }];
  }, [stats.history]);

  // Фильтрация пользователей (из исходного кода)
  const filteredUsers = useMemo(() => {
    let list = bot.connectedUsers || [];
    if (search) {
      const s = search.toLowerCase();
      list = list.filter(u => 
        u.id.toString().includes(s) || 
        u.username?.toLowerCase().includes(s) || 
        u.first_name?.toLowerCase().includes(s)
      );
    }
    if (filter === 'active') list = list.filter(u => !u.is_banned && u.is_active !== false);
    if (filter === 'banned') list = list.filter(u => u.is_banned);
    if (filter === 'unsubscribed') list = list.filter(u => u.is_active === false);
    return list;
  }, [bot.connectedUsers, search, filter]);

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* Заголовок с индикатором обновления */}
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xl font-black text-white uppercase tracking-tighter flex items-center gap-2">
          <Activity className="w-5 h-5 text-blue-500" />
          Аналитика бота
        </h3>
        <div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-900/50 rounded-xl border border-zinc-800">
          <RefreshCw className={`w-3 h-3 text-blue-500 ${isAutoUpdating ? 'animate-spin' : ''}`} />
          <span className="text-[9px] font-black text-zinc-500 uppercase tracking-widest">
            Live Update (5s)
          </span>
        </div>
      </div>

      {/* Сетка основных показателей */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-[#111] p-5 rounded-[2rem] border border-zinc-800/50 relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <Users className="w-12 h-12 text-blue-500" />
          </div>
          <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Всего юзеров</p>
          <p className="text-3xl font-black text-white mt-1">{bot.connectedUsers?.length || 0}</p>
        </div>

        <div className="bg-[#111] p-5 rounded-[2rem] border border-zinc-800/50 relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <TrendingUp className="w-12 h-12 text-emerald-500" />
          </div>
          <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Сообщений (24ч)</p>
          <p className="text-3xl font-black text-emerald-500 mt-1">{stats.incomingToday + stats.outgoingToday}</p>
        </div>

        <div className="bg-[#111] p-5 rounded-[2rem] border border-zinc-800/50 relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <UserCheck className="w-12 h-12 text-purple-500" />
          </div>
          <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Актив (24ч)</p>
          <p className="text-3xl font-black text-purple-500 mt-1">{stats.activeUsers24h || 0}</p>
        </div>

        <div className="bg-[#111] p-5 rounded-[2rem] border border-zinc-800/50 relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <Ban className="w-12 h-12 text-rose-500" />
          </div>
          <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">В бане</p>
          <p className="text-3xl font-black text-rose-500 mt-1">{stats.bannedCount || 0}</p>
        </div>
      </div>

      {/* Графики */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-[#111] p-8 rounded-[2.5rem] border border-zinc-800/50">
          <div className="flex items-center justify-between mb-8">
            <div>
              <h4 className="text-sm font-black text-white uppercase tracking-widest">Трафик сообщений</h4>
              <p className="text-[10px] text-zinc-500 font-bold uppercase mt-1">Входящие vs Исходящие</p>
            </div>
            <div className="flex gap-4">
               <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-blue-500"></div><span className="text-[9px] font-bold text-zinc-400 uppercase">Вход</span></div>
               <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-emerald-500"></div><span className="text-[9px] font-bold text-zinc-400 uppercase">Выход</span></div>
            </div>
          </div>
          <div className="h-[250px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={safeHistory}>
                <defs>
                  <linearGradient id="colorInc" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/><stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/></linearGradient>
                  <linearGradient id="colorOut" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/><stop offset="95%" stopColor="#10b981" stopOpacity={0}/></linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#222" vertical={false} />
                <XAxis dataKey="date" stroke="#444" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis stroke="#444" fontSize={10} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={{ backgroundColor: '#111', border: '1px solid #333', borderRadius: '12px', fontSize: '10px' }} />
                <Area type="monotone" dataKey="incoming" stroke="#3b82f6" fillOpacity={1} fill="url(#colorInc)" strokeWidth={3} />
                <Area type="monotone" dataKey="outgoing" stroke="#10b981" fillOpacity={1} fill="url(#colorOut)" strokeWidth={3} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-[#111] p-8 rounded-[2.5rem] border border-zinc-800/50">
          <div className="mb-8">
            <h4 className="text-sm font-black text-white uppercase tracking-widest">Рост аудитории</h4>
            <p className="text-[10px] text-zinc-500 font-bold uppercase mt-1">Общее количество пользователей</p>
          </div>
          <div className="h-[250px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={safeHistory}>
                <CartesianGrid strokeDasharray="3 3" stroke="#222" vertical={false} />
                <XAxis dataKey="date" stroke="#444" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis stroke="#444" fontSize={10} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={{ backgroundColor: '#111', border: '1px solid #333', borderRadius: '12px', fontSize: '10px' }} />
                <Line type="stepAfter" dataKey="totalUsers" stroke="#a855f7" strokeWidth={4} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Секция управления пользователями (из исходного кода) */}
      <div className="bg-[#111] rounded-[2.5rem] border border-zinc-800/50 overflow-hidden">
        <div className="p-6 border-b border-zinc-800/50 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="relative flex-1">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
            <input 
              type="text" 
              placeholder="Поиск по ID или Username..." 
              className="w-full bg-black border border-zinc-800 rounded-2xl py-3 pl-12 pr-4 text-sm text-white focus:ring-1 focus:ring-blue-500 outline-none transition-all"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-2 overflow-x-auto pb-2 md:pb-0">
            <Filter className="w-4 h-4 text-zinc-500 ml-2" />
            {(['all', 'active', 'banned', 'unsubscribed'] as const).map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all whitespace-nowrap ${
                  filter === f ? 'bg-blue-600 text-white' : 'bg-zinc-900 text-zinc-500 hover:text-white'
                }`}
              >
                {f === 'all' && 'Все'}
                {f === 'active' && 'Активные'}
                {f === 'banned' && 'Бан'}
                {f === 'unsubscribed' && 'Ушли'}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-zinc-800/30">
                <th className="px-6 py-4 text-[10px] font-black text-zinc-500 uppercase tracking-widest">Пользователь</th>
                <th className="px-6 py-4 text-[10px] font-black text-zinc-500 uppercase tracking-widest">Статус</th>
                <th className="px-6 py-4 text-[10px] font-black text-zinc-500 uppercase tracking-widest text-right">Действия</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/30">
              {filteredUsers.map(u => (
                <tr key={u.id} className="hover:bg-white/[0.02] transition-colors group">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-gradient-to-br from-zinc-800 to-zinc-900 rounded-xl flex items-center justify-center border border-zinc-700">
                        <Users className="w-5 h-5 text-zinc-500" />
                      </div>
                      <div>
                        <p className="text-sm font-bold text-white leading-none">{u.first_name || 'User'}</p>
                        <p className="text-[10px] text-zinc-500 font-mono mt-1">ID: {u.id}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    {u.is_banned ? (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-rose-500/10 text-rose-500 text-[9px] font-black uppercase border border-rose-500/20">
                        <ShieldAlert className="w-3 h-3" /> Забанен
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-500/10 text-emerald-500 text-[9px] font-black uppercase border border-emerald-500/20">
                        <ShieldCheck className="w-3 h-3" /> Активен
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button className="text-[10px] font-black text-zinc-600 hover:text-white uppercase tracking-widest transition-colors">
                      Управление
                    </button>
                  </td>
                </tr>
              ))}
              {filteredUsers.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-6 py-12 text-center">
                    <p className="text-zinc-600 text-[11px] font-bold uppercase tracking-widest">Никого не найдено</p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default BotStatsView;
