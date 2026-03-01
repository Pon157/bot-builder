import React, { useState, useEffect, useRef } from 'react';
import { api } from '../services/apiService';
import { 
  LayoutDashboard, Users, Bot, Key, LogOut, 
  Activity, ShieldAlert, Play, Square, RefreshCw, 
  ExternalLink, Clock, Search, ShieldCheck, 
  ChevronRight, HardDrive, Cpu, MessageSquare, 
  AlertCircle, Menu, X, Globe, Zap, CheckCircle2,
  Lock, Trash2, Filter, MoreVertical, Ban, Briefcase,
  Mail, Star, ChevronDown, ChevronUp, Megaphone, Code2, UserCheck,
  CheckCircle, XCircle, Loader2, AlertTriangle, Eye, BarChart2
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

// --- Interfaces ---
interface AdminUser {
  id: string;
  email: string;
  created_at?: string;
  is_banned?: boolean;
}

interface AdminBot {
  id: string;
  name: string;
  owner_id: string;
  status: string;
  token: string;
  license_expires_at?: number;
  config?: any;
}

interface AdminPanelProps {
  onLogout: () => void;
}

const fmtDate = (ms: number) => ms ? new Date(ms).toLocaleDateString('ru-RU', { day:'2-digit', month:'short', year:'numeric' }) : '—';

const AdminPanel: React.FC<AdminPanelProps> = ({ onLogout }) => {
  const navigate = useNavigate();
  
  // --- Auth State ---
  const [token, setToken] = useState<string | null>(localStorage.getItem('admin_token'));
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  
  // --- UI State ---
  const [activeTab, setActiveTab] = useState<'dash' | 'users' | 'bots' | 'keys' | 'monitoring' | 'applications' | 'chatsites' | 'allmsgs' | 'ads'>('dash');
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  
  // --- Data State ---
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [bots, setBots] = useState<AdminBot[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [generatedKey, setGeneratedKey] = useState('');
  const [keyDuration, setKeyDuration] = useState(1);
  const [realLogs, setRealLogs] = useState<any[]>([]);
  const [applications, setApplications] = useState<any[]>([]);
  const [appExpandedId, setAppExpandedId] = useState<string | null>(null);
  const [chatSites, setChatSites] = useState<any[]>([]);
  const [chatConvs, setChatConvs] = useState<any[]>([]);
  const [selectedChatSite, setSelectedChatSite] = useState<any | null>(null);
  const [selectedChatConv, setSelectedChatConv] = useState<any | null>(null);
  const [chatMessages, setChatMessages] = useState<any[]>([]);
  const [chatSitesLoading, setChatSitesLoading] = useState(false);
  // All messages feed
  const [allMsgs, setAllMsgs] = useState<any[]>([]);
  const [allMsgsLoading, setAllMsgsLoading] = useState(false);
  const [allMsgsSiteFilter, setAllMsgsSiteFilter] = useState<string>('all');
  const allMsgsPollRef = useRef<NodeJS.Timeout>();

  // 1. Авторизация
  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const data = await api.adminLogin(login, password);
      setToken(data.token);
      localStorage.setItem('admin_token', data.token);
      await loadAllData(data.token);
    } catch (err) { 
      alert('Ошибка доступа: Неверные учетные данные администратора.'); 
    } finally {
      setLoading(false);
    }
  };

  // 2. Глобальная загрузка данных
  const loadAllData = async (t: string) => {
    setLoading(true);
    try {
      const [uData, bData, logsData, dashboardData, appsData] = await Promise.all([
        api.getAllUsers(t),
        api.getAllBots(t),
        api.getSystemLogs(t),
        api.getAdminDashboard(t),
        api.getApplications(t),
      ]);
      
      setUsers(uData || []);
      setBots(bData || []);
      setRealLogs(logsData || []);
      setStats(dashboardData || {});
      setApplications(appsData || []);

    } catch (err) { 
      console.error("Critical load error:", err); 
      if ((err as any).message === 'Unauthorized') {
        localStorage.removeItem('admin_token');
        setToken(null);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (token) loadAllData(token);
  }, [token]);

  // Load chat sites when tab selected
  useEffect(() => {
    if (activeTab === 'chatsites' && token) {
      setChatSitesLoading(true);
      fetch('/api/admin/chat/sites', { headers: { 'x-admin-token': token } })
        .then(r => r.json())
        .then(data => setChatSites(Array.isArray(data) ? data : []))
        .catch(() => setChatSites([]))
        .finally(() => setChatSitesLoading(false));
    }
  }, [activeTab, token]);

  // Load all messages feed
  const loadAllMsgs = async (t: string) => {
    try {
      const sites = await fetch('/api/admin/chat/sites', { headers: { 'x-admin-token': t } }).then(r => r.json());
      if (!Array.isArray(sites) || sites.length === 0) { setAllMsgs([]); return; }
      const allConvPromises = sites.map((s: any) =>
        fetch(`/api/chat/site/${s.slug}/conversations?role=owner&session_id=admin`, { headers: { 'x-admin-token': t } })
          .then(r => r.json()).then(convs => (Array.isArray(convs) ? convs : []).map((c: any) => ({ ...c, _site: s })))
          .catch(() => [])
      );
      const allConvs = (await Promise.all(allConvPromises)).flat();
      const msgPromises = allConvs.map((c: any) =>
        fetch(`/api/chat/site/${c._site.slug}/messages/${c.id}?role=owner&session_id=admin`, { headers: { 'x-admin-token': t } })
          .then(r => r.json()).then(msgs => (Array.isArray(msgs) ? msgs : []).map((m: any) => ({
            ...m,
            _site: c._site,
            _conv: c,
          })))
          .catch(() => [])
      );
      const allMessages = (await Promise.all(msgPromises)).flat();
      allMessages.sort((a: any, b: any) => b.created_at - a.created_at);
      setAllMsgs(allMessages.slice(0, 200));
    } catch { setAllMsgs([]); }
  };

  useEffect(() => {
    if (activeTab === 'allmsgs' && token) {
      setAllMsgsLoading(true);
      loadAllMsgs(token).finally(() => setAllMsgsLoading(false));
      allMsgsPollRef.current = setInterval(() => loadAllMsgs(token), 10000);
      return () => clearInterval(allMsgsPollRef.current);
    }
  }, [activeTab, token]);

  // 3. Действия
  const handleGenerateKey = async () => {
    if (!token) return;
    try {
      const res = await api.generateKey(token, keyDuration, 0);
      setGeneratedKey(res.key);
      loadAllData(token); 
    } catch (e) { alert("Ошибка генерации ключа"); }
  };

  const handleConfigAccess = async (botId: string) => {
    const userKey = window.prompt("Введите активный лицензионный ключ для доступа к редактированию:");
    if (!userKey) return;

    try {
      const data = await api.verifyAccessKey(userKey, botId);

      if (data && data.ok) {
        navigate(`/admin/editor/${botId}`);
      } else {
        alert("Доступ запрещен: Неверный или просроченный ключ.");
      }
    } catch (err: any) {
      console.error("403 Error Details:", err);
      alert(err.message || "Ошибка доступа (403). Ключ не подходит к этому боту.");
    }
  };

  const toggleBot = async (bot: AdminBot) => {
    if (!token) return;
    try {
      const action = bot.status === 'RUNNING' ? 'stop' : 'start';
      await api.adminBotAction(token, bot.id, action);
      alert(`Команда ${action} отправлена`);
      loadAllData(token);
    } catch (e) { alert("Ошибка управления ботом"); }
  };

  const loadChatConvs = async (site: any) => {
    setSelectedChatSite(site);
    setSelectedChatConv(null);
    setChatMessages([]);
    try {
      const r = await fetch(`/api/chat/site/${site.slug}/conversations?role=owner&session_id=admin`, {
        headers: { 'x-admin-token': token || '' }
      });
      const data = await r.json();
      setChatConvs(Array.isArray(data) ? data : []);
    } catch { setChatConvs([]); }
  };

  const loadChatMessages = async (site: any, conv: any) => {
    setSelectedChatConv(conv);
    try {
      const r = await fetch(`/api/chat/site/${site.slug}/messages/${conv.id}?role=owner&session_id=admin`, {
        headers: { 'x-admin-token': token || '' }
      });
      const data = await r.json();
      setChatMessages(Array.isArray(data) ? data : []);
    } catch { setChatMessages([]); }
  };

  const handleBanUser = async (user: AdminUser) => {
    if (!token) return;
    const confirmMsg = user.is_banned 
        ? `Разблокировать пользователя ${user.email}?` 
        : `ЗАБАНИТЬ пользователя ${user.email}? Это остановит всех его ботов.`;
    
    if (!window.confirm(confirmMsg)) return;

    try {
        await api.adminToggleBan(token, user.id, !user.is_banned);
        loadAllData(token);
    } catch (e) { alert("Ошибка изменения статуса"); }
  };

  const filteredUsers = users.filter(u => u.email.toLowerCase().includes(searchQuery.toLowerCase()));
  const filteredBots = bots.filter(b => b.name.toLowerCase().includes(searchQuery.toLowerCase()));

  const formatDateString = (ts?: string | number) => {
    if (!ts) return 'N/A';
    if (typeof ts === 'number') return new Date(ts).toLocaleDateString('ru-RU');
    return new Date(ts).toLocaleDateString('ru-RU');
  };

  // --- Render: Login ---
  if (!token) {
    return (
      <div className="min-h-screen bg-[#050505] flex items-center justify-center p-4 font-sans relative overflow-hidden">
        <div className="absolute inset-0 bg-red-600/5 radial-grid opacity-20 pointer-events-none" />
        <div className="absolute -top-24 -left-24 w-96 h-96 bg-red-600/10 rounded-full blur-[120px]" />
        
        <form onSubmit={handleLogin} className="w-full max-w-md bg-zinc-900/40 border border-zinc-800/50 p-8 md:p-12 rounded-[3rem] backdrop-blur-3xl shadow-2xl relative z-10 animate-in fade-in zoom-in duration-500">
          <div className="w-20 h-20 bg-red-600/10 rounded-3xl flex items-center justify-center text-red-500 mb-8 mx-auto border border-red-500/20 shadow-inner">
            <ShieldAlert size={40} />
          </div>
          <h1 className="text-2xl font-black text-center text-white mb-2 uppercase tracking-[0.2em]">Staff Access</h1>
          <p className="text-zinc-500 text-[10px] text-center mb-10 uppercase font-bold tracking-widest opacity-60">BotEngine Master Terminal</p>
          
          <div className="space-y-4">
            <div className="relative group">
              <input className="w-full bg-black/60 border border-zinc-800 p-5 rounded-2xl text-white outline-none focus:border-red-600 transition-all pl-14 text-sm" placeholder="Administrator Login" value={login} onChange={e => setLogin(e.target.value)} required />
              <Users className="absolute left-5 top-1/2 -translate-y-1/2 text-zinc-600 group-focus-within:text-red-500 transition-colors" size={20} />
            </div>
            <div className="relative group">
              <input type="password" className="w-full bg-black/60 border border-zinc-800 p-5 rounded-2xl text-white outline-none focus:border-red-600 transition-all pl-14 text-sm" placeholder="Security Password" value={password} onChange={e => setPassword(e.target.value)} required />
              <Lock className="absolute left-5 top-1/2 -translate-y-1/2 text-zinc-600 group-focus-within:text-red-500 transition-colors" size={20} />
            </div>
            <button disabled={loading} className="w-full bg-red-600 hover:bg-red-500 text-white font-black py-5 rounded-2xl transition-all uppercase tracking-widest text-xs shadow-xl shadow-red-600/20 active:scale-[0.98]">
              {loading ? 'Verifying Credentials...' : 'Authorize Session'}
            </button>
          </div>
        </form>
      </div>
    );
  }

  const VACANCY_MAP: Record<string, { label: string; icon: any; color: string }> = {
    smm:      { label: 'SMM / Монтажёр / Пиар', icon: Megaphone, color: 'text-sky-400' },
    outreach: { label: 'Спец. по работе с ботами', icon: UserCheck, color: 'text-violet-400' },
    tech:     { label: 'Тех. администратор ботов', icon: Code2,    color: 'text-emerald-400' },
  };

  return (
    <div className="min-h-screen bg-[#050505] text-zinc-300 flex flex-col md:flex-row font-sans selection:bg-red-600/30">
      
      {/* --- SIDEBAR (PC) --- */}
      <aside className="hidden md:flex w-80 border-r border-zinc-800/50 p-8 flex-col gap-2 bg-[#080808] sticky top-0 h-screen z-50">
        <div className="flex items-center gap-4 mb-12 px-4">
          <div className="w-12 h-12 bg-gradient-to-br from-red-600 to-red-900 rounded-2xl flex items-center justify-center text-white font-black text-xl shadow-lg shadow-red-600/20">BE</div>
          <div>
            <span className="font-black text-white uppercase tracking-tighter block text-lg leading-none">Engine</span>
            <span className="text-[10px] text-red-500 font-black uppercase tracking-[0.3em]">Master v2.4</span>
          </div>
        </div>
        
        <nav className="space-y-1.5 overflow-y-auto no-scrollbar">
          <p className="text-[9px] font-black text-zinc-600 uppercase mb-4 px-4 tracking-widest">Main Modules</p>
          <NavBtn icon={LayoutDashboard} label="Обзор / Дашборд" active={activeTab === 'dash'} onClick={() => setActiveTab('dash')} />
          <NavBtn icon={Users} label="Клиенты системы" active={activeTab === 'users'} onClick={() => setActiveTab('users')} />
          <NavBtn icon={Bot} label="Управление ботами" active={activeTab === 'bots'} onClick={() => setActiveTab('bots')} />
          <NavBtn icon={Key} label="Центр лицензий" active={activeTab === 'keys'} onClick={() => setActiveTab('keys')} />
          <NavBtn icon={Activity} label="Мониторинг" active={activeTab === 'monitoring'} onClick={() => setActiveTab('monitoring')} />
          <NavBtn icon={Megaphone} label="Рекламные посты" active={activeTab === 'ads'} onClick={() => setActiveTab('ads')} />
          <NavBtn icon={Briefcase} label="Отклики" active={activeTab === 'applications'} onClick={() => setActiveTab('applications')} badge={applications.filter((a:any)=>a.status==='new').length} />
          <NavBtn icon={MessageSquare} label="Чат-сайты" active={activeTab === 'chatsites'} onClick={() => setActiveTab('chatsites')} />
          <NavBtn icon={Mail} label="Все сообщения" active={activeTab === 'allmsgs'} onClick={() => setActiveTab('allmsgs')} />
        </nav>

        <div className="mt-auto pt-8 border-t border-zinc-900/50">
          <div className="bg-zinc-900/40 p-5 rounded-2xl mb-6 border border-zinc-800/50">
             <div className="flex items-center gap-3 mb-1">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse shadow-[0_0_8px_rgba(34,197,94,0.8)]" />
                <span className="text-[10px] font-black text-white uppercase">Core Online</span>
             </div>
             <p className="text-[9px] text-zinc-600 font-bold uppercase">DB Connection: Stable</p>
          </div>
          <button onClick={() => { localStorage.removeItem('admin_token'); setToken(null); onLogout(); }} className="w-full flex items-center gap-4 px-6 py-4 rounded-2xl text-zinc-500 hover:text-red-500 hover:bg-red-500/5 transition-all text-[11px] font-black uppercase tracking-[0.2em] group">
            <LogOut size={18} className="group-hover:-translate-x-1 transition-transform" /> Sign Out
          </button>
        </div>
      </aside>

      {/* --- MOBILE NAVIGATION --- */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-[#080808]/80 border-t border-zinc-800 z-[100] flex justify-around items-center p-3 backdrop-blur-2xl overflow-x-auto no-scrollbar gap-2">
        <MobileNavBtn icon={LayoutDashboard} active={activeTab === 'dash'} onClick={() => setActiveTab('dash')} />
        <MobileNavBtn icon={Users} active={activeTab === 'users'} onClick={() => setActiveTab('users')} />
        <MobileNavBtn icon={Bot} active={activeTab === 'bots'} onClick={() => setActiveTab('bots')} />
        <MobileNavBtn icon={Key} active={activeTab === 'keys'} onClick={() => setActiveTab('keys')} />
        <MobileNavBtn icon={Activity} active={activeTab === 'monitoring'} onClick={() => setActiveTab('monitoring')} />
        <MobileNavBtn icon={Megaphone} active={activeTab === 'ads'} onClick={() => setActiveTab('ads')} />
        <MobileNavBtn icon={Briefcase} active={activeTab === 'applications'} onClick={() => setActiveTab('applications')} badge={applications.filter((a:any)=>a.status==='new').length} />
        <MobileNavBtn icon={MessageSquare} active={activeTab === 'chatsites'} onClick={() => setActiveTab('chatsites')} />
        <MobileNavBtn icon={Mail} active={activeTab === 'allmsgs'} onClick={() => setActiveTab('allmsgs')} />
      </nav>

      {/* --- MAIN CONTENT --- */}
      <main className="flex-1 p-5 md:p-12 pb-24 md:pb-12 overflow-y-auto">
        <div className="max-w-6xl mx-auto space-y-10">
          
          {/* Header & Search */}
          <div className="flex flex-col lg:flex-row justify-between items-start lg:items-end gap-8">
            <div className="animate-in slide-in-from-left duration-500">
              <h1 className="text-3xl md:text-5xl font-black text-white uppercase tracking-tighter leading-none">
                {activeTab === 'dash' && 'Real-time Analytics'}
                {activeTab === 'users' && 'Customer Database'}
                {activeTab === 'bots' && 'Fleet Operations'}
                {activeTab === 'keys' && 'Licensing Hub'}
                {activeTab === 'monitoring' && 'System Logs'}
                {activeTab === 'ads' && 'Модерация рекламы'}
                {activeTab === 'applications' && 'Отклики на вакансии'}
                {activeTab === 'chatsites' && 'Диалоги чат-сайтов'}
                {activeTab === 'allmsgs' && 'Все сообщения'}
              </h1>
              <div className="flex items-center gap-3 mt-4">
                <div className="h-1 w-16 bg-red-600 rounded-full" />
                <span className="text-[10px] font-black text-zinc-600 uppercase tracking-widest">Admin Control Layer</span>
              </div>
            </div>
            
            <div className="relative w-full lg:w-96 group">
              <input type="text" placeholder="Global search..." className="w-full bg-zinc-900/40 border border-zinc-800 p-5 rounded-2xl text-sm outline-none focus:border-zinc-500 transition-all pl-14 shadow-2xl" value={searchQuery} onChange={e => setSearchQuery(e.target.value)} />
              <Search className="absolute left-5 top-1/2 -translate-y-1/2 text-zinc-600 group-focus-within:text-white transition-colors" size={20} />
              {searchQuery && <button onClick={() => setSearchQuery('')} className="absolute right-5 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-white"><X size={16} /></button>}
            </div>
          </div>

          {/* TAB CONTENT COMPONENTS */}
          {activeTab === 'dash' && stats && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 animate-in fade-in duration-700">
              <StatCard icon={Users} label="Total Users" value={stats.total_users || 0} color="text-blue-500" trend="Real DB Data" />
              <StatCard icon={Bot} label="Active Bots" value={stats.active_bots || 0} color="text-green-500" trend={`${stats.total_bots || 0} total`} />
              <StatCard icon={Zap} label="Keys Issued" value={stats.total_keys || 0} color="text-yellow-500" trend="Licenses" />
              <StatCard icon={ShieldCheck} label="Est. Revenue" value={`$${stats.revenue || 0}`} color="text-emerald-500" trend="Calculated" />
              
              <div className="lg:col-span-3 bg-zinc-900/20 border border-zinc-800/50 p-8 rounded-[3rem] h-80 flex items-center justify-center relative overflow-hidden">
                 <div className="absolute inset-0 opacity-10 flex items-center justify-center"><Activity size={300} strokeWidth={0.5} /></div>
                 <p className="text-zinc-600 font-black uppercase text-xs tracking-widest relative z-10">Real-time Traffic Visualization (Coming Soon)</p>
              </div>
              <div className="lg:col-span-1 bg-red-600/5 border border-red-600/20 p-8 rounded-[3rem] flex flex-col justify-between">
                 <h4 className="text-white font-black uppercase text-xs tracking-widest">System Health</h4>
                 <div className="space-y-4 py-4">
                    <div className="flex gap-3 text-[10px] font-bold text-green-400 uppercase"><CheckCircle2 size={14} /> Database Connected</div>
                    <div className="flex gap-3 text-[10px] font-bold text-zinc-500 uppercase"><Clock size={14} /> Uptime: 99.9%</div>
                 </div>
                 <button onClick={() => loadAllData(token!)} className="w-full py-3 bg-red-600 text-white rounded-xl text-[10px] font-black uppercase tracking-widest">Refresh Data</button>
              </div>
            </div>
          )}

          {activeTab === 'users' && (
            <div className="space-y-4 animate-in slide-in-from-bottom-4 duration-500">
              <div className="flex justify-between items-center px-4">
                <p className="text-[10px] font-black text-zinc-600 uppercase tracking-[0.2em]">Found {filteredUsers.length} clients</p>
                <button className="text-zinc-500 hover:text-white flex items-center gap-2 text-[10px] font-black uppercase"><Filter size={14}/> Filter</button>
              </div>
              <div className="grid gap-3">
                {filteredUsers.map(u => (
                  <div key={u.id} className={`border p-5 md:p-7 rounded-[2.5rem] flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6 transition-all group ${u.is_banned ? 'bg-red-950/20 border-red-900/50' : 'bg-zinc-900/20 border-zinc-800/40 hover:bg-zinc-900/40'}`}>
                    <div className="flex items-center gap-6">
                      <div className={`w-14 h-14 rounded-2xl flex items-center justify-center shadow-xl transition-all ${u.is_banned ? 'bg-red-600 text-white' : 'bg-zinc-800/50 text-zinc-600 group-hover:bg-red-600 group-hover:text-white'}`}>
                        {u.is_banned ? <Ban size={24} /> : <Users size={24} />}
                      </div>
                      <div>
                        <p className={`text-lg font-black ${u.is_banned ? 'text-red-500 line-through' : 'text-white'}`}>{u.email}</p>
                        <div className="flex gap-4 mt-1">
                          <p className="text-zinc-600 text-[9px] font-mono uppercase">UID: {u.id}</p>
                          {u.is_banned && <span className="text-red-500 text-[9px] font-black uppercase bg-red-500/10 px-2 rounded">BANNED</span>}
                        </div>
                      </div>
                    </div>
                    <div className="flex w-full sm:w-auto justify-between sm:justify-end items-center gap-10 border-t sm:border-t-0 border-zinc-800/50 pt-4 sm:pt-0">
                      <div className="text-right">
                        <p className="text-white font-black text-xl leading-none">{bots.filter(b => b.owner_id === u.id).length}</p>
                        <p className="text-[9px] text-zinc-600 uppercase font-black mt-1">Bots Owned</p>
                      </div>
                      <div className="flex gap-2">
                        <button onClick={() => handleBanUser(u)} className={`p-3 rounded-xl transition-colors ${u.is_banned ? 'bg-green-600/20 text-green-500 hover:bg-green-600 hover:text-white' : 'bg-zinc-800/50 text-zinc-500 hover:text-red-500 hover:bg-red-500/10'}`}>
                            {u.is_banned ? <CheckCircle2 size={18} /> : <Ban size={18} />}
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === 'bots' && (
            <div className="grid gap-6 animate-in fade-in duration-500">
              {filteredBots.map(b => (
                <div key={b.id} className="bg-[#0c0c0c] border border-zinc-800 p-6 md:p-10 rounded-[3rem] flex flex-col lg:flex-row justify-between items-start lg:items-center gap-8 relative overflow-hidden group">
                  <div className={`absolute top-0 left-0 w-1 h-full ${b.status === 'RUNNING' ? 'bg-green-500 shadow-[0_0_15px_rgba(34,197,94,0.5)]' : 'bg-zinc-800'}`} />
                  
                  <div className="flex items-center gap-6">
                    <div className={`w-16 h-16 rounded-[1.5rem] flex items-center justify-center border ${b.status === 'RUNNING' ? 'bg-green-500/5 border-green-500/20 text-green-500' : 'bg-zinc-900 border-zinc-800 text-zinc-700'}`}>
                      <Bot size={32} />
                    </div>
                    <div>
                      <div className="flex items-center gap-3">
                        <h3 className="text-xl md:text-2xl font-black text-white uppercase tracking-tighter">{b.name}</h3>
                        {b.license_expires_at && b.license_expires_at > Date.now() && (
                            <div className="p-1 px-2 bg-emerald-500/10 text-emerald-500 text-[8px] font-black rounded-md border border-emerald-500/20 uppercase">Licensed</div>
                        )}
                      </div>
                      <div className="flex flex-wrap gap-3 mt-3">
                        <span className="text-[9px] font-black text-zinc-500 uppercase bg-zinc-900 px-3 py-1.5 rounded-lg border border-zinc-800">
                            Owner: {users.find(u=>u.id===b.owner_id)?.email || b.owner_id.slice(0,8)}
                        </span>
                        <span className={`text-[9px] font-black uppercase px-3 py-1.5 rounded-lg flex items-center gap-2 ${b.status === 'RUNNING' ? 'bg-green-500/10 text-green-500' : 'bg-zinc-800 text-zinc-500'}`}>
                          <div className={`w-1.5 h-1.5 rounded-full ${b.status === 'RUNNING' ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
                          {b.status}
                        </span>
                      </div>
                    </div>
                  </div>
                  
                  <div className="flex flex-col sm:flex-row gap-3 w-full lg:w-auto relative z-10">
                    <button onClick={() => toggleBot(b)} className={`flex-1 flex items-center justify-center gap-3 px-8 py-5 rounded-2xl transition-all text-[10px] font-black uppercase tracking-widest border ${b.status === 'RUNNING' ? 'bg-red-600/10 border-red-600/20 text-red-500 hover:bg-red-600 hover:text-white' : 'bg-green-600/10 border-green-500/20 text-green-500 hover:bg-green-600 hover:text-white'}`}>
                      {b.status === 'RUNNING' ? <Square size={16} fill="currentColor" /> : <Play size={16} fill="currentColor" />}
                      {b.status === 'RUNNING' ? 'Stop' : 'Run'}
                    </button>
                    <button onClick={() => handleConfigAccess(b.id)} className="flex-1 flex items-center justify-center gap-3 bg-zinc-800 hover:bg-white text-zinc-400 hover:text-black px-8 py-5 rounded-2xl transition-all text-[10px] font-black uppercase tracking-widest active:scale-95 shadow-lg">
                      <ExternalLink size={16} /> Edit Config
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {activeTab === 'keys' && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-10 animate-in zoom-in-95 duration-500">
              <div className="lg:col-span-1">
                <div className="bg-zinc-900/40 border border-zinc-800 p-10 rounded-[3.5rem] sticky top-8 shadow-2xl">
                  <h3 className="text-white font-black uppercase mb-10 text-[11px] tracking-[0.2em] flex items-center gap-3 text-red-500">
                    <Key size={20} /> License Issuance
                  </h3>
                  <div className="space-y-8">
                    <div>
                      <label className="text-[10px] font-black text-zinc-500 uppercase mb-4 block px-2">Select Duration</label>
                      <div className="grid grid-cols-3 gap-3">
                        {[1, 3, 12].map(m => (
                          <button key={m} onClick={() => setKeyDuration(m)} className={`py-4 rounded-2xl text-[10px] font-black border transition-all ${keyDuration === m ? 'bg-white text-black border-white shadow-xl shadow-white/10' : 'bg-transparent text-zinc-500 border-zinc-800 hover:border-zinc-600'}`}>
                            {m === 12 ? '1 YEAR' : `${m} MO.`}
                          </button>
                        ))}
                      </div>
                    </div>
                    <button onClick={handleGenerateKey} className="w-full bg-red-600 hover:bg-red-500 text-white font-black py-5 rounded-2xl transition-all uppercase text-xs tracking-[0.3em] shadow-2xl shadow-red-600/30">Generate License</button>
                    
                    {generatedKey && (
                      <div className="mt-10 p-6 bg-black border border-red-500/40 rounded-[2rem] text-center animate-in slide-in-from-top-4">
                        <p className="text-[9px] text-zinc-600 font-black uppercase mb-3">Key Token Generated:</p>
                        <p className="text-red-500 font-mono text-xl font-black select-all break-all tracking-tighter cursor-copy">{generatedKey}</p>
                        <p className="text-[8px] text-zinc-700 font-bold uppercase mt-4 italic">Share with client carefully</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="lg:col-span-2 space-y-4">
                <h3 className="text-zinc-600 font-black uppercase text-[10px] tracking-widest mb-6 px-4 flex items-center gap-3"><Clock size={16}/> Active Licenses (Bots)</h3>
                <div className="grid gap-3">
                  {bots.filter(b => b.license_expires_at && b.license_expires_at > Date.now()).map(b => (
                    <div key={b.id} className="bg-zinc-900/10 border border-zinc-800/40 p-6 rounded-[2rem] flex justify-between items-center group hover:border-emerald-500/30 transition-all">
                      <div className="flex items-center gap-5">
                        <div className="w-14 h-14 bg-zinc-900 border border-zinc-800 rounded-2xl flex items-center justify-center text-zinc-700 group-hover:text-emerald-500 transition-colors shadow-inner"><ShieldCheck size={28} /></div>
                        <div>
                          <p className="text-white font-black text-sm uppercase group-hover:text-emerald-400 transition-colors">{b.name}</p>
                          <p className="text-[9px] text-zinc-600 font-mono mt-1 tracking-widest">ID: {b.id.slice(0,12)}</p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-emerald-500 font-mono text-base font-black tracking-tighter">
                          {formatDateString(b.license_expires_at)}
                        </p>
                        <p className="text-[9px] text-zinc-700 uppercase font-black tracking-widest mt-1">Expiry Date</p>
                      </div>
                    </div>
                  ))}
                  {bots.filter(b => b.license_expires_at && b.license_expires_at > Date.now()).length === 0 && (
                    <div className="py-20 text-center border-2 border-dashed border-zinc-900 rounded-[3rem]">
                       <p className="text-zinc-700 font-black uppercase text-[10px] tracking-widest">No active licenses found</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'monitoring' && (
            <div className="space-y-8 animate-in fade-in duration-500">
              
              <div className="bg-zinc-900/20 border border-zinc-800 p-8 md:p-12 rounded-[4rem] shadow-2xl relative overflow-hidden">
                <div className="absolute top-0 right-0 p-8 opacity-20"><RefreshCw size={100} className="animate-spin-slow text-zinc-700" /></div>
                <h3 className="text-white font-black uppercase mb-10 text-xs tracking-[0.3em] flex items-center gap-3 relative z-10">
                   <div className="w-2 h-2 bg-red-600 rounded-full animate-ping" /> Real-time Message Stream
                </h3>
                <div className="space-y-4 max-h-[400px] overflow-y-auto no-scrollbar font-mono text-[10px] md:text-[11px] relative z-10">
                  {realLogs.length === 0 && <div className="text-zinc-600">No messages yet.</div>}
                  {realLogs.map((log) => (
                    <div key={log.id} className="flex flex-col md:flex-row gap-2 md:gap-6 p-4 rounded-2xl bg-black/40 border border-zinc-800/50 hover:border-zinc-700 transition-colors group">
                      <span className="text-zinc-600 shrink-0 font-bold group-hover:text-zinc-400">
                          [{new Date(log.created_at).toLocaleTimeString()}]
                      </span>
                      <span className="text-blue-500 font-black uppercase shrink-0 tracking-widest">
                          {log.bots?.name || 'Unknown Bot'}
                      </span>
                      <span className="text-zinc-400 leading-relaxed truncate">
                          User {log.user_id}: {log.message_text}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* --- РЕКЛАМНЫЕ ПОСТЫ (ПАТЧ) --- */}
          {activeTab === 'ads' && token && (
            <div className="animate-in fade-in duration-500">
              <AdsModTab token={token} />
            </div>
          )}

          {activeTab === 'applications' && (
            <div className="space-y-6 animate-in fade-in duration-500">
              <div className="flex items-center justify-between px-2">
                <p className="text-[10px] font-black text-zinc-600 uppercase tracking-[0.2em]">
                  Всего откликов: {applications.length} · Новых: {applications.filter((a:any)=>a.status==='new').length}
                </p>
                <button
                  onClick={() => token && fetch(`/api/applications/list`, { headers: { 'x-admin-token': token } }).then(r=>r.json()).then(setApplications)}
                  className="text-zinc-500 hover:text-white flex items-center gap-2 text-[10px] font-black uppercase transition-colors"
                >
                  <RefreshCw size={12} /> Обновить
                </button>
              </div>

              {applications.length === 0 ? (
                <div className="border border-zinc-800/50 rounded-[3rem] p-16 text-center">
                  <Briefcase size={40} className="text-zinc-800 mx-auto mb-4" />
                  <p className="text-zinc-600 font-black uppercase text-xs tracking-widest">Откликов пока нет</p>
                  <p className="text-zinc-700 text-[10px] mt-1">Они появятся здесь после отклика на странице /careers</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {applications.map((app: any) => {
                    const vInfo = VACANCY_MAP[app.vacancy_id] || { label: app.vacancy_title || 'Неизвестно', icon: Briefcase, color: 'text-zinc-400' };
                    const VIcon = vInfo.icon;
                    const isExpanded = appExpandedId === app.id;
                    const isNew = app.status === 'new';

                    return (
                      <div key={app.id} className={`border rounded-[2rem] overflow-hidden transition-all ${isNew ? 'bg-blue-950/20 border-blue-900/40' : 'bg-zinc-900/20 border-zinc-800/40'}`}>
                        
                        <button
                          onClick={() => setAppExpandedId(isExpanded ? null : app.id)}
                          className="w-full flex items-center gap-5 p-6 text-left group"
                        >
                          <div className={`w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 border ${isNew ? 'bg-blue-900/30 border-blue-700/40' : 'bg-zinc-800/50 border-zinc-700/30'} ${vInfo.color}`}>
                            <VIcon size={20} />
                          </div>

                          <div className="flex-1 min-w-0">
                            <div className="flex flex-wrap items-center gap-2 mb-0.5">
                              <p className="font-black text-white text-sm">{app.contact || 'Без контакта'}</p>
                              {isNew && (
                                <span className="text-[8px] font-black uppercase px-2 py-0.5 bg-blue-600 text-white rounded-full tracking-widest">Новый</span>
                              )}
                            </div>
                            <p className="text-zinc-500 text-[11px]">{vInfo.label}</p>
                            <p className="text-zinc-700 text-[10px] mt-0.5">
                              {new Date(app.created_at).toLocaleString('ru-RU', { day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit' })}
                            </p>
                          </div>

                          <div className={`shrink-0 transition-colors ${isExpanded ? vInfo.color : 'text-zinc-700 group-hover:text-zinc-400'}`}>
                            {isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                          </div>
                        </button>

                        {isExpanded && (
                          <div className="px-6 pb-6 space-y-4 animate-in fade-in duration-150">
                            <div className="h-px bg-zinc-800/60" />

                            <div className="grid md:grid-cols-2 gap-4">
                              {[
                                { label: 'Контакт для связи', value: app.contact },
                                { label: 'Вакансия', value: app.vacancy_title || vInfo.label },
                                { label: 'Опыт', value: app.experience },
                              ].map(({ label, value }) => value && (
                                <div key={label} className="bg-black/40 border border-zinc-800/50 rounded-2xl p-4">
                                  <p className="text-[9px] font-black text-zinc-600 uppercase tracking-widest mb-1.5">{label}</p>
                                  <p className="text-white text-sm leading-relaxed">{value}</p>
                                </div>
                              ))}
                            </div>

                            {app.about && (
                              <div className="bg-black/40 border border-zinc-800/50 rounded-2xl p-4">
                                <p className="text-[9px] font-black text-zinc-600 uppercase tracking-widest mb-1.5">О себе / Сильные стороны</p>
                                <p className="text-zinc-300 text-sm leading-relaxed whitespace-pre-wrap">{app.about}</p>
                              </div>
                            )}

                            {app.extra && (
                              <div className="bg-black/40 border border-zinc-800/50 rounded-2xl p-4">
                                <p className="text-[9px] font-black text-zinc-600 uppercase tracking-widest mb-1.5">Портфолио / Ссылки</p>
                                <p className="text-zinc-300 text-sm leading-relaxed whitespace-pre-wrap break-all">{app.extra}</p>
                              </div>
                            )}

                            <div className="flex gap-3 pt-1">
                              {isNew && (
                                <button
                                  onClick={async () => {
                                    if (!token) return;
                                    await fetch(`/api/applications/${app.id}/status`, {
                                      method: 'PATCH',
                                      headers: { 'Content-Type': 'application/json', 'x-admin-token': token },
                                      body: JSON.stringify({ status: 'reviewed' }),
                                    });
                                    setApplications(prev => prev.map((a:any) => a.id === app.id ? { ...a, status: 'reviewed' } : a));
                                  }}
                                  className="flex items-center gap-2 px-4 py-2 bg-emerald-600/20 hover:bg-emerald-600/40 text-emerald-400 text-[10px] font-black uppercase rounded-xl transition-all"
                                >
                                  <CheckCircle2 size={14} /> Отмечено как просмотрено
                                </button>
                              )}
                              <button
                                onClick={async () => {
                                  if (!token || !window.confirm('Удалить этот отклик?')) return;
                                  await fetch(`/api/applications/${app.id}`, {
                                    method: 'DELETE',
                                    headers: { 'x-admin-token': token },
                                  });
                                  setApplications(prev => prev.filter((a:any) => a.id !== app.id));
                                  setAppExpandedId(null);
                                }}
                                className="flex items-center gap-2 px-4 py-2 bg-rose-600/10 hover:bg-rose-600/20 text-rose-500 text-[10px] font-black uppercase rounded-xl transition-all"
                              >
                                <Trash2 size={14} /> Удалить
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {activeTab === 'chatsites' && (
            <div className="space-y-6 animate-in fade-in duration-500">
              <div className="flex gap-4">
                <div className="w-64 shrink-0 space-y-2">
                  <p className="text-[9px] font-black text-zinc-600 uppercase tracking-widest px-2 mb-3">Чат-сайты ({chatSites.length})</p>
                  {chatSitesLoading ? (
                    <div className="flex justify-center py-8"><RefreshCw size={18} className="text-zinc-700 animate-spin" /></div>
                  ) : chatSites.length === 0 ? (
                    <div className="border border-dashed border-zinc-800 rounded-2xl p-6 text-center">
                      <p className="text-zinc-700 text-xs font-black uppercase">Нет сайтов</p>
                    </div>
                  ) : chatSites.map((site: any) => (
                    <button key={site.id}
                      onClick={() => loadChatConvs(site)}
                      className={`w-full text-left p-4 rounded-2xl border transition-all ${selectedChatSite?.id === site.id ? 'bg-red-600/10 border-red-600/20 text-white' : 'bg-zinc-900/20 border-zinc-800/40 text-zinc-400 hover:border-zinc-700'}`}>
                      <div className="flex items-center gap-3">
                        <div className="w-3 h-3 rounded-full shrink-0" style={{ background: site.config?.primaryColor || '#6366f1' }} />
                        <div className="min-w-0">
                          <p className="font-black text-sm truncate">{site.name}</p>
                          <p className="text-[9px] font-mono text-zinc-600">/chat/{site.slug}</p>
                        </div>
                        <div className={`w-2 h-2 rounded-full shrink-0 ml-auto ${site.is_active ? 'bg-emerald-500' : 'bg-zinc-600'}`} />
                      </div>
                    </button>
                  ))}
                </div>

                {selectedChatSite && (
                  <div className="w-72 shrink-0 space-y-2">
                    <p className="text-[9px] font-black text-zinc-600 uppercase tracking-widest px-2 mb-3">
                      Диалоги — {selectedChatSite.name} ({chatConvs.length})
                    </p>
                    {chatConvs.length === 0 ? (
                      <div className="border border-dashed border-zinc-800 rounded-2xl p-6 text-center">
                        <p className="text-zinc-700 text-xs font-black uppercase">Нет диалогов</p>
                      </div>
                    ) : chatConvs.map((conv: any) => (
                      <button key={conv.id}
                        onClick={() => loadChatMessages(selectedChatSite, conv)}
                        className={`w-full text-left p-4 rounded-2xl border transition-all ${selectedChatConv?.id === conv.id ? 'bg-red-600/10 border-red-600/20' : 'bg-zinc-900/20 border-zinc-800/40 hover:border-zinc-700'}`}>
                        <div className="flex items-center gap-3">
                          <div className="w-9 h-9 rounded-full bg-zinc-800 flex items-center justify-center text-white text-sm font-black shrink-0">
                            {(conv.user_name || '?')[0]?.toUpperCase()}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <p className="text-white font-black text-sm truncate">{conv.user_name || 'Пользователь'}</p>
                              {(conv.unread_admin > 0 || conv.unread_user > 0) && (
                                <span className="w-4 h-4 rounded-full bg-red-600 text-white text-[8px] font-black flex items-center justify-center shrink-0">
                                  {conv.unread_admin || conv.unread_user}
                                </span>
                              )}
                            </div>
                            <p className="text-zinc-600 text-[10px] truncate">{conv.admin_name}</p>
                            {conv.last_message_preview && (
                              <p className="text-zinc-700 text-[9px] truncate mt-0.5">{conv.last_message_preview}</p>
                            )}
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}

                {selectedChatConv && selectedChatSite && (
                  <div className="flex-1 bg-zinc-900/20 border border-zinc-800 rounded-[2rem] overflow-hidden flex flex-col" style={{ minHeight: '500px' }}>
                    <div className="flex items-center gap-3 p-5 border-b border-zinc-800">
                      <div className="w-9 h-9 rounded-full bg-zinc-800 flex items-center justify-center text-white font-black">
                        {(selectedChatConv.user_name || '?')[0]?.toUpperCase()}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-white font-black">{selectedChatConv.user_name}</p>
                        <p className="text-zinc-600 text-[10px]">с {selectedChatConv.admin_name} • {selectedChatSite.name}</p>
                      </div>
                      <button
                        onClick={() => { setSelectedChatConv(null); setChatMessages([]); }}
                        className="p-2 hover:bg-zinc-800 rounded-xl text-zinc-600 hover:text-white transition-colors"
                      >
                        <X size={16} />
                      </button>
                    </div>

                    <div className="flex-1 overflow-y-auto p-5 space-y-3">
                      {chatMessages.length === 0 ? (
                        <div className="flex items-center justify-center h-full">
                          <p className="text-zinc-700 font-bold text-sm">Нет сообщений</p>
                        </div>
                      ) : chatMessages.map((msg: any) => {
                        const isAdmin = msg.from_role === 'admin' || msg.from_role === 'owner';
                        const p = selectedChatSite.config?.primaryColor || '#6366f1';
                        return (
                          <div key={msg.id} className={`flex gap-3 ${isAdmin ? 'flex-row-reverse' : 'flex-row'}`}>
                            <div className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-black shrink-0"
                              style={{ background: isAdmin ? p + '40' : '#27272a' }}>
                              {(msg.from_name || '?')[0]?.toUpperCase()}
                            </div>
                            <div className={`max-w-[70%] ${isAdmin ? 'items-end' : 'items-start'} flex flex-col gap-1`}>
                              <span className="text-[9px] font-black uppercase tracking-wider px-1" style={{ color: isAdmin ? p : 'rgba(255,255,255,0.3)' }}>
                                {msg.from_name}
                              </span>
                              {msg.text && (
                                <div className="px-4 py-2.5 rounded-2xl text-sm text-white leading-relaxed break-words"
                                  style={{ background: isAdmin ? p + '20' : 'rgba(255,255,255,0.06)' }}>
                                  {msg.text}
                                </div>
                              )}
                              {msg.media_url && (
                                <div className="rounded-2xl overflow-hidden border border-white/10">
                                  {msg.media_type === 'image' ? (
                                    <img src={msg.media_url.startsWith('http') ? msg.media_url : window.location.origin + msg.media_url}
                                      alt="img" className="max-w-[200px] max-h-40 object-cover cursor-pointer block"
                                      onClick={() => window.open(msg.media_url.startsWith('http') ? msg.media_url : window.location.origin + msg.media_url, '_blank')} />
                                  ) : msg.media_type === 'video' ? (
                                    <video src={msg.media_url.startsWith('http') ? msg.media_url : window.location.origin + msg.media_url}
                                      controls className="max-w-[200px] max-h-40" />
                                  ) : msg.media_type === 'audio' ? (
                                    <div className="flex items-center gap-2 px-3 py-2 bg-white/5 min-w-[160px]">
                                      <span className="text-xs text-zinc-400">🎵 Голосовое</span>
                                      <audio src={msg.media_url.startsWith('http') ? msg.media_url : window.location.origin + msg.media_url} controls className="h-7 flex-1" preload="metadata" />
                                    </div>
                                  ) : (
                                    <a href={msg.media_url.startsWith('http') ? msg.media_url : window.location.origin + msg.media_url}
                                      target="_blank" rel="noopener noreferrer"
                                      className="flex items-center gap-2 px-3 py-2 bg-white/5 hover:bg-white/10 transition-all">
                                      <span className="text-base">📎</span>
                                      <span className="text-xs text-white truncate max-w-[120px]">
                                        {msg.media_url.split('/').pop()?.replace(/^\d+_\d+_/, '') || 'Файл'}
                                      </span>
                                    </a>
                                  )}
                                </div>
                              )}
                              {msg.sticker_emoji && (
                                <div className="text-4xl">{msg.sticker_emoji}</div>
                              )}
                              <span className="text-[9px] px-1" style={{ color: 'rgba(255,255,255,0.2)' }}>
                                {new Date(msg.created_at).toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' })}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    <div className="p-4 border-t border-zinc-800">
                      <button
                        onClick={() => loadChatMessages(selectedChatSite, selectedChatConv)}
                        className="flex items-center gap-2 text-[10px] font-black uppercase text-zinc-500 hover:text-white transition-colors"
                      >
                        <RefreshCw size={12} /> Обновить диалог
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'allmsgs' && (
            <div className="space-y-4 animate-in fade-in duration-500">
              <div className="flex items-center gap-3 flex-wrap">
                <button onClick={() => setAllMsgsSiteFilter('all')}
                  className={`px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-wider transition-all border ${allMsgsSiteFilter === 'all' ? 'bg-red-600/20 border-red-600/30 text-red-400' : 'border-zinc-800 text-zinc-500 hover:text-white'}`}>
                  Все сайты ({allMsgs.length})
                </button>
                {Array.from(new Set(allMsgs.map((m: any) => m._site?.id))).map(siteId => {
                  const site = allMsgs.find((m: any) => m._site?.id === siteId)?._site;
                  if (!site) return null;
                  const count = allMsgs.filter((m: any) => m._site?.id === siteId).length;
                  return (
                    <button key={siteId as string} onClick={() => setAllMsgsSiteFilter(siteId as string)}
                      className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-wider transition-all border ${allMsgsSiteFilter === siteId ? 'bg-white/10 border-white/20 text-white' : 'border-zinc-800 text-zinc-500 hover:text-white'}`}>
                      <div className="w-2 h-2 rounded-full" style={{ background: site.config?.primaryColor || '#6366f1' }} />
                      {site.name} ({count})
                    </button>
                  );
                })}
                <button onClick={() => token && loadAllMsgs(token)}
                  className="ml-auto px-3 py-2 rounded-xl text-[10px] font-black uppercase text-zinc-500 hover:text-white border border-zinc-800 hover:border-zinc-700 transition-all flex items-center gap-1.5">
                  <RefreshCw size={12} /> Обновить
                </button>
              </div>

              {allMsgsLoading ? (
                <div className="flex justify-center py-16"><RefreshCw size={24} className="text-zinc-700 animate-spin" /></div>
              ) : (
                <div className="space-y-2">
                  {(allMsgsSiteFilter === 'all' ? allMsgs : allMsgs.filter((m: any) => m._site?.id === allMsgsSiteFilter))
                    .map((msg: any) => {
                      const isAdmin = msg.from_role === 'admin' || msg.from_role === 'owner';
                      const isSystem = msg.from_role === 'system';
                      const p = msg._site?.config?.primaryColor || '#6366f1';
                      const absUrl = msg.media_url ? (msg.media_url.startsWith('http') ? msg.media_url : window.location.origin + msg.media_url) : null;
                      return (
                        <div key={msg.id} className="bg-zinc-900/40 border border-zinc-800/50 rounded-2xl p-4 hover:border-zinc-700 transition-all">
                          <div className="flex items-center gap-3 mb-2.5 flex-wrap">
                            <div className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-black shrink-0"
                              style={{ background: isSystem ? '#27272a' : isAdmin ? p + '40' : '#27272a' }}>
                              {isSystem ? '📢' : (msg.from_name || '?')[0]?.toUpperCase()}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="text-white font-black text-xs">{msg.from_name || 'Неизвестно'}</span>
                                <span className={`text-[8px] px-1.5 py-0.5 rounded-full font-black uppercase ${isSystem ? 'bg-purple-500/20 text-purple-400' : isAdmin ? 'bg-blue-500/20 text-blue-400' : 'bg-zinc-800 text-zinc-500'}`}>
                                  {isSystem ? 'system' : isAdmin ? 'admin' : 'user'}
                                </span>
                                {allMsgsSiteFilter === 'all' && (
                                  <span className="text-[8px] px-2 py-0.5 rounded-full font-black border"
                                    style={{ borderColor: p + '40', color: p, background: p + '10' }}>
                                    {msg._site?.name}
                                  </span>
                                )}
                                <span className="text-[9px] text-zinc-600 ml-auto shrink-0">
                                  {new Date(msg.created_at).toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' })}
                                  {' · '}
                                  {new Date(msg.created_at).toLocaleDateString('ru', { day: 'numeric', month: 'short' })}
                                </span>
                              </div>
                              <p className="text-[9px] text-zinc-600 font-mono truncate">
                                диалог: {msg._conv?.user_name || '?'} ↔ {msg._conv?.admin_name || '?'}
                              </p>
                            </div>
                          </div>
                          {msg.sticker_emoji && <div className="text-3xl mb-1">{msg.sticker_emoji}</div>}
                          {msg.text && (
                            <div className="text-sm text-zinc-300 leading-relaxed break-words">
                              {msg.text.startsWith('📢') ? (
                                <div className="flex items-start gap-2 p-3 rounded-xl" style={{ background: p + '10', border: `1px solid ${p}25` }}>
                                  <span className="text-base shrink-0">📢</span>
                                  <span style={{ color: p + 'cc' }}>{msg.text.slice(2).trim()}</span>
                                </div>
                              ) : msg.text}
                            </div>
                          )}
                          {absUrl && (
                            <div className="mt-2 rounded-xl overflow-hidden border border-white/10 inline-block">
                              {msg.media_type === 'image' ? (
                                <img src={absUrl} alt="img" className="max-w-[180px] max-h-32 object-cover cursor-pointer block"
                                  onClick={() => window.open(absUrl, '_blank')} />
                              ) : msg.media_type === 'video' ? (
                                <video src={absUrl} controls className="max-w-[180px] max-h-32" />
                              ) : msg.media_type === 'audio' ? (
                                <div className="flex items-center gap-2 px-3 py-2 bg-white/5 min-w-[160px]">
                                  <span className="text-xs text-zinc-400">🎵</span>
                                  <audio src={absUrl} controls className="h-7 flex-1" preload="metadata" />
                                </div>
                              ) : (
                                <a href={absUrl} target="_blank" rel="noopener noreferrer"
                                  className="flex items-center gap-2 px-3 py-2 bg-white/5 hover:bg-white/10 transition-all">
                                  <span className="text-base">📎</span>
                                  <span className="text-xs text-white truncate max-w-[120px]">
                                    {msg.media_url?.split('/').pop()?.replace(/^\d+_\d+_/, '') || 'Файл'}
                                  </span>
                                </a>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  {allMsgs.length === 0 && !allMsgsLoading && (
                    <div className="border border-dashed border-zinc-800 rounded-2xl p-16 text-center">
                      <Mail size={40} className="mx-auto mb-4 text-zinc-800" />
                      <p className="text-zinc-700 text-xs font-black uppercase">Нет сообщений</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

        </div>
      </main>
    </div>
  );
};

// --- SUB-COMPONENTS ---

const NavBtn = ({ icon: Icon, label, active, onClick, badge }: any) => (
  <button onClick={onClick} className={`w-full flex items-center gap-4 px-6 py-4 rounded-2xl transition-all border ${active ? 'bg-white text-black border-white shadow-2xl shadow-white/5 font-black scale-[1.02]' : 'text-zinc-500 border-transparent hover:text-white hover:bg-zinc-900/50'}`}>
    <Icon size={20} className={active ? 'text-black' : 'text-zinc-600'} />
    <span className="text-[11px] uppercase tracking-widest">{label}</span>
    <div className="ml-auto flex items-center gap-2">
      {badge > 0 && <span className="w-5 h-5 bg-blue-600 text-white text-[9px] font-black rounded-full flex items-center justify-center">{badge}</span>}
      {active && <div className="w-1.5 h-1.5 bg-red-600 rounded-full" />}
    </div>
  </button>
);

const MobileNavBtn = ({ icon: Icon, active, onClick, badge }: any) => (
  <button onClick={onClick} className={`p-4 rounded-2xl transition-all relative ${active ? 'text-red-500' : 'text-zinc-600'}`}>
    <Icon size={24} />
    {active && <div className="absolute -top-1 left-1/2 -translate-x-1/2 w-1 h-1 bg-red-500 rounded-full" />}
    {badge > 0 && <span className="absolute top-2 right-2 w-4 h-4 bg-blue-600 text-white text-[8px] font-black rounded-full flex items-center justify-center">{badge}</span>}
  </button>
);

const StatCard = ({ icon: Icon, label, value, color, trend }: any) => (
  <div className="bg-zinc-900/40 border border-zinc-800 p-8 rounded-[2.5rem] hover:border-zinc-700 transition-all shadow-xl group">
    <div className="flex justify-between items-start mb-6">
      <div className={`p-4 bg-zinc-950 border border-zinc-800 rounded-[1.5rem] ${color} group-hover:scale-110 transition-transform`}><Icon size={24} /></div>
      <div className="text-[8px] font-black text-zinc-600 uppercase tracking-widest bg-zinc-900 px-2 py-1 rounded-md">{trend}</div>
    </div>
    <p className="text-zinc-500 text-[9px] font-black uppercase tracking-widest mb-1">{label}</p>
    <p className="text-3xl font-black text-white tracking-tighter">{value}</p>
  </div>
);

// --- ADS MODERATION COMPONENT (PATCH) ---

const StatusBadge: React.FC<{ s: string }> = ({ s }) => {
  const map: Record<string, string> = {
    pending: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    approved: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    active: 'bg-green-500/10 text-green-400 border-green-500/20',
    rejected: 'bg-red-500/10 text-red-400 border-red-500/20',
    finished: 'bg-zinc-800 text-zinc-500 border-zinc-700',
  };
  const labels: Record<string, string> = {
    pending: 'Ожидает', approved: 'Одобрено', active: 'Активно',
    rejected: 'Отклонено', finished: 'Завершено',
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-widest border ${map[s] || 'bg-zinc-800 text-zinc-500 border-zinc-700'}`}>
      {labels[s] || s}
    </span>
  );
};

export const AdsModTab: React.FC<{ token: string }> = ({ token }) => {
  const [posts, setPosts]       = useState<any[]>([]);
  const [stats, setStats]       = useState<any>(null);
  const [filter, setFilter]     = useState('pending');
  const [loading, setLoading]   = useState(false);
  const [rejectId, setRejectId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [actionMsg, setActionMsg] = useState('');

  const fetchPosts = async (f: string = filter) => {
    setLoading(true);
    try {
      const r = await fetch(`/api/admin/ads/posts?status=${f}`, {
        headers: { 'X-Admin-Token': token }
      });
      if (r.ok) setPosts(await r.json());

      const sr = await fetch('/api/admin/ads/stats', {
        headers: { 'X-Admin-Token': token }
      });
      if (sr.ok) setStats(await sr.json());
    } catch {}
    setLoading(false);
  };

  useEffect(() => { fetchPosts(); }, [filter]);

  const handleApprove = async (postId: string) => {
    const r = await fetch(`/api/admin/ads/posts/${postId}/approve`, {
      method: 'POST',
      headers: { 'X-Admin-Token': token }
    });
    if (r.ok) {
      setActionMsg('✅ Пост одобрен');
      fetchPosts();
      setTimeout(() => setActionMsg(''), 3000);
    }
  };

  const handleReject = async () => {
    if (!rejectId) return;
    const r = await fetch(`/api/admin/ads/posts/${rejectId}/reject`, {
      method: 'POST',
      headers: { 'X-Admin-Token': token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: rejectReason || 'Не соответствует правилам' })
    });
    if (r.ok) {
      setActionMsg('✅ Пост отклонён');
      setRejectId(null); setRejectReason('');
      fetchPosts();
      setTimeout(() => setActionMsg(''), 3000);
    }
  };

  return (
    <div>
      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <div className="p-4 bg-zinc-900/60 border border-zinc-800 rounded-2xl">
            <div className="text-xl font-black text-white font-mono">{stats.agents_count}</div>
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest mt-0.5">Рекламодателей</div>
          </div>
          <div className="p-4 bg-zinc-900/60 border border-zinc-800 rounded-2xl">
            <div className="text-xl font-black text-amber-400 font-mono">{stats.posts_by_status?.pending || 0}</div>
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest mt-0.5">На модерации</div>
          </div>
          <div className="p-4 bg-zinc-900/60 border border-zinc-800 rounded-2xl">
            <div className="text-xl font-black text-green-400 font-mono">{(stats.total_impressions_used || 0).toLocaleString()}</div>
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest mt-0.5">Показов выдано</div>
          </div>
          <div className="p-4 bg-zinc-900/60 border border-zinc-800 rounded-2xl">
            <div className="text-xl font-black text-blue-400 font-mono">{(stats.total_revenue_rub || 0).toFixed(2)} ₽</div>
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest mt-0.5">Доход</div>
          </div>
        </div>
      )}

      {actionMsg && (
        <div className="mb-4 p-3 bg-green-500/10 border border-green-500/20 rounded-xl text-green-400 text-xs">
          {actionMsg}
        </div>
      )}

      {/* Filter */}
      <div className="flex gap-2 mb-4 flex-wrap">
        {['pending', 'approved', 'active', 'rejected', 'finished', 'all'].map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-xl text-[11px] font-bold uppercase tracking-widest transition-colors
              ${filter === f ? 'bg-amber-500 text-black' : 'bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-white'}`}>
            {f === 'all' ? 'Все' : f === 'pending' ? 'Ожидают' : f === 'approved' ? 'Одобрено' : f === 'active' ? 'Активные' : f === 'rejected' ? 'Отклонено' : 'Завершено'}
          </button>
        ))}
        <button onClick={() => fetchPosts(filter)}
          className="p-2 bg-zinc-900 border border-zinc-800 rounded-xl text-zinc-500 hover:text-white transition-colors ml-auto">
          <RefreshCw size={14} />
        </button>
      </div>

      {/* Posts */}
      {loading ? (
        <div className="flex justify-center py-10"><Loader2 size={20} className="animate-spin text-zinc-600" /></div>
      ) : posts.length === 0 ? (
        <div className="text-center py-12 bg-zinc-900/40 border border-zinc-800 rounded-2xl">
          <Megaphone size={28} className="text-zinc-700 mx-auto mb-2" />
          <p className="text-zinc-600 text-sm">Постов нет</p>
        </div>
      ) : (
        <div className="space-y-3">
          {posts.map((post: any) => (
            <div key={post.id} className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-4">
              <div className="flex items-start justify-between gap-3 mb-3">
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-white leading-snug mb-1">{post.text}</div>
                  {post.media_url && (
                    <a href={post.media_url} target="_blank" rel="noreferrer"
                      className="text-[10px] text-blue-400 hover:underline flex items-center gap-1">
                      <Eye size={11} /> Медиа
                    </a>
                  )}
                  <div className="text-[10px] text-zinc-600 mt-1">
                    ID агента: {post.agent_id} · {fmtDate(post.created_at)}
                  </div>
                </div>
                <StatusBadge s={post.status} />
              </div>

              {post.status === 'pending' && (
                <div className="flex gap-2">
                  <button onClick={() => handleApprove(post.id)}
                    className="flex-1 py-2 bg-green-500/10 hover:bg-green-500/20 border border-green-500/20 rounded-xl text-xs font-bold text-green-400 transition-colors flex items-center justify-center gap-1.5">
                    <CheckCircle size={13} /> Одобрить
                  </button>
                  <button onClick={() => { setRejectId(post.id); setRejectReason(''); }}
                    className="flex-1 py-2 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 rounded-xl text-xs font-bold text-red-400 transition-colors flex items-center justify-center gap-1.5">
                    <XCircle size={13} /> Отклонить
                  </button>
                </div>
              )}

              {post.status === 'active' && (
                <div className="text-xs text-zinc-500">
                  Показов: {post.impressions_used}/{post.impressions_paid}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Reject Modal */}
      {rejectId && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="w-full max-w-sm bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
            <h3 className="font-black text-white mb-3 text-sm flex items-center gap-2">
              <AlertTriangle size={15} className="text-red-400" /> Причина отклонения
            </h3>
            <textarea
              value={rejectReason}
              onChange={e => setRejectReason(e.target.value)}
              rows={3}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-red-500 resize-none mb-3"
              placeholder="Не соответствует правилам площадки..."
            />
            <div className="flex gap-2">
              <button onClick={() => setRejectId(null)}
                className="flex-1 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-xl text-xs font-bold transition-colors">
                Отмена
              </button>
              <button onClick={handleReject}
                className="flex-1 py-2 bg-red-600 hover:bg-red-700 rounded-xl text-xs font-black text-white transition-colors">
                Отклонить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminPanel;
