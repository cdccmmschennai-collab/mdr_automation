/**
 * The completion card — the approved design's `isComplete` state (Auto
 * MDR.dc.html), reached once `POST .../automate` has actually succeeded.
 *
 * The counter grid mirrors the design's 2x2 layout but shows only fields the
 * real `GET .../summary` response returns (`SummaryResponse` in
 * `backend/app/api/schemas/mdr.py`) — nothing here is computed or invented.
 * A summary fetch failure is shown inline with its own retry and never
 * implies the automation itself failed; same for a download failure.
 */

import { useState } from 'react';
import { AlertTriangle, Check, Download, Loader2 } from 'lucide-react';

import type { SummaryResponse } from '../types/api';
import { downloadWorkbook } from '../services/mdrService';
import './ResultCard.css';

interface ResultCardProps {
  fileName: string;
  mdrId: string;
  summary?: SummaryResponse;
  summaryError?: string;
  onRetrySummary: () => void;
  onReset: () => void;
}

function triggerBrowserDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function ResultCard({ fileName, mdrId, summary, summaryError, onRetrySummary, onReset }: ResultCardProps) {
  const [downloadState, setDownloadState] = useState<'idle' | 'downloading' | 'error'>('idle');
  const [downloadError, setDownloadError] = useState('');

  const handleDownload = async () => {
    if (downloadState === 'downloading') return;
    setDownloadState('downloading');
    setDownloadError('');
    try {
      const { blob, filename } = await downloadWorkbook(mdrId);
      triggerBrowserDownload(blob, filename ?? fileName);
      setDownloadState('idle');
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : 'The workbook could not be downloaded.';
      setDownloadError(message);
      setDownloadState('error');
    }
  };

  return (
    <div className="amdr-result-card">
      <div className="amdr-result-card__icon">
        <Check size={26} color="#F2C94C" strokeWidth={2.5} />
      </div>
      <h2 className="amdr-result-card__heading">Automation complete</h2>
      <p className="amdr-result-card__subtext">Your MDR workbook has been automated successfully.</p>

      {summary && (
        <div className="amdr-result-card__grid">
          <div className="amdr-result-card__stat">
            <div className="amdr-result-card__stat-value">{summary.row_count.toLocaleString()}</div>
            <div className="amdr-result-card__stat-label">Rows processed</div>
          </div>
          <div className="amdr-result-card__stat">
            <div className="amdr-result-card__stat-value">{summary.idb_populated.toLocaleString()}</div>
            <div className="amdr-result-card__stat-label">IDB automated</div>
          </div>
          <div className="amdr-result-card__stat">
            <div className="amdr-result-card__stat-value amdr-result-card__stat-value--warning">
              {summary.idb_manual_check_required.toLocaleString()}
            </div>
            <div className="amdr-result-card__stat-label">Manual check required</div>
          </div>
          <div className="amdr-result-card__stat">
            <div className="amdr-result-card__stat-value amdr-result-card__stat-value--error">
              {summary.sow_unresolved.toLocaleString()}
            </div>
            <div className="amdr-result-card__stat-label">SOW unresolved</div>
          </div>
        </div>
      )}

      {summaryError && (
        <div className="amdr-result-card__summary-error">
          <AlertTriangle size={15} color="#B23B27" />
          <p>{summaryError}</p>
          <button type="button" className="amdr-result-card__inline-retry" onClick={onRetrySummary}>
            Retry
          </button>
        </div>
      )}

      <button
        type="button"
        className="amdr-result-card__download-button"
        onClick={() => void handleDownload()}
        disabled={downloadState === 'downloading'}
      >
        {downloadState === 'downloading' ? (
          <Loader2 size={17} color="#FFFFFF" className="spin-icon" />
        ) : (
          <Download size={17} color="#FFFFFF" />
        )}
        {downloadState === 'downloading' ? 'Downloading…' : 'Download MDR Workbook'}
      </button>

      {downloadState === 'error' && (
        <div className="amdr-result-card__download-error">
          <AlertTriangle size={14} color="#B23B27" />
          <p>{downloadError}</p>
        </div>
      )}

      <a
        href="#"
        className="amdr-result-card__reset-link"
        onClick={(event) => {
          event.preventDefault();
          onReset();
        }}
      >
        Automate another workbook
      </a>
    </div>
  );
}
