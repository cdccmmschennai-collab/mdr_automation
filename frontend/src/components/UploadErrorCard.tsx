/**
 * Inline validation error for an unsupported workbook format, shown inside
 * the workspace frame in place of the upload content. Same error visual
 * language as `AutomationErrorCard` (shared `UploadErrorCard.css`), with copy
 * specific to this frontend validation step. There is no valid workbook to
 * show, so this state has no workbook row above it.
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
    <div className="amdr-error amdr-error--centered" role="alert">
      <div className="amdr-error__center">
        <span className="amdr-error__icon amdr-error__icon--large">
          <AlertTriangle size={24} color="#B23B27" strokeWidth={2} />
        </span>
        <h2 className="amdr-error__heading">Unsupported file type</h2>
        <p className="amdr-error__subtext">&ldquo;{fileName}&rdquo; isn&rsquo;t a supported workbook format.</p>
        <div className="amdr-error__message">
          <p>{message}</p>
        </div>
        <button type="button" className="amdr-error__button" onClick={onChooseAnother}>
          <Upload size={15} color="#FFFFFF" />
          Choose another workbook
        </button>
      </div>
    </div>
  );
}
