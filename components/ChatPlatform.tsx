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
  User, Star, Clock, TrendingUp, Activity, UserCheck,
  AlertTriangle, VolumeX, Volume2, Pin, MessageCircle,
  Sliders, CornerDownRight, Layers
  CreditCard, RefreshCw
} from 'lucide-react';
import { User as AppUser } from '../types';

// ─── Types ─────────────────────────────────────────────────────────────────────

interface AutoReply { command: string; reply: string; }

interface SiteConfig {
  primaryColor: string; bgColor: string; fontFamily: string;
  welcomeMessage: string; commands: string[]; logoText: string;
  requireEmailVerification?: boolean; showOnlineStatus?: boolean;
  borderRadius?: string;    // 'none'|'md'|'xl'|'2xl'|'full'
  fontScale?: string;       // 'sm'|'md'|'lg'
  autoReplies?: AutoReply[];
  groupChatEnabled?: boolean;
  maxWarnsBeforeBan?: number;
  theme?: 'dark' | 'light'; // светлая/тёмная тема
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

interface SiteUser {
  id: string; username: string; email: string | null;
  is_banned: boolean; ban_reason: string | null;
  muted_until: number; warn_count: number;
  last_seen: number; created_at: number;
}

interface WarnEntry {
  id: string; admin_name: string; reason: string; created_at: number;
}

interface LicenseInfo {
  active: boolean; expires_at: number | null; days_left: number; expires_formatted: string | null;
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
const FONT_OPTIONS = [
  'Manrope, sans-serif', 'Inter, sans-serif', 'JetBrains Mono, monospace',
  'Georgia, serif', 'system-ui', 'Roboto, sans-serif', 'Nunito, sans-serif'
];
const FONT_LABELS: Record<string, string> = {
  'Manrope, sans-serif': 'Manrope', 'Inter, sans-serif': 'Inter',
  'JetBrains Mono, monospace': 'JetBrains Mono', 'Georgia, serif': 'Georgia',
  'system-ui': 'Системный', 'Roboto, sans-serif': 'Roboto', 'Nunito, sans-serif': 'Nunito'
};
const BORDER_RADIUS_OPTIONS = [
  { value: 'none', label: 'Острые' },
  { value: 'md', label: 'Мягкие' },
  { value: 'xl', label: 'Округлые' },
  { value: '2xl', label: 'Большие' },
  { value: 'full', label: 'Пузыри' },
];
const FONT_SCALE_OPTIONS = [
  { value: 'sm', label: 'Мелкий' },
  { value: 'md', label: 'Обычный' },
  { value: 'lg', label: 'Крупный' },
];
const COLOR_PRESETS = [
  // Тёмные темы
  { label: 'Индиго', primary: '#6366f1', bg: '#09090b', theme: 'dark' as const },
  { label: 'Синий', primary: '#3b82f6', bg: '#09090b', theme: 'dark' as const },
  { label: 'Изумруд', primary: '#10b981', bg: '#061a0f', theme: 'dark' as const },
  { label: 'Янтарь', primary: '#f59e0b', bg: '#0a0800', theme: 'dark' as const },
  { label: 'Розовый', primary: '#ec4899', bg: '#0d040a', theme: 'dark' as const },
  { label: 'Фиолет', primary: '#8b5cf6', bg: '#070510', theme: 'dark' as const },
  { label: 'Красный', primary: '#ef4444', bg: '#0d0505', theme: 'dark' as const },
  { label: 'Циан', primary: '#06b6d4', bg: '#05090a', theme: 'dark' as const },
  // Светлые темы
  { label: 'Белый', primary: '#6366f1', bg: '#f8f9fa', theme: 'light' as const },
  { label: 'Синий', primary: '#2563eb', bg: '#f0f4ff', theme: 'light' as const },
  { label: 'Зелёный', primary: '#059669', bg: '#f0fdf4', theme: 'light' as const },
  { label: 'Розовый', primary: '#db2777', bg: '#fdf0f6', theme: 'light' as const },
  { label: 'Янтарь', primary: '#d97706', bg: '#fffbeb', theme: 'light' as const },
  { label: 'Серый', primary: '#4b5563', bg: '#f9fafb', theme: 'light' as const },
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

const fmtTime = (ts: number) => new Date(ts).toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' });
const fmtDate = (ts: number) => new Date(ts).toLocaleDateString('ru', { day: 'numeric', month: 'short' });

// ─── License Badge ─────────────────────────────────────────────────────────────

const LicenseBadge: React.FC<{ lic: LicenseInfo | null; onActivate: () => void }> = ({ lic, onActivate }) => {
  if (!lic) return null;
  if (lic.active && lic.days_left > 7) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
        <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        <span className="text-emerald-400 text-[9px] font-black uppercase tracking-widest">
          Лицензия: {lic.days_left} дн. ({lic.expires_formatted})
        </span>
      </div>
    );
  }
  if (lic.active && lic.days_left <= 7) {
    return (
      <button onClick={onActivate}
        className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-amber-500/10 border border-amber-500/20 hover:bg-amber-500/20 transition-all">
        <AlertTriangle className="w-3 h-3 text-amber-400" />
        <span className="text-amber-400 text-[9px] font-black uppercase tracking-widest">
          Истекает: {lic.days_left} дн. — Продлить
        </span>
      </button>
    );
  }
  return (
    <button onClick={onActivate}
      className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-rose-500/10 border border-rose-500/20 hover:bg-rose-500/20 transition-all">
      <Key className="w-3 h-3 text-rose-400" />
      <span className="text-rose-400 text-[9px] font-black uppercase tracking-widest">
        Нет лицензии — Активировать
      </span>
    </button>
  );
};

// ─── Activate Key Modal ────────────────────────────────────────────────────────

const ActivateKeyModal: React.FC<{ 
  siteId: string; 
  userId: string; 
  onClose: () => void; 
  onActivated: (lic?: any) => void; 
  isNewSite?: boolean; 
  siteName?: string 
}> = ({ siteId, userId, onClose, onActivated, isNewSite, siteName }) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleBalanceBuy = async () => {
    setLoading(true); 
    setError('');
    try {
      // Используем твой api.buyService из apiService.ts
      const result = await api.buyService(userId, 'miniapp_30d', siteId);
      
      if (result && result.status === 'ok') {
        // Успех! Передаем данные о лицензии наверх
        onActivated({ 
          active: true, 
          expires_at: Date.now() + 30 * 24 * 60 * 60 * 1000 
        });
        onClose();
      } else {
        // Если денег не хватило или сервер вернул ошибку
        setError(result?.detail || 'Недостаточно средств. Пополните баланс в профиле.');
      }
    } catch (e: any) {
      setError('Ошибка соединения с сервером');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
      {/* Закрытие по клику на фон (только если это не принудительная активация нового сайта) */}
      <div className="absolute inset-0 bg-black/90 backdrop-blur-xl" onClick={isNewSite ? undefined : onClose} />
      
      <div className="relative w-full max-w-sm bg-[#0A0A0A] border border-zinc-800 rounded-[3rem] p-10 shadow-2xl animate-in zoom-in-95 duration-200">
        <div className="flex flex-col items-center text-center mb-8">
          <div className="w-16 h-16 rounded-[2rem] bg-blue-500/10 flex items-center justify-center mb-4 border border-blue-500/20">
            <Zap className="w-8 h-8 text-blue-400 fill-blue-400/20" />
          </div>
          <h3 className="text-xl font-black text-white mb-2">Активация платформы</h3>
          <p className="text-zinc-500 text-xs leading-relaxed px-4">
            Для запуска сайта «{siteName || 'Новая платформа'}» необходимо активировать лицензию на 30 дней.
          </p>
        </div>

        <div className="bg-zinc-900/50 border border-zinc-800 rounded-[2rem] p-6 mb-8 text-center">
          <div className="text-[10px] font-bold text-zinc-500 uppercase tracking-[0.2em] mb-1">Стоимость</div>
          <div className="text-3xl font-black text-white italic">150 ₽</div>
          <div className="text-[10px] text-blue-400 font-bold mt-2 uppercase">30 дней доступа</div>
        </div>

        {error && (
          <div className="mb-6 flex items-center gap-3 bg-rose-500/5 border border-rose-500/10 rounded-2xl p-4">
            <AlertCircle className="w-5 h-5 text-rose-500 shrink-0" />
            <span className="text-rose-500 text-[11px] font-bold">{error}</span>
          </div>
        )}

        <div className="space-y-3">
          <button 
            onClick={handleBalanceBuy}
            disabled={loading}
            className="w-full py-5 rounded-[1.5rem] bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-[11px] font-black uppercase tracking-wider transition-all flex items-center justify-center gap-3 shadow-lg shadow-blue-600/20"
          >
            {loading ? <RefreshCw className="w-5 h-5 animate-spin" /> : <CreditCard className="w-5 h-5" />}
            {loading ? 'Обработка...' : 'Оплатить с баланса'}
          </button>

          <button 
            onClick={onClose} 
            className="w-full py-4 rounded-[1.5rem] text-zinc-600 hover:text-white text-[10px] font-black uppercase tracking-widest transition-all"
          >
            {isNewSite ? 'Активировать позже' : 'Отмена'}
          </button>
        </div>
      </div>
    </div>
  );
};

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
    { label: 'Псевдоним администратора', value: site.admin_name },
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

  const handleSave = async () => {
    if (!form.display_name.trim() || !form.login.trim()) { setError('Псевдоним и логин обязательны'); return; }
    if (!editAdmin && !form.password) { setError('Пароль обязателен'); return; }
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
        <button onClick={() => { setEditAdmin(null); setForm({ display_name: '', login: '', password: '', bio: '', avatar_color: '#6366f1', is_active: true }); setError(''); setShowForm(true); }}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-[9px] font-black uppercase tracking-wider bg-blue-600/20 text-blue-400 border border-blue-500/20 hover:bg-blue-600/30 transition-all">
          <Plus className="w-3.5 h-3.5" /> Добавить
        </button>
      </div>

      {showForm && (
        <div className="bg-zinc-900/60 border border-zinc-700 rounded-2xl p-5 space-y-4">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-black text-white">{editAdmin ? 'Редактировать' : 'Новый администратор'}</p>
            <button onClick={() => setShowForm(false)} className="text-zinc-600 hover:text-white transition-colors"><X className="w-4 h-4" /></button>
          </div>
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

      {loading ? (
        <div className="flex justify-center py-6"><RefreshCw className="w-5 h-5 text-zinc-600 animate-spin" /></div>
      ) : (
        <div className="space-y-2">
          {admins.map(a => (
            <div key={a.id} className="flex items-center gap-4 p-4 bg-zinc-900/40 border border-zinc-800 rounded-2xl">
              <div className="w-10 h-10 rounded-full flex items-center justify-center font-black text-white text-sm shrink-0 relative"
                style={{ background: a.avatar_color + '30', border: `2px solid ${a.avatar_color}50` }}>
                {a.display_name[0]?.toUpperCase()}
                <div className={`absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-[#111] ${a.is_online ? 'bg-emerald-400' : 'bg-zinc-600'}`} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-white font-black text-sm">{a.display_name}</span>
                  {!a.is_active && <span className="text-[8px] bg-zinc-800 text-zinc-500 px-2 py-0.5 rounded-full font-bold uppercase">отключён</span>}
                  <span className={`text-[8px] px-1.5 py-0.5 rounded-full font-bold ${a.is_online ? 'bg-emerald-500/10 text-emerald-400' : 'bg-zinc-800 text-zinc-600'}`}>
                    {a.is_online ? 'онлайн' : 'офлайн'}
                  </span>
                </div>
                <p className="text-zinc-600 text-[10px] font-mono">@{a.login}</p>
                {a.bio && <p className="text-zinc-500 text-xs mt-0.5 truncate">{a.bio}</p>}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button onClick={() => { setEditAdmin(a); setForm({ display_name: a.display_name, login: a.login, password: '', bio: a.bio || '', avatar_color: a.avatar_color, is_active: a.is_active }); setError(''); setShowForm(true); }}
                  className="p-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white transition-all"><Settings className="w-3.5 h-3.5" /></button>
                <button onClick={() => handleDelete(a.id)}
                  className="p-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-500 transition-all"><Trash2 className="w-3.5 h-3.5" /></button>
              </div>
            </div>
          ))}
          {admins.length === 0 && (
            <div className="text-center py-8 text-zinc-600 font-bold text-sm">Нет администраторов</div>
          )}
        </div>
      )}
    </div>
  );
};

// ─── Users Manager ─────────────────────────────────────────────────────────────

const UsersManager: React.FC<{ site: ChatSite; userId: string }> = ({ site, userId }) => {
  const [users, setUsers] = useState<SiteUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedUser, setSelectedUser] = useState<SiteUser | null>(null);
  const [warns, setWarns] = useState<WarnEntry[]>([]);
  const [warnReason, setWarnReason] = useState('');
  const [muteMinutes, setMuteMinutes] = useState('60');
  const [banReason, setBanReason] = useState('');
  const [processing, setProcessing] = useState(false);

  const loadUsers = async () => {
    try {
      const data = await apiFetch(`${API}/chat/site/${site.slug}/users?role=owner`);
      setUsers(Array.isArray(data) ? data : []);
    } catch { } finally { setLoading(false); }
  };

  const loadWarns = async (userId: string) => {
    try {
      const data = await apiFetch(`${API}/chat/site/${site.slug}/users/${userId}/warns?role=owner`);
      setWarns(Array.isArray(data) ? data : []);
    } catch { setWarns([]); }
  };

  useEffect(() => { loadUsers(); }, [site.id]);

  const openUser = (u: SiteUser) => { setSelectedUser(u); loadWarns(u.id); };

  const handleWarn = async () => {
    if (!selectedUser || !warnReason.trim()) return;
    setProcessing(true);
    try {
      const data = await apiFetch(`${API}/chat/site/${site.slug}/users/${selectedUser.id}/warn`, {
        method: 'POST',
        body: JSON.stringify({ role: 'owner', admin_id: userId, admin_name: 'Владелец', reason: warnReason })
      });
      setWarnReason('');
      await loadWarns(selectedUser.id);
      setSelectedUser(u => u ? { ...u, warn_count: data.warn_count } : u);
      if (data.auto_banned) { alert(`Пользователь автоматически забанен (${data.warn_count} варнов)`); loadUsers(); }
    } catch (e: any) { alert(e.message); }
    finally { setProcessing(false); }
  };

  const handleMute = async (unmute = false) => {
    if (!selectedUser) return;
    setProcessing(true);
    const muted_until_ms = unmute ? 0 : Date.now() + parseInt(muteMinutes) * 60000;
    try {
      await apiFetch(`${API}/chat/site/${site.slug}/users/${selectedUser.id}/mute`, {
        method: 'POST', body: JSON.stringify({ role: 'owner', muted_until_ms })
      });
      setSelectedUser(u => u ? { ...u, muted_until: muted_until_ms } : u);
      setUsers(prev => prev.map(u => u.id === selectedUser.id ? { ...u, muted_until: muted_until_ms } : u));
    } catch (e: any) { alert(e.message); }
    finally { setProcessing(false); }
  };

  const handleBan = async (ban: boolean) => {
    if (!selectedUser) return;
    setProcessing(true);
    try {
      await apiFetch(`${API}/chat/site/${site.slug}/users/${selectedUser.id}/ban`, {
        method: 'POST', body: JSON.stringify({ role: 'owner', is_banned: ban, ban_reason: banReason || undefined })
      });
      setSelectedUser(u => u ? { ...u, is_banned: ban, ban_reason: ban ? banReason : null } : u);
      setUsers(prev => prev.map(u => u.id === selectedUser.id ? { ...u, is_banned: ban } : u));
      setBanReason('');
    } catch (e: any) { alert(e.message); }
    finally { setProcessing(false); }
  };

  const handleClearWarns = async () => {
    if (!selectedUser) return;
    try {
      await fetch(`${API}/chat/site/${site.slug}/users/${selectedUser.id}/warns?role=owner`, { method: 'DELETE' });
      setWarns([]);
      setSelectedUser(u => u ? { ...u, warn_count: 0 } : u);
      setUsers(prev => prev.map(u => u.id === selectedUser.id ? { ...u, warn_count: 0 } : u));
    } catch { }
  };

  const filtered = users.filter(u => u.username.toLowerCase().includes(search.toLowerCase()));
  const now = Date.now();

  return (
    <div className="flex gap-4 h-full min-h-[400px]">
      {/* Левая панель: список */}
      <div className="w-64 shrink-0 space-y-3">
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Поиск..."
          className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-2.5 rounded-xl outline-none transition-all text-xs" />
        <div className="space-y-1 max-h-96 overflow-y-auto no-scrollbar">
          {loading ? <div className="flex justify-center py-4"><RefreshCw className="w-4 h-4 text-zinc-600 animate-spin" /></div>
          : filtered.map(u => (
            <button key={u.id} onClick={() => openUser(u)}
              className={`w-full flex items-center gap-3 p-3 rounded-xl transition-all text-left ${selectedUser?.id === u.id ? 'bg-blue-600/20 border border-blue-500/30' : 'hover:bg-zinc-900/60 border border-transparent'}`}>
              <div className="w-7 h-7 rounded-full bg-zinc-800 flex items-center justify-center text-white text-xs font-black shrink-0">
                {u.username[0]?.toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <p className={`text-xs font-bold truncate ${u.is_banned ? 'text-zinc-600 line-through' : 'text-white'}`}>{u.username}</p>
                <div className="flex items-center gap-1 mt-0.5">
                  {u.is_banned && <span className="text-[8px] bg-rose-500/20 text-rose-400 px-1 rounded">Бан</span>}
                  {(u.muted_until || 0) > now && <span className="text-[8px] bg-orange-500/20 text-orange-400 px-1 rounded">Мут</span>}
                  {(u.warn_count || 0) > 0 && <span className="text-[8px] bg-amber-500/20 text-amber-400 px-1 rounded">{u.warn_count}⚠</span>}
                </div>
              </div>
            </button>
          ))}
          {filtered.length === 0 && !loading && <p className="text-center text-zinc-600 text-xs py-4">Нет пользователей</p>}
        </div>
      </div>

      {/* Правая панель: детали */}
      {selectedUser ? (
        <div className="flex-1 bg-zinc-900/40 border border-zinc-800 rounded-2xl p-5 space-y-5 overflow-y-auto max-h-[500px]">
          <div className="flex items-center gap-3 pb-4 border-b border-zinc-800">
            <div className="w-12 h-12 rounded-full bg-zinc-800 flex items-center justify-center text-white text-lg font-black">
              {selectedUser.username[0]?.toUpperCase()}
            </div>
            <div className="flex-1">
              <p className="text-white font-black">{selectedUser.username}</p>
              {selectedUser.email && <p className="text-zinc-600 text-xs">{selectedUser.email}</p>}
              <p className="text-zinc-700 text-[10px] mt-0.5">Был: {selectedUser.last_seen ? fmtDate(selectedUser.last_seen) : '—'}</p>
            </div>
            <div className="flex gap-2">
              {selectedUser.is_banned
                ? <span className="text-[9px] bg-rose-500/20 text-rose-400 border border-rose-500/30 px-2 py-1 rounded-lg font-black">ЗАБАНЕН</span>
                : <span className="text-[9px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-1 rounded-lg font-black">АКТИВЕН</span>
              }
            </div>
          </div>

          {/* Варны */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <p className="text-[9px] font-black text-zinc-500 uppercase tracking-widest flex items-center gap-1.5">
                <AlertTriangle className="w-3 h-3 text-amber-400" />
                Варны ({selectedUser.warn_count || 0} / {site.config.maxWarnsBeforeBan || 3})
              </p>
              {(selectedUser.warn_count || 0) > 0 && (
                <button onClick={handleClearWarns} className="text-[9px] text-zinc-500 hover:text-white transition-colors">Сбросить</button>
              )}
            </div>
            <div className="flex gap-2 mb-3">
              <input value={warnReason} onChange={e => setWarnReason(e.target.value)} placeholder="Причина варна..."
                className="flex-1 bg-black border border-zinc-800 focus:border-amber-500 text-white p-2 rounded-xl outline-none text-xs" />
              <button onClick={handleWarn} disabled={processing || !warnReason.trim()}
                className="px-3 py-2 rounded-xl bg-amber-500/20 text-amber-400 text-[9px] font-black uppercase border border-amber-500/30 hover:bg-amber-500/30 disabled:opacity-40 transition-all">
                +Варн
              </button>
            </div>
            {warns.length > 0 && (
              <div className="space-y-1 max-h-32 overflow-y-auto">
                {warns.map(w => (
                  <div key={w.id} className="flex items-start gap-2 p-2 bg-amber-500/5 border border-amber-500/10 rounded-xl">
                    <AlertTriangle className="w-3 h-3 text-amber-400 mt-0.5 shrink-0" />
                    <div>
                      <p className="text-white text-[10px]">{w.reason}</p>
                      <p className="text-zinc-600 text-[8px]">{w.admin_name} • {fmtDate(w.created_at)}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Мут */}
          <div>
            <p className="text-[9px] font-black text-zinc-500 uppercase tracking-widest mb-3 flex items-center gap-1.5">
              <VolumeX className="w-3 h-3 text-orange-400" />
              Мут {(selectedUser.muted_until || 0) > now ? `(до ${fmtDate(selectedUser.muted_until)})` : ''}
            </p>
            {(selectedUser.muted_until || 0) > now ? (
              <button onClick={() => handleMute(true)} disabled={processing}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500/10 text-emerald-400 text-[9px] font-black border border-emerald-500/20 hover:bg-emerald-500/20 disabled:opacity-40 transition-all">
                <Volume2 className="w-3 h-3" /> Снять мут
              </button>
            ) : (
              <div className="flex gap-2">
                <select value={muteMinutes} onChange={e => setMuteMinutes(e.target.value)}
                  className="bg-black border border-zinc-800 text-white p-2 rounded-xl outline-none text-xs">
                  <option value="10">10 мин</option>
                  <option value="30">30 мин</option>
                  <option value="60">1 час</option>
                  <option value="360">6 часов</option>
                  <option value="1440">24 часа</option>
                  <option value="10080">7 дней</option>
                </select>
                <button onClick={() => handleMute(false)} disabled={processing}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl bg-orange-500/10 text-orange-400 text-[9px] font-black border border-orange-500/20 hover:bg-orange-500/20 disabled:opacity-40 transition-all">
                  <VolumeX className="w-3 h-3" /> Замутить
                </button>
              </div>
            )}
          </div>

          {/* Бан */}
          <div>
            <p className="text-[9px] font-black text-zinc-500 uppercase tracking-widest mb-3 flex items-center gap-1.5">
              <Ban className="w-3 h-3 text-rose-400" /> Блокировка
            </p>
            {selectedUser.is_banned ? (
              <div>
                {selectedUser.ban_reason && <p className="text-zinc-500 text-xs mb-2">Причина: {selectedUser.ban_reason}</p>}
                <button onClick={() => handleBan(false)} disabled={processing}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500/10 text-emerald-400 text-[9px] font-black border border-emerald-500/20 hover:bg-emerald-500/20 disabled:opacity-40 transition-all">
                  <Check className="w-3 h-3" /> Разблокировать
                </button>
              </div>
            ) : (
              <div className="flex gap-2">
                <input value={banReason} onChange={e => setBanReason(e.target.value)} placeholder="Причина бана..."
                  className="flex-1 bg-black border border-zinc-800 focus:border-rose-500 text-white p-2 rounded-xl outline-none text-xs" />
                <button onClick={() => handleBan(true)} disabled={processing}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl bg-rose-500/10 text-rose-400 text-[9px] font-black border border-rose-500/20 hover:bg-rose-500/20 disabled:opacity-40 transition-all">
                  <Ban className="w-3 h-3" /> Забанить
                </button>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-zinc-700 font-bold text-sm">Выберите пользователя</p>
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
  const p = site.config.primaryColor || '#6366f1';
  const pieData = [
    { name: 'Пользователи', value: ov.user_messages },
    { name: 'Администраторы', value: ov.admin_messages },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
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

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {[
          { label: 'Пользователей', value: ov.total_users, color: 'text-white' },
          { label: 'Активны 24ч', value: ov.active_24h, color: 'text-emerald-400' },
          { label: 'Заблокировано', value: ov.banned, color: 'text-rose-400' },
          { label: 'Диалогов', value: ov.total_conversations, color: 'text-blue-400' },
          { label: 'Сообщений', value: ov.total_messages, color: 'text-white' },
          { label: 'Ср. ответ', value: ov.avg_response_min ? `${ov.avg_response_min}мин` : '—', color: 'text-amber-400' },
        ].map(s => (
          <div key={s.label} className="bg-[#111] border border-zinc-800 rounded-[1.5rem] p-5">
            <p className="text-[8px] font-black text-zinc-600 uppercase tracking-widest mb-3">{s.label}</p>
            <p className={`text-3xl font-black ${s.color}`}>{s.value}</p>
          </div>
        ))}
      </div>

      {data.msg_chart.length > 0 && (
        <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6">
          <p className="text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-5">Сообщения по дням</p>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={data.msg_chart} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" />
              <XAxis dataKey="day" tick={{ fill: '#52525b', fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#52525b', fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: '#111', border: '1px solid #27272a', borderRadius: '12px', fontSize: '11px', color: '#fff' }} />
              <Line type="monotone" dataKey="total" stroke={p} strokeWidth={2} dot={false} name="Всего" />
              <Line type="monotone" dataKey="user" stroke="#71717a" strokeWidth={1.5} dot={false} name="Пользователи" strokeDasharray="4 2" />
              <Line type="monotone" dataKey="admin" stroke="#10b981" strokeWidth={1.5} dot={false} name="Администраторы" strokeDasharray="4 2" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6">
          <p className="text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-5">Активность по часам</p>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={data.hours_chart} margin={{ top: 0, right: 0, left: -25, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff06" />
              <XAxis dataKey="hour" tick={{ fill: '#52525b', fontSize: 9 }} axisLine={false} tickLine={false} tickFormatter={h => `${h}:00`} interval={3} />
              <YAxis tick={{ fill: '#52525b', fontSize: 9 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: '#111', border: '1px solid #27272a', borderRadius: '10px', fontSize: '11px', color: '#fff' }} />
              <Bar dataKey="count" fill={p} radius={[4, 4, 0, 0]} name="Сообщений" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6">
          <p className="text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-5">Соотношение сообщений</p>
          {pieData.some(d => d.value > 0) ? (
            <ResponsiveContainer width="100%" height={160}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={40} outerRadius={65} paddingAngle={4} dataKey="value">
                  {pieData.map((_, i) => <Cell key={i} fill={[p, '#10b981'][i]} />)}
                </Pie>
                <Tooltip contentStyle={{ background: '#111', border: '1px solid #27272a', borderRadius: '10px', fontSize: '11px', color: '#fff' }} />
                <Legend iconType="circle" iconSize={8} formatter={(v) => <span style={{ color: '#71717a', fontSize: '11px' }}>{v}</span>} />
              </PieChart>
            </ResponsiveContainer>
          ) : <div className="h-40 flex items-center justify-center text-zinc-700 font-bold text-sm">Нет данных</div>}
        </div>
      </div>

      {data.admin_stats.length > 0 && (
        <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6">
          <p className="text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-4">Статистика администраторов</p>
          <div className="space-y-3">
            {data.admin_stats.map(a => {
              const maxMsgs = Math.max(...data.admin_stats.map(x => x.messages_sent)) || 1;
              return (
                <div key={a.id} className="flex items-center gap-4">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center font-black text-white text-xs shrink-0 relative"
                    style={{ background: a.avatar_color + '40', border: `1.5px solid ${a.avatar_color}60` }}>
                    {a.name[0].toUpperCase()}
                    <div className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-[#111] ${a.is_online ? 'bg-emerald-400' : 'bg-zinc-600'}`} />
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


// ─── License Gated Editor ──────────────────────────────────────────────────────
// Показывает экран активации если нет лицензии, иначе — SiteEditor

const LicenseGatedEditor: React.FC<{
  site: ChatSite; userId: string;
  onBack: () => void; onUpdated: (s: ChatSite) => void;
}> = ({ site, userId, onBack, onUpdated }) => {
  const [license, setLicense] = useState<LicenseInfo | null>(null);
  const [licLoading, setLicLoading] = useState(true);
  const [showActivate, setShowActivate] = useState(false);

  const loadLicense = () => {
    setLicLoading(true);
    apiFetch(`${API}/chat/sites/${site.id}/license?owner_id=${userId}`)
      .then(setLicense)
      .catch(() => setLicense(null))
      .finally(() => setLicLoading(false));
  };

  useEffect(() => { loadLicense(); }, [site.id]);

  if (licLoading) return (
    <div className="min-h-screen bg-[#09090b] flex items-center justify-center">
      <RefreshCw className="w-6 h-6 text-white/20 animate-spin" />
    </div>
  );

  if (!license?.active) {
    return (
      <div className="min-h-screen bg-[#09090b] flex flex-col items-center justify-center p-6 gap-6 relative">
        {/* Expired overlay on top of editor UI */}
        <div className="absolute inset-0 bg-black/70 backdrop-blur-sm z-40 flex items-center justify-center">
          <div className="flex flex-col items-center gap-6 max-w-sm w-full text-center p-8 bg-[#111] border border-rose-500/20 rounded-[2.5rem] shadow-2xl">
            <div className="w-16 h-16 rounded-3xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center">
              <Lock className="w-8 h-8 text-rose-400" />
            </div>
            <div>
              <h2 className="text-2xl font-black text-white mb-2">Лицензия истекла</h2>
              <p className="text-zinc-500 text-sm leading-relaxed">
                Доступ к конструктору сайта <span className="text-white font-bold">«{site.name}»</span> заблокирован. Обновите лицензию для продолжения работы.
              </p>
            </div>
            <div className="w-full space-y-3">
              <button
                onClick={() => setShowActivate(true)}
                className="w-full py-4 rounded-2xl font-black text-[11px] uppercase tracking-wider text-white transition-all flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 shadow-lg shadow-blue-600/20"
              >
                <Key className="w-4 h-4" /> Активировать новый ключ
              </button>
              <button onClick={onBack} className="w-full py-3 rounded-2xl bg-zinc-800 hover:bg-zinc-700 text-zinc-400 font-black text-[10px] uppercase tracking-wider transition-all">
                Вернуться назад
              </button>
            </div>
          </div>
        </div>
        {showActivate && (
          <ActivateKeyModal
            siteId={site.id}
            userId={userId}
            onClose={() => setShowActivate(false)}
            onActivated={lic => { setLicense(lic ?? null); setShowActivate(false); }}
          />
        )}
      </div>
    );
  }

  return (
    <SiteEditor
      site={site}
      userId={userId}
      onBack={onBack}
      onUpdated={onUpdated}
      license={license}
    />
  );
};

const SiteEditor: React.FC<{
  site: ChatSite; userId: string;
  onBack: () => void; onUpdated: (s: ChatSite) => void;
  license?: LicenseInfo | null;
}> = ({ site, userId, onBack, onUpdated, license: propLicense }) => {
  const [config, setConfig] = useState<SiteConfig>({ ...site.config });
  const [name, setName] = useState(site.name);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [tab, setTab] = useState<'design' | 'admins' | 'users' | 'analytics' | 'broadcast' | 'license'>('design');
  const [commandInput, setCommandInput] = useState('');
  const [autoReplyCmd, setAutoReplyCmd] = useState('');
  const [autoReplyText, setAutoReplyText] = useState('');
  const [broadcastText, setBroadcastText] = useState('');
  const [broadcasting, setBroadcasting] = useState(false);
  const [broadcastDone, setBroadcastDone] = useState(false);
  const [license, setLicense] = useState<LicenseInfo | null>(propLicense || null);
  const [showActivateKey, setShowActivateKey] = useState(false);

  const siteUrl = `${window.location.origin}/chat/${site.slug}`;

  useEffect(() => {
    if (!propLicense) {
      apiFetch(`${API}/chat/sites/${site.id}/license?owner_id=${userId}`)
        .then(setLicense).catch(() => {});
    }
  }, [site.id]);

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

  const addAutoReply = () => {
    if (!autoReplyCmd.trim() || !autoReplyText.trim()) return;
    const cmd = autoReplyCmd.startsWith('/') ? autoReplyCmd.trim() : `/${autoReplyCmd.trim()}`;
    setConfig(c => ({ ...c, autoReplies: [...(c.autoReplies || []), { command: cmd, reply: autoReplyText.trim() }] }));
    setAutoReplyCmd(''); setAutoReplyText('');
  };

  const removeAutoReply = (i: number) => {
    setConfig(c => ({ ...c, autoReplies: (c.autoReplies || []).filter((_, idx) => idx !== i) }));
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
    { id: 'users', label: 'Пользователи', icon: Users },
    { id: 'analytics', label: 'Аналитика', icon: BarChart3 },
    { id: 'broadcast', label: 'Рассылка', icon: Megaphone },
    { id: 'license', label: 'Лицензия', icon: Key },
  ] as const;

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {showActivateKey && (
        <ActivateKeyModal siteId={site.id} userId={userId}
          onClose={() => setShowActivateKey(false)}
          onActivated={lic => { setLicense(lic); setShowActivateKey(false); }} />
      )}

      {/* Шапка */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-4 flex-wrap">
          <button onClick={onBack} className="flex items-center gap-2 text-zinc-500 hover:text-white text-[10px] font-black uppercase tracking-widest transition-colors group">
            <ArrowLeft className="w-3.5 h-3.5 group-hover:-translate-x-1 transition-transform" /> Все сайты
          </button>
          <div className="h-4 w-px bg-zinc-800 hidden sm:block" />
          <div>
            <h2 className="text-xl font-black text-white">{site.name}</h2>
            <div className="flex items-center gap-2 mt-0.5">
              <a href={siteUrl} target="_blank" rel="noopener noreferrer" className="text-blue-400 text-xs hover:underline font-mono truncate max-w-[180px] sm:max-w-xs">{siteUrl}</a>
              <CopyBtn value={siteUrl} />
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <LicenseBadge lic={license} onActivate={() => setShowActivateKey(true)} />
          {tab === 'design' && (
            <button onClick={handleSave} disabled={saving}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-2xl text-[10px] font-black uppercase tracking-wider transition-all shadow-lg ${saved ? 'bg-emerald-600 shadow-emerald-600/20 text-white' : 'bg-blue-600 hover:bg-blue-500 shadow-blue-600/20 text-white'}`}>
              {saved ? <Check className="w-4 h-4" /> : <Save className="w-4 h-4" />}
              {saved ? 'Сохранено' : saving ? '...' : 'Сохранить'}
            </button>
          )}
        </div>
      </div>

      {/* Табы */}
      <div className="flex gap-1 border-b border-zinc-800 overflow-x-auto no-scrollbar">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id as any)}
            className={`flex items-center gap-1.5 px-3 sm:px-4 py-3 text-[10px] font-black uppercase tracking-widest border-b-2 transition-all whitespace-nowrap ${tab === t.id ? 'border-blue-500 text-blue-400' : 'border-transparent text-zinc-600 hover:text-zinc-300'}`}>
            <t.icon className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">{t.label}</span>
          </button>
        ))}
      </div>

      {/* ── Дизайн ── */}
      {tab === 'design' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Текст и шрифты */}
          <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6 space-y-5">
            <h3 className="text-[10px] font-black text-zinc-500 uppercase tracking-widest flex items-center gap-2"><Type className="w-3.5 h-3.5" /> Текст и шрифты</h3>
            <label>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Название сайта</span>
              <input value={name} onChange={e => setName(e.target.value)} className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-3.5 rounded-xl outline-none transition-all text-sm" />
            </label>
            <label>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Текст лого</span>
              <input value={config.logoText || ''} onChange={e => setConfig(c => ({ ...c, logoText: e.target.value }))} className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-3.5 rounded-xl outline-none transition-all text-sm" />
            </label>
            <label>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Приветствие</span>
              <input value={config.welcomeMessage || ''} onChange={e => setConfig(c => ({ ...c, welcomeMessage: e.target.value }))} className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-3.5 rounded-xl outline-none transition-all text-sm" />
            </label>

            {/* Шрифт */}
            <div>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Шрифт</span>
              <div className="grid grid-cols-2 gap-2">
                {FONT_OPTIONS.map(f => (
                  <button key={f} onClick={() => setConfig(c => ({ ...c, fontFamily: f }))}
                    className={`p-3 rounded-xl text-left transition-all border ${config.fontFamily === f ? 'border-blue-500 bg-blue-500/10 text-blue-400' : 'border-zinc-800 bg-black text-zinc-500 hover:border-zinc-700'}`}
                    style={{ fontFamily: f }}>
                    <span className="text-xs font-bold">{FONT_LABELS[f]}</span>
                    <span className="text-[9px] block text-current opacity-50 mt-0.5">Aa Бб 123</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Размер шрифта */}
            <div>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Размер шрифта</span>
              <div className="flex gap-2">
                {FONT_SCALE_OPTIONS.map(o => (
                  <button key={o.value} onClick={() => setConfig(c => ({ ...c, fontScale: o.value }))}
                    className={`flex-1 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-wider transition-all border ${(config.fontScale || 'md') === o.value ? 'border-blue-500 bg-blue-500/10 text-blue-400' : 'border-zinc-800 bg-black text-zinc-600 hover:border-zinc-700'}`}>
                    {o.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Цвета и скругление */}
          <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6 space-y-5">
            <h3 className="text-[10px] font-black text-zinc-500 uppercase tracking-widest flex items-center gap-2"><Palette className="w-3.5 h-3.5" /> Цвета и форма</h3>
            
            <div>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Готовые темы</span>
              <div className="grid grid-cols-4 sm:grid-cols-6 gap-2">
                {COLOR_PRESETS.map(pr => (
                  <button key={pr.label} onClick={() => setConfig(c => ({ ...c, primaryColor: pr.primary, bgColor: pr.bg, theme: pr.theme }))}
                    className={`p-2.5 rounded-xl transition-all border ${config.primaryColor === pr.primary && (config.theme || 'dark') === pr.theme ? 'border-white/30' : 'border-zinc-800'}`}
                    style={{ background: pr.bg }}>
                    <div className="w-full h-4 rounded-lg mb-1" style={{ background: pr.primary }} />
                    <span className="text-[8px] font-bold" style={{ color: pr.primary }}>{pr.label}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Основной цвет</span>
                <div className="flex items-center gap-2">
                  <div className="w-10 h-10 rounded-xl border border-zinc-700 cursor-pointer overflow-hidden">
                    <input type="color" value={config.primaryColor || '#6366f1'} onChange={e => setConfig(c => ({ ...c, primaryColor: e.target.value }))}
                      className="w-14 h-14 -ml-2 -mt-2 cursor-pointer" />
                  </div>
                  <span className="text-white text-xs font-mono">{config.primaryColor}</span>
                </div>
              </div>
              <div>
                <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Фон</span>
                <div className="flex items-center gap-2">
                  <div className="w-10 h-10 rounded-xl border border-zinc-700 cursor-pointer overflow-hidden">
                    <input type="color" value={config.bgColor || '#09090b'} onChange={e => setConfig(c => ({ ...c, bgColor: e.target.value }))}
                      className="w-14 h-14 -ml-2 -mt-2 cursor-pointer" />
                  </div>
                  <span className="text-white text-xs font-mono">{config.bgColor}</span>
                </div>
              </div>
            </div>

            {/* Theme toggle */}
            <div>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Тема интерфейса</span>
              <div className="flex gap-2">
                {([
                  { value: 'dark', label: '🌙 Тёмная', desc: 'Тёмный фон' },
                  { value: 'light', label: '☀️ Светлая', desc: 'Светлый фон' },
                ] as const).map(opt => (
                  <button key={opt.value} onClick={() => {
                    setConfig(c => ({
                      ...c,
                      theme: opt.value,
                      bgColor: opt.value === 'light' ? (c.bgColor === '#09090b' || c.bgColor === '#061a0f' || c.bgColor === '#0a0800' || c.bgColor === '#0d040a' || c.bgColor === '#070510' || c.bgColor === '#0d0505' || c.bgColor === '#05090a' ? '#f8f9fa' : c.bgColor) : (c.bgColor === '#f8f9fa' || c.bgColor === '#f0f4ff' || c.bgColor === '#f0fdf4' || c.bgColor === '#fdf0f6' || c.bgColor === '#fffbeb' || c.bgColor === '#f9fafb' ? '#09090b' : c.bgColor)
                    }));
                  }}
                    className="flex-1 py-3 px-3 rounded-xl text-xs font-black uppercase tracking-wider transition-all border flex flex-col items-center gap-1"
                    style={{
                      background: (config.theme || 'dark') === opt.value ? '#6366f120' : 'transparent',
                      borderColor: (config.theme || 'dark') === opt.value ? '#6366f150' : '#27272a',
                      color: (config.theme || 'dark') === opt.value ? '#a5b4fc' : '#52525b'
                    }}>
                    <span className="text-base">{opt.label.split(' ')[0]}</span>
                    <span className="text-[8px]">{opt.label.split(' ').slice(1).join(' ')}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Скругление углов */}
            <div>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2 flex items-center gap-1.5"><Sliders className="w-3 h-3" /> Скругление углов</span>
              <div className="grid grid-cols-5 gap-1.5">
                {BORDER_RADIUS_OPTIONS.map(o => {
                  const radiusMap: Record<string,string> = { none: '4px', md: '8px', xl: '14px', '2xl': '20px', full: '999px' };
                  return (
                    <button key={o.value} onClick={() => setConfig(c => ({ ...c, borderRadius: o.value }))}
                      className={`py-2 text-[9px] font-black uppercase tracking-wider transition-all border flex flex-col items-center gap-1 ${(config.borderRadius || '2xl') === o.value ? 'border-blue-500 bg-blue-500/10 text-blue-400' : 'border-zinc-800 bg-black text-zinc-600 hover:border-zinc-700'}`}
                      style={{ borderRadius: '10px' }}>
                      <div className="w-5 h-5 bg-current opacity-30" style={{ borderRadius: radiusMap[o.value] }} />
                      {o.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Настройки */}
            <div className="space-y-3">
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block">Дополнительно</span>
              {[
                { key: 'requireEmailVerification', label: 'Email-верификация при регистрации' },
                { key: 'showOnlineStatus', label: 'Показывать онлайн-статус' },
                { key: 'groupChatEnabled', label: 'Групповой чат (все вместе)' },
              ].map(({ key, label }) => (
                <div key={key} className="flex items-center justify-between">
                  <span className="text-zinc-400 text-xs">{label}</span>
                  <button onClick={() => setConfig(c => ({ ...c, [key]: !(c as any)[key] }))}
                    className={`relative w-9 h-5 rounded-full transition-all ${(config as any)[key] ? 'bg-blue-600' : 'bg-zinc-700'}`}>
                    <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all ${(config as any)[key] ? 'left-4' : 'left-0.5'}`} />
                  </button>
                </div>
              ))}
              <div className="flex items-center justify-between">
                <span className="text-zinc-400 text-xs">Авто-бан после N варнов</span>
                <select value={config.maxWarnsBeforeBan || 3}
                  onChange={e => setConfig(c => ({ ...c, maxWarnsBeforeBan: parseInt(e.target.value) }))}
                  className="bg-black border border-zinc-800 text-white p-1.5 rounded-lg outline-none text-xs">
                  {[2,3,5,10].map(n => <option key={n} value={n}>{n}</option>)}
                </select>
              </div>
            </div>
          </div>

          {/* Команды */}
          <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6 space-y-4">
            <h3 className="text-[10px] font-black text-zinc-500 uppercase tracking-widest flex items-center gap-2"><Hash className="w-3.5 h-3.5" /> Команды (подсказки)</h3>
            <div className="flex gap-2">
              <input value={commandInput} onChange={e => setCommandInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && addCmd()}
                placeholder="/help /start..."
                className="flex-1 bg-black border border-zinc-800 focus:border-blue-500 text-white p-3 rounded-xl outline-none transition-all text-sm" />
              <button onClick={addCmd} className="px-4 py-2 rounded-xl bg-blue-600 text-white text-xs font-black hover:bg-blue-500 transition-all">+</button>
            </div>
            <div className="flex flex-wrap gap-2">
              {(config.commands || []).map(cmd => (
                <span key={cmd} className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-zinc-900 border border-zinc-800 text-zinc-400 text-xs font-mono">
                  {cmd}
                  <button onClick={() => setConfig(c => ({ ...c, commands: (c.commands || []).filter(x => x !== cmd) }))} className="text-zinc-600 hover:text-rose-400 transition-colors"><X className="w-3 h-3" /></button>
                </span>
              ))}
            </div>
          </div>

          {/* Авто-ответы */}
          <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6 space-y-4">
            <h3 className="text-[10px] font-black text-zinc-500 uppercase tracking-widest flex items-center gap-2"><CornerDownRight className="w-3.5 h-3.5" /> Авто-ответы на команды</h3>
            <div className="space-y-2">
              <div className="flex gap-2">
                <input value={autoReplyCmd} onChange={e => setAutoReplyCmd(e.target.value)} placeholder="/help"
                  className="w-24 bg-black border border-zinc-800 focus:border-blue-500 text-white p-2.5 rounded-xl outline-none text-xs font-mono" />
                <input value={autoReplyText} onChange={e => setAutoReplyText(e.target.value)} placeholder="Ответ на команду..."
                  onKeyDown={e => e.key === 'Enter' && addAutoReply()}
                  className="flex-1 bg-black border border-zinc-800 focus:border-blue-500 text-white p-2.5 rounded-xl outline-none text-xs" />
                <button onClick={addAutoReply} className="px-3 py-2 rounded-xl bg-blue-600 text-white text-xs font-black hover:bg-blue-500 transition-all">+</button>
              </div>
            </div>
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {(config.autoReplies || []).map((ar, i) => (
                <div key={i} className="flex items-start gap-2 p-3 bg-zinc-900/60 border border-zinc-800 rounded-xl">
                  <span className="text-blue-400 text-xs font-mono font-black shrink-0">{ar.command}</span>
                  <CornerDownRight className="w-3 h-3 text-zinc-600 shrink-0 mt-0.5" />
                  <span className="text-zinc-400 text-xs flex-1 min-w-0 break-words">{ar.reply}</span>
                  <button onClick={() => removeAutoReply(i)} className="text-zinc-600 hover:text-rose-400 transition-colors shrink-0"><X className="w-3.5 h-3.5" /></button>
                </div>
              ))}
              {!(config.autoReplies || []).length && (
                <p className="text-zinc-700 text-xs text-center py-3">Нет авто-ответов</p>
              )}
            </div>
          </div>
        </div>
      )}

      {tab === 'admins' && (
        <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6">
          <AdminManager site={site} userId={userId} />
        </div>
      )}

      {tab === 'users' && (
        <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6">
          <UsersManager site={site} userId={userId} />
        </div>
      )}

      {tab === 'analytics' && <AnalyticsView site={site} userId={userId} />}

      {tab === 'broadcast' && (
        <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6 max-w-2xl space-y-5">
          <h3 className="text-[10px] font-black text-zinc-500 uppercase tracking-widest flex items-center gap-2"><Megaphone className="w-3.5 h-3.5" /> Рассылка всем</h3>
          <textarea value={broadcastText} onChange={e => setBroadcastText(e.target.value)} placeholder="Текст сообщения..." rows={5}
            className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-4 rounded-2xl outline-none transition-all text-sm resize-none" />
          <div className="flex items-center justify-between flex-wrap gap-3">
            <p className="text-[9px] text-zinc-600 font-bold">Сообщение появится во всех диалогах как системное</p>
            <button onClick={handleBroadcast} disabled={broadcasting || !broadcastText.trim()}
              className={`flex items-center gap-2 px-6 py-3 rounded-2xl text-[10px] font-black uppercase tracking-wider transition-all disabled:opacity-40 shadow-lg ${broadcastDone ? 'bg-emerald-600 shadow-emerald-600/20 text-white' : 'bg-blue-600 hover:bg-blue-500 shadow-blue-600/20 text-white'}`}>
              {broadcastDone ? <Check className="w-4 h-4" /> : <Send className="w-4 h-4" />}
              {broadcastDone ? 'Отправлено' : broadcasting ? '...' : 'Отправить'}
            </button>
          </div>
        </div>
      )}

      {tab === 'license' && (
        <div className="max-w-md space-y-5">
          <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6 space-y-5">
            <h3 className="text-[10px] font-black text-zinc-500 uppercase tracking-widest flex items-center gap-2"><Key className="w-3.5 h-3.5" /> Лицензия сайта</h3>
            {license?.active ? (
              <div className="space-y-4">
                <div className="p-5 bg-emerald-500/5 border border-emerald-500/20 rounded-2xl">
                  <div className="flex items-center gap-3 mb-3">
                    <div className="w-3 h-3 rounded-full bg-emerald-400 animate-pulse" />
                    <span className="text-emerald-400 font-black">Лицензия активна</span>
                  </div>
                  <p className="text-white text-2xl font-black mb-1">{license.days_left} дней</p>
                  <p className="text-zinc-500 text-xs">до {license.expires_formatted}</p>
                </div>
                <button onClick={() => setShowActivateKey(true)}
                  className="w-full py-3.5 rounded-2xl border border-zinc-800 text-zinc-400 text-[10px] font-black uppercase tracking-wider hover:bg-zinc-900 transition-all flex items-center justify-center gap-2">
                  <Plus className="w-4 h-4" /> Добавить ещё один ключ (продлить)
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="p-5 bg-rose-500/5 border border-rose-500/20 rounded-2xl">
                  <p className="text-rose-400 font-black mb-1">Лицензия не активирована</p>
                  <p className="text-zinc-500 text-xs">Для работы сайта необходим активный ключ</p>
                </div>
                <div className="p-4 bg-zinc-900/50 border border-zinc-800 rounded-2xl space-y-2">
                  <p className="text-white font-black text-sm">1 месяц = 150 ₽</p>
                  <p className="text-zinc-500 text-xs leading-relaxed">Приобретите ключ доступа и активируйте его. Один ключ активируется на один сайт.</p>
                </div>
                <button onClick={() => setShowActivateKey(true)}
                  className="w-full py-4 rounded-2xl bg-blue-600 hover:bg-blue-500 text-white text-[10px] font-black uppercase tracking-wider transition-all shadow-lg shadow-blue-600/20 flex items-center justify-center gap-2">
                  <Key className="w-4 h-4" /> Активировать ключ
                </button>
              </div>
            )}
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
  const [activateNewSite, setActivateNewSite] = useState<CreatedSiteResult | null>(null);

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
    // Immediately open key activation for the newly created site
    setActivateNewSite(s);
  };

  const handleDelete = async (siteId: string) => {
    if (!confirm('Удалить чат-сайт? Все данные будут утеряны.')) return;
    await fetch(`${API}/chat/sites/${siteId}?owner_id=${user.id}`, { method: 'DELETE' });
    setSites(prev => prev.filter(s => s.id !== siteId));
    if (editingSite?.id === siteId) setEditingSite(null);
  };

  if (editingSite) {
    return (
      <LicenseGatedEditor
        site={editingSite}
        userId={user.id}
        onBack={() => setEditingSite(null)}
        onUpdated={updated => { setSites(prev => prev.map(s => s.id === updated.id ? updated : s)); setEditingSite(updated); }}
      />
    );
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {showCreate && <CreateModal userId={user.id} onClose={() => setShowCreate(false)} onCreated={handleCreated} />}
      {createdSite && <CredsModal site={createdSite} onClose={() => setCreatedSite(null)} />}
      {activateNewSite && (
        <ActivateKeyModal
          siteId={activateNewSite.id}
          userId={user.id}
          onClose={() => setActivateNewSite(null)}
          onActivated={() => {
            setActivateNewSite(null);
            apiFetch(`${API}/chat/sites/owner/${user.id}`)
              .then(data => setSites(Array.isArray(data) ? data : []))
              .catch(() => {});
          }}
          isNewSite
          siteName={activateNewSite.name}
        />
      )}

      <header className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-3xl sm:text-4xl font-black text-white">Чат-платформы</h1>
          <p className="text-zinc-500 text-sm font-medium mt-1">Публичные мессенджеры с несколькими администраторами</p>
        </div>
        <button onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-5 py-3 rounded-2xl text-[10px] font-black uppercase tracking-wider transition-all shadow-lg shadow-blue-600/20">
          <Plus className="w-4 h-4" /> Создать сайт
        </button>
      </header>

      <div className="bg-blue-500/5 border border-blue-500/20 rounded-[2rem] p-5 flex gap-4 items-start">
        <MessageSquare className="w-5 h-5 text-blue-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-white font-black text-sm mb-1">Полноценная платформа поддержки</p>
          <p className="text-zinc-500 text-xs leading-relaxed">Варны, муты, групповой чат, авто-ответы, медиафайлы на диске, голосовые сообщения, аналитика и статусы онлайн.</p>
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
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {sites.map(site => {
            const siteUrl = `${window.location.origin}/chat/${site.slug}`;
            const p = site.config?.primaryColor || '#6366f1';
            return (
              <div key={site.id} className="bg-[#111] border border-zinc-800 rounded-[2.5rem] overflow-hidden hover:border-zinc-700 transition-all group">
                <div className="h-16 flex items-center px-5" style={{ background: site.config?.bgColor || '#09090b' }}>
                  <div className="w-2.5 h-2.5 rounded-full mr-2.5" style={{ background: p }} />
                  <span className="font-black text-sm truncate" style={{ color: p }}>{site.config?.logoText || site.name}</span>
                  <div className="ml-auto flex gap-1.5">
                    {[0,1,2].map(i => <div key={i} className="w-2 h-2 rounded-full bg-white/10" />)}
                  </div>
                </div>
                <div className="p-5">
                  <div className="flex items-start justify-between mb-4">
                    <div className="min-w-0">
                      <h3 className="text-base font-black text-white group-hover:text-blue-400 transition-colors truncate">{site.name}</h3>
                      <a href={siteUrl} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}
                        className="text-[10px] text-zinc-600 hover:text-zinc-400 font-mono transition-colors truncate block max-w-[160px]">
                        /chat/{site.slug}
                      </a>
                    </div>
                    <div className={`w-2.5 h-2.5 rounded-full mt-1.5 shrink-0 ${site.is_active ? 'bg-emerald-500' : 'bg-zinc-600'}`} />
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
