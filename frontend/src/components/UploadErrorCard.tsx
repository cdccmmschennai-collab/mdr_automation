/**
 * Inline validation error for an unsupported workbook format. Visually this
 * reuses the approved design's error card (`isError` in Auto MDR.dc.html —
 * same container, icon circle, message pill and single action), with copy
 * specific to this frontend validation step rather than a Phase 3 automation
 * failure.
 */

import { AlertTriangle, Upload } from 'lucide-react';

import './UploadErrorCard.css';

interface UploadErrorCardProps {
  fileName: string;
  message: string;
  onChooseAnother: () => void;
}

export function UploadErrorCard({ fileName, message, onChooseAnother }: UploadErrorCardProps) {
  return (
    <div className="amdr-error-card">
      <div className="amdr-error-card__icon">
        <AlertTriangle size={24} color="#B23B27" strokeWidth={2} />
      </div>
      <h2 className="amdr-error-card__heading">Unsupported file type</h2>
      <p className="amdr-error-card__subtext">&ldquo;{fileName}&rdquo; isn&rsquo;t a supported workbook format.</p>
      <div className="amdr-error-card__message">
        <p>{message}</p>
      </div>
      <button type="button" className="amdr-error-card__button" onClick={onChooseAnother}>
        <Upload size={15} color="#FFFFFF" />
        Choose another workbook
      </button>
    </div>
  );
}
