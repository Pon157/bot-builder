import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation, useParams } from 'react-router-dom';
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

// --- [ КОМПОНЕНТ: РЕДАКТОР ДЛЯ АДМИНИСТРАТОРА ] ---
/**
 * Этот компонент используется, когда админ заходит в редактор чужого бота 
 * через кнопку "Edit Bot" в админ-панели.
 */
const AdminBotEditorWrapper: React.FC = () => {
  const { botId } = useParams<{ botId: string }>();
  const [bot, setBot] = useState<BotConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  
  // Берем админ-токен, который сохранился после входа в /admin-zone
  const adminToken = localStorage.getItem('admin_token');

  useEffect(() => {
    const loadBotData = async () => {
      if (!adminToken || !botId) {
        navigate('/admin-zone');
        return;
      }

      try {
        setLoading(true);
        // Запрашиваем данные бота через специальный админский метод
        const data = await api.getBotAsAdmin(adminToken, botId);
        if (data) {
          setBot(data);
        } else {
          setError("Бот не найден или доступ запрещен");
        }
      } catch (err) {
        console.error("Admin Editor Error:", err);
        setError("Ошибка при загрузке данных бота");
      } finally {
        setLoading(false);
      }
    };

    loadBotData();
  }, [botId, adminToken, navigate]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#050505] flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-t-2 border-red-600 rounded-full animate-spin"></div>
          <span className="text-zinc-500 font-black uppercase tracking-widest text-[10px]">
            Establishing Secure Connection...
          </span>
        </div>
      </div>
    );
  }

  if (error || !bot) {
    return (
      <div className="min-h-screen bg-[#050505] flex flex-col items-center justify-center p-6">
        <div className="text-red-500 font-black uppercase mb-4">{error}</div>
        <button onClick={() => navigate('/admin-zone')} className="px-6 py-3 bg-zinc-900 rounded-xl text-white">
          Вернуться в админку
        </button>
      </div>
    );
  }

  return (
    <div className="bg-[#050505] min-h-screen p-4 md:p-12 overflow-y-auto">
      <div className="max-w-6xl mx-auto">
        {/* Хедер режима супер-админа */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-12">
          <button 
            onClick={() => navigate('/admin-zone')} 
            className="flex items-center gap-2 text-zinc-500 hover:text-white transition-colors uppercase text-[10px] font-black tracking-widest"
          >
            <ArrowLeft size={14} /> Вернуться в терминал
          </button>
          
          <div className="flex items-center gap-3 px-4 py-2 bg-red-600/10 border border-red-600/20 rounded-full">
            <div className="w-2 h-2 bg-red-600 rounded-full animate-pulse" />
            <span className="text-red-500 text-[10px] font-black uppercase tracking-widest">
              Support Mode: {bot.name}
            </span>
          </div>
        </div>

        <BotEditor 
          bot={bot} 
          onUpdate={async (updatedBot) => {
            if (adminToken) {
              await api.saveBotAsAdmin(adminToken, updatedBot);
              setBot(updatedBot);
            }
          }} 
          onDelete={() => {
            alert("Удаление ботов доступно только из списка в админ-панели");
          }}
        />
      </div>
    </div>
  );
};

// --- [ LAYOUT КОМПОНЕНТ ДЛЯ ОБЫЧНЫХ ПОЛЬЗОВАТЕЛЕЙ ] ---
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
      {/* Overlay для мобилки */}
      {isSidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 md:hidden" 
          onClick={() => setIsSidebarOpen(false)} 
        />
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
        {/* Мобильный хедер */}
        <header className="md:hidden flex items-center justify-between p-4 bg-[#121212] border-b border-zinc-800 shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 bg-blue-600 rounded flex items-center justify-center font-bold text-white text-[10px]">BE</div>
            <span className="font-black text-sm uppercase tracking-wider text-white">BotEngine <span className="text-blue-500">Pro</span></span>
          </div>
          <button onClick={() => setIsSidebarOpen(!isSidebarOpen)} className="p-2 bg-zinc-800 rounded-lg text-white">
            {isSidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </header>
        
        {/* Основной контент */}
        <main className="flex-1 overflow-y-auto p-4 md:p-12 no-scrollbar">
          <div className="max-w-6xl mx-auto">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
};

// --- [ ГЛАВНЫЙ КОМПОНЕНТ ПРИЛОЖЕНИЯ ] ---
const App: React.FC = () => {
  const [user, setUser] = useState<User | null>(null);
  const [bots, setBots] = useState<BotConfig[]>([]);
  const [selectedBotId, setSelectedBotId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  // Синхронизация данных пользователя и его ботов
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

  // Инициализация при загрузке страницы
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
        console.error("Init error:", e);
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
    
    const newBotId = `bot_${Math.random().toString(36).substring(2, 11)}`;
    
    const newBot: BotConfig = {
      id: newBotId,
      owner_id: user.id,
      name: name,
      token: token,
      status: BotStatus.IDLE,
      created_at: Date.now(),
      license_expires_at: Date.now() + (3 * 24 * 3600 * 1000), // 3 дня триала
      usersCount: 0,
      description: 'Новый бот BotEngine',
      adminChatId: '',
      welcomeMessage: `Добро пожаловать в ${name}!`,
      logs: [],
      connectedUsers: [],
      subscribers: [],
      triggers: [],
      buttons: [],
      stats: { 
        totalMessages: 0, incomingToday: 0, outgoingToday: 0, 
        activeUsers24h: 0, bannedCount: 0, history: [] 
      },
      settings: { 
        useTopics: false, 
        topicPerRequest: false, 
        anonymousTopics: false,
        autoApproveJoin: false, 
        forwardToAdmin: true, 
        antiSpam: true, 
        rateLimit: 1, 
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
    } catch (e) {
      console.error("Create bot error:", e);
      alert("Ошибка при создании бота. Проверьте соединение с сервером.");
    }
  };

  if (loading) {
    return (
      <div className="h-screen bg-[#0a0a0a] flex items-center justify-center">
        <div className="w-10 h-10 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        {/* --- [ РОУТЫ БЕЗ ЛАЙАУТА ] --- */}
        
        {/* 1. Авторизация пользователей */}
        <Route 
          path="/auth" 
          element={!user ? <Auth onLogin={handleLogin} /> : <Navigate to="/dashboard" replace />} 
        />

        {/* 2. Админ-панель (Терминал) */}
        <Route 
           path="/admin-zone" 
           element={<AdminPanel onLogout={() => window.location.href = '/auth'} />} 
        />

        {/* 3. Редактор админа (Режим поддержки) */}
        <Route 
          path="/admin/editor/:botId" 
          element={<AdminBotEditorWrapper />} 
        />

        {/* --- [ ЗАЩИЩЕННЫЕ РОУТЫ (С ЛАЙАУТОМ) ] --- */}
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
                    <Profile 
                      user={user} 
                      bots={bots} 
                      onUpdateBots={(updated) => { setBots(updated); syncData(user.id); }} 
                    />
                  } />
                  
                  <Route path="/editor" element={
                    (() => {
                      const currentBot = bots.find(b => b.id === selectedBotId);
                      return currentBot ? (
                        <BotEditor 
                          bot={currentBot} 
                          onUpdate={(updated) => setBots(prev => prev.map(b => b.id === updated.id ? updated : b))} 
                          onDelete={async () => { 
                            if (window.confirm("Удалить бота навсегда?")) {
                              await api.deleteBot(user.id, selectedBotId!); 
                              syncData(user.id);
                              navigate('/dashboard');
                            }
                          }} 
                        />
                      ) : <Navigate to="/dashboard" replace />;
                    })()
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

      <CreateBotModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
        onSubmit={handleCreateBot} 
      />
    </BrowserRouter>
  );
};

export default App;
