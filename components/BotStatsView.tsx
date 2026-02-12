import React, { useState, useMemo, useEffect, useRef } from 'react';
import { BotConfig, TelegramUser } from '../types';
import { api } from '../services/apiService';
import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, 
  ResponsiveContainer, LineChart, Line, Legend 
} from 'recharts';
import { 
  Users, UserMinus, UserCheck, Activity, AlertTriangle, 
  TrendingUp, Search, ShieldAlert, MessageSquare, 
  Clock, Calendar, Zap, ArrowUpRight, ArrowDownRight, RefreshCw
} from 'lucide-react';

const POLL_INTERVAL_MS = 3000; // Обновление каждые 3 секунды

interface BotStatsViewProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
}

const BotStatsView: React.FC<BotStatsViewProps> = ({ bot, onUpdate }) => {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<'all' | 'active' | 'banned' | 'unsubscribed'>('all');
  const [liveStats, setLiveStats] = useState<any>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [isPolling, setIsPolling] = useState(true);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Live-polling статистики из БД
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const data = await api.getBotStats(bot.id);
        if (data?.stats) {
          setLiveStats(data.stats);
          setLastUpdated(new Date());
          // Обновляем bot объект если статистика изменилась
          if (onUpdate && JSON.stringify(data.stats) !== JSON.stringify(bot.stats)) {
            onUpdate({ ...bot, stats: data.stats });
          }
        }
      } catch {
        // Тихая ошибка — покажем последние данные
      }
    };

    fetchStats(); // Сразу при монтировании
    if (isPolling) {
      pollRef.current = setInterval(fetchStats, POLL_INTERVAL_MS);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [bot.id, isPolling]);

  // Итоговый объект статистики: live данные > bot.stats > config.stats > дефолт
  const stats = useMemo(() => {
    const src = liveStats
      || (bot.stats && Object.keys(bot.stats).length > 0 ? bot.stats : null)
      || bot.config?.stats
      || null;
    return src || {
      totalMessages: 0, incomingToday: 0, outgoingToday: 0,
      bannedCount: 0, history: [], activeUsers24h: 0
    };
  }, [liveStats, bot.stats, bot.config?.stats]);

  const users = (bot.config?.connectedUsers || []) as TelegramUser[];

  // Подсчет расширенных метрик
  const metrics = useMemo(() => {
    const total = users.length;
    const banned = users.filter(u => u.is_banned).length;
    const unsubscribed = users.filter(u => u.is_active === false).length;
    const active = users.filter(u => u.is_active !== false && !u.is_banned).length;
    const retention = total > 0 ? Math.round((active / total) * 100) : 0;
    
    // Сравнение с "вчера" (условно берем из истории)
    const prevDay = stats.history && stats.history.length > 1 ? stats.history[stats.history.length - 2] : null;
    const today = stats.history && stats.history.length > 0 ? stats.history[stats.history.length - 1] : null;
    
    const userDiff = today && prevDay ? (today.totalUsers || 0) - (prevDay.totalUsers || 0) : 0;

    return { total, banned, unsubscribed, active, retention, userDiff };
  }, [users, stats.history]);

  // Данные для графиков за ВСЕ дни
  const chartData = useMemo(() => {
    if (!Array.isArray(stats.history) || stats.history.length === 0) {
      return [{ date: 'Нет данных', incoming: 0, outgoing: 0, totalUsers: 0, activeUsers: 0 }];
    }
    return stats.history.map(pt => ({
      date: pt.date || '??',
      incoming: pt.incoming || 0,
      outgoing: pt.outgoing || 0,
      totalUsers: pt.totalUsers || 0,
      activeUsers: pt.activeUsers || 0
    }));
  }, [stats.history]);

  // Фильтрация списка
  const filteredUsers = useMemo(() => {
    return users.filter(u => {
      const matchesSearch = 
        u.first_name?.toLowerCase().includes(search.toLowerCase()) ||
        u.username?.toLowerCase().includes(search.toLowerCase()) ||
        u.id.toString().includes(search);
      
      if (filter === 'active') return matchesSearch && u.is_active !== false && !u.is_banned;
      if (filter === 'banned') return matchesSearch && u.is_banned;
      if (filter === 'unsubscribed') return matchesSearch && u.is_active === false;
      return matchesSearch;
    });
  }, [users, search, filter]);

  return (
    <div className="space-y-6 pb-10 animate-in fade-in duration-700">
      
      {/* Live indicator */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsPolling(p => !p)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-xl text-[10px] font-black uppercase tracking-widest border transition-all ${
              isPolling 
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' 
                : 'bg-zinc-900 border-zinc-800 text-zinc-500'
            }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${isPolling ? 'bg-emerald-500 animate-pulse' : 'bg-zinc-600'}`}></span>
            {isPolling ? 'Live' : 'Пауза'}
          </button>
          {lastUpdated && (
            <span className="text-[9px] text-zinc-600 font-mono">
              Обновлено: {lastUpdated.toLocaleTimeString()}
            </span>
          )}
        </div>
        <button
          onClick={() => { setLiveStats(null); setIsPolling(true); }}
          className="p-2 rounded-xl bg-zinc-900 border border-zinc-800 text-zinc-500 hover:text-white transition-all"
          title="Обновить сейчас"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Главные карточки (Metrics Grid) */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard 
          icon={<Users className="w-5 h-5 text-blue-400" />}
          label="Всего пользователей"
          value={metrics.total}
          trend={metrics.userDiff}
          subtext="Общий размер базы"
        />
        <StatCard 
          icon={<UserCheck className="w-5 h-5 text-emerald-400" />}
          label="Живой актив (Alive)"
          value={metrics.active}
          subtext={`${metrics.retention}% удержания`}
          highlight
        />
        <StatCard 
          icon={<MessageSquare className="w-5 h-5 text-purple-400" />}
          label="Сообщения"
          value={stats.totalMessages}
          subtext={`${stats.incomingToday} за сегодня`}
        />
        <StatCard 
          icon={<UserMinus className="w-5 h-5 text-rose-400" />}
          label="Отток / Блоки"
          value={metrics.unsubscribed}
          subtext="Потерянные пользователи"
        />
      </div>

      {/* Секция графиков */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Большой график активности */}
        <div className="lg:col-span-2 bg-zinc-900/50 border border-zinc-800 rounded-3xl p-6 shadow-xl shadow-black/20">
          <div className="flex items-center justify-between mb-8">
            <div>
              <h3 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
                <Activity className="w-5 h-5 text-emerald-500" />
                Активность сообщений
              </h3>
              <p className="text-xs text-zinc-500 mt-1">История взаимодействия за все дни</p>
            </div>
            <div className="flex gap-4 text-[10px] font-bold uppercase tracking-widest text-zinc-500">
              <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-emerald-500"></div> Входящие</div>
              <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-purple-500"></div> Исходящие</div>
            </div>
          </div>
          
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="colorInc" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.2}/>
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis dataKey="date" stroke="#71717a" fontSize={10} tickLine={false} axisLine={false} dy={10} />
                <YAxis stroke="#71717a" fontSize={10} tickLine={false} axisLine={false} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#18181b', border: '1px solid #3f3f46', borderRadius: '16px', boxShadow: '0 10px 15px -3px rgba(0,0,0,0.5)' }}
                />
                <Area type="monotone" dataKey="incoming" stroke="#10b981" strokeWidth={3} fill="url(#colorInc)" />
                <Area type="monotone" dataKey="outgoing" stroke="#a855f7" strokeWidth={2} fill="transparent" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* График роста аудитории */}
        <div className="bg-zinc-900/50 border border-zinc-800 rounded-3xl p-6 shadow-xl shadow-black/20">
          <h3 className="text-sm font-bold text-zinc-100 flex items-center gap-2 mb-8 uppercase tracking-tighter">
            <TrendingUp className="w-5 h-5 text-blue-500" />
            Динамика роста
          </h3>
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis dataKey="date" stroke="#71717a" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis stroke="#71717a" fontSize={10} hide />
                <Tooltip contentStyle={{ backgroundColor: '#18181b', border: '1px solid #3f3f46', borderRadius: '12px' }} />
                <Line 
                  type="stepAfter" 
                  dataKey="totalUsers" 
                  name="Всего" 
                  stroke="#3b82f6" 
                  strokeWidth={4} 
                  dot={{ r: 4, fill: '#3b82f6', strokeWidth: 0 }} 
                />
                <Line 
                   type="monotone" 
                   dataKey="activeUsers" 
                   name="Актив" 
                   stroke="#f59e0b" 
                   strokeWidth={2} 
                   strokeDasharray="5 5"
                   dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Список пользователей с фильтрацией */}
      <div className="bg-zinc-900/50 border border-zinc-800 rounded-3xl overflow-hidden shadow-2xl">
        <div className="p-6 border-b border-zinc-800 bg-zinc-900/40 flex flex-col md:flex-row gap-4 justify-between items-center">
          <div className="relative w-full md:w-96 group">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 group-focus-within:text-blue-500 transition-colors" />
            <input 
              type="text"
              placeholder="Поиск по ID, Имени или Юзернейму..."
              className="w-full bg-zinc-950 border border-zinc-800 rounded-2xl py-3 pl-12 pr-4 text-sm focus:ring-2 focus:ring-blue-500/20 outline-none transition-all"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          
          <div className="flex gap-1 p-1.5 bg-zinc-950 border border-zinc-800 rounded-2xl">
            {(['all', 'active', 'unsubscribed', 'banned'] as const).map(f => (
              <button 
                key={f}
                onClick={() => setFilter(f)}
                className={`px-4 py-2 rounded-xl text-[10px] font-black uppercase transition-all tracking-widest ${
                  filter === f ? 'bg-zinc-800 text-white shadow-lg' : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {f === 'all' ? 'Все' : f === 'active' ? 'Живые' : f === 'unsubscribed' ? 'Ушли' : 'Бан'}
              </button>
            ))}
          </div>
        </div>

        <div className="divide-y divide-zinc-800/50 max-h-[600px] overflow-y-auto custom-scrollbar">
          {filteredUsers.length > 0 ? filteredUsers.map(user => (
            <div key={user.id} className="p-5 hover:bg-white/[0.02] transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                {/* Аватар-заглушка */}
                <div className={`w-12 h-12 rounded-2xl flex items-center justify-center font-black text-lg border-2 shadow-inner ${
                  user.is_active === false 
                  ? 'border-zinc-800 bg-zinc-900 text-zinc-700' 
                  : 'border-blue-500/20 bg-gradient-to-br from-blue-500/10 to-purple-500/10 text-blue-400'
                }`}>
                  {user.first_name?.[0] || '?'}
                </div>
                
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-bold text-zinc-100">{user.first_name || 'Anonymous'}</span>
                    {user.is_active === false && (
                      <span className="text-[8px] bg-rose-500/10 text-rose-500 px-2 py-0.5 rounded-full border border-rose-500/20 font-black uppercase tracking-tighter">
                        Бот удален
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-zinc-500">
                    <span className="font-mono">ID: {user.id}</span>
                    {user.username && <span className="text-blue-500/60 font-medium">@{user.username}</span>}
                  </div>
                </div>
              </div>

              {/* Статусы и активность */}
              <div className="flex items-center gap-6">
                 {/* Информация о варнах */}
                 {(user.warns || 0) > 0 && (
                    <div className="flex flex-col items-center px-3 py-1 bg-amber-500/5 border border-amber-500/10 rounded-xl">
                        <span className="text-[8px] text-amber-500/50 font-black uppercase">Warns</span>
                        <span className="text-xs font-bold text-amber-500">{user.warns}</span>
                    </div>
                 )}

                 {/* Значок бана */}
                 {user.is_banned && (
                    <div className="p-2 bg-rose-500/10 rounded-xl border border-rose-500/20">
                        <ShieldAlert className="w-4 h-4 text-rose-500" />
                    </div>
                 )}

                <div className="flex flex-col items-end min-w-[100px]">
                  <div className="flex items-center gap-1.5 text-zinc-600 mb-1">
                    <Clock className="w-3 h-3" />
                    <span className="text-[9px] font-black uppercase tracking-tighter">Last Seen</span>
                  </div>
                  <span className="text-xs font-medium text-zinc-400">
                    {user.last_seen ? new Date(user.last_seen * 1000).toLocaleDateString() : 'Неизвестно'}
                  </span>
                </div>
              </div>
            </div>
          )) : (
            <div className="py-20 flex flex-col items-center justify-center text-zinc-600">
              <Zap className="w-12 h-12 mb-4 opacity-10" />
              <p className="text-sm font-bold uppercase tracking-widest opacity-50">Пользователи не найдены</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// Вспомогательный компонент карточки
const StatCard = ({ icon, label, value, trend, subtext, highlight }: any) => (
  <div className={`relative overflow-hidden bg-zinc-900/50 border ${highlight ? 'border-emerald-500/30' : 'border-zinc-800'} p-6 rounded-3xl hover:border-zinc-700 transition-all group shadow-lg`}>
    <div className="flex items-center justify-between mb-4">
      <div className={`p-2.5 rounded-2xl bg-zinc-950 border border-zinc-800 group-hover:scale-110 transition-transform`}>
        {icon}
      </div>
      {trend !== undefined && trend !== 0 && (
        <div className={`flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-black ${trend > 0 ? 'bg-emerald-500/10 text-emerald-500' : 'bg-rose-500/10 text-rose-500'}`}>
          {trend > 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
          {Math.abs(trend)}
        </div>
      )}
    </div>
    <div className="text-3xl font-black text-zinc-100 mb-1 tracking-tight">
      {typeof value === 'number' ? value.toLocaleString() : value}
    </div>
    <div className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-1">{label}</div>
    <div className="text-[9px] font-medium text-zinc-600 italic">{subtext}</div>
    
    {/* Декоративный эффект */}
    {highlight && (
        <div className="absolute -right-4 -bottom-4 w-24 h-24 bg-emerald-500/5 rounded-full blur-2xl"></div>
    )}
  </div>
);

export default BotStatsView;
