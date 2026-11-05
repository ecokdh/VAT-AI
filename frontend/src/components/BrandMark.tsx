// VAT-AI 영수증 로고. 색은 사용하는 화면의 CSS(.brand-mark__*)에서 정한다.
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg className={`brand-mark ${className ?? ""}`} viewBox="0 0 96 96" aria-hidden="true">
      <path className="brand-mark__body" d="M18 12 Q18 8 22 8 H74 Q78 8 78 12 V86 L73 80 L68 86 L63 80 L58 86 L53 80 L48 86 L43 80 L38 86 L33 80 L28 86 L23 80 L18 86 Z" />
      <rect className="brand-mark__line" x="28" y="20" width="22" height="5" rx="1" />
      <path className="brand-mark__spark" d="M64 13 Q64 22 73 22 Q64 22 64 31 Q64 22 55 22 Q64 22 64 13 Z" />
      <path className="brand-mark__check" d="M31 50 L43 62 L65 38" fill="none" strokeWidth="9" strokeLinejoin="miter" />
    </svg>
  );
}

// 기울어진 각진 "VAT-AI" 글자. 색은 .brand-word__vat / .brand-word__ai 로 정한다.
export function BrandWordmark({ className }: { className?: string }) {
  return (
    <svg className={`brand-word ${className ?? ""}`} viewBox="0 0 188 48" aria-hidden="true">
      <g transform="translate(12 0) skewX(-14)">
        <path className="brand-word__vat" d="M0 0 H10 L17 30 L24 0 H34 L22 48 H12 Z" />
        <path className="brand-word__vat" fillRule="evenodd" d="M50 0 H60 L72 48 H62 L59.5 38 H50.5 L48 48 H38 Z M52.75 29 L55 20 L57.25 29 Z" />
        <path className="brand-word__vat" d="M76 0 H106 V10 H96 V48 H86 V10 H76 Z" />
        <path className="brand-word__ai" d="M110 20 H124 V29 H110 Z" />
        <path className="brand-word__ai" fillRule="evenodd" d="M140 0 H150 L162 48 H152 L149.5 38 H140.5 L138 48 H128 Z M142.75 29 L145 20 L147.25 29 Z" />
        <path className="brand-word__ai" d="M166 0 H176 V48 H166 Z" />
      </g>
    </svg>
  );
}
