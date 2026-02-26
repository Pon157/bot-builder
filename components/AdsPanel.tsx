// AdsPanel.tsx — Панель рекламодателя (/ads)
// Публичная страница, не требует основного User (своя авторизация)

import React, { useState, useEffect } from 'react';
import {
  Megaphone, Plus, BarChart2, Eye, DollarSign, Pause, Play,
  LogIn, UserPlus, ArrowLeft, Loader2, AlertTriangle, TrendingUp,
  Wallet, ChevronRight, X, CheckCircle, ImageIcon, ExternalLink
} from 'lucide-react';

const API_BASE = (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000';

const DEFAULT_CPM = 0.50;  // стоимость 1 показа по умолчанию

interface Advertiser {
  id: string;
  name: string;
  email: string;
  balance: number;
}

interface Campaign {
  id: string;
  advertiser_id: string;
  title: string;
  ad_text: string;
  photo_url?: string;
  button_text?: string;
  button_url?: string;
  budget: number;
  balance: number;
  cost_per_impression: number;
  impressions: number;
  status: 'active' | 'paused' | 'depleted';
  created_at: number;
}

const api = {
  async register(name: string, email: string, password: string): Promise<Advertiser> {
    const r = await fetch(`${API_BASE}/api/ads/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password }),
    });
    if (!r.ok) throw new Error((await r.json()).detail || 'Ошибка регистрации');
    return r.json();
  },
  async login(email: string, password: string): Promise<Advertiser> {
    const r = await fetch(`${API_BASE}/api/ads/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!r.ok) throw new Error((await r.json()).detail || 'Неверный email или пароль');
    return r.json();
  },
  async getCampaigns(advId: string): Promise<Campaign[]> {
    const r = await fetch(`${API_BASE}/api/ads/campaigns?advertiser_id=${advId}`);
    return r.ok ? r.json() : [];
  },
  async createCampaign(data: Partial<Campaign> & { advertiser_id: string }): Promise<Campaign> {
    const r = await fetch(`${API_BASE}/api/ads/campaigns`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!r.ok) throw new Error((await r.json()).detail || 'Ошибка создания кампании');
    return r.json();
  },
  async updateCampaign(campId: string, advId: string, data: Partial<Campaign>): Promise<void> {
    const r = await fetch(`${API_BASE}/api/ads/campaigns/${campId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...data, advertiser_id: advId }),
    });
    if (!r.ok) throw new Error('Ошибка обновления');
  },
  async topupCampaign(campId: string, advId: string, amount: number): Promise<{ new_balance: number; advertiser_balance: number }> {
    const r = await fetch(`${API_BASE}/api/ads/campaigns/${campId}/topup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ advertiser_id: advId, amount }),
    });
    if (!r.ok) throw new Error((await r.json()).detail || 'Ошибка пополнения');
    return r.json();
  },
  async getStats(campId: string, advId: string): Promise<any> {
    const r = await fetch(`${API_BASE}/api/ads/stats/${campId}?advertiser_id=${advId}`);
    return r.ok ? r.json() : null;
  },
};

// ── ХЕЛПЕРЫ ────────────────────────────────────────────────────────────────
const statusConfig = {
  active:   { label: 'Активна',   color: 'text-emerald-400', dot: 'bg-emerald-500', bg: 'bg-emerald-500/10 border-emerald-500/20' },
  paused:   { label: 'На паузе',  color: 'text-yellow-400',  dot: 'bg-yellow-500',  bg: 'bg-yellow-500/10 border-yellow-500/20' },
  depleted: { label: 'Исчерпана', color: 'text-zinc-500',    dot: 'bg-zinc-600',    bg: 'bg-zinc-800 border-zinc-700' },
};

const fmt = (n: number) => n.toFixed(2);


// ════════════════════════════════════════════════════════════════════════
// КОМПОНЕНТ
// ════════════════════════════════════════════════════════════════════════
const AdsPanel: React.FC = () => {
  const [adv, setAdv] = useState<Advertiser | null>(() => {
    const raw = localStorage.getItem('ads_session');
    return raw ? JSON.parse(raw) : null;
  });

  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [authEmail, setAuthEmail] = useState('');
  const [authPwd,   setAuthPwd]   = useState('');
  const [authName,  setAuthName]  = useState('');
  const [authLoading, setAuthLoading] = useState(false);

  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState('');
  const [success, setSuccess] = useState('');

  // Модалки
  const [showCreate, setShowCreate] = useState(false);
  const [showStats,  setShowStats]  = useState<Campaign | null>(null);
  const [statsData,  setStatsData]  = useState<any>(null);
  const [showTopup,  setShowTopup]  = useState<Campaign | null>(null);
  const [topupAmt,   setTopupAmt]   = useState('100');

  // Форма создания
  const [cfTitle,   setCfTitle]   = useState('');
  const [cfText,    setCfText]    = useState('');
  const [cfPhoto,   setCfPhoto]   = useState('');
  const [cfBtnText, setCfBtnText] = useState('');
  const [cfBtnUrl,  setCfBtnUrl]  = useState('');
  const [cfBudget,  setCfBudget]  = useState('100');
  const [cfCpi,     setCfCpi]     = useState(String(DEFAULT_CPM));
  const [cfSaving,  setCfSaving]  = useState(false);

  useEffect(() => {
    if (adv) loadCampaigns();
  }, [adv]);

  const notify = (msg: string, isErr = false) => {
    if (isErr) { setError(msg); setTimeout(() => setError(''), 5000); }
    else { setSuccess(msg); setTimeout(() => setSuccess(''), 3000); }
  };

  const loadCampaigns = async () => {
    if (!adv) return;
    setLoading(true);
    try {
      const c = await api.getCampaigns(adv.id);
      setCampaigns(c);
    } finally { setLoading(false); }
  };

  // ── Auth ──────────────────────────────────────────────────────────────
  const handleAuth = async () => {
    if (!authEmail.trim() || !authPwd.trim()) return notify('Заполните все поля', true);
    setAuthLoading(true);
    try {
      let a: Advertiser;
      if (authMode === 'register') {
        if (!authName.trim()) return notify('Введите имя / название компании', true);
        a = await api.register(authName, authEmail, authPwd);
      } else {
        a = await api.login(authEmail, authPwd);
      }
      localStorage.setItem('ads_session', JSON.stringify(a));
      setAdv(a);
    } catch (e: any) {
      notify(e.message, true);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('ads_session');
    setAdv(null);
    setCampaigns([]);
  };

  // ── Создание кампании ─────────────────────────────────────────────────
  const handleCreate = async () => {
    if (!adv) return;
    if (!cfTitle.trim() || !cfText.trim()) return notify('Заполните название и текст объявления', true);
    const budget = parseFloat(cfBudget);
    const cpi    = parseFloat(cfCpi);
    if (isNaN(budget) || budget < 100) return notify('Минимальный бюджет 100 ₽', true);
    if (isNaN(cpi) || cpi < 0.10) return notify('Минимальная ставка 0.10 ₽/показ', true);
    if (budget > adv.balance) return notify(`Недостаточно средств. Баланс: ${fmt(adv.balance)} ₽`, true);

    setCfSaving(true);
    try {
      const camp = await api.createCampaign({
        advertiser_id: adv.id,
        title: cfTitle,
        ad_text: cfText,
        photo_url: cfPhoto,
        button_text: cfBtnText,
        button_url: cfBtnUrl,
        budget,
        cost_per_impression: cpi,
      });
      setCampaigns(prev => [camp, ...prev]);
      setAdv(prev => prev ? { ...prev, balance: prev.balance - budget } : prev);
      setShowCreate(false);
      resetCreateForm();
      notify('Кампания создана и отправлена на модерацию!');
    } catch (e: any) {
      notify(e.message, true);
    } finally {
      setCfSaving(false);
    }
  };

  const resetCreateForm = () => {
    setCfTitle(''); setCfText(''); setCfPhoto('');
    setCfBtnText(''); setCfBtnUrl('');
    setCfBudget('100'); setCfCpi(String(DEFAULT_CPM));
  };

  // ── Пауза/Возобновление ───────────────────────────────────────────────
  const handleToggle = async (camp: Campaign) => {
    if (!adv) return;
    if (camp.status === 'depleted') return notify('Пополните баланс кампании', true);
    const newStatus = camp.status === 'active' ? 'paused' : 'active';
    try {
      await api.updateCampaign(camp.id, adv.id, { status: newStatus });
      setCampaigns(prev => prev.map(c => c.id === camp.id ? { ...c, status: newStatus as any } : c));
    } catch (e: any) { notify(e.message, true); }
  };

  // ── Пополнение кампании ───────────────────────────────────────────────
  const handleTopup = async () => {
    if (!adv || !showTopup) return;
    const amount = parseFloat(topupAmt);
    if (isNaN(amount) || amount <= 0) return notify('Введите сумму', true);
    if (amount > adv.balance) return notify(`Недостаточно средств. Баланс: ${fmt(adv.balance)} ₽`, true);
    try {
      const res = await api.topupCampaign(showTopup.id, adv.id, amount);
      setCampaigns(prev => prev.map(c => c.id === showTopup.id
        ? { ...c, balance: res.new_balance, budget: c.budget + amount, status: 'active' as any }
        : c
      ));
      setAdv(prev => prev ? { ...prev, balance: res.advertiser_balance } : prev);
      setShowTopup(null);
      notify(`Бюджет пополнен на ${amount} ₽`);
    } catch (e: any) { notify(e.message, true); }
  };

  // ── Статистика ────────────────────────────────────────────────────────
  const openStats = async (camp: Campaign) => {
    if (!adv) return;
    setShowStats(camp);
    setStatsData(null);
    try {
      const s = await api.getStats(camp.id, adv.id);
      setStatsData(s);
    } catch (e) {
      setStatsData({ error: 'Ошибка загрузки' });
    }
  };

  // ════════════════════════════════════════════════════════════════════════
  // РЕНДЕР — АВТОРИЗАЦИЯ
  // ════════════════════════════════════════════════════════════════════════
  if (!adv) {
    return (
      <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center p-4">
        <div className="w-full max-w-md">
          <div className="text-center mb-8">
            <div className="w-14 h-14 bg-orange-500/15 border border-orange-500/20 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <Megaphone className="text-orange-400" size={26} />
            </div>
            <h1 className="text-white font-black text-2xl uppercase tracking-tight">Рекламный кабинет</h1>
            <p className="text-zinc-500 text-sm mt-1">Dialoge Engine · Ads Platform</p>
          </div>

          {/* Вкладки */}
          <div className="flex bg-zinc-900 border border-zinc-800 rounded-2xl p-1 mb-6">
            {(['login', 'register'] as const).map(m => (
              <button
                key={m}
                onClick={() => setAuthMode(m)}
                className={`flex-1 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest transition-all ${
                  authMode === m
                    ? 'bg-orange-500 text-white shadow'
                    : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {m === 'login' ? 'Войти' : 'Регистрация'}
              </button>
            ))}
          </div>

          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 space-y-4">
            {error && (
              <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-xs flex items-center gap-2">
                <AlertTriangle size={14} /> {error}
              </div>
            )}

            {authMode === 'register' && (
              <div>
                <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">Имя / Компания</label>
                <input
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 text-white text-sm focus:border-orange-500 focus:outline-none"
                  value={authName} onChange={e => setAuthName(e.target.value)}
                  placeholder="ООО «Ваша компания»"
                />
              </div>
            )}

            <div>
              <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">Email</label>
              <input
                type="email"
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 text-white text-sm focus:border-orange-500 focus:outline-none"
                value={authEmail} onChange={e => setAuthEmail(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleAuth()}
                placeholder="you@company.com"
              />
            </div>

            <div>
              <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">Пароль</label>
              <input
                type="password"
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 text-white text-sm focus:border-orange-500 focus:outline-none"
                value={authPwd} onChange={e => setAuthPwd(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleAuth()}
                placeholder="••••••••"
              />
            </div>

            <button
              onClick={handleAuth}
              disabled={authLoading}
              className="w-full py-3 bg-orange-500 hover:bg-orange-600 disabled:opacity-50 rounded-xl text-white font-black uppercase text-sm tracking-widest transition-colors flex items-center justify-center gap-2"
            >
              {authLoading
                ? <Loader2 size={16} className="animate-spin" />
                : authMode === 'login'
                  ? <><LogIn size={16} /> Войти</>
                  : <><UserPlus size={16} /> Зарегистрироваться</>
              }
            </button>
          </div>

          {/* Инфо */}
          <div className="mt-6 grid grid-cols-3 gap-3 text-center">
            {[
              { label: 'Стоимость', value: 'от 0.50 ₽' },
              { label: 'Аудитория', value: 'Telegram' },
              { label: 'Модерация', value: '1-2 дня' },
            ].map(item => (
              <div key={item.label} className="bg-zinc-900 border border-zinc-800 rounded-xl p-3">
                <p className="text-white font-black text-sm">{item.value}</p>
                <p className="text-zinc-600 text-[10px] uppercase mt-0.5">{item.label}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // ════════════════════════════════════════════════════════════════════════
  // РЕНДЕР — ДАШБОРД
  // ════════════════════════════════════════════════════════════════════════
  const totalImp  = campaigns.reduce((a, c) => a + (c.impressions || 0), 0);
  const totalSpent = campaigns.reduce((a, c) => a + (c.budget - c.balance), 0);
  const activeCount = campaigns.filter(c => c.status === 'active').length;

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-zinc-300 p-4 md:p-10">
      <div className="max-w-5xl mx-auto">

        {/* Хедер */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-orange-500/15 border border-orange-500/20 rounded-xl flex items-center justify-center">
              <Megaphone className="text-orange-400" size={18} />
            </div>
            <div>
              <p className="text-white font-black text-lg uppercase tracking-tight">Рекламный кабинет</p>
              <p className="text-zinc-600 text-xs">{adv.name} · {adv.email}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-4 py-2 bg-zinc-900 border border-zinc-800 rounded-xl">
              <Wallet size={14} className="text-orange-400" />
              <span className="text-white font-black text-sm">{fmt(adv.balance)} ₽</span>
              <span className="text-zinc-600 text-xs">баланс</span>
            </div>
            <button
              onClick={handleLogout}
              className="px-3 py-2 text-zinc-500 hover:text-zinc-300 text-xs font-bold transition-colors"
            >
              Выйти
            </button>
          </div>
        </div>

        {/* Уведомления */}
        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm flex items-center gap-2">
            <AlertTriangle size={16} /> {error}
          </div>
        )}
        {success && (
          <div className="mb-4 p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-400 text-sm flex items-center gap-2">
            <CheckCircle size={16} /> {success}
          </div>
        )}

        {/* Метрики */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
          {[
            { label: 'Показов всего',   value: totalImp.toLocaleString(), icon: Eye,        color: 'text-blue-400' },
            { label: 'Потрачено',       value: `${fmt(totalSpent)} ₽`,   icon: DollarSign,  color: 'text-orange-400' },
            { label: 'Активных кампаний', value: String(activeCount),    icon: TrendingUp,  color: 'text-emerald-400' },
            { label: 'Баланс счёта',    value: `${fmt(adv.balance)} ₽`,  icon: Wallet,      color: 'text-violet-400' },
          ].map(m => (
            <div key={m.label} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
              <m.icon size={16} className={`${m.color} mb-2`} />
              <p className="text-white font-black text-xl">{m.value}</p>
              <p className="text-zinc-600 text-[10px] uppercase mt-0.5">{m.label}</p>
            </div>
          ))}
        </div>

        {/* Пополнение баланса счёта */}
        <div className="mb-6 p-4 bg-orange-500/5 border border-orange-500/15 rounded-2xl flex flex-col md:flex-row md:items-center gap-3 md:gap-6">
          <div className="flex-1">
            <p className="text-orange-300 font-bold text-sm">Пополнение баланса счёта</p>
            <p className="text-zinc-500 text-xs mt-0.5">
              Пополните через Telegram-бота: найдите нашего бота, команда /ads → выберите пакет.
              После подтверждения баланс зачислится автоматически.
            </p>
          </div>
          <a
            href="https://t.me/dialoge_engine_bot"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 px-4 py-2.5 bg-orange-500 hover:bg-orange-600 rounded-xl text-white text-xs font-black uppercase tracking-wider transition-colors whitespace-nowrap"
          >
            Пополнить через бот <ExternalLink size={13} />
          </a>
        </div>

        {/* Кампании */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-white font-black uppercase text-sm tracking-widest">Кампании</h2>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2 bg-orange-500 hover:bg-orange-600 rounded-xl text-white text-xs font-black uppercase tracking-wider transition-colors"
          >
            <Plus size={14} /> Создать
          </button>
        </div>

        {loading && (
          <div className="flex justify-center py-12"><Loader2 className="text-orange-500 animate-spin" size={28} /></div>
        )}

        {!loading && campaigns.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 border border-dashed border-zinc-800 rounded-3xl gap-4">
            <Megaphone size={40} className="text-zinc-700" />
            <p className="text-zinc-500 text-sm text-center">Нет кампаний. Создайте первую!</p>
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-2 px-5 py-2.5 bg-orange-500 hover:bg-orange-600 rounded-xl text-white text-sm font-bold transition-colors"
            >
              <Plus size={15} /> Создать кампанию
            </button>
          </div>
        )}

        <div className="space-y-3">
          {campaigns.map(camp => {
            const sc = statusConfig[camp.status] || statusConfig.paused;
            const spent = camp.budget - camp.balance;
            const pct = camp.budget > 0 ? Math.min(100, (spent / camp.budget) * 100) : 0;
            return (
              <div key={camp.id} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
                <div className="flex items-start justify-between gap-4 mb-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <div className={`w-2 h-2 rounded-full ${sc.dot} ${camp.status === 'active' ? 'animate-pulse' : ''}`} />
                      <span className="text-white font-bold text-sm truncate">{camp.title}</span>
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${sc.bg} ${sc.color}`}>
                        {sc.label}
                      </span>
                    </div>
                    <p className="text-zinc-500 text-xs line-clamp-2">{camp.ad_text}</p>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => openStats(camp)}
                      className="p-2 hover:bg-zinc-800 rounded-lg transition-colors"
                      title="Статистика"
                    >
                      <BarChart2 size={15} className="text-zinc-400" />
                    </button>
                    <button
                      onClick={() => { setShowTopup(camp); setTopupAmt('100'); }}
                      className="p-2 hover:bg-zinc-800 rounded-lg transition-colors"
                      title="Пополнить бюджет"
                    >
                      <Wallet size={15} className="text-zinc-400" />
                    </button>
                    <button
                      onClick={() => handleToggle(camp)}
                      disabled={camp.status === 'depleted'}
                      className="p-2 hover:bg-zinc-800 disabled:opacity-30 rounded-lg transition-colors"
                      title={camp.status === 'active' ? 'Пауза' : 'Запустить'}
                    >
                      {camp.status === 'active'
                        ? <Pause size={15} className="text-yellow-400" />
                        : <Play size={15} className="text-emerald-400" />
                      }
                    </button>
                  </div>
                </div>

                {/* Прогресс бюджета */}
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-[10px] text-zinc-600 uppercase">
                    <span>Бюджет использован</span>
                    <span>{fmt(spent)} / {fmt(camp.budget)} ₽</span>
                  </div>
                  <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${camp.status === 'depleted' ? 'bg-zinc-600' : 'bg-orange-500'}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>

                <div className="flex items-center gap-4 mt-3 text-xs text-zinc-600">
                  <span><Eye size={11} className="inline mr-1" />{camp.impressions.toLocaleString()} показов</span>
                  <span>{fmt(camp.cost_per_impression)} ₽/показ</span>
                  <span>Остаток: <span className="text-zinc-400">{fmt(camp.balance)} ₽</span></span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Модалка создания кампании ────────────────────────────────── */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-[#111] border border-zinc-800 rounded-2xl w-full max-w-xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-5 border-b border-zinc-800 sticky top-0 bg-[#111]">
              <span className="text-white font-black uppercase text-sm tracking-widest">Новая кампания</span>
              <button onClick={() => { setShowCreate(false); resetCreateForm(); }}>
                <X size={18} className="text-zinc-500 hover:text-white" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              <div>
                <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">Название кампании</label>
                <input
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-2.5 text-white text-sm focus:border-orange-500 focus:outline-none"
                  value={cfTitle} onChange={e => setCfTitle(e.target.value)}
                  placeholder="Летняя распродажа 2025"
                />
              </div>

              <div>
                <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">Текст объявления</label>
                <textarea
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-2.5 text-white text-sm focus:border-orange-500 focus:outline-none resize-none"
                  rows={4}
                  value={cfText} onChange={e => setCfText(e.target.value)}
                  placeholder="Ваш рекламный текст (поддерживает HTML: <b>, <i>, <a href>)"
                />
                <p className="text-zinc-600 text-[10px] mt-1">Поддерживается HTML: &lt;b&gt;, &lt;i&gt;, &lt;a href=&quot;...&quot;&gt;</p>
              </div>

              <div>
                <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block flex items-center gap-1">
                  <ImageIcon size={11} /> URL изображения (необязательно)
                </label>
                <input
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-2.5 text-white text-sm font-mono focus:border-orange-500 focus:outline-none"
                  value={cfPhoto} onChange={e => setCfPhoto(e.target.value)}
                  placeholder="https://example.com/image.jpg"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">Текст кнопки (необязательно)</label>
                  <input
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-2.5 text-white text-sm focus:border-orange-500 focus:outline-none"
                    value={cfBtnText} onChange={e => setCfBtnText(e.target.value)}
                    placeholder="Перейти на сайт"
                  />
                </div>
                <div>
                  <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">URL кнопки</label>
                  <input
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-2.5 text-white text-sm font-mono focus:border-orange-500 focus:outline-none"
                    value={cfBtnUrl} onChange={e => setCfBtnUrl(e.target.value)}
                    placeholder="https://yoursite.com"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">Бюджет кампании (₽)</label>
                  <input
                    type="number" min="100"
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-2.5 text-white text-sm focus:border-orange-500 focus:outline-none"
                    value={cfBudget} onChange={e => setCfBudget(e.target.value)}
                  />
                  <p className="text-zinc-600 text-[10px] mt-1">Минимум 100 ₽</p>
                </div>
                <div>
                  <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">Цена за показ (₽)</label>
                  <input
                    type="number" min="0.10" step="0.10"
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-2.5 text-white text-sm focus:border-orange-500 focus:outline-none"
                    value={cfCpi} onChange={e => setCfCpi(e.target.value)}
                  />
                  <p className="text-zinc-600 text-[10px] mt-1">
                    {cfBudget && cfCpi
                      ? `≈ ${Math.floor(parseFloat(cfBudget) / parseFloat(cfCpi)).toLocaleString()} показов`
                      : 'Минимум 0.10 ₽'
                    }
                  </p>
                </div>
              </div>

              <div className="p-3 bg-orange-500/5 border border-orange-500/15 rounded-xl text-xs text-zinc-500">
                💡 Чем выше ставка, тем чаще ваша реклама будет показываться.
                Стандартная ставка: <b className="text-orange-400">0.50 ₽/показ</b>.
              </div>

              {/* Итог */}
              <div className="flex items-center justify-between p-3 bg-zinc-800 rounded-xl">
                <span className="text-zinc-400 text-sm">Спишется с баланса:</span>
                <span className="text-white font-black text-sm">{parseFloat(cfBudget) || 0} ₽</span>
              </div>

              <div className="flex gap-3 pt-1">
                <button
                  onClick={handleCreate}
                  disabled={cfSaving}
                  className="flex-1 py-3 bg-orange-500 hover:bg-orange-600 disabled:opacity-50 rounded-xl text-white font-black text-sm uppercase tracking-wider transition-colors flex items-center justify-center gap-2"
                >
                  {cfSaving ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
                  Создать кампанию
                </button>
                <button
                  onClick={() => { setShowCreate(false); resetCreateForm(); }}
                  className="px-5 py-3 bg-zinc-800 hover:bg-zinc-700 rounded-xl text-zinc-300 text-sm font-bold transition-colors"
                >
                  Отмена
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Модалка статистики ──────────────────────────────────────── */}
      {showStats && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-[#111] border border-zinc-800 rounded-2xl w-full max-w-lg">
            <div className="flex items-center justify-between p-5 border-b border-zinc-800">
              <span className="text-white font-black uppercase text-sm tracking-widest">
                Статистика: {showStats.title}
              </span>
              <button onClick={() => { setShowStats(null); setStatsData(null); }}>
                <X size={18} className="text-zinc-500 hover:text-white" />
              </button>
            </div>
            <div className="p-5">
              {!statsData && <div className="flex justify-center py-8"><Loader2 className="text-orange-500 animate-spin" size={24} /></div>}
              {statsData?.error && <p className="text-red-400 text-sm text-center py-4">{statsData.error}</p>}
              {statsData && !statsData.error && (
                <div className="space-y-4">
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      { label: 'Показов', value: statsData.total_impressions?.toLocaleString() ?? '0' },
                      { label: 'Потрачено', value: `${fmt(statsData.spent ?? 0)} ₽` },
                      { label: 'Остаток', value: `${fmt(statsData.balance ?? 0)} ₽` },
                    ].map(s => (
                      <div key={s.label} className="bg-zinc-900 border border-zinc-800 rounded-xl p-3 text-center">
                        <p className="text-white font-black text-lg">{s.value}</p>
                        <p className="text-zinc-600 text-[10px] uppercase">{s.label}</p>
                      </div>
                    ))}
                  </div>

                  {statsData.history?.length > 0 && (
                    <div>
                      <p className="text-zinc-500 text-xs uppercase font-bold mb-2">По дням (последние 7)</p>
                      <div className="space-y-1.5">
                        {statsData.history.map((h: any) => {
                          const maxImp = Math.max(...statsData.history.map((x: any) => x.impressions), 1);
                          return (
                            <div key={h.date} className="flex items-center gap-3">
                              <span className="text-zinc-600 text-xs w-10 shrink-0">{h.date}</span>
                              <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
                                <div
                                  className="h-full bg-orange-500 rounded-full"
                                  style={{ width: `${(h.impressions / maxImp) * 100}%` }}
                                />
                              </div>
                              <span className="text-zinc-400 text-xs w-12 text-right shrink-0">{h.impressions}</span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Модалка пополнения кампании ────────────────────────────── */}
      {showTopup && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-[#111] border border-zinc-800 rounded-2xl w-full max-w-sm">
            <div className="flex items-center justify-between p-5 border-b border-zinc-800">
              <span className="text-white font-black uppercase text-sm tracking-widest">Пополнить кампанию</span>
              <button onClick={() => setShowTopup(null)}>
                <X size={18} className="text-zinc-500 hover:text-white" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <p className="text-zinc-400 text-sm">
                Кампания: <b className="text-white">{showTopup.title}</b>
              </p>
              <p className="text-zinc-500 text-xs">
                Баланс счёта: <b className="text-white">{fmt(adv.balance)} ₽</b>
              </p>
              <div>
                <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">Сумма пополнения (₽)</label>
                <input
                  type="number" min="1"
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 text-white text-sm focus:border-orange-500 focus:outline-none"
                  value={topupAmt} onChange={e => setTopupAmt(e.target.value)}
                />
                {topupAmt && showTopup.cost_per_impression > 0 && (
                  <p className="text-zinc-600 text-[10px] mt-1">
                    ≈ {Math.floor(parseFloat(topupAmt) / showTopup.cost_per_impression).toLocaleString()} дополнительных показов
                  </p>
                )}
              </div>
              <div className="flex gap-3">
                <button
                  onClick={handleTopup}
                  className="flex-1 py-3 bg-orange-500 hover:bg-orange-600 rounded-xl text-white font-black text-sm uppercase tracking-wider transition-colors"
                >
                  Пополнить
                </button>
                <button
                  onClick={() => setShowTopup(null)}
                  className="px-5 py-3 bg-zinc-800 hover:bg-zinc-700 rounded-xl text-zinc-300 text-sm font-bold transition-colors"
                >
                  Отмена
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdsPanel;
