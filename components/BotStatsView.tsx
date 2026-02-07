import React, { useState, useMemo } from 'react';
import { BotConfig, TelegramUser } from '../types';
import { api } from '../services/apiService';
import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, 
  ResponsiveContainer, LineChart, Line 
} from 'recharts';
import { 
  Users, UserMinus, Ban, UserCheck, Activity, AlertTriangle, 
  TrendingUp, Search, Filter, ShieldAlert, UserX, ShieldCheck,
  RefreshCw, MessageSquare, Trash2
} from 'lucide-react';

interface BotStatsViewProps {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
}

const BotStatsView: React.FC<BotStatsViewProps> = ({ bot, onUpdate }) => {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<'all' | 'active' | 'banned' | 'unsubscribed'>('all');
  const [isUpdating, setIsUpdating] = useState<number | null>(null);

  const stats = bot.stats || { 
    totalMessages: 0, incomingToday: 0, outgoingToday: 0, 
    bannedCount: 0, history: [], activeUsers24h: 0 
  };

  const users = (bot.config?.connectedUsers || []) as TelegramUser[];

  // Расширенная статистика
  const userStats = useMemo(() => {
    const total = users.length;
    const banned = users.filter(u => u.is_banned).length;
    const unsubscribed = users.filter(u => u.is_active === false).length;
    const active = users.filter(u => u.is_active !== false && !u.is_banned).length;
    const retention = total > 0 ? Math.round((active / total) * 100) : 0;

    return { total, banned, unsubscribed, active, retention };
  }, [users]);

  // Данные графиков
  const chartData = useMemo(() => {
    if (!Array.isArray(stats.history) || stats.history.length === 0) {
      return [{ date: 'Нет данных', incoming: 0, outgoing: 0, totalUsers: 0 }];
    }
    return stats.history;
  }, [stats.history]);

  // Функции управления пользователями
  const handleUserAction = async (userId: number, action: 'ban' | 'unban' | 'warn' | 'reset_warns') => {
    setIsUpdating(userId);
    const updatedUsers = users.map(u => {
      if (u.id === userId) {
        if (action === 'ban') return { ...u, is_banned: true };
        if (action === 'unban') return { ...u, is_banned: false };
        if (action === 'warn') return { ...u, warns: (u.warns || 0) + 1 };
        if (action === 'reset_warns') return { ...u, warns: 0 };
      }
      return u;
    });

    const updatedBot = {
      ...bot,
      config: { ...bot.config, connectedUsers: updatedUsers }
    };

    try {
      await api.updateBotConfig(updatedBot);
      onUpdate(updatedBot);
    } catch (err) {
      console.error("Failed to update user:", err);
    } finally {
      setIsUpdating(null);
    }
  };

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
    <div className="space-y-6">
      
      {/* Карточки */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard 
          icon={<Users className="w-5 h-5 text-blue-400" />}
          label="Всего юзеров"
          value={userStats.total}
          subtext="База данных"
        />
        <StatCard 
          icon={<UserCheck className="w-5 h-5 text-emerald-400" />}
          label="Живые (Alive)"
          value={userStats.active}
          subtext={`${userStats.retention}% Retention`}
        />
        <StatCard 
          icon={<MessageSquare className="w-5 h-5 text-purple-400" />}
          label="Сообщения"
          value={stats.totalMessages}
          subtext={`${stats.incomingToday} сегодня`}
        />
        <StatCard 
          icon={<UserX className="w-5 h-5 text-rose-400" />}
          label="В бане / Ушли"
          value={userStats.banned + userStats.unsubscribed}
          subtext="Неактивные"
        />
      </div>

      {/* Графики */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-6">
          <h3 className="text-sm font-bold text-zinc-100 flex items-center gap-2 mb-6 uppercase tracking-widest">
            <Activity className="w-4 h-4 text-emerald-500" /> Активность
          </h3>
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis dataKey="date" stroke="#71717a" fontSize={10} />
                <Tooltip contentStyle={{ backgroundColor: '#18181b', border: '1px solid #3f3f46' }} />
                <Area type="monotone" dataKey="incoming" name="Входящие" stroke="#10b981" fill="#10b981" fillOpacity={0.1} />
                <Area type="monotone" dataKey="outgoing" name="Исходящие" stroke="#a855f7" fill="transparent" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-6">
          <h3 className="text-sm font-bold text-zinc-100 flex items-center gap-2 mb-6 uppercase tracking-widest">
            <TrendingUp className="w-4 h-4 text-blue-500" /> Рост базы
          </h3>
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis dataKey="date" stroke="#71717a" fontSize={10} />
                <Tooltip contentStyle={{ backgroundColor: '#18181b', border: '1px solid #3f3f46' }} />
                <Line type="stepAfter" dataKey="totalUsers" name="Юзеры" stroke="#3b82f6" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Управление пользователями */}
      <div className="bg-zinc-900/50 border border-zinc-800 rounded-2xl overflow-hidden">
        <div className="p-4 border-b border-zinc-800 flex flex-col md:flex-row gap-4 justify-between items-center bg-zinc-900/30">
          <div className="relative w-full md:w-80">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
            <input 
              type="text"
              placeholder="Поиск по ID или Name..."
              className="w-full bg-zinc-950 border border-zinc-800 rounded-xl py-2 pl-10 pr-4 text-xs focus:ring-1 focus:ring-blue-500 outline-none"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          
          <div className="flex gap-1 p-1 bg-zinc-950 border border-zinc-800 rounded-xl">
            {(['all', 'active', 'unsubscribed', 'banned'] as const).map(f => (
              <button 
                key={f}
                onClick={() => setFilter(f)}
                className={`px-3 py-1.5 rounded-lg text-[10px] font-black uppercase transition-all ${
                  filter === f ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {f === 'all' ? 'Все' : f === 'active' ? 'Живые' : f === 'unsubscribed' ? 'Ушли' : 'Бан'}
              </button>
            ))}
          </div>
        </div>

        <div className="divide-y divide-zinc-800 max-h-[500px] overflow-y-auto">
          {filteredUsers.map(user => (
            <div key={user.id} className="p-4 hover:bg-white/[0.02] flex flex-col sm:flex-row sm:items-center justify-between gap-4 transition-colors">
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center font-black text-sm border-2 ${
                  user.is_active === false ? 'border-zinc-800 text-zinc-700' : 'border-blue-500/20 bg-blue-500/10 text-blue-400'
                }`}>
                  {user.first_name?.[0] || '?'}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-zinc-100">{user.first_name}</span>
                    {user.is_active === false && (
                      <span className="text-[9px] bg-rose-500/10 text-rose-500 px-1.5 py-0.5 rounded border border-rose-500/20 font-black uppercase">Удалил бота</span>
                    )}
                  </div>
                  <p className="text-xs text-zinc-500">ID: {user.id} {user.username && `@${user.username}`}</p>
                </div>
              </div>

              {/* Кнопки управления */}
              <div className="flex items-center gap-2">
                <div className="mr-4 text-right hidden lg:block">
                  <div className="text-[9px] text-zinc-600 uppercase font-black">Варны</div>
                  <div className={`text-xs font-bold ${user.warns ? 'text-amber-500' : 'text-zinc-700'}`}>{user.warns || 0}</div>
                </div>

                {user.is_banned ? (
                  <button 
                    disabled={isUpdating === user.id}
                    onClick={() => handleUserAction(user.id, 'unban')}
                    className="flex items-center gap-2 px-3 py-1.5 bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 rounded-lg text-[10px] font-black uppercase hover:bg-emerald-500/20 transition-all"
                  >
                    <ShieldCheck className="w-3.5 h-3.5" /> Разбанить
                  </button>
                ) : (
                  <>
                    <button 
                      disabled={isUpdating === user.id}
                      onClick={() => handleUserAction(user.id, 'warn')}
                      className="p-2 bg-amber-500/10 text-amber-500 border border-amber-500/20 rounded-lg hover:bg-amber-500/20 transition-all"
                      title="Выдать предупреждение"
                    >
                      <AlertTriangle className="w-3.5 h-3.5" />
                    </button>
                    <button 
                      disabled={isUpdating === user.id}
                      onClick={() => handleUserAction(user.id, 'ban')}
                      className="flex items-center gap-2 px-3 py-1.5 bg-rose-500/10 text-rose-500 border border-rose-500/20 rounded-lg text-[10px] font-black uppercase hover:bg-rose-500/20 transition-all"
                    >
                      <Ban className="w-3.5 h-3.5" /> Забанить
                    </button>
                  </>
                )}
                
                {isUpdating === user.id && <RefreshCw className="w-4 h-4 text-blue-500 animate-spin ml-2" />}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

const StatCard = ({ icon, label, value, subtext }: any) => (
  <div className="bg-zinc-900/50 border border-zinc-800 p-5 rounded-2xl hover:border-zinc-700 transition-all">
    <div className="flex items-center gap-3 mb-3">
      <div className="p-2 bg-zinc-950 rounded-lg">{icon}</div>
      <span className="text-[10px] font-black text-zinc-500 uppercase tracking-widest">{label}</span>
    </div>
    <div className="text-2xl font-black text-zinc-100">{value.toLocaleString()}</div>
    <div className="text-[9px] font-bold text-zinc-600 uppercase mt-1">{subtext}</div>
  </div>
);

export default BotStatsView;
