/**
 * The only page in the scaffold.
 *
 * It reports whether the backend is reachable. It deliberately does NOT show
 * MDR results: result display, upload and exception triage are Phase 7, and a
 * screen for capabilities that do not exist yet would be a fake dashboard.
 */

import { useEffect, useState } from 'react';

import { getHealth } from '../services/healthService';
import type { HealthResponse } from '../types/api';

type State =
  | { kind: 'loading' }
  | { kind: 'ok'; health: HealthResponse }
  | { kind: 'error'; message: string };

export function StatusPage() {
  const [state, setState] = useState<State>({ kind: 'loading' });

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((health) => {
        if (!cancelled) setState({ kind: 'ok', health });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({
            kind: 'error',
            message: error instanceof Error ? error.message : String(error),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="page">
      <h1>MDR Automation Tool</h1>
      <p className="lede">
        Frontend scaffold. The MDR engine runs in the backend; this page only
        checks that the API boundary is reachable.
      </p>

      <section>
        <h2>Backend</h2>
        {state.kind === 'loading' && <p>Checking…</p>}
        {state.kind === 'ok' && (
          <p className="ok">
            Reachable — status <code>{state.health.status}</code>, phase{' '}
            <code>{state.health.phase}</code>.
          </p>
        )}
        {state.kind === 'error' && (
          <p className="error">
            Not reachable: {state.message}
            <br />
            Start it with <code>uvicorn app.main:app --reload</code> from{' '}
            <code>backend/</code>.
          </p>
        )}
      </section>

      <section>
        <h2>Not implemented</h2>
        <p>
          Upload, run history, result browsing, exception triage and
          authentication are Phase 7. Classification, SOW, IDB, check status and
          Excel output are Phases 2–5.
        </p>
      </section>
    </main>
  );
}
