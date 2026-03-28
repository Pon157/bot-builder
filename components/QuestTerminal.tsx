import React, { useState, useEffect } from 'react';

const QuestTerminal: React.FC = () => {
  const [inputValue, setInputValue] = useState('');
  const [status, setStatus] = useState<string | null>(null);

  // 1. Первый ключ (раскодированный Base64)
  const secretKey = "Hjdvdosi3245";

  // 2. ЗАШИФРОВАННЫЙ ФИНАЛЬНЫЙ КОД (чтобы не нашли в Source)
  // Это зашифрованный "TG_MASTER_QUEST_777" с ключом "quest"
  const encryptedPrize = "DR4XRE1NQ05CVF9RVkVTVF83Nzc="; 

  // Простая функция дешифровки (XOR), чтобы скрыть код
  const decrypt = (encoded: string, key: string): string => {
    const data = atob(encoded);
    return data.split('').map((char, i) => 
      String.fromCharCode(char.charCodeAt(0) ^ key.charCodeAt(i % key.length))
    ).join('');
  };

  useEffect(() => {
    // Очищаем консоль для чистоты эксперимента
    console.clear();

    // ЗАПУТЫВАНИЕ: Выводим в консоль кучу ложных логов
    for(let i=0; i<15; i++) {
      console.log(`%c [СИСТЕМА] Проверка сектора ${Math.floor(Math.random()*100)}... ОК`, "color: #333");
    }

    // ВЫВОДИМ БАЗОВЫЙ ФРАГМЕНТ (Base64)
    console.log("%c [ЯДРО]: Обнаружен зашифрованный вызов. ", "color: #0f0; font-weight: bold; font-size: 12px;");
    console.log("ФРАГМЕНТ_ПАМЯТИ: %c SHpkdmRvc2kzMjQ1 ", "background: #222; color: #ff0; padding: 2px;");
    // Убрали подсказку про "исполни здесь"

    // МАГИЯ: Глобальный геттер (работает БЕЗ скобок)
    try {
      Object.defineProperty(window, secretKey, {
        get: () => {
          // Дешифруем приз только в момент вызова!
          const prize = decrypt(encryptedPrize, "quest"); 
          
          console.log("%c [УСПЕХ]: Доступ к ядру разрешен! ", "color: white; background: green; padding: 5px; font-weight: bold;");
          console.log(`%c ВАШ ФИНАЛЬНЫЙ КОД ДЛЯ БОТА: ${prize}`, "font-size: 16px; font-weight: bold; color: #0f0;");
          return "--- Доступ зафиксирован ---";
        },
        configurable: true // Чтобы можно было удалить при размонтировании
      });
    } catch (e) {
      // Игнорируем ошибки, если defineProperty не поддерживается
    }

    return () => {
      // Подчищаем за собой
      try {
        delete (window as any)[secretKey];
      } catch (e) {}
    };
  }, []);

  // Хендлер для ЛОЖНОЙ формы
  const handleFakeSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim()) return;

    setStatus('ПРОВЕРКА...');
    
    // Имитируем долгую проверку, чтобы юзер поверил
    setTimeout(() => {
      setStatus('ОШИБКА: Ключ не найден в локальной базе данных.');
      setInputValue('');
      // Через 3 секунды убираем статус
      setTimeout(() => setStatus(null), 3000);
    }, 1500);
  };

  return (
    <div style={{ backgroundColor: '#000', color: '#0f0', height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'monospace', padding: '20px' }}>
      <div style={{ border: '1px solid #0f0', padding: '30px', textAlign: 'center', boxShadow: '0 0 15px rgba(0, 255, 65, 0.1)', maxWidth: '500px', width: '100%' }}>
        <h1 style={{ letterSpacing: '2px', fontSize: '24px', marginBottom: '10px' }}>УДАЛЕННЫЙ_ТЕРМИНАЛ</h1>
        <p style={{ color: '#008f11', fontSize: '14px', marginBottom: '30px' }}>{" > "} Введите токен доступа для авторизации в ядре.</p>
        
        {/* ЛОЖНАЯ ФОРМА ВВОДА */}
        <form onSubmit={handleFakeSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
          <input 
            type="text" 
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="XXXX-XXXX-XXXX-XXXX"
            style={{ 
              background: 'transparent', 
              border: '1px solid #0f0', 
              color: '#0f0', 
              padding: '12px',
              outline: 'none', 
              fontFamily: 'monospace',
              textAlign: 'center',
              fontSize: '16px'
            }}
          />
          <button 
            type="submit"
            style={{ 
              background: '#0f0', 
              color: '#000', 
              border: 'none', 
              padding: '12px', 
              cursor: 'pointer', 
              fontWeight: 'bold', 
              textTransform: 'uppercase',
              letterSpacing: '1px'
            }}
          >
            Авторизоваться
          </button>
        </form>
        
        {/* Статус проверки (ложный) */}
        <div style={{ marginTop: '20px', height: '20px', fontSize: '12px', color: status?.startsWith('ОШИБКА') ? '#ff4444' : '#888' }}>
          {status && `[ СТАТУС ]: ${status}`}
        </div>
      </div>
    </div>
  );
};

export default QuestTerminal;
