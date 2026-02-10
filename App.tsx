import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { BotConfig, BotStatus, User } from './types';
import Dashboard from './components/Dashboard';
import BotEditor from './components/BotEditor';
import Sidebar from './components/Sidebar';
import BroadcastManager from './components/BroadcastManager';
import Auth from './components/Auth';
import Profile from './components/Profile';
import CreateBotModal from './components/CreateBotModal';
import { api } from './services/apiService';
import { Menu, X } from 'lucide-react';

// Вспомогательный компонент для обертки основного контента (Layout)
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

  // Определяем активную вкладку на основе URL для синхронизации с Sidebar
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
    // ... логика создания объекта newBot (как в твоем исходном коде) ...
    const newBot: BotConfig = {
        id: newBotId,
        owner_id: user.id,
        name,
        token,
        status: BotStatus.IDLE,
        created_at: Date.now(),
        license_expires_at: Date.now() + (3 * 24 * 3600 * 1000),
        usersCount: 0,
        description: 'Новый бот BotEngine',
        adminChatId: '',
        welcomeMessage: `Добро пожаловать в ${name}!`,
        logs: [],
        connectedUsers: [],
        subscribers: [],
        triggers: [],
        buttons: [],
        stats: { totalMessages: 0, incomingToday: 0, outgoingToday: 0, activeUsers24h: 0, bannedCount: 0, history: [] },
        settings: { 
          useTopics: false, 
          topicPerRequest: false, 
          anonymousTopics: false,
          autoApproveJoin: false, 
          forwardToAdmin: true, 
          antiSpam: true, 
          rateLimit: 15, 
          showUserInfo: true, 
          showUsername: true, 
          autoBanThreshold: 0,
          showHeaderId: true,
          showHeaderName: true,
          showHeaderUsername: true
        }
      };

    try {
      await api.saveBot(user.id, newBot);
      setBots(prev => [...prev, newBot]);
      setSelectedBotId(newBotId);
      setIsModalOpen(false);
      // После создания перекидываем в редактор через навигацию (нужен useNavigate, который ниже в роутах)
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

        {/* Защищенные роуты внутри MainLayout */}
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
