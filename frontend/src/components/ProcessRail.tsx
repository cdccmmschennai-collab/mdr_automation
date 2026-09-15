/**
 * The processing rail — shown inside the workbook panel while the real
 * upload / extract / automate requests are in flight. Driven by the request
 * lifecycle in `AutomatePage`, never by timers.
 *
 * Three steps because the backend has exactly three requests to report; no
 * "validating" or "preparing workbook" step is invented, and there is no
 * percentage because none is measured. The activity bar is indeterminate on
 * purpose.
 */

import { Check, Loader2 } from 'lucide-react';

import './ProcessRail.css';

export type ProcessingStage = 'uploading' | 'extracting' | 'automating';

const STEPS: { key: ProcessingStage; label: string; activeLabel: string; detail: string }[] = [
  {
    key: 'uploading',
    label: 'Upload',
    activeLabel: 'Uploading workbook',
    detail: 'Sending the workbook to Auto MDR',
  },
  {
    key: 'extracting',
    label: 'Extract',
    activeLabel: 'Extracting workbook data',
    detail: 'Reading MDR rows and document information',
  },
  {
    key: 'automating',
    label: 'Automate',
    activeLabel: 'Applying automation rules',
    detail: 'Resolving DOC TYPE, SOW and IDB for every row',
  },
];

interface ProcessRailProps {
  stage: ProcessingStage;
  /** True once the active stage's request has actually succeeded. */
  done: boolean;
}

export function ProcessRail({ stage, done }: ProcessRailProps) {
  const activeIndex = STEPS.findIndex((step) => step.key === stage);
  const active = STEPS[activeIndex];
  const allDone = activeIndex === STEPS.length - 1 && done;

  return (
    <div className="amdr-rail" role="status" aria-live="polite">
      <div className="amdr-rail__label">Processing workbook</div>

      <ol className="amdr-rail__steps">
        {STEPS.map((step, index) => {
          const isDone = index < activeIndex || (index === activeIndex && done);
          const isActive = index === activeIndex && !done;
          const className = [
            'amdr-rail__step',
            isDone && 'amdr-rail__step--done',
            isActive && 'amdr-rail__step--active',
          ]
            .filter(Boolean)
            .join(' ');

          return (
            <li className={className} key={step.key} aria-current={isActive ? 'step' : undefined}>
              <span className="amdr-rail__marker">
                {isDone ? (
                  <Check size={12} color="#FFFFFF" strokeWidth={3} />
                ) : isActive ? (
                  <Loader2 size={13} color="#1B5F95" className="spin-icon" />
                ) : null}
              </span>
              <span className="amdr-rail__step-label">{step.label}</span>
              {index < STEPS.length - 1 && <span className="amdr-rail__connector" aria-hidden="true" />}
            </li>
          );
        })}
      </ol>

      <div className="amdr-rail__current">
        <div className="amdr-rail__current-title">
          {allDone ? 'Automation applied' : active?.activeLabel}
        </div>
        <div className="amdr-rail__current-detail">
          {allDone ? 'Loading the result summary' : active?.detail}
        </div>
      </div>

      <div className="amdr-rail__activity" aria-hidden="true">
        <span className="amdr-rail__activity-bar" />
      </div>

      <p className="amdr-rail__note">Keep this page open while Auto MDR completes the automation.</p>
    </div>
  );
}
