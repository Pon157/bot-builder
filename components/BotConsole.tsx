
import React, { useEffect, useState, useRef } from 'react';
import { Terminal, RefreshCw, Zap } from 'lucide-react';
import { api } from '../services/apiService';

interface BotConsoleProps {
  botId: string;
}

const BotConsole: React.FC<BotConsoleProps> = ({ botId }) => {
  const [logs, setLogs] = useState<string>('Подключение к серверу логов...');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const scrollRef = useRef<HTMLPreElement>(null);

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
            {logs || 'Логи пусты.'}
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
