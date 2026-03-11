import React, { useState, useEffect } from 'react';
import { User } from '../types';
import { api } from '../services/apiService';
import {
  Users,
  Copy,
  Check,
  Gift,
  TrendingUp,
  Link2,
  Crown,
  Sparkles,
  ChevronRight,
  Wallet
} from 'lucide-react';

interface ReferralsProps {
  user: User;
  onUserUpdate?: (user: User) => void;
}

interface ReferralStats {
  referral_code: string;
  referral_link: string;
  total_invited: number;
  earnings_total: number;
  commission_percent: number;
  referrals: Array<{
    id: string;
    username: string;
    joined_at: number;
    earned_from: number;
  }>;
}

const Referrals: React.FC<ReferralsProps> = ({ user, onUserUpdate }) => {
  const [stats, setStats] = useState<ReferralStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    loadStats();
  }, [user.id]);

  const loadStats = async () => {
    setLoading(true);
    try {
      const data = await api.getReferralStats(user.id);
      setStats(data);
    } catch (e) {
      console.error('Failed to load referral stats', e);
    }
    setLoading(false);
  };

  const copyLink = () => {
    if (!stats) return;
    navigator.clipboard.writeText(stats.referral_link);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Получаем уровень комиссии исходя из количества приглашенных
  const getCommissionTier = (count: number) => {
    if (count >= 20) return { percent: 20, label: 'Элита', color: 'text-yellow-400', bg: 'bg-yellow-400/10 border-yellow-400/20' };
    if (count >= 10) return { percent: 15, label: 'Про', color: 'text-purple-400', bg: 'bg-purple-400/10 border-purple-400/20' };
    return { percent: 10, label: 'Базовый', color: 'text-blue-400', bg: 'bg-blue-400/10 border-blue-400/20' };
  };

  const tier = getCommissionTier(stats?.total_invited || 0);

  // Следующий порог
  const nextThreshold = (stats?.total_invited || 0) < 10 ? 10 : (stats?.total_invited || 0) < 20 ? 20 : null;
  const progress = nextThreshold
    ? Math.min(100, ((stats?.total_invited || 0) / nextThreshold) * 100)
    : 100;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-zinc-500 text-xs font-bold uppercase tracking-widest">Загрузка...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      {/* Заголовок */}
      <div>
        <h1 className="text-2xl font-black text-white tracking-tight">Реферальная программа</h1>
        <p className="text-zinc-500 text-sm mt-1">Приглашайте друзей и зарабатывайте с каждой их покупки</p>
      </div>

      {/* Карточки статистики */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-9 h-9 rounded-xl bg-blue-600/10 flex items-center justify-center">
              <Users size={18} className="text-blue-400" />
            </div>
            <span className="text-xs font-black uppercase tracking-widest text-zinc-500">Приглашено</span>
          </div>
          <p className="text-3xl font-black text-white">{stats?.total_invited ?? 0}</p>
          <p className="text-[10px] text-zinc-600 mt-1 font-bold uppercase tracking-widest">пользователей</p>
        </div>

        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-9 h-9 rounded-xl bg-emerald-600/10 flex items-center justify-center">
              <Wallet size={18} className="text-emerald-400" />
            </div>
            <span className="text-xs font-black uppercase tracking-widest text-zinc-500">Заработано</span>
          </div>
          <p className="text-3xl font-black text-white">{stats?.earnings_total ?? 0} ₽</p>
          <p className="text-[10px] text-zinc-600 mt-1 font-bold uppercase tracking-widest">на баланс</p>
        </div>

        <div className={`border rounded-2xl p-5 ${tier.bg}`}>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-9 h-9 rounded-xl bg-white/5 flex items-center justify-center">
              <Crown size={18} className={tier.color} />
            </div>
            <span className="text-xs font-black uppercase tracking-widest text-zinc-500">Ваш уровень</span>
          </div>
          <p className={`text-3xl font-black ${tier.color}`}>{tier.percent}%</p>
          <p className={`text-[10px] mt-1 font-black uppercase tracking-widest ${tier.color} opacity-70`}>{tier.label}</p>
        </div>
      </div>

      {/* Прогресс до следующего уровня */}
      {nextThreshold && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <TrendingUp size={16} className="text-purple-400" />
              <span className="text-sm font-black text-white">Прогресс до следующего уровня</span>
            </div>
            <span className="text-xs font-bold text-zinc-500">
              {stats?.total_invited ?? 0} / {nextThreshold}
            </span>
          </div>
          <div className="w-full bg-zinc-800 rounded-full h-2.5 overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-blue-500 to-purple-500 rounded-full transition-all duration-700"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-xs text-zinc-500 mt-2">
            Ещё {nextThreshold - (stats?.total_invited || 0)} приглашений — и комиссия вырастет до{' '}
            <span className="text-purple-400 font-bold">{nextThreshold >= 20 ? 20 : 15}%</span>
          </p>
        </div>
      )}

      {/* Реферальная ссылка */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Link2 size={16} className="text-blue-400" />
          <h2 className="text-sm font-black text-white uppercase tracking-widest">Ваша реферальная ссылка</h2>
        </div>

        <div className="flex gap-2">
          <div className="flex-1 bg-black border border-zinc-800 rounded-xl px-4 py-3 font-mono text-xs text-zinc-400 truncate select-all">
            {stats?.referral_link ?? 'Загрузка...'}
          </div>
          <button
            onClick={copyLink}
            className={`px-4 py-3 rounded-xl flex items-center gap-2 font-black text-xs uppercase tracking-widest transition-all ${
              copied
                ? 'bg-green-600 text-white'
                : 'bg-blue-600 hover:bg-blue-700 text-white'
            }`}
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
            {copied ? 'Скопировано' : 'Копировать'}
          </button>
        </div>

        <p className="text-[10px] text-zinc-600 font-bold uppercase tracking-widest">
          Ваш код: <span className="text-blue-400">{stats?.referral_code ?? '...'}</span>
        </p>
      </div>

      {/* Как это работает */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <Sparkles size={16} className="text-yellow-400" />
          <h2 className="text-sm font-black text-white uppercase tracking-widest">Как это работает</h2>
        </div>
        <div className="space-y-3">
          {[
            { step: '01', text: 'Поделитесь ссылкой с другом', sub: 'Скопируйте ссылку и отправьте кому угодно' },
            { step: '02', text: 'Друг регистрируется', sub: 'Вам зачислится +10 ₽ после успешной регистрации' },
            { step: '03', text: 'Друг совершает покупки', sub: `Вы получаете ${tier.percent}% от каждой его оплаты` },
            { step: '04', text: 'Приглашайте больше', sub: 'С 10 друзей — 15%, с 20 — 20% комиссия' },
          ].map((item) => (
            <div key={item.step} className="flex items-start gap-4">
              <div className="w-8 h-8 rounded-lg bg-blue-600/10 border border-blue-600/20 flex items-center justify-center shrink-0">
                <span className="text-[10px] font-black text-blue-400">{item.step}</span>
              </div>
              <div>
                <p className="text-sm font-bold text-white">{item.text}</p>
                <p className="text-xs text-zinc-500">{item.sub}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Список приглашённых */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <Gift size={16} className="text-emerald-400" />
          <h2 className="text-sm font-black text-white uppercase tracking-widest">
            Приглашённые ({stats?.referrals?.length ?? 0})
          </h2>
        </div>

        {!stats?.referrals?.length ? (
          <div className="text-center py-8 border border-dashed border-zinc-800 rounded-xl">
            <Users size={28} className="text-zinc-700 mx-auto mb-2" />
            <p className="text-[11px] text-zinc-600 font-bold uppercase tracking-widest">Пока никого нет</p>
            <p className="text-xs text-zinc-700 mt-1">Поделитесь ссылкой чтобы начать зарабатывать</p>
          </div>
        ) : (
          <div className="space-y-2">
            {stats.referrals.map((ref) => (
              <div
                key={ref.id}
                className="flex items-center justify-between px-4 py-3 rounded-xl bg-zinc-800/50 border border-zinc-800"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center text-white text-xs font-black">
                    {ref.username.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <p className="text-sm font-bold text-white">{ref.username}</p>
                    <p className="text-[10px] text-zinc-500">
                      {new Date(ref.joined_at).toLocaleDateString('ru-RU')}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm font-black text-emerald-400">+{ref.earned_from} ₽</p>
                  <p className="text-[10px] text-zinc-600">заработано</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default Referrals;
