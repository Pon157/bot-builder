
import React, { useEffect, useRef } from 'react';
import { MessageLog } from '../types';

interface BotConsoleProps {
  logs: MessageLog[];
}

const BotConsole: React.FC<BotConsoleProps> = ({ logs }) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = 0;
    }
  }, [logs]);

  return (
    <div className="bg-black border border-zinc-800 rounded-2xl overflow-hidden flex flex-col h-[300px]">
      <div className="bg-zinc-900/50 px-4 py-2 border-b border-zinc-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></div>
          <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Live Console</span>
        </div>
        <span className="text-[10px] text-zinc-600 font-mono">STDOUT/STDERR</span>
      </div>
      <div 
        ref={scrollRef}
        className="flex-1 p-4 font-mono text-[11px] overflow-y-auto flex flex-col-reverse gap-1 scrollbar-hide"
      >
        {logs.length === 0 ? (
          <div className="text-zinc-700 italic">No activity recorded...</div>
        ) : (
          logs.map(log => (
            <div key={log.id} className="flex gap-3 border-l border-zinc-800/50 pl-2 ml-1">
              <span className="text-zinc-600 shrink-0">[{new Date(log.timestamp).toLocaleTimeString()}]</span>
              <span className={`
                ${log.type === 'error' ? 'text-red-400' : ''}
                ${log.type === 'info' ? 'text-blue-400' : ''}
                ${log.type === 'incoming' ? 'text-green-400' : ''}
                ${log.type === 'outgoing' ? 'text-purple-400' : ''}
                truncate
              `}>
                <span className="opacity-50 mr-1 uppercase">[{log.type}]</span>
                {log.text}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default BotConsole;
