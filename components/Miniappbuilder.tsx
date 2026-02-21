import React, { useState, useCallback, useRef } from 'react';
import {
  Plus, Trash2, ChevronUp, ChevronDown, Settings2, Eye, EyeOff,
  Type, MousePointerClick, Link2, TextCursorInput, AlignLeft,
  Minus, Image as ImageIcon, Save, Copy, ExternalLink, Palette,
  Code2, X, MoveVertical, Square, Layers, Globe, Zap, Check,
  AlignCenter, AlignRight, Bold, Italic, Layout
} from 'lucide-react';
import { api } from '../services/apiService';
import { User } from '../types';

// ─── Types ────────────────────────────────────────────────────────────────────

type CompType =
  | 'heading' | 'text' | 'button' | 'linkButton'
  | 'input' | 'textarea' | 'divider' | 'image' | 'spacer' | 'card';

interface CompProps {
  // Text / Heading
  text?: string;
  level?: 'h1' | 'h2' | 'h3';
  fontSize?: number;
  fontWeight?: string;
  color?: string;
  align?: 'left' | 'center' | 'right';
  italic?: boolean;
  // Button
  bgColor?: string;
  textColor?: string;
  action?: 'link' | 'submit' | 'none';
  url?: string;
  // Input
  placeholder?: string;
  label?: string;
  required?: boolean;
  inputType?: string;
  name?: string;
  // Image
  src?: string;
  alt?: string;
  width?: string;
  // Spacer / Divider
  height?: number;
  dividerColor?: string;
  // Card
  cardBg?: string;
  cardBorder?: string;
  cardPadding?: number;
  cardRadius?: number;
  children?: AppComponent[];
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
  id?: string;
  owner_id?: string;
  title: string;
  theme: AppTheme;
  components: AppComponent[];
  formWebhook?: string;
  published?: boolean;
  slug?: string;
}

// ─── Palette config ──────────────────────────────────────────────────────────

const PALETTE_ITEMS: { type: CompType; label: string; icon: React.ElementType; desc: string }[] = [
  { type: 'heading',    label: 'Заголовок',    icon: Type,               desc: 'H1 / H2 / H3' },
  { type: 'text',       label: 'Текст',        icon: AlignLeft,          desc: 'Параграф' },
  { type: 'button',     label: 'Кнопка',       icon: MousePointerClick,  desc: 'Действие' },
  { type: 'linkButton', label: 'Ссылка-кнопка',icon: Link2,              desc: 'Открыть URL' },
  { type: 'input',      label: 'Поле ввода',   icon: TextCursorInput,    desc: 'Форма' },
  { type: 'textarea',   label: 'Textarea',     icon: Square,             desc: 'Многострочный ввод' },
  { type: 'image',      label: 'Изображение',  icon: ImageIcon,          desc: 'URL картинки' },
  { type: 'divider',    label: 'Разделитель',  icon: Minus,              desc: 'Линия' },
  { type: 'spacer',     label: 'Отступ',       icon: MoveVertical,       desc: 'Пустое место' },
];

const FONT_OPTIONS = [
  { label: 'System',      value: 'system-ui' },
  { label: 'Manrope',     value: "'Manrope', sans-serif" },
  { label: 'Syne',        value: "'Syne', sans-serif" },
  { label: 'DM Sans',     value: "'DM Sans', sans-serif" },
  { label: 'Space Mono',  value: "'Space Mono', monospace" },
  { label: 'Playfair',    value: "'Playfair Display', serif" },
  { label: 'Bebas Neue',  value: "'Bebas Neue', sans-serif" },
];

const PRESET_THEMES: { label: string; theme: Partial<AppTheme> }[] = [
  { label: 'Ночь',    theme: { bg: '#0a0a0f', surface: '#13131c', primary: '#6366f1', textPrimary: '#f8fafc', textSecondary: '#94a3b8', gradient: 'radial-gradient(ellipse at 30% 0%, #312e8155 0%, transparent 60%)' } },
  { label: 'Лёд',     theme: { bg: '#f0f9ff', surface: '#ffffff',  primary: '#0ea5e9', textPrimary: '#0f172a', textSecondary: '#64748b', gradient: '' } },
  { label: 'Уголь',   theme: { bg: '#111111', surface: '#1c1c1e',  primary: '#f59e0b', textPrimary: '#fafaf9', textSecondary: '#78716c', gradient: '' } },
  { label: 'Лес',     theme: { bg: '#0d1f12', surface: '#142419',  primary: '#22c55e', textPrimary: '#f0fdf4', textSecondary: '#86efac', gradient: '' } },
  { label: 'Роза',    theme: { bg: '#fff1f2', surface: '#ffffff',  primary: '#f43f5e', textPrimary: '#1c1917', textSecondary: '#78716c', gradient: '' } },
  { label: 'Закат',   theme: { bg: '#1c0d2b', surface: '#251238',  primary: '#f97316', textPrimary: '#fff7ed', textSecondary: '#d1a27c', gradient: 'radial-gradient(ellipse at 80% 0%, #7c2d8840 0%, transparent 60%)' } },
];

const mkId = () => Math.random().toString(36).slice(2, 9);

const DEFAULT_THEME: AppTheme = {
  bg: '#0a0a0f', surface: '#13131c', primary: '#6366f1',
  textPrimary: '#f8fafc', textSecondary: '#94a3b8',
  radius: 12, font: "'Manrope', sans-serif",
  gradient: "radial-gradient(ellipse at 30% 0%, #312e8155 0%, transparent 60%)",
};

const newComp = (type: CompType): AppComponent => {
  const base = { id: mkId(), type, props: {} };
  switch (type) {
    case 'heading':    return { ...base, props: { text: 'Заголовок', level: 'h2', fontSize: 28, fontWeight: '800', color: '', align: 'left' } };
    case 'text':       return { ...base, props: { text: 'Введите текст сюда. Можно редактировать прямо здесь.', fontSize: 16, color: '', align: 'left' } };
    case 'button':     return { ...base, props: { text: 'Нажми меня', bgColor: '', textColor: '#fff', action: 'none' } };
    case 'linkButton': return { ...base, props: { text: 'Перейти →', bgColor: '', textColor: '#fff', url: 'https://', action: 'link' } };
    case 'input':      return { ...base, props: { label: 'Ваш email', placeholder: 'user@example.com', inputType: 'email', name: 'email', required: true } };
    case 'textarea':   return { ...base, props: { label: 'Сообщение', placeholder: 'Введите текст...', name: 'message', required: false } };
    case 'image':      return { ...base, props: { src: 'https://picsum.photos/seed/mini/800/400', alt: 'Изображение', width: '100%' } };
    case 'divider':    return { ...base, props: { dividerColor: '' } };
    case 'spacer':     return { ...base, props: { height: 32 } };
    default:           return base;
  }
};

// ─── Preview Renderer ─────────────────────────────────────────────────────────

const PreviewComp: React.FC<{ comp: AppComponent; theme: AppTheme; selected?: boolean; onClick?: () => void }> = ({ comp, theme, selected, onClick }) => {
  const { type, props } = comp;
  const p = props;

  const baseStyle: React.CSSProperties = {
    fontFamily: theme.font,
    cursor: onClick ? 'pointer' : 'default',
    outline: selected ? `2px solid ${theme.primary}` : undefined,
    outlineOffset: selected ? '3px' : undefined,
    borderRadius: selected ? 4 : undefined,
    transition: 'outline 0.15s',
  };

  const wrap = (el: React.ReactNode) => (
    <div style={baseStyle} onClick={onClick} className="w-full">
      {el}
    </div>
  );

  if (type === 'heading') {
    const Tag = (p.level || 'h2') as 'h1' | 'h2' | 'h3';
    return wrap(
      <Tag style={{
        fontSize: p.fontSize || 28, fontWeight: p.fontWeight || '800',
        color: p.color || theme.textPrimary, textAlign: p.align || 'left',
        fontStyle: p.italic ? 'italic' : 'normal', margin: 0, lineHeight: 1.2,
      }}>{p.text || 'Заголовок'}</Tag>
    );
  }

  if (type === 'text') {
    return wrap(
      <p style={{
        fontSize: p.fontSize || 16, color: p.color || theme.textSecondary,
        textAlign: p.align || 'left', margin: 0, lineHeight: 1.65,
        fontStyle: p.italic ? 'italic' : 'normal', fontWeight: p.fontWeight || '400',
      }}>{p.text || 'Текст'}</p>
    );
  }

  if (type === 'button' || type === 'linkButton') {
    const el = (
      <button
        style={{
          background: p.bgColor || theme.primary, color: p.textColor || '#fff',
          borderRadius: theme.radius, fontWeight: '700',
          fontSize: 15, padding: '12px 28px', border: 'none',
          cursor: 'pointer', fontFamily: theme.font, display: 'inline-block',
        }}
        onClick={e => { if (!onClick) return; e.stopPropagation(); }}
      >
        {p.text || 'Кнопка'}
      </button>
    );
    return wrap(<div style={{ textAlign: 'center' }}>{el}</div>);
  }

  if (type === 'input') {
    return wrap(
      <label style={{ display: 'block' }}>
        {p.label && <span style={{ display: 'block', fontSize: 12, fontWeight: '700', color: theme.textSecondary, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{p.label}{p.required ? ' *' : ''}</span>}
        <input
          type={p.inputType || 'text'}
          placeholder={p.placeholder}
          readOnly
          style={{
            width: '100%', boxSizing: 'border-box', background: theme.surface,
            border: `1px solid ${theme.textSecondary}33`, color: theme.textPrimary,
            borderRadius: theme.radius * 0.7, padding: '10px 14px', fontSize: 15,
            fontFamily: theme.font, outline: 'none',
          }}
        />
      </label>
    );
  }

  if (type === 'textarea') {
    return wrap(
      <label style={{ display: 'block' }}>
        {p.label && <span style={{ display: 'block', fontSize: 12, fontWeight: '700', color: theme.textSecondary, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{p.label}{p.required ? ' *' : ''}</span>}
        <textarea
          placeholder={p.placeholder} readOnly rows={4}
          style={{
            width: '100%', boxSizing: 'border-box', background: theme.surface,
            border: `1px solid ${theme.textSecondary}33`, color: theme.textPrimary,
            borderRadius: theme.radius * 0.7, padding: '10px 14px', fontSize: 15,
            fontFamily: theme.font, outline: 'none', resize: 'vertical',
          }}
        />
      </label>
    );
  }

  if (type === 'image') {
    return wrap(
      <img
        src={p.src} alt={p.alt || ''}
        style={{ width: p.width || '100%', borderRadius: theme.radius, display: 'block', maxWidth: '100%' }}
        onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
      />
    );
  }

  if (type === 'divider') {
    return wrap(
      <hr style={{ border: 'none', borderTop: `1px solid ${p.dividerColor || theme.textSecondary + '40'}`, margin: '4px 0' }} />
    );
  }

  if (type === 'spacer') {
    return wrap(<div style={{ height: p.height || 32 }} />);
  }

  return wrap(<div style={{ color: theme.textSecondary, fontSize: 12 }}>{type}</div>);
};

// ─── Properties Panel ─────────────────────────────────────────────────────────

const PropInput: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <label className="block">
    <span className="block text-[9px] font-black text-zinc-500 uppercase tracking-widest mb-1.5">{label}</span>
    {children}
  </label>
);

const PInput: React.FC<React.InputHTMLAttributes<HTMLInputElement>> = (props) => (
  <input
    {...props}
    className="w-full bg-black border border-zinc-800 focus:border-indigo-500 text-white text-sm p-2.5 rounded-lg outline-none transition-all"
  />
);

const PSelect: React.FC<React.SelectHTMLAttributes<HTMLSelectElement> & { options: { value: string; label: string }[] }> = ({ options, ...rest }) => (
  <select
    {...rest}
    className="w-full bg-black border border-zinc-800 focus:border-indigo-500 text-white text-sm p-2.5 rounded-lg outline-none transition-all cursor-pointer"
  >
    {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
  </select>
);

const ColorRow: React.FC<{ label: string; value: string; placeholder?: string; onChange: (v: string) => void }> = ({ label, value, placeholder, onChange }) => (
  <PropInput label={label}>
    <div className="flex gap-2">
      <div className="relative shrink-0">
        <input type="color" value={value || '#6366f1'} onChange={e => onChange(e.target.value)}
          className="w-10 h-10 rounded-lg border border-zinc-800 bg-black cursor-pointer p-0.5" />
      </div>
      <PInput value={value} placeholder={placeholder || '#ffffff'} onChange={e => onChange(e.target.value)} />
    </div>
  </PropInput>
);

const PropertiesPanel: React.FC<{
  comp: AppComponent | null;
  theme: AppTheme;
  onChange: (id: string, props: Partial<CompProps>) => void;
}> = ({ comp, theme, onChange }) => {
  if (!comp) return (
    <div className="flex flex-col items-center justify-center h-full gap-3 opacity-20 select-none p-8">
      <Layers className="w-12 h-12 text-zinc-500" />
      <p className="text-xs text-zinc-500 font-black uppercase tracking-widest text-center">Выберите компонент</p>
    </div>
  );

  const p = comp.props;
  const up = (patch: Partial<CompProps>) => onChange(comp.id, patch);

  return (
    <div className="p-4 space-y-4 text-sm">
      <div className="text-[9px] font-black uppercase tracking-[0.2em] text-indigo-400 mb-4 flex items-center gap-2">
        <Settings2 className="w-3 h-3" /> Свойства: {comp.type}
      </div>

      {/* TEXT / HEADING ─────────────────── */}
      {(comp.type === 'heading' || comp.type === 'text') && (<>
        <PropInput label="Текст">
          <textarea
            value={p.text || ''}
            rows={3}
            onChange={e => up({ text: e.target.value })}
            className="w-full bg-black border border-zinc-800 focus:border-indigo-500 text-white text-sm p-2.5 rounded-lg outline-none transition-all resize-none"
          />
        </PropInput>
        {comp.type === 'heading' && (
          <PropInput label="Уровень">
            <PSelect value={p.level || 'h2'} onChange={e => up({ level: e.target.value as any })}
              options={[{ value: 'h1', label: 'H1 — Главный' }, { value: 'h2', label: 'H2 — Средний' }, { value: 'h3', label: 'H3 — Малый' }]} />
          </PropInput>
        )}
        <PropInput label="Размер шрифта (px)">
          <PInput type="number" min={10} max={80} value={p.fontSize || 16} onChange={e => up({ fontSize: Number(e.target.value) })} />
        </PropInput>
        <PropInput label="Жирность">
          <PSelect value={p.fontWeight || '400'} onChange={e => up({ fontWeight: e.target.value })}
            options={[{ value: '400', label: 'Обычный' }, { value: '600', label: 'Полужирный' }, { value: '700', label: 'Жирный' }, { value: '800', label: 'Очень жирный' }, { value: '900', label: 'Черный' }]} />
        </PropInput>
        <PropInput label="Выравнивание">
          <div className="flex gap-1">
            {[['left', AlignLeft], ['center', AlignCenter], ['right', AlignRight]].map(([val, Icon]) => (
              <button key={val as string} onClick={() => up({ align: val as any })}
                className={`flex-1 p-2.5 rounded-lg border text-xs font-bold transition-all flex items-center justify-center ${p.align === val ? 'bg-indigo-500/20 border-indigo-500/50 text-indigo-400' : 'border-zinc-800 text-zinc-600 hover:border-zinc-700'}`}>
                <(Icon as React.ElementType) className="w-3.5 h-3.5" />
              </button>
            ))}
          </div>
        </PropInput>
        <ColorRow label="Цвет текста (пусто = авто)" value={p.color || ''} placeholder={theme.textPrimary} onChange={v => up({ color: v })} />
      </>)}

      {/* BUTTON / LINK BUTTON ────────────── */}
      {(comp.type === 'button' || comp.type === 'linkButton') && (<>
        <PropInput label="Текст кнопки">
          <PInput value={p.text || ''} onChange={e => up({ text: e.target.value })} />
        </PropInput>
        <ColorRow label="Цвет фона (пусто = акцент)" value={p.bgColor || ''} placeholder={theme.primary} onChange={v => up({ bgColor: v })} />
        <ColorRow label="Цвет текста" value={p.textColor || '#ffffff'} onChange={v => up({ textColor: v })} />
        {comp.type === 'linkButton' && (
          <PropInput label="URL">
            <PInput type="url" value={p.url || ''} placeholder="https://example.com" onChange={e => up({ url: e.target.value })} />
          </PropInput>
        )}
        {comp.type === 'button' && (
          <PropInput label="Действие">
            <PSelect value={p.action || 'none'} onChange={e => up({ action: e.target.value as any })}
              options={[{ value: 'none', label: 'Нет' }, { value: 'submit', label: 'Отправить форму' }, { value: 'link', label: 'Открыть ссылку' }]} />
          </PropInput>
        )}
        {comp.type === 'button' && p.action === 'link' && (
          <PropInput label="URL">
            <PInput type="url" value={p.url || ''} placeholder="https://" onChange={e => up({ url: e.target.value })} />
          </PropInput>
        )}
      </>)}

      {/* INPUT / TEXTAREA ────────────────── */}
      {(comp.type === 'input' || comp.type === 'textarea') && (<>
        <PropInput label="Подпись поля">
          <PInput value={p.label || ''} onChange={e => up({ label: e.target.value })} />
        </PropInput>
        <PropInput label="Placeholder">
          <PInput value={p.placeholder || ''} onChange={e => up({ placeholder: e.target.value })} />
        </PropInput>
        <PropInput label="Имя поля (name)">
          <PInput value={p.name || ''} onChange={e => up({ name: e.target.value })} />
        </PropInput>
        {comp.type === 'input' && (
          <PropInput label="Тип">
            <PSelect value={p.inputType || 'text'} onChange={e => up({ inputType: e.target.value })}
              options={[{ value: 'text', label: 'Текст' }, { value: 'email', label: 'Email' }, { value: 'tel', label: 'Телефон' }, { value: 'number', label: 'Число' }, { value: 'url', label: 'URL' }]} />
          </PropInput>
        )}
        <div className="flex items-center justify-between p-3 rounded-lg bg-zinc-900/50 border border-zinc-800">
          <span className="text-xs font-bold text-zinc-400">Обязательное поле</span>
          <button onClick={() => up({ required: !p.required })}
            className={`w-10 h-5 rounded-full relative transition-all ${p.required ? 'bg-indigo-500' : 'bg-zinc-700'}`}>
            <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-all ${p.required ? 'left-5' : 'left-0.5'}`} />
          </button>
        </div>
      </>)}

      {/* IMAGE ───────────────────────────── */}
      {comp.type === 'image' && (<>
        <PropInput label="URL изображения">
          <PInput value={p.src || ''} placeholder="https://..." onChange={e => up({ src: e.target.value })} />
        </PropInput>
        <PropInput label="Alt текст">
          <PInput value={p.alt || ''} onChange={e => up({ alt: e.target.value })} />
        </PropInput>
        <PropInput label="Ширина">
          <PSelect value={p.width || '100%'} onChange={e => up({ width: e.target.value })}
            options={[{ value: '100%', label: 'Полная ширина' }, { value: '75%', label: '75%' }, { value: '50%', label: '50%' }, { value: '25%', label: '25%' }, { value: 'auto', label: 'Авто' }]} />
        </PropInput>
      </>)}

      {/* DIVIDER ─────────────────────────── */}
      {comp.type === 'divider' && (
        <ColorRow label="Цвет линии" value={p.dividerColor || ''} placeholder="#334155" onChange={v => up({ dividerColor: v })} />
      )}

      {/* SPACER ──────────────────────────── */}
      {comp.type === 'spacer' && (
        <PropInput label="Высота (px)">
          <PInput type="number" min={4} max={300} value={p.height || 32} onChange={e => up({ height: Number(e.target.value) })} />
        </PropInput>
      )}
    </div>
  );
};

// ─── Theme Panel ──────────────────────────────────────────────────────────────

const ThemePanel: React.FC<{ theme: AppTheme; onChange: (t: Partial<AppTheme>) => void }> = ({ theme, onChange }) => (
  <div className="p-4 space-y-4">
    <div className="text-[9px] font-black uppercase tracking-[0.2em] text-indigo-400 mb-4 flex items-center gap-2">
      <Palette className="w-3 h-3" /> Тема приложения
    </div>

    {/* Presets */}
    <div>
      <span className="block text-[9px] font-black text-zinc-500 uppercase tracking-widest mb-2">Пресеты</span>
      <div className="grid grid-cols-3 gap-1.5">
        {PRESET_THEMES.map(pt => (
          <button key={pt.label} onClick={() => onChange(pt.theme)}
            style={{ background: pt.theme.bg, borderColor: pt.theme.primary + '60' }}
            className="border rounded-lg p-2 text-[9px] font-black uppercase tracking-wider transition-all hover:scale-105 relative overflow-hidden"
          >
            <span style={{ color: pt.theme.textPrimary }}>{pt.label}</span>
            <span className="block w-3 h-3 rounded-full mt-1 mx-auto" style={{ background: pt.theme.primary }} />
          </button>
        ))}
      </div>
    </div>

    <div className="h-px bg-zinc-800" />

    <ColorRow label="Фон" value={theme.bg} onChange={v => onChange({ bg: v })} />
    <ColorRow label="Поверхность (карточки)" value={theme.surface} onChange={v => onChange({ surface: v })} />
    <ColorRow label="Акцентный цвет" value={theme.primary} onChange={v => onChange({ primary: v })} />
    <ColorRow label="Основной текст" value={theme.textPrimary} onChange={v => onChange({ textPrimary: v })} />
    <ColorRow label="Вторичный текст" value={theme.textSecondary} onChange={v => onChange({ textSecondary: v })} />

    <PropInput label="Скругление углов (px)">
      <input type="range" min={0} max={32} value={theme.radius} onChange={e => onChange({ radius: Number(e.target.value) })}
        className="w-full accent-indigo-500" />
      <span className="text-[10px] text-zinc-500 mt-1 block">{theme.radius}px</span>
    </PropInput>

    <PropInput label="Шрифт">
      <select value={theme.font} onChange={e => onChange({ font: e.target.value })}
        className="w-full bg-black border border-zinc-800 focus:border-indigo-500 text-white text-sm p-2.5 rounded-lg outline-none cursor-pointer transition-all">
        {FONT_OPTIONS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
      </select>
    </PropInput>

    <PropInput label="Фоновый градиент (CSS)">
      <PInput value={theme.gradient || ''} placeholder="radial-gradient(...)" onChange={e => onChange({ gradient: e.target.value })} />
    </PropInput>
  </div>
);

// ─── Main Builder ─────────────────────────────────────────────────────────────

interface MiniAppBuilderProps {
  user: User;
}

const MiniAppBuilder: React.FC<MiniAppBuilderProps> = ({ user }) => {
  const [app, setApp] = useState<MiniAppData>({
    title: 'Моё мини-приложение',
    theme: { ...DEFAULT_THEME },
    components: [
      newComp('heading'),
      newComp('text'),
      newComp('button'),
    ],
    formWebhook: '',
  });

  const [selectedId, setSelectedId]   = useState<string | null>(null);
  const [rightTab, setRightTab]       = useState<'props' | 'theme'>('props');
  const [previewMode, setPreviewMode] = useState(false);
  const [saving, setSaving]           = useState(false);
  const [saved, setSaved]             = useState(false);
  const [publishedUrl, setPublishedUrl] = useState<string | null>(null);
  const [savedApps, setSavedApps]     = useState<MiniAppData[]>([]);
  const [loadingApps, setLoadingApps] = useState(false);
  const [showSaved, setShowSaved]     = useState(false);

  const selected = app.components.find(c => c.id === selectedId) || null;

  const addComp = (type: CompType) => {
    const c = newComp(type);
    setApp(a => ({ ...a, components: [...a.components, c] }));
    setSelectedId(c.id);
  };

  const removeComp = (id: string) => {
    setApp(a => ({ ...a, components: a.components.filter(c => c.id !== id) }));
    if (selectedId === id) setSelectedId(null);
  };

  const moveComp = (id: string, dir: -1 | 1) => {
    setApp(a => {
      const comps = [...a.components];
      const idx = comps.findIndex(c => c.id === id);
      const to = idx + dir;
      if (to < 0 || to >= comps.length) return a;
      [comps[idx], comps[to]] = [comps[to], comps[idx]];
      return { ...a, components: comps };
    });
  };

  const updateProps = (id: string, props: Partial<CompProps>) => {
    setApp(a => ({
      ...a,
      components: a.components.map(c => c.id === id ? { ...c, props: { ...c.props, ...props } } : c)
    }));
  };

  const updateTheme = (patch: Partial<AppTheme>) => {
    setApp(a => ({ ...a, theme: { ...a.theme, ...patch } }));
  };

  const saveApp = async () => {
    setSaving(true);
    try {
      const base = '/api';
      const payload = {
        ...app,
        owner_id: user.id,
        id: app.id || mkId(),
      };
      const res = await fetch(`${base}/miniapps/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        const data = await res.json();
        const appId = data.id || payload.id;
        setApp(a => ({ ...a, id: appId }));
        setPublishedUrl(`${window.location.origin}/app/${appId}`);
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      } else {
        alert('Ошибка сохранения. Попробуйте снова.');
      }
    } catch {
      // Если сервер не поддерживает — сохраняем локально
      const appId = app.id || mkId();
      const payload = { ...app, id: appId, owner_id: user.id };
      localStorage.setItem(`miniapp_${appId}`, JSON.stringify(payload));
      setApp(a => ({ ...a, id: appId }));
      setPublishedUrl(`${window.location.origin}/app/${appId}`);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      alert('Сохранено локально (сервер недоступен). Для публикации настройте бэкенд.');
    } finally {
      setSaving(false);
    }
  };

  const { theme } = app;

  const canvasStyle: React.CSSProperties = {
    background: theme.bg,
    fontFamily: theme.font,
    minHeight: '100%',
    position: 'relative',
  };

  const gradientOverlay: React.CSSProperties = theme.gradient ? {
    position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 0,
    background: theme.gradient,
  } : {};

  return (
    <div className="flex flex-col h-full bg-[#080808] text-zinc-300">

      {/* ── TOP BAR ─────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-5 py-3.5 border-b border-zinc-800/80 bg-[#0d0d0d] shrink-0">
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center shrink-0">
            <Layout className="w-4 h-4 text-white" />
          </div>
          <input
            value={app.title}
            onChange={e => setApp(a => ({ ...a, title: e.target.value }))}
            className="text-white font-black text-sm bg-transparent outline-none border-b border-transparent focus:border-indigo-500 transition-all max-w-64 truncate"
            placeholder="Название приложения"
          />
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {/* Preview toggle */}
          <button
            onClick={() => setPreviewMode(p => !p)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-[10px] font-black uppercase tracking-wider transition-all ${previewMode ? 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30' : 'bg-zinc-800 text-zinc-400 hover:text-white border border-zinc-700'}`}
          >
            {previewMode ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            {previewMode ? 'Редактор' : 'Превью'}
          </button>

          {/* Save */}
          <button
            onClick={saveApp}
            disabled={saving}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-[10px] font-black uppercase tracking-wider transition-all shadow-lg ${saved ? 'bg-emerald-600 text-white shadow-emerald-600/20' : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-600/20'}`}
          >
            {saved ? <Check className="w-3.5 h-3.5" /> : <Save className="w-3.5 h-3.5" />}
            {saved ? 'Сохранено!' : saving ? 'Сохраняю...' : 'Сохранить'}
          </button>

          {/* Published URL */}
          {publishedUrl && (
            <a href={publishedUrl} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-[10px] font-black uppercase tracking-wider bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition-all">
              <Globe className="w-3.5 h-3.5" /> Открыть
            </a>
          )}
        </div>
      </div>

      {/* ── BODY ─────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0">

        {/* ── LEFT: PALETTE ─────────────────────────────────── */}
        {!previewMode && (
          <aside className="w-48 border-r border-zinc-800/80 bg-[#0a0a0a] flex flex-col shrink-0 overflow-y-auto">
            <div className="px-4 pt-4 pb-2">
              <p className="text-[9px] font-black text-zinc-500 uppercase tracking-[0.2em]">Компоненты</p>
            </div>
            <div className="px-2 pb-4 space-y-1">
              {PALETTE_ITEMS.map(item => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.type}
                    onClick={() => addComp(item.type)}
                    className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-left text-zinc-400 hover:text-white hover:bg-zinc-800/60 transition-all group"
                  >
                    <div className="w-7 h-7 rounded-lg bg-indigo-500/10 flex items-center justify-center shrink-0 group-hover:bg-indigo-500/20 transition-all">
                      <Icon className="w-3.5 h-3.5 text-indigo-400" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-[11px] font-bold leading-tight truncate">{item.label}</p>
                      <p className="text-[9px] text-zinc-600 leading-tight">{item.desc}</p>
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Webhook */}
            <div className="mt-auto p-4 border-t border-zinc-800/80">
              <p className="text-[9px] font-black text-zinc-500 uppercase tracking-widest mb-2">Webhook формы</p>
              <input
                value={app.formWebhook || ''}
                onChange={e => setApp(a => ({ ...a, formWebhook: e.target.value }))}
                placeholder="https://..."
                className="w-full bg-black border border-zinc-800 focus:border-indigo-500 text-white text-[10px] p-2 rounded-lg outline-none transition-all"
              />
              <p className="text-[8px] text-zinc-700 mt-1 leading-relaxed">POST-запрос с данными формы</p>
            </div>
          </aside>
        )}

        {/* ── CENTER: CANVAS ─────────────────────────────────── */}
        <main
          className="flex-1 overflow-y-auto"
          style={{ background: '#111' }}
          onClick={() => !previewMode && setSelectedId(null)}
        >
          {/* Mini-app frame */}
          <div className="min-h-full flex items-start justify-center py-8 px-4">
            <div
              className="w-full max-w-md shadow-2xl overflow-hidden"
              style={{ borderRadius: theme.radius * 1.2, minHeight: 500 }}
            >
              <div style={canvasStyle}>
                {theme.gradient && <div style={gradientOverlay} />}
                <div style={{ position: 'relative', zIndex: 1, padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>

                  {app.components.length === 0 && (
                    <div style={{ textAlign: 'center', padding: '40px 0', opacity: 0.3 }}>
                      <p style={{ color: theme.textSecondary, fontSize: 13, fontFamily: theme.font }}>
                        Добавьте компоненты из панели слева
                      </p>
                    </div>
                  )}

                  {app.components.map((comp, idx) => (
                    <div
                      key={comp.id}
                      style={{ position: 'relative' }}
                      onClick={e => { if (!previewMode) { e.stopPropagation(); setSelectedId(comp.id); }}}
                    >
                      <PreviewComp
                        comp={comp}
                        theme={theme}
                        selected={!previewMode && selectedId === comp.id}
                        onClick={previewMode ? undefined : () => {}}
                      />

                      {/* Controls overlay */}
                      {!previewMode && selectedId === comp.id && (
                        <div className="absolute -top-2 -right-2 flex gap-1 z-10">
                          <button onClick={e => { e.stopPropagation(); moveComp(comp.id, -1); }}
                            disabled={idx === 0}
                            className="w-6 h-6 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed shadow-lg">
                            <ChevronUp className="w-3 h-3" />
                          </button>
                          <button onClick={e => { e.stopPropagation(); moveComp(comp.id, 1); }}
                            disabled={idx === app.components.length - 1}
                            className="w-6 h-6 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed shadow-lg">
                            <ChevronDown className="w-3 h-3" />
                          </button>
                          <button onClick={e => { e.stopPropagation(); removeComp(comp.id); }}
                            className="w-6 h-6 rounded bg-rose-600/80 hover:bg-rose-500 text-white flex items-center justify-center shadow-lg">
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      )}
                    </div>
                  ))}

                  {/* Add component hint */}
                  {!previewMode && (
                    <div className="border-2 border-dashed border-zinc-700/50 rounded-xl p-4 text-center hover:border-indigo-500/40 transition-all cursor-default">
                      <p style={{ color: theme.textSecondary, opacity: 0.4, fontSize: 12, fontFamily: theme.font }}>
                        + кликните по компоненту в панели слева
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </main>

        {/* ── RIGHT: PROPERTIES ─────────────────────────────── */}
        {!previewMode && (
          <aside className="w-64 border-l border-zinc-800/80 bg-[#0a0a0a] flex flex-col shrink-0">
            {/* Tabs */}
            <div className="flex border-b border-zinc-800/80 shrink-0">
              {[
                { id: 'props', label: 'Свойства', icon: Settings2 },
                { id: 'theme', label: 'Тема',     icon: Palette    },
              ].map(tab => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setRightTab(tab.id as any)}
                    className={`flex-1 flex items-center justify-center gap-1.5 py-3.5 text-[10px] font-black uppercase tracking-widest transition-all border-b-2 ${rightTab === tab.id ? 'border-indigo-500 text-indigo-400' : 'border-transparent text-zinc-600 hover:text-zinc-400'}`}
                  >
                    <Icon className="w-3.5 h-3.5" /> {tab.label}
                  </button>
                );
              })}
            </div>

            <div className="flex-1 overflow-y-auto">
              {rightTab === 'props' ? (
                <PropertiesPanel comp={selected} theme={theme} onChange={updateProps} />
              ) : (
                <ThemePanel theme={theme} onChange={updateTheme} />
              )}
            </div>

            {/* Layer list */}
            {rightTab === 'props' && (
              <div className="border-t border-zinc-800/80 p-3 shrink-0">
                <p className="text-[9px] font-black text-zinc-600 uppercase tracking-widest mb-2 flex items-center gap-1.5">
                  <Layers className="w-3 h-3" /> Слои ({app.components.length})
                </p>
                <div className="space-y-0.5 max-h-32 overflow-y-auto">
                  {app.components.map((c, i) => {
                    const item = PALETTE_ITEMS.find(p => p.type === c.type);
                    const Icon = item?.icon || Square;
                    return (
                      <button key={c.id} onClick={() => setSelectedId(c.id)}
                        className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left text-[10px] transition-all ${selectedId === c.id ? 'bg-indigo-500/15 text-indigo-300' : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40'}`}>
                        <Icon className="w-3 h-3 shrink-0" />
                        <span className="truncate font-bold">{item?.label || c.type}</span>
                        <span className="ml-auto text-zinc-700">{i + 1}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </aside>
        )}
      </div>
    </div>
  );
};

export default MiniAppBuilder;
