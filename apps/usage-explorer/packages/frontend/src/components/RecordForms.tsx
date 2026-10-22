import { useId, useState } from 'react';
import type { ReactNode } from 'react';
import { X } from 'lucide-react';
import { ACTION_PRIORITIES, ACTION_STATUSES } from '@rayfin-app/shared';
import type { DiagnosisRecord, FollowUpRecord } from '@rayfin-app/shared';

import type { AdoptionRow } from '@/lib/adoption';
import { numberLabel, periodLabel } from '@/lib/adoption';
import { Notice } from './workbench-parts';

function Editor({
  title,
  children,
  close,
  pending,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
  pending: boolean;
}) {
  return (
    <section className="wb-panel border-primary" aria-label={title}>
      <div className="mb-500 flex items-center justify-between gap-300">
        <h2 className="text-600 font-semibold">{title}</h2>
        <button
          className="wb-secondary"
          disabled={pending}
          onClick={close}
          aria-label="Close editor"
        >
          <X className="icon-size-200" />
        </button>
      </div>
      {children}
    </section>
  );
}

export function DiagnosisForm({
  evidence,
  previous,
  existing,
  save,
  close,
}: {
  evidence?: AdoptionRow;
  previous?: AdoptionRow;
  existing?: DiagnosisRecord;
  save: (input: Omit<DiagnosisRecord, 'id' | 'owner_id'>) => Promise<void>;
  close: () => void;
}) {
  const id = useId();
  const [title, setTitle] = useState(
    existing?.title ??
      `${evidence?.feature || 'Adoption review'} / ${evidence?.tenant ?? ''}`,
  );
  const [notes, setNotes] = useState(existing?.notes ?? '');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const capturedAt = useState(() => new Date())[0];
  return (
    <Editor
      title={
        existing ? 'Edit your diagnosis' : 'Capture an evidence-based diagnosis'
      }
      close={close}
      pending={pending}
    >
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          if (!title.trim() || pending || (!existing && !evidence)) return;
          setPending(true);
          setError('');
          try {
            const source = existing ?? {
              tenant: evidence!.tenant,
              period: evidence!.period,
              feature: evidence!.feature ?? '',
              events: evidence!.events,
              activeUsers: evidence!.activeUsers,
              avgDuration: evidence!.avgDuration,
              previousEvents: previous?.events ?? null,
              previousUsers: previous?.activeUsers ?? null,
              capturedAt,
            };
            await save({ ...source, title: title.trim(), notes: notes.trim() });
          } catch {
            setError(
              'The diagnosis could not be saved. Your text is still here. Check your connection and data-service access, then retry.',
            );
          } finally {
            setPending(false);
          }
        }}
        className="space-y-400"
      >
        <fieldset disabled={pending} className="space-y-400">
          <div className="rounded-xl bg-muted p-400 text-300">
            <strong>{existing?.tenant ?? evidence?.tenant}</strong> /{' '}
            {periodLabel(existing?.period ?? evidence!.period)} /{' '}
            {existing?.feature || evidence?.feature || 'All features'}
            <p className="mt-100 text-muted-foreground">
              {numberLabel(existing?.events ?? evidence!.events)} events and{' '}
              {numberLabel(existing?.activeUsers ?? evidence!.activeUsers)}{' '}
              active users. Figures are stored as a snapshot; they will not
              silently refresh.
            </p>
          </div>
          <label htmlFor={`${id}-title`} className="wb-field">
            Diagnosis title
            <input
              id={`${id}-title`}
              required
              maxLength={160}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className="wb-input"
            />
          </label>
          <label htmlFor={`${id}-notes`} className="wb-field">
            Your interpretation
            <textarea
              id={`${id}-notes`}
              maxLength={2000}
              rows={4}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="What do these observations suggest? What would you verify with the customer?"
              className="wb-input"
            />
          </label>
          <p className="text-200 text-muted-foreground">
            Private to your signed-in account. Do not include personal data or
            confidential customer information.
          </p>
        </fieldset>
        {error && <Notice title="Save failed">{error}</Notice>}
        <div className="flex gap-300">
          <button
            className="wb-primary"
            disabled={pending || !title.trim()}
            type="submit"
          >
            {pending
              ? 'Saving...'
              : existing
                ? 'Save changes'
                : 'Save diagnosis'}
          </button>
          <button
            className="wb-secondary"
            type="button"
            disabled={pending}
            onClick={close}
          >
            Cancel
          </button>
        </div>
      </form>
    </Editor>
  );
}

export function ActionForm({
  diagnosis,
  existing,
  save,
  close,
}: {
  diagnosis: DiagnosisRecord;
  existing?: FollowUpRecord;
  save: (
    input: Pick<
      FollowUpRecord,
      'title' | 'notes' | 'priority' | 'dueDate' | 'status'
    >,
  ) => Promise<void>;
  close: () => void;
}) {
  const id = useId();
  const [title, setTitle] = useState(existing?.title ?? '');
  const [notes, setNotes] = useState(existing?.notes ?? '');
  const [priority, setPriority] = useState(existing?.priority ?? 'Normal');
  const [status, setStatus] = useState(existing?.status ?? 'Planned');
  const [dueDate, setDueDate] = useState(existing?.dueDate ?? '');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  return (
    <Editor
      title={
        existing
          ? 'Edit follow-up action'
          : 'Turn this diagnosis into an action'
      }
      close={close}
      pending={pending}
    >
      <form
        className="space-y-400"
        onSubmit={async (event) => {
          event.preventDefault();
          if (!title.trim() || pending) return;
          setPending(true);
          setError('');
          try {
            await save({
              title: title.trim(),
              notes: notes.trim(),
              priority,
              status,
              dueDate,
            });
          } catch {
            setError(
              'The action could not be saved. Your edits are still here. Check your connection and data-service access, then retry.',
            );
          } finally {
            setPending(false);
          }
        }}
      >
        <p className="rounded-xl bg-muted p-400 text-300">
          Linked to <strong>{diagnosis.title}</strong>. Responsible owner:{' '}
          <strong>You</strong>.
        </p>
        <fieldset disabled={pending} className="space-y-400">
          <label htmlFor={`${id}-title`} className="wb-field">
            Action title
            <input
              id={`${id}-title`}
              className="wb-input"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={160}
              required
              placeholder="For example: validate the feature-adoption hypothesis"
            />
          </label>
          <label htmlFor={`${id}-notes`} className="wb-field">
            Plan and success criteria
            <textarea
              id={`${id}-notes`}
              className="wb-input"
              rows={3}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              maxLength={2000}
            />
          </label>
          <div className="grid gap-400 sm:grid-cols-3">
            <label className="wb-field">
              Priority
              <select
                className="wb-input"
                value={priority}
                onChange={(event) => {
                  const value = ACTION_PRIORITIES.find(
                    (item) => item === event.target.value,
                  );
                  if (value) setPriority(value);
                }}
              >
                {ACTION_PRIORITIES.map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
            <label className="wb-field">
              Due date
              <input
                type="date"
                className="wb-input"
                value={dueDate}
                onChange={(event) => setDueDate(event.target.value)}
              />
            </label>
            <label className="wb-field">
              Status
              <select
                className="wb-input"
                disabled={!existing}
                value={status}
                onChange={(event) => {
                  const value = ACTION_STATUSES.find(
                    (item) => item === event.target.value,
                  );
                  if (value) setStatus(value);
                }}
              >
                {ACTION_STATUSES.map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
          </div>
        </fieldset>
        {error && <Notice title="Save failed">{error}</Notice>}
        <div className="flex gap-300">
          <button
            className="wb-primary"
            disabled={pending || !title.trim()}
            type="submit"
          >
            {pending ? 'Saving...' : existing ? 'Save action' : 'Create action'}
          </button>
          <button
            type="button"
            className="wb-secondary"
            disabled={pending}
            onClick={close}
          >
            Cancel
          </button>
        </div>
      </form>
    </Editor>
  );
}
