import React, { useEffect, useState, useMemo } from 'react';

const QuestTerminal: React.FC = () => {
  const [v2, setV2] = useState('');
  const [msg, setMsg] = useState('СТАТУС: ОЖИДАНИЕ_ДАННЫХ');
  const [bot, setBot] = useState('');

  const noise = useMemo(() => {
    const p = ["01000101", "01010010", "01001111", "01010100", "01001011", "01011000"];
    return Array.from({ length: 40 }).map(() => ({
      t: p[Math.floor(Math.random() * p.length)],
      y: `${Math.random() * 100}%`,
      x: `${Math.random() * 100}%`,
      d: `${5 + Math.random() * 7}s`,
      delay: `${Math.random() * 5}s`
    }));
  }, []);

  useEffect(() => {
    console.clear();
    console.log("%c [!] 01010011 01011001 01010011 01010100 01000101 01001101 [!] ", "color:red;font-weight:bold;font-size:20px;");
    console.log("01100101 01101100 01110001 01100100 01110101 01100010 01011111 01110111 01110010 01011111 01100110 01100100 01100100 01110110 01100100 01110101 01011111 01110000 01101100 01101110 01110111 01110110 01011111 00110110");
    console.log("CMD_01: 01110101 01101000 01110011 01100100 01101100 01110101 01011111 01110000 01110010 01100111 01111000 01101111 01101000");

    (window as any).repair_module = () => {
      const f = document.querySelectorAll('.c-p');
      const k = Array.from(f).map(e => ({ c: (e as HTMLElement).dataset.c || '', o: parseInt((e as HTMLElement).dataset.o || '0') })).sort((a, b) => a.o - b.o).map(p => p.c).join('');
      
      if (k === "Hjdvdosi3245") {
        console.log("%c [01001111 01001011] ", "color:#0f0;font-weight:bold;");
        console.log("DATA_02: 01001011 01101101 01100111 01111001 01100111 01110010 01110110 01101100 00110110 00110101 00110111 00111000");

        Object.defineProperty(window, k, {
          get: () => {
            console.log("CMD_03: 01101000 01100001 01101000 01100110 01111000 01110111 01101000 01011111 01110101 01101000 01100110 01110010 01111001 01101000 01110101 01100010");
            
            (window as any).execute_recovery = () => {
                console.log("FINAL_BYTE_STREAM:");
                console.log("01100001 01100101 01110110 01101100 01010010 01110001 00101001 01100010 01110111 01111001 01101101 01001000 01111010 00100011 01100101 01111111 01101100 01101011 01000111 01111000");
                return "01010011 01010101 01000011 01000011 01000101 01010011 01010011";
            };
            return "01001100 01001111 01000001 01000100 01001001 01001110 01000111";
          },
          configurable: true
        });
        return "01000100 01001111 01001110 01000101";
      }
      return "01000101 01010010 01010010 01001111 01010010";
    };
  }, []);

  const handleAuth = (e: React.FormEvent) => {
    e.preventDefault();
    if (v2.trim() === "xbsiOn)ytvjEw#bihDu") {
      const b = [102, 115, 103, 104, 115, 103, 100, 112, 105, 103, 104, 100, 102, 98, 111, 116].map(c => String.fromCharCode(c)).join('');
      setBot(`@${b}`);
      setMsg("АВТОРИЗАЦИЯ ПРОЙДЕНА.");
    } else {
      setMsg("ОШИБКА_КЛЮЧА.");
    }
  };

  return (
    <div style={{ backgroundColor: '#000', color: '#0f0', height: '100vh', width: '100vw', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'monospace', overflow: 'hidden', position: 'fixed', top: 0, left: 0 }}>
      
      {noise.map((p, i) => (
        <div key={i} style={{ 
          position: 'absolute', 
          bottom: '-100px', 
          left: p.x, 
          color: '#00ff00', 
          fontSize: '14px', 
          opacity: 0.2,
          animation: `floatUp ${p.d} linear infinite`, 
          animationDelay: p.delay,
          zIndex: 0,
          whiteSpace: 'nowrap',
          pointerEvents: 'none'
        }}>
          {p.t}
        </div>
      ))}

      <div className="c-p" data-o="8" data-c="i" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="1" data-c="H" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="12" data-c="5" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="2" data-c="j" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="3" data-c="d" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="4" data-c="v" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="5" data-c="d" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="6" data-c="o" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="7" data-c="s" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="9" data-c="3" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="10" data-c="2" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="11" data-c="4" style={{ display: 'none' }}></div>

      <div style={{ border: '2px solid #0f0', padding: '50px', background: '#000', textAlign: 'center', width: '450px', zIndex: 10, boxShadow: '0 0 30px rgba(0,255,0,0.2)' }}>
        <h1 style={{ marginBottom: '30px', letterSpacing: '8px', fontSize: '20px', color: '#0f0' }}>ТЕРМИНАЛ_ЯДРА_V12</h1>
        
        <form onSubmit={handleAuth} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <input type="text" placeholder="ID_СЕССИИ" style={{ background: '#000', border: '1px solid #005500', color: '#0f0', width: '100%', padding: '12px', outline: 'none' }} />
          <input type="text" value={v2} onChange={(e) => setV2(e.target.value)} placeholder="ВВЕДИТЕ КЛЮЧ" style={{ background: '#000', border: '1px solid #0f0', color: '#0f0', width: '100%', padding: '12px', outline: 'none', textAlign: 'center' }} />
          <button type="submit" style={{ background: '#0f0', color: '#000', border: 'none', padding: '15px', fontWeight: 'bold', cursor: 'pointer', letterSpacing: '2px' }}>АВТОРИЗАЦИЯ</button>
        </form>

        <div style={{ marginTop: '30px', minHeight: '60px' }}>
          <p style={{ fontSize: '14px', color: '#0f0' }}>{msg}</p>
          {bot && <div style={{ border: '1px dashed #0f0', padding: '15px', marginTop: '15px', color: '#fff', background: 'rgba(0,255,0,0.1)' }}>ЦЕЛЬ: <span style={{color:'#0f0', fontWeight: 'bold'}}>{bot}</span></div>}
        </div>
      </div>

      <style>{`
        @keyframes floatUp {
          0% { transform: translateY(0); opacity: 0; }
          20% { opacity: 0.3; }
          80% { opacity: 0.3; }
          100% { transform: translateY(-120vh); opacity: 0; }
        }
      `}</style>
    </div>
  );
};

export default QuestTerminal;
