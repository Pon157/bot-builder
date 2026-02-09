import React, { useState, useEffect } from 'react';
import { api } from '../services/apiService';
import { 
  LayoutDashboard, Users, Bot, Key, LogOut, 
  Activity, Server, Database, ShieldAlert,
  Search, Play, Square, Trash2, RefreshCw
} from 'lucide-react';

interface AdminPanelProps {
  onLogout: () => void;
}

const AdminPanel: React.FC<AdminPanelProps> = ({ onLogout }) => {
  const [token, setToken] = useState<string | null>(localStorage.getItem('admin_token'));
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [activeTab, setActiveTab] = useState<'dash' | 'users' | 'bots' | 'keys'>('dash');
  const [loading, setLoading] = useState(false);
  
  // Data States
  const [stats, setStats] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [bots, setBots] = useState<any[]>([]);
  const [generatedKey, setGeneratedKey] = useState('');

  // Login Logic
  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const data = await api.adminLogin(login, password);
      setToken(data.token);
      localStorage.setItem('admin_token', data.token);
      loadData(data.token);
    } catch (err) {
      alert('Ошибка доступа');
    }
    setLoading(false);
  };

  const loadData = async (authToken: string) => {
    setLoading(true);
    try {
      const dStats = await api.getAdminDashboard(authToken);
      setStats(dStats);
      
      const dUsers = await api.getAllUsers(authToken);
      setUsers(dUsers);
      
      const dBots = await api.getAllBots(authToken);
      setBots(dBots);
    } catch (e) {
      console.error(e);
      if ((e as any).status === 403) {
        setToken(null);
        localStorage.removeItem('admin_token');
      }
    }
    setLoading(false);
  };

  useEffect(() => {
    if (token) loadData(token);
  }, [token]);

  // Actions
  const handleBotAction = async (botId: string, action: 'stop' | 'delete') => {
    if (!confirm(`Вы уверены, что хотите ${action} этого бота?`)) return;
    if (!token) return;
    await api.adminBotAction(token, botId, action);
    loadData(token);
  };

  const handleGenKey = async (months: number) => {
    if (!token) return;
    const res = await api.generateKey(token, months, 0);
    setGeneratedKey(res.key);
  };

  // --- RENDER: LOGIN ---
  if (!token) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center p-4">
        <div className="bg-[#111] border border-zinc-800 p-8 rounded-3xl w-full max-w-sm">
          <div className="flex justify-center mb-6">
            <div className="w-12 h-12 bg-red-600/20 rounded-xl flex items-center justify-center">
              <ShieldAlert className="text-red-500 w-6 h-6" />
            </div>
          </div>
          <h2 className="text-2xl font-black text-white text-center mb-6">STAFF ACCESS</h2>
          <form onSubmit={handleLogin} className="space-y-4">
            <input 
              type="text" placeholder="Login ID" 
              className="w-full bg-black border border-zinc-800 rounded-xl p-3 text-white focus:border-red-500 outline-none"
              value={login} onChange={e => setLogin(e.target.value)}
            />
            <input 
              type="password" placeholder="Password" 
              className="w-full bg-black border border-zinc-800 rounded-xl p-3 text-white focus:border-red-500 outline-none"
              value={password} onChange={e => setPassword(e.target.value)}
            />
            <button disabled={loading} className="w-full bg-red-600 hover:bg-red-700 text-white font-bold py-3 rounded-xl transition-colors">
              {loading ? 'VERIFYING...' : 'AUTHENTICATE'}
            </button>
          </form>
        </div>
      </div>
    );
  }

  // --- RENDER: PANEL ---
  return (
    <div className="min-h-screen bg-black text-zinc-300 flex font-sans">
      {/* SIDEBAR */}
      <div className="w-64 bg-[#080808] border-r border-zinc-900 flex flex-col p-4">
        <div className="mb-8 px-2 flex items-center gap-3">
          <div className="w-8 h-8 bg-gradient-to-br from-red-600 to-orange-600 rounded-lg"></div>
          <span className="font-black text-white tracking-wider">ADMIN CORE</span>
        </div>
        
        <nav className="space-y-1 flex-1">
          <NavBtn icon={LayoutDashboard} label="Обзор" active={activeTab === 'dash'} onClick={() => setActiveTab('dash')} />
          <NavBtn icon={Users} label="Пользователи" active={activeTab === 'users'} onClick={() => setActiveTab('users')} />
          <NavBtn icon={Bot} label="Все боты" active={activeTab === 'bots'} onClick={() => setActiveTab('bots')} />
          <NavBtn icon={Key} label="Лицензии" active={activeTab === 'keys'} onClick={() => setActiveTab('keys')} />
        </nav>

        <button onClick={() => { setToken(null); localStorage.removeItem('admin_token'); }} className="mt-auto flex items-center gap-3 px-4 py-3 text-zinc-500 hover:text-white transition-colors">
          <LogOut size={18} /> <span className="text-xs font-bold uppercase">Выход</span>
        </button>
      </div>

      {/* CONTENT */}
      <div className="flex-1 overflow-y-auto p-8">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold text-white">
            {activeTab === 'dash' && 'Аналитика системы'}
            {activeTab === 'users' && 'База клиентов'}
            {activeTab === 'bots' && 'Реестр ботов'}
            {activeTab === 'keys' && 'Генератор ключей'}
          </h1>
          <button onClick={() => loadData(token)} className="p-2 hover:bg-zinc-800 rounded-lg text-zinc-500 hover:text-white">
            <RefreshCw size={20} className={loading ? "animate-spin" : ""} />
          </button>
        </div>

        {/* DASHBOARD TAB */}
        {activeTab === 'dash' && stats && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <StatCard icon={Users} label="Всего клиентов" value={stats.total_users} color="text-blue-500" />
            <StatCard icon={Bot} label="Всего ботов" value={stats.total_bots} color="text-purple-500" />
            <StatCard icon={Activity} label="Активны сейчас" value={stats.active_bots} color="text-green-500" />
            <StatCard icon={Database} label="Сообщений" value={stats.total_messages} color="text-yellow-500" />
            
            <div className="col-span-4 bg-[#111] border border-zinc-800 rounded-2xl p-6 mt-4">
              <h3 className="text-white font-bold mb-4">Последняя активность (Сообщения)</h3>
              <div className="space-y-2">
                {stats.chart_data?.slice(0, 8).map((msg: any, i: number) => (
                  <div key={i} className="flex justify-between text-xs border-b border-zinc-900 pb-2">
                    <span className="text-zinc-500">{new Date(msg.created_at).toLocaleString()}</span>
                    <span className={msg.is_from_admin ? "text-blue-400" : "text-green-400"}>
                      {msg.is_from_admin ? "ADMIN RESPONSE" : "USER MESSAGE"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* USERS TAB */}
        {activeTab === 'users' && (
          <div className="bg-[#111] border border-zinc-800 rounded-2xl overflow-hidden">
            <table className="w-full text-left text-sm">
              <thead className="bg-zinc-900/50 text-zinc-500 uppercase text-xs font-bold">
                <tr>
                  <th className="p-4">ID / Email</th>
                  <th className="p-4">Баланс</th>
                  <th className="p-4">Регистрация</th>
                  <th className="p-4">Согласие (Email)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {users.map(u => (
                  <tr key={u.id} className="hover:bg-zinc-900/30">
                    <td className="p-4">
                      <div className="font-bold text-white">{u.username}</div>
                      <div className="text-xs text-zinc-500">{u.email}</div>
                      <div className="text-[10px] text-zinc-700 font-mono">{u.id}</div>
                    </td>
                    <td className="p-4 font-mono text-green-500">{u.balance} ₽</td>
                    <td className="p-4 text-zinc-500">{new Date(u.created_at).toLocaleDateString()}</td>
                    <td className="p-4">
                      {u.marketing_consent 
                        ? <span className="px-2 py-1 bg-green-500/10 text-green-500 rounded text-xs">ДА</span>
                        : <span className="px-2 py-1 bg-red-500/10 text-red-500 rounded text-xs">НЕТ</span>
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* BOTS TAB */}
        {activeTab === 'bots' && (
          <div className="space-y-4">
            <div className="bg-[#111] border border-zinc-800 rounded-2xl overflow-hidden">
              <table className="w-full text-left text-sm">
                <thead className="bg-zinc-900/50 text-zinc-500 uppercase text-xs font-bold">
                  <tr>
                    <th className="p-4">Бот</th>
                    <th className="p-4">Владелец</th>
                    <th className="p-4">Статус</th>
                    <th className="p-4 text-right">Действия</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {bots.map(b => (
                    <tr key={b.id} className="hover:bg-zinc-900/30">
                      <td className="p-4">
                        <div className="font-bold text-white">{b.name}</div>
                        <div className="text-[10px] text-zinc-600 font-mono">ID: {b.id}</div>
                      </td>
                      <td className="p-4">
                        <div className="text-white text-xs">{b.owner?.email}</div>
                      </td>
                      <td className="p-4">
                        <span className={`px-2 py-1 rounded text-xs font-bold ${
                          b.status === 'RUNNING' ? 'bg-green-500/10 text-green-500' : 'bg-zinc-800 text-zinc-500'
                        }`}>
                          {b.status}
                        </span>
                      </td>
                      <td className="p-4 text-right space-x-2">
                        {b.status === 'RUNNING' && (
                          <button onClick={() => handleBotAction(b.id, 'stop')} className="p-2 bg-red-500/10 text-red-500 hover:bg-red-500 hover:text-white rounded-lg transition-all" title="Force Stop">
                            <Square size={16} />
                          </button>
                        )}
                        <button onClick={() => handleBotAction(b.id, 'delete')} className="p-2 bg-zinc-800 text-zinc-500 hover:bg-red-900 hover:text-white rounded-lg transition-all" title="Delete">
                          <Trash2 size={16} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* KEYS TAB */}
        {activeTab === 'keys' && (
          <div className="max-w-xl">
            <div className="bg-[#111] border border-zinc-800 p-6 rounded-2xl">
              <h3 className="text-white font-bold mb-4">Генерация лицензионного ключа</h3>
              <div className="flex gap-4 mb-6">
                <button onClick={() => handleGenKey(1)} className="flex-1 py-3 bg-zinc-900 hover:bg-zinc-800 text-white rounded-xl border border-zinc-700 transition-colors">
                  1 Месяц
                </button>
                <button onClick={() => handleGenKey(3)} className="flex-1 py-3 bg-zinc-900 hover:bg-zinc-800 text-white rounded-xl border border-zinc-700 transition-colors">
                  3 Месяца
                </button>
                <button onClick={() => handleGenKey(12)} className="flex-1 py-3 bg-zinc-900 hover:bg-zinc-800 text-white rounded-xl border border-zinc-700 transition-colors">
                  1 Год
                </button>
              </div>
              
              {generatedKey && (
                <div className="bg-green-500/10 border border-green-500/30 p-4 rounded-xl text-center animate-in fade-in">
                  <p className="text-zinc-500 text-xs uppercase mb-1">Сгенерированный ключ:</p>
                  <p className="text-2xl font-black text-green-500 font-mono tracking-widest select-all">{generatedKey}</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// UI Components Helpers
const NavBtn = ({ icon: Icon, label, active, onClick }: any) => (
  <button 
    onClick={onClick}
    className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${
      active ? 'bg-white text-black font-bold' : 'text-zinc-500 hover:text-white hover:bg-zinc-900'
    }`}
  >
    <Icon size={18} />
    <span className="text-sm">{label}</span>
  </button>
);

const StatCard = ({ icon: Icon, label, value, color }: any) => (
  <div className="bg-[#111] border border-zinc-800 p-5 rounded-2xl flex items-center gap-4">
    <div className={`w-12 h-12 rounded-xl flex items-center justify-center bg-zinc-900 ${color}`}>
      <Icon size={24} />
    </div>
    <div>
      <div className="text-zinc-500 text-xs font-bold uppercase">{label}</div>
      <div className="text-2xl font-black text-white">{value || 0}</div>
    </div>
  </div>
);

export default AdminPanel;
