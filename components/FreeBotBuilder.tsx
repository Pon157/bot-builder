// FreeBotBuilder.tsx
// Маршрут /free — бесплатный конструктор ботов (ограниченный функционал)
// Требует авторизации (тот же user из localStorage)

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bot, Play, Square, Plus, Trash2, Save, ChevronRight,
  AlertTriangle, Zap, Lock, ArrowLeft, Loader2, Terminal,
  MessageSquare, Hash
} from 'lucide-react';

const API_BASE = (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000';

interface FreeButton {
  text: string;
  response: string;
  type: 'info' | 'request';
}

interface FreeTrigger {
  keyword: string;
  response: string;
}

interface FreeBot {
  id: string;
  owner_id: string;
  name: string;
  token: string;
  status: 'IDLE' | 'RUNNING' | 'BANNED';
  welcomeMessage: string;
  adminChatId: string;
  buttons: FreeButton[];
  triggers: FreeTrigger[];
}

const FREE_LIMITS = { buttons: 3, triggers: 2 };

const api = {
  async getFreeBots(ownerId: string): Promise<FreeBot[]> {
    const r = await fetch(`${API_BASE}/api/free/bots/${ownerId}`);
    return r.ok ? r.json() : [];
  },
  async createFreeBot(data: Partial<FreeBot>): Promise<FreeBot> {
    const r = await fetch(`${API_BASE}/api/free/bots`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!r.ok) throw new Error((await r.json()).detail || 'Ошибка создания');
    return r.json();
  },
  async saveFreeBot(data: Partial<FreeBot>): Promise<void> {
    const r = await fetch(`${API_BASE}/api/free/bots/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!r.ok) throw new Error((await r.json()).detail || 'Ошибка сохранения');
  },
  async startFreeBot(id: string): Promise<void> {
    const r = await fetch(`${API_BASE}/api/free/bots/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id }),
    });
    if (!r.ok) throw new Error((await r.json()).detail || 'Ошибка запуска');
  },
  async stopFreeBot(id: string): Promise<void> {
    const r = await fetch(`${API_BASE}/api/free/bots/stop/${id}`, { method: 'POST' });
    if (!r.ok) throw new Error('Ошибка остановки');
  },
  async deleteFreeBot(ownerId: string, id: string): Promise<void> {
    const r = await fetch(`${API_BASE}/api/free/bots/delete/${ownerId}/${id}`, { method: 'DELETE' });
    if (!r.ok) throw new Error('Ошибка удаления');
  },
  async getLogs(id: string): Promise<string> {
    const r = await fetch(`${API_BASE}/api/free/bots/logs/${id}`);
    return r.ok ? (await r.json()).logs : 'Логи недоступны';
  },
};

// ── Компонент ──────────────────────────────────────────────────────────────
const FreeBotBuilder: React.FC = () => {
  const navigate = useNavigate();
  const [user, setUser] = useState<any>(null);
  const [bot, setBot] = useState<FreeBot | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [starting, setStarting] = useState(false);
  const [logs, setLogs] = useState('');
  const [showLogs, setShowLogs] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Форма создания
  const [createMode, setCreateMode] = useState(false);
  const [newName, setNewName] = useState('');
  const [newToken, setNewToken] = useState('');

  // Поля бота
  const [name, setName] = useState('');
  const [token, setToken] = useState('');
  const [welcome, setWelcome] = useState('');
  const [adminId, setAdminId] = useState('');
  const [buttons, setButtons] = useState<FreeButton[]>([]);
  const [triggers, setTriggers] = useState<FreeTrigger[]>([]);

  useEffect(() => {
    const raw = localStorage.getItem('active_session_user');
    if (!raw) { navigate('/auth'); return; }
    const u = JSON.parse(raw);
    setUser(u);
    loadBot(u.id);
  }, []);

  const loadBot = async (ownerId: string) => {
    try {
      const bots = await api.getFreeBots(ownerId);
      if (bots.length > 0) {
        const b = bots[0];
        applyBot(b);
      }
    } catch (e) { /* empty */ }
    setLoading(false);
  };

  const applyBot = (b: FreeBot) => {
    setBot(b);
    setName(b.name);
    setToken('');  // токен не показываем
    setWelcome(b.welcomeMessage || '');
    setAdminId(String(b.adminChatId || ''));
    setButtons(b.buttons || []);
    setTriggers(b.triggers || []);
  };

  const showMsg = (msg: string, isError = false) => {
    if (isError) { setError(msg); setTimeout(() => setError(''), 4000); }
    else { setSuccess(msg); setTimeout(() => setSuccess(''), 3000); }
  };

  const handleCreate = async () => {
    if (!newToken.includes(':')) return showMsg('Введите корректный токен', true);
    if (!newName.trim()) return showMsg('Введите название бота', true);
    try {
      setSaving(true);
      const b = await api.createFreeBot({
        owner_id: user.id,
        name: newName,
        token: newToken,
        welcomeMessage: 'Привет! Я бесплатный бот.',
        buttons: [],
        triggers: [],
      });
      applyBot(b);
      setCreateMode(false);
      setNewToken(''); setNewName('');
      showMsg('Бот создан!');
    } catch (e: any) {
      showMsg(e.message, true);
    } finally { setSaving(false); }
  };

  const handleSave = async () => {
    if (!bot) return;
    try {
      setSaving(true);
      await api.saveFreeBot({
        id: bot.id,
        owner_id: user.id,
        name,
        token: token || undefined,
        welcomeMessage: welcome,
        adminChatId: adminId as any,
        buttons,
        triggers,
      });
      setBot(prev => prev ? { ...prev, name, welcomeMessage: welcome, adminChatId: adminId as any, buttons, triggers } : prev);
      showMsg('Сохранено!');
    } catch (e: any) {
      showMsg(e.message, true);
    } finally { setSaving(false); }
  };

  const handleStart = async () => {
    if (!bot) return;
    try {
      setStarting(true);
      await handleSave();
      await api.startFreeBot(bot.id);
      setBot(prev => prev ? { ...prev, status: 'RUNNING' } : prev);
      showMsg('Бот запущен!');
    } catch (e: any) {
      showMsg(e.message, true);
    } finally { setStarting(false); }
  };

  const handleStop = async () => {
    if (!bot) return;
    try {
      await api.stopFreeBot(bot.id);
      setBot(prev => prev ? { ...prev, status: 'IDLE' } : prev);
      showMsg('Бот остановлен');
    } catch (e: any) { showMsg(e.message, true); }
  };

  const handleDelete = async () => {
    if (!bot || !window.confirm('Удалить бота?')) return;
    try {
      await api.deleteFreeBot(user.id, bot.id);
      setBot(null);
    } catch (e: any) { showMsg(e.message, true); }
  };

  const loadLogs = async () => {
    if (!bot) return;
    const l = await api.getLogs(bot.id);
    setLogs(l);
    setShowLogs(true);
  };

  // Кнопки
  const addButton = () => {
    if (buttons.length >= FREE_LIMITS.buttons) return showMsg(`Максимум ${FREE_LIMITS.buttons} кнопки на бесплатном плане`, true);
    setButtons(prev => [...prev, { text: '', response: '', type: 'info' }]);
  };
  const updateButton = (i: number, field: keyof FreeButton, val: string) =>
    setButtons(prev => prev.map((b, idx) => idx === i ? { ...b, [field]: val } : b));
  const removeButton = (i: number) => setButtons(prev => prev.filter((_, idx) => idx !== i));

  // Триггеры
  const addTrigger = () => {
    if (triggers.length >= FREE_LIMITS.triggers) return showMsg(`Максимум ${FREE_LIMITS.triggers} триггера на бесплатном плане`, true);
    setTriggers(prev => [...prev, { keyword: '', response: '' }]);
  };
  const updateTrigger = (i: number, field: keyof FreeTrigger, val: string) =>
    setTriggers(prev => prev.map((t, idx) => idx === i ? { ...t, [field]: val } : t));
  const removeTrigger = (i: number) => setTriggers(prev => prev.filter((_, idx) => idx !== i));

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    );
  }

  // ── UI ─────────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-zinc-300 p-4 md:p-10">
      <div className="max-w-3xl mx-auto">

        {/* Хедер */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate('/')} className="p-2 hover:bg-zinc-800 rounded-lg transition-colors">
              <ArrowLeft size={18} />
            </button>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-white font-black text-xl uppercase tracking-tight">Бесплатный конструктор</span>
                <span className="px-2 py-0.5 bg-emerald-500/15 text-emerald-400 text-[10px] font-black uppercase rounded-full border border-emerald-500/20">FREE</span>
              </div>
              <p className="text-zinc-500 text-xs mt-0.5">1 бот · 3 кнопки · 2 триггера · без AI</p>
            </div>
          </div>
          <button
            onClick={() => navigate('/ads')}
            className="flex items-center gap-2 px-4 py-2 bg-orange-500/10 border border-orange-500/20 rounded-xl text-orange-400 text-xs font-bold hover:bg-orange-500/20 transition-colors"
          >
            <Zap size={14} />
            Разместить рекламу
          </button>
        </div>

        {/* Уведомления */}
        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm flex items-center gap-2">
            <AlertTriangle size={16} /> {error}
          </div>
        )}
        {success && (
          <div className="mb-4 p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-400 text-sm">
            ✅ {success}
          </div>
        )}

        {/* Баннер ограничений */}
        <div className="mb-6 p-4 bg-zinc-900 border border-zinc-800 rounded-2xl">
          <div className="flex items-start gap-3">
            <Lock size={16} className="text-zinc-500 mt-0.5 shrink-0" />
            <div className="text-xs text-zinc-500 space-y-1">
              <p className="text-zinc-400 font-bold">Ограничения бесплатного плана:</p>
              <p>• Максимум <b className="text-zinc-300">3 кнопки</b> и <b className="text-zinc-300">2 триггера</b></p>
              <p>• Нет AI-ассистента, тем (топиков), сложных сценариев (flow)</p>
              <p>• <b className="text-zinc-300">Реклама</b> показывается после /start (монетизация платформы)</p>
              <p>• Только текстовые ответы от администратора (без медиа)</p>
              <p>• <a href="/dashboard" className="text-blue-500 hover:underline">Перейти на платный план →</a></p>
            </div>
          </div>
        </div>

        {/* Нет бота — экран создания */}
        {!bot && !createMode && (
          <div className="flex flex-col items-center justify-center py-20 gap-6 border border-dashed border-zinc-800 rounded-3xl">
            <Bot size={48} className="text-zinc-600" />
            <div className="text-center">
              <p className="text-zinc-300 font-bold text-lg">У вас нет бесплатного бота</p>
              <p className="text-zinc-600 text-sm mt-1">Создайте одного — это бесплатно</p>
            </div>
            <button
              onClick={() => setCreateMode(true)}
              className="flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 rounded-xl text-white font-bold text-sm transition-colors"
            >
              <Plus size={16} /> Создать бота
            </button>
          </div>
        )}

        {/* Форма создания */}
        {!bot && createMode && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 space-y-4">
            <h3 className="text-white font-black uppercase text-sm tracking-widest">Новый бот</h3>
            <div>
              <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">Название бота</label>
              <input
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-2.5 text-white text-sm focus:border-blue-500 focus:outline-none"
                value={newName}
                onChange={e => setNewName(e.target.value)}
                placeholder="Мой крутой бот"
              />
            </div>
            <div>
              <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">Токен бота (от @BotFather)</label>
              <input
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-2.5 text-white text-sm font-mono focus:border-blue-500 focus:outline-none"
                value={newToken}
                onChange={e => setNewToken(e.target.value)}
                placeholder="123456789:AAABB..."
              />
            </div>
            <div className="flex gap-3 pt-2">
              <button
                onClick={handleCreate}
                disabled={saving}
                className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-xl text-white font-bold text-sm transition-colors"
              >
                {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                Создать
              </button>
              <button
                onClick={() => setCreateMode(false)}
                className="px-5 py-2.5 bg-zinc-800 hover:bg-zinc-700 rounded-xl text-zinc-300 text-sm font-bold transition-colors"
              >
                Отмена
              </button>
            </div>
          </div>
        )}

        {/* Редактор бота */}
        {bot && (
          <div className="space-y-5">

            {/* Статус + управление */}
            <div className="flex items-center justify-between p-4 bg-zinc-900 border border-zinc-800 rounded-2xl">
              <div className="flex items-center gap-3">
                <div className={`w-2.5 h-2.5 rounded-full ${bot.status === 'RUNNING' ? 'bg-emerald-500 animate-pulse' : 'bg-zinc-600'}`} />
                <span className="text-white font-bold text-sm">{bot.name}</span>
                <span className="text-zinc-600 text-xs font-mono">{bot.id}</span>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={loadLogs} className="p-2 hover:bg-zinc-800 rounded-lg transition-colors" title="Логи">
                  <Terminal size={15} className="text-zinc-500" />
                </button>
                {bot.status !== 'RUNNING' ? (
                  <button
                    onClick={handleStart}
                    disabled={starting}
                    className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 rounded-xl text-white text-xs font-bold transition-colors"
                  >
                    {starting ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
                    Запустить
                  </button>
                ) : (
                  <button
                    onClick={handleStop}
                    className="flex items-center gap-1.5 px-4 py-2 bg-red-600/80 hover:bg-red-600 rounded-xl text-white text-xs font-bold transition-colors"
                  >
                    <Square size={13} /> Остановить
                  </button>
                )}
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="flex items-center gap-1.5 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 rounded-xl text-zinc-300 text-xs font-bold transition-colors"
                >
                  {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                  Сохранить
                </button>
              </div>
            </div>

            {/* Базовые настройки */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5 space-y-4">
              <h3 className="text-white font-black uppercase text-xs tracking-widest flex items-center gap-2">
                <Bot size={14} /> Основные
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">Название</label>
                  <input
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-2.5 text-white text-sm focus:border-blue-500 focus:outline-none"
                    value={name}
                    onChange={e => setName(e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">ID Админ-чата</label>
                  <input
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-2.5 text-white text-sm font-mono focus:border-blue-500 focus:outline-none"
                    value={adminId}
                    onChange={e => setAdminId(e.target.value)}
                    placeholder="-100123456789"
                  />
                </div>
              </div>
              <div>
                <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">Новый токен (оставьте пустым, чтобы не менять)</label>
                <input
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-2.5 text-white text-sm font-mono focus:border-blue-500 focus:outline-none"
                  value={token}
                  onChange={e => setToken(e.target.value)}
                  placeholder="Введите новый токен..."
                />
              </div>
              <div>
                <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">Приветственное сообщение</label>
                <textarea
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-2.5 text-white text-sm focus:border-blue-500 focus:outline-none resize-none"
                  rows={3}
                  value={welcome}
                  onChange={e => setWelcome(e.target.value)}
                />
              </div>
            </div>

            {/* Кнопки */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-white font-black uppercase text-xs tracking-widest flex items-center gap-2">
                  <MessageSquare size={14} /> Кнопки
                  <span className="text-zinc-600 font-normal normal-case text-[10px]">
                    {buttons.length}/{FREE_LIMITS.buttons}
                  </span>
                </h3>
                <button
                  onClick={addButton}
                  disabled={buttons.length >= FREE_LIMITS.buttons}
                  className="flex items-center gap-1 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-xs font-bold text-zinc-300 transition-colors"
                >
                  <Plus size={12} /> Добавить
                </button>
              </div>
              {buttons.length === 0 && (
                <p className="text-zinc-600 text-xs text-center py-4">Нет кнопок. Добавьте до {FREE_LIMITS.buttons}.</p>
              )}
              {buttons.map((btn, i) => (
                <div key={i} className="bg-zinc-800 rounded-xl p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <input
                      className="flex-1 bg-zinc-700 border border-zinc-600 rounded-lg px-3 py-2 text-white text-sm focus:border-blue-500 focus:outline-none"
                      value={btn.text}
                      onChange={e => updateButton(i, 'text', e.target.value)}
                      placeholder="Текст кнопки"
                    />
                    <select
                      className="bg-zinc-700 border border-zinc-600 rounded-lg px-3 py-2 text-zinc-300 text-xs focus:outline-none"
                      value={btn.type}
                      onChange={e => updateButton(i, 'type', e.target.value)}
                    >
                      <option value="info">Информация</option>
                      <option value="request">Обращение</option>
                    </select>
                    <button onClick={() => removeButton(i)} className="p-2 hover:bg-zinc-600 rounded-lg transition-colors">
                      <Trash2 size={14} className="text-red-400" />
                    </button>
                  </div>
                  <textarea
                    className="w-full bg-zinc-700 border border-zinc-600 rounded-lg px-3 py-2 text-zinc-300 text-sm focus:border-blue-500 focus:outline-none resize-none"
                    rows={2}
                    value={btn.response}
                    onChange={e => updateButton(i, 'response', e.target.value)}
                    placeholder="Ответ бота..."
                  />
                </div>
              ))}
            </div>

            {/* Триггеры */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-white font-black uppercase text-xs tracking-widest flex items-center gap-2">
                  <Hash size={14} /> Триггеры
                  <span className="text-zinc-600 font-normal normal-case text-[10px]">
                    {triggers.length}/{FREE_LIMITS.triggers}
                  </span>
                </h3>
                <button
                  onClick={addTrigger}
                  disabled={triggers.length >= FREE_LIMITS.triggers}
                  className="flex items-center gap-1 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-xs font-bold text-zinc-300 transition-colors"
                >
                  <Plus size={12} /> Добавить
                </button>
              </div>
              {triggers.length === 0 && (
                <p className="text-zinc-600 text-xs text-center py-4">Нет триггеров. Добавьте до {FREE_LIMITS.triggers}.</p>
              )}
              {triggers.map((trig, i) => (
                <div key={i} className="bg-zinc-800 rounded-xl p-4 space-y-2">
                  <div className="flex items-center gap-2">
                    <input
                      className="flex-1 bg-zinc-700 border border-zinc-600 rounded-lg px-3 py-2 text-white text-sm font-mono focus:border-blue-500 focus:outline-none"
                      value={trig.keyword}
                      onChange={e => updateTrigger(i, 'keyword', e.target.value)}
                      placeholder="ключевое слово"
                    />
                    <button onClick={() => removeTrigger(i)} className="p-2 hover:bg-zinc-600 rounded-lg transition-colors">
                      <Trash2 size={14} className="text-red-400" />
                    </button>
                  </div>
                  <input
                    className="w-full bg-zinc-700 border border-zinc-600 rounded-lg px-3 py-2 text-zinc-300 text-sm focus:border-blue-500 focus:outline-none"
                    value={trig.response}
                    onChange={e => updateTrigger(i, 'response', e.target.value)}
                    placeholder="Ответ бота..."
                  />
                </div>
              ))}
            </div>

            {/* Удаление */}
            <button
              onClick={handleDelete}
              className="w-full py-3 border border-red-800/30 hover:border-red-600/50 rounded-xl text-red-500/70 hover:text-red-500 text-xs font-bold uppercase tracking-widest transition-colors"
            >
              Удалить бота
            </button>
          </div>
        )}

        {/* Логи */}
        {showLogs && (
          <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-end md:items-center justify-center z-50 p-4">
            <div className="bg-[#0f0f0f] border border-zinc-800 rounded-2xl w-full max-w-2xl max-h-[70vh] flex flex-col">
              <div className="flex items-center justify-between p-4 border-b border-zinc-800">
                <span className="text-white font-black uppercase text-xs tracking-widest flex items-center gap-2">
                  <Terminal size={14} /> Логи бота
                </span>
                <button onClick={() => setShowLogs(false)} className="text-zinc-500 hover:text-white text-lg">×</button>
              </div>
              <pre className="flex-1 overflow-y-auto p-4 text-[11px] text-green-400 font-mono whitespace-pre-wrap break-all">
                {logs || 'Логи пусты'}
              </pre>
              <div className="p-3 border-t border-zinc-800">
                <button onClick={loadLogs} className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-xs font-bold text-zinc-300 transition-colors">
                  Обновить
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default FreeBotBuilder;
