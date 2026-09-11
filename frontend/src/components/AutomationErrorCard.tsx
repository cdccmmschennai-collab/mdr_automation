/**
 * Shown when a real upload/extract/automate request fails. Same error-card
 * visual language as `UploadErrorCard` (Auto MDR.dc.html's `isError` state
 * — same container, icon circle and message pill, `UploadErrorCard.css`
 * shared between the two) with copy for an actual backend failure and a
 * retry action, since the file is still held in memory and nothing has to
 * be re-selected to try again.
 */

import { AlertTriangle } from 'lucide-react';

import './UploadErrorCard.css';

interface AutomationErrorCardProps {
  fileName: string;
  message: string;
  onRetry: () => void;
  onChangeWorkbook: () => void;
}

export function AutomationErrorCard({ fileName, message, onRetry, onChangeWorkbook }: AutomationErrorCardProps) {
  return (
    <div className="amdr-error-card">
      <div className="amdr-error-card__icon">
        <AlertTriangle size={24} color="#B23B27" strokeWidth={2} />
      </div>
      <h2 className="amdr-error-card__heading">Automation couldn&rsquo;t be completed</h2>
      <p className="amdr-error-card__subtext">{fileName}</p>
      <div className="amdr-error-card__message">
        <p>{message}</p>
      </div>
      <div className="amdr-error-card__actions">
        <button type="button" className="amdr-error-card__button" onClick={onRetry}>
          Try again
        </button>
        <button type="button" className="amdr-error-card__secondary-button" onClick={onChangeWorkbook}>
          Change workbook
        </button>
      </div>
    </div>
  );
}
