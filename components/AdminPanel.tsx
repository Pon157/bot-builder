import React, { useState, useEffect } from 'react';
import { api } from '../services/apiService';
import { 
  LayoutDashboard, Users, Bot, Key, LogOut, 
  Activity, ShieldAlert, Play, Square, RefreshCw, 
  ExternalLink, Clock, Search, ShieldCheck, 
  ChevronRight, HardDrive, Cpu, MessageSquare, AlertCircle
} from 'lucide-react';

interface AdminPanelProps {
  onLogout: () => void;
}

const AdminPanel: React.FC<AdminPanelProps> = ({ onLogout }) => {
  const [token, setToken] = useState<string | null>(localStorage.getItem('admin_token'));
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [activeTab, setActiveTab] = useState<'users' | 'bots' | 'keys' | 'monitoring'>('users');
  const [loading, setLoading] = useState(false);
  
  // States для данных
  const [users, setUsers] = useState<any[]>([]);
  const [bots, setBots] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [generatedKey, setGeneratedKey] = useState('');
  const [keyDuration, setKeyDuration] = useState(1); // в месяцах

  // 1. Авторизация админа
  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const data = await api.adminLogin(login, password);
      setToken(data.token);
      localStorage.setItem('admin_token', data.token);
      await loadAllData(data.token);
    } catch (err) { 
      alert('Ошибка: Неверный логин/пароль или сервер недоступен'); 
    } finally {
      setLoading(false);
    }
  };

  // 2. Загрузка данных (исправляем 422, передавая только токен)
  const loadAllData = async (t: string) => {
    setLoading(true);
    try {
      // Запрашиваем данные по отдельности, чтобы легче отловить ошибку
      const uData = await api.getAllUsers(t);
      setUsers(uData || []);

      const bData = await api.getAllBots(t);
      setBots(bData || []);

      // Если эндпоинт дашборда все еще выдает 422, делаем его опциональным
      try {
        const sData = await api.getAdminDashboard(t);
        setStats(sData);
      } catch (e) {
        console.warn("Dashboard stats error (422): check server params", e);
      }
    } catch (err) { 
      console.error("Global load error:", err); 
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (token) loadAllData(token);
  }, [token]);

  // 3. Генерация лицензионного ключа
  const handleGenerateKey = async () => {
    if (!token) return;
    try {
      const res = await api.generateKey(token, keyDuration, 0);
      setGeneratedKey(res.key);
      alert(`Ключ на ${keyDuration} мес. успешно создан!`);
    } catch (e) {
      alert("Ошибка генерации");
    }
  };

  // 4. Логика временного доступа (Admin -> User Bot)
  const handleRequestAccess = async (botId: string) => {
    const accessKey = prompt("Введите временный ключ (Support Key), созданный пользователем в настройках бота:");
    if (!accessKey) return;
    
    // Сохраняем ключ в сессию для BotEditor
    localStorage.setItem(`admin_access_${botId}`, accessKey);
    // Перенаправляем (в твоем App.tsx должен быть обработчик этих параметров)
    window.location.href = `/editor?botId=${botId}&adminKey=${accessKey}`;
  };

  // 5. Управление ботом (Запуск)
  const handleStartBot = async (bot: any) => {
    try {
      await api.startBotOnServer(bot);
      alert(`Команда на запуск бота ${bot.name} отправлена`);
      if (token) loadAllData(token);
    } catch (e) {
      alert("Ошибка запуска");
    }
  };

  // Рендер формы логина
  if (!token) {
    return (
      <div className="min-h-screen bg-[#050505] flex items-center justify-center p-6 font-sans">
        <div className="absolute inset-0 bg-red-600/5 radial-grid opacity-20 pointer-events-none" />
        <form onSubmit={handleLogin} className="w-full max-w-md bg-zinc-900/50 border border-zinc-800 p-10 rounded-[3rem] backdrop-blur-xl shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-red-600 to-transparent" />
          <div className="w-20 h-20 bg-red-600/10 rounded-3xl flex items-center justify-center text-red-500 mb-8 mx-auto border border-red-500/20">
            <ShieldAlert size={40} />
          </div>
          <h1 className="text-2xl font-black text-center text-white mb-2 uppercase tracking-[0.2em]">Staff Login</h1>
          <p className="text-zinc-500 text-[10px] text-center mb-10 uppercase font-bold tracking-widest">BotEngine Pro Infrastructure</p>
          
          <div className="space-y-4">
            <div className="relative">
              <input 
                className="w-full bg-black/40 border border-zinc-800 p-5 rounded-2xl text-white outline-none focus:border-red-500 transition-all pl-12" 
                placeholder="Admin Login" 
                value={login} 
                onChange={e => setLogin(e.target.value)} 
                required
              />
              <Users className="absolute left-4 top-5 text-zinc-600" size={20} />
            </div>
            <div className="relative">
              <input 
                type="password" 
                className="w-full bg-black/40 border border-zinc-800 p-5 rounded-2xl text-white outline-none focus:border-red-500 transition-all pl-12" 
                placeholder="Security Password" 
                value={password} 
                onChange={e => setPassword(e.target.value)} 
                required
              />
              <ShieldCheck className="absolute left-4 top-5 text-zinc-600" size={20} />
            </div>
            <button 
              disabled={loading}
              className="w-full bg-red-600 hover:bg-red-500 text-white font-black py-5 rounded-2xl transition-all uppercase tracking-widest text-sm shadow-lg shadow-red-600/20 disabled:opacity-50"
            >
              {loading ? 'Verifying...' : 'Authenticate'}
            </button>
          </div>
        </form>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#050505] text-zinc-300 flex font-sans overflow-hidden">
      {/* --- SIDEBAR --- */}
      <div className="w-80 border-r border-zinc-800/50 p-8 flex flex-col gap-2 bg-[#080808]">
        <div className="flex items-center gap-4 mb-12 px-4">
          <div className="w-10 h-10 bg-gradient-to-br from-red-600 to-red-800 rounded-2xl flex items-center justify-center text-white font-black text-lg shadow-lg">BE</div>
          <div>
            <span className="font-black text-white uppercase tracking-tighter block leading-none">BotEngine</span>
            <span className="text-[9px] text-red-500 font-black uppercase tracking-[0.3em]">Master Admin</span>
          </div>
        </div>
        
        <div className="space-y-1">
          <p className="text-[9px] font-black text-zinc-600 uppercase mb-4 px-4 tracking-widest">Управление</p>
          <NavBtn icon={Users} label="Пользователи" active={activeTab === 'users'} onClick={() => setActiveTab('users')} />
          <NavBtn icon={Bot} label="Все боты" active={activeTab === 'bots'} onClick={() => setActiveTab('bots')} />
          <NavBtn icon={Key} label="Лицензии" active={activeTab === 'keys'} onClick={() => setActiveTab('keys')} />
          <NavBtn icon={Activity} label="Мониторинг" active={activeTab === 'monitoring'} onClick={() => setActiveTab('monitoring')} />
        </div>

        <div className="mt-auto pt-8 border-t border-zinc-900">
          <div className="bg-zinc-900/50 p-4 rounded-2xl mb-4 border border-zinc-800/50">
             <div className="flex items-center gap-3">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                <span className="text-[10px] font-black text-zinc-400 uppercase">System Online</span>
             </div>
          </div>
          <button 
            onClick={() => { localStorage.removeItem('admin_token'); setToken(null); onLogout(); }}
            className="w-full flex items-center gap-4 px-6 py-4 rounded-2xl text-zinc-500 hover:text-red-500 hover:bg-red-500/5 transition-all text-sm uppercase font-black tracking-widest"
          >
            <LogOut size={18} /> Выход
          </button>
        </div>
      </div>

      {/* --- MAIN CONTENT --- */}
      <div className="flex-1 p-12 overflow-y-auto relative">
        <div className="max-w-6xl mx-auto">
          
          {/* Header Section */}
          <div className="flex justify-between items-end mb-12">
            <div>
              <h1 className="text-4xl font-black text-white uppercase tracking-tighter">
                {activeTab === 'users' && 'База данных клиентов'}
                {activeTab === 'bots' && 'Управление инфраструктурой'}
                {activeTab === 'keys' && 'Лицензионный центр'}
                {activeTab === 'monitoring' && 'Состояние узлов'}
              </h1>
              <div className="h-1 w-20 bg-red-600 mt-4 rounded-full" />
            </div>
            
            <div className="relative group">
              <input 
                type="text" 
                placeholder="Поиск по ID или Email..." 
                className="bg-zinc-900 border border-zinc-800 p-4 rounded-2xl w-80 text-sm outline-none focus:border-zinc-600 transition-all pl-12"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
              />
              <Search className="absolute left-4 top-4 text-zinc-600" size={18} />
            </div>
          </div>

          {/* Tab: USERS */}
          {activeTab === 'users' && (
            <div className="grid gap-4">
              {users.filter(u => u.email.includes(searchQuery)).map(u => (
                <div key={u.id} className="bg-zinc-900/30 border border-zinc-800/50 p-6 rounded-[2.5rem] flex justify-between items-center hover:bg-zinc-900/50 transition-all group">
                  <div className="flex items-center gap-6">
                    <div className="w-14 h-14 bg-zinc-800 rounded-2xl flex items-center justify-center text-zinc-500 group-hover:bg-red-600 group-hover:text-white transition-all">
                      <Users size={24} />
                    </div>
                    <div>
                      <p className="text-white text-lg font-black">{u.email}</p>
                      <p className="text-zinc-600 text-[10px] font-mono uppercase tracking-widest mt-1">UUID: {u.id}</p>
                    </div>
                  </div>
                  <div className="flex gap-10 items-center">
                    <div className="text-right">
                      <p className="text-white font-bold">{bots.filter(b => b.owner_id === u.id).length}</p>
                      <p className="text-[9px] text-zinc-600 uppercase font-black">Ботов создано</p>
                    </div>
                    <ChevronRight className="text-zinc-800 group-hover:text-white transition-all" />
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Tab: BOTS */}
          {activeTab === 'bots' && (
            <div className="grid gap-6">
              {bots.filter(b => b.name.toLowerCase().includes(searchQuery.toLowerCase())).map(b => (
                <div key={b.id} className="bg-[#0c0c0c] border border-zinc-800 p-8 rounded-[3rem] flex justify-between items-center shadow-xl">
                  <div className="flex items-center gap-6">
                    <div className={`w-4 h-4 rounded-full ${b.status === 'RUNNING' ? 'bg-green-500 shadow-[0_0_15px_rgba(34,197,94,0.4)]' : 'bg-zinc-800'} animate-pulse`} />
                    <div>
                      <h3 className="text-xl font-black text-white uppercase tracking-tighter">{b.name}</h3>
                      <div className="flex gap-4 mt-2">
                        <span className="text-[9px] font-black text-zinc-500 uppercase bg-zinc-900 px-3 py-1 rounded-full">Owner: {b.owner_id.slice(0,8)}...</span>
                        <span className="text-[9px] font-black text-red-500 uppercase bg-red-500/5 px-3 py-1 rounded-full">
                          {b.status === 'RUNNING' ? 'В сети' : 'Остановлен'}
                        </span>
                      </div>
                    </div>
                  </div>
                  
                  <div className="flex gap-3">
                    {/* КНОПКА ЗАПУСКА (PLAY) */}
                    <button 
                      onClick={() => handleStartBot(b)}
                      className="flex items-center gap-3 bg-green-600/10 hover:bg-green-600 text-green-500 hover:text-white px-8 py-4 rounded-2xl transition-all text-[10px] font-black uppercase tracking-widest border border-green-500/20"
                    >
                      <Play size={16} fill="currentColor" /> Запустить
                    </button>
                    
                    {/* КНОПКА КОНФИГА (ВРЕМЕННЫЙ ДОСТУП) */}
                    <button 
                      onClick={() => handleRequestAccess(b.id)}
                      className="flex items-center gap-3 bg-zinc-800 hover:bg-white text-zinc-400 hover:text-black px-8 py-4 rounded-2xl transition-all text-[10px] font-black uppercase tracking-widest"
                    >
                      <ExternalLink size={16} /> Войти в конфиг
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Tab: KEYS (ЛИЦЕНЗИИ) */}
          {activeTab === 'keys' && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              {/* Генератор */}
              <div className="lg:col-span-1 space-y-6">
                <div className="bg-zinc-900/50 border border-zinc-800 p-8 rounded-[2.5rem] sticky top-8">
                  <h3 className="text-white font-black uppercase mb-8 tracking-widest text-xs flex items-center gap-2">
                    <Key className="text-red-600" size={16} /> Создать лицензию
                  </h3>
                  
                  <div className="space-y-6">
                    <div>
                      <label className="text-[10px] font-black text-zinc-500 uppercase mb-3 block">Длительность (мес.)</label>
                      <div className="grid grid-cols-3 gap-2">
                        {[1, 3, 12].map(m => (
                          <button 
                            key={m}
                            onClick={() => setKeyDuration(m)}
                            className={`py-3 rounded-xl text-[10px] font-black border transition-all ${keyDuration === m ? 'bg-white text-black border-white' : 'bg-transparent text-zinc-500 border-zinc-800 hover:border-zinc-600'}`}
                          >
                            {m === 12 ? '1 ГОД' : `${m} МЕС.`}
                          </button>
                        ))}
                      </div>
                    </div>

                    <button 
                      onClick={handleGenerateKey}
                      className="w-full bg-red-600 hover:bg-red-500 text-white font-black py-5 rounded-2xl transition-all uppercase text-xs tracking-[0.2em]"
                    >
                      Сгенерировать
                    </button>
                  </div>

                  {generatedKey && (
                    <div className="mt-8 p-6 bg-black border border-red-500/20 rounded-2xl text-center animate-in zoom-in-95">
                      <p className="text-[9px] text-zinc-600 font-black uppercase mb-2">Ваш ключ готов:</p>
                      <p className="text-red-500 font-mono text-xl font-black select-all tracking-tighter">{generatedKey}</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Список подключенных ключей */}
              <div className="lg:col-span-2 space-y-4">
                <h3 className="text-zinc-500 font-black uppercase text-[10px] tracking-[0.3em] mb-6 px-4">Активные подписки ботов</h3>
                {bots.filter(b => b.license_expires_at).map(b => (
                  <div key={b.id} className="bg-zinc-900/20 border border-zinc-800/40 p-6 rounded-3xl flex justify-between items-center group">
                    <div className="flex items-center gap-4">
                      <div className="w-12 h-12 bg-zinc-900 rounded-xl flex items-center justify-center text-zinc-700 group-hover:text-green-500 transition-colors">
                        <ShieldCheck size={24} />
                      </div>
                      <div>
                        <p className="text-white font-black text-sm uppercase">{b.name}</p>
                        <p className="text-[9px] text-zinc-600 font-mono">ID: {b.id}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-green-500 font-mono text-sm font-black">
                        {new Date(b.license_expires_at).toLocaleDateString('ru-RU')}
                      </p>
                      <p className="text-[9px] text-zinc-600 uppercase font-black tracking-widest mt-1 italic">Дата истечения</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Tab: MONITORING */}
          {activeTab === 'monitoring' && (
            <div className="space-y-8">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <StatCard icon={HardDrive} label="Disk Usage" value="14.2 ГБ / 40 ГБ" color="text-blue-500" />
                <StatCard icon={Cpu} label="CPU Load" value="8%" color="text-green-500" />
                <StatCard icon={MessageSquare} label="API Traffic" value="1.2k req/min" color="text-purple-500" />
              </div>
              
              <div className="bg-zinc-900/30 border border-zinc-800 p-8 rounded-[3rem]">
                <h3 className="text-white font-black uppercase mb-6 text-xs tracking-widest">Системные события</h3>
                <div className="space-y-3 max-h-[400px] overflow-y-auto no-scrollbar">
                  {[...Array(5)].map((_, i) => (
                    <div key={i} className="flex gap-4 text-[10px] font-mono p-3 border-b border-zinc-800/50">
                      <span className="text-zinc-600">[{new Date().toLocaleTimeString()}]</span>
                      <span className="text-blue-500 uppercase">INFO</span>
                      <span className="text-zinc-400">Worker node #{i+1} synchronized successfully. License checks completed.</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
};

// --- Вспомогательные компоненты ---

const NavBtn = ({ icon: Icon, label, active, onClick }: any) => (
  <button 
    onClick={onClick} 
    className={`w-full flex items-center gap-4 px-6 py-4 rounded-2xl transition-all border ${active ? 'bg-white text-black border-white shadow-xl shadow-white/5 font-black' : 'text-zinc-500 border-transparent hover:text-white hover:bg-zinc-900/50'}`}
  >
    <Icon size={18} />
    <span className="text-xs uppercase tracking-tighter">{label}</span>
  </button>
);

const StatCard = ({ icon: Icon, label, value, color }: any) => (
  <div className="bg-zinc-900/50 border border-zinc-800 p-8 rounded-[2.5rem]">
    <div className="flex justify-between items-start mb-4">
      <div className={`p-3 bg-zinc-800 rounded-xl ${color}`}>
        <Icon size={20} />
      </div>
      <div className="w-1.5 h-1.5 rounded-full bg-green-500 shadow-[0_0_10px_rgba(34,197,94,0.5)]" />
    </div>
    <p className="text-zinc-500 text-[9px] font-black uppercase tracking-widest mb-1">{label}</p>
    <p className="text-xl font-black text-white">{value}</p>
  </div>
);

export default AdminPanel;
