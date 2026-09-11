/**
 * The upload-card illustration: a workbook page with a badge-pulse "ready"
 * arrow. Geometry and colors copied verbatim from the approved design's
 * inline SVG so the shape matches exactly — this is not a redrawn icon.
 */

import './WorkbookIllustration.css';

export function WorkbookIllustration() {
  return (
    <div className="amdr-illo">
      <svg viewBox="0 0 240 260" width="185" height="200" style={{ display: 'block' }}>
        <polygon
          points="150,10 190,50 150,50"
          fill="#FFF4C7"
          stroke="#F2C94C"
          strokeWidth="3"
          strokeLinejoin="round"
        />
        <rect x="30" y="10" width="160" height="220" rx="14" fill="#FFFFFF" stroke="#F2C94C" strokeWidth="3" />
        <rect x="46" y="34" width="128" height="28" rx="6" fill="#F2C94C" />
        <rect x="46" y="76" width="38" height="32" rx="4" fill="none" stroke="#F2C94C" strokeWidth="2.5" />
        <rect x="90" y="76" width="38" height="32" rx="4" fill="none" stroke="#F2C94C" strokeWidth="2.5" />
        <rect
          x="134"
          y="76"
          width="40"
          height="32"
          rx="4"
          fill="#2EAD63"
          opacity="0.16"
          stroke="#2EAD63"
          strokeWidth="2.5"
        />
        <rect x="46" y="118" width="38" height="32" rx="4" fill="none" stroke="#F2C94C" strokeWidth="2.5" />
        <rect x="90" y="118" width="38" height="32" rx="4" fill="none" stroke="#F2C94C" strokeWidth="2.5" />
        <rect x="134" y="118" width="40" height="32" rx="4" fill="none" stroke="#F2C94C" strokeWidth="2.5" />
        <rect x="46" y="160" width="38" height="32" rx="4" fill="none" stroke="#F2C94C" strokeWidth="2.5" />
        <rect x="90" y="160" width="38" height="32" rx="4" fill="none" stroke="#F2C94C" strokeWidth="2.5" />
        <rect x="134" y="160" width="40" height="32" rx="4" fill="none" stroke="#F2C94C" strokeWidth="2.5" />
        <circle className="badge-pulse-ring" cx="182" cy="196" r="36" fill="none" stroke="#1B5F95" strokeWidth="3" />
        <circle cx="182" cy="196" r="36" fill="#1B5F95" />
        <path
          d="M168 196 h26 M186 184 l12 12 -12 12"
          stroke="#FFFFFF"
          strokeWidth="4"
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}
