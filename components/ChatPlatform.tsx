import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts';
import {
  Plus, MessageSquare, Globe, Copy, Check, Trash2, Settings,
  Users, BarChart3, Send, Shield, Eye, EyeOff, RefreshCw,
  Ban, Megaphone, X, ArrowLeft, Key, Lock, Palette, Type,
  Zap, Save, Hash, AlertCircle, ExternalLink, ChevronRight,
  User, Star, Clock, TrendingUp, Activity, UserCheck
} from 'lucide-react';
import { User as AppUser } from '../types';

// ─── Types ─────────────────────────────────────────────────────────────────────

interface SiteConfig {
  primaryColor: string; bgColor: string; fontFamily: string;
  welcomeMessage: string; commands: string[]; logoText: string;
  requireEmailVerification?: boolean; showOnlineStatus?: boolean;
}

interface ChatSite {
  id: string; owner_id: string; name: string; slug: string;
  config: SiteConfig; owner_login: string; created_at: number; is_active: boolean;
}

interface CreatedSiteResult extends ChatSite {
  owner_password_plain: string; admin_login: string;
  admin_password_plain: string; admin_name: string; admin_id: string;
}

interface SiteAdmin {
  id: string; site_id: string; display_name: string; login: string;
  avatar_color: string; bio: string; is_active: boolean; is_online: boolean;
  last_seen: number; created_at: number;
}

interface Analytics {
  overview: {
    total_users: number; active_24h: number; banned: number;
    total_conversations: number; total_messages: number;
    user_messages: number; admin_messages: number;
    avg_response_min: number; admins_count: number;
  };
  msg_chart: { day: string; user: number; admin: number; total: number }[];
  reg_chart: { day: string; count: number }[];
  hours_chart: { hour: number; count: number }[];
  admin_stats: { id: string; name: string; avatar_color: string; is_online: boolean; conversations: number; messages_sent: number }[];
}

const API = '/api';
const FONT_OPTIONS = ['Manrope, sans-serif', 'Inter, sans-serif', 'JetBrains Mono, monospace', 'Georgia, serif', 'system-ui'];
const FONT_LABELS: Record<string, string> = {
  'Manrope, sans-serif': 'Manrope', 'Inter, sans-serif': 'Inter',
  'JetBrains Mono, monospace': 'JetBrains Mono', 'Georgia, serif': 'Georgia', 'system-ui': 'Системный'
};
const COLOR_PRESETS = [
  { label: 'Индиго', primary: '#6366f1', bg: '#09090b' },
  { label: 'Синий', primary: '#3b82f6', bg: '#09090b' },
  { label: 'Изумруд', primary: '#10b981', bg: '#061a0f' },
  { label: 'Янтарь', primary: '#f59e0b', bg: '#0a0800' },
  { label: 'Розовый', primary: '#ec4899', bg: '#0d040a' },
  { label: 'Фиолет', primary: '#8b5cf6', bg: '#070510' },
];
const AVATAR_COLORS = ['#6366f1','#3b82f6','#10b981','#f59e0b','#ec4899','#8b5cf6','#ef4444','#14b8a6','#f97316','#06b6d4'];

// ─── Helpers ───────────────────────────────────────────────────────────────────

const CopyBtn: React.FC<{ value: string }> = ({ value }) => {
  const [copied, setCopied] = useState(false);
  return (
    <button onClick={() => { navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
      className={`p-1.5 rounded-lg transition-all ${copied ? 'bg-emerald-500/20 text-emerald-400' : 'bg-zinc-800 text-zinc-500 hover:text-white'}`}>
      {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
    </button>
  );
};

async function apiFetch(url: string, opts: RequestInit = {}) {
  const r = await fetch(url, { headers: { 'Content-Type': 'application/json', ...((opts as any).headers || {}) }, ...opts });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Ошибка'); }
  return r.json();
}

// ─── Create Site Modal ─────────────────────────────────────────────────────────

const CreateModal: React.FC<{ userId: string; onClose: () => void; onCreated: (s: CreatedSiteResult) => void }> = ({ userId, onClose, onCreated }) => {
  const [name, setName] = useState('');
  const [adminName, setAdminName] = useState('Поддержка');
  const [adminLogin, setAdminLogin] = useState('admin');
  const [adminPass, setAdminPass] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleCreate = async () => {
    if (!name.trim()) { setError('Введите название'); return; }
    setLoading(true); setError('');
    try {
      const data = await apiFetch(`${API}/chat/sites`, {
        method: 'POST',
        body: JSON.stringify({ owner_id: userId, name: name.trim(), admin_name: adminName.trim(), admin_login: adminLogin.trim() || undefined, admin_password: adminPass || undefined })
      });
      onCreated(data);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/80 backdrop-blur-md" onClick={onClose} />
      <div className="relative w-full max-w-md bg-[#111] border border-zinc-800 rounded-[2.5rem] p-8 shadow-2xl animate-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between mb-7">
          <div>
            <h3 className="text-xl font-black text-white">Новый чат-сайт</h3>
            <p className="text-zinc-600 text-[10px] font-bold uppercase tracking-widest mt-1">Публичная платформа поддержки</p>
          </div>
          <button onClick={onClose} className="p-2 rounded-xl hover:bg-zinc-800 text-zinc-600 hover:text-white transition-all"><X className="w-5 h-5" /></button>
        </div>
        <div className="space-y-4">
          <label className="block">
            <span className="text-[9px] font-black text-zinc-500 uppercase tracking-widest block mb-2">Название *</span>
            <input value={name} onChange={e => setName(e.target.value)} autoFocus placeholder="Поддержка клиентов"
              className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-4 rounded-2xl outline-none transition-all text-sm" />
          </label>
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-4 space-y-3">
            <p className="text-[9px] font-black text-zinc-500 uppercase tracking-widest">Первый администратор</p>
            <label className="block">
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1.5">Псевдоним</span>
              <input value={adminName} onChange={e => setAdminName(e.target.value)} placeholder="Поддержка"
                className="w-full bg-black border border-zinc-800 focus:border-blue-500/50 text-white p-3 rounded-xl outline-none transition-all text-sm" />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1.5">Логин</span>
                <input value={adminLogin} onChange={e => setAdminLogin(e.target.value)} placeholder="admin"
                  className="w-full bg-black border border-zinc-800 focus:border-blue-500/50 text-white p-3 rounded-xl outline-none transition-all text-xs" />
              </label>
              <label className="block">
                <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1.5">Пароль</span>
                <input type="password" value={adminPass} onChange={e => setAdminPass(e.target.value)} placeholder="Авто"
                  className="w-full bg-black border border-zinc-800 focus:border-blue-500/50 text-white p-3 rounded-xl outline-none transition-all text-xs" />
              </label>
            </div>
          </div>
          {error && <div className="flex items-center gap-2 bg-rose-500/10 border border-rose-500/20 rounded-xl p-3"><AlertCircle className="w-4 h-4 text-rose-400 shrink-0" /><span className="text-rose-400 text-xs">{error}</span></div>}
        </div>
        <div className="flex gap-3 mt-7">
          <button onClick={onClose} className="flex-1 py-4 rounded-2xl bg-zinc-800 text-zinc-400 text-[10px] font-black uppercase tracking-wider hover:bg-zinc-700 transition-all">Отмена</button>
          <button onClick={handleCreate} disabled={loading}
            className="flex-1 py-4 rounded-2xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-[10px] font-black uppercase tracking-wider transition-all shadow-lg shadow-blue-600/20 flex items-center justify-center gap-2">
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            {loading ? 'Создание...' : 'Создать'}
          </button>
        </div>
      </div>
    </div>
  );
};

// ─── Credentials Modal ─────────────────────────────────────────────────────────

const CredsModal: React.FC<{ site: CreatedSiteResult; onClose: () => void }> = ({ site, onClose }) => {
  const siteUrl = `${window.location.origin}/chat/${site.slug}`;
  const rows = [
    { label: 'URL сайта', value: siteUrl },
    { label: 'Логин владельца', value: site.owner_login },
    { label: 'Пароль владельца', value: site.owner_password_plain },
    { label: `Псевдоним администратора`, value: site.admin_name },
    { label: 'Логин администратора', value: site.admin_login },
    { label: 'Пароль администратора', value: site.admin_password_plain },
  ];
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/90 backdrop-blur-md" />
      <div className="relative w-full max-w-lg bg-[#111] border border-amber-500/30 rounded-[2.5rem] p-8 shadow-2xl animate-in zoom-in-95 duration-200">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
            <Shield className="w-5 h-5 text-amber-400" />
          </div>
          <div>
            <h3 className="text-lg font-black text-white">Сохраните данные доступа</h3>
            <p className="text-amber-400/70 text-[9px] font-black uppercase tracking-widest">Показывается только один раз</p>
          </div>
        </div>
        <div className="space-y-2">
          {rows.map(({ label, value }) => (
            <div key={label} className="flex items-center gap-3 bg-black/50 border border-zinc-800 rounded-2xl px-4 py-3">
              <div className="flex-1 min-w-0">
                <p className="text-[8px] text-zinc-600 font-black uppercase tracking-widest">{label}</p>
                <p className="text-white text-xs font-mono mt-0.5 truncate">{value}</p>
              </div>
              <CopyBtn value={value} />
            </div>
          ))}
        </div>
        <button onClick={onClose} className="w-full mt-6 py-4 rounded-2xl bg-amber-500 hover:bg-amber-400 text-black text-[10px] font-black uppercase tracking-wider transition-all">
          Я сохранил данные
        </button>
      </div>
    </div>
  );
};

// ─── Admin Manager ─────────────────────────────────────────────────────────────

const AdminManager: React.FC<{ site: ChatSite; userId: string }> = ({ site, userId }) => {
  const [admins, setAdmins] = useState<SiteAdmin[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editAdmin, setEditAdmin] = useState<SiteAdmin | null>(null);
  const [form, setForm] = useState({ display_name: '', login: '', password: '', bio: '', avatar_color: '#6366f1', is_active: true });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const loadAdmins = async () => {
    try {
      const data = await apiFetch(`${API}/chat/sites/${site.id}/admins?owner_id=${userId}`);
      setAdmins(Array.isArray(data) ? data : []);
    } catch { } finally { setLoading(false); }
  };

  useEffect(() => { loadAdmins(); }, [site.id]);

  const openCreate = () => {
    setEditAdmin(null);
    setForm({ display_name: '', login: '', password: '', bio: '', avatar_color: '#6366f1', is_active: true });
    setError('');
    setShowForm(true);
  };

  const openEdit = (a: SiteAdmin) => {
    setEditAdmin(a);
    setForm({ display_name: a.display_name, login: a.login, password: '', bio: a.bio || '', avatar_color: a.avatar_color, is_active: a.is_active });
    setError('');
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!form.display_name.trim() || !form.login.trim()) { setError('Псевдоним и логин обязательны'); return; }
    if (!editAdmin && !form.password) { setError('Пароль обязателен для нового администратора'); return; }
    setSaving(true); setError('');
    try {
      if (editAdmin) {
        await apiFetch(`${API}/chat/sites/${site.id}/admins/${editAdmin.id}`, {
          method: 'PATCH', body: JSON.stringify({ owner_id: userId, ...form })
        });
      } else {
        await apiFetch(`${API}/chat/sites/${site.id}/admins`, {
          method: 'POST', body: JSON.stringify({ owner_id: userId, ...form })
        });
      }
      await loadAdmins();
      setShowForm(false);
    } catch (e: any) { setError(e.message); }
    finally { setSaving(false); }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Удалить администратора?')) return;
    await fetch(`${API}/chat/sites/${site.id}/admins/${id}?owner_id=${userId}`, { method: 'DELETE' });
    setAdmins(prev => prev.filter(a => a.id !== id));
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-[9px] font-black text-zinc-500 uppercase tracking-widest">Администраторы ({admins.length})</p>
        <button onClick={openCreate}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-[9px] font-black uppercase tracking-wider bg-blue-600/20 text-blue-400 border border-blue-500/20 hover:bg-blue-600/30 transition-all">
          <Plus className="w-3.5 h-3.5" /> Добавить
        </button>
      </div>

      {/* Форма добавления/редактирования */}
      {showForm && (
        <div className="bg-zinc-900/60 border border-zinc-700 rounded-2xl p-5 space-y-4">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-black text-white">{editAdmin ? 'Редактировать' : 'Новый администратор'}</p>
            <button onClick={() => setShowForm(false)} className="text-zinc-600 hover:text-white transition-colors"><X className="w-4 h-4" /></button>
          </div>

          {/* Выбор цвета аватара */}
          <div>
            <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Цвет аватара</span>
            <div className="flex gap-2 flex-wrap">
              {AVATAR_COLORS.map(c => (
                <button key={c} onClick={() => setForm(f => ({ ...f, avatar_color: c }))}
                  className="w-8 h-8 rounded-full transition-all hover:scale-110"
                  style={{ background: c, outline: form.avatar_color === c ? `3px solid white` : 'none', outlineOffset: '2px' }} />
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1.5">Псевдоним *</span>
              <input value={form.display_name} onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))} placeholder="Иван"
                className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-3 rounded-xl outline-none transition-all text-sm" />
            </label>
            <label>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1.5">Логин *</span>
              <input value={form.login} onChange={e => setForm(f => ({ ...f, login: e.target.value }))} placeholder="ivan_support"
                className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-3 rounded-xl outline-none transition-all text-sm" />
            </label>
            <label>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1.5">{editAdmin ? 'Новый пароль' : 'Пароль *'}</span>
              <input type="password" value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))} placeholder={editAdmin ? 'Оставьте пустым' : ''}
                className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-3 rounded-xl outline-none transition-all text-sm" />
            </label>
            <label>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1.5">Статус</span>
              <div className="flex items-center gap-3 mt-2">
                <button onClick={() => setForm(f => ({ ...f, is_active: !f.is_active }))}
                  className={`relative w-10 h-5 rounded-full transition-all ${form.is_active ? 'bg-blue-600' : 'bg-zinc-700'}`}>
                  <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all ${form.is_active ? 'left-5' : 'left-0.5'}`} />
                </button>
                <span className="text-xs text-zinc-400">{form.is_active ? 'Активен' : 'Отключён'}</span>
              </div>
            </label>
          </div>
          <label>
            <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1.5">Описание (видно пользователям)</span>
            <input value={form.bio} onChange={e => setForm(f => ({ ...f, bio: e.target.value }))} placeholder="Специалист по..."
              className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-3 rounded-xl outline-none transition-all text-sm" />
          </label>
          {error && <div className="flex items-center gap-2 bg-rose-500/10 border border-rose-500/20 rounded-xl p-3"><AlertCircle className="w-4 h-4 text-rose-400 shrink-0" /><span className="text-rose-400 text-xs">{error}</span></div>}
          <div className="flex gap-3">
            <button onClick={() => setShowForm(false)} className="flex-1 py-3 rounded-xl bg-zinc-800 text-zinc-400 text-[10px] font-black uppercase tracking-wider hover:bg-zinc-700 transition-all">Отмена</button>
            <button onClick={handleSave} disabled={saving}
              className="flex-1 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-[10px] font-black uppercase tracking-wider transition-all flex items-center justify-center gap-2">
              {saving ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
              {saving ? '...' : 'Сохранить'}
            </button>
          </div>
        </div>
      )}

      {/* Список администраторов */}
      {loading ? (
        <div className="flex items-center justify-center py-8"><RefreshCw className="w-5 h-5 text-zinc-600 animate-spin" /></div>
      ) : admins.length === 0 ? (
        <div className="text-center py-8 text-zinc-700 font-bold text-sm">Нет администраторов</div>
      ) : (
        <div className="space-y-2">
          {admins.map(a => (
            <div key={a.id} className="flex items-center gap-4 p-4 bg-zinc-900/40 border border-zinc-800 rounded-2xl">
              <div className="w-10 h-10 rounded-full flex items-center justify-center font-black text-white shrink-0"
                style={{ background: a.avatar_color + '40', border: `2px solid ${a.avatar_color}60` }}>
                {a.display_name[0].toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-white font-black text-sm">{a.display_name}</span>
                  {a.is_online && <span className="text-[8px] font-black px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Онлайн</span>}
                  {!a.is_active && <span className="text-[8px] font-black px-1.5 py-0.5 rounded-full bg-zinc-800 text-zinc-500">Отключён</span>}
                </div>
                <p className="text-[10px] text-zinc-600 font-mono mt-0.5">@{a.login}{a.bio ? ` · ${a.bio}` : ''}</p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button onClick={() => openEdit(a)} className="p-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-500 hover:text-white transition-all"><Settings className="w-3.5 h-3.5" /></button>
                <button onClick={() => handleDelete(a.id)} className="p-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-500 transition-all"><Trash2 className="w-3.5 h-3.5" /></button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ─── Analytics View ────────────────────────────────────────────────────────────

const AnalyticsView: React.FC<{ site: ChatSite; userId: string }> = ({ site, userId }) => {
  const [data, setData] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);

  useEffect(() => {
    setLoading(true);
    apiFetch(`${API}/chat/site/${site.slug}/analytics?role=owner&days=${days}`)
      .then(setData).catch(() => {}).finally(() => setLoading(false));
  }, [site.slug, days]);

  if (loading) return <div className="flex items-center justify-center py-24 gap-3"><RefreshCw className="w-5 h-5 text-zinc-600 animate-spin" /><span className="text-zinc-600 text-xs font-black uppercase tracking-widest">Загрузка...</span></div>;
  if (!data) return <div className="text-center py-16 text-zinc-600 font-bold">Нет данных</div>;

  const ov = data.overview;
  const pieData = [
    { name: 'Пользователи', value: ov.user_messages },
    { name: 'Администраторы', value: ov.admin_messages },
  ];
  const PIE_COLORS = [site.config.primaryColor || '#6366f1', '#10b981'];

  const STAT_CARDS = [
    { label: 'Пользователей', value: ov.total_users, icon: Users, color: 'text-white' },
    { label: 'Активны (24ч)', value: ov.active_24h, icon: Activity, color: 'text-emerald-400' },
    { label: 'Заблокированных', value: ov.banned, icon: Ban, color: 'text-rose-400' },
    { label: 'Диалогов', value: ov.total_conversations, icon: MessageSquare, color: 'text-blue-400' },
    { label: 'Сообщений', value: ov.total_messages, icon: BarChart3, color: 'text-white' },
    { label: 'Среднее время ответа', value: ov.avg_response_min ? `${ov.avg_response_min} мин` : '—', icon: Clock, color: 'text-amber-400' },
  ];

  return (
    <div className="space-y-6">
      {/* Period selector */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-black text-white">Аналитика</h3>
        <div className="flex gap-1 bg-zinc-900 border border-zinc-800 rounded-xl p-1">
          {[7, 14, 30, 90].map(d => (
            <button key={d} onClick={() => setDays(d)}
              className={`px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-wider transition-all ${days === d ? 'bg-blue-600 text-white' : 'text-zinc-500 hover:text-zinc-300'}`}>
              {d}д
            </button>
          ))}
        </div>
      </div>

      {/* Карточки */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {STAT_CARDS.map(s => (
          <div key={s.label} className="bg-[#111] border border-zinc-800 rounded-[1.5rem] p-5">
            <div className="flex items-start justify-between mb-3">
              <p className="text-[8px] font-black text-zinc-600 uppercase tracking-widest leading-tight">{s.label}</p>
              <s.icon className="w-4 h-4 text-zinc-700" />
            </div>
            <p className={`text-3xl font-black ${s.color}`}>{s.value}</p>
          </div>
        ))}
      </div>

      {/* График сообщений */}
      {data.msg_chart.length > 0 && (
        <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6">
          <p className="text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-5">Сообщения по дням</p>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={data.msg_chart} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" />
              <XAxis dataKey="day" tick={{ fill: '#52525b', fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#52525b', fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: '#111', border: '1px solid #27272a', borderRadius: '12px', fontSize: '11px', color: '#fff' }} />
              <Line type="monotone" dataKey="total" stroke={site.config.primaryColor || '#6366f1'} strokeWidth={2} dot={false} name="Всего" />
              <Line type="monotone" dataKey="user" stroke="#71717a" strokeWidth={1.5} dot={false} name="Пользователи" strokeDasharray="4 2" />
              <Line type="monotone" dataKey="admin" stroke="#10b981" strokeWidth={1.5} dot={false} name="Администраторы" strokeDasharray="4 2" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Активность по часам */}
        <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6">
          <p className="text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-5">Активность по часам</p>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={data.hours_chart} margin={{ top: 0, right: 0, left: -25, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff06" />
              <XAxis dataKey="hour" tick={{ fill: '#52525b', fontSize: 9 }} axisLine={false} tickLine={false}
                tickFormatter={h => `${h}:00`} interval={3} />
              <YAxis tick={{ fill: '#52525b', fontSize: 9 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: '#111', border: '1px solid #27272a', borderRadius: '10px', fontSize: '11px', color: '#fff' }} formatter={(v, n) => [v, `${n}:00`]} />
              <Bar dataKey="count" fill={site.config.primaryColor || '#6366f1'} radius={[4, 4, 0, 0]} name="Час" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Pie: соотношение */}
        <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6">
          <p className="text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-5">Соотношение сообщений</p>
          {pieData.some(d => d.value > 0) ? (
            <ResponsiveContainer width="100%" height={160}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={40} outerRadius={65} paddingAngle={4} dataKey="value">
                  {pieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i]} />)}
                </Pie>
                <Tooltip contentStyle={{ background: '#111', border: '1px solid #27272a', borderRadius: '10px', fontSize: '11px', color: '#fff' }} />
                <Legend iconType="circle" iconSize={8} formatter={(v) => <span style={{ color: '#71717a', fontSize: '11px' }}>{v}</span>} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-40 flex items-center justify-center text-zinc-700 font-bold text-sm">Нет данных</div>
          )}
        </div>
      </div>

      {/* Регистрации по дням */}
      {data.reg_chart.length > 0 && (
        <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6">
          <p className="text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-5">Новые пользователи по дням</p>
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={data.reg_chart} margin={{ top: 0, right: 0, left: -25, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff06" />
              <XAxis dataKey="day" tick={{ fill: '#52525b', fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#52525b', fontSize: 10 }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip contentStyle={{ background: '#111', border: '1px solid #27272a', borderRadius: '10px', fontSize: '11px', color: '#fff' }} />
              <Bar dataKey="count" fill="#10b981" radius={[4, 4, 0, 0]} name="Регистрации" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Статистика администраторов */}
      {data.admin_stats.length > 0 && (
        <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6">
          <p className="text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-4">Статистика администраторов</p>
          <div className="space-y-3">
            {data.admin_stats.map(a => {
              const maxMsgs = Math.max(...data.admin_stats.map(x => x.messages_sent)) || 1;
              return (
                <div key={a.id} className="flex items-center gap-4">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center font-black text-white text-xs shrink-0"
                    style={{ background: a.avatar_color + '40', border: `1.5px solid ${a.avatar_color}60` }}>
                    {a.name[0].toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-white text-sm font-bold">{a.name}</span>
                      <div className="flex items-center gap-3 text-[10px] text-zinc-500">
                        <span>{a.conversations} диал.</span>
                        <span className="font-black" style={{ color: a.avatar_color }}>{a.messages_sent} msg</span>
                      </div>
                    </div>
                    <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                      <div className="h-full rounded-full transition-all" style={{ width: `${(a.messages_sent / maxMsgs) * 100}%`, background: a.avatar_color }} />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

// ─── Site Editor ───────────────────────────────────────────────────────────────

const SiteEditor: React.FC<{
  site: ChatSite; userId: string;
  onBack: () => void; onUpdated: (s: ChatSite) => void;
}> = ({ site, userId, onBack, onUpdated }) => {
  const [config, setConfig] = useState<SiteConfig>({ ...site.config });
  const [name, setName] = useState(site.name);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [tab, setTab] = useState<'design' | 'admins' | 'analytics' | 'broadcast'>('design');
  const [commandInput, setCommandInput] = useState('');
  const [broadcastText, setBroadcastText] = useState('');
  const [broadcasting, setBroadcasting] = useState(false);
  const [broadcastDone, setBroadcastDone] = useState(false);

  const siteUrl = `${window.location.origin}/chat/${site.slug}`;

  const handleSave = async () => {
    setSaving(true);
    try {
      await apiFetch(`${API}/chat/sites/${site.id}`, {
        method: 'PATCH', body: JSON.stringify({ owner_id: userId, name, config })
      });
      onUpdated({ ...site, name, config });
      setSaved(true); setTimeout(() => setSaved(false), 2500);
    } catch { alert('Ошибка сохранения'); }
    finally { setSaving(false); }
  };

  const addCmd = () => {
    const cmd = commandInput.trim();
    if (!cmd) return;
    const n = cmd.startsWith('/') ? cmd : `/${cmd}`;
    setConfig(c => ({ ...c, commands: [...(c.commands || []), n] }));
    setCommandInput('');
  };

  const handleBroadcast = async () => {
    if (!broadcastText.trim()) return;
    setBroadcasting(true);
    try {
      await apiFetch(`${API}/chat/site/${site.slug}/broadcast`, {
        method: 'POST',
        body: JSON.stringify({ role: 'owner', from_id: `owner_${site.id}`, from_name: 'Администрация', text: broadcastText })
      });
      setBroadcastDone(true); setBroadcastText('');
      setTimeout(() => setBroadcastDone(false), 3000);
    } catch { }
    finally { setBroadcasting(false); }
  };

  const TABS = [
    { id: 'design', label: 'Дизайн', icon: Palette },
    { id: 'admins', label: 'Администраторы', icon: Shield },
    { id: 'analytics', label: 'Аналитика', icon: BarChart3 },
    { id: 'broadcast', label: 'Рассылка', icon: Megaphone },
  ] as const;

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Шапка */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-4">
          <button onClick={onBack} className="flex items-center gap-2 text-zinc-500 hover:text-white text-[10px] font-black uppercase tracking-widest transition-colors group">
            <ArrowLeft className="w-3.5 h-3.5 group-hover:-translate-x-1 transition-transform" /> Все сайты
          </button>
          <div className="h-4 w-px bg-zinc-800" />
          <div>
            <h2 className="text-xl font-black text-white">{site.name}</h2>
            <div className="flex items-center gap-2 mt-0.5">
              <a href={siteUrl} target="_blank" rel="noopener noreferrer" className="text-blue-400 text-xs hover:underline font-mono truncate max-w-xs">{siteUrl}</a>
              <CopyBtn value={siteUrl} />
              <a href={siteUrl} target="_blank" rel="noopener noreferrer"><ExternalLink className="w-3 h-3 text-zinc-600 hover:text-white transition-colors" /></a>
            </div>
          </div>
        </div>
        {tab === 'design' && (
          <button onClick={handleSave} disabled={saving}
            className={`flex items-center gap-2 px-6 py-3 rounded-2xl text-[10px] font-black uppercase tracking-wider transition-all shadow-lg ${saved ? 'bg-emerald-600 shadow-emerald-600/20 text-white' : 'bg-blue-600 hover:bg-blue-500 shadow-blue-600/20 text-white'}`}>
            {saved ? <Check className="w-4 h-4" /> : <Save className="w-4 h-4" />}
            {saved ? 'Сохранено' : saving ? '...' : 'Сохранить'}
          </button>
        )}
      </div>

      {/* Табы */}
      <div className="flex gap-1 border-b border-zinc-800 overflow-x-auto no-scrollbar">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id as any)}
            className={`flex items-center gap-1.5 px-4 py-3 text-[10px] font-black uppercase tracking-widest border-b-2 transition-all whitespace-nowrap ${tab === t.id ? 'border-blue-500 text-blue-400' : 'border-transparent text-zinc-600 hover:text-zinc-300'}`}>
            <t.icon className="w-3.5 h-3.5" />{t.label}
          </button>
        ))}
      </div>

      {/* ── Дизайн ── */}
      {tab === 'design' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6 space-y-5">
            <h3 className="text-[10px] font-black text-zinc-500 uppercase tracking-widest flex items-center gap-2"><Type className="w-3.5 h-3.5" /> Текст</h3>
            <label>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Название сайта</span>
              <input value={name} onChange={e => setName(e.target.value)} className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-3.5 rounded-xl outline-none transition-all text-sm" />
            </label>
            <label>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Текст лого</span>
              <input value={config.logoText || ''} onChange={e => setConfig(c => ({ ...c, logoText: e.target.value }))} className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-3.5 rounded-xl outline-none transition-all text-sm" />
            </label>
            <label>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Приветственный текст</span>
              <textarea value={config.welcomeMessage} onChange={e => setConfig(c => ({ ...c, welcomeMessage: e.target.value }))} rows={3} className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-3.5 rounded-xl outline-none transition-all text-sm resize-none" />
            </label>
            <label>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Шрифт</span>
              <select value={config.fontFamily} onChange={e => setConfig(c => ({ ...c, fontFamily: e.target.value }))} className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-3.5 rounded-xl outline-none transition-all text-sm cursor-pointer">
                {FONT_OPTIONS.map(f => <option key={f} value={f}>{FONT_LABELS[f] || f}</option>)}
              </select>
            </label>
            <div className="flex items-center justify-between p-4 bg-zinc-900/50 rounded-xl">
              <span className="text-xs text-zinc-400 font-bold">Требовать email при регистрации</span>
              <button onClick={() => setConfig(c => ({ ...c, requireEmailVerification: !c.requireEmailVerification }))}
                className={`relative w-10 h-5 rounded-full transition-all ${config.requireEmailVerification ? 'bg-blue-600' : 'bg-zinc-700'}`}>
                <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all ${config.requireEmailVerification ? 'left-5' : 'left-0.5'}`} />
              </button>
            </div>
          </div>

          <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6 space-y-5">
            <h3 className="text-[10px] font-black text-zinc-500 uppercase tracking-widest flex items-center gap-2"><Palette className="w-3.5 h-3.5" /> Оформление</h3>
            <div>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-3">Готовые темы</span>
              <div className="grid grid-cols-3 gap-2">
                {COLOR_PRESETS.map(pr => (
                  <button key={pr.label} onClick={() => setConfig(c => ({ ...c, primaryColor: pr.primary, bgColor: pr.bg }))}
                    style={{ background: pr.bg, borderColor: config.primaryColor === pr.primary ? pr.primary : 'rgba(255,255,255,0.05)' }}
                    className="border-2 rounded-xl p-3 transition-all hover:scale-105">
                    <div className="w-full h-3 rounded-full mb-1.5" style={{ background: pr.primary }} />
                    <span className="text-[9px] font-black uppercase" style={{ color: pr.primary }}>{pr.label}</span>
                  </button>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              {[{ key: 'primaryColor', label: 'Акцент' }, { key: 'bgColor', label: 'Фон' }].map(({ key, label }) => (
                <label key={key}>
                  <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">{label}</span>
                  <div className="flex gap-2">
                    <input type="color" value={(config as any)[key]} onChange={e => setConfig(c => ({ ...c, [key]: e.target.value }))}
                      className="w-10 h-10 rounded-xl border border-zinc-800 bg-black cursor-pointer p-0.5 shrink-0" />
                    <input value={(config as any)[key]} onChange={e => setConfig(c => ({ ...c, [key]: e.target.value }))}
                      className="flex-1 bg-black border border-zinc-800 text-white text-xs p-2.5 rounded-xl outline-none focus:border-blue-500 transition-all font-mono" />
                  </div>
                </label>
              ))}
            </div>
            <div>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2 flex items-center gap-1.5"><Zap className="w-3 h-3" /> Быстрые команды</span>
              <div className="flex gap-2 mb-2">
                <input value={commandInput} onChange={e => setCommandInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && addCmd()} placeholder="/помощь"
                  className="flex-1 bg-black border border-zinc-800 focus:border-blue-500/50 text-white text-xs p-2.5 rounded-xl outline-none transition-all" />
                <button onClick={addCmd} className="px-4 py-2 bg-blue-600/20 border border-blue-500/30 text-blue-400 rounded-xl text-xs font-bold hover:bg-blue-600/30 transition-all"><Plus className="w-4 h-4" /></button>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {(config.commands || []).map((cmd, i) => (
                  <span key={i} className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 rounded-lg px-2.5 py-1 text-[10px] font-mono text-zinc-300">
                    {cmd}
                    <button onClick={() => setConfig(c => ({ ...c, commands: c.commands.filter((_, idx) => idx !== i) }))} className="text-zinc-600 hover:text-rose-400 transition-colors ml-0.5"><X className="w-3 h-3" /></button>
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === 'admins' && <AdminManager site={site} userId={userId} />}
      {tab === 'analytics' && <AnalyticsView site={site} userId={userId} />}

      {/* ── Рассылка ── */}
      {tab === 'broadcast' && (
        <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6 max-w-2xl space-y-5">
          <h3 className="text-[10px] font-black text-zinc-500 uppercase tracking-widest flex items-center gap-2"><Megaphone className="w-3.5 h-3.5" /> Рассылка всем</h3>
          <textarea value={broadcastText} onChange={e => setBroadcastText(e.target.value)} placeholder="Текст сообщения..." rows={5}
            className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-4 rounded-2xl outline-none transition-all text-sm resize-none" />
          <div className="flex items-center justify-between">
            <p className="text-[9px] text-zinc-600 font-bold">Сообщение появится во всех диалогах как системное</p>
            <button onClick={handleBroadcast} disabled={broadcasting || !broadcastText.trim()}
              className={`flex items-center gap-2 px-6 py-3 rounded-2xl text-[10px] font-black uppercase tracking-wider transition-all disabled:opacity-40 shadow-lg ${broadcastDone ? 'bg-emerald-600 shadow-emerald-600/20 text-white' : 'bg-blue-600 hover:bg-blue-500 shadow-blue-600/20 text-white'}`}>
              {broadcastDone ? <Check className="w-4 h-4" /> : <Send className="w-4 h-4" />}
              {broadcastDone ? 'Отправлено' : broadcasting ? '...' : 'Отправить'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

// ─── Main ChatPlatform ─────────────────────────────────────────────────────────

const ChatPlatform: React.FC<{ user: AppUser }> = ({ user }) => {
  const [sites, setSites] = useState<ChatSite[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [createdSite, setCreatedSite] = useState<CreatedSiteResult | null>(null);
  const [editingSite, setEditingSite] = useState<ChatSite | null>(null);

  useEffect(() => {
    apiFetch(`${API}/chat/sites/owner/${user.id}`)
      .then(data => setSites(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [user.id]);

  const handleCreated = (s: CreatedSiteResult) => {
    setSites(prev => [s, ...prev]);
    setShowCreate(false);
    setCreatedSite(s);
  };

  const handleDelete = async (siteId: string) => {
    if (!confirm('Удалить чат-сайт? Все данные будут утеряны.')) return;
    await fetch(`${API}/chat/sites/${siteId}?owner_id=${user.id}`, { method: 'DELETE' });
    setSites(prev => prev.filter(s => s.id !== siteId));
    if (editingSite?.id === siteId) setEditingSite(null);
  };

  if (editingSite) {
    return (
      <SiteEditor site={editingSite} userId={user.id}
        onBack={() => setEditingSite(null)}
        onUpdated={updated => { setSites(prev => prev.map(s => s.id === updated.id ? updated : s)); setEditingSite(updated); }}
      />
    );
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {showCreate && <CreateModal userId={user.id} onClose={() => setShowCreate(false)} onCreated={handleCreated} />}
      {createdSite && <CredsModal site={createdSite} onClose={() => setCreatedSite(null)} />}

      <header className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-4xl font-black text-white">Чат-платформы</h1>
          <p className="text-zinc-500 text-sm font-medium mt-1">Публичные мессенджеры с несколькими администраторами</p>
        </div>
        <button onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-6 py-3.5 rounded-2xl text-[10px] font-black uppercase tracking-wider transition-all shadow-lg shadow-blue-600/20">
          <Plus className="w-4 h-4" /> Создать сайт
        </button>
      </header>

      <div className="bg-blue-500/5 border border-blue-500/20 rounded-[2rem] p-5 flex gap-4 items-start">
        <div className="w-8 h-8 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center shrink-0 mt-0.5">
          <MessageSquare className="w-4 h-4 text-blue-400" />
        </div>
        <div>
          <p className="text-white font-black text-sm mb-1">Полноценная платформа поддержки</p>
          <p className="text-zinc-500 text-xs leading-relaxed">Несколько администраторов с псевдонимами, пользователи выбирают с кем общаться. Email-верификация, стикеры, медиафайлы, аналитика.</p>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-24 gap-3">
          <RefreshCw className="w-5 h-5 text-zinc-600 animate-spin" />
          <span className="text-zinc-600 text-xs font-black uppercase tracking-widest">Загрузка...</span>
        </div>
      ) : sites.length === 0 ? (
        <div className="border-2 border-dashed border-zinc-800 rounded-[2.5rem] p-16 text-center">
          <MessageSquare className="w-12 h-12 text-zinc-800 mx-auto mb-4" />
          <p className="text-zinc-600 font-black text-sm uppercase tracking-widest mb-6">Нет чат-сайтов</p>
          <button onClick={() => setShowCreate(true)}
            className="bg-blue-600 hover:bg-blue-500 px-8 py-4 rounded-2xl text-[10px] font-black text-white uppercase tracking-wider inline-flex items-center gap-2 transition-all shadow-lg shadow-blue-600/20">
            <Plus className="w-4 h-4" /> Создать первый
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {sites.map(site => {
            const siteUrl = `${window.location.origin}/chat/${site.slug}`;
            const p = site.config?.primaryColor || '#6366f1';
            return (
              <div key={site.id} className="bg-[#111] border border-zinc-800 rounded-[2.5rem] overflow-hidden hover:border-zinc-700 transition-all group">
                <div className="h-20 flex items-center px-6" style={{ background: site.config?.bgColor || '#09090b' }}>
                  <div className="w-3 h-3 rounded-full mr-2.5" style={{ background: p }} />
                  <span className="font-black text-sm truncate" style={{ color: p }}>{site.config?.logoText || site.name}</span>
                  <div className="ml-auto flex gap-1.5">
                    {[0,1,2].map(i => <div key={i} className="w-2 h-2 rounded-full bg-white/10" />)}
                  </div>
                </div>
                <div className="p-6">
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <h3 className="text-lg font-black text-white group-hover:text-blue-400 transition-colors">{site.name}</h3>
                      <a href={siteUrl} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}
                        className="text-[10px] text-zinc-600 hover:text-zinc-400 font-mono transition-colors truncate block max-w-[180px]">
                        /chat/{site.slug}
                      </a>
                    </div>
                    <div className={`w-2.5 h-2.5 rounded-full mt-1.5 ${site.is_active ? 'bg-emerald-500' : 'bg-zinc-600'}`} />
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => setEditingSite(site)}
                      className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white text-[9px] font-black uppercase tracking-wider transition-all">
                      <Settings className="w-3 h-3" /> Настройки
                    </button>
                    <a href={siteUrl} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}
                      className="py-2.5 px-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white transition-all flex items-center justify-center">
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                    <button onClick={() => handleDelete(site.id)} className="py-2.5 px-3 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-500 transition-all">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default ChatPlatform;
