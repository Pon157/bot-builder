import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { User, BotConfig } from '../types';
import { api } from '../services/apiService';
import {
  Bot as BotIcon, RefreshCw, FileText,
  ExternalLink, Megaphone, MessageCircle, LifeBuoy, Brain,
  AppWindow, Wallet, Plus, Clock, CheckCircle, XCircle,
  CreditCard, ChevronRight, Zap, ShieldCheck
} from 'lucide-react';

interface ProfileProps {
  user: User;
  bots: BotConfig[];
  onUpdateBots: (bots: BotConfig[]) => void;
}

type Section = 'wallet' | 'license' | 'ai' | 'miniapps';

interface Transaction {
  id: string;
  type: 'topup' | 'spend';
  amount: number;
  balance_after: number;
  description: string;
  service?: string;
  status: 'pending' | 'completed' | 'failed';
  created_at: number;
}

interface ServicePrice {
  service_key: string;
  label: string;
  price_rub: number;
  meta: Record<string, any>;
}

const GITHUB_RAW_URL = "https://raw.githubusercontent.com/Pon157/bot-builder/main";

const Profile: React.FC<ProfileProps> = ({ user, bots, onUpdateBots }) => {
  const [activeSection, setActiveSection] = useState<Section>('wallet');
  const [isSyncing, setIsSyncing]         = useState(false);

  // ── Кошелёк ──────────────────────────────────────────────────────────────
  const [balance, setBalance]           = useState<number>(0);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [topupAmount, setTopupAmount]   = useState('');
  const [isPolling, setIsPolling]           = useState(false);
  const [isInitiating, setIsInitiating]     = useState(false);
  const [prices, setPrices]             = useState<ServicePrice[]>([]);

  // ── Покупка услуги ────────────────────────────────────────────────────────
  const [buyBotId, setBuyBotId]         = useState('');
  const [isBuying, setIsBuying]         = useState<string | null>(null); // service_key

  // ── AI-балансы ────────────────────────────────────────────────────────────
  const [aiBalances, setAiBalances]     = useState<Record<string, number>>({});

  // ── Мини-апп лицензии ────────────────────────────────────────────────────
  const [miniappLicenses, setMiniappLicenses] = useState<Record<string, { active: boolean; expires_at: number }>>({});

  // ── Загрузка данных ───────────────────────────────────────────────────────
  const loadWallet = useCallback(async () => {
    try {
      const r = await fetch(`/api/payments/balance/${user.id}`);
      const d = await r.json();
      setBalance(d.balance ?? 0);
      setTransactions(d.transactions ?? []);
    } catch { /* тихо */ }
  }, [user.id]);

  const loadPrices = useCallback(async () => {
    try {
      const r = await fetch('/api/payments/prices');
      setPrices(await r.json());
    } catch { /* тихо */ }
  }, []);

  // Polling баланса после редиректа с ЮKassa — webhook может прийти с задержкой
  const pollBalanceAfterPayment = useCallback(async (prevBalance: number) => {
    setIsPolling(true);
    const MAX_ATTEMPTS = 10;
    const INTERVAL_MS  = 3000;
    for (let i = 0; i < MAX_ATTEMPTS; i++) {
      await new Promise(res => setTimeout(res, INTERVAL_MS));
      try {
        const r = await fetch(`/api/payments/balance/${user.id}`);
        const d = await r.json();
        if (d.balance > prevBalance) {
          setBalance(d.balance);
          setTransactions(d.transactions ?? []);
          setIsPolling(false);
          return;
        }
      } catch { /* тихо */ }
    }
    setIsPolling(false);
    loadWallet();
  }, [loadWallet, user.id]);

  useEffect(() => {
    loadWallet();
    loadPrices();
    // Проверяем успешный редирект с ЮKassa
    const params = new URLSearchParams(window.location.search);
    if (params.get('payment') === 'success') {
      window.history.replaceState({}, '', '/profile');
      // Сначала грузим текущий баланс, потом запускаем polling
      fetch(`/api/payments/balance/${user.id}`)
        .then(r => r.json())
        .then(d => {
          setBalance(d.balance ?? 0);
          setTransactions(d.transactions ?? []);
          pollBalanceAfterPayment(d.balance ?? 0);
        })
        .catch(() => {});
    }
    bots.forEach(bot => {
      fetch(`/api/ai/balance/${bot.id}`)
        .then(r => r.json())
        .then(d => setAiBalances(prev => ({ ...prev, [bot.id]: d.tokens_balance || 0 })))
        .catch(() => {});
      fetch(`/api/miniapps/license/${bot.id}`)
        .then(r => r.json())
        .then(d => setMiniappLicenses(prev => ({ ...prev, [bot.id]: d })))
        .catch(() => {});
    });
  }, [loadWallet, loadPrices, pollBalanceAfterPayment, bots, user.id]);

  const refreshData = async () => {
    setIsSyncing(true);
    try {
      const serverBots = await api.getBots(user.id);
      onUpdateBots(serverBots);
      await loadWallet();
    } catch (e) { console.error('Refresh failed', e); }
    finally { setIsSyncing(false); }
  };

  // ── Пополнить баланс ──────────────────────────────────────────────────────
  const handleTopup = async () => {
    const amount = parseFloat(topupAmount);
    if (!amount || amount < 10) {
      alert('Минимальная сумма — 10 ₽');
      return;
    }
    setIsInitiating(true);
    try {
      const r = await fetch('/api/payments/initiate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: user.id, amount })
      });
      const d = await r.json();
      if (d.payment_url) {
        setTopupAmount('');
        // Прямой переход — window.open после await блокируется браузером как popup
        window.location.href = d.payment_url;
      } else {
        alert('Ошибка создания платежа: ' + (d.detail || 'неизвестная ошибка'));
      }
    } catch { alert('Ошибка сети'); }
    finally { setIsInitiating(false); }
  };

  // ── Купить услугу ─────────────────────────────────────────────────────────
  const handleBuy = async (serviceKey: string) => {
    if (!buyBotId) {
      alert('Выберите бота');
      return;
    }
    const price = prices.find(p => p.service_key === serviceKey);
    if (!price) return;
    if (balance < price.price_rub) {
      alert(`Недостаточно средств. Нужно ${price.price_rub} ₽, у вас ${balance.toFixed(2)} ₽`);
      return;
    }
    if (!window.confirm(`Списать ${price.price_rub} ₽ за «${price.label}»?`)) return;

    setIsBuying(serviceKey);
    try {
      const r = await fetch('/api/payments/buy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: user.id, service_key: serviceKey, target_id: buyBotId })
      });
      const d = await r.json();
      if (d.status === 'ok') {
        setBalance(d.new_balance);
        await loadWallet();
        // Обновляем AI-баланс если нужно
        if (serviceKey.startsWith('ai_')) {
          const ab = await fetch(`/api/ai/balance/${buyBotId}`).then(r => r.json());
          setAiBalances(prev => ({ ...prev, [buyBotId]: ab.tokens_balance || 0 }));
        }
        // Обновляем список ботов
        const serverBots = await api.getBots(user.id);
        onUpdateBots(serverBots);
        alert(d.message);
      } else {
        alert('Ошибка: ' + (d.detail || d.message || 'Недостаточно средств'));
      }
    } catch { alert('Ошибка сети'); }
    finally { setIsBuying(null); }
  };

  // ── Хелперы ───────────────────────────────────────────────────────────────
  const formatDate = (ts: number) =>
    new Date(ts).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });

  const pricesByGroup = {
    bot:     prices.filter(p => p.service_key.startsWith('bot_')),
    ai:      prices.filter(p => p.service_key.startsWith('ai_')),
    miniapp: prices.filter(p => p.service_key.startsWith('miniapp_')),
  };

  const licenseStatus = (bot: BotConfig) => {
    const exp = (bot as any).license_expires_at;
    if (!exp) return { text: 'Нет лицензии', color: 'text-red-400' };
    const now = Date.now();
    if (exp < now) return { text: 'Истекла', color: 'text-red-400' };
    const days = Math.floor((exp - now) / 86_400_000);
    if (days <= 3) return { text: `${days} д.`, color: 'text-yellow-400' };
    return { text: `${days} д.`, color: 'text-green-400' };
  };

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-8 md:space-y-12 animate-in fade-in duration-500 pb-10">

      {/* Шапка */}
      <header className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold mb-2 text-white">Профиль</h1>
          <p className="text-sm text-zinc-500">Баланс, лицензии и настройки</p>
        </div>
        <button onClick={refreshData} disabled={isSyncing}
          className="flex items-center gap-2 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-xl text-xs font-bold transition-all border border-zinc-700">
          <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? 'animate-spin' : ''}`} />
          Обновить
        </button>
      </header>

      {/* Балансовый виджет — всегда виден */}
      <div className="bg-gradient-to-br from-indigo-900/40 to-purple-900/20 border border-indigo-500/30 rounded-3xl p-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 bg-indigo-600 rounded-2xl flex items-center justify-center shadow-lg shadow-indigo-600/30">
            <Wallet className="w-6 h-6 text-white" />
          </div>
          <div>
            <p className="text-xs text-zinc-500 uppercase tracking-widest font-bold">Баланс</p>
            <p className="text-3xl font-black text-white">{balance.toFixed(2)} ₽</p>
          </div>
        </div>
        <button onClick={() => setActiveSection('wallet')}
          className="text-xs text-indigo-400 hover:text-indigo-300 font-bold flex items-center gap-1">
          Пополнить <ChevronRight className="w-3 h-3" />
        </button>
      </div>

      {/* Баннер «Оплата обрабатывается» — показывается пока polling активен */}
      {isPolling && (
        <div className="flex items-center gap-3 p-4 bg-yellow-950/30 border border-yellow-700/40 rounded-2xl animate-pulse">
          <RefreshCw className="w-4 h-4 text-yellow-400 animate-spin flex-shrink-0" />
          <div>
            <p className="text-sm font-bold text-yellow-300">Оплата обрабатывается...</p>
            <p className="text-[11px] text-yellow-700">Баланс обновится автоматически в течение нескольких секунд</p>
          </div>
        </div>
      )}

      {/* Переключатель раздела */}
      <div className="flex bg-black border border-zinc-800 rounded-2xl p-1 w-fit gap-1 flex-wrap">
        {([
          { id: 'wallet',   label: '💳 Кошелёк'     },
          { id: 'license',  label: '🔑 Лицензии'    },
          { id: 'ai',       label: '🤖 AI-токены'   },
          { id: 'miniapps', label: '📱 Мини-апп'    },
        ] as const).map(({ id, label }) => (
          <button key={id} onClick={() => setActiveSection(id)}
            className={`px-5 py-3 rounded-xl text-[11px] font-black uppercase tracking-wider transition-all ${
              activeSection === id ? 'bg-indigo-600 text-white shadow-lg' : 'text-zinc-500 hover:text-zinc-300'
            }`}>{label}</button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 md:gap-8">
        {/* ══════════════════════ ЛЕВАЯ КОЛОНКА ══════════════════════ */}
        <div className="lg:col-span-2 space-y-6 md:space-y-8">

          {/* ── КОШЕЛЁК ─────────────────────────────────────────────── */}
          {activeSection === 'wallet' && (<>

            {/* Пополнение */}
            <section className="bg-[#121212] border border-zinc-800 rounded-[2rem] p-6 md:p-8 shadow-2xl space-y-5">
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <CreditCard className="w-5 h-5 text-indigo-400" />
                Пополнить баланс
              </h3>
              <p className="text-xs text-zinc-500 leading-relaxed">
                Оплата через ЮKassa — банковской картой или кошельком ЮMoney.
                Средства поступают автоматически в течение нескольких секунд.
              </p>

              {/* Быстрые суммы */}
              <div className="grid grid-cols-4 gap-2">
                {[50, 100, 200, 500].map(v => (
                  <button key={v} onClick={() => setTopupAmount(String(v))}
                    className={`py-3 rounded-xl text-sm font-bold border transition-all ${
                      topupAmount === String(v)
                        ? 'bg-indigo-600 border-indigo-500 text-white'
                        : 'bg-black border-zinc-800 text-zinc-400 hover:border-zinc-600 hover:text-white'
                    }`}>
                    {v} ₽
                  </button>
                ))}
              </div>

              {/* Своя сумма */}
              <div className="flex gap-3">
                <input
                  type="number"
                  min={10}
                  max={100000}
                  placeholder="Другая сумма, ₽"
                  value={topupAmount}
                  onChange={e => setTopupAmount(e.target.value)}
                  className="flex-1 bg-black border border-zinc-800 rounded-xl p-4 text-sm text-white outline-none focus:border-indigo-500 transition-colors placeholder-zinc-700"
                />
                <button
                  onClick={handleTopup}
                  disabled={isInitiating || !topupAmount || parseFloat(topupAmount) < 10}
                  className="px-6 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white font-black rounded-xl transition-all flex items-center gap-2 text-sm shadow-lg shadow-indigo-600/20">
                  {isInitiating ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <><Plus className="w-4 h-4" />Оплатить</>
                  )}
                </button>
              </div>

              <div className="flex items-center gap-2 text-[10px] text-zinc-600">
                <ShieldCheck className="w-3 h-3 text-green-500 flex-shrink-0" />
                Минимум 10 ₽ · Оплата через ЮKassa · Безопасно
              </div>
            </section>

            {/* История */}
            <section className="bg-[#121212] border border-zinc-800 rounded-[2rem] p-6 md:p-8 shadow-2xl">
              <h3 className="text-lg font-bold text-white mb-5 flex items-center gap-2">
                <Clock className="w-5 h-5 text-zinc-500" />
                История транзакций
              </h3>
              {transactions.length === 0 ? (
                <p className="text-sm text-zinc-600 text-center py-8">Транзакций пока нет</p>
              ) : (
                <div className="space-y-2">
                  {transactions.map(tx => {
                    const isPendingTopup = tx.type === 'topup' && tx.status === 'pending';
                    const isCompleted    = tx.status === 'completed';
                    const isFailed       = tx.status === 'failed';

                    return (
                    <div key={tx.id}
                      className={`flex items-center justify-between p-4 border rounded-2xl transition-all ${
                        isPendingTopup
                          ? 'bg-yellow-950/20 border-yellow-800/30'
                          : isFailed
                          ? 'bg-red-950/10 border-red-900/20'
                          : 'bg-black border-zinc-800'
                      }`}>
                      <div className="flex items-center gap-3">
                        {isPendingTopup ? (
                          <Clock className="w-4 h-4 text-yellow-500 flex-shrink-0 animate-pulse" />
                        ) : isFailed ? (
                          <XCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
                        ) : tx.type === 'topup' ? (
                          <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0" />
                        ) : (
                          <Zap className="w-4 h-4 text-purple-400 flex-shrink-0" />
                        )}
                        <div>
                          <p className="text-xs font-bold text-white">{tx.description}</p>
                          <p className="text-[10px] text-zinc-600">
                            {formatDate(tx.created_at)}
                            {isPendingTopup && <span className="ml-2 text-yellow-600">· Ожидание оплаты...</span>}
                            {isFailed       && <span className="ml-2 text-red-600">· Отменено</span>}
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className={`text-sm font-black ${
                          isFailed       ? 'text-zinc-600 line-through' :
                          tx.type === 'topup' ? 'text-green-400' : 'text-red-400'
                        }`}>
                          {tx.type === 'topup' ? '+' : '−'}{Math.abs(tx.amount).toFixed(2)} ₽
                        </p>
                        {/* Показываем balance_after только если платёж уже завершён */}
                        {isCompleted && (
                          <p className="text-[10px] text-zinc-600">→ {tx.balance_after.toFixed(2)} ₽</p>
                        )}
                      </div>
                    </div>
                    );
                  })}
                </div>
              )}
            </section>
          </>)}

          {/* ── ЛИЦЕНЗИИ БОТОВ ───────────────────────────────────────── */}
          {activeSection === 'license' && (<>
            <section className="bg-[#121212] border border-zinc-800 rounded-[2rem] p-6 md:p-8 shadow-2xl space-y-5">
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <BotIcon className="w-5 h-5 text-blue-500" />
                Ваши боты
              </h3>

              {/* Список ботов */}
              <div className="space-y-2">
                {bots.map(bot => {
                  const lic = licenseStatus(bot);
                  return (
                    <div key={bot.id}
                      className="flex items-center justify-between p-4 bg-black border border-zinc-800 rounded-2xl">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 bg-zinc-900 rounded-xl flex items-center justify-center">
                          <BotIcon className="w-4 h-4 text-blue-400" />
                        </div>
                        <div>
                          <p className="text-sm font-bold text-white">{bot.name}</p>
                          <p className="text-[10px] text-zinc-600 uppercase">{bot.platform}</p>
                        </div>
                      </div>
                      <span className={`text-xs font-bold ${lic.color}`}>{lic.text}</span>
                    </div>
                  );
                })}
                {bots.length === 0 && (
                  <p className="text-sm text-zinc-600 text-center py-4">Ботов нет</p>
                )}
              </div>

              {/* Выбор бота и покупка */}
              <div className="border-t border-zinc-800 pt-5 space-y-4">
                <label className="block">
                  <span className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2 block">Выберите бота</span>
                  <select value={buyBotId} onChange={e => setBuyBotId(e.target.value)}
                    className="w-full bg-black border border-zinc-800 rounded-xl p-4 text-sm text-white outline-none focus:border-indigo-500">
                    <option value="">— Выберите —</option>
                    {bots.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                </label>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {pricesByGroup.bot.map(p => (
                    <button key={p.service_key}
                      onClick={() => handleBuy(p.service_key)}
                      disabled={isBuying === p.service_key || !buyBotId}
                      className="flex items-center justify-between p-4 bg-blue-600/10 border border-blue-500/20 hover:border-blue-500/50 rounded-2xl transition-all disabled:opacity-40 group">
                      <div className="text-left">
                        <p className="text-xs font-bold text-white group-hover:text-blue-300 transition-colors">{p.label}</p>
                        <p className="text-[10px] text-zinc-500">{p.meta?.days} дней</p>
                      </div>
                      <span className="text-sm font-black text-blue-400">{p.price_rub} ₽</span>
                    </button>
                  ))}
                </div>
              </div>
            </section>
          </>)}

          {/* ── AI-ТОКЕНЫ ─────────────────────────────────────────────── */}
          {activeSection === 'ai' && (<>
            <section className="bg-[#121212] border border-zinc-800 rounded-[2rem] p-6 md:p-8 shadow-2xl space-y-5">
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <Brain className="w-5 h-5 text-purple-500" />
                AI-токены
              </h3>

              {/* Балансы по ботам */}
              <div className="space-y-2">
                {bots.map(bot => (
                  <div key={bot.id}
                    className="flex items-center justify-between p-4 bg-black border border-zinc-800 rounded-2xl">
                    <span className="text-sm text-white">{bot.name}</span>
                    <span className="text-sm font-black text-purple-400">
                      {(aiBalances[bot.id] || 0).toLocaleString('ru-RU')} токенов
                    </span>
                  </div>
                ))}
              </div>

              {/* Покупка токенов */}
              <div className="border-t border-zinc-800 pt-5 space-y-4">
                <label className="block">
                  <span className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2 block">Для бота</span>
                  <select value={buyBotId} onChange={e => setBuyBotId(e.target.value)}
                    className="w-full bg-black border border-zinc-800 rounded-xl p-4 text-sm text-white outline-none focus:border-indigo-500">
                    <option value="">— Выберите —</option>
                    {bots.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                </label>

                <div className="grid grid-cols-1 gap-3">
                  {pricesByGroup.ai.map(p => (
                    <button key={p.service_key}
                      onClick={() => handleBuy(p.service_key)}
                      disabled={isBuying === p.service_key || !buyBotId}
                      className="flex items-center justify-between p-4 bg-purple-600/10 border border-purple-500/20 hover:border-purple-500/50 rounded-2xl transition-all disabled:opacity-40 group">
                      <div className="text-left">
                        <p className="text-xs font-bold text-white group-hover:text-purple-300 transition-colors">{p.label}</p>
                        <p className="text-[10px] text-zinc-500">≈ {(p.price_rub / (p.meta?.tokens || 1) * 1000).toFixed(3)} ₽ / 1k токенов</p>
                      </div>
                      <span className="text-sm font-black text-purple-400">{p.price_rub} ₽</span>
                    </button>
                  ))}
                </div>
              </div>
            </section>
          </>)}

          {/* ── МИНИ-АПП ─────────────────────────────────────────────── */}
          {activeSection === 'miniapps' && (<>
            <section className="bg-[#121212] border border-zinc-800 rounded-[2rem] p-6 md:p-8 shadow-2xl space-y-5">
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <AppWindow className="w-5 h-5 text-indigo-400" />
                Мини-приложения
              </h3>

              <div className="space-y-2">
                {bots.map(bot => {
                  const lic = miniappLicenses[bot.id];
                  const active = lic?.active;
                  const exp = lic?.expires_at;
                  return (
                    <div key={bot.id}
                      className="flex items-center justify-between p-4 bg-black border border-zinc-800 rounded-2xl">
                      <span className="text-sm text-white">{bot.name}</span>
                      <span className={`text-xs font-bold ${active ? 'text-green-400' : 'text-red-400'}`}>
                        {active && exp
                          ? `до ${new Date(exp).toLocaleDateString('ru-RU')}`
                          : 'Неактивно'}
                      </span>
                    </div>
                  );
                })}
              </div>

              <div className="border-t border-zinc-800 pt-5 space-y-4">
                <label className="block">
                  <span className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2 block">Для бота</span>
                  <select value={buyBotId} onChange={e => setBuyBotId(e.target.value)}
                    className="w-full bg-black border border-zinc-800 rounded-xl p-4 text-sm text-white outline-none focus:border-indigo-500">
                    <option value="">— Выберите —</option>
                    {bots.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                </label>

                <div className="grid grid-cols-1 gap-3">
                  {pricesByGroup.miniapp.map(p => (
                    <button key={p.service_key}
                      onClick={() => handleBuy(p.service_key)}
                      disabled={isBuying === p.service_key || !buyBotId}
                      className="flex items-center justify-between p-4 bg-indigo-600/10 border border-indigo-500/20 hover:border-indigo-500/50 rounded-2xl transition-all disabled:opacity-40 group">
                      <div className="text-left">
                        <p className="text-xs font-bold text-white group-hover:text-indigo-300 transition-colors">{p.label}</p>
                        <p className="text-[10px] text-zinc-500">Неограниченно приложений</p>
                      </div>
                      <span className="text-sm font-black text-indigo-400">{p.price_rub} ₽</span>
                    </button>
                  ))}
                </div>
              </div>
            </section>
          </>)}
        </div>

        {/* ══════════════════════ ПРАВАЯ КОЛОНКА ══════════════════════ */}
        <div className="space-y-6">

          {/* Инструкция пополнения */}
          {activeSection === 'wallet' && (
            <div className="bg-[#121212] border border-zinc-800 rounded-3xl p-6 space-y-4">
              <h4 className="text-xs font-bold text-zinc-500 uppercase tracking-widest">Как пополнить</h4>
              {[
                ['1', 'Укажите сумму и нажмите «Оплатить»'],
                ['2', 'Откроется форма ЮKassa — оплатите картой'],
                ['3', 'Баланс пополнится автоматически'],
              ].map(([n, t]) => (
                <div key={n} className="flex gap-3">
                  <span className="w-6 h-6 bg-indigo-600 rounded-full text-white text-[10px] font-black flex items-center justify-center flex-shrink-0">{n}</span>
                  <p className="text-xs text-zinc-400 leading-relaxed">{t}</p>
                </div>
              ))}
            </div>
          )}

          {/* Тех. поддержка */}
          <a href="https://t.me/DialogeEngineSupportBot" target="_blank" rel="noreferrer"
            className="flex items-center gap-4 p-5 bg-emerald-500/10 border border-emerald-500/20 rounded-3xl hover:bg-emerald-500/20 transition-all group">
            <div className="w-10 h-10 bg-emerald-500 rounded-2xl flex items-center justify-center shadow-lg shadow-emerald-500/20">
              <LifeBuoy className="w-5 h-5 text-white animate-pulse" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-white group-hover:text-emerald-400 transition-colors">Тех. поддержка</h4>
              <p className="text-[10px] text-zinc-500">Поможем с настройкой 24/7</p>
            </div>
          </a>

          {/* Канал */}
          <div className="bg-[#121212] border border-zinc-800 rounded-3xl p-6 flex flex-col items-center text-center">
            <div className="w-10 h-10 bg-zinc-800 rounded-full flex items-center justify-center mb-4">
              <MessageCircle className="w-5 h-5 text-sky-400" />
            </div>
            <h4 className="text-sm font-bold text-white mb-1 uppercase tracking-tight">Наше сообщество</h4>
            <p className="text-[11px] text-zinc-500 mb-4">Новости, обновления, промокоды.</p>
            <a href="https://t.me/dialogeengine" target="_blank" rel="noreferrer"
              className="w-full py-3 bg-zinc-800 hover:bg-zinc-700 text-sky-400 text-[11px] font-bold rounded-xl transition-colors flex items-center justify-center gap-2">
              Перейти в канал <ExternalLink className="w-3 h-3" />
            </a>
          </div>

          {/* Реклама */}
          <div className="bg-zinc-900/30 border border-zinc-800/50 rounded-3xl p-6">
            <div className="flex items-center gap-2 mb-4 opacity-50">
              <Megaphone className="w-3 h-3 text-zinc-400" />
              <span className="text-[9px] font-black uppercase tracking-[0.2em] text-zinc-400">Реклама</span>
            </div>
            <a href="https://t.me/NOVA_creators" target="_blank" rel="noreferrer" className="block group">
              <p className="text-xs font-bold text-zinc-200 group-hover:text-blue-400 transition-colors mb-1">NOVA CREATIVE STUDIO</p>
              <p className="text-[10px] text-zinc-500 leading-relaxed mb-3">Крутые аватарки, баннеры, тексты и оформление для твоего канала.</p>
              <span className="text-[10px] text-blue-500 font-bold flex items-center gap-1 group-hover:underline">
                Подробнее <ExternalLink className="w-2.5 h-2.5" />
              </span>
            </a>
          </div>

          {/* Документация */}
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-3xl p-6">
            <h4 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-4 flex items-center gap-2">
              <FileText className="w-3 h-3" />Документация
            </h4>
            <div className="space-y-2">
              <Link to="/refund"
                className="flex items-center justify-between p-3 bg-black/30 border border-zinc-800 rounded-xl text-[10px] text-zinc-400 hover:text-white hover:border-zinc-600 transition-all">
                Правила возврата <ExternalLink className="w-3 h-3 opacity-30" />
              </Link>
              <Link to="/contacts"
                className="flex items-center justify-between p-3 bg-black/30 border border-zinc-800 rounded-xl text-[10px] text-zinc-400 hover:text-white hover:border-zinc-600 transition-all">
                Контакты и реквизиты <ExternalLink className="w-3 h-3 opacity-30" />
              </Link>
              {[
                { label: 'Соглашение',          file: 'user_agreement.pdf' },
                { label: 'Конфиденциальность',  file: 'privacy_policy.pdf' },
              ].map(({ label, file }) => (
                <a key={file} href={`${GITHUB_RAW_URL}/${file}`} target="_blank" rel="noreferrer"
                  className="flex items-center justify-between p-3 bg-black/30 border border-zinc-800 rounded-xl text-[10px] text-zinc-400 hover:text-white hover:border-zinc-600 transition-all">
                  {label} <ExternalLink className="w-3 h-3 opacity-30" />
                </a>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Profile;
