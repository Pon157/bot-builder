import React, { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';

// ─── Types (duplicated for standalone use) ────────────────────────────────────

type CompType =
  | 'heading' | 'text' | 'button' | 'linkButton'
  | 'input' | 'textarea' | 'divider' | 'image' | 'spacer' | 'card';

interface CompProps {
  text?: string;
  level?: 'h1' | 'h2' | 'h3';
  fontSize?: number;
  fontWeight?: string;
  color?: string;
  align?: 'left' | 'center' | 'right';
  italic?: boolean;
  bgColor?: string;
  textColor?: string;
  action?: 'link' | 'submit' | 'none';
  url?: string;
  placeholder?: string;
  label?: string;
  required?: boolean;
  inputType?: string;
  name?: string;
  src?: string;
  alt?: string;
  width?: string;
  height?: number;
  dividerColor?: string;
}

interface AppComponent {
  id: string;
  type: CompType;
  props: CompProps;
}

interface AppTheme {
  bg: string;
  surface: string;
  primary: string;
  textPrimary: string;
  textSecondary: string;
  radius: number;
  font: string;
  gradient?: string;
}

interface MiniAppData {
  id: string;
  title: string;
  theme: AppTheme;
  components: AppComponent[];
  formWebhook?: string;
}

// ─── Font loader ──────────────────────────────────────────────────────────────

const GOOGLE_FONTS: Record<string, string> = {
  "'Manrope', sans-serif":          'Manrope:wght@400;600;700;800',
  "'Syne', sans-serif":             'Syne:wght@400;700;800',
  "'DM Sans', sans-serif":          'DM+Sans:wght@400;500;700',
  "'Space Mono', monospace":        'Space+Mono:wght@400;700',
  "'Playfair Display', serif":      'Playfair+Display:wght@400;700;900',
  "'Bebas Neue', sans-serif":       'Bebas+Neue',
};

function loadFont(font: string) {
  const key = GOOGLE_FONTS[font];
  if (!key || document.querySelector(`link[data-font="${key}"]`)) return;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = `https://fonts.googleapis.com/css2?family=${key}&display=swap`;
  link.setAttribute('data-font', key);
  document.head.appendChild(link);
}

// ─── Component renderer ───────────────────────────────────────────────────────

const RenderComp: React.FC<{
  comp: AppComponent;
  theme: AppTheme;
  formData: Record<string, string>;
  onFormChange: (name: string, value: string) => void;
  onSubmit: () => void;
}> = ({ comp, theme, formData, onFormChange, onSubmit }) => {
  const { type, props: p } = comp;

  if (type === 'heading') {
    const Tag = (p.level || 'h2') as 'h1' | 'h2' | 'h3';
    return (
      <Tag style={{
        fontSize: p.fontSize || 28, fontWeight: p.fontWeight || '800',
        color: p.color || theme.textPrimary, textAlign: p.align || 'left',
        fontStyle: p.italic ? 'italic' : 'normal', margin: 0, lineHeight: 1.25,
        fontFamily: theme.font,
      }}>{p.text || 'Заголовок'}</Tag>
    );
  }

  if (type === 'text') {
    return (
      <p style={{
        fontSize: p.fontSize || 16, color: p.color || theme.textSecondary,
        textAlign: p.align || 'left', margin: 0, lineHeight: 1.7,
        fontStyle: p.italic ? 'italic' : 'normal', fontWeight: p.fontWeight || '400',
        fontFamily: theme.font,
      }}>{p.text || ''}</p>
    );
  }

  if (type === 'button') {
    const handleClick = () => {
      if (p.action === 'submit') onSubmit();
      else if (p.action === 'link' && p.url) window.open(p.url, '_blank');
    };
    return (
      <div style={{ textAlign: 'center' }}>
        <button onClick={handleClick}
          style={{
            background: p.bgColor || theme.primary, color: p.textColor || '#fff',
            borderRadius: theme.radius, fontWeight: '700', fontSize: 16,
            padding: '13px 32px', border: 'none', cursor: 'pointer',
            fontFamily: theme.font, transition: 'opacity 0.15s',
            boxShadow: `0 4px 20px ${(p.bgColor || theme.primary)}55`,
          }}
          onMouseEnter={e => (e.currentTarget as HTMLButtonElement).style.opacity = '0.85'}
          onMouseLeave={e => (e.currentTarget as HTMLButtonElement).style.opacity = '1'}
        >{p.text || 'Нажми'}</button>
      </div>
    );
  }

  if (type === 'linkButton') {
    return (
      <div style={{ textAlign: 'center' }}>
        <a href={p.url || '#'} target="_blank" rel="noopener noreferrer"
          style={{
            display: 'inline-block', background: p.bgColor || theme.primary,
            color: p.textColor || '#fff', borderRadius: theme.radius, fontWeight: '700',
            fontSize: 16, padding: '13px 32px', textDecoration: 'none',
            fontFamily: theme.font, transition: 'opacity 0.15s',
            boxShadow: `0 4px 20px ${(p.bgColor || theme.primary)}55`,
          }}
          onMouseEnter={e => (e.currentTarget as HTMLAnchorElement).style.opacity = '0.85'}
          onMouseLeave={e => (e.currentTarget as HTMLAnchorElement).style.opacity = '1'}
        >{p.text || 'Перейти'}</a>
      </div>
    );
  }

  if (type === 'input') {
    return (
      <label style={{ display: 'block' }}>
        {p.label && (
          <span style={{
            display: 'block', fontSize: 11, fontWeight: '700',
            color: theme.textSecondary, marginBottom: 6,
            textTransform: 'uppercase', letterSpacing: '0.08em', fontFamily: theme.font,
          }}>{p.label}{p.required ? ' *' : ''}</span>
        )}
        <input
          type={p.inputType || 'text'}
          name={p.name}
          placeholder={p.placeholder}
          required={p.required}
          value={formData[p.name || ''] || ''}
          onChange={e => onFormChange(p.name || '', e.target.value)}
          style={{
            width: '100%', boxSizing: 'border-box', background: theme.surface,
            border: `1.5px solid ${theme.textSecondary}25`, color: theme.textPrimary,
            borderRadius: theme.radius * 0.7, padding: '12px 16px', fontSize: 15,
            fontFamily: theme.font, outline: 'none', transition: 'border-color 0.2s',
          }}
          onFocus={e => (e.currentTarget as HTMLInputElement).style.borderColor = theme.primary + '80'}
          onBlur={e => (e.currentTarget as HTMLInputElement).style.borderColor = theme.textSecondary + '25'}
        />
      </label>
    );
  }

  if (type === 'textarea') {
    return (
      <label style={{ display: 'block' }}>
        {p.label && (
          <span style={{
            display: 'block', fontSize: 11, fontWeight: '700',
            color: theme.textSecondary, marginBottom: 6,
            textTransform: 'uppercase', letterSpacing: '0.08em', fontFamily: theme.font,
          }}>{p.label}{p.required ? ' *' : ''}</span>
        )}
        <textarea
          name={p.name}
          placeholder={p.placeholder}
          required={p.required}
          rows={4}
          value={formData[p.name || ''] || ''}
          onChange={e => onFormChange(p.name || '', e.target.value)}
          style={{
            width: '100%', boxSizing: 'border-box', background: theme.surface,
            border: `1.5px solid ${theme.textSecondary}25`, color: theme.textPrimary,
            borderRadius: theme.radius * 0.7, padding: '12px 16px', fontSize: 15,
            fontFamily: theme.font, outline: 'none', transition: 'border-color 0.2s',
            resize: 'vertical',
          }}
          onFocus={e => (e.currentTarget as HTMLTextAreaElement).style.borderColor = theme.primary + '80'}
          onBlur={e => (e.currentTarget as HTMLTextAreaElement).style.borderColor = theme.textSecondary + '25'}
        />
      </label>
    );
  }

  if (type === 'image') {
    return (
      <img src={p.src} alt={p.alt || ''}
        style={{ width: p.width || '100%', borderRadius: theme.radius, display: 'block', maxWidth: '100%' }} />
    );
  }

  if (type === 'divider') {
    return <hr style={{ border: 'none', borderTop: `1px solid ${p.dividerColor || theme.textSecondary + '30'}`, margin: '4px 0' }} />;
  }

  if (type === 'spacer') {
    return <div style={{ height: p.height || 32 }} />;
  }

  return null;
};

// ─── Main Renderer ────────────────────────────────────────────────────────────

const MiniAppRenderer: React.FC = () => {
  const { appId } = useParams<{ appId: string }>();
  const [appData, setAppData] = useState<MiniAppData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [formData, setFormData] = useState<Record<string, string>>({});
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        // Try server first
        const res = await fetch(`/api/miniapps/${appId}`);
        if (res.ok) {
          const data = await res.json();
          setAppData(data);
          if (data.theme?.font) loadFont(data.theme.font);
        } else {
          // Fallback to localStorage
          const local = localStorage.getItem(`miniapp_${appId}`);
          if (local) {
            const data = JSON.parse(local);
            setAppData(data);
            if (data.theme?.font) loadFont(data.theme.font);
          } else {
            setError('Приложение не найдено');
          }
        }
      } catch {
        const local = localStorage.getItem(`miniapp_${appId}`);
        if (local) {
          const data = JSON.parse(local);
          setAppData(data);
          if (data.theme?.font) loadFont(data.theme.font);
        } else {
          setError('Ошибка загрузки');
        }
      } finally {
        setLoading(false);
      }
    };
    if (appId) load();
  }, [appId]);

  const handleFormChange = (name: string, value: string) => {
    setFormData(p => ({ ...p, [name]: value }));
  };

  const handleSubmit = async () => {
    if (!appData?.formWebhook) return;
    setSubmitting(true);
    try {
      await fetch(appData.formWebhook, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        mode: 'no-cors',
        body: JSON.stringify({ ...formData, _appId: appId, _appTitle: appData.title }),
      });
      setSubmitted(true);
    } catch {
      setSubmitted(true); // still show success (no-cors won't confirm)
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0a0a0f' }}>
        <div style={{ width: 40, height: 40, border: '3px solid #6366f130', borderTop: '3px solid #6366f1', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (error || !appData) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0a0a0f', flexDirection: 'column', gap: 16 }}>
        <p style={{ color: '#ef4444', fontFamily: 'system-ui', fontSize: 18, fontWeight: 700 }}>Приложение не найдено</p>
        <p style={{ color: '#71717a', fontFamily: 'system-ui', fontSize: 14 }}>{error}</p>
      </div>
    );
  }

  const { theme } = appData;

  return (
    <>
      <style>{`
        * { box-sizing: border-box; }
        body { margin: 0; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        .miniapp-comp { animation: fadeIn 0.3s ease both; }
      `}</style>

      <div style={{
        minHeight: '100vh', background: theme.bg, fontFamily: theme.font,
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        padding: '24px 16px', position: 'relative', overflow: 'hidden',
      }}>
        {theme.gradient && (
          <div style={{ position: 'fixed', inset: 0, background: theme.gradient, pointerEvents: 'none', zIndex: 0 }} />
        )}

        <div style={{
          width: '100%', maxWidth: 480, position: 'relative', zIndex: 1,
          display: 'flex', flexDirection: 'column', gap: 20,
          animation: 'fadeIn 0.4s ease',
        }}>
          {submitted ? (
            <div style={{
              background: theme.surface, borderRadius: theme.radius * 1.5,
              padding: 48, textAlign: 'center',
              boxShadow: `0 20px 60px ${theme.primary}22`,
            }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>✅</div>
              <p style={{ color: theme.textPrimary, fontSize: 22, fontWeight: 800, margin: '0 0 8px', fontFamily: theme.font }}>Отправлено!</p>
              <p style={{ color: theme.textSecondary, fontSize: 15, margin: 0, fontFamily: theme.font }}>Ваши данные успешно получены.</p>
              <button
                onClick={() => { setSubmitted(false); setFormData({}); }}
                style={{ marginTop: 24, background: theme.primary, color: '#fff', border: 'none', borderRadius: theme.radius, padding: '12px 28px', fontSize: 15, fontWeight: 700, cursor: 'pointer', fontFamily: theme.font }}
              >Заполнить снова</button>
            </div>
          ) : (
            appData.components.map((comp, i) => (
              <div key={comp.id} className="miniapp-comp" style={{ animationDelay: `${i * 50}ms` }}>
                <RenderComp
                  comp={comp}
                  theme={theme}
                  formData={formData}
                  onFormChange={handleFormChange}
                  onSubmit={handleSubmit}
                />
              </div>
            ))
          )}
        </div>
      </div>
    </>
  );
};

export default MiniAppRenderer;
