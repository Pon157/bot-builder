import React, { useState, useEffect, useParams } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { BotConfig, BotStatus, User } from './types';
import Dashboard from './components/Dashboard';
import BotEditor from './components/BotEditor';
import Sidebar from './components/Sidebar';
import BroadcastManager from './components/BroadcastManager';
import Auth from './components/Auth';
import Profile from './components/Profile';
import CreateBotModal from './components/CreateBotModal';
import AdminPanel from './components/AdminPanel';
import { api } from './services/apiService';
import { Menu, X, ArrowLeft } from 'lucide-react';

// --- СПЕЦИАЛЬНЫЙ КОМПОНЕНТ: Редактор для Админа ---
// Позволяет редактировать любого бота по ID, используя токен админа из localStorage
const AdminBotEditorWrapper = () => {
  const { botId } = useParams<{ botId: string }>();
  const [bot, setBot] = useState<BotConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const adminToken = localStorage.getItem('admin_token');

  useEffect(() => {
    const loadBotAsAdmin = async () => {
      if (!adminToken || !botId) {
        navigate('/admin-zone');
        return;
      }
      try {
        const data = await api.getBotAsAdmin(adminToken, botId);
        if (data) setBot(data);
        else navigate('/admin-zone');
      } catch (e) {
        console.error("Admin access error:", e);
        navigate('/admin-zone');
      } finally {
        setLoading(false);
      }
    };
    loadBotAsAdmin();
  }, [botId, adminToken, navigate]);

  if (loading) return (
    <div className="min-h-screen bg-[#050505] flex items-center justify-center">
      <div className="text-zinc-500 font-black uppercase tracking-widest animate-pulse">Loading Admin Context...</div>
    </div>
  );

  if (!bot) return null;

  return (
    <div className="bg-[#050505] min-h-screen p-4 md:p-12 overflow-y-auto">
      <div className="max-w-6xl mx-auto">
        <button 
          onClick={() => navigate('/admin-zone')} 
          className="mb-8 flex items-center gap-2 text-zinc-500 hover:text-white transition-colors uppercase text-[10px] font-black tracking-widest"
        >
          <ArrowLeft size={14} /> Back to Admin Terminal
        </button>
        
        <div className="bg-red-600/5 border border-red-600/20 p-4 rounded-2xl mb-8 flex items-center gap-3">
          <div className="w-2 h-2 bg-red-600 rounded-full animate-pulse" />
          <span className="text-red-500 text-[10px] font-black uppercase tracking-widest">
            Privileged Access Mode: Editing Bot {bot.name} (ID: {bot.id})
          </span>
        </div>

        <BotEditor 
          bot={bot} 
          onUpdate={async (updated) => {
            if (adminToken) {
              await api.saveBotAsAdmin(adminToken, updated);
              setBot(updated);
            }
          }} 
          onDelete={() => alert("Admin cannot delete bots from this view. Use the main Admin Panel list.")}
        />
      </div>
    </div>
  );
};

// --- LAYOUT КОМПОНЕНТ ---
const MainLayout: React.FC<{
  user: User;
  bots: BotConfig[];
  selectedBotId: string | null;
  setSelectedBotId: (id: string | null) => void;
  setIsModalOpen: (open: boolean) => void;
  onLogout: () => void;
  children: React.ReactNode;
}> = ({ user, bots, selectedBotId, setSelectedBotId, setIsModalOpen, onLogout, children }) => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const activeTab = location.pathname.split('/')[1] || 'dashboard';

  return (
    <div className="flex h-screen bg-[#0a0a0a] text-zinc-300 overflow-hidden font-sans relative">
      {isSidebarOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 md:hidden" onClick={() => setIsSidebarOpen(false)} />
      )}
      
      <Sidebar 
        activeTab={activeTab as any} 
        setActiveTab={(tab) => { navigate(`/${tab}`); setIsSidebarOpen(false); }} 
        bots={bots} 
        selectedBotId={selectedBotId} 
        setSelectedBotId={(id) => { setSelectedBotId(id); navigate('/editor'); setIsSidebarOpen(false); }} 
        onAddBot={() => { setIsModalOpen(true); setIsSidebarOpen(false); }} 
        user={user} 
        onLogout={onLogout} 
        isOpen={isSidebarOpen} 
      />

      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        <header className="md:hidden flex items-center justify-between p-4 bg-[#121212] border-b border-zinc-800 shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 bg-blue-600 rounded flex items-center justify-center font-bold text-white text-[10px]">BE</div>
            <span className="font-black text-sm uppercase tracking-wider text-white">BotEngine <span className="text-blue-500">Pro</span></span>
          </div>
          <button onClick={() => setIsSidebarOpen(!isSidebarOpen)} className="p-2 bg-zinc-800 rounded-lg text-white">
            {isSidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </header>
        
        <main className="flex-1 overflow-y-auto p-4 md:p-12 no-scrollbar">
          <div className="max-w-6xl mx-auto">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
};

// --- ГЛАВНЫЙ КОМПОНЕНТ APP ---
const App: React.FC = () => {
  const [user, setUser] = useState<User | null>(null);
  const [bots, setBots] = useState<BotConfig[]>([]);
  const [selectedBotId, setSelectedBotId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  const syncData = async (userId: string) => {
    try {
      const [serverBots, updatedUser] = await Promise.all([
        api.getBots(userId),
        api.getUser(userId)
      ]);
      setBots(serverBots || []);
      if (updatedUser) {
        setUser(updatedUser);
        localStorage.setItem('active_session_user', JSON.stringify(updatedUser));
      }
    } catch (e) {
      console.error("Sync error:", e);
    }
  };

  useEffect(() => {
    const init = async () => {
      try {
        const savedUserStr = localStorage.getItem('active_session_user');
        if (savedUserStr && savedUserStr !== "undefined" && savedUserStr !== "null") {
          const parsedUser = JSON.parse(savedUserStr);
          if (parsedUser && parsedUser.id) {
            setUser(parsedUser);
            await syncData(parsedUser.id);
          }
        }
      } catch (e) {
        localStorage.removeItem('active_session_user');
      } finally {
        setLoading(false);
      }
    };
    init();
  }, []);

  const handleLogin = async (newUser: User) => {
    setUser(newUser);
    localStorage.setItem('active_session_user', JSON.stringify(newUser));
    await syncData(newUser.id);
  };

  const handleLogout = () => {
    setUser(null);
    localStorage.removeItem('active_session_user');
    setBots([]);
    setSelectedBotId(null);
  };

  const handleCreateBot = async (name: string, token: string) => {
    if (!user) return;
    const newBotId = `bot_${Math.random().toString(36).substr(2, 9)}`;
    const newBot: any = { // Используем any для краткости, в идеале BotConfig
      id: newBotId,
      owner_id: user.id,
      name,
      token,
      status: BotStatus.IDLE,
      created_at: Date.now(),
      license_expires_at: Date.now() + (3 * 24 * 3600 * 1000),
      settings: { 
        useTopics: false, 
        forwardToAdmin: true, 
        antiSpam: true, 
        rateLimit: 15, 
        showUserInfo: true, 
        showUsername: true 
      }
    };

    try {
      await api.saveBot(user.id, newBot);
      setBots(prev => [...prev, newBot]);
      setSelectedBotId(newBotId);
      setIsModalOpen(false);
    } catch (e) {
      alert("Ошибка при создании бота");
    }
  };

  if (loading) return null;

  return (
    <BrowserRouter>
      <Routes>
        {/* Публичный роут авторизации */}
        <Route 
          path="/auth" 
          element={!user ? <Auth onLogin={handleLogin} /> : <Navigate to="/dashboard" replace />} 
        />

        {/* СЕКРЕТНЫЙ РОУТ ДЛЯ АДМИНОВ */}
        <Route 
           path="/admin-zone" 
           element={<AdminPanel onLogout={() => window.location.href = '/auth'} />} 
        />

        {/* СПЕЦИАЛЬНЫЙ РОУТ: Редактирование бота админом */}
        <Route 
          path="/admin/editor/:botId" 
          element={<AdminBotEditorWrapper />} 
        />

        {/* Защищенные роуты приложения */}
        <Route 
          path="*" 
          element={
            user ? (
              <MainLayout 
                user={user} 
                bots={bots} 
                selectedBotId={selectedBotId} 
                setSelectedBotId={setSelectedBotId}
                setIsModalOpen={setIsModalOpen}
                onLogout={handleLogout}
              >
                <Routes>
                  <Route path="/dashboard" element={
                    <Dashboard 
                      bots={bots} 
                      onSelectBot={(id) => { setSelectedBotId(id); }} 
                      onAddBot={() => setIsModalOpen(true)} 
                    />
                  } />
                  <Route path="/profile" element={
                    <Profile user={user} bots={bots} onUpdateBots={(updated) => { setBots(updated); syncData(user.id); }} />
                  } />
                  <Route path="/editor" element={
                    bots.find(b => b.id === selectedBotId) ? (
                      <BotEditor 
                        bot={bots.find(b => b.id === selectedBotId)!} 
                        onUpdate={(u) => setBots(prev => prev.map(b => b.id === u.id ? u : b))} 
                        onDelete={() => { api.deleteBot(user.id, selectedBotId!); syncData(user.id); }} 
                      />
                    ) : <Navigate to="/dashboard" replace />
                  } />
                  <Route path="/broadcast" element={<BroadcastManager bots={bots} />} />
                  <Route path="/" element={<Navigate to="/dashboard" replace />} />
                </Routes>
              </MainLayout>
            ) : (
              <Navigate to="/auth" replace />
            )
          } 
        />
      </Routes>
      <CreateBotModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} onSubmit={handleCreateBot} />
    </BrowserRouter>
  );
};

export default App;
