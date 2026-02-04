
import React, { useEffect, useState, useRef, useMemo } from 'react';
import { Terminal, RefreshCw, Zap } from 'lucide-react';
import { api } from '../services/apiService';

interface BotConsoleProps {
  botId: string;
}

const BotConsole: React.FC<BotConsoleProps> = ({ botId }) => {
  const [logs, setLogs] = useState<string>('Подключение к серверу логов...');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const scrollRef = useRef<HTMLPreElement>(null);

  // Функция для маскирования конфиденциальных данных
  const maskSensitiveInfo = (text: string) => {
    if (!text) return text;
    
    // 1. Маскируем поддомены supabase.co (например, hjureycxvbprcfyfeeir.supabase.co)
    let masked = text.replace(/https:\/\/([a-z0-9]+)\.supabase\.co/gi, 'https://[SECURE_DATABASE_ENDPOINT].supabase.co');
    
    // 2. Маскируем токены ботов, если они вдруг попали в логи (формат 123456:ABC-DEF...)
    masked = masked.replace(/\d{8,10}:[a-zA-Z0-9_-]{35}/g, '[BOT_TOKEN_HIDDEN]');

    // 3. Маскируем Bearer токены в заголовках, если они видны
    masked = masked.replace(/Bearer\s+[a-zA-Z0-9._-]{20,}/g, 'Bearer [AUTH_TOKEN_MASKED]');

    return masked;
  };

  const fetchLogs = async () => {
    setIsRefreshing(true);
    const data = await api.getBotLogs(botId);
    setLogs(data);
    setIsRefreshing(false);
  };

  useEffect(() => {
    fetchLogs();
    const interval = setInterval(fetchLogs, 5000); // Обновление каждые 5 сек
    return () => clearInterval(interval);
  }, [botId]);

  useEffect(() => {
    if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  // Используем useMemo для эффективной обработки текста
  const processedLogs = useMemo(() => maskSensitiveInfo(logs), [logs]);

  return (
    <div className="bg-[#0a0a0a] border border-zinc-800 rounded-3xl overflow-hidden flex flex-col h-[500px] shadow-2xl">
      <div className="bg-[#111] px-6 py-4 border-b border-zinc-800 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-500/10 rounded-lg">
            <Terminal className="w-4 h-4 text-blue-500" />
          </div>
          <div>
            <span className="text-[10px] font-black uppercase tracking-widest text-white">Bot Server Terminal</span>
            <p className="text-[8px] text-zinc-500 font-bold uppercase mt-0.5">Live process output</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
            <div className="flex items-center gap-1 bg-emerald-500/10 px-2 py-1 rounded-md border border-emerald-500/20">
              <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse"></div>
              <span className="text-[8px] font-black text-emerald-500 uppercase">Privacy Filter Active</span>
            </div>
            <button 
                onClick={fetchLogs}
                disabled={isRefreshing}
                className={`p-2 hover:bg-white/5 rounded-lg transition-colors text-zinc-500 hover:text-white ${isRefreshing ? 'animate-spin' : ''}`}
            >
                <RefreshCw className="w-3.5 h-3.5" />
            </button>
        </div>
      </div>
      
      <div className="flex-1 p-6 font-mono text-[12px] overflow-hidden bg-[radial-gradient(circle_at_top_right,_var(--tw-gradient-stops))] from-zinc-900/20 via-transparent to-transparent">
        <pre 
            ref={scrollRef}
            className="h-full overflow-y-auto no-scrollbar text-zinc-400 whitespace-pre-wrap leading-relaxed"
        >
            {processedLogs || 'Логи пусты.'}
        </pre>
      </div>
      
      <div className="px-6 py-2 bg-zinc-900/30 border-t border-zinc-800 flex items-center gap-2">
        <Zap className="w-3 h-3 text-amber-500 animate-pulse" />
        <span className="text-[9px] text-zinc-600 font-bold uppercase">Автоматическое обновление включено (5с)</span>
      </div>
    </div>
  );
};

export default BotConsole;
