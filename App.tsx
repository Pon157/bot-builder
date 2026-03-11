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
import Landing from './components/Landing';
import Careers from './components/Careers';
import MiniAppBuilder from './components/MiniAppBuilder';
import MiniAppRenderer from './components/MiniAppRenderer';
import ChatPlatform from './components/ChatPlatform';
import ChatSiteApp from './components/ChatSiteApp';
import RefundPolicy from './components/RefundPolicy'; 
import Contacts from './components/Contacts';
import SuccessPage from './components/Success';
import { api } from './services/apiService';
import { Menu, X, ArrowLeft, ShieldAlert } from 'lucide-react';

// ── NEW: Free Plan & Ads ──────────────────────────────────────────────────
import FreePlan from './components/FreePlan';
import AdsAuth from './components/AdsAuth';
import AdsPortal from './components/AdsPortal';
import Referrals from './components/Referrals';

// --- [ РЕФЕРАЛЬНЫЙ РЕДИРЕКТ ] ---
// Роут /ref/:refCode сохраняет код в localStorage и кидает на /auth
const RefRedirect: React.FC = () => {
  const { refCode } = useParams<{ refCode: string }>();
  const navigate = useNavigate();
  useEffect(() => {
    if (refCode) {
      localStorage.setItem('pending_referral_code', refCode);
    }
    navigate('/auth', { replace: true });
  }, [refCode, navigate]);
  return null;
};

// --- [ КОМПОНЕНТ: РЕДАКТОР ДЛЯ АДМИНИСТРАТОРА ] ---
const AdminBotEditorWrapper: React.FC = () => {
  const { botId } = useParams<{ botId: string }>();
  const [bot, setBot] = useState<BotConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  
  const adminToken = localStorage.getItem('admin_token');

  const loadBotData = async () => {
    if (!adminToken || !botId) {
      navigate('/admin-zone');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await api.getBotAsAdmin(adminToken, botId);
      if (data) {
        setBot(data);
      } else {
        setError("Доступ закрыт. Пользователь должен сгенерировать ключ доступа в своей панели.");
      }
    } catch (err: any) {
      setError(err.message || "Ошибка авторизации в режиме поддержки");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadBotData();
  }, [botId, adminToken]);

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
      <div className="min-h-screen bg-[#050505] flex flex-col items-center justify-center p-6 text-center">
        <ShieldAlert size={48} className="text-red-600 mb-6 opacity-50" />
        <div className="text-red-500 font-black uppercase mb-2 tracking-widest">Access Denied</div>
        <div className="text-zinc-500 text-xs max-w-xs mb-8 uppercase font-bold leading-relaxed">
          {error || "Для редактирования этого бота требуется активный временный ключ доступа."}
        </div>
        <div className="flex gap-4">
          <button onClick={() => navigate('/admin-zone')} 
            className="px-8 py-4 bg-zinc-900 border border-zinc-800 rounded-2xl text-white text-[10px] font-black uppercase tracking-widest hover:bg-zinc-800 transition-all">
            В терминал
          </button>
          <button onClick={loadBotData}
            className="px-8 py-4 bg-red-600 rounded-2xl text-white text-[10px] font-black uppercase tracking-widest hover:bg-red-700 transition-all shadow-lg shadow-red-600/20">
            Повторить
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-[#050505] min-h-screen p-4 md:p-12 overflow-y-auto">
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-12">
          <button onClick={() => navigate('/admin-zone')} 
            className="flex items-center gap-2 text-zinc-500 hover:text-white transition-colors uppercase text-[10px] font-black tracking-widest group">
            <ArrowLeft size={14} className="group-hover:-translate-x-1 transition-transform" /> 
            Back to Terminal
          </button>
          <div className="flex items-center gap-4">
            <div className="flex flex-col items-end">
              <span className="text-white text-[10px] font-black uppercase tracking-widest">{bot.name}</span>
              <span className="text-zinc-600 text-[8px] font-bold uppercase tracking-tighter">Support Session Active</span>
            </div>
            <div className="flex items-center gap-3 px-4 py-2 bg-red-600/10 border border-red-600/20 rounded-full">
              <div className="w-2 h-2 bg-red-600 rounded-full animate-pulse" />
              <span className="text-red-500 text-[10px] font-black uppercase tracking-widest">Support Mode</span>
            </div>
          </div>
        </div>

        <BotEditor 
          bot={bot} 
          isAdminMode={true} 
          onUpdate={async (updatedBot) => {
            if (adminToken) {
              try {
                await api.saveBotAsAdmin(adminToken, updatedBot);
                setBot(updatedBot);
              } catch (e) {
                alert("Ошибка сохранения: сессия поддержки могла истечь");
              }
            }
          }} 
          onDelete={() => {
            console.warn("Delete attempt in support mode blocked.");
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

// --- [ ГЛАВНЫЙ КОМПОНЕНТ ПРИЛОЖЕНИЯ ] ---
const App: React.FC = () => {
  const [user, setUser] = useState<User | null>(null);
  const [bots, setBots] = useState<BotConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedBotId, setSelectedBotId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const syncData = async (userId: string) => {
    try {
      const botsData = await api.getBots(userId);
      if (botsData) setBots(botsData);
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
        useTopics: false, topicPerRequest: false, anonymousTopics: false,
        autoApproveJoin: false, forwardToAdmin: true, antiSpam: true, 
        rateLimit: 1, showUserInfo: true, showUsername: true, autoBanThreshold: 0,
        showHeaderId: true, showHeaderName: true, showHeaderUsername: true
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
        {/* --- ПУБЛИЧНЫЕ РОУТЫ --- */}
        {/* Реферальный роут: сохраняет код и редиректит на /auth */}
        <Route path="/ref/:refCode" element={<RefRedirect />} />
        <Route path="/" element={<Landing />} />
        <Route path="/app/:appId" element={<MiniAppRenderer />} />
        <Route path="/chat/:slug" element={<ChatSiteApp />} />
        <Route path="/careers" element={<Careers />} />
        <Route path="/refund" element={<RefundPolicy />} />
        <Route path="/contacts" element={<Contacts />} />
        <Route path="/success" element={<SuccessPage />} />

        {/* ── FREE PLAN ─────────────────────────────────────────────── */}
        {/*
          /free — бесплатный план (не требует Pro лицензии, но требует авторизации)
          Аккаунт берётся из того же localStorage что и у Pro
        */}
        <Route path="/free" element={<FreePlan />} />

        {/* ── ADS PLATFORM ─────────────────────────────────────────── */}
        {/*
          /adsauth — регистрация/вход для рекламных агентов
          /ads     — личный кабинет рекламного агента
          Отдельная система авторизации, хранится в ads_agent_token
        */}
        <Route path="/adsauth" element={<AdsAuth />} />
        <Route
          path="/ads"
          element={
            localStorage.getItem('ads_agent_token')
              ? <AdsPortal />
              : <Navigate to="/adsauth" replace />
          }
        />

        {/* --- АВТОРИЗАЦИЯ --- */}
        <Route 
          path="/auth" 
          element={!user ? <Auth onLogin={handleLogin} /> : <Navigate to="/dashboard" replace />} 
        />

        {/* --- АДМИН-ЗОНА --- */}
        <Route path="/admin-zone" element={<AdminPanel onLogout={() => window.location.href = '/auth'} />} />
        <Route path="/admin/editor/:botId" element={<AdminBotEditorWrapper />} />

        {/* --- ЗАЩИЩЁННЫЕ РОУТЫ --- */}
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
                      user={user}
                      onSelectBot={(id) => setSelectedBotId(id)} 
                      onAddBot={() => setIsModalOpen(true)}
                      onNavigate={() => {}}
                    />
                  } />
                  
                  <Route path="/profile" element={
                    <Profile 
                      user={user} 
                      bots={bots} 
                      onUpdateBots={(updated) => { setBots(updated); syncData(user.id); }} 
                    />
                  } />
                  
                  <Route path="/editor" element={(() => {
                    const currentBot = bots.find(b => b.id === selectedBotId);
                    return currentBot ? (
                      <BotEditor 
                        key={currentBot.id} 
                        bot={currentBot} 
                        onUpdate={(updated) => setBots(prev => prev.map(b => b.id === updated.id ? updated : b))} 
                        onDelete={async () => { 
                          if (window.confirm("Удалить бота навсегда?")) {
                            await api.deleteBot(user.id, selectedBotId!); 
                            syncData(user.id);
                          }
                        }} 
                      />
                    ) : <Navigate to="/dashboard" replace />;
                  })()} />
                  
                  <Route path="/broadcast" element={<BroadcastManager bots={bots} />} />
                  <Route path="/referrals" element={<Referrals user={user} />} />
                  <Route path="/miniapps" element={<MiniAppBuilder user={user} />} />
                  <Route path="/chatplatform" element={<ChatPlatform user={user} />} />
                  {/* ── Free и Ads доступны и залогиненным пользователям ── */}
                  <Route path="/free" element={<FreePlan />} />
                  <Route path="/ads" element={<AdsPortal />} />
                  <Route path="/adsauth" element={<AdsAuth />} />
                  <Route path="/dashboard" element={<Navigate to="/dashboard" replace />} />
                  <Route path="*" element={<Navigate to="/dashboard" replace />} />
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
