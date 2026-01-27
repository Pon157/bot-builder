
import React, { useEffect, useRef } from 'react';
import { MessageLog } from '../types';

interface BotConsoleProps {
  logs: MessageLog[];
}

const BotConsole: React.FC<BotConsoleProps> = ({ logs }) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Сортируем логи по времени (новые сверху)
  const sortedLogs = [...logs].sort((a, b) => b.timestamp - a.timestamp);

  return (
    <div className="bg-black border border-zinc-800 rounded-2xl overflow-hidden flex flex-col h-[450px] shadow-inner">
      <div className="bg-zinc-900/50 px-6 py-3 border-b border-zinc-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
          <span className="text-[10px] font-black uppercase tracking-widest text-zinc-400">System Logs</span>
        </div>
        <span className="text-[10px] text-zinc-600 font-mono">REAL-TIME UPDATE</span>
      </div>
      <div 
        ref={scrollRef}
        className="flex-1 p-6 font-mono text-[12px] overflow-y-auto space-y-2 scrollbar-hide"
      >
        {sortedLogs.length === 0 ? (
          <div className="text-zinc-800 flex flex-col items-center justify-center h-full opacity-50">
            <svg className="w-8 h-8 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z" strokeWidth="2"/></svg>
            <p className="uppercase tracking-widest text-[10px] font-bold">Ожидание активности...</p>
          </div>
        ) : (
          sortedLogs.map(log => (
            <div key={log.id} className="group flex gap-4 items-start border-l border-zinc-900 pl-4 py-1 hover:bg-zinc-900/30 transition-colors">
              <span className="text-zinc-600 shrink-0 text-[10px] tabular-nums mt-0.5">
                {new Date(log.timestamp).toLocaleTimeString()}
              </span>
              <div className="flex-1">
                <span className={`
                  inline-block px-1.5 py-0.5 rounded text-[9px] font-black uppercase tracking-tighter mr-2
                  ${log.type === 'error' ? 'bg-red-500/10 text-red-500' : ''}
                  ${log.type === 'info' ? 'bg-blue-500/10 text-blue-500' : ''}
                  ${log.type === 'incoming' ? 'bg-green-500/10 text-green-500' : ''}
                  ${log.type === 'outgoing' ? 'bg-purple-500/10 text-purple-500' : ''}
                  ${log.type === 'system' ? 'bg-zinc-800 text-zinc-400' : ''}
                `}>
                  {log.type}
                </span>
                <span className={`
                  ${log.type === 'error' ? 'text-red-400' : 'text-zinc-300'}
                  leading-relaxed break-words
                `}>
                  {log.text}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default BotConsole;
