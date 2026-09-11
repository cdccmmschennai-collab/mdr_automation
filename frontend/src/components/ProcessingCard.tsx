/**
 * The processing card — the approved design's `isProcessing` state
 * (Auto MDR.dc.html), driven by the real upload/extract/automate request
 * lifecycle rather than timers.
 *
 * Only three stages: the backend has no "validating" or "preparing summary"
 * step to report, so the design's five-stage list is trimmed to the three
 * real requests instead of inventing progress for steps that don't exist.
 */

import { Check, Loader2, Lock } from 'lucide-react';

import './ProcessingCard.css';

export type ProcessingStage = 'uploading' | 'extracting' | 'automating';

const STAGES: { key: ProcessingStage; label: string }[] = [
  { key: 'uploading', label: 'Uploading workbook' },
  { key: 'extracting', label: 'Extracting workbook data' },
  { key: 'automating', label: 'Automating MDR data' },
];

interface ProcessingCardProps {
  fileName: string;
  stage: ProcessingStage;
  /** True once the active stage's request has actually succeeded. */
  done: boolean;
}

export function ProcessingCard({ fileName, stage, done }: ProcessingCardProps) {
  const activeIndex = STAGES.findIndex((s) => s.key === stage);

  return (
    <div className="amdr-processing-card">
      <h2 className="amdr-processing-card__heading">Automating your workbook</h2>
      <p className="amdr-processing-card__subtext">Processing {fileName}</p>

      <div className="amdr-processing-card__steps">
        {STAGES.map((step, index) => {
          const isDone = index < activeIndex || (index === activeIndex && done);
          const isActive = index === activeIndex && !done;
          const labelClassName = [
            'amdr-processing-card__step-label',
            (isDone || isActive) && 'amdr-processing-card__step-label--reached',
            isActive && 'amdr-processing-card__step-label--current',
          ]
            .filter(Boolean)
            .join(' ');

          return (
            <div className="amdr-processing-card__step" key={step.key}>
              {isDone ? (
                <span className="amdr-processing-card__step-icon amdr-processing-card__step-icon--done">
                  <Check size={13} color="#FFFFFF" />
                </span>
              ) : isActive ? (
                <span className="amdr-processing-card__step-icon amdr-processing-card__step-icon--active">
                  <Loader2 size={14} color="#B9860A" className="spin-icon" />
                </span>
              ) : (
                <span className="amdr-processing-card__step-icon amdr-processing-card__step-icon--pending" />
              )}
              <span className={labelClassName}>{step.label}</span>
            </div>
          );
        })}
      </div>

      <div className="amdr-processing-card__note">
        <Lock size={14} color="#6F7880" />
        <p>Keep this page open while Auto MDR completes the automation.</p>
      </div>
    </div>
  );
}
