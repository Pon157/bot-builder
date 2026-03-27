// Типизация для наших "ложных" ключей
type SystemStatus = 'INITIALIZING' | 'BREACH_DETECTED' | 'ENCRYPTED' | 'VOID';

const QuestPage: React.FC = () => { // Если используешь React, если нет — логика ниже
  
  // Оригинальный код: Hjdvdosi3245
  // Закодируем его в Base64, чтобы его не было видно в исходнике: SHpkdmRvc2kzMjQ1
  const secretEncoded = "SHpkdmRvc2kzMjQ1";

  const handleFakeClick = () => {
    const output = document.getElementById('output');
    if (output) {
      output.innerText = `[ERROR]: System integrity compromised. Node_${Math.floor(Math.random() * 1000)} is offline.`;
      output.style.color = 'red';
    }
  };

  // Инициализация ловушек
  const initTraps = () => {
    // 1. Засоряем консоль "мусором"
    for (let i = 0; i < 30; i++) {
      console.log(`%c Decrypting layer ${i}... Failed.`, "color: #444");
    }

    // 2. Выводим настоящий код через задержку с "хакерским" оформлением
    setTimeout(() => {
      console.log(
        "%c [!] КРИТИЧЕСКИЙ ТОКЕН ОБНАРУЖЕН [!] ",
        "background: #222; color: #00ff00; font-size: 14px; border: 1px solid #00ff00;"
      );
      // Декодируем на лету, чтобы в коде страницы была только абракадабра
      console.log(`%c КЛЮЧ: ${atob(secretEncoded)}`, "color: #fff; font-weight: bold; font-size: 18px;");
      console.log("%c Введите этот код в боте конструктора.", "color: #888; italic");
    }, 3000);
  };

  // Вызываем при загрузке
  if (typeof window !== 'undefined') {
    initTraps();
    // Блокируем правую кнопку для атмосферы
    window.oncontextmenu = (e) => {
      e.preventDefault();
      console.error("Access Denied: Manual inspection blocked.");
    };
  }

  return (
    <div style={{ backgroundColor: '#000', color: '#0f0', height: '100vh', fontFamily: 'monospace', padding: '50px' }}>
      <div style={{ border: '1px solid #0f0', padding: '20px', maxWidth: '500px' }}>
        <h2>PRIVATE_NODE_ROOT</h2>
        <p>> Статус сессии: <span className="glitch">НЕСТАБИЛЬНО</span></p>
        <p>> Логирование: Активно</p>
        
        {/* Путаница: невидимые части кода разбросаны по DOM */}
        <span style={{ opacity: 0, fontSize: '1px' }}>part_1: Hjdv</span>
        
        <button 
          onClick={handleFakeClick}
          style={{ background: '#0f0', border: 'none', padding: '10px', cursor: 'pointer', fontWeight: 'bold' }}
        >
          CONNECT TO CORE
        </button>
        
        <div id="output" style={{ marginTop: '20px', fontSize: '12px' }}></div>
        
        <span style={{ opacity: 0, fontSize: '1px' }}>part_2: dosi3245</span>
      </div>
      
      {/* Скрытая подсказка для тех, кто смотрит код элементов */}
      <footer style={{ marginTop: '50px', color: '#111' }}>
         Hint: Look into the 'Console' tab or find hidden spans.
      </footer>
    </div>
  );
};
