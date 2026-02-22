import React, { useState, useEffect, useRef } from 'react';
import {
  Plus, MessageSquare, Globe, Copy, Check, Trash2, Settings,
  Users, BarChart3, Send, Shield, Eye, EyeOff, ChevronRight,
  ExternalLink, RefreshCw, Ban, Megaphone, X, ArrowLeft,
  Key, Lock, Palette, Type, Zap, Save, Hash, AlertCircle
} from 'lucide-react';
import { User } from '../types';

// ─── Types ────────────────────────────────────────────────────────────────────

interface ChatSiteConfig {
  primaryColor: string;
  bgColor: string;
  fontFamily: string;
  welcomeMessage: string;
  commands: string[];
  logoText: string;
}

interface ChatSite {
  id: string;
  owner_id: string;
  name: string;
  slug: string;
  config: ChatSiteConfig;
  admin_login: string;
  owner_login: string;
  created_at: number;
  is_active: boolean;
}

interface CreatedSiteResult extends ChatSite {
  owner_password_plain: string;
  admin_password_plain: string;
}

interface ChatPlatformProps {
  user: User;
}

const API = '/api';

const FONT_OPTIONS = [
  { value: 'Manrope', label: 'Manrope' },
  { value: 'Inter', label: 'Inter' },
  { value: 'JetBrains Mono', label: 'JetBrains Mono' },
  { value: 'Georgia, serif', label: 'Georgia' },
  { value: 'system-ui', label: 'Системный' },
];

const COLOR_PRESETS = [
  { label: 'Индиго', primary: '#6366f1', bg: '#09090b' },
  { label: 'Синий', primary: '#3b82f6', bg: '#09090b' },
  { label: 'Изумруд', primary: '#10b981', bg: '#061a0f' },
  { label: 'Янтарь', primary: '#f59e0b', bg: '#0a0800' },
  { label: 'Розовый', primary: '#ec4899', bg: '#0d040a' },
  { label: 'Серый', primary: '#71717a', bg: '#09090b' },
];

// ─── Sub-components ───────────────────────────────────────────────────────────

const CopyButton: React.FC<{ value: string; className?: string }> = ({ value, className = '' }) => {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
      className={`p-1.5 rounded-lg transition-all ${copied ? 'bg-emerald-500/20 text-emerald-400' : 'bg-zinc-800 text-zinc-500 hover:text-white'} ${className}`}
      title="Скопировать"
    >
      {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
    </button>
  );
};

// ─── Create Site Modal ────────────────────────────────────────────────────────

const CreateSiteModal: React.FC<{
  onClose: () => void;
  onCreated: (site: CreatedSiteResult) => void;
  userId: string;
}> = ({ onClose, onCreated, userId }) => {
  const [name, setName] = useState('');
  const [adminLogin, setAdminLogin] = useState('');
  const [adminPassword, setAdminPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleCreate = async () => {
    if (!name.trim()) { setError('Введите название'); return; }
    setLoading(true); setError('');
    try {
      const res = await fetch(`${API}/chat/sites`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          owner_id: userId,
          name: name.trim(),
          admin_login: adminLogin.trim() || undefined,
          admin_password: adminPassword.trim() || undefined,
        })
      });
      if (!res.ok) { const d = await res.json(); setError(d.detail || 'Ошибка'); return; }
      const data = await res.json();
      onCreated(data);
    } catch { setError('Ошибка сети'); }
    finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/80 backdrop-blur-md" onClick={onClose} />
      <div className="relative w-full max-w-md bg-[#111] border border-zinc-800 rounded-[2.5rem] p-8 shadow-2xl animate-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h3 className="text-xl font-black text-white">Новый чат-сайт</h3>
            <p className="text-zinc-600 text-xs font-bold uppercase tracking-widest mt-1">Настройка публичного мессенджера</p>
          </div>
          <button onClick={onClose} className="p-2 rounded-xl hover:bg-zinc-800 text-zinc-600 hover:text-white transition-all">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-5">
          <label className="block">
            <span className="text-[10px] font-black text-zinc-500 uppercase tracking-widest block mb-2">Название сайта *</span>
            <input
              value={name} onChange={e => setName(e.target.value)}
              placeholder="Поддержка клиентов"
              className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-4 rounded-2xl outline-none transition-all text-sm"
              autoFocus
            />
          </label>

          <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-4 space-y-4">
            <p className="text-[9px] font-black text-zinc-500 uppercase tracking-widest">Доступ администратора (опционально)</p>
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1.5">Логин</span>
                <input
                  value={adminLogin} onChange={e => setAdminLogin(e.target.value)}
                  placeholder="admin"
                  className="w-full bg-black border border-zinc-800 focus:border-blue-500/50 text-white p-3 rounded-xl outline-none transition-all text-xs"
                />
              </label>
              <label className="block">
                <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-1.5">Пароль</span>
                <input
                  type="password"
                  value={adminPassword} onChange={e => setAdminPassword(e.target.value)}
                  placeholder="Авто"
                  className="w-full bg-black border border-zinc-800 focus:border-blue-500/50 text-white p-3 rounded-xl outline-none transition-all text-xs"
                />
              </label>
            </div>
            <p className="text-[8px] text-zinc-700 leading-relaxed">Если оставить пустым — логин и пароль будут сгенерированы автоматически</p>
          </div>

          {error && (
            <div className="flex items-center gap-2 bg-rose-500/10 border border-rose-500/20 rounded-xl p-3">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
              <span className="text-rose-400 text-xs">{error}</span>
            </div>
          )}
        </div>

        <div className="flex gap-3 mt-8">
          <button onClick={onClose} className="flex-1 py-4 rounded-2xl bg-zinc-800 text-zinc-400 text-[10px] font-black uppercase tracking-wider hover:bg-zinc-700 transition-all">
            Отмена
          </button>
          <button
            onClick={handleCreate} disabled={loading}
            className="flex-1 py-4 rounded-2xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-[10px] font-black uppercase tracking-wider transition-all shadow-lg shadow-blue-600/20 flex items-center justify-center gap-2"
          >
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            {loading ? 'Создание...' : 'Создать'}
          </button>
        </div>
      </div>
    </div>
  );
};

// ─── Credentials Modal (показывается сразу после создания) ───────────────────

const CredsModal: React.FC<{ site: CreatedSiteResult; onClose: () => void }> = ({ site, onClose }) => {
  const rows = [
    { label: 'URL сайта', value: `${window.location.origin}/chat/${site.slug}`, icon: Globe },
    { label: 'Логин владельца', value: site.owner_login, icon: Key },
    { label: 'Пароль владельца', value: site.owner_password_plain, icon: Lock },
    { label: 'Логин администратора', value: site.admin_login, icon: Key },
    { label: 'Пароль администратора', value: site.admin_password_plain, icon: Lock },
  ];

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/90 backdrop-blur-md" />
      <div className="relative w-full max-w-lg bg-[#111] border border-amber-500/30 rounded-[2.5rem] p-8 shadow-2xl animate-in zoom-in-95 duration-200">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
            <Shield className="w-5 h-5 text-amber-400" />
          </div>
          <div>
            <h3 className="text-lg font-black text-white">Сохраните данные доступа</h3>
            <p className="text-amber-400/70 text-[9px] font-black uppercase tracking-widest">Показывается только один раз</p>
          </div>
        </div>

        <div className="mt-6 space-y-3">
          {rows.map(({ label, value, icon: Icon }) => (
            <div key={label} className="flex items-center gap-3 bg-black/50 border border-zinc-800 rounded-2xl px-4 py-3">
              <Icon className="w-3.5 h-3.5 text-zinc-600 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-[8px] text-zinc-600 font-black uppercase tracking-widest">{label}</p>
                <p className="text-white text-xs font-mono mt-0.5 truncate">{value}</p>
              </div>
              <CopyButton value={value} />
            </div>
          ))}
        </div>

        <button
          onClick={onClose}
          className="w-full mt-6 py-4 rounded-2xl bg-amber-500 hover:bg-amber-400 text-black text-[10px] font-black uppercase tracking-wider transition-all"
        >
          Я сохранил данные
        </button>
      </div>
    </div>
  );
};

// ─── Site Editor ──────────────────────────────────────────────────────────────

const SiteEditor: React.FC<{
  site: ChatSite;
  userId: string;
  onBack: () => void;
  onUpdated: (s: ChatSite) => void;
}> = ({ site, userId, onBack, onUpdated }) => {
  const [config, setConfig] = useState<ChatSiteConfig>({ ...site.config });
  const [name, setName] = useState(site.name);
  const [adminLogin, setAdminLogin] = useState(site.admin_login || '');
  const [adminPassword, setAdminPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [commandInput, setCommandInput] = useState('');
  const [stats, setStats] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [tab, setTab] = useState<'design' | 'access' | 'users' | 'broadcast'>('design');
  const [broadcastText, setBroadcastText] = useState('');
  const [broadcasting, setBroadcasting] = useState(false);
  const [broadcastDone, setBroadcastDone] = useState(false);

  useEffect(() => {
    // Загружаем статистику и пользователей
    const slug = site.slug;
    fetch(`${API}/chat/site/${slug}/stats?role=owner`)
      .then(r => r.json()).then(setStats).catch(() => {});
    fetch(`${API}/chat/site/${slug}/users?role=owner`)
      .then(r => r.json()).then(setUsers).catch(() => {});
  }, [site.slug]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const body: any = { owner_id: userId, name, config };
      if (adminLogin) body.admin_login = adminLogin;
      if (adminPassword) body.admin_password = adminPassword;

      await fetch(`${API}/chat/sites/${site.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      onUpdated({ ...site, name, config, admin_login: adminLogin });
      setSaved(true); setTimeout(() => setSaved(false), 2000);
    } catch { alert('Ошибка сохранения'); }
    finally { setSaving(false); }
  };

  const addCommand = () => {
    const cmd = commandInput.trim();
    if (!cmd) return;
    const norm = cmd.startsWith('/') ? cmd : `/${cmd}`;
    setConfig(c => ({ ...c, commands: [...(c.commands || []), norm] }));
    setCommandInput('');
  };

  const removeCommand = (i: number) => {
    setConfig(c => ({ ...c, commands: c.commands.filter((_, idx) => idx !== i) }));
  };

  const handleBan = async (userId: string, isBanned: boolean) => {
    await fetch(`${API}/chat/site/${site.slug}/users/${userId}/ban`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: 'owner', is_banned: isBanned })
    });
    setUsers(prev => prev.map(u => u.id === userId ? { ...u, is_banned: isBanned } : u));
  };

  const handleBroadcast = async () => {
    if (!broadcastText.trim()) return;
    setBroadcasting(true);
    await fetch(`${API}/chat/site/${site.slug}/broadcast`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: 'owner', from_id: `owner_${site.id}`, from_name: 'Администрация', text: broadcastText })
    });
    setBroadcasting(false);
    setBroadcastDone(true);
    setBroadcastText('');
    setTimeout(() => setBroadcastDone(false), 3000);
  };

  const TABS = [
    { id: 'design', label: 'Внешний вид', icon: Palette },
    { id: 'access', label: 'Доступ', icon: Key },
    { id: 'users', label: `Пользователи${users.length ? ` (${users.length})` : ''}`, icon: Users },
    { id: 'broadcast', label: 'Рассылка', icon: Megaphone },
  ] as const;

  const siteUrl = `${window.location.origin}/chat/${site.slug}`;

  return (
    <div className="animate-in fade-in duration-300 space-y-6">
      {/* Шапка */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-4">
          <button onClick={onBack} className="flex items-center gap-2 text-zinc-500 hover:text-white text-[10px] font-black uppercase tracking-widest transition-colors group">
            <ArrowLeft className="w-3.5 h-3.5 group-hover:-translate-x-1 transition-transform" /> Все сайты
          </button>
          <div className="h-4 w-px bg-zinc-800" />
          <div>
            <h2 className="text-xl font-black text-white">{site.name}</h2>
            <div className="flex items-center gap-2 mt-0.5">
              <a href={siteUrl} target="_blank" rel="noopener noreferrer" className="text-blue-400 text-xs hover:underline font-mono">{siteUrl}</a>
              <CopyButton value={siteUrl} />
              <a href={siteUrl} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="w-3 h-3 text-zinc-600 hover:text-white transition-colors" />
              </a>
            </div>
          </div>
        </div>
        <button
          onClick={handleSave} disabled={saving}
          className={`flex items-center gap-2 px-6 py-3 rounded-2xl text-[10px] font-black uppercase tracking-wider transition-all shadow-lg ${saved ? 'bg-emerald-600 shadow-emerald-600/20 text-white' : 'bg-blue-600 hover:bg-blue-500 shadow-blue-600/20 text-white'}`}
        >
          {saved ? <Check className="w-4 h-4" /> : <Save className="w-4 h-4" />}
          {saved ? 'Сохранено' : saving ? '...' : 'Сохранить'}
        </button>
      </div>

      {/* Статистика */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Пользователей', value: stats.total_users, color: 'text-white' },
            { label: 'Активны 24ч', value: stats.active_24h, color: 'text-blue-400' },
            { label: 'Сообщений', value: stats.total_messages, color: 'text-white' },
            { label: 'Непрочитано', value: stats.unread, color: 'text-amber-400' },
          ].map(s => (
            <div key={s.label} className="bg-[#111] border border-zinc-800 rounded-[1.5rem] p-5">
              <p className="text-[8px] font-black text-zinc-600 uppercase tracking-widest mb-2">{s.label}</p>
              <p className={`text-3xl font-black ${s.color}`}>{s.value ?? '—'}</p>
            </div>
          ))}
        </div>
      )}

      {/* Табы */}
      <div className="flex gap-1 border-b border-zinc-800">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id as any)}
            className={`flex items-center gap-1.5 px-4 py-3 text-[10px] font-black uppercase tracking-widest border-b-2 transition-all whitespace-nowrap ${tab === t.id ? 'border-blue-500 text-blue-400' : 'border-transparent text-zinc-600 hover:text-zinc-300'}`}>
            <t.icon className="w-3.5 h-3.5" />{t.label}
          </button>
        ))}
      </div>

      {/* ── Внешний вид ── */}
      {tab === 'design' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6 space-y-5">
            <h3 className="text-[10px] font-black text-zinc-500 uppercase tracking-widest flex items-center gap-2">
              <Type className="w-3.5 h-3.5" /> Текст
            </h3>
            <label className="block">
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Название сайта</span>
              <input value={name} onChange={e => setName(e.target.value)}
                className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-3.5 rounded-xl outline-none transition-all text-sm" />
            </label>
            <label className="block">
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Текст лого</span>
              <input value={config.logoText || ''} onChange={e => setConfig(c => ({ ...c, logoText: e.target.value }))}
                className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-3.5 rounded-xl outline-none transition-all text-sm" />
            </label>
            <label className="block">
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Приветственное сообщение</span>
              <textarea value={config.welcomeMessage} onChange={e => setConfig(c => ({ ...c, welcomeMessage: e.target.value }))}
                rows={3}
                className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-3.5 rounded-xl outline-none transition-all text-sm resize-none" />
            </label>
            <label className="block">
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Шрифт</span>
              <select value={config.fontFamily} onChange={e => setConfig(c => ({ ...c, fontFamily: e.target.value }))}
                className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-3.5 rounded-xl outline-none transition-all text-sm cursor-pointer">
                {FONT_OPTIONS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
              </select>
            </label>
          </div>

          <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6 space-y-5">
            <h3 className="text-[10px] font-black text-zinc-500 uppercase tracking-widest flex items-center gap-2">
              <Palette className="w-3.5 h-3.5" /> Оформление
            </h3>
            <div>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-3">Готовые темы</span>
              <div className="grid grid-cols-3 gap-2">
                {COLOR_PRESETS.map(p => (
                  <button key={p.label}
                    onClick={() => setConfig(c => ({ ...c, primaryColor: p.primary, bgColor: p.bg }))}
                    style={{ background: p.bg, borderColor: config.primaryColor === p.primary ? p.primary : 'transparent' }}
                    className="border-2 rounded-xl p-3 transition-all hover:scale-105">
                    <div className="w-full h-3 rounded-full mb-1.5" style={{ background: p.primary }} />
                    <span className="text-[9px] font-black uppercase" style={{ color: p.primary }}>{p.label}</span>
                  </button>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <label className="block">
                <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Акцентный цвет</span>
                <div className="flex gap-2">
                  <input type="color" value={config.primaryColor} onChange={e => setConfig(c => ({ ...c, primaryColor: e.target.value }))}
                    className="w-10 h-10 rounded-xl border border-zinc-800 bg-black cursor-pointer p-0.5 shrink-0" />
                  <input value={config.primaryColor} onChange={e => setConfig(c => ({ ...c, primaryColor: e.target.value }))}
                    className="flex-1 bg-black border border-zinc-800 text-white text-xs p-2.5 rounded-xl outline-none focus:border-blue-500 transition-all font-mono" />
                </div>
              </label>
              <label className="block">
                <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Фон</span>
                <div className="flex gap-2">
                  <input type="color" value={config.bgColor} onChange={e => setConfig(c => ({ ...c, bgColor: e.target.value }))}
                    className="w-10 h-10 rounded-xl border border-zinc-800 bg-black cursor-pointer p-0.5 shrink-0" />
                  <input value={config.bgColor} onChange={e => setConfig(c => ({ ...c, bgColor: e.target.value }))}
                    className="flex-1 bg-black border border-zinc-800 text-white text-xs p-2.5 rounded-xl outline-none focus:border-blue-500 transition-all font-mono" />
                </div>
              </label>
            </div>

            {/* Команды */}
            <div>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2 flex items-center gap-1.5">
                <Zap className="w-3 h-3" /> Быстрые команды (подсказки)
              </span>
              <div className="flex gap-2 mb-2">
                <input value={commandInput} onChange={e => setCommandInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addCommand()}
                  placeholder="/помощь"
                  className="flex-1 bg-black border border-zinc-800 focus:border-blue-500/50 text-white text-xs p-2.5 rounded-xl outline-none transition-all" />
                <button onClick={addCommand} className="px-4 py-2 bg-blue-600/20 border border-blue-500/30 text-blue-400 rounded-xl text-xs font-bold hover:bg-blue-600/30 transition-all">
                  <Plus className="w-4 h-4" />
                </button>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {(config.commands || []).map((cmd, i) => (
                  <span key={i} className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 rounded-lg px-2.5 py-1 text-[10px] font-mono text-zinc-300">
                    {cmd}
                    <button onClick={() => removeCommand(i)} className="text-zinc-600 hover:text-rose-400 transition-colors ml-0.5">
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
                {!(config.commands || []).length && <span className="text-[9px] text-zinc-700">Нет команд</span>}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Доступ ── */}
      {tab === 'access' && (
        <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6 space-y-6 max-w-2xl">
          <h3 className="text-[10px] font-black text-zinc-500 uppercase tracking-widest flex items-center gap-2">
            <Key className="w-3.5 h-3.5" /> Данные администратора
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <label className="block">
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Логин</span>
              <input value={adminLogin} onChange={e => setAdminLogin(e.target.value)}
                className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-3.5 rounded-xl outline-none transition-all text-sm" />
            </label>
            <label className="block">
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest block mb-2">Новый пароль</span>
              <input type="password" value={adminPassword} onChange={e => setAdminPassword(e.target.value)}
                placeholder="Оставьте пустым чтобы не менять"
                className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-3.5 rounded-xl outline-none transition-all text-sm" />
            </label>
          </div>
          <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-4">
            <p className="text-[9px] font-black text-zinc-500 uppercase tracking-widest mb-3">Ссылки для входа</p>
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <span className="text-[9px] text-zinc-600 uppercase font-bold w-24 shrink-0">Пользователь</span>
                <code className="text-xs text-zinc-400 font-mono flex-1 truncate">{siteUrl}</code>
                <CopyButton value={siteUrl} />
              </div>
              <div className="flex items-center gap-3">
                <span className="text-[9px] text-zinc-600 uppercase font-bold w-24 shrink-0">Администратор</span>
                <code className="text-xs text-zinc-400 font-mono flex-1 truncate">{siteUrl}?as=admin</code>
                <CopyButton value={`${siteUrl}?as=admin`} />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Пользователи ── */}
      {tab === 'users' && (
        <div className="bg-[#111] border border-zinc-800 rounded-[2rem] overflow-hidden">
          <div className="p-6 border-b border-zinc-800">
            <h3 className="text-[10px] font-black text-zinc-500 uppercase tracking-widest">Зарегистрированные пользователи</h3>
          </div>
          {users.length === 0 ? (
            <div className="p-12 text-center">
              <Users className="w-10 h-10 text-zinc-800 mx-auto mb-3" />
              <p className="text-zinc-600 text-sm font-bold">Нет пользователей</p>
            </div>
          ) : (
            <div className="divide-y divide-zinc-900">
              {users.map(u => (
                <div key={u.id} className="flex items-center gap-4 px-6 py-4 hover:bg-zinc-900/30 transition-all">
                  <div className="w-8 h-8 rounded-xl bg-zinc-800 flex items-center justify-center text-zinc-400 font-black text-xs shrink-0">
                    {u.username[0].toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm font-bold truncate ${u.is_banned ? 'text-zinc-600 line-through' : 'text-white'}`}>{u.username}</p>
                    <p className="text-[9px] text-zinc-600 font-bold">
                      Последнее посещение: {u.last_seen ? new Date(u.last_seen).toLocaleDateString('ru') : '—'}
                    </p>
                  </div>
                  {u.is_banned && (
                    <span className="text-[8px] font-black uppercase tracking-wider text-rose-400 bg-rose-500/10 border border-rose-500/20 px-2 py-1 rounded-lg">Заблокирован</span>
                  )}
                  <button
                    onClick={() => handleBan(u.id, !u.is_banned)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[9px] font-black uppercase tracking-wider transition-all ${u.is_banned ? 'bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 border border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 border border-rose-500/20'}`}
                  >
                    <Ban className="w-3 h-3" />
                    {u.is_banned ? 'Разблокировать' : 'Заблокировать'}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Рассылка ── */}
      {tab === 'broadcast' && (
        <div className="bg-[#111] border border-zinc-800 rounded-[2rem] p-6 max-w-2xl space-y-5">
          <h3 className="text-[10px] font-black text-zinc-500 uppercase tracking-widest flex items-center gap-2">
            <Megaphone className="w-3.5 h-3.5" /> Рассылка всем пользователям
          </h3>
          <textarea
            value={broadcastText} onChange={e => setBroadcastText(e.target.value)}
            placeholder="Текст сообщения для всех пользователей сайта..."
            rows={5}
            className="w-full bg-black border border-zinc-800 focus:border-blue-500 text-white p-4 rounded-2xl outline-none transition-all text-sm resize-none"
          />
          <div className="flex items-center justify-between">
            <p className="text-[9px] text-zinc-600 font-bold">Сообщение получат все зарегистрированные пользователи</p>
            <button
              onClick={handleBroadcast}
              disabled={broadcasting || !broadcastText.trim()}
              className={`flex items-center gap-2 px-6 py-3 rounded-2xl text-[10px] font-black uppercase tracking-wider transition-all disabled:opacity-40 shadow-lg ${broadcastDone ? 'bg-emerald-600 shadow-emerald-600/20 text-white' : 'bg-blue-600 hover:bg-blue-500 shadow-blue-600/20 text-white'}`}
            >
              {broadcastDone ? <Check className="w-4 h-4" /> : <Send className="w-4 h-4" />}
              {broadcastDone ? 'Отправлено' : broadcasting ? '...' : 'Отправить'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

// ─── Main Component ───────────────────────────────────────────────────────────

const ChatPlatform: React.FC<ChatPlatformProps> = ({ user }) => {
  const [sites, setSites] = useState<ChatSite[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [createdSite, setCreatedSite] = useState<CreatedSiteResult | null>(null);
  const [editingSite, setEditingSite] = useState<ChatSite | null>(null);

  const loadSites = async () => {
    try {
      const res = await fetch(`${API}/chat/sites/owner/${user.id}`);
      const data = await res.json();
      setSites(Array.isArray(data) ? data : []);
    } catch { setSites([]); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadSites(); }, [user.id]);

  const handleCreated = (site: CreatedSiteResult) => {
    setSites(prev => [site, ...prev]);
    setShowCreate(false);
    setCreatedSite(site);
  };

  const handleDelete = async (siteId: string) => {
    if (!window.confirm('Удалить чат-сайт? Все данные будут утеряны.')) return;
    await fetch(`${API}/chat/sites/${siteId}?owner_id=${user.id}`, { method: 'DELETE' });
    setSites(prev => prev.filter(s => s.id !== siteId));
    if (editingSite?.id === siteId) setEditingSite(null);
  };

  if (editingSite) {
    return (
      <SiteEditor
        site={editingSite}
        userId={user.id}
        onBack={() => setEditingSite(null)}
        onUpdated={updated => {
          setSites(prev => prev.map(s => s.id === updated.id ? updated : s));
          setEditingSite(updated);
        }}
      />
    );
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {showCreate && (
        <CreateSiteModal
          onClose={() => setShowCreate(false)}
          onCreated={handleCreated}
          userId={user.id}
        />
      )}
      {createdSite && (
        <CredsModal site={createdSite} onClose={() => setCreatedSite(null)} />
      )}

      <header className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-4xl font-black text-white">Чат-платформы</h1>
          <p className="text-zinc-500 text-sm font-medium mt-1">Публичные мессенджеры для вашего бизнеса</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-6 py-3.5 rounded-2xl text-[10px] font-black uppercase tracking-wider transition-all shadow-lg shadow-blue-600/20"
        >
          <Plus className="w-4 h-4" /> Создать сайт
        </button>
      </header>

      {/* Инфо-блок */}
      <div className="bg-blue-500/5 border border-blue-500/20 rounded-[2rem] p-6 flex gap-4 items-start">
        <div className="w-8 h-8 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center shrink-0 mt-0.5">
          <MessageSquare className="w-4 h-4 text-blue-400" />
        </div>
        <div>
          <p className="text-white font-black text-sm mb-1">Собственная платформа поддержки</p>
          <p className="text-zinc-500 text-xs leading-relaxed">
            Создайте публичный чат-сайт с уникальным URL. Пользователи регистрируются и пишут вам — администратор отвечает через тот же интерфейс. Владелец управляет всем через суперпанель.
          </p>
        </div>
      </div>

      {/* Список сайтов */}
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
            return (
              <div key={site.id}
                className="bg-[#111] border border-zinc-800 rounded-[2.5rem] overflow-hidden hover:border-zinc-700 transition-all group">
                {/* Превью шапки */}
                <div
                  className="h-20 relative flex items-center px-6"
                  style={{ background: site.config?.bgColor || '#09090b' }}>
                  <div className="w-2 h-2 rounded-full mr-2" style={{ background: site.config?.primaryColor || '#6366f1' }} />
                  <span className="font-black text-sm" style={{ color: site.config?.primaryColor || '#6366f1', fontFamily: site.config?.fontFamily }}>
                    {site.config?.logoText || site.name}
                  </span>
                  <div className="ml-auto flex gap-1.5">
                    {[0, 1, 2].map(i => (
                      <div key={i} className="w-2 h-2 rounded-full bg-white/10" />
                    ))}
                  </div>
                </div>

                <div className="p-6">
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <h3 className="text-lg font-black text-white group-hover:text-blue-400 transition-colors">{site.name}</h3>
                      <a href={siteUrl} target="_blank" rel="noopener noreferrer"
                        className="text-[10px] text-zinc-600 hover:text-zinc-400 font-mono transition-colors truncate block max-w-[180px]" onClick={e => e.stopPropagation()}>
                        /chat/{site.slug}
                      </a>
                    </div>
                    <div className={`w-2.5 h-2.5 rounded-full mt-1.5 ${site.is_active ? 'bg-emerald-500' : 'bg-zinc-600'}`} />
                  </div>

                  <div className="flex gap-2 mt-4">
                    <button onClick={() => setEditingSite(site)}
                      className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white text-[9px] font-black uppercase tracking-wider transition-all">
                      <Settings className="w-3 h-3" /> Настройки
                    </button>
                    <a href={siteUrl} target="_blank" rel="noopener noreferrer"
                      className="py-2.5 px-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white transition-all flex items-center justify-center"
                      onClick={e => e.stopPropagation()}>
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                    <button onClick={() => handleDelete(site.id)}
                      className="py-2.5 px-3 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-500 transition-all">
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
