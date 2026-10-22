import type { DiagnosisRecord, FollowUpRecord } from '@rayfin-app/shared';

import { getRayfinClient } from '@/lib/rayfin-client';

interface Page<T> {
  items: T[];
  hasNextPage: boolean;
  endCursor?: string | null;
}

export async function collectPages<T>(
  fetchPage: (cursor?: string) => Promise<Page<T>>,
): Promise<T[]> {
  const rows: T[] = [];
  let cursor: string | undefined;
  const seen = new Set<string>();
  for (let pageNumber = 0; pageNumber < 40; pageNumber++) {
    const page = await fetchPage(cursor);
    rows.push(...page.items);
    if (!page.hasNextPage) return rows;
    if (!page.endCursor || seen.has(page.endCursor))
      throw new Error('The records cursor did not advance.');
    seen.add(page.endCursor);
    cursor = page.endCursor;
  }
  throw new Error(
    'More than 2,000 saved records. Narrow the workspace before loading it.',
  );
}

export async function loadWorkbench() {
  const client = await getRayfinClient();
  const [diagnoses, actions] = await Promise.all([
    collectPages<DiagnosisRecord>(async (cursor) => {
      let query = client.data.Diagnosis.select([
        'id',
        'title',
        'notes',
        'owner_id',
        'tenant',
        'period',
        'feature',
        'events',
        'activeUsers',
        'avgDuration',
        'previousEvents',
        'previousUsers',
        'capturedAt',
      ])
        .orderBy({ capturedAt: 'desc', id: 'asc' })
        .first(50);
      if (cursor) query = query.after(cursor);
      return query.executePaginated();
    }),
    collectPages<FollowUpRecord>(async (cursor) => {
      let query = client.data.FollowUp.select([
        'id',
        'diagnosis_id',
        'title',
        'notes',
        'owner_id',
        'status',
        'priority',
        'dueDate',
        'createdAt',
        'updatedAt',
      ])
        .orderBy({ createdAt: 'desc', id: 'asc' })
        .first(50);
      if (cursor) query = query.after(cursor);
      return query.executePaginated();
    }),
  ]);
  return { diagnoses, actions };
}

async function currentOwner() {
  const client = await getRayfinClient();
  const session = client.auth.getSession();
  if (!session.isAuthenticated || !session.user?.id) {
    throw new Error('Sign in again before saving a record.');
  }
  return { client, owner_id: session.user.id };
}

export async function createDiagnosis(
  input: Omit<DiagnosisRecord, 'id' | 'owner_id'>,
) {
  const { client, owner_id } = await currentOwner();
  return client.data.Diagnosis.create({ ...input, owner_id });
}

export async function updateDiagnosis(
  id: string,
  patch: Pick<DiagnosisRecord, 'title' | 'notes'>,
) {
  return (await getRayfinClient()).data.Diagnosis.update({ id }, patch);
}

export async function createFollowUp(
  input: Pick<
    FollowUpRecord,
    'diagnosis_id' | 'title' | 'notes' | 'dueDate' | 'priority'
  >,
) {
  const { client, owner_id } = await currentOwner();
  const parent = await client.data.Diagnosis.findById(input.diagnosis_id);
  if (!parent)
    throw new Error(
      'The selected diagnosis is no longer available. Refresh your workspace.',
    );
  return client.data.FollowUp.create({
    ...input,
    owner_id,
    status: 'Planned',
    createdAt: new Date(),
    updatedAt: new Date(),
  });
}

export async function updateFollowUp(
  id: string,
  patch: Pick<
    FollowUpRecord,
    'title' | 'notes' | 'dueDate' | 'priority' | 'status'
  >,
) {
  return (await getRayfinClient()).data.FollowUp.update(
    { id },
    { ...patch, updatedAt: new Date() },
  );
}
