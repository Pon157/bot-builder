import React, { useEffect, useState } from 'react';

const QuestTerminal: React.FC = () => {
  const [s, setS] = useState<string>('СИСТЕМНЫЙ СБОЙ: 0x800421');

  useEffect(() => {
    console.clear();
    console.log("%c КРИТИЧЕСКАЯ ОШИБКА: СЕКТОР ПАМЯТИ ПОВРЕЖДЕН ", "color:red;font-weight:bold;");
    
    (window as any).repair_module = () => {
      const f = document.querySelectorAll('.c-p');
      const k = Array.from(f)
        .map(e => ({ c: (e as HTMLElement).dataset.c || '', o: parseInt((e as HTMLElement).dataset.o || '0') }))
        .sort((a, b) => a.o - b.o).map(p => p.c).join('');

      if (k === "Hjdvdosi3245") {
        Object.defineProperty(window, k, {
          get: () => {
            const c1 = [2, 11, 2, 1, 31, 88, 51, 8, 23, 11, 23, 31];
            const m = "pass";
            const r1 = c1.map((b, i) => String.fromCharCode(b ^ m.charCodeAt(i % m.length))).join('');
            
            console.log(`%c ЭТАП 1 ЗАВЕРШЕН. КЛЮЧ: ${r1}`, "color:#0f0;font-weight:bold;");
            console.log("%c ТРЕБУЕТСЯ АКТИВАЦИЯ ПОТОКА: 'get_final_access()'", "color:#888;");
            return "STAGE_1_OK";
          },
          configurable: true
        });

        (window as any).get_final_access = () => {
          const c2 = [27, 13, 1, 12, 16, 24, 16, 26, 27, 4, 15, 26, 1, 26, 1, 16, 27, 13, 27, 3];
          const m2 = "core_v9";
          const r2 = c2.map((b, i) => String.fromCharCode(b ^ m2.charCodeAt(i % m2.length))).join('');
          console.log("%c [!] ДОСТУП ВОССТАНОВЛЕН [!] ", "background:#0f0;color:#000;padding:5px;");
          console.log(`%c ФИНАЛЬНЫЙ КОД: ${r2}`, "font-size:16px;color:#0f0;font-weight:bold;");
          return "TERMINATED";
        };

        return `Слой [${k}] активен.`;
      }
      return "ОШИБКА_ЦЕЛОСТНОСТИ";
    };
    return () => { delete (window as any).repair_module; };
  }, []);

  return (
    <div style={{ backgroundColor: '#000', color: '#0f0', height: '100vh', display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'center', fontFamily: 'monospace', overflow: 'hidden' }}>
      
      <div className="c-p" data-o="8" data-c="i" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="3" data-c="d" style={{ opacity: 0 }}></div>
      <div className="c-p" data-o="12" data-c="5" style={{ position: 'absolute', left: '-2000px' }}></div>
      <div className="c-p" data-o="1" data-c="H" style={{ width: 0, height: 0, overflow: 'hidden' }}></div>
      <div className="c-p" data-o="6" data-c="o" style={{ visibility: 'hidden' }}></div>
      <div className="c-p" data-o="10" data-c="2" style={{ color: 'transparent' }}></div>
      <div className="c-p" data-o="4" data-c="v" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="2" data-c="j" style={{ fontSize: 0 }}></div>
      <div className="c-p" data-o="11" data-c="4" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="7" data-c="s" style={{ opacity: 0 }}></div>
      <div className="c-p" data-o="5" data-c="d" style={{ position: 'fixed', top: '-100px' }}></div>
      <div className="c-p" data-o="9" data-c="3" style={{ display: 'none' }}></div>

      <div style={{ border: '1px solid #003300', padding: '50px', textAlign: 'center', background: '#050505', boxShadow: '0 0 30px rgba(0,255,0,0.05)' }}>
        <h2 style={{ letterSpacing: '8px', opacity: 0.8 }}>ROOT_CORE_V9</h2>
        <div style={{ margin: '30px 0' }}>
          <input 
            type="text" 
            placeholder="TOKEN..."
            style={{ background: 'transparent', border: '1px solid #004400', color: '#0f0', textAlign: 'center', padding: '10px', outline: 'none' }}
            onChange={() => setS('ОШИБКА: ОБНАРУЖЕН ПЕРЕХВАТ ПАКЕТОВ.')}
          />
        </div>
        <p style={{ fontSize: '10px', color: '#500', fontWeight: 'bold' }}>{s}</p>
      </div>

      <div style={{ position: 'fixed', bottom: '10px', right: '10px', fontSize: '9px', color: '#111', userSelect: 'all' }}>
        PROCESS_ID: fsghsgdpighdfbot
      </div>
    </div>
  );
};

export default QuestTerminal;
