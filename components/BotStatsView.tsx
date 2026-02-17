import React, { useState, useMemo, useEffect, useRef } from 'react';
import { BotConfig, RandomizerUser, Lottery } from '../types';
import { api } from '../services/apiService';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar, LineChart, Line
} from 'recharts';
import {
  Users, UserMinus, UserCheck, Activity, AlertTriangle,
  TrendingUp, Search, ShieldAlert, MessageSquare,
  Clock, Send, Shuffle, Trophy, Gift,
  FileText, ArrowUpRight, ArrowDownRight, Zap, Hash
} from 'lucide-react';

const POLL_MS = 5000;

interface Props {
  bot: BotConfig;
  onUpdate: (bot: BotConfig) => void;
}

// ── Мини-карточки статистики ────────────────────────────────
const StatCard = ({ icon, label, value, trend, sub, accent = '' }: any) => (
  <div className={`bg-zinc-900/60 border ${accent ? `border-${accent}-500/25` : 'border-zinc-800'} p-5 rounded-3xl hover:border-zinc-700 transition-all group`}>
    <div className="flex items-center justify-between mb-3">
      <div className="p-2 rounded-xl bg-zinc-950 border border-zinc-800 group-hover:scale-105 transition-transform">
        {icon}
      </div>
      {trend !== undefined && trend !== 0 && (
        <div className={`flex items-center gap-0.5 px-2 py-1 rounded-lg text-[9px] font-black ${trend > 0 ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
          {trend > 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
          {Math.abs(trend)}
        </div>
      )}
    </div>
    <div className="text-3xl font-black text-zinc-100 tracking-tight mb-0.5">
      {typeof value === 'number' ? value.toLocaleString() : (value ?? 0)}
    </div>
    <div className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">{label}</div>
    {sub && <div className="text-[9px] text-zinc-600 mt-0.5">{sub}</div>}
  </div>
);

// ── Tooltip общий ────────────────────────────────────────────
const chartTooltipStyle = {
  backgroundColor: '#18181b',
  border: '1px solid #3f3f46',
  borderRadius: '12px',
  boxShadow: '0 10px 25px rgba(0,0,0,0.5)',
};

// ════════════════════════════════════════════════════════════
// POSTER STATS
// ════════════════════════════════════════════════════════════
const PosterStats: React.FC<{ stats: any }> = ({ stats }) => {
  const history = stats?.history || [];
  const chartData = history.length > 0
    ? history.map((d: any) => ({ date: d.date, posts: d.posts || 0 }))
    : [{ date: 'Нет данных', posts: 0 }];

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <StatCard icon={<Send className="w-5 h-5 text-emerald-400" />}
          label="Всего постов" value={stats?.totalPosts ?? 0} accent="emerald" />
        <StatCard icon={<Activity className="w-5 h-5 text-blue-400" />}
          label="За последний день"
          value={history.length > 0 ? (history[history.length - 1]?.posts || 0) : 0}
          sub="Постов за последний период" />
        <StatCard icon={<TrendingUp className="w-5 h-5 text-purple-400" />}
          label="Активных дней"
          value={history.filter((d: any) => (d.posts || 0) > 0).length}
          sub="Дней с публикациями" />
      </div>

      <div className="bg-zinc-900/50 border border-zinc-800 rounded-3xl p-6">
        <h3 className="text-sm font-bold text-zinc-200 flex items-center gap-2 mb-6 uppercase tracking-tight">
          <Activity className="w-4 h-4 text-emerald-500" />График публикаций
        </h3>
        <div className="h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
              <XAxis dataKey="date" stroke="#52525b" fontSize={10} tickLine={false} axisLine={false} dy={8} />
              <YAxis stroke="#52525b" fontSize={10} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip contentStyle={chartTooltipStyle} />
              <Bar dataKey="posts" name="Постов" fill="#10b981" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {history.length === 0 && (
        <div className="text-center py-16 text-zinc-700 text-xs uppercase font-black tracking-widest opacity-40">
          После первой публикации здесь появится статистика
        </div>
      )}
    </div>
  );
};

// ════════════════════════════════════════════════════════════
// RANDOMIZER STATS
// ════════════════════════════════════════════════════════════
const RandomizerStats: React.FC<{ bot: BotConfig }> = ({ bot }) => {
  const [search, setSearch] = useState('');
  const [userFilter, setUserFilter] = useState<'all' | 'blocked'>('all');
  const [tab, setTab] = useState<'users' | 'lotteries'>('users');

  const rawUsers: RandomizerUser[] = (bot.config?.users || bot.users || []) as RandomizerUser[];
  const rawLotteries: Lottery[]    = (bot.config?.lotteries || bot.lotteries || []) as Lottery[];
  const stats = bot.config?.stats || bot.stats || {};

  const filteredUsers = useMemo(() => rawUsers.filter(u => {
    const q = search.toLowerCase();
    const match = u.name?.toLowerCase().includes(q) || u.username?.toLowerCase().includes(q) || String(u.id).includes(q);
    if (userFilter === 'blocked') return match && u.is_blocked;
    return match;
  }), [rawUsers, search, userFilter]);

  const activeLots    = rawLotteries.filter(l => l.status === 'active');
  const finishedLots  = rawLotteries.filter(l => l.status === 'finished');

  const histData = (stats.history || []).map((d: any) => ({
    date: d.date,
    users: d.totalUsers || 0,
  }));

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* Метрики */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard icon={<Users className="w-5 h-5 text-purple-400" />}
          label="Пользователей" value={rawUsers.length} accent="purple" />
        <StatCard icon={<Gift className="w-5 h-5 text-amber-400" />}
          label="Розыгрышей" value={rawLotteries.length}
          sub={`${activeLots.length} активных`} />
        <StatCard icon={<Trophy className="w-5 h-5 text-emerald-400" />}
          label="Завершённых" value={finishedLots.length} />
        <StatCard icon={<UserMinus className="w-5 h-5 text-rose-400" />}
          label="Заблокировали" value={rawUsers.filter(u => u.is_blocked).length}
          sub="Удалили бота" />
      </div>

      {/* График роста */}
      {histData.length > 0 && (
        <div className="bg-zinc-900/50 border border-zinc-800 rounded-3xl p-6">
          <h3 className="text-sm font-bold text-zinc-200 flex items-center gap-2 mb-5 uppercase tracking-tight">
            <TrendingUp className="w-4 h-4 text-purple-500" />Рост базы пользователей
          </h3>
          <div className="h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={histData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis dataKey="date" stroke="#52525b" fontSize={10} tickLine={false} axisLine={false} dy={8} />
                <YAxis stroke="#52525b" fontSize={10} tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip contentStyle={chartTooltipStyle} />
                <Line type="stepAfter" dataKey="users" name="Участников" stroke="#a855f7" strokeWidth={3}
                  dot={{ r: 3, fill: '#a855f7', strokeWidth: 0 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Переключатель */}
      <div className="flex gap-1 p-1.5 bg-zinc-950 border border-zinc-800 rounded-2xl w-fit">
        {(['users', 'lotteries'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-5 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${
              tab === t ? 'bg-zinc-800 text-white shadow-lg' : 'text-zinc-500 hover:text-zinc-300'
            }`}>
            {t === 'users' ? `Участники (${rawUsers.length})` : `Розыгрыши (${rawLotteries.length})`}
          </button>
        ))}
      </div>

      {/* Участники */}
      {tab === 'users' && (
        <div className="bg-zinc-900/50 border border-zinc-800 rounded-3xl overflow-hidden">
          <div className="p-5 border-b border-zinc-800 flex flex-col sm:flex-row gap-3 justify-between items-center">
            <div className="relative w-full sm:w-80">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
              <input type="text" placeholder="Поиск по ID, имени, @username..."
                className="w-full bg-zinc-950 border border-zinc-800 rounded-xl py-2.5 pl-10 pr-4 text-sm outline-none focus:border-purple-500 transition-all"
                value={search} onChange={e => setSearch(e.target.value)} />
            </div>
            <div className="flex gap-1 p-1 bg-zinc-950 border border-zinc-800 rounded-xl">
              {(['all','blocked'] as const).map(f => (
                <button key={f} onClick={() => setUserFilter(f)}
                  className={`px-4 py-1.5 rounded-lg text-[9px] font-black uppercase transition-all ${
                    userFilter === f ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-300'
                  }`}>
                  {f === 'all' ? 'Все' : 'Заблокировали'}
                </button>
              ))}
            </div>
          </div>
          <div className="divide-y divide-zinc-800/50 max-h-[500px] overflow-y-auto">
            {filteredUsers.length === 0 ? (
              <div className="py-16 text-center text-zinc-700 text-xs uppercase font-black tracking-widest opacity-40 flex flex-col items-center gap-3">
                <Zap className="w-8 h-8" />Участники не найдены
              </div>
            ) : filteredUsers.map(u => (
              <div key={u.id} className="p-4 hover:bg-white/[0.02] flex items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-2xl flex items-center justify-center font-black text-base border ${
                    u.is_blocked ? 'border-zinc-800 bg-zinc-900 text-zinc-700' : 'border-purple-500/20 bg-purple-500/10 text-purple-400'
                  }`}>{u.name?.[0] || '?'}</div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-zinc-200">{u.name}</span>
                      {u.is_blocked && (
                        <span className="text-[8px] bg-rose-500/10 text-rose-400 px-1.5 py-0.5 rounded border border-rose-500/20 font-black uppercase">Заблок</span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 text-[10px] text-zinc-500">
                      <span className="font-mono">ID: {u.id}</span>
                      {u.username && <span className="text-purple-400/60">@{u.username}</span>}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-4 text-[10px] text-zinc-500">
                  <div className="text-center">
                    <div className="font-black text-zinc-300">{u.participations || 0}</div>
                    <div className="uppercase tracking-wider">участий</div>
                  </div>
                  <div className="text-center">
                    <div className="font-black text-amber-400">{u.wins || 0}</div>
                    <div className="uppercase tracking-wider">побед</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Розыгрыши */}
      {tab === 'lotteries' && (
        <div className="space-y-4">
          {rawLotteries.length === 0 ? (
            <div className="py-20 text-center text-zinc-700 text-xs uppercase font-black tracking-widest opacity-40 flex flex-col items-center gap-3">
              <Gift className="w-8 h-8" />Розыгрышей ещё не было
            </div>
          ) : rawLotteries.slice().reverse().map(lot => (
            <div key={lot.id} className={`bg-zinc-900/50 border rounded-2xl p-5 ${
              lot.status === 'active' ? 'border-purple-500/30' : 'border-zinc-800'
            }`}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <span className={`text-[9px] px-2 py-1 rounded-lg font-black uppercase border ${
                    lot.status === 'active'
                      ? 'bg-purple-500/10 border-purple-500/20 text-purple-400'
                      : 'bg-zinc-900 border-zinc-700 text-zinc-500'
                  }`}>{lot.status === 'active' ? '● Активен' : '✓ Завершён'}</span>
                  <span className="text-[10px] font-black text-zinc-400 uppercase">#{lot.id}</span>
                </div>
                <div className="flex items-center gap-4 text-[10px] text-zinc-500">
                  <div className="text-center">
                    <div className="font-black text-zinc-300">{lot.participants?.length || 0}</div>
                    <div className="uppercase">участников</div>
                  </div>
                  <div className="text-center">
                    <div className="font-black text-amber-400">{lot.winners_count}</div>
                    <div className="uppercase">победит</div>
                  </div>
                </div>
              </div>
              {lot.text && (
                <p className="text-xs text-zinc-400 line-clamp-2 mb-2">{lot.text.replace(/<[^>]+>/g, '')}</p>
              )}
              <div className="flex items-center gap-4 text-[9px] text-zinc-600 uppercase font-bold">
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {lot.finish_type === 'time' ? `До: ${lot.finish_value}` : `Первые: ${lot.finish_value} чел.`}
                </span>
                <span>Создан: {lot.created_at}</span>
                {lot.winners?.length > 0 && (
                  <span className="text-amber-400">🏆 {lot.winners.length} победителей</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ════════════════════════════════════════════════════════════
// SUPPORT STATS (оригинальная аналитика для TG/VK)
// ════════════════════════════════════════════════════════════
const SupportStats: React.FC<{ bot: BotConfig; onUpdate: (b: BotConfig) => void }> = ({ bot, onUpdate }) => {
  const [search, setSearch]     = useState('');
  const [filter, setFilter]     = useState<'all'|'active'|'banned'|'unsubscribed'>('all');
  const [lastUpd, setLastUpd]   = useState<Date>(new Date());

  // Обновляем timestamp при каждом ре-рендере с новыми данными
  useEffect(() => { setLastUpd(new Date()); }, [bot.stats]);

  const stats = useMemo(() => {
    const src = (bot.stats && Object.keys(bot.stats).length > 0 ? bot.stats : null) || bot.config?.stats;
    return src || { totalMessages: 0, incomingToday: 0, outgoingToday: 0, bannedCount: 0, history: [], activeUsers24h: 0 };
  }, [bot.stats, bot.config?.stats]);

  const users = (bot.config?.connectedUsers || bot.connectedUsers || []) as any[];

  const metrics = useMemo(() => {
    const total       = users.length;
    const banned      = users.filter(u => u.is_banned).length;
    const unsubscribed= users.filter(u => u.is_active === false).length;
    const active      = users.filter(u => u.is_active !== false && !u.is_banned).length;
    const retention   = total > 0 ? Math.round((active / total) * 100) : 0;
    const h           = stats.history;
    const prevDay     = h?.length > 1 ? h[h.length - 2] : null;
    const today       = h?.length > 0  ? h[h.length - 1] : null;
    const userDiff    = today && prevDay ? (today.totalUsers || 0) - (prevDay.totalUsers || 0) : 0;
    return { total, banned, unsubscribed, active, retention, userDiff };
  }, [users, stats.history]);

  const chartData = useMemo(() => {
    if (!Array.isArray(stats.history) || stats.history.length === 0)
      return [{ date: 'Нет данных', incoming: 0, outgoing: 0, totalUsers: 0 }];
    return stats.history.map((pt: any) => ({
      date: pt.date || '??',
      incoming: pt.incoming || 0,
      outgoing: pt.outgoing || 0,
      totalUsers: pt.totalUsers || 0,
    }));
  }, [stats.history]);

  const filtered = useMemo(() => users.filter(u => {
    const q = search.toLowerCase();
    const m = u.first_name?.toLowerCase().includes(q) || u.username?.toLowerCase().includes(q) || String(u.id).includes(q);
    if (filter === 'active')       return m && u.is_active !== false && !u.is_banned;
    if (filter === 'banned')       return m && u.is_banned;
    if (filter === 'unsubscribed') return m && u.is_active === false;
    return m;
  }), [users, search, filter]);

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* Индикатор обновления */}
      <div className="flex items-center justify-end">
        <span className="text-[9px] text-zinc-600 font-mono flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          Обновлено: {lastUpd.toLocaleTimeString()}
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard icon={<Users className="w-5 h-5 text-blue-400" />}
          label="Пользователей" value={metrics.total} trend={metrics.userDiff} sub="Общий размер базы" />
        <StatCard icon={<UserCheck className="w-5 h-5 text-emerald-400" />}
          label="Активные" value={metrics.active} sub={`${metrics.retention}% удержания`} accent="emerald" />
        <StatCard icon={<MessageSquare className="w-5 h-5 text-purple-400" />}
          label="Сообщений" value={stats.totalMessages} sub={`${stats.incomingToday} сегодня`} />
        <StatCard icon={<UserMinus className="w-5 h-5 text-rose-400" />}
          label="Отток" value={metrics.unsubscribed} sub="Потерянные" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 bg-zinc-900/50 border border-zinc-800 rounded-3xl p-6">
          <h3 className="text-sm font-bold text-zinc-200 flex items-center gap-2 mb-6 uppercase tracking-tight">
            <Activity className="w-4 h-4 text-emerald-500" />Активность сообщений
          </h3>
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="gi" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.2}/>
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis dataKey="date" stroke="#52525b" fontSize={10} tickLine={false} axisLine={false} dy={8} />
                <YAxis stroke="#52525b" fontSize={10} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={chartTooltipStyle} />
                <Area type="monotone" dataKey="incoming" name="Входящие" stroke="#10b981" strokeWidth={2.5} fill="url(#gi)" />
                <Area type="monotone" dataKey="outgoing" name="Исходящие" stroke="#a855f7" strokeWidth={2} fill="transparent" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="bg-zinc-900/50 border border-zinc-800 rounded-3xl p-6">
          <h3 className="text-sm font-bold text-zinc-200 flex items-center gap-2 mb-6 uppercase tracking-tight">
            <TrendingUp className="w-4 h-4 text-blue-500" />Рост базы
          </h3>
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis dataKey="date" stroke="#52525b" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis stroke="#52525b" fontSize={10} hide />
                <Tooltip contentStyle={chartTooltipStyle} />
                <Line type="stepAfter" dataKey="totalUsers" name="Всего" stroke="#3b82f6" strokeWidth={3}
                  dot={{ r: 3, fill: '#3b82f6', strokeWidth: 0 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Список пользователей */}
      <div className="bg-zinc-900/50 border border-zinc-800 rounded-3xl overflow-hidden">
        <div className="p-5 border-b border-zinc-800 flex flex-col sm:flex-row gap-3 justify-between items-center">
          <div className="relative w-full sm:w-80">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
            <input type="text" placeholder="ID, имя, @username..."
              className="w-full bg-zinc-950 border border-zinc-800 rounded-xl py-2.5 pl-10 pr-4 text-sm outline-none focus:border-blue-500 transition-all"
              value={search} onChange={e => setSearch(e.target.value)} />
          </div>
          <div className="flex gap-1 p-1 bg-zinc-950 border border-zinc-800 rounded-xl">
            {(['all','active','unsubscribed','banned'] as const).map(f => (
              <button key={f} onClick={() => setFilter(f)}
                className={`px-3 py-1.5 rounded-lg text-[9px] font-black uppercase transition-all ${
                  filter === f ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-300'
                }`}>
                {f === 'all' ? 'Все' : f === 'active' ? 'Живые' : f === 'unsubscribed' ? 'Ушли' : 'Бан'}
              </button>
            ))}
          </div>
        </div>
        <div className="divide-y divide-zinc-800/40 max-h-[550px] overflow-y-auto">
          {filtered.length === 0 ? (
            <div className="py-16 text-center text-zinc-700 text-xs uppercase font-black tracking-widest opacity-40 flex flex-col items-center gap-3">
              <Zap className="w-8 h-8" />Пользователи не найдены
            </div>
          ) : filtered.map((u: any) => (
            <div key={u.id} className="p-4 hover:bg-white/[0.02] flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-2xl flex items-center justify-center font-black text-base border ${
                  u.is_active === false ? 'border-zinc-800 bg-zinc-900 text-zinc-700' : 'border-blue-500/20 bg-blue-500/10 text-blue-400'
                }`}>{u.first_name?.[0] || '?'}</div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-zinc-200">{u.first_name || 'Anonymous'}</span>
                    {u.is_active === false && <span className="text-[8px] bg-zinc-800 text-zinc-500 px-1.5 py-0.5 rounded font-black uppercase">Ушёл</span>}
                  </div>
                  <div className="flex items-center gap-2 text-[10px] text-zinc-500">
                    <span className="font-mono">ID: {u.id}</span>
                    {u.username && <span className="text-blue-400/60">@{u.username}</span>}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-4">
                {(u.warns || 0) > 0 && (
                  <div className="text-center px-2 py-1 bg-amber-500/5 border border-amber-500/10 rounded-xl">
                    <div className="text-[8px] text-amber-500/50 font-black uppercase">Warns</div>
                    <div className="text-xs font-bold text-amber-400">{u.warns}</div>
                  </div>
                )}
                {u.is_banned && (
                  <div className="p-2 bg-rose-500/10 rounded-xl border border-rose-500/20">
                    <ShieldAlert className="w-4 h-4 text-rose-400" />
                  </div>
                )}
                <div className="flex items-center gap-1 text-[9px] text-zinc-600 font-mono">
                  <Clock className="w-3 h-3" />
                  {u.last_seen ? new Date(u.last_seen * 1000).toLocaleDateString() : '—'}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// ════════════════════════════════════════════════════════════
// MAIN EXPORT — роутинг по типу
// ════════════════════════════════════════════════════════════
const BotStatsView: React.FC<Props> = ({ bot, onUpdate }) => {
  const [liveStats, setLive] = useState<any>(null);
  const [lastUpd, setLastUpd] = useState<Date|null>(null);
  const [polling, setPolling] = useState(true);
  const pollRef = useRef<ReturnType<typeof setInterval>|null>(null);

  useEffect(() => {
    const doFetch = async () => {
      try {
        const data = await api.getBotStats(bot.id);
        if (data?.stats) { setLive(data.stats); setLastUpd(new Date()); }
      } catch {}
    };
    doFetch();
    if (polling) pollRef.current = setInterval(doFetch, POLL_MS);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [bot.id, polling]);

  // Для постера приоритет: liveStats (если содержит totalPosts), иначе config.stats
  const effectiveBot = (() => {
    if (!liveStats) return bot;
    if (bot.platform === 'poster') {
      // Мержим: берём totalPosts из liveStats (если есть), иначе из config
      const configStats = bot.config?.stats || bot.stats || {};
      const merged = {
        ...configStats,
        ...liveStats,
        totalPosts: (liveStats.totalPosts || 0) > 0 ? liveStats.totalPosts : (configStats.totalPosts || 0),
        history: (liveStats.history?.length > 0 ? liveStats.history : configStats.history) || [],
      };
      return { ...bot, stats: merged };
    }
    return { ...bot, stats: { ...bot.stats, ...liveStats } };
  })();

  if (bot.platform === 'poster') {
    const stats = effectiveBot.stats || {};
    return (
      <div>
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-sm font-black text-zinc-300 uppercase flex items-center gap-2">
            <Send className="w-4 h-4 text-emerald-500" />Аналитика постинга
          </h2>
          <div className="flex items-center gap-2">
            <button onClick={() => setPolling(p => !p)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[9px] font-black uppercase border transition-all ${
                polling ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-zinc-900 border-zinc-800 text-zinc-500'
              }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${polling ? 'bg-emerald-500 animate-pulse' : 'bg-zinc-600'}`} />
              {polling ? 'Live' : 'Пауза'}
            </button>
            {lastUpd && <span className="text-[9px] text-zinc-600 font-mono">{lastUpd.toLocaleTimeString()}</span>}
          </div>
        </div>
        <PosterStats stats={stats} />
      </div>
    );
  }

  if (bot.platform === 'randomizer') {
    return (
      <div>
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-sm font-black text-zinc-300 uppercase flex items-center gap-2">
            <Shuffle className="w-4 h-4 text-purple-500" />Аналитика розыгрышей
          </h2>
          <div className="flex items-center gap-2">
            <button onClick={() => setPolling(p => !p)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[9px] font-black uppercase border transition-all ${
                polling ? 'bg-purple-500/10 border-purple-500/30 text-purple-400' : 'bg-zinc-900 border-zinc-800 text-zinc-500'
              }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${polling ? 'bg-purple-500 animate-pulse' : 'bg-zinc-600'}`} />
              {polling ? 'Live' : 'Пауза'}
            </button>
            {lastUpd && <span className="text-[9px] text-zinc-600 font-mono">{lastUpd.toLocaleTimeString()}</span>}
          </div>
        </div>
        <RandomizerStats bot={effectiveBot} />
      </div>
    );
  }

  // Support bot (TG + VK) — передаём данные в SupportStats, убираем двойной polling
  return <SupportStats bot={effectiveBot} onUpdate={onUpdate} />;
};

export default BotStatsView;
