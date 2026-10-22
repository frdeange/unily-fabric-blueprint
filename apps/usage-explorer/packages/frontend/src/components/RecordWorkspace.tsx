import {
  ArrowRight,
  BookOpen,
  CalendarDays,
  CircleCheck,
  Pencil,
  Plus,
  UserRound,
} from 'lucide-react';
import { ACTION_STATUSES } from '@rayfin-app/shared';
import type { DiagnosisRecord, FollowUpRecord } from '@rayfin-app/shared';

import { dueLabel, isOverdue, numberLabel, periodLabel } from '@/lib/adoption';
import { Change, Empty } from './workbench-parts';

export function DiagnosisWorkspace({
  diagnoses,
  actions,
  selected,
  select,
  edit,
  addAction,
  inspect,
}: {
  diagnoses: DiagnosisRecord[];
  actions: FollowUpRecord[];
  selected?: DiagnosisRecord;
  select: (id: string) => void;
  edit: (record: DiagnosisRecord) => void;
  addAction: (record: DiagnosisRecord) => void;
  inspect: (record: DiagnosisRecord) => void;
}) {
  if (!diagnoses.length)
    return (
      <Empty title="Start with an observation, not an empty task">
        Investigate a tenant, choose the whole tenant or a feature, and capture
        your first diagnosis. The source figures and your interpretation stay
        together.
      </Empty>
    );
  return (
    <div className="grid items-start gap-500 lg:grid-cols-3">
      <section aria-label="Saved diagnoses" className="space-y-300">
        {diagnoses.map((record) => (
          <button
            key={record.id}
            onClick={() => select(record.id)}
            aria-pressed={selected?.id === record.id}
            className={`w-full rounded-2xl border bg-card p-500 text-left ${selected?.id === record.id ? 'border-primary' : ''}`}
          >
            <p className="wb-eyebrow">
              {record.tenant} / {periodLabel(record.period)}
            </p>
            <h3 className="mt-200 font-semibold">{record.title}</h3>
            <div className="mt-300 flex items-center justify-between text-200 text-muted-foreground">
              <span>{record.feature || 'All features'}</span>
              <span>
                {
                  actions.filter((action) => action.diagnosis_id === record.id)
                    .length
                }{' '}
                actions
              </span>
            </div>
          </button>
        ))}
      </section>
      {selected && (
        <section className="wb-panel lg:col-span-2">
          <div className="flex flex-wrap items-start justify-between gap-300">
            <div>
              <p className="wb-eyebrow">Saved evidence / Private to you</p>
              <h2 className="mt-200 text-600 font-semibold">
                {selected.title}
              </h2>
            </div>
            <button className="wb-secondary" onClick={() => edit(selected)}>
              <Pencil className="icon-size-200" /> Edit diagnosis
            </button>
          </div>
          <p className="mt-200 text-300 text-muted-foreground">
            {selected.tenant} / {periodLabel(selected.period)} /{' '}
            {selected.feature || 'All features'}
          </p>
          <div className="mt-500 rounded-xl bg-muted p-400">
            <p className="text-200 font-semibold">
              Evidence snapshot captured{' '}
              {new Date(selected.capturedAt).toLocaleString('en')}
            </p>
            <p className="mt-100 text-200 text-muted-foreground">
              ProductAnalytics_Safe / synthetic lab / saved figures, not a live
              refresh
            </p>
          </div>
          <dl className="mt-500 grid gap-400 sm:grid-cols-3">
            <div>
              <dt className="text-300 text-muted-foreground">Events</dt>
              <dd className="my-200 font-numeric text-600 font-semibold">
                {numberLabel(selected.events)}
              </dd>
              <Change
                value={selected.events}
                previous={selected.previousEvents}
              />
            </div>
            <div>
              <dt className="text-300 text-muted-foreground">Active users</dt>
              <dd className="my-200 font-numeric text-600 font-semibold">
                {numberLabel(selected.activeUsers)}
              </dd>
              <Change
                value={selected.activeUsers}
                previous={selected.previousUsers}
              />
            </div>
            <div>
              <dt className="text-300 text-muted-foreground">Avg. duration</dt>
              <dd className="my-200 font-numeric text-600 font-semibold">
                {selected.avgDuration == null
                  ? 'N/A'
                  : `${selected.avgDuration.toFixed(1)} s`}
              </dd>
            </div>
          </dl>
          <div className="mt-600 border-t pt-500">
            <h3 className="font-semibold">Your interpretation</h3>
            <p className="mt-200 whitespace-pre-wrap text-300 leading-400 text-muted-foreground">
              {selected.notes ||
                'No interpretation added yet. Edit this diagnosis to record your hypothesis.'}
            </p>
          </div>
          <div className="mt-500 flex flex-wrap gap-300">
            <button className="wb-primary" onClick={() => addAction(selected)}>
              <Plus className="icon-size-200" /> Add follow-up action
            </button>
            <button className="wb-secondary" onClick={() => inspect(selected)}>
              <BookOpen className="icon-size-200" /> Revisit live context
            </button>
          </div>
          <div className="mt-600 border-t pt-500">
            <h3 className="font-semibold">Linked follow-ups</h3>
            <ul className="mt-300 space-y-300">
              {actions
                .filter((action) => action.diagnosis_id === selected.id)
                .map((action) => (
                  <li
                    key={action.id}
                    className="flex flex-wrap justify-between gap-200 rounded-xl border p-300"
                  >
                    <span>{action.title}</span>
                    <span className="text-200 text-muted-foreground">
                      {action.status} / {dueLabel(action.dueDate)}
                    </span>
                  </li>
                ))}
            </ul>
            {!actions.some((action) => action.diagnosis_id === selected.id) && (
              <p className="mt-200 text-300 text-muted-foreground">
                No follow-ups yet. Turn your interpretation into a concrete next
                step.
              </p>
            )}
          </div>
        </section>
      )}
    </div>
  );
}

export function ActionBoard({
  actions,
  diagnoses,
  search,
  setSearch,
  filter,
  setFilter,
  edit,
  openDiagnosis,
}: {
  actions: FollowUpRecord[];
  diagnoses: DiagnosisRecord[];
  search: string;
  setSearch: (value: string) => void;
  filter: string;
  setFilter: (value: string) => void;
  edit: (record: FollowUpRecord) => void;
  openDiagnosis: (id: string) => void;
}) {
  const matching = actions.filter((action) => {
    const diagnosis = diagnoses.find(
      (record) => record.id === action.diagnosis_id,
    );
    const matchesSearch =
      `${action.title} ${diagnosis?.tenant ?? ''} ${diagnosis?.title ?? ''}`
        .toLowerCase()
        .includes(search.toLowerCase());
    return (
      matchesSearch &&
      (filter !== 'overdue' || isOverdue(action.dueDate, action.status)) &&
      (filter !== 'high' || action.priority === 'High')
    );
  });
  return (
    <div className="space-y-500">
      <div className="flex flex-wrap items-end justify-between gap-400">
        <div>
          <p className="wb-eyebrow">03 / Follow through</p>
          <h2 className="mt-100 text-600 font-semibold">
            Evidence becomes useful when someone acts
          </h2>
        </div>
        <div className="flex flex-wrap gap-300">
          <label className="wb-field">
            Find an action
            <input
              className="wb-input"
              type="search"
              placeholder="Title, tenant or diagnosis"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <label className="wb-field">
            Show
            <select
              className="wb-input"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
            >
              <option value="all">All actions</option>
              <option value="overdue">Overdue only (UTC)</option>
              <option value="high">High priority</option>
            </select>
          </label>
        </div>
      </div>
      {!actions.length ? (
        <Empty title="Your action board is ready">
          Create an action from a saved diagnosis. Every follow-up stays linked
          to the evidence that motivated it.
        </Empty>
      ) : matching.length === 0 ? (
        <Empty title="No actions match these filters">
          Change the search or filter to see your other actions.
        </Empty>
      ) : (
        <div className="grid gap-400 lg:grid-cols-3">
          {ACTION_STATUSES.map((status) => {
            const rows = matching.filter((action) => action.status === status);
            return (
              <section
                key={status}
                aria-label={`${status} actions`}
                className="rounded-2xl border bg-muted p-400"
              >
                <div className="mb-400 flex items-center justify-between">
                  <h3 className="flex items-center gap-200 font-semibold">
                    {status === 'Done' && (
                      <CircleCheck className="icon-size-200" />
                    )}
                    {status}
                  </h3>
                  <span className="rounded-full bg-card px-300 py-100 text-200">
                    {rows.length}
                  </span>
                </div>
                <div className="space-y-300">
                  {rows.map((action) => {
                    const diagnosis = diagnoses.find(
                      (record) => record.id === action.diagnosis_id,
                    );
                    return (
                      <article
                        key={action.id}
                        className="rounded-xl border bg-card p-400"
                      >
                        <div className="flex items-center justify-between gap-200">
                          <span
                            className={
                              action.priority === 'High'
                                ? 'wb-badge text-primary'
                                : 'wb-badge'
                            }
                          >
                            {action.priority} priority
                          </span>
                          <button
                            className="text-primary"
                            aria-label={`Edit ${action.title}`}
                            onClick={() => edit(action)}
                          >
                            <Pencil className="icon-size-200" />
                          </button>
                        </div>
                        <h4 className="mt-300 font-semibold">{action.title}</h4>
                        <p className="mt-200 whitespace-pre-wrap text-300 text-muted-foreground">
                          {action.notes || 'No additional notes.'}
                        </p>
                        <button
                          className="mt-400 flex items-center gap-100 text-left text-200 text-primary hover:underline"
                          onClick={() => openDiagnosis(action.diagnosis_id)}
                        >
                          {diagnosis?.tenant ?? 'Saved diagnosis'} /{' '}
                          {diagnosis?.title ?? 'Open evidence'}
                          <ArrowRight className="icon-size-100 shrink-0" />
                        </button>
                        <div className="mt-400 flex flex-wrap justify-between gap-200 border-t pt-300 text-200 text-muted-foreground">
                          <span className="inline-flex items-center gap-100">
                            <UserRound className="icon-size-100" /> You
                          </span>
                          <span
                            className={`inline-flex items-center gap-100 ${isOverdue(action.dueDate, action.status) ? 'text-destructive' : ''}`}
                          >
                            <CalendarDays className="icon-size-100" />
                            {isOverdue(action.dueDate, action.status)
                              ? 'Overdue / '
                              : ''}
                            {dueLabel(action.dueDate)}
                          </span>
                        </div>
                      </article>
                    );
                  })}
                  {!rows.length && (
                    <p className="p-400 text-300 text-muted-foreground">
                      No matching actions in this stage.
                    </p>
                  )}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
