/**
 * The workspace's content once a workbook has been chosen — for every state
 * from "selected" through processing to complete or failed.
 *
 * The top of the panel is constant: the WORKBOOK label and the workbook row
 * (icon, filename, type · size, check). Only the body beneath it changes
 * with the state — the action row, the process rail, the result, or the
 * failure — so the user always sees which workbook Auto MDR is working on,
 * inside the same frame, while the job moves along.
 *
 * Pure presentation: the state machine lives in `AutomatePage`.
 */

import { ArrowRight, CheckCircle2, FileSpreadsheet, X } from 'lucide-react';

import type { SummaryResponse } from '../types/api';
import { AutomationErrorCard } from './AutomationErrorCard';
import { ProcessRail, type ProcessingStage } from './ProcessRail';
import { ResultCard } from './ResultCard';
import './WorkbookPanel.css';

export type WorkbookPanelState =
  | { kind: 'selected' }
  | { kind: 'processing'; stage: ProcessingStage; done: boolean }
  | { kind: 'complete'; mdrId: string; summary?: SummaryResponse; summaryError?: string }
  | { kind: 'failed'; message: string };

interface WorkbookPanelProps {
  file: File;
  state: WorkbookPanelState;
  /** Why Run Automation is unavailable (no plant selected), or undefined. */
  runBlockedReason?: string;
  onRunAutomation: () => void;
  onChangeWorkbook: () => void;
  onRetry: () => void;
  onRetrySummary: () => void;
}

function formatFileSize(bytes: number): string {
  if (!bytes) return '';
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(0)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

function describeWorkbook(file: File): string {
  const isXlsm = file.name.toLowerCase().endsWith('.xlsm');
  const typeLabel = isXlsm ? 'Excel macro-enabled workbook (.xlsm)' : 'Excel workbook (.xlsx)';
  const sizeLabel = formatFileSize(file.size);
  return sizeLabel ? `${typeLabel} · ${sizeLabel}` : typeLabel;
}

export function WorkbookPanel({
  file,
  state,
  runBlockedReason,
  onRunAutomation,
  onChangeWorkbook,
  onRetry,
  onRetrySummary,
}: WorkbookPanelProps) {
  const isRunBlocked = Boolean(runBlockedReason);

  return (
    <div className="amdr-workbook">
      <div className="amdr-workbook__label">Workbook</div>
      <div className="amdr-workbook__row">
        <span className="amdr-workbook__icon" aria-hidden="true">
          <FileSpreadsheet size={22} color="#1B5F95" strokeWidth={1.75} />
        </span>
        <div className="amdr-workbook__info">
          <div className="amdr-workbook__name" title={file.name}>
            {file.name}
          </div>
          <div className="amdr-workbook__meta">{describeWorkbook(file)}</div>
        </div>
        <span className="amdr-workbook__check" aria-label="Workbook ready">
          <CheckCircle2 size={20} color="#2EAD63" />
        </span>
      </div>

      {/* Keyed by state so each body settles in freshly when the state
          changes, while the header above it stays put. */}
      <div className="amdr-workbook__body settle-in" key={state.kind}>
        {state.kind === 'selected' && (
          <div className="amdr-workbook__actions">
            <button
              type="button"
              className="amdr-workbook__run"
              onClick={onRunAutomation}
              disabled={isRunBlocked}
              aria-describedby={isRunBlocked ? 'amdr-run-blocked' : undefined}
            >
              Run Automation
              <ArrowRight size={17} color="#FFFFFF" />
            </button>
            <button type="button" className="amdr-workbook__change" onClick={onChangeWorkbook}>
              <X size={14} />
              Change workbook
            </button>
            {isRunBlocked && (
              <p className="amdr-workbook__blocked" id="amdr-run-blocked">
                {runBlockedReason}
              </p>
            )}
          </div>
        )}

        {state.kind === 'processing' && <ProcessRail stage={state.stage} done={state.done} />}

        {state.kind === 'complete' && (
          <ResultCard
            fileName={file.name}
            mdrId={state.mdrId}
            summary={state.summary}
            summaryError={state.summaryError}
            onRetrySummary={onRetrySummary}
            onReset={onChangeWorkbook}
          />
        )}

        {state.kind === 'failed' && (
          <AutomationErrorCard message={state.message} onRetry={onRetry} onChangeWorkbook={onChangeWorkbook} />
        )}
      </div>
    </div>
  );
}
