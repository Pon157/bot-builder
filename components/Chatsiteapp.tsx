import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import {
  Send, Users, LogOut, Ban, Megaphone, RefreshCw,
  MessageCircle, Lock, UserPlus, ChevronRight, Check,
  BarChart3, X, Shield, Hash, AlertCircle
} from 'lucide-react';

// ─── Types ─────────────────────────────────────────────────────────────────────

interface SiteConfig {
  primaryColor: string;
  bgColor: string;
  fontFamily: string;
  welcomeMessage: string;
  commands: string[];
  logoText: string;
}

interface PublicSite {
  id: string;
  name: string;
  slug: string;
  config: SiteConfig;
  admin_login: string;
}

interface ChatSession {
  id: string;
  username: string;
  site_id: string;
  role: 'user' | 'admin' | 'owner';
  token: string;
}

interface Message {
  id: string;
  site_id: string;
  from_id: string;
  from_name: string;
  from_role: 'user' | 'admin' | 'owner';
  to_user_id: string | null;
  text: string;
  created_at: number;
  is_read: boolean;
}

interface SiteUser {
  id: string;
  username: string;
  is_banned: boolean;
  last_seen: number;
  created_at: number;
}

interface Stats {
  total_users: number;
  banned_users: number;
  active_24h: number;
  total_messages: number;
  user_messages: number;
  admin_messages: number;
  unread: number;
}

const API = '/api';
const POLL_INTERVAL = 2500;

// ─── Helpers ───────────────────────────────────────────────────────────────────

const fmt = (ts: number) => {
  const d = new Date(ts);
  return d.toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' });
};

const fmtDate = (ts: number) => {
  const d = new Date(ts);
  return d.toLocaleDateString('ru', { day: 'numeric', month: 'short' });
};

const isToday = (ts: number) => {
  const d = new Date(ts);
  const now = new Date();
  return d.getDate() === now.getDate() && d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
};

// ─── Auth Screen ────────────────────────────────────────────────────────────────

const AuthScreen: React.FC<{
  site: PublicSite;
  defaultMode?: 'login' | 'register';
  onAuth: (session: ChatSession) => void;
}> = ({ site, defaultMode = 'login', onAuth }) => {
  const cfg = site.config;
  const [mode, setMode] = useState<'login' | 'register'>(defaultMode);
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const primary = cfg.primaryColor || '#6366f1';
  const bg = cfg.bgColor || '#09090b';
  const font = cfg.fontFamily || 'Manrope';

  const handleSubmit = async () => {
    if (!login.trim() || !password.trim()) { setError('Заполните все поля'); return; }
    setLoading(true); setError('');

    try {
      if (mode === 'register') {
        const res = await fetch(`${API}/chat/site/${site.slug}/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: login.trim(), password: password.trim() })
        });
        const data = await res.json();
        if (!res.ok) { setError(data.detail || 'Ошибка регистрации'); return; }
        onAuth(data);
      } else {
        const res = await fetch(`${API}/chat/site/${site.slug}/auth`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ login: login.trim(), password: password.trim() })
        });
        const data = await res.json();
        if (!res.ok) { setError(data.detail || 'Неверный логин или пароль'); return; }
        onAuth(data);
      }
    } catch { setError('Ошибка сети. Попробуйте ещё раз.'); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4"
      style={{ background: bg, fontFamily: font }}>

      {/* Лого */}
      <div className="mb-10 text-center">
        <div className="inline-flex items-center gap-2.5 mb-3">
          <div className="w-3 h-3 rounded-full" style={{ background: primary }} />
          <span className="text-2xl font-black" style={{ color: primary }}>{cfg.logoText || site.name}</span>
        </div>
        <p className="text-sm" style={{ color: primary + '80' }}>{cfg.welcomeMessage || 'Чем можем помочь?'}</p>
      </div>

      {/* Карточка */}
      <div className="w-full max-w-sm bg-white/5 border rounded-[2.5rem] p-8 backdrop-blur-sm"
        style={{ borderColor: primary + '30' }}>

        {/* Переключатель режимов (только для обычных пользователей) */}
        <div className="flex rounded-2xl overflow-hidden border mb-8" style={{ borderColor: primary + '20' }}>
          {(['login', 'register'] as const).map(m => (
            <button key={m} onClick={() => { setMode(m); setError(''); }}
              className="flex-1 py-3 text-[10px] font-black uppercase tracking-widest transition-all"
              style={{ background: mode === m ? primary : 'transparent', color: mode === m ? '#fff' : primary + '80' }}>
              {m === 'login' ? 'Войти' : 'Регистрация'}
            </button>
          ))}
        </div>

        <div className="space-y-4">
          <div>
            <label className="text-[9px] font-black uppercase tracking-widest block mb-2" style={{ color: primary + '80' }}>
              {mode === 'register' ? 'Имя пользователя' : 'Логин'}
            </label>
            <input
              value={login} onChange={e => setLogin(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSubmit()}
              placeholder={mode === 'register' ? 'Иван' : 'Введите логин'}
              className="w-full bg-white/5 border text-white p-4 rounded-2xl outline-none transition-all text-sm placeholder-white/20"
              style={{ borderColor: primary + '30' }}
              autoFocus
            />
          </div>
          <div>
            <label className="text-[9px] font-black uppercase tracking-widest block mb-2" style={{ color: primary + '80' }}>Пароль</label>
            <input
              type="password" value={password} onChange={e => setPassword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSubmit()}
              placeholder="••••••••"
              className="w-full bg-white/5 border text-white p-4 rounded-2xl outline-none transition-all text-sm placeholder-white/20"
              style={{ borderColor: primary + '30' }}
            />
          </div>

          {error && (
            <div className="flex items-center gap-2 bg-red-500/10 border border-red-500/20 rounded-xl p-3">
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
              <span className="text-red-400 text-xs">{error}</span>
            </div>
          )}

          <button
            onClick={handleSubmit} disabled={loading}
            className="w-full py-4 rounded-2xl font-black text-[10px] uppercase tracking-widest transition-all disabled:opacity-50 flex items-center justify-center gap-2 mt-2"
            style={{ background: primary, color: '#fff', boxShadow: `0 8px 24px ${primary}40` }}>
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : mode === 'login' ? <ChevronRight className="w-4 h-4" /> : <UserPlus className="w-4 h-4" />}
            {loading ? 'Подождите...' : mode === 'login' ? 'Войти' : 'Зарегистрироваться'}
          </button>
        </div>
      </div>

      <p className="mt-6 text-[9px] font-bold uppercase tracking-wider" style={{ color: primary + '40' }}>
        Powered by ChatPlatform
      </p>
    </div>
  );
};

// ─── Message Bubble ─────────────────────────────────────────────────────────────

const MessageBubble: React.FC<{
  msg: Message;
  session: ChatSession;
  primary: string;
  isAdmin?: boolean;
}> = ({ msg, session, primary, isAdmin }) => {
  const isOwn = msg.from_id === session.id;
  const isFromAdmin = msg.from_role === 'admin' || msg.from_role === 'owner';
  const isBroadcast = msg.to_user_id === null && isFromAdmin;

  if (isBroadcast && !isAdmin) {
    return (
      <div className="flex justify-center my-2">
        <div className="flex items-center gap-2 bg-white/5 border border-white/10 rounded-2xl px-4 py-2 max-w-xs">
          <Megaphone className="w-3 h-3 shrink-0" style={{ color: primary }} />
          <div>
            <p className="text-[8px] font-black uppercase tracking-wider mb-0.5" style={{ color: primary }}>Объявление</p>
            <p className="text-xs text-white/80">{msg.text}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex gap-3 mb-3 ${isOwn ? 'flex-row-reverse' : 'flex-row'}`}>
      {/* Аватар */}
      {!isOwn && (
        <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 font-black text-xs text-white/60"
          style={{ background: isFromAdmin ? primary + '30' : '#ffffff15' }}>
          {isFromAdmin ? 'A' : msg.from_name[0]?.toUpperCase()}
        </div>
      )}

      <div className={`max-w-[72%] ${isOwn ? 'items-end' : 'items-start'} flex flex-col gap-1`}>
        {!isOwn && (
          <span className="text-[9px] font-black uppercase tracking-wider px-1" style={{ color: isFromAdmin ? primary : 'rgba(255,255,255,0.4)' }}>
            {isFromAdmin ? 'Администратор' : msg.from_name}
          </span>
        )}

        <div className="px-4 py-3 rounded-[1.5rem] text-sm leading-relaxed"
          style={{
            background: isOwn ? primary : isFromAdmin ? primary + '20' : 'rgba(255,255,255,0.08)',
            color: isOwn ? '#fff' : 'rgba(255,255,255,0.9)',
            borderBottomRightRadius: isOwn ? '6px' : undefined,
            borderBottomLeftRadius: !isOwn ? '6px' : undefined,
          }}>
          {msg.text}
        </div>

        <span className="text-[9px] px-1" style={{ color: 'rgba(255,255,255,0.25)' }}>
          {fmt(msg.created_at)}
        </span>
      </div>
    </div>
  );
};

// ─── User Chat View ─────────────────────────────────────────────────────────────

const UserChat: React.FC<{
  site: PublicSite;
  session: ChatSession;
  onLogout: () => void;
}> = ({ site, session, onLogout }) => {
  const cfg = site.config;
  const primary = cfg.primaryColor || '#6366f1';
  const bg = cfg.bgColor || '#09090b';
  const font = cfg.fontFamily || 'Manrope';

  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [lastTs, setLastTs] = useState(0);
  const [showCommands, setShowCommands] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const fetchMessages = useCallback(async () => {
    try {
      const res = await fetch(`${API}/chat/site/${site.slug}/messages?role=${session.role}&user_id=${session.id}&since=${lastTs}`);
      const data: Message[] = await res.json();
      if (data.length > 0) {
        setMessages(prev => {
          const ids = new Set(prev.map(m => m.id));
          const fresh = data.filter(m => !ids.has(m.id));
          return fresh.length ? [...prev, ...fresh] : prev;
        });
        setLastTs(Math.max(...data.map(m => m.created_at)));
      }
    } catch { /* сетевая ошибка — игнорируем, следующий поллинг повторит */ }
  }, [site.slug, session.id, session.role, lastTs]);

  // Первая загрузка + поллинг
  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(`${API}/chat/site/${site.slug}/messages?role=${session.role}&user_id=${session.id}&since=0`);
        const data: Message[] = await res.json();
        if (data.length) {
          setMessages(data);
          setLastTs(Math.max(...data.map(m => m.created_at)));
        }
      } catch { }
    };
    load();
    const interval = setInterval(fetchMessages, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    const t = text.trim();
    if (!t || sending) return;
    setSending(true);
    setText('');
    setShowCommands(false);
    try {
      const res = await fetch(`${API}/chat/site/${site.slug}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          from_id: session.id,
          from_name: session.username,
          from_role: session.role,
          text: t,
        })
      });
      const msg: Message = await res.json();
      setMessages(prev => [...prev, msg]);
      setLastTs(msg.created_at);
    } catch { setText(t); }
    finally { setSending(false); inputRef.current?.focus(); }
  };

  const commands = cfg.commands || [];
  const filteredCommands = text.startsWith('/')
    ? commands.filter(c => c.startsWith(text))
    : commands;

  return (
    <div className="flex flex-col h-screen" style={{ background: bg, fontFamily: font }}>
      {/* Шапка */}
      <div className="flex items-center justify-between px-5 py-4 border-b"
        style={{ borderColor: primary + '20', background: bg + 'ee' }}>
        <div className="flex items-center gap-3">
          <div className="w-3 h-3 rounded-full" style={{ background: primary }} />
          <div>
            <span className="font-black text-white text-base">{cfg.logoText || site.name}</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-xs" style={{ color: primary + '80' }}>
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            <span className="font-bold text-[10px] uppercase tracking-wider">{session.username}</span>
          </div>
          <button onClick={onLogout} className="p-2 rounded-xl hover:bg-white/5 transition-colors text-white/30 hover:text-white/70">
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Сообщения */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-0.5 no-scrollbar">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-3 opacity-50">
            <MessageCircle className="w-12 h-12" style={{ color: primary + '60' }} />
            <p className="text-sm font-bold" style={{ color: primary + '80' }}>Напишите первое сообщение</p>
          </div>
        )}

        {messages.map((msg, i) => {
          const prevMsg = messages[i - 1];
          const showDate = !prevMsg || !isToday(msg.created_at) !== !isToday(prevMsg.created_at) ||
            new Date(msg.created_at).getDate() !== new Date(prevMsg?.created_at || 0).getDate();
          return (
            <React.Fragment key={msg.id}>
              {showDate && (
                <div className="text-center py-3">
                  <span className="text-[9px] font-black uppercase tracking-widest px-3 py-1 rounded-full"
                    style={{ color: primary + '60', background: primary + '10' }}>
                    {isToday(msg.created_at) ? 'Сегодня' : fmtDate(msg.created_at)}
                  </span>
                </div>
              )}
              <MessageBubble msg={msg} session={session} primary={primary} />
            </React.Fragment>
          );
        })}
        <div ref={bottomRef} />
      </div>

      {/* Команды-подсказки */}
      {showCommands && filteredCommands.length > 0 && (
        <div className="mx-4 mb-1 border rounded-2xl overflow-hidden"
          style={{ borderColor: primary + '30', background: bg }}>
          {filteredCommands.map(cmd => (
            <button key={cmd} onClick={() => { setText(cmd + ' '); setShowCommands(false); inputRef.current?.focus(); }}
              className="flex items-center gap-2 w-full px-4 py-2.5 hover:bg-white/5 transition-colors text-left">
              <Hash className="w-3 h-3" style={{ color: primary }} />
              <span className="text-xs font-mono" style={{ color: primary }}>{cmd}</span>
            </button>
          ))}
        </div>
      )}

      {/* Ввод */}
      <div className="p-4 border-t" style={{ borderColor: primary + '15' }}>
        <div className="flex gap-3 items-end">
          <div className="flex-1 relative">
            <input
              ref={inputRef}
              value={text}
              onChange={e => { setText(e.target.value); setShowCommands(e.target.value.startsWith('/')); }}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } if (e.key === 'Escape') setShowCommands(false); }}
              placeholder={cfg.welcomeMessage || 'Напишите сообщение...'}
              className="w-full px-5 py-3.5 rounded-[1.5rem] text-sm text-white placeholder-white/20 outline-none transition-all pr-4"
              style={{ background: 'rgba(255,255,255,0.06)', border: `1.5px solid ${primary}30`, caretColor: primary }}
            />
          </div>
          <button
            onClick={handleSend}
            disabled={!text.trim() || sending}
            className="w-11 h-11 rounded-[1rem] flex items-center justify-center transition-all disabled:opacity-30 shrink-0"
            style={{ background: primary, boxShadow: `0 4px 16px ${primary}50` }}>
            {sending ? <RefreshCw className="w-4 h-4 text-white animate-spin" /> : <Send className="w-4 h-4 text-white" />}
          </button>
        </div>
      </div>
    </div>
  );
};

// ─── Admin Panel View ───────────────────────────────────────────────────────────

const AdminPanel: React.FC<{
  site: PublicSite;
  session: ChatSession;
  onLogout: () => void;
}> = ({ site, session, onLogout }) => {
  const cfg = site.config;
  const primary = cfg.primaryColor || '#6366f1';
  const bg = cfg.bgColor || '#09090b';
  const font = cfg.fontFamily || 'Manrope';

  const [allMessages, setAllMessages] = useState<Message[]>([]);
  const [users, setUsers] = useState<SiteUser[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [selectedUser, setSelectedUser] = useState<SiteUser | null>(null);
  const [replyText, setReplyText] = useState('');
  const [broadcastText, setBroadcastText] = useState('');
  const [tab, setTab] = useState<'chat' | 'users' | 'broadcast' | 'stats'>('chat');
  const [sending, setSending] = useState(false);
  const [lastTs, setLastTs] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);

  const fetchAll = useCallback(async () => {
    try {
      const [msgsRes, usersRes, statsRes] = await Promise.all([
        fetch(`${API}/chat/site/${site.slug}/messages?role=${session.role}&user_id=${session.id}&since=${lastTs}`),
        fetch(`${API}/chat/site/${site.slug}/users?role=${session.role}`),
        fetch(`${API}/chat/site/${site.slug}/stats?role=${session.role}`)
      ]);
      const msgs: Message[] = await msgsRes.json();
      const usrs: SiteUser[] = await usersRes.json();
      const st = await statsRes.json();

      if (msgs.length) {
        setAllMessages(prev => {
          const ids = new Set(prev.map(m => m.id));
          const fresh = msgs.filter(m => !ids.has(m.id));
          return fresh.length ? [...prev, ...fresh] : prev;
        });
        setLastTs(Math.max(...msgs.map(m => m.created_at)));
      }
      setUsers(Array.isArray(usrs) ? usrs : []);
      if (st && !st.detail) setStats(st);
    } catch { }
  }, [site.slug, session.role, session.id, lastTs]);

  useEffect(() => {
    const init = async () => {
      try {
        const [msgsRes, usersRes, statsRes] = await Promise.all([
          fetch(`${API}/chat/site/${site.slug}/messages?role=${session.role}&user_id=${session.id}&since=0`),
          fetch(`${API}/chat/site/${site.slug}/users?role=${session.role}`),
          fetch(`${API}/chat/site/${site.slug}/stats?role=${session.role}`)
        ]);
        const msgs: Message[] = await msgsRes.json();
        const usrs: SiteUser[] = await usersRes.json();
        const st = await statsRes.json();
        setAllMessages(Array.isArray(msgs) ? msgs : []);
        setUsers(Array.isArray(usrs) ? usrs : []);
        if (st && !st.detail) setStats(st);
        if (msgs.length) setLastTs(Math.max(...msgs.map((m: Message) => m.created_at)));
      } catch { }
    };
    init();
    const interval = setInterval(fetchAll, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (tab === 'chat') bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [allMessages, tab]);

  const sendReply = async (toUserId: string | null = null) => {
    const t = (toUserId ? replyText : broadcastText).trim();
    if (!t || sending) return;
    setSending(true);
    try {
      const endpoint = toUserId ? `${API}/chat/site/${site.slug}/messages` : `${API}/chat/site/${site.slug}/broadcast`;
      const body = toUserId
        ? { from_id: session.id, from_name: session.username, from_role: session.role, to_user_id: toUserId, text: t }
        : { role: session.role, from_id: session.id, from_name: session.username, text: t };

      const res = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const msg = await res.json();

      if (toUserId) {
        setAllMessages(prev => [...prev, msg]);
        setReplyText('');
      } else {
        setBroadcastText('');
      }
    } catch { }
    finally { setSending(false); }
  };

  const handleBan = async (userId: string, isBanned: boolean) => {
    await fetch(`${API}/chat/site/${site.slug}/users/${userId}/ban`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: session.role, is_banned: isBanned })
    });
    setUsers(prev => prev.map(u => u.id === userId ? { ...u, is_banned: isBanned } : u));
    if (selectedUser?.id === userId) setSelectedUser(prev => prev ? { ...prev, is_banned: isBanned } : prev);
  };

  // Сообщения выбранного пользователя
  const userMessages = selectedUser
    ? allMessages.filter(m => m.from_id === selectedUser.id || m.to_user_id === selectedUser.id || (m.to_user_id === null && (m.from_role === 'admin' || m.from_role === 'owner')))
    : allMessages;

  const TABS = [
    { id: 'chat', label: 'Чат', icon: MessageCircle },
    { id: 'users', label: `Пользователи (${users.length})`, icon: Users },
    { id: 'broadcast', label: 'Рассылка', icon: Megaphone },
    { id: 'stats', label: 'Статистика', icon: BarChart3 },
  ] as const;

  return (
    <div className="flex h-screen" style={{ background: bg, fontFamily: font }}>
      {/* Сайдбар */}
      <div className="w-72 border-r flex flex-col shrink-0" style={{ borderColor: primary + '20', background: bg + 'dd' }}>
        {/* Лого + имя */}
        <div className="p-6 border-b" style={{ borderColor: primary + '15' }}>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-2.5 h-2.5 rounded-full" style={{ background: primary }} />
            <span className="font-black text-white">{cfg.logoText || site.name}</span>
          </div>
          <div className="flex items-center gap-1.5 mt-2">
            <Shield className="w-3 h-3" style={{ color: primary }} />
            <span className="text-[10px] font-black uppercase tracking-wider" style={{ color: primary }}>
              {session.role === 'owner' ? 'Владелец' : 'Администратор'}
            </span>
          </div>
          <span className="text-[9px] text-white/30 block mt-0.5">{session.username}</span>
        </div>

        {/* Навигация */}
        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id as any)}
              className="flex items-center gap-3 w-full px-4 py-3 rounded-2xl transition-all text-left text-sm"
              style={{
                background: tab === t.id ? primary + '20' : 'transparent',
                color: tab === t.id ? primary : 'rgba(255,255,255,0.4)'
              }}>
              <t.icon className="w-4 h-4 shrink-0" />
              <span className="font-bold text-xs">{t.label}</span>
              {t.id === 'chat' && stats?.unread > 0 && (
                <span className="ml-auto text-[8px] font-black px-2 py-0.5 rounded-full"
                  style={{ background: primary, color: '#fff' }}>
                  {stats.unread}
                </span>
              )}
            </button>
          ))}
        </nav>

        {/* Список пользователей (в чате — для выбора) */}
        {tab === 'chat' && (
          <div className="border-t p-3 max-h-72 overflow-y-auto" style={{ borderColor: primary + '15' }}>
            <p className="text-[8px] font-black uppercase tracking-widest mb-2 px-1" style={{ color: primary + '60' }}>Пользователи</p>
            <button
              onClick={() => setSelectedUser(null)}
              className="flex items-center gap-2 w-full px-3 py-2 rounded-xl transition-all mb-1"
              style={{ background: !selectedUser ? primary + '20' : 'transparent', color: !selectedUser ? primary : 'rgba(255,255,255,0.5)' }}>
              <Megaphone className="w-3.5 h-3.5" />
              <span className="text-xs font-bold">Все сообщения</span>
            </button>
            {users.map(u => (
              <button key={u.id}
                onClick={() => setSelectedUser(u)}
                className="flex items-center gap-2 w-full px-3 py-2 rounded-xl transition-all"
                style={{ background: selectedUser?.id === u.id ? primary + '20' : 'transparent', color: selectedUser?.id === u.id ? primary : 'rgba(255,255,255,0.5)' }}>
                <div className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-black shrink-0"
                  style={{ background: primary + '20', color: primary }}>
                  {u.username[0].toUpperCase()}
                </div>
                <span className="text-xs font-bold truncate flex-1">{u.username}</span>
                {u.is_banned && <span className="text-[8px] text-rose-400">ban</span>}
              </button>
            ))}
          </div>
        )}

        <div className="p-4 border-t" style={{ borderColor: primary + '10' }}>
          <button onClick={onLogout}
            className="flex items-center gap-2 w-full px-4 py-2.5 rounded-2xl text-[10px] font-black uppercase tracking-wider transition-all"
            style={{ color: 'rgba(255,255,255,0.3)', background: 'rgba(255,255,255,0.03)' }}>
            <LogOut className="w-3.5 h-3.5" /> Выйти
          </button>
        </div>
      </div>

      {/* Основная область */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* ── ЧАТ ── */}
        {tab === 'chat' && (
          <>
            {/* Заголовок */}
            <div className="px-6 py-4 border-b flex items-center justify-between" style={{ borderColor: primary + '15' }}>
              <div>
                <p className="font-black text-white">{selectedUser ? selectedUser.username : 'Все диалоги'}</p>
                <p className="text-[9px] font-bold uppercase tracking-wider" style={{ color: primary + '60' }}>
                  {selectedUser ? (selectedUser.is_banned ? 'заблокирован' : 'активен') : `${users.length} пользователей`}
                </p>
              </div>
              {selectedUser && (
                <button
                  onClick={() => handleBan(selectedUser.id, !selectedUser.is_banned)}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-[9px] font-black uppercase tracking-wider transition-all"
                  style={{
                    background: selectedUser.is_banned ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                    color: selectedUser.is_banned ? '#10b981' : '#ef4444',
                    border: `1px solid ${selectedUser.is_banned ? '#10b98130' : '#ef444430'}`
                  }}>
                  <Ban className="w-3 h-3" />
                  {selectedUser.is_banned ? 'Разблокировать' : 'Заблокировать'}
                </button>
              )}
            </div>

            {/* Лента сообщений */}
            <div className="flex-1 overflow-y-auto px-6 py-4 no-scrollbar">
              {userMessages.length === 0 && (
                <div className="flex flex-col items-center justify-center h-full gap-2 opacity-40">
                  <MessageCircle className="w-10 h-10" style={{ color: primary }} />
                  <p className="text-sm font-bold text-white/50">Нет сообщений</p>
                </div>
              )}
              {userMessages.map(msg => (
                <MessageBubble key={msg.id} msg={msg} session={session} primary={primary} isAdmin />
              ))}
              <div ref={bottomRef} />
            </div>

            {/* Ответ */}
            {selectedUser && !selectedUser.is_banned && (
              <div className="p-4 border-t" style={{ borderColor: primary + '15' }}>
                <div className="flex gap-3">
                  <input
                    value={replyText}
                    onChange={e => setReplyText(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && sendReply(selectedUser.id)}
                    placeholder={`Ответить ${selectedUser.username}...`}
                    className="flex-1 px-5 py-3 rounded-2xl text-sm text-white placeholder-white/20 outline-none"
                    style={{ background: 'rgba(255,255,255,0.06)', border: `1.5px solid ${primary}30` }}
                    autoFocus
                  />
                  <button onClick={() => sendReply(selectedUser.id)} disabled={!replyText.trim() || sending}
                    className="w-10 h-10 rounded-2xl flex items-center justify-center disabled:opacity-30 transition-all"
                    style={{ background: primary }}>
                    <Send className="w-4 h-4 text-white" />
                  </button>
                </div>
              </div>
            )}
          </>
        )}

        {/* ── ПОЛЬЗОВАТЕЛИ ── */}
        {tab === 'users' && (
          <div className="flex-1 overflow-y-auto p-6">
            <h2 className="text-xl font-black text-white mb-6">Пользователи</h2>
            {users.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-16 opacity-40">
                <Users className="w-10 h-10 text-white/30" />
                <p className="text-sm font-bold text-white/40">Нет пользователей</p>
              </div>
            ) : (
              <div className="space-y-3">
                {users.map(u => (
                  <div key={u.id} className="flex items-center gap-4 p-5 rounded-[1.5rem] border transition-all"
                    style={{ background: 'rgba(255,255,255,0.03)', borderColor: primary + '15' }}>
                    <div className="w-10 h-10 rounded-2xl flex items-center justify-center font-black text-sm shrink-0"
                      style={{ background: primary + '20', color: primary }}>
                      {u.username[0].toUpperCase()}
                    </div>
                    <div className="flex-1">
                      <p className={`font-bold text-sm ${u.is_banned ? 'text-white/30 line-through' : 'text-white'}`}>{u.username}</p>
                      <p className="text-[9px] text-white/30 font-bold">
                        Был: {u.last_seen ? new Date(u.last_seen).toLocaleString('ru') : '—'}
                      </p>
                    </div>
                    {u.is_banned && (
                      <span className="text-[8px] font-black uppercase tracking-wider px-2 py-1 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400">Заблокирован</span>
                    )}
                    <button
                      onClick={() => handleBan(u.id, !u.is_banned)}
                      className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-[9px] font-black uppercase tracking-wider transition-all"
                      style={{
                        background: u.is_banned ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                        color: u.is_banned ? '#10b981' : '#ef4444',
                        border: `1px solid ${u.is_banned ? '#10b98130' : '#ef444430'}`
                      }}>
                      <Ban className="w-3 h-3" />
                      {u.is_banned ? 'Разблокировать' : 'Забанить'}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── РАССЫЛКА ── */}
        {tab === 'broadcast' && (
          <div className="flex-1 p-6">
            <h2 className="text-xl font-black text-white mb-6">Рассылка</h2>
            <div className="max-w-2xl space-y-5">
              <div className="p-5 rounded-[1.5rem] border" style={{ background: 'rgba(255,255,255,0.03)', borderColor: primary + '20' }}>
                <p className="text-[9px] font-black uppercase tracking-wider mb-3" style={{ color: primary }}>
                  Сообщение всем пользователям
                </p>
                <textarea
                  value={broadcastText}
                  onChange={e => setBroadcastText(e.target.value)}
                  placeholder="Текст сообщения..."
                  rows={5}
                  className="w-full bg-transparent text-white text-sm outline-none resize-none placeholder-white/20 leading-relaxed"
                />
              </div>
              <button
                onClick={() => sendReply(null)}
                disabled={!broadcastText.trim() || sending}
                className="flex items-center gap-2 px-8 py-4 rounded-2xl font-black text-[10px] uppercase tracking-wider transition-all disabled:opacity-40"
                style={{ background: primary, color: '#fff', boxShadow: `0 4px 16px ${primary}40` }}>
                {sending ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                {sending ? 'Отправка...' : 'Отправить всем'}
              </button>
            </div>
          </div>
        )}

        {/* ── СТАТИСТИКА ── */}
        {tab === 'stats' && (
          <div className="flex-1 p-6 overflow-y-auto">
            <h2 className="text-xl font-black text-white mb-6">Статистика</h2>
            {stats ? (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                {[
                  { label: 'Всего пользователей', value: stats.total_users, color: 'text-white' },
                  { label: 'Активны (24ч)', value: stats.active_24h, color: 'text-emerald-400' },
                  { label: 'Заблокированных', value: stats.banned_users, color: 'text-rose-400' },
                  { label: 'Всего сообщений', value: stats.total_messages, color: 'text-white' },
                  { label: 'От пользователей', value: stats.user_messages },
                  { label: 'Непрочитанных', value: stats.unread, color: 'text-amber-400' },
                ].map(s => (
                  <div key={s.label} className="p-6 rounded-[1.5rem] border"
                    style={{ background: 'rgba(255,255,255,0.03)', borderColor: primary + '15' }}>
                    <p className="text-[8px] font-black uppercase tracking-widest mb-3 text-white/30">{s.label}</p>
                    <p className={`text-4xl font-black ${s.color || 'text-white/70'}`}>{s.value ?? '—'}</p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex items-center justify-center h-32 gap-3">
                <RefreshCw className="w-5 h-5 text-white/20 animate-spin" />
                <span className="text-white/30 text-sm font-bold">Загрузка...</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

// ─── Root Component ─────────────────────────────────────────────────────────────

const ChatSiteApp: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const [searchParams] = useSearchParams();
  const asAdmin = searchParams.get('as') === 'admin';

  const [site, setSite] = useState<PublicSite | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [session, setSession] = useState<ChatSession | null>(() => {
    try {
      const saved = localStorage.getItem(`chat_session_${slug}`);
      return saved ? JSON.parse(saved) : null;
    } catch { return null; }
  });

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(`${API}/chat/site/${slug}/public`);
        if (!res.ok) { setNotFound(true); return; }
        setSite(await res.json());
      } catch { setNotFound(true); }
      finally { setLoading(false); }
    };
    load();
  }, [slug]);

  const handleAuth = (s: ChatSession) => {
    setSession(s);
    localStorage.setItem(`chat_session_${slug}`, JSON.stringify(s));
  };

  const handleLogout = () => {
    setSession(null);
    localStorage.removeItem(`chat_session_${slug}`);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#09090b] flex items-center justify-center">
        <RefreshCw className="w-6 h-6 text-white/20 animate-spin" />
      </div>
    );
  }

  if (notFound || !site) {
    return (
      <div className="min-h-screen bg-[#09090b] flex items-center justify-center p-8 text-center">
        <div>
          <p className="text-6xl font-black text-white/10 mb-4">404</p>
          <p className="text-white/40 font-bold">Чат-сайт не найден</p>
        </div>
      </div>
    );
  }

  if (!session) {
    return <AuthScreen site={site} defaultMode={asAdmin ? 'login' : 'login'} onAuth={handleAuth} />;
  }

  if (session.role === 'admin' || session.role === 'owner') {
    return <AdminPanel site={site} session={session} onLogout={handleLogout} />;
  }

  return <UserChat site={site} session={session} onLogout={handleLogout} />;
};

export default ChatSiteApp;
