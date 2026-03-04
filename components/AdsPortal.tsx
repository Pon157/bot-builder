import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Megaphone, BarChart2, Wallet, Plus, Clock, CheckCircle, XCircle,
  Play, Pause, LogOut, Loader2, AlertTriangle, ExternalLink,
  TrendingUp, Users, Bot, ChevronRight, RefreshCw, Eye, ArrowUpRight,
  CreditCard, FileText, Info, Zap
} from 'lucide-react';

const API = (path: string) => path;

const fmt    = (n: number | null | undefined) => new Intl.NumberFormat('ru-RU').format(n ?? 0);
const fmtRub = (n: number | null | undefined) => {
  const val = parseFloat(String(n ?? 0));
  return `${isNaN(val) ? '0.00' : val.toFixed(2)} ₽`;
};
const fmtDate = (ms: number) =>
  ms ? new Date(ms).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';

type Tab = 'dashboard' | 'posts' | 'balance' | 'create' | 'stats';

const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const map: Record<string, { label: string; cls: string }> = {
    pending:  { label: 'На модерации', cls: 'bg-amber-500/10 text-amber-400 border-amber-500/20' },
    approved: { label: 'Одобрено',     cls: 'bg-blue-500/10 text-blue-400 border-blue-500/20'   },
    active:   { label: 'Активно',      cls: 'bg-green-500/10 text-green-400 border-green-500/20' },
    paused:   { label: 'Пауза',        cls: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20'    },
    rejected: { label: 'Отклонено',    cls: 'bg-red-500/10 text-red-400 border-red-500/20'       },
    finished: { label: 'Завершено',    cls: 'bg-zinc-800 text-zinc-500 border-zinc-700'          },
  };
  const { label, cls } = map[status] || { label: status, cls: 'bg-zinc-800 text-zinc-500 border-zinc-700' };
  return <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-widest border ${cls}`}>{label}</span>;
};

const MetricCard: React.FC<{
  label: string; value: string | number; icon: React.ReactNode; color: string; sub?: string;
}> = ({ label, value, icon, color, sub }) => (
  <div className="p-4 bg-zinc-900/60 border border-zinc-800 rounded-2xl">
    <div className={`mb-2 ${color}`}>{icon}</div>
    <div className="text-xl font-black text-white font-mono">{value}</div>
    <div className="text-[10px] text-zinc-500 uppercase tracking-widest mt-0.5">{label}</div>
    {sub && <div className="text-[10px] text-zinc-600 mt-1">{sub}</div>}
  </div>
);

// ── Числовой инпут без бага "нельзя удалить первую цифру" ────────────────────
// Проблема: value={Math.max(1, parseInt(e.target.value) || 1)} применяет min сразу,
// что не даёт очистить поле перед вводом нового числа.
// Решение: храним строковое значение в state, конвертируем только при blur/confirm.
const NumericInput: React.FC<{
  value: number;
  onChange: (n: number) => void;
  min?: number;
  max?: number;
  className?: string;
}> = ({ value, onChange, min = 1, max, className = '' }) => {
  const [raw, setRaw] = useState(String(value));

  // Синхронизируем если value изменился снаружи (напр. кнопка быстрого выбора)
  useEffect(() => { setRaw(String(value)); }, [value]);

  const commit = (str: string) => {
    const n = parseInt(str, 10);
    if (!isNaN(n)) {
      const clamped = max !== undefined ? Math.max(min, Math.min(max, n)) : Math.max(min, n);
      onChange(clamped);
      setRaw(String(clamped));
    } else {
      setRaw(String(value)); // откат к последнему валидному
    }
  };

  return (
    <input
      type="text"
      inputMode="numeric"
      pattern="[0-9]*"
      enterKeyHint="done"
      value={raw}
      className={className}
      onChange={e => setRaw(e.target.value.replace(/[^0-9]/g, ''))}
      onBlur={e => commit(e.target.value)}
      onKeyDown={e => { if (e.key === 'Enter') { e.currentTarget.blur(); } }}
    />
  );
};

const AdsPortal: React.FC = () => {
  const navigate = useNavigate();

  const [tab,     setTab]     = useState<Tab>('dashboard');
  const [token,   setToken]   = useState<string | null>(null);
  const [agent,   setAgent]   = useState<any>(null);
  const [data,    setData]    = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState('');

  const [postText,   setPostText]   = useState('');
  const [postMedia,  setPostMedia]  = useState('');
  const [creating,   setCreating]   = useState(false);
  const [createMsg,  setCreateMsg]  = useState('');
  const [createErr,  setCreateErr]  = useState('');

  const [buyingPost, setBuyingPost] = useState<any>(null);
  const [buyCount,   setBuyCount]   = useState(100);
  const [buying,     setBuying]     = useState(false);
  const [buyMsg,     setBuyMsg]     = useState('');

  const [topupAmount, setTopupAmount] = useState(500);

  useEffect(() => {
    const t = localStorage.getItem('ads_agent_token');
    const a = localStorage.getItem('ads_agent');
    if (!t) { navigate('/adsauth'); return; }
    setToken(t);
    if (a) {
      try {
        const cached = JSON.parse(a);
        if (cached && cached.id) setAgent(cached);
      } catch {}
    }
    loadDashboard(t);
  }, []);

  const authHeader = (t: string) => ({ Authorization: `Bearer ${t}`, 'Content-Type': 'application/json' });

  const loadDashboard = async (t: string) => {
    setLoading(true); setError('');
    try {
      const r = await fetch('/api/ads/dashboard', { headers: authHeader(t) });
      if (r.status === 401) {
        localStorage.removeItem('ads_agent_token');
        localStorage.removeItem('ads_agent');
        navigate('/adsauth');
        return;
      }
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || `Ошибка сервера: ${r.status}`);
      }
      const d = await r.json();
      setData(d);
      if (d.agent) {
        setAgent(d.agent);
        localStorage.setItem('ads_agent', JSON.stringify({ ...d.agent, password_hash: undefined }));
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('ads_agent_token');
    localStorage.removeItem('ads_agent');
    navigate('/adsauth');
  };

  const handleCreatePost = async () => {
    if (!token || !postText.trim()) return;
    setCreating(true); setCreateErr(''); setCreateMsg('');
    try {
      const r = await fetch('/api/ads/posts/create', {
        method: 'POST',
        headers: authHeader(token),
        body: JSON.stringify({ text: postText.trim(), media_url: postMedia.trim() || undefined }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Ошибка');
      setCreateMsg('✅ Пост создан и отправлен на модерацию!');
      setPostText(''); setPostMedia('');
      await loadDashboard(token);
    } catch (e: any) {
      setCreateErr(e.message);
    } finally {
      setCreating(false);
    }
  };

  const handleBuyImpressions = async () => {
    if (!token || !buyingPost) return;
    setBuying(true); setBuyMsg('');
    try {
      const r = await fetch(`/api/ads/posts/${buyingPost.id}/buy-impressions`, {
        method: 'POST',
        headers: authHeader(token),
        body: JSON.stringify({ impressions: buyCount }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || 'Ошибка покупки показов');
      await loadDashboard(token);
      setBuyMsg(`✅ Куплено ${fmt(buyCount)} показов!`);
      setTimeout(() => { setBuyingPost(null); setBuyMsg(''); }, 3000);
    } catch (e: any) {
      setBuyMsg(`❌ ${e.message}`);
    } finally {
      setBuying(false);
    }
  };

  const getTopupUrl = async () => {
    if (!token) return;
    try {
      const r = await fetch('/api/ads/payments/create', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount: topupAmount }),
      });
      const d = await r.json();
      if (d.confirmation_url) {
        window.open(d.confirmation_url, '_blank');
      } else {
        alert(d.detail || 'Ошибка создания платежа');
      }
    } catch {}
  };

  if (loading) return (
    <div className="min-h-screen bg-[#060608] flex items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <Loader2 size={28} className="animate-spin text-amber-500" />
        <span className="text-zinc-600 text-xs font-bold uppercase tracking-widest">Загрузка...</span>
      </div>
    </div>
  );

  const posts  = data?.posts || [];
  const txs    = data?.transactions || [];
  const stats  = data?.stats || {};
  const sysSt  = data?.system_stats || {};
  const balance = parseFloat(String(agent?.balance_rub ?? data?.agent?.balance_rub ?? 0)) || 0;
  const PRICE_PER_IMP = 0.2;

  return (
    <div className="min-h-screen bg-[#060608] text-white"
      style={{ backgroundImage: 'radial-gradient(ellipse 80% 30% at 50% 0%, rgba(234,179,8,0.05), transparent)' }}>
      <div className="max-w-4xl mx-auto px-4 py-6">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-gradient-to-br from-amber-500 to-orange-600 rounded-xl flex items-center justify-center">
              <Megaphone size={17} className="text-white" />
            </div>
            <div>
              <h1 className="text-base font-black text-white">BotEngine Ads</h1>
              <div className="text-[10px] text-zinc-600 font-mono truncate max-w-[160px]">{agent?.email}</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="px-3 py-1.5 bg-amber-500/10 border border-amber-500/20 rounded-xl">
              <span className="text-amber-400 font-black text-sm">{fmtRub(balance)}</span>
            </div>
            <button onClick={handleLogout}
              className="p-2 bg-zinc-900 border border-zinc-800 rounded-xl hover:bg-zinc-800 transition-colors text-zinc-500 hover:text-white">
              <LogOut size={15} />
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 p-1 bg-zinc-900/80 border border-zinc-800 rounded-2xl mb-6 overflow-x-auto no-scrollbar">
          {([
            { id: 'dashboard', icon: <BarChart2 size={13} />, label: 'Обзор'      },
            { id: 'posts',     icon: <FileText size={13} />,  label: 'Посты'      },
            { id: 'create',    icon: <Plus size={13} />,      label: 'Создать'    },
            { id: 'balance',   icon: <Wallet size={13} />,    label: 'Баланс'     },
            { id: 'stats',     icon: <TrendingUp size={13} />,label: 'Статистика' },
          ] as { id: Tab; icon: React.ReactNode; label: string }[]).map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-[11px] font-bold whitespace-nowrap transition-all
                ${tab === t.id ? 'bg-amber-500 text-black' : 'text-zinc-500 hover:text-zinc-300'}`}>
              {t.icon} {t.label}
            </button>
          ))}
        </div>

        {/* ── DASHBOARD ─────────────────────────────────────────────────── */}
        {tab === 'dashboard' && (
          <div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
              <MetricCard label="Активных постов" value={stats.active_posts || 0}   icon={<Zap size={16} />}   color="text-green-400" />
              <MetricCard label="Всего показов"   value={fmt(stats.total_impressions || 0)} icon={<Eye size={16} />} color="text-blue-400" />
              <MetricCard label="Free-ботов" value={sysSt.free_bots || 0} icon={<Bot size={16} />} color="text-amber-400"
                sub={`${sysSt.running_bots || 0} запущено`} />
              <MetricCard label="Аудитория" value={fmt(sysSt.free_users || 0)} icon={<Users size={16} />} color="text-purple-400"
                sub="пользователей ботов" />
            </div>

            <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-5 mb-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xs font-black text-zinc-300 uppercase tracking-widest">Последние посты</h2>
                <button onClick={() => setTab('posts')}
                  className="text-[10px] text-amber-400 hover:text-amber-300 font-bold uppercase tracking-widest transition-colors flex items-center gap-1">
                  Все <ChevronRight size={12} />
                </button>
              </div>
              {posts.length === 0 ? (
                <div className="text-center py-6 text-zinc-600 text-xs">
                  Постов нет. <button onClick={() => setTab('create')} className="text-amber-400 hover:underline">Создать первый</button>
                </div>
              ) : (
                <div className="space-y-2">
                  {posts.slice(0, 5).map((p: any) => (
                    <div key={p.id} className="flex items-center gap-3 p-3 bg-zinc-800/40 rounded-xl">
                      <div className="flex-1 min-w-0">
                        <div className="text-xs text-white truncate">{p.text}</div>
                        <div className="flex items-center gap-2 mt-1">
                          <StatusBadge status={p.status} />
                          <span className="text-[10px] text-zinc-600">{fmtDate(p.created_at)}</span>
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <div className="text-xs font-bold text-white font-mono">
                          {fmt(p.impressions_used)}/{fmt(p.impressions_paid)}
                        </div>
                        <div className="text-[10px] text-zinc-600">показов</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <button onClick={() => setTab('create')}
                className="p-4 bg-amber-500/10 border border-amber-500/20 hover:border-amber-500/40 rounded-2xl text-left transition-colors">
                <Plus size={18} className="text-amber-400 mb-2" />
                <div className="text-xs font-black text-amber-300 uppercase tracking-widest">Создать пост</div>
                <div className="text-[10px] text-zinc-500 mt-0.5">Новая рекламная кампания</div>
              </button>
              <button onClick={() => setTab('balance')}
                className="p-4 bg-zinc-900/60 border border-zinc-800 hover:border-zinc-700 rounded-2xl text-left transition-colors">
                <Wallet size={18} className="text-green-400 mb-2" />
                <div className="text-xs font-black text-zinc-300 uppercase tracking-widest">Пополнить</div>
                <div className="text-[10px] text-zinc-500 mt-0.5">Через ЮМани</div>
              </button>
            </div>
          </div>
        )}

        {/* ── POSTS ─────────────────────────────────────────────────────── */}
        {tab === 'posts' && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-black text-zinc-300 uppercase tracking-widest">Рекламные посты</h2>
              <button onClick={() => token && loadDashboard(token)}
                className="p-2 bg-zinc-900 border border-zinc-800 rounded-xl hover:bg-zinc-800 transition-colors text-zinc-500">
                <RefreshCw size={14} />
              </button>
            </div>

            {posts.length === 0 ? (
              <div className="text-center py-16 bg-zinc-900/40 border border-zinc-800 rounded-2xl">
                <FileText size={32} className="text-zinc-700 mx-auto mb-3" />
                <p className="text-zinc-500 text-sm mb-4">Постов нет</p>
                <button onClick={() => setTab('create')}
                  className="px-5 py-2 bg-amber-500 hover:bg-amber-400 rounded-xl text-xs font-black text-black uppercase tracking-widest transition-colors">
                  Создать пост
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                {posts.map((p: any) => {
                  const pct       = (p.impressions_paid || 0) > 0 ? Math.round((p.impressions_used || 0) / p.impressions_paid * 100) : 0;
                  const remaining = (p.impressions_paid || 0) - (p.impressions_used || 0);
                  return (
                    <div key={p.id} className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-4">
                      <div className="flex items-start justify-between gap-3 mb-3">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-white leading-snug">{p.text}</p>
                          {p.reject_reason && (
                            <div className="mt-1 text-xs text-red-400 flex items-start gap-1">
                              <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                              {p.reject_reason}
                            </div>
                          )}
                        </div>
                        <StatusBadge status={p.status} />
                      </div>

                      {p.impressions_paid > 0 && (
                        <div className="mb-3">
                          <div className="flex justify-between text-[10px] text-zinc-500 mb-1">
                            <span>{fmt(p.impressions_used)} показов использовано</span>
                            <span>{fmt(p.impressions_paid)} куплено ({pct}%)</span>
                          </div>
                          <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                            <div className="h-full bg-gradient-to-r from-amber-500 to-orange-500 rounded-full transition-all"
                              style={{ width: `${pct}%` }} />
                          </div>
                        </div>
                      )}

                      <div className="flex items-center justify-between">
                        <span className="text-[10px] text-zinc-600">{fmtDate(p.created_at)}</span>
                        <div className="flex gap-2">
                          {p.status === 'approved' && (
                            <button onClick={() => { setBuyingPost(p); setBuyCount(100); setBuyMsg(''); }}
                              className="px-3 py-1.5 bg-amber-500 hover:bg-amber-400 rounded-xl text-[11px] font-black text-black uppercase tracking-widest transition-colors">
                              Купить показы
                            </button>
                          )}
                          {p.status === 'active' && remaining > 0 && (
                            <button onClick={() => { setBuyingPost(p); setBuyCount(100); setBuyMsg(''); }}
                              className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-xl text-[11px] font-bold transition-colors flex items-center gap-1">
                              <Plus size={11} /> Ещё показы
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Buy Impressions Modal */}
            {buyingPost && (
              <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 z-50">
                <div className="w-full max-w-sm bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
                  <h3 className="font-black text-white mb-1 text-sm">Купить показы</h3>
                  <p className="text-zinc-500 text-xs mb-4 truncate">{buyingPost.text}</p>

                  <div className="mb-4">
                    <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5">
                      Количество показов
                    </label>
                    {/* БАГ-ФИХ: используем NumericInput вместо type="number" с Math.max,
                        чтобы можно было очистить поле и ввести новое число целиком */}
                    <NumericInput
                      value={buyCount}
                      onChange={setBuyCount}
                      min={1}
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500 font-mono"
                    />
                    <div className="flex justify-between mt-2 text-xs">
                      <span className="text-zinc-500">Стоимость:</span>
                      <span className="font-bold text-amber-400">{fmtRub(buyCount * PRICE_PER_IMP)}</span>
                    </div>
                    <div className="flex justify-between text-xs mt-1">
                      <span className="text-zinc-500">Ваш баланс:</span>
                      <span className={`font-bold ${balance < buyCount * PRICE_PER_IMP ? 'text-red-400' : 'text-green-400'}`}>
                        {fmtRub(balance)}
                      </span>
                    </div>
                  </div>

                  <div className="flex gap-2 mb-4">
                    {[100, 500, 1000, 5000].map(n => (
                      <button key={n} onClick={() => setBuyCount(n)}
                        className={`flex-1 py-1.5 rounded-xl text-[11px] font-bold transition-colors
                          ${buyCount === n ? 'bg-amber-500 text-black' : 'bg-zinc-800 text-zinc-400 hover:text-white'}`}>
                        {fmt(n)}
                      </button>
                    ))}
                  </div>

                  {buyMsg && (
                    <div className={`mb-3 p-3 rounded-xl text-xs flex items-start gap-2
                      ${buyMsg.startsWith('✅') ? 'bg-green-500/10 border border-green-500/20 text-green-400' : 'bg-red-500/10 border border-red-500/20 text-red-400'}`}>
                      {buyMsg}
                    </div>
                  )}

                  <div className="flex gap-2">
                    <button onClick={() => setBuyingPost(null)}
                      className="flex-1 py-2.5 bg-zinc-800 hover:bg-zinc-700 rounded-xl text-xs font-bold transition-colors">
                      Отмена
                    </button>
                    <button onClick={handleBuyImpressions} disabled={buying || balance < buyCount * PRICE_PER_IMP}
                      className="flex-1 py-2.5 bg-amber-500 hover:bg-amber-400 disabled:bg-zinc-800 disabled:text-zinc-600 rounded-xl text-xs font-black text-black transition-colors flex items-center justify-center gap-2">
                      {buying && <Loader2 size={13} className="animate-spin" />}
                      {buying ? 'Покупка...' : 'Купить'}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── CREATE ────────────────────────────────────────────────────── */}
        {tab === 'create' && (
          <div>
            <h2 className="text-sm font-black text-zinc-300 uppercase tracking-widest mb-5">Новый рекламный пост</h2>
            <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-5">
              <div className="space-y-4">
                <div>
                  <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5">
                    Текст рекламы <span className="text-zinc-600">({postText.length}/250)</span>
                  </label>
                  <textarea
                    value={postText}
                    onChange={e => setPostText(e.target.value.slice(0, 250))}
                    rows={4}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500 resize-none"
                    placeholder="Краткое и привлекательное объявление. Будет показано в Telegram-ботах."
                  />
                </div>
                <div>
                  <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5">
                    URL изображения <span className="text-zinc-600">(опционально)</span>
                  </label>
                  <input
                    value={postMedia}
                    onChange={e => setPostMedia(e.target.value)}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500"
                    placeholder="https://example.com/banner.jpg"
                  />
                </div>

                {postText && (
                  <div className="p-3 bg-zinc-800/60 border border-zinc-700 rounded-xl">
                    <div className="text-[10px] text-zinc-500 uppercase tracking-widest mb-2 flex items-center gap-1">
                      <Eye size={11} /> Предпросмотр в боте:
                    </div>
                    <div className="text-xs text-white leading-relaxed">
                      <div className="text-zinc-500 text-[10px] mb-1">─────────────────</div>
                      <div className="text-amber-400 font-bold text-[11px] mb-1">📢 Реклама</div>
                      <div>{postText}</div>
                      <div className="text-zinc-500 text-[10px] mt-1">─────────────────</div>
                    </div>
                  </div>
                )}

                <div className="flex items-start gap-2 p-3 bg-blue-500/5 border border-blue-500/10 rounded-xl">
                  <Info size={14} className="text-blue-400 shrink-0 mt-0.5" />
                  <p className="text-xs text-zinc-500">
                    Пост будет отправлен на модерацию. После одобрения вы сможете купить показы и запустить кампанию.
                    Стоимость: <b className="text-amber-400">0.2 ₽ / показ</b>.
                  </p>
                </div>

                {createErr && (
                  <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-xs">
                    <AlertTriangle size={13} /> {createErr}
                  </div>
                )}
                {createMsg && (
                  <div className="p-3 bg-green-500/10 border border-green-500/20 rounded-xl text-green-400 text-xs">
                    {createMsg}
                  </div>
                )}

                <button onClick={handleCreatePost} disabled={creating || !postText.trim()}
                  className="w-full py-3 bg-amber-500 hover:bg-amber-400 disabled:bg-zinc-800 disabled:text-zinc-600 rounded-xl text-sm font-black text-black transition-colors flex items-center justify-center gap-2">
                  {creating && <Loader2 size={15} className="animate-spin" />}
                  {creating ? 'Отправка...' : 'Отправить на модерацию'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── BALANCE ───────────────────────────────────────────────────── */}
        {tab === 'balance' && (
          <div>
            <h2 className="text-sm font-black text-zinc-300 uppercase tracking-widest mb-5">Баланс</h2>

            <div className="bg-gradient-to-br from-amber-500/10 to-orange-500/5 border border-amber-500/20 rounded-2xl p-6 mb-5 text-center">
              <div className="text-[10px] text-amber-500/60 uppercase tracking-widest mb-1">Текущий баланс</div>
              <div className="text-4xl font-black text-amber-400 font-mono">{fmtRub(balance)}</div>
              <div className="text-[11px] text-zinc-500 mt-2">
                Хватит на ≈{Math.floor(balance / 0.2)} показов
              </div>
            </div>

            <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-5 mb-4">
              <h3 className="text-xs font-black text-zinc-300 uppercase tracking-widest mb-4 flex items-center gap-2">
                <CreditCard size={14} /> Пополнить через ЮМани
              </h3>
              <div className="mb-3">
                <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1.5">Сумма пополнения (₽)</label>
                {/* БАГ-ФИХ: NumericInput для topupAmount */}
                <NumericInput
                  value={topupAmount}
                  onChange={setTopupAmount}
                  min={10}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500 font-mono"
                />
                <div className="text-[10px] text-zinc-600 mt-1">≈{Math.floor(topupAmount / 0.2)} показов</div>
              </div>
              <div className="flex gap-2 mb-4">
                {[100, 300, 500, 1000].map(a => (
                  <button key={a} onClick={() => setTopupAmount(a)}
                    className={`flex-1 py-1.5 rounded-xl text-[11px] font-bold transition-colors
                      ${topupAmount === a ? 'bg-amber-500 text-black' : 'bg-zinc-800 text-zinc-400 hover:text-white'}`}>
                    {a} ₽
                  </button>
                ))}
              </div>
              <button onClick={getTopupUrl}
                className="w-full py-3 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 rounded-xl text-sm font-black text-black flex items-center justify-center gap-2 transition-all">
                <ArrowUpRight size={15} /> Перейти к оплате
              </button>
              <p className="text-[10px] text-zinc-600 text-center mt-2">После оплаты баланс пополнится автоматически</p>
            </div>

            <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-5">
              <h3 className="text-xs font-black text-zinc-300 uppercase tracking-widest mb-4">История транзакций</h3>
              {txs.length === 0 ? (
                <div className="text-center py-4 text-zinc-600 text-xs">Транзакций нет</div>
              ) : (
                <div className="space-y-2">
                  {txs.map((tx: any) => (
                    <div key={tx.id} className="flex items-center justify-between p-3 bg-zinc-800/40 rounded-xl">
                      <div>
                        <div className="text-xs text-white">{tx.description || tx.type}</div>
                        <div className="text-[10px] text-zinc-600">{fmtDate(tx.created_at)}</div>
                      </div>
                      <div className={`text-sm font-black font-mono ${parseFloat(tx.amount) > 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {parseFloat(tx.amount) > 0 ? '+' : ''}{fmtRub(parseFloat(tx.amount))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── STATISTICS ────────────────────────────────────────────────── */}
        {tab === 'stats' && (
          <div>
            <h2 className="text-sm font-black text-zinc-300 uppercase tracking-widest mb-5">Статистика показов</h2>
            <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-5 mb-4">
              <h3 className="text-xs font-black text-zinc-400 uppercase tracking-widest mb-4">Охват аудитории</h3>
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 bg-zinc-800/50 rounded-xl">
                  <div className="text-lg font-black text-amber-400 font-mono">{fmt(sysSt.free_bots || 0)}</div>
                  <div className="text-[10px] text-zinc-500 mt-0.5">Всего free-ботов</div>
                  <div className="text-[10px] text-green-500 mt-0.5">{sysSt.running_bots || 0} запущено</div>
                </div>
                <div className="p-3 bg-zinc-800/50 rounded-xl">
                  <div className="text-lg font-black text-blue-400 font-mono">{fmt(sysSt.free_users || 0)}</div>
                  <div className="text-[10px] text-zinc-500 mt-0.5">Польз. всех ботов</div>
                </div>
              </div>
            </div>

            <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-5">
              <h3 className="text-xs font-black text-zinc-400 uppercase tracking-widest mb-4">По постам</h3>
              {posts.length === 0 ? (
                <div className="text-center py-4 text-zinc-600 text-xs">Постов нет</div>
              ) : (
                <div className="space-y-3">
                  {posts.map((p: any) => {
                    const ctr   = (p.impressions_paid || 0) > 0 ? ((p.impressions_used || 0) / p.impressions_paid * 100).toFixed(1) : '0';
                    const spent = ((p.impressions_used || 0) * 0.2).toFixed(2);
                    return (
                      <div key={p.id} className="p-3 bg-zinc-800/40 rounded-xl">
                        <div className="text-xs text-white truncate mb-2">{p.text}</div>
                        <div className="grid grid-cols-3 gap-2">
                          <div>
                            <div className="text-sm font-black text-white font-mono">{fmt(p.impressions_used)}</div>
                            <div className="text-[10px] text-zinc-600">Показов</div>
                          </div>
                          <div>
                            <div className="text-sm font-black text-white font-mono">{ctr}%</div>
                            <div className="text-[10px] text-zinc-600">Прогресс</div>
                          </div>
                          <div>
                            <div className="text-sm font-black text-amber-400 font-mono">{spent} ₽</div>
                            <div className="text-[10px] text-zinc-600">Потрачено</div>
                          </div>
                        </div>
                        <div className="mt-2 h-1.5 bg-zinc-700 rounded-full overflow-hidden">
                          <div className="h-full bg-gradient-to-r from-amber-500 to-orange-500 rounded-full"
                            style={{ width: `${p.impressions_paid > 0 ? p.impressions_used / p.impressions_paid * 100 : 0}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AdsPortal;
