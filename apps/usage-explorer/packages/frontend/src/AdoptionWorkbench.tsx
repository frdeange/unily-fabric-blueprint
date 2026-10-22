import { useState } from 'react';
import {
  ArrowRight,
  BookOpen,
  CheckCheck,
  Compass,
  Database,
  LayoutDashboard,
  Moon,
  RefreshCw,
  ShieldCheck,
  Sun,
} from 'lucide-react';
import type { DiagnosisRecord, FollowUpRecord } from '@rayfin-app/shared';

import { Investigation } from '@/components/Investigation';
import { ActionForm, DiagnosisForm } from '@/components/RecordForms';
import { ActionBoard, DiagnosisWorkspace } from '@/components/RecordWorkspace';
import { Empty, Notice } from '@/components/workbench-parts';
import { useAdoption } from '@/hooks/use-adoption';
import { useWorkbench } from '@/hooks/use-workbench';
import { useAppTheme } from '@/hooks/use-theme';
import type { AdoptionRow } from '@/lib/adoption';
import { isOverdue } from '@/lib/adoption';
import {
  createDiagnosis,
  createFollowUp,
  updateDiagnosis,
  updateFollowUp,
} from '@/lib/workbench-repository';

type View = 'investigate' | 'diagnoses' | 'actions';
type Editor =
  | { kind: 'capture'; row: AdoptionRow; previous?: AdoptionRow }
  | { kind: 'diagnosis'; record: DiagnosisRecord }
  | { kind: 'action'; diagnosis: DiagnosisRecord; record?: FollowUpRecord };

export function AdoptionWorkbench() {
  const analytics = useAdoption();
  const records = useWorkbench();
  const { isDark, toggleTheme } = useAppTheme();
  const [view, setView] = useState<View>('investigate');
  const [tenantChoice, setTenant] = useState('');
  const [periodChoice, setPeriod] = useState('');
  const [feature, setFeature] = useState('');
  const [diagnosisId, setDiagnosisId] = useState('');
  const [editor, setEditor] = useState<Editor>();
  const [notice, setNotice] = useState('');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const tenant =
    analytics.status === 'ready' &&
    analytics.totals.some((row) => row.tenant === tenantChoice)
      ? tenantChoice
      : analytics.status === 'ready'
        ? (analytics.totals[0]?.tenant ?? '')
        : '';
  const available =
    analytics.status === 'ready'
      ? analytics.totals
          .filter((row) => row.tenant === tenant)
          .map((row) => row.period)
          .sort()
          .reverse()
      : [];
  const period = available.includes(periodChoice)
    ? periodChoice
    : (available[0] ?? '');
  const selected =
    records.diagnoses.find((record) => record.id === diagnosisId) ??
    records.diagnoses[0];
  const openActions = records.actions.filter(
    (action) => action.status !== 'Done',
  );
  const navigate = (next: View) => {
    setView(next);
    setEditor(undefined);
    setNotice('');
  };
  const title =
    view === 'investigate'
      ? 'Investigate adoption'
      : view === 'diagnoses'
        ? 'Your evidence library'
        : 'Your action workspace';

  return (
    <div className="min-h-screen bg-background font-base text-300 text-foreground">
      <a
        href="#workbench-content"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-card focus:p-400"
      >
        Skip to workspace
      </a>
      <div className="mx-auto grid min-h-screen max-w-workbench lg:grid-cols-[var(--wb-shell-columns)]">
        <aside className="flex flex-col border-b bg-card p-500 lg:border-r lg:border-b-0">
          <div className="flex items-center gap-300">
            <span className="rounded-xl bg-primary p-300 text-primary-foreground">
              <Compass className="icon-size-400" aria-hidden="true" />
            </span>
            <div>
              <p className="font-semibold">Adoption</p>
              <p className="text-200 text-muted-foreground">WORKBENCH / LAB</p>
            </div>
          </div>
          <nav
            aria-label="Workbench"
            className="mt-600 flex flex-wrap gap-200 lg:flex-col"
          >
            {(
              [
                ['investigate', 'Investigate', Compass],
                ['diagnoses', 'My diagnoses', BookOpen],
                ['actions', 'Action board', CheckCheck],
              ] as const
            ).map(([key, label, Icon]) => (
              <button
                key={key}
                className={`flex items-center gap-300 rounded-xl px-400 py-300 text-left font-medium ${view === key ? 'bg-accent text-primary' : 'text-muted-foreground hover:bg-muted'}`}
                aria-current={view === key ? 'page' : undefined}
                onClick={() => navigate(key)}
              >
                <Icon className="icon-size-300" aria-hidden="true" />
                {label}
              </button>
            ))}
          </nav>
          <div className="mt-600 hidden rounded-xl border p-400 lg:mt-auto lg:block">
            <ShieldCheck
              className="icon-size-300 text-primary"
              aria-hidden="true"
            />
            <p className="mt-300 font-semibold">Your private workspace</p>
            <p className="mt-200 text-200 leading-300 text-muted-foreground">
              Diagnoses and actions belong to your signed-in account. Source
              data stays read-only.
            </p>
          </div>
          <p className="mt-400 text-200 leading-300 text-muted-foreground">
            Proposed demo scenario. Not a confirmed Unily process.
          </p>
        </aside>

        <div className="min-w-0">
          <header className="flex flex-wrap items-center justify-between gap-300 border-b bg-card px-500 py-400 lg:px-800">
            <div className="flex items-center gap-200 text-200 text-muted-foreground">
              <LayoutDashboard className="icon-size-200" aria-hidden="true" />
              <span>Product analytics</span>
              <ArrowRight className="icon-size-100" />
              <span className="text-foreground">{title}</span>
            </div>
            <div className="flex items-center gap-200">
              <span className="wb-badge">
                <Database className="icon-size-100" /> Synthetic lab source
              </span>
              <button
                className="wb-secondary"
                aria-label="Toggle light and dark theme"
                onClick={toggleTheme}
              >
                {isDark ? (
                  <Sun className="icon-size-200" />
                ) : (
                  <Moon className="icon-size-200" />
                )}
              </button>
            </div>
          </header>

          <main id="workbench-content" className="space-y-500 p-500 lg:p-800">
            <div className="flex flex-wrap items-end justify-between gap-400">
              <div>
                <p className="wb-eyebrow">From observation to follow-through</p>
                <h1 className="mt-200 text-hero-800 font-semibold tracking-tight">
                  Adoption Workbench
                </h1>
                <p className="mt-200 max-w-2xl text-400 leading-500 text-muted-foreground">
                  Investigate the evidence. Capture your thinking. Make the next
                  step happen.
                </p>
              </div>
              <button
                className="wb-secondary"
                disabled={
                  records.status === 'loading' || analytics.status === 'loading'
                }
                onClick={() => {
                  void analytics.refresh();
                  void records.refresh();
                }}
              >
                <RefreshCw className="icon-size-200" /> Refresh workspace
              </button>
            </div>
            <ol
              className="grid gap-300 text-300 sm:grid-cols-3"
              aria-label="Your investigation workflow"
            >
              <li className="rounded-xl border bg-card p-400">
                <span className="wb-eyebrow">01 / Investigate</span>
                <p className="mt-100 text-muted-foreground">
                  Live tenant and feature evidence
                </p>
              </li>
              <li className="rounded-xl border bg-card p-400">
                <span className="wb-eyebrow">02 / Diagnose</span>
                <p className="mt-100 text-muted-foreground">
                  {records.status === 'ready'
                    ? `${records.diagnoses.length} saved diagnoses`
                    : 'Private evidence library'}
                </p>
              </li>
              <li className="rounded-xl border bg-card p-400">
                <span className="wb-eyebrow">03 / Follow through</span>
                <p className="mt-100 text-muted-foreground">
                  {records.status === 'ready'
                    ? `${openActions.length} open actions / ${openActions.filter((action) => isOverdue(action.dueDate, action.status)).length} overdue`
                    : 'Persistent action tracking'}
                </p>
              </li>
            </ol>

            {notice && (
              <p
                role="status"
                className="rounded-xl border border-primary bg-card p-400"
              >
                {notice}
              </p>
            )}
            {records.status === 'error' && (
              <Notice
                title="Saved-records connection needs attention"
                retry={() => void records.refresh()}
              >
                {records.error} Live investigation can still be used
                independently.
              </Notice>
            )}

            {editor?.kind === 'capture' && (
              <DiagnosisForm
                key="capture"
                evidence={editor.row}
                previous={editor.previous}
                close={() => setEditor(undefined)}
                save={async (input) => {
                  const record = await createDiagnosis(input);
                  records.storeDiagnosis(record);
                  setDiagnosisId(record.id);
                  setEditor(undefined);
                  setView('diagnoses');
                  setNotice(
                    'Diagnosis saved with its evidence snapshot. Add a follow-up when you are ready.',
                  );
                }}
              />
            )}
            {editor?.kind === 'diagnosis' && (
              <DiagnosisForm
                key={editor.record.id}
                existing={editor.record}
                close={() => setEditor(undefined)}
                save={async (input) => {
                  const record = await updateDiagnosis(editor.record.id, {
                    title: input.title,
                    notes: input.notes,
                  });
                  records.storeDiagnosis(record);
                  setEditor(undefined);
                  setNotice(
                    'Diagnosis updated. Its captured evidence is unchanged.',
                  );
                }}
              />
            )}
            {editor?.kind === 'action' && (
              <ActionForm
                key={editor.record?.id ?? editor.diagnosis.id}
                diagnosis={editor.diagnosis}
                existing={editor.record}
                close={() => setEditor(undefined)}
                save={async (input) => {
                  const record = editor.record
                    ? await updateFollowUp(editor.record.id, input)
                    : await createFollowUp({
                        ...input,
                        diagnosis_id: editor.diagnosis.id,
                      });
                  records.storeAction(record);
                  setEditor(undefined);
                  setView('actions');
                  setSearch('');
                  setFilter('all');
                  setNotice(
                    'Action saved. Its owner is you, and it remains linked to the original diagnosis.',
                  );
                }}
              />
            )}

            {view === 'investigate' &&
              (analytics.status === 'loading' ? (
                <div role="status" className="wb-panel animate-pulse">
                  Loading live tenant and feature evidence from
                  ProductAnalytics_Safe...
                </div>
              ) : analytics.status === 'error' ? (
                <Notice
                  title="Live analytics are unavailable"
                  retry={() => void analytics.refresh()}
                >
                  {analytics.message} Saved diagnoses and actions do not depend
                  on a successful live query.
                </Notice>
              ) : analytics.totals.length === 0 ? (
                <Empty title="The model returned no observations">
                  Check source data availability and your model permissions. No
                  sample values have been substituted.
                </Empty>
              ) : (
                <Investigation
                  totals={analytics.totals}
                  features={analytics.features}
                  tenant={tenant}
                  period={period}
                  feature={feature}
                  setTenant={setTenant}
                  setPeriod={setPeriod}
                  setFeature={setFeature}
                  save={(row, previous) => {
                    setEditor({ kind: 'capture', row, previous });
                    setNotice('');
                  }}
                  canSave={records.status === 'ready'}
                />
              ))}
            {view !== 'investigate' && records.status === 'loading' && (
              <p role="status" className="wb-panel">
                Loading your saved records...
              </p>
            )}
            {view === 'diagnoses' && records.status === 'ready' && (
              <DiagnosisWorkspace
                diagnoses={records.diagnoses}
                actions={records.actions}
                selected={selected}
                select={setDiagnosisId}
                edit={(record) => setEditor({ kind: 'diagnosis', record })}
                addAction={(diagnosis) =>
                  setEditor({ kind: 'action', diagnosis })
                }
                inspect={(record) => {
                  navigate('investigate');
                  setTenant(record.tenant);
                  setPeriod(record.period);
                  setFeature(record.feature);
                }}
              />
            )}
            {view === 'actions' && records.status === 'ready' && (
              <ActionBoard
                actions={records.actions}
                diagnoses={records.diagnoses}
                search={search}
                setSearch={setSearch}
                filter={filter}
                setFilter={setFilter}
                edit={(record) => {
                  const diagnosis = records.diagnoses.find(
                    (item) => item.id === record.diagnosis_id,
                  );
                  if (diagnosis)
                    setEditor({ kind: 'action', record, diagnosis });
                  else
                    setNotice(
                      'The linked diagnosis is unavailable. Refresh your saved records before editing this action.',
                    );
                }}
                openDiagnosis={(id) => {
                  navigate('diagnoses');
                  setDiagnosisId(id);
                }}
              />
            )}
            <footer className="border-t pt-400 text-200 leading-300 text-muted-foreground">
              Live source: ProductAnalytics_Safe. Synthetic observations, not
              customer facts. No source data is changed. Diagnoses are
              user-authored hypotheses, not automated recommendations.
            </footer>
          </main>
        </div>
      </div>
    </div>
  );
}
