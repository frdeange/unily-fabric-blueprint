import { beforeEach, describe, expect, it, vi } from 'vitest';

const client = vi.hoisted(() => ({
  auth: { getSession: vi.fn() },
  data: {
    Diagnosis: { create: vi.fn(), findById: vi.fn(), update: vi.fn() },
    FollowUp: { create: vi.fn(), update: vi.fn() },
  },
}));
vi.mock('@/lib/rayfin-client', () => ({ getRayfinClient: async () => client }));

import {
  collectPages,
  createDiagnosis,
  createFollowUp,
  updateFollowUp,
} from './workbench-repository';

describe('complete lists', () => {
  it('follows all pages rather than stopping at the default first page', async () => {
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce({
        items: [1],
        hasNextPage: true,
        endCursor: 'next',
      })
      .mockResolvedValueOnce({ items: [2], hasNextPage: false });
    expect(await collectPages(fetchPage)).toEqual([1, 2]);
    expect(fetchPage).toHaveBeenLastCalledWith('next');
  });
  it('fails visibly if a service repeats or omits a cursor', async () => {
    await expect(
      collectPages(async () => ({
        items: [],
        hasNextPage: true,
        endCursor: 'same',
      })),
    ).rejects.toThrow(/did not advance/);
    await expect(
      collectPages(async () => ({ items: [], hasNextPage: true })),
    ).rejects.toThrow(/did not advance/);
  });
});

describe('writes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    client.auth.getSession.mockReturnValue({
      isAuthenticated: true,
      user: { id: 'session-owner' },
    });
  });
  it('stamps the authenticated owner rather than trusting user-entered ownership', async () => {
    const input = {
      title: 'Review',
      notes: '',
      tenant: 'tenant_example',
      period: '2026-09',
      feature: '',
      events: 120,
      activeUsers: 5,
      capturedAt: new Date(),
    };
    client.data.Diagnosis.create.mockResolvedValue({
      ...input,
      id: 'saved',
      owner_id: 'session-owner',
    });
    const saved = await createDiagnosis(input);
    expect(client.data.Diagnosis.create).toHaveBeenCalledWith({
      ...input,
      owner_id: 'session-owner',
    });
    expect(saved.id).toBe('saved');
  });
  it('requires an authenticated session before creating a row', async () => {
    client.auth.getSession.mockReturnValue({ isAuthenticated: false });
    await expect(
      createFollowUp({
        diagnosis_id: 'parent',
        title: 'Follow up',
        notes: '',
        priority: 'Normal',
        dueDate: '',
      }),
    ).rejects.toThrow(/Sign in/);
    expect(client.data.FollowUp.create).not.toHaveBeenCalled();
  });
  it('refuses to create a follow-up for an inaccessible parent', async () => {
    client.data.Diagnosis.findById.mockResolvedValue(null);
    await expect(
      createFollowUp({
        diagnosis_id: 'parent',
        title: 'Follow up',
        notes: '',
        priority: 'Normal',
        dueDate: '',
      }),
    ).rejects.toThrow(/no longer available/);
    expect(client.data.FollowUp.create).not.toHaveBeenCalled();
  });
  it('starts actions planned and only patches editable action fields', async () => {
    client.data.Diagnosis.findById.mockResolvedValue({ id: 'parent' });
    await createFollowUp({
      diagnosis_id: 'parent',
      title: 'Follow up',
      notes: '',
      priority: 'High',
      dueDate: '2026-09-01',
    });
    expect(client.data.FollowUp.create).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'Planned', owner_id: 'session-owner' }),
    );
    await updateFollowUp('saved', {
      title: 'Follow up',
      notes: '',
      status: 'Done',
      priority: 'High',
      dueDate: '',
    });
    expect(client.data.FollowUp.update).toHaveBeenCalledWith(
      { id: 'saved' },
      expect.not.objectContaining({ owner_id: expect.anything() }),
    );
  });
});
